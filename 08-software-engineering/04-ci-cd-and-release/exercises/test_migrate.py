"""8.4 演習3 — マイグレーションの実行器と、拡張・縮小による列の改名のテスト

実行: python3 tools/check.py 8.4   （またはこのディレクトリで python3 -m unittest -v test_migrate）
"""
import hashlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from migrate import (
    ChecksumMismatchError,
    Migration,
    MigrationError,
    contract_sql,
    discover,
    expand_sql,
    migrate,
    status,
    switch_sql,
)

FIXED = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)
CREATE_USERS = "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);\n"


class MigrationTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)

    def write(self, filename, sql):
        (self.dir / filename).write_text(sql, encoding="utf-8")

    def tables(self):
        return {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def recorded(self):
        return self.conn.execute(
            "SELECT version, name, checksum, applied_at FROM schema_migrations ORDER BY version").fetchall()

    def run_migrate(self, **kwargs):
        return migrate(self.conn, self.dir, clock=lambda: FIXED, **kwargs)


class TestDiscover(MigrationTestCase):
    def test_sorted_by_version_and_ignores_other_files(self):
        self.write("0010_add_index.sql", "SELECT 1;")
        self.write("0002_add_orders.sql", "SELECT 1;")
        self.write("1_create_users.sql", CREATE_USERS)
        self.write("README.md", "説明")
        found = discover(self.dir)
        self.assertEqual([(m.version, m.name) for m in found], [(1, "create_users"), (2, "add_orders"), (10, "add_index")])
        self.assertIsInstance(found[0], Migration)
        self.assertEqual(found[0].checksum, hashlib.sha256(CREATE_USERS.encode()).hexdigest())

    def test_invalid_file_names(self):
        for bad in ("create_users.sql", "0001-create-users.sql", "0000_zero.sql", "0001_名前.sql"):
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / bad).write_text("SELECT 1;", encoding="utf-8")
                with self.assertRaises(MigrationError, msg=bad):
                    discover(Path(tmp))

    def test_duplicate_versions(self):
        self.write("0002_a.sql", "SELECT 1;")
        self.write("002_b.sql", "SELECT 2;")
        with self.assertRaises(MigrationError):
            discover(self.dir)


