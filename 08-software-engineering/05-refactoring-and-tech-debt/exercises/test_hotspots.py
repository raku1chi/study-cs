"""8.5 演習1 — ホットスポットと変更の結合の分析のテスト

実行: python3 tools/check.py 8.5   （またはこのディレクトリで python3 -m unittest -v test_hotspots）

データ: exercises/data/hotspots/ に、架空の EC サイトの 1 年分の Git の履歴（git_log.txt）と、
現在のソースコード（repo/）があります。履歴は本物の Git で作ったものです。
"""
import unittest
from datetime import date
from pathlib import Path

from hotspots import Churn, Commit, Coupling, FileChange, Hotspot, churn, complexity, hotspots, parse_log, temporal_coupling

DATA = Path(__file__).parent / "data" / "hotspots"
LOG = (DATA / "git_log.txt").read_text(encoding="utf-8")
ROOT = DATA / "repo"

INVOICE = "shop/billing/invoice.py"
TAX = "shop/billing/tax.py"
MAIL = "shop/notifications/email_templates.py"
MODELS = "shop/orders/models.py"
SERVICE = "shop/orders/service.py"
REPORT = "shop/legacy/report_generator.py"
TEST_INVOICE = "tests/test_invoice.py"


class TestParseLog(unittest.TestCase):
    def test_small_example(self):
        text = (
            "--abc1234--2026-09-02--Alice\n"
            "6\t4\tshop/billing/invoice.py\n"
            "1\t0\tdocs/メモ.txt\n"
            "\n"
            "--def5678--2026-08-19--Bob -- the builder\n"
            "-\t-\tassets/logo.png\n"
            "\n"
            "--0000000--2026-08-01--Carol\n"
        )
        commits = parse_log(text)
        self.assertEqual(len(commits), 3)
        self.assertIsInstance(commits[0], Commit)
        self.assertEqual(commits[0], Commit("abc1234", date(2026, 9, 2), "Alice", (
            FileChange("shop/billing/invoice.py", 6, 4), FileChange("docs/メモ.txt", 1, 0))))
        self.assertEqual(commits[1].author, "Bob -- the builder", "作者名の中の -- で分割しない")
        self.assertEqual(commits[1].changes, (FileChange("assets/logo.png", None, None),))
        self.assertEqual(commits[2].changes, (), "変更のないコミットも含める")

    def test_fixture(self):
        commits = parse_log(LOG)
        self.assertEqual(len(commits), 31)
        newest, oldest = commits[0], commits[-1]
        self.assertEqual((newest.date, newest.author), (date(2026, 9, 16), "Carol"))
        self.assertEqual((oldest.date, oldest.author, len(oldest.changes)), (date(2025, 10, 1), "Dave", 11))

    def test_invalid_logs(self):
        bad_logs = [
            "6\t4\tfile.py\n",                             # 見出しより前に変更の行
            "--abc--2026-01-01--A\n6\t4\n",                # 項目が 2 つしかない
            "--abc--2026-01-01--A\nx\t4\tfile.py\n",       # 行数が数字でない
            "--abc--2026-13-01--A\n",                      # 日付が不正
            "--abc--2026-01-01\n",                         # 作者がない
        ]
        for text in bad_logs:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse_log(text)


class TestChurn(unittest.TestCase):
    def setUp(self):
        self.commits = parse_log(LOG)

    def test_revisions_and_lines(self):
        c = churn(self.commits)
        self.assertEqual(c[INVOICE], Churn(18, 154, 102))
        self.assertEqual(c[MODELS].revisions, 10)
        self.assertEqual(c[REPORT].revisions, 2, "初期インポートと一括のヘッダ削除だけ")
        self.assertEqual(c["assets/logo.png"], Churn(2, 0, 0), "バイナリは行数 0 として数える")
        self.assertEqual(c["shop/billing/old_discount.py"].revisions, 3, "削除されたファイルも履歴には残る")

    def test_since(self):
        c = churn(self.commits, since=date(2026, 4, 1))
        self.assertEqual(c[INVOICE].revisions, 6)
        self.assertNotIn(REPORT, c)
        self.assertEqual(churn(self.commits, since=date(2026, 9, 16))[MODELS].revisions, 1, "その日を含む")


class TestComplexity(unittest.TestCase):
    def test_counts_decisions_in_the_whole_file(self):
        self.assertEqual(complexity("x = 1\n"), 1)
        source = (
            "import sys\n"
            "if sys.argv:\n"                       # +1（モジュールの直下も数える）
            "    pass\n"
            "def f(xs, a, b):\n"
            "    for x in xs:\n"                   # +1
            "        if x and a or b:\n"           # +1、and/or で +2
            "            pass\n"
            "    try:\n"
            "        return [y for y in xs if y]\n"  # 内包表記 +2
            "    except (KeyError, ValueError):\n"   # +1
            "        return 0 if a else 1\n"           # +1
        )
        self.assertEqual(complexity(source), 1 + 1 + 1 + 1 + 2 + 2 + 1 + 1)

    def test_fixture_files(self):
        self.assertEqual(complexity((ROOT / INVOICE).read_text(encoding="utf-8")), 29)
        self.assertEqual(complexity((ROOT / REPORT).read_text(encoding="utf-8")), 24)

    def test_syntax_error(self):
        with self.assertRaises(SyntaxError):
            complexity("def broken(:\n")


