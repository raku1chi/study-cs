"""8.6 演習3 — ADR の管理ツールのテスト

実行: python3 tools/check.py 8.6   （またはこのディレクトリで python3 -m unittest -v test_adr_tool）
"""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from adr_tool import STATUSES, AdrInfo, list_adrs, new_adr, set_status, slugify, supersede

DAY = date(2026, 9, 28)

EXPECTED_FIRST = """# 1. PostgreSQL を主データベースに採用する

- 日付: 2026-09-28

## ステータス

提案中

## コンテキスト

（この決定が必要になった背景、制約、検討した選択肢を書く）

## 決定

（何をするか。「〜する」と能動態で書く）

## 結果

（この決定によって、何が容易になり、何が困難になるか。良い面も悪い面も書く）
"""


class AdrTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name) / "docs" / "adr"


class TestSlugify(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(slugify("Use PostgreSQL for the main DB"), "use-postgresql-for-the-main-db")
        self.assertEqual(slugify("ＰｏｓｔｇｒｅＳＱＬ を採用する"), "postgresql")
        self.assertEqual(slugify("認証方式の決定"), "decision")
        self.assertEqual(slugify("  API v2: Rate-Limit 100 req/s "), "api-v2-rate-limit-100-req-s")


class TestNewAndList(AdrTestCase):
    def test_first_adr_content(self):
        path = new_adr(self.dir, "PostgreSQL を主データベースに採用する", on=DAY, slug="use-postgresql")
        self.assertEqual(path, self.dir / "0001-use-postgresql.md", "ディレクトリがなければ作る")
        self.assertEqual(path.read_text(encoding="utf-8"), EXPECTED_FIRST)

    def test_numbering_continues_after_gaps(self):
        new_adr(self.dir, "Use PostgreSQL", on=DAY)
        (self.dir / "0007-imported.md").write_text("# 7. 他所から移した記録\n\n## ステータス\n\n承認済み\n", encoding="utf-8")
        path = new_adr(self.dir, "Adopt OpenTelemetry", on=DAY)
        self.assertEqual(path.name, "0008-adopt-opentelemetry.md", "最大の番号 + 1（欠番は埋めない）")

    def test_list(self):
        new_adr(self.dir, "Use PostgreSQL", on=DAY, status="承認済み")
        new_adr(self.dir, "認証に OIDC を使う", on=DAY)
        (self.dir / "README.md").write_text("ADR の一覧", encoding="utf-8")
        (self.dir / "template.md").write_text("# テンプレート", encoding="utf-8")
        adrs = list_adrs(self.dir)
        self.assertEqual([a.number for a in adrs], [1, 2])
        self.assertIsInstance(adrs[0], AdrInfo)
        self.assertEqual((adrs[0].title, adrs[0].status), ("Use PostgreSQL", "承認済み"))
        self.assertEqual((adrs[1].title, adrs[1].status, adrs[1].path.name), ("認証に OIDC を使う", "提案中", "0002-oidc.md"))
        self.assertEqual(list_adrs(self.dir / "nothing-here"), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            new_adr(self.dir, "   ", on=DAY)
        with self.assertRaises(ValueError):
            new_adr(self.dir, "Title", on=DAY, status="accepted")
        self.assertIn("承認済み", STATUSES)


class TestStatusAndSupersede(AdrTestCase):
    def test_set_status_changes_only_the_status_line(self):
        path = new_adr(self.dir, "PostgreSQL を主データベースに採用する", on=DAY, slug="use-postgresql")
        set_status(self.dir, 1, "承認済み")
        self.assertEqual(path.read_text(encoding="utf-8"), EXPECTED_FIRST.replace("\n提案中\n", "\n承認済み\n"))
        with self.assertRaises(KeyError):
            set_status(self.dir, 9, "承認済み")
        with self.assertRaises(ValueError):
            set_status(self.dir, 1, "done")

    def test_supersede_links_both_records(self):
        new_adr(self.dir, "PostgreSQL を主データベースに採用する", on=DAY, status="承認済み", slug="use-postgresql")
        new_adr(self.dir, "Use Redis for sessions", on=DAY, status="承認済み")
        path = supersede(self.dir, 1, "Migrate to Aurora PostgreSQL", on=date(2026, 10, 1))
        self.assertEqual(path.name, "0003-migrate-to-aurora-postgresql.md")

        new_text = path.read_text(encoding="utf-8")
        self.assertIn("- 日付: 2026-10-01\n", new_text)
        self.assertIn(
            "## ステータス\n\n承認済み\n\n置き換え元: [ADR-0001 PostgreSQL を主データベースに採用する](0001-use-postgresql.md)\n\n## コンテキスト",
            new_text,
        )
        old_text = (self.dir / "0001-use-postgresql.md").read_text(encoding="utf-8")
        self.assertIn(
            "## ステータス\n\n置き換え済み\n\n置き換え先: [ADR-0003 Migrate to Aurora PostgreSQL](0003-migrate-to-aurora-postgresql.md)\n\n## コンテキスト",
            old_text,
        )
        self.assertTrue(old_text.startswith("# 1. PostgreSQL を主データベースに採用する\n"), "ほかの部分は変えない")
        statuses = {a.number: a.status for a in list_adrs(self.dir)}
        self.assertEqual(statuses, {1: "置き換え済み", 2: "承認済み", 3: "承認済み"})

    def test_supersede_errors(self):
        new_adr(self.dir, "Use PostgreSQL", on=DAY, status="承認済み")
        with self.assertRaises(KeyError):
            supersede(self.dir, 5, "New", on=DAY)
        supersede(self.dir, 1, "Use Aurora", on=DAY)
        with self.assertRaises(ValueError, msg="すでに置き換えられた ADR は、もう一度置き換えられない"):
            supersede(self.dir, 1, "Use Spanner", on=DAY)
        self.assertEqual(len(list_adrs(self.dir)), 2, "失敗したときは新しい ADR を作らない")


if __name__ == "__main__":
    unittest.main()
