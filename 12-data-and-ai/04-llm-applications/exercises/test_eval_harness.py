"""12.4 演習3: 評価ハーネス — テスト

実行: python3 tools/check.py 12.4   （またはこのディレクトリで python3 -m unittest -v test_eval_harness）
"""
import math
import random
import unittest

from eval_harness import (
    BootstrapResult,
    ComparisonReport,
    EvalItem,
    JudgeVerdict,
    OverlapJudge,
    char_f1,
    compare_versions,
    exact_match,
    normalize_answer,
    paired_bootstrap,
    pairwise_preference,
    should_block_release,
    token_f1,
)

ITEMS = [
    EvalItem("q1", "コアタイムは？", ("11時から15時まで",)),
    EvalItem("q2", "在宅勤務は週何日まで？", ("週3日まで", "3日")),
    EvalItem("q3", "タクシーを使える条件は？", ("22時以降の移動または重い荷物がある場合",)),
    EvalItem("q4", "宿泊費の上限は？", ("1泊12,000円",)),
    EvalItem("q5", "経費精算の締め切りは？", ("翌月10日まで",)),
]
ANSWERS_A = {
    "コアタイムは？": "11時から15時です",
    "在宅勤務は週何日まで？": "週に3日までです",
    "タクシーを使える条件は？": "夜遅い場合",
    "宿泊費の上限は？": "12000円",
    "経費精算の締め切りは？": "月末まで",
}
ANSWERS_B = {
    "コアタイムは？": "11時から15時まで",
    "在宅勤務は週何日まで？": "3日",
    "タクシーを使える条件は？": "22時以降の移動か、重い荷物がある場合",
    "宿泊費の上限は？": "1泊12,000円",
    "経費精算の締め切りは？": "翌月末まで",
}


class TestMetrics(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_answer("  １泊　12,000円。 "), "1泊12000円")
        self.assertEqual(normalize_answer("Hello, World!"), "helloworld")
        self.assertEqual(normalize_answer("「はい」\n"), "はい")

    def test_exact_match(self):
        self.assertEqual(exact_match("1泊 12,000円", "１泊12000円"), 1.0)
        self.assertEqual(exact_match("12,000円", "1泊12,000円"), 0.0)
        self.assertEqual(exact_match("3日", ["週3日まで", "3日"]), 1.0, "参照解答が複数なら最大値")
        with self.assertRaises(ValueError):
            exact_match("x", [])

    def test_char_f1(self):
        self.assertEqual(char_f1("週3日まで", "週3日まで"), 1.0)
        # 予測「3日です」(4文字) と参照「週3日まで」(5文字) の共通は「3」「日」の 2 文字
        self.assertAlmostEqual(char_f1("3日です", "週3日まで"), 2 * (2 / 4) * (2 / 5) / (2 / 4 + 2 / 5))
        self.assertEqual(char_f1("まったく違う", "週3日まで"), 0.0)
        self.assertAlmostEqual(char_f1("ああい", "あい"), 2 * (2 / 3) * 1.0 / (2 / 3 + 1.0), msg="重複は多重集合で数える")
        self.assertEqual(char_f1("", ""), 1.0)
        self.assertEqual(char_f1("", "あ"), 0.0)
        self.assertEqual(char_f1("3日", ["週3日まで", "3日"]), 1.0)

    def test_token_f1(self):
        self.assertAlmostEqual(token_f1("the cat sat", "the cat is here"), 2 * (2 / 3) * (2 / 4) / (2 / 3 + 2 / 4))
        self.assertEqual(token_f1("The Cat!", "the cat"), 1.0)