class TestHotspots(unittest.TestCase):
    def setUp(self):
        self.commits = parse_log(LOG)

    def test_ranking(self):
        result = hotspots(self.commits, ROOT)
        self.assertIsInstance(result[0], Hotspot)
        self.assertEqual(result[0], Hotspot(INVOICE, 18, 29, 522))
        self.assertEqual([h.path for h in result[:3]], [INVOICE, SERVICE, TAX])
        scores = [h.score for h in result]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_complex_but_untouched_code_is_not_a_top_hotspot(self):
        result = hotspots(self.commits, ROOT)
        paths = [h.path for h in result]
        report = result[paths.index(REPORT)]
        self.assertEqual((report.complexity, report.revisions), (24, 2))
        self.assertGreater(paths.index(REPORT), 2, "複雑でも、誰も変更しないコードの利子は小さい")

    def test_excludes_deleted_and_non_python_files(self):
        paths = {h.path for h in hotspots(self.commits, ROOT)}
        self.assertNotIn("shop/billing/old_discount.py", paths)
        self.assertNotIn("assets/logo.png", paths)
        self.assertNotIn("docs/operations.txt", paths)
        self.assertEqual(len(paths), 8)

    def test_top_and_since(self):
        recent = hotspots(self.commits, ROOT, since=date(2026, 4, 1), top=3)
        self.assertEqual(recent, [Hotspot(INVOICE, 6, 29, 174), Hotspot(SERVICE, 3, 7, 21), Hotspot(TAX, 3, 5, 15)])

    def test_skips_files_that_do_not_parse(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "ok.py").write_text("if x:\n    pass\n", encoding="utf-8")
            (Path(tmp) / "broken.py").write_text("def broken(:\n", encoding="utf-8")
            commits = parse_log("--a--2026-01-01--A\n1\t0\tok.py\n1\t0\tbroken.py\n")
            self.assertEqual(hotspots(commits, Path(tmp)), [Hotspot("ok.py", 1, 2, 2)])


class TestTemporalCoupling(unittest.TestCase):
    def setUp(self):
        self.commits = parse_log(LOG)

    def test_large_commits_are_ignored(self):
        result = temporal_coupling(self.commits, max_changeset_size=5)
        self.assertIsInstance(result[0], Coupling)
        pairs = [(c.a, c.b, c.shared) for c in result]
        self.assertEqual(pairs[0], (MODELS, SERVICE, 6))
        self.assertAlmostEqual(result[0].degree, 0.8)
        self.assertIn((INVOICE, MAIL, 6), pairs, "請求書とメールの文面が、見えない依存で一緒に変わっている")
        self.assertNotIn(MODELS, {c.a for c in result if c.b == "shop/utils/strings.py"},
                         "一括のコミットを除くと、偶然の組み合わせは消える")

    def test_ordering_and_values(self):
        result = temporal_coupling(self.commits, max_changeset_size=5)
        self.assertEqual(
            [(c.a, c.b) for c in result],
            [(MODELS, SERVICE), (INVOICE, TAX), (INVOICE, TEST_INVOICE), (INVOICE, MAIL),
             (TAX, MAIL), (TAX, TEST_INVOICE)],
        )
        self.assertAlmostEqual(result[1].degree, 2 / 3)
        self.assertAlmostEqual(result[3].degree, 6 / 11)

    def test_including_large_commits_adds_noise(self):
        pairs = {(c.a, c.b) for c in temporal_coupling(self.commits)}
        self.assertIn((MODELS, "shop/utils/strings.py"), pairs, "巨大なコミットを除かないと、偶然の組が現れる")

    def test_thresholds_and_since(self):
        everything = temporal_coupling(self.commits, max_changeset_size=5, min_shared=1, min_degree=0.0)
        self.assertEqual(len(everything), 10)
        self.assertTrue(all(c.a < c.b for c in everything))
        recent = temporal_coupling(self.commits, max_changeset_size=5, since=date(2026, 4, 1), min_shared=2)
        self.assertEqual([(c.a, c.b, c.shared) for c in recent][:2], [(MODELS, SERVICE, 2), (INVOICE, MAIL, 3)])

    def test_small_example(self):
        log = (
            "--c3--2026-01-03--A\n1\t0\ta.py\n1\t0\tb.py\n\n"
            "--c2--2026-01-02--A\n1\t0\ta.py\n1\t0\tb.py\n1\t0\tc.py\n\n"
            "--c1--2026-01-01--A\n1\t0\ta.py\n"
        )
        result = temporal_coupling(parse_log(log), min_shared=1, min_degree=0.0)
        by_pair = {(c.a, c.b): (c.shared, round(c.degree, 4)) for c in result}
        # a は 3 回、b は 2 回、c は 1 回変更。a と b は 2 回一緒 → 2 / 2.5 = 0.8
        self.assertEqual(by_pair, {("a.py", "b.py"): (2, 0.8), ("a.py", "c.py"): (1, 0.5), ("b.py", "c.py"): (1, 0.6667)})


if __name__ == "__main__":
    unittest.main()
