"""SQLite への接続・トランザクション・マイグレーション。

- 接続はリクエストごとに開いて閉じる（SQLite の接続はスレッド間で共有しない）。
- トランザクションは transaction() で BEGIN〜COMMIT を明示する。
- スキーマは migrations/NNNN_名前.sql を番号順に適用し、適用済みの番号を
  schema_migrations テーブルに記録する。適用済みのファイルは編集しない。
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .timeutil import to_iso, utc_now

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
_MIGRATION_NAME_RE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path


def connect(db_path: str) -> sqlite3.Connection:
    """接続を開く。

    - timeout=5.0: 他の接続が書き込みロックを持っているとき、すぐにエラーにせず最大 5 秒待つ
      （SQLite の busy timeout）。
    - isolation_level=None: sqlite3 モジュールの「暗黙のトランザクション開始」を無効にする。
      どこからどこまでが 1 つのトランザクションかを、transaction() でコードに明示するため。
    - PRAGMA foreign_keys: SQLite は接続ごとに有効にしないと外部キー制約を検査しない。
    """
    conn = sqlite3.connect(db_path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection, *, write: bool = True) -> Iterator[sqlite3.Connection]:
    """BEGIN〜COMMIT を明示するコンテキストマネージャ。例外が出たら ROLLBACK して再送出する。

    書き込むトランザクションは BEGIN IMMEDIATE で始め、最初に書き込みロックを取る。
    WAL モードでは、BEGIN（DEFERRED）で読み始めたトランザクションが後から書こうとしたとき、
    その間に別の接続がコミットしていると SQLITE_BUSY になり、busy timeout で待っても解消しないため。
    """
    conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
    try:
        yield conn
    except BaseException:
        # ディスクフル（SQLITE_FULL）などのエラーでは、SQLite 自身がすでにロールバックしていることがある。
        # そこへ ROLLBACK を重ねると別のエラーになり、本当の原因が隠れてしまうので、確かめてから実行する
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


# ---------------------------------------------------------------------------
# マイグレーション
# ---------------------------------------------------------------------------

def discover_migrations(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """ディレクトリ内の NNNN_名前.sql を番号順に返す。名前の規則違反や番号の重複は ValueError。"""
    migrations: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        m = _MIGRATION_NAME_RE.match(path.name)
        if m is None:
            raise ValueError(f"マイグレーションのファイル名が規則に合いません: {path.name}（例: 0002_add_labels.sql）")
        migrations.append(Migration(int(m.group(1)), m.group(2), path))
    versions = [m.version for m in migrations]
    if len(versions) != len(set(versions)):
        raise ValueError(f"マイグレーションの番号が重複しています: {versions}")
    return migrations


def _ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )


def pending_migrations(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    _ensure_migrations_table(conn)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    return [m for m in discover_migrations(directory) if m.version not in applied]


def migrate(conn: sqlite3.Connection, directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """未適用のマイグレーションを番号順に適用し、適用したものを返す。何度実行してもよい（冪等）。

    各マイグレーションは 1 つのトランザクションで適用する（SQLite は DDL もロールバックできる）。
    複数のプロセスが同時に実行しても二重に適用しないよう、ロックを取ってから適用済みかを確かめる。
    """
    # WAL: 読み取りが書き込みをブロックしなくなる。設定は DB ファイルに保存される（トランザクション外で実行する）
    conn.execute("PRAGMA journal_mode = WAL")
    _ensure_migrations_table(conn)
    applied: list[Migration] = []
    for migration in discover_migrations(directory):
        statements = split_sql_statements(migration.path.read_text(encoding="utf-8"))
        with transaction(conn):
            done = conn.execute(
                "SELECT 1 FROM schema_migrations WHERE version = ?", (migration.version,)
            ).fetchone()
            if done:
                continue
            for statement in statements:
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (migration.version, migration.name, to_iso(utc_now())),
            )
        applied.append(migration)
    return applied


def split_sql_statements(script: str) -> list[str]:
    """SQL スクリプトを文ごとに分割する。

    文の終わりの判定は sqlite3.complete_statement（SQLite 自身の字句解析）に任せるので、
    文字列リテラルやコメントの中のセミコロン、CREATE TRIGGER の本体も正しく扱える。
    文の外にある空行・コメント行は捨てる。
    """
    statements: list[str] = []
    buffer = ""
    for line in script.splitlines(keepends=True):
        if not buffer and (not line.strip() or line.lstrip().startswith("--")):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statements.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        raise ValueError(f"SQL の文が途中で終わっています: {buffer.strip()[:60]!r}")
    return statements