class TestBootstrap(unittest.TestCase):
    def test_identical_and_constant_shift(self):
        same = paired_bootstrap([0.2, 0.5, 0.9], [0.2, 0.5, 0.9], n_resamples=200)
        self.assertEqual((same.diff, same.ci_low, same.ci_high, same.p_b_better), (0.0, 0.0, 0.0, 0.0))
        shifted = paired_bootstrap([0.1, 0.4, 0.2], [0.6, 0.9, 0.7], n_resamples=200)
        self.assertAlmostEqual(shifted.ci_low, 0.5)
        self.assertAlmostEqual(shifted.ci_high, 0.5)
        self.assertEqual(shifted.p_b_better, 1.0)
        self.assertIsInstance(shifted, BootstrapResult)

    def test_exact_algorithm(self):
        # 仕様どおりのアルゴリズム（各反復で rng.randrange(n) を n 回、順に呼ぶ）なら、この値になる
        a = [0, 1, 0, 1, 1, 0, 1, 0, 0, 1]
        b = [1, 1, 0, 1, 1, 1, 1, 0, 1, 1]
        r = paired_bootstrap(a, b, n_resamples=1000, seed=42)
        self.assertEqual((r.mean_a, r.mean_b), (0.5, 0.8))
        self.assertAlmostEqual(r.diff, 0.3)
        self.assertAlmostEqual(r.ci_low, 0.0)
        self.assertAlmostEqual(r.ci_high, 0.6)
        self.assertAlmostEqual(r.p_b_better, 0.948)

    def test_properties_on_random_data(self):
        rng = random.Random(7)
        a = [rng.random() for _ in range(80)]
        b = [x + 0.05 + rng.gauss(0, 0.1) for x in a]
        r = paired_bootstrap(a, b, n_resamples=500, seed=1)
        self.assertLessEqual(r.ci_low, r.diff)
        self.assertLessEqual(r.diff, r.ci_high)
        self.assertGreater(r.ci_low, 0.0, "一貫して良くなっているなら区間は 0 を含まない")
        self.assertEqual(r, paired_bootstrap(a, b, n_resamples=500, seed=1), "シードが同じなら同じ結果")
        narrow = paired_bootstrap(a, b, n_resamples=500, seed=1, confidence=0.5)
        self.assertLessEqual(narrow.ci_high - narrow.ci_low, r.ci_high - r.ci_low)

    def test_errors(self):
        with self.assertRaises(ValueError):
            paired_bootstrap([], [])
        with self.assertRaises(ValueError):
            paired_bootstrap([1.0], [1.0, 0.0])
        with self.assertRaises(ValueError):
            paired_bootstrap([1.0], [1.0], confidence=1.0)


class TestJudges(unittest.TestCase):
    def test_overlap_judge(self):
        judge = OverlapJudge()
        perfect = judge("q", "週3日まで", "週3日まで")
        self.assertIsInstance(perfect, JudgeVerdict)
        self.assertEqual(perfect.score, 5)
        self.assertEqual(judge("q", "わかりません", "週3日まで").score, 1)
        self.assertTrue(1 <= judge("q", "3日です", "週3日まで").score <= 5)

    def test_pairwise_cancels_position_bias(self):
        always_first = lambda q, x, y: "first"  # noqa: E731  いつも先に見せた方を選ぶ偏った審査員
        self.assertEqual(pairwise_preference(always_first, "q", "A の回答", "B の回答"), "tie")

        def longer_is_better(q, x, y):
            return "first" if len(x) > len(y) else "second" if len(y) > len(x) else "tie"

        self.assertEqual(pairwise_preference(longer_is_better, "q", "詳しい回答です", "短い"), "A")
        self.assertEqual(pairwise_preference(longer_is_better, "q", "短い", "詳しい回答です"), "B")
        with self.assertRaises(ValueError):
            pairwise_preference(lambda q, x, y: "A", "q", "a", "b")


class TestCompareVersions(unittest.TestCase):
    def test_report(self):
        report = compare_versions(ITEMS, ANSWERS_A.get, ANSWERS_B.get, n_resamples=500, seed=0)
        self.assertIsInstance(report, ComparisonReport)
        self.assertEqual(len(report.scores_a), 5)
        self.assertGreater(report.bootstrap.mean_b, report.bootstrap.mean_a)
        self.assertEqual(report.improvements, ["q1", "q2", "q3", "q4"])
        self.assertEqual(report.regressions, [], "q5 は A も B も同じくらい外れている")
        self.assertFalse(should_block_release(report))

    def test_regressions_are_listed_and_block_release(self):
        report = compare_versions(ITEMS, ANSWERS_B.get, ANSWERS_A.get, metric=exact_match, n_resamples=500)
        self.assertEqual(report.regressions, ["q1", "q2", "q4"])
        self.assertTrue(should_block_release(report))

    def test_tolerance(self):
        a = [1.0] * 50
        b = [1.0] * 49 + [0.0]  # 1 問だけ悪化（平均 -0.02）
        items = [EvalItem(f"q{i}", f"問{i}", ("x",)) for i in range(50)]
        answers_a = {f"問{i}": "x" for i in range(50)}
        answers_b = dict(answers_a, **{"問49": "y"})
        report = compare_versions(items, answers_a.get, answers_b.get, metric=exact_match, n_resamples=300)
        self.assertEqual([s for s in report.scores_a], a)
        self.assertEqual([s for s in report.scores_b], b)
        self.assertTrue(should_block_release(report, tolerance=0.0))
        self.assertFalse(should_block_release(report, tolerance=0.05), "許容幅の中の悪化は通す")
        self.assertEqual(report.regressions, ["q49"])

    def test_empty(self):
        with self.assertRaises(ValueError):
            compare_versions([], str, str)


if __name__ == "__main__":
    unittest.main()