class TestMigrate(MigrationTestCase):
    def setUp(self):
        super().setUp()
        self.write("0001_create_users.sql", CREATE_USERS)
        self.write("0002_create_orders.sql",
                   "CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, note TEXT);\n"
                   "INSERT INTO orders (user_id, note) VALUES (1, 'セミコロン; を含む文字列');\n")

    def test_applies_in_order_and_records(self):
        self.assertEqual(self.run_migrate(), [1, 2])
        self.assertTrue({"users", "orders", "schema_migrations"} <= self.tables())
        rows = self.recorded()
        self.assertEqual([(v, n) for v, n, _, _ in rows], [(1, "create_users"), (2, "create_orders")])
        self.assertEqual(rows[0][2], hashlib.sha256(CREATE_USERS.encode()).hexdigest())
        self.assertEqual(rows[0][3], FIXED.isoformat())
        self.assertEqual(self.conn.execute("SELECT note FROM orders").fetchone()[0], "セミコロン; を含む文字列")

    def test_rerun_is_idempotent(self):
        self.run_migrate()
        self.assertEqual(self.run_migrate(), [])
        self.write("0003_add_email.sql", "ALTER TABLE users ADD COLUMN email TEXT;")
        self.assertEqual(self.run_migrate(), [3])
        self.assertEqual(len(self.recorded()), 3)

    def test_target(self):
        self.assertEqual(self.run_migrate(target=1), [1])
        self.assertNotIn("orders", self.tables())
        self.assertEqual(self.run_migrate(target=1), [])
        self.assertEqual(self.run_migrate(), [2])

    def test_failed_migration_is_rolled_back_entirely(self):
        self.write("0003_broken.sql",
                   "CREATE TABLE audit (id INTEGER PRIMARY KEY);\n"
                   "INSERT INTO no_such_table VALUES (1);\n")
        with self.assertRaises(MigrationError) as ctx:
            self.run_migrate()
        self.assertIn("broken", str(ctx.exception), "どのマイグレーションで失敗したかをメッセージに含める")
        self.assertNotIn("audit", self.tables(), "失敗したマイグレーションの途中の変更（CREATE TABLE）も戻る")
        self.assertEqual([r[0] for r in self.recorded()], [1, 2], "それより前のマイグレーションは適用されたまま")
        # 直して再実行すれば適用できる
        self.write("0003_broken.sql", "CREATE TABLE audit (id INTEGER PRIMARY KEY);\n")
        self.assertEqual(self.run_migrate(), [3])

    def test_edited_applied_migration_is_detected(self):
        self.run_migrate()
        self.write("0001_create_users.sql", CREATE_USERS + "-- あとから書き換えた\n")
        self.write("0003_add_email.sql", "ALTER TABLE users ADD COLUMN email TEXT;")
        with self.assertRaises(ChecksumMismatchError):
            self.run_migrate()
        self.assertEqual(len(self.recorded()), 2, "検証に失敗したら何も適用しない")
        self.assertTrue(issubclass(ChecksumMismatchError, MigrationError))

    def test_missing_applied_file_is_an_error(self):
        self.run_migrate()
        (self.dir / "0002_create_orders.sql").unlink()
        with self.assertRaises(MigrationError):
            self.run_migrate()

    def test_out_of_order_migration_is_rejected(self):
        self.write("0005_later.sql", "SELECT 1;")
        self.run_migrate()
        self.write("0004_from_another_branch.sql", "SELECT 1;")
        with self.assertRaises(MigrationError):
            self.run_migrate()

    def test_status(self):
        self.run_migrate(target=1)
        self.assertEqual(status(self.conn, self.dir), [(1, "create_users", "applied"), (2, "create_orders", "pending")])
        self.run_migrate()
        self.write("0001_create_users.sql", CREATE_USERS + "-- changed\n")
        (self.dir / "0002_create_orders.sql").unlink()
        self.assertEqual(status(self.conn, self.dir), [(1, "create_users", "modified"), (2, "create_orders", "missing")])

    def test_works_with_autocommit_connection(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(conn.close)
        self.write("0003_broken.sql", "CREATE TABLE audit (id INTEGER);\nSELECT * FROM nope;\n")
        with self.assertRaises(MigrationError):
            migrate(conn, self.dir, clock=lambda: FIXED)
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertNotIn("audit", tables)
        self.assertEqual(conn.execute("SELECT count(*) FROM schema_migrations").fetchone()[0], 2)


# ---------------------------------------------------------------------------
# 拡張・縮小: 3 つのリリースに分けた列の改名
# ---------------------------------------------------------------------------

# アプリケーションの 3 つの版（テストの中の「本番のコード」）
def v1_insert(conn, user_id, name):
    conn.execute("INSERT INTO users (id, name) VALUES (?, ?)", (user_id, name))


def v1_rename(conn, user_id, name):
    conn.execute("UPDATE users SET name = ? WHERE id = ?", (name, user_id))


def v1_read(conn, user_id):
    return conn.execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()[0]


def v2_insert(conn, user_id, name):
    conn.execute("INSERT INTO users (id, name, full_name) VALUES (?, ?, ?)", (user_id, name, name))


def v2_rename(conn, user_id, name):
    conn.execute("UPDATE users SET name = ?, full_name = ? WHERE id = ?", (name, name, user_id))


def v2_read(conn, user_id):
    return conn.execute("SELECT full_name FROM users WHERE id = ?", (user_id,)).fetchone()[0]


def v3_insert(conn, user_id, name):
    conn.execute("INSERT INTO users (id, full_name) VALUES (?, ?)", (user_id, name))


def v3_rename(conn, user_id, name):
    conn.execute("UPDATE users SET full_name = ? WHERE id = ?", (name, user_id))


v3_read = v2_read


@unittest.skipUnless(sqlite3.sqlite_version_info >= (3, 35, 0), "DROP COLUMN には SQLite 3.35 以降が必要")
class TestExpandContractRename(MigrationTestCase):
    def setUp(self):
        super().setUp()
        self.write("0001_create_users.sql", CREATE_USERS)
        self.assertEqual(self.run_migrate(), [1])
        v1_insert(self.conn, 1, "山田太郎")
        v1_insert(self.conn, 2, "佐藤花子")
        self.conn.commit()

    def release(self, filename, sql):
        self.write(filename, sql)
        applied = self.run_migrate()
        self.assertEqual(len(applied), 1, f"{filename} が適用されていません")

    def columns(self):
        return [r[1] for r in self.conn.execute("PRAGMA table_info(users)")]

    def test_release_1_expand_keeps_v1_and_v2_consistent(self):
        self.release("0002_expand_full_name.sql", expand_sql())
        self.assertIn("full_name", self.columns())
        self.assertEqual(v2_read(self.conn, 1), "山田太郎", "既存の行が埋め戻されていない")
        # ローリングデプロイ中: v1 と v2 が同時に動く
        v1_insert(self.conn, 3, "鈴木一郎")
        self.assertEqual(v2_read(self.conn, 3), "鈴木一郎", "v1 が書いた値を v2 が読めない（INSERT の同期）")
        v2_insert(self.conn, 4, "高橋次郎")
        self.assertEqual(v1_read(self.conn, 4), "高橋次郎", "v2 が書いた値を v1 が読めない")
        v1_rename(self.conn, 1, "山田一郎")
        self.assertEqual(v2_read(self.conn, 1), "山田一郎", "v1 の更新が full_name に届かない（UPDATE の同期）")
        v2_rename(self.conn, 2, "佐藤桜")
        self.assertEqual((v1_read(self.conn, 2), v2_read(self.conn, 2)), ("佐藤桜", "佐藤桜"))

    def test_release_2_switch_keeps_v2_and_v3_consistent(self):
        self.release("0002_expand_full_name.sql", expand_sql())
        self.release("0003_drop_sync_triggers.sql", switch_sql())
        triggers = self.conn.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0]
        self.assertEqual(triggers, 0, "リリース 2 で同期用のトリガーを削除すること")
        v3_insert(self.conn, 5, "伊藤三郎")
        self.assertEqual(v2_read(self.conn, 5), "伊藤三郎")
        v2_insert(self.conn, 6, "渡辺四郎")
        self.assertEqual(v3_read(self.conn, 6), "渡辺四郎")
        v3_rename(self.conn, 1, "山田二郎")
        self.assertEqual(v2_read(self.conn, 1), "山田二郎")

    def test_release_3_contract_removes_old_column_and_keeps_data(self):
        self.release("0002_expand_full_name.sql", expand_sql())
        v1_insert(self.conn, 3, "鈴木一郎")  # リリース 1 の期間中に v1 が書いたデータ
        self.release("0003_drop_sync_triggers.sql", switch_sql())
        v3_insert(self.conn, 4, "高橋次郎")
        self.release("0004_drop_name.sql", contract_sql())
        self.assertEqual(self.columns(), ["id", "full_name"])
        names = self.conn.execute("SELECT id, full_name FROM users ORDER BY id").fetchall()
        self.assertEqual(names, [(1, "山田太郎"), (2, "佐藤花子"), (3, "鈴木一郎"), (4, "高橋次郎")])
        v3_insert(self.conn, 5, "新しい利用者")
        self.assertEqual(v3_read(self.conn, 5), "新しい利用者")
        with self.assertRaises(sqlite3.OperationalError, msg="縮小の後は、name に書く古いアプリは動かない"):
            v2_insert(self.conn, 6, "x")


if __name__ == "__main__":
    unittest.main()
