"""db.py（トランザクション・マイグレーション）とスキーマの制約のテスト。"""
from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from taskapi import db

NOW = "2026-04-01T09:00:00.000Z"


class DatabaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmpdir = Path(tmp.name)
        self.db_path = os.path.join(tmp.name, "test.db")
        self.conn = db.connect(self.db_path)
        self.addCleanup(self.conn.close)


class MigrationTest(DatabaseTestCase):
    def test_migrate_applies_all_then_is_idempotent(self) -> None:
        first = db.migrate(self.conn)
        self.assertEqual([m.version for m in first], [1])
        self.assertEqual(db.migrate(self.conn), [], "2 回目は何も適用しない")
        self.assertEqual(db.pending_migrations(self.conn), [])

    def test_all_tables_are_created(self) -> None:
        db.migrate(self.conn)
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertLessEqual({"tenants", "users", "projects", "tasks", "comments", "schema_migrations"}, tables)

    def test_file_name_rule_is_enforced(self) -> None:
        (self.tmpdir / "0001_ok.sql").write_text("CREATE TABLE a (x);", encoding="utf-8")
        (self.tmpdir / "2_bad-name.sql").write_text("CREATE TABLE b (x);", encoding="utf-8")
        with self.assertRaises(ValueError):
            db.discover_migrations(self.tmpdir)

    def test_failed_migration_is_rolled_back_entirely(self) -> None:
        migrations = self.tmpdir / "migrations"
        migrations.mkdir()
        (migrations / "0001_broken.sql").write_text(
            "CREATE TABLE a (x INTEGER);\nINSERT INTO no_such_table VALUES (1);\n", encoding="utf-8"
        )
        with self.assertRaises(sqlite3.OperationalError):
            db.migrate(self.conn, migrations)
        tables = {row[0] for row in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertNotIn("a", tables, "途中まで適用された状態が残ってはいけない")
        self.assertEqual([m.version for m in db.pending_migrations(self.conn, migrations)], [1])


class SplitSqlTest(unittest.TestCase):
    def test_comments_strings_and_triggers(self) -> None:
        script = """
-- コメント行; セミコロンを含んでも文の区切りではない
CREATE TABLE t (x TEXT DEFAULT 'a;b');

CREATE TRIGGER trg AFTER INSERT ON t BEGIN
    UPDATE t SET x = 'c' WHERE x = 'd';
END;
"""
        statements = db.split_sql_statements(script)
        self.assertEqual(len(statements), 2)
        self.assertTrue(statements[1].startswith("CREATE TRIGGER"))
        self.assertTrue(statements[1].endswith("END;"))

    def test_incomplete_statement_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            db.split_sql_statements("CREATE TABLE t (x TEXT)")


class TransactionTest(DatabaseTestCase):
    def test_commit_and_rollback(self) -> None:
        self.conn.execute("CREATE TABLE t (x INTEGER)")
        with db.transaction(self.conn):
            self.conn.execute("INSERT INTO t VALUES (1)")
        with self.assertRaises(RuntimeError):
            with db.transaction(self.conn):
                self.conn.execute("INSERT INTO t VALUES (2)")
                raise RuntimeError("途中で失敗")
        self.assertEqual([row[0] for row in self.conn.execute("SELECT x FROM t")], [1])

    def test_disk_full_reports_the_original_error(self) -> None:
        # max_page_count で DB ファイルを今より大きくできなくして、ディスクフルを再現する。
        # SQLite が自動でロールバックした後に ROLLBACK を重ねると、元のエラーが隠れてしまう
        self.conn.execute("CREATE TABLE t (x TEXT)")
        pages = self.conn.execute("PRAGMA page_count").fetchone()[0]
        self.conn.execute(f"PRAGMA max_page_count = {int(pages)}")
        with self.assertRaises(sqlite3.OperationalError) as ctx:
            with db.transaction(self.conn):
                for _ in range(1000):
                    self.conn.execute("INSERT INTO t VALUES (?)", ("x" * 500,))
        self.assertIn("full", str(ctx.exception), "ROLLBACK の失敗ではなく、ディスクフルが報告されること")
        self.assertFalse(self.conn.in_transaction)


class TenantIsolationSchemaTest(DatabaseTestCase):
    """スキーマ（複合外部キー）が、テナントをまたぐ参照を DB レベルで拒否することを確かめる。"""

    def setUp(self) -> None:
        super().setUp()
        db.migrate(self.conn)
        for tenant in ("ten_a", "ten_b"):
            self.conn.execute("INSERT INTO tenants VALUES (?, ?, ?)", (tenant, tenant, NOW))
        self.conn.execute("INSERT INTO projects VALUES ('ten_a', 'prj_a', 'A の案件', ?)", (NOW,))

    def insert_task(self, tenant_id: str, project_id: str) -> None:
        self.conn.execute(
            "INSERT INTO tasks (tenant_id, id, project_id, title, created_at, updated_at)"
            " VALUES (?, ?, ?, 'タスク', ?, ?)",
            (tenant_id, f"tsk_{tenant_id}", project_id, NOW, NOW),
        )

    def test_task_in_same_tenant_is_allowed(self) -> None:
        self.insert_task("ten_a", "prj_a")

    def test_task_pointing_to_other_tenants_project_is_rejected(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.insert_task("ten_b", "prj_a")

    def test_connect_enables_foreign_keys(self) -> None:
        # SQLite は接続ごとに PRAGMA foreign_keys = ON にしないと外部キーを検査しない。db.connect() がそれを行う
        with closing(db.connect(self.db_path)) as other:
            with self.assertRaises(sqlite3.IntegrityError):
                other.execute("INSERT INTO projects VALUES ('ten_x', 'prj_x', 'x', ?)", (NOW,))


if __name__ == "__main__":
    unittest.main()
