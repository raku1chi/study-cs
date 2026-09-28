"""8.4 CI/CDとリリースエンジニアリング — 演習3: データベースのマイグレーション

アプリケーションのコードは Git で版を管理しますが、データベースのスキーマは「今どの変更まで
適用されたか」を DB 自身に記録しなければなりません。この演習では、Flyway や Alembic のような
マイグレーションツールの中核を sqlite3 で作り、さらに「列の名前の変更」を、無停止で行うための
拡張・縮小（expand–contract）の手順で、3 回のリリースに分けて実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.4

演習の構成:
    3-1 discover / status / migrate（★★★）: マイグレーションの実行器
    3-2 expand_sql / switch_sql / contract_sql（★★☆）: users.name → users.full_name の無停止の改名

-----------------------------------------------------------------------------
3-1 の仕様
-----------------------------------------------------------------------------
マイグレーションのファイル:
    - ディレクトリ直下の "<番号>_<名前>.sql"（例: 0001_create_users.sql）。番号は 1 以上の整数。
      名前は英数字とアンダースコア（[A-Za-z0-9_]+）。
    - .sql 以外のファイル（README.md など）は無視する。
    - .sql なのに形式に合わないファイル、番号の重複（0002_a.sql と 002_b.sql）は MigrationError。
    - チェックサム: ファイルの内容（バイト列）の SHA-256 を 16 進数にしたもの。

適用の記録（DB 内のテーブル）:
    CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY, name TEXT NOT NULL, checksum TEXT NOT NULL, applied_at TEXT NOT NULL)

migrate の手順:
    1. schema_migrations がなければ作る。
    2. 検証（1 つでも問題があれば、何も適用せずに例外）:
       - 適用済みなのにファイルがない → MigrationError
       - 適用済みのファイルの内容が変わっている（チェックサムが違う）→ ChecksumMismatchError
         （適用済みのマイグレーションを書き換えても DB には反映されず、環境ごとにスキーマが
           ずれる原因になる。直したいなら新しいマイグレーションを足すこと）
       - 未適用なのに、番号が適用済みの最大の番号より小さい → MigrationError
         （別ブランチで番号が前後した。黙って適用すると環境ごとに適用順が変わる）
    3. 未適用のもの（target を指定したら番号が target 以下のもの）を番号順に、
       **1 つずつ別々のトランザクションで** 適用する: SQL をすべて実行し、schema_migrations に
       記録し、コミットする。途中で失敗したら、そのマイグレーションの変更をすべてロールバックし、
       MigrationError（番号と名前を含むメッセージ）を送出する。それより前に適用できたものは残る。
    4. 適用した番号のリストを返す。何も適用しなければ [] （何度実行しても安全 = 冪等）。

sqlite3 での実装のヒント:
    - conn.executescript(sql) は複数の文を実行できるが、実行の前に進行中のトランザクションを
      コミットしてしまう。そこで conn.executescript("BEGIN;\\n" + sql) としてトランザクションを
      始めつつ SQL を実行し、conn.execute("INSERT INTO schema_migrations ...") で記録してから
      conn.commit() する。例外が起きたら conn.rollback()。
    - SQLite は DDL（CREATE TABLE・ALTER TABLE など）もトランザクションの中でロールバックできる。
      （MySQL のように DDL で暗黙にコミットされる DB もあるので、本物のツールでは注意が必要）
    - マイグレーションのファイルの中に BEGIN や COMMIT を書かないこと（二重のトランザクションになる）。

-----------------------------------------------------------------------------
3-2 の仕様: users.name を users.full_name に、無停止で改名する
-----------------------------------------------------------------------------
最初のスキーマ（0001）: CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)

ローリングデプロイでは、新旧のアプリケーションが同時に動く時間があります。そこで、次の 3 回の
リリースに分けます。各リリースでは、まずマイグレーションを適用し、次にアプリケーションを入れ替えます。

  リリース 1（拡張 expand）: 0002 = expand_sql()
      - full_name 列を追加し、既存の行を埋め戻す（backfill）。
      - 旧アプリ v1（name だけを書き・読む）が書いた値が full_name にも入るよう、トリガーで同期する
        （INSERT のときと、name を UPDATE したとき）。
      - 新アプリ v2 は name と full_name の両方に書き、full_name を読む。
      この間、v1 と v2 が混在しても、どちらからも正しい値が読めること。
  リリース 2（移行 migrate）: 0003 = switch_sql()
      - v1 はもう存在しないので、同期用のトリガーを削除する。
      - 新アプリ v3 は full_name だけを書き・読む。v2 と v3 が混在しても、どちらも正しく動くこと。
  リリース 3（縮小 contract）: 0004 = contract_sql()
      - v2 はもう存在しないので、name 列を削除する（ALTER TABLE ... DROP COLUMN。SQLite 3.35 以降）。

テストでは、各段階で新旧のアプリケーション（テストの中に書かれた v1・v2・v3 の関数）を
交互に動かして、データが食い違わないことを確かめます。
"""
from __future__ import annotations

