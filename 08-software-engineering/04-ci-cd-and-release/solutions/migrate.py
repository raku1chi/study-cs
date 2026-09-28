"""8.4 CI/CDとリリースエンジニアリング — 解答例: データベースのマイグレーション

仕様は exercises/migrate.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

MIGRATION_TABLE = "schema_migrations"
FILENAME_RE = re.compile(r"([0-9]+)_([A-Za-z0-9_]+)\.sql")


class MigrationError(Exception):
    """マイグレーションを安全に実行できない。"""


class ChecksumMismatchError(MigrationError):
    """適用済みのマイグレーションのファイルが変更されている。"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    checksum: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 演習3-1: マイグレーションの実行器
# ---------------------------------------------------------------------------

def discover(directory: Path) -> list[Migration]:
    migrations: dict[int, Migration] = {}
    for path in sorted(Path(directory).iterdir()):
        if not path.is_file() or path.suffix != ".sql":
            continue
        m = FILENAME_RE.fullmatch(path.name)
        if m is None or int(m.group(1)) < 1:
            raise MigrationError(f"マイグレーションのファイル名が不正です: {path.name}（例: 0001_create_users.sql）")
        version = int(m.group(1))
        if version in migrations:
            raise MigrationError(f"番号 {version} が重複しています: {migrations[version].path.name} と {path.name}")
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        migrations[version] = Migration(version, m.group(2), path, checksum)
    return [migrations[v] for v in sorted(migrations)]


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    conn.commit()


def _applied(conn: sqlite3.Connection) -> dict[int, tuple[str, str]]:
    rows = conn.execute(f"SELECT version, name, checksum FROM {MIGRATION_TABLE}").fetchall()
    return {version: (name, checksum) for version, name, checksum in rows}


def status(conn: sqlite3.Connection, directory: Path) -> list[tuple[int, str, str]]:
    _ensure_table(conn)
    applied = _applied(conn)
    files = {m.version: m for m in discover(directory)}
    result = []
    for version in sorted(set(applied) | set(files)):
        if version not in applied:
            result.append((version, files[version].name, "pending"))
        elif version not in files:
            result.append((version, applied[version][0], "missing"))
        elif applied[version][1] != files[version].checksum:
            result.append((version, files[version].name, "modified"))
        else:
            result.append((version, files[version].name, "applied"))
    return result


def _validate(applied: dict[int, tuple[str, str]], files: dict[int, Migration], pending: list[Migration]) -> None:
    for version, (name, checksum) in sorted(applied.items()):
        if version not in files:
            raise MigrationError(f"適用済みのマイグレーション {version}_{name} のファイルがありません")
        if files[version].checksum != checksum:
            raise ChecksumMismatchError(
                f"適用済みのマイグレーション {version}_{name} が変更されています。"
                "直したい場合は、新しいマイグレーションを追加してください"
            )
    if applied and pending and pending[0].version < max(applied):
        raise MigrationError(
            f"未適用のマイグレーション {pending[0].version}_{pending[0].name} が、"
            f"適用済みの最新（{max(applied)}）より前にあります。番号を振り直してください"
        )


def migrate(
    conn: sqlite3.Connection,
    directory: Path,
    *,
    target: Optional[int] = None,
    clock: Callable[[], datetime] = _utc_now,
) -> list[int]:
    _ensure_table(conn)
    applied = _applied(conn)
    migrations = discover(directory)
    files = {m.version: m for m in migrations}
    pending = [m for m in migrations if m.version not in applied and (target is None or m.version <= target)]
    _validate(applied, files, pending)  # 問題があれば、何も適用しないうちに止める

    done = []
    for m in pending:
        sql = m.path.read_text(encoding="utf-8")
        try:
            # executescript は実行前に進行中のトランザクションをコミットするので、
            # 自分で BEGIN を先頭に付けて、このマイグレーション全体を 1 つのトランザクションにする
            conn.executescript("BEGIN;\n" + sql)
            conn.execute(
                f"INSERT INTO {MIGRATION_TABLE} (version, name, checksum, applied_at) VALUES (?, ?, ?, ?)",
                (m.version, m.name, m.checksum, clock().isoformat()),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise MigrationError(f"マイグレーション {m.version}_{m.name} の適用に失敗しました: {exc}") from exc
        done.append(m.version)
    return done


# ---------------------------------------------------------------------------
# 演習3-2: 拡張・縮小による列の改名
# ---------------------------------------------------------------------------

def expand_sql() -> str:
    return """
-- リリース 1（拡張）: 新しい列を足し、古い列と同期させる。古いアプリ（v1）はそのまま動く
ALTER TABLE users ADD COLUMN full_name TEXT;

-- 既存の行の埋め戻し（大きなテーブルでは、ロックを避けるために小分けにして実行する）
UPDATE users SET full_name = name WHERE full_name IS NULL;

-- v1 は name にしか書かないので、full_name にも写す（v2 は両方に書くので WHEN で除外）
CREATE TRIGGER users_sync_full_name_on_insert AFTER INSERT ON users
WHEN NEW.full_name IS NULL
BEGIN
    UPDATE users SET full_name = NEW.name WHERE id = NEW.id;
END;

CREATE TRIGGER users_sync_full_name_on_update AFTER UPDATE OF name ON users
BEGIN
    UPDATE users SET full_name = NEW.name WHERE id = NEW.id;
END;
"""


def switch_sql() -> str:
    return """
-- リリース 2: v1 はもういないので同期は不要。name 列を参照するトリガーを先に消しておく
DROP TRIGGER IF EXISTS users_sync_full_name_on_insert;
DROP TRIGGER IF EXISTS users_sync_full_name_on_update;
"""


def contract_sql() -> str:
    return """
-- リリース 3（縮小）: name を書くアプリ（v2）がいなくなってから、古い列を消す
ALTER TABLE users DROP COLUMN name;
"""