import hashlib  # noqa: F401  実装で使います
import re  # noqa: F401  実装で使えます
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

MIGRATION_TABLE = "schema_migrations"


class MigrationError(Exception):
    """マイグレーションを安全に実行できない。"""


class ChecksumMismatchError(MigrationError):
    """適用済みのマイグレーションのファイルが変更されている。"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str  # ファイル名の <名前> の部分（例: "create_users"）
    path: Path
    checksum: str  # ファイルの内容の SHA-256（16 進数）


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 演習3-1（★★★）: マイグレーションの実行器
# ---------------------------------------------------------------------------

def discover(directory: Path) -> list[Migration]:
    """directory 直下のマイグレーションのファイルを、番号の昇順で返す（仕様はモジュールの docstring）。"""
    raise NotImplementedError("演習3-1: discover を実装してください")


def status(conn: sqlite3.Connection, directory: Path) -> list[tuple[int, str, str]]:
    """各マイグレーションの状態を (番号, 名前, 状態) のリストで、番号の昇順に返す。

    状態: "applied"（適用済みで内容も同じ）/ "pending"（未適用）/
          "modified"（適用済みだがファイルの内容が変わった）/ "missing"（適用済みだがファイルがない。
          名前は schema_migrations に記録されたものを使う）
    schema_migrations がなければ作ってよい。
    """
    raise NotImplementedError("演習3-1: status を実装してください")


def migrate(
    conn: sqlite3.Connection,
    directory: Path,
    *,
    target: Optional[int] = None,
    clock: Callable[[], datetime] = _utc_now,
) -> list[int]:
    """未適用のマイグレーションを適用し、適用した番号のリストを返す（仕様はモジュールの docstring）。

    applied_at には clock() の結果を isoformat() した文字列を記録する。
    """
    raise NotImplementedError("演習3-1: migrate を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★★☆）: 拡張・縮小による列の改名
# ---------------------------------------------------------------------------

def expand_sql() -> str:
    """リリース 1 のマイグレーション（0002）の SQL: full_name 列の追加・埋め戻し・同期トリガー。

    ヒント: SQLite のトリガーは NEW の値を書き換えられないので、AFTER INSERT / AFTER UPDATE OF name
            のトリガーの中で UPDATE users SET full_name = NEW.name WHERE id = NEW.id とする。
            v2 は両方の列に書くので、INSERT のトリガーは full_name が NULL のとき（WHEN 句）だけ動けばよい。
    """
    raise NotImplementedError("演習3-2: expand_sql を実装してください")


def switch_sql() -> str:
    """リリース 2 のマイグレーション（0003）の SQL: 同期トリガーの削除。"""
    raise NotImplementedError("演習3-2: switch_sql を実装してください")


def contract_sql() -> str:
    """リリース 3 のマイグレーション（0004）の SQL: name 列の削除。"""
    raise NotImplementedError("演習3-2: contract_sql を実装してください")
