"""12.1 データ基盤とデータエンジニアリング — 演習2: 増分・冪等な ETL と SCD Type 2（解答例）

演習の仕様は exercises/scd_etl.py の docstring を参照してください。
業務 DB（ソース）から、スタースキーマのデータウェアハウス（DW）へ増分ロードします。
ポイントは次の 3 つです。
- 冪等性: 同じ入力で何度実行しても DW の内容が変わらない（だから安心して再実行・再処理できる）
- 原子性: 1 回の実行を 1 トランザクションにし、途中で失敗したら何も書かない
- 時点の正しさ: 事実（注文）は「その時点で有効だった」ディメンションのバージョンを指す
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

# 初回に観測したバージョンは「過去全体に対して有効」とみなす（初回ロードより前の履歴は分からないため）
MIN_TIME = "0001-01-01T00:00:00"
# 事実が先に届いたときに作る「推定メンバー」の属性値
INFERRED = "(未着)"

TYPE1_COLUMNS = ("name",)  # 上書きする属性（誤記の訂正など、履歴に意味がない）
TYPE2_COLUMNS = ("prefecture", "tier")  # 履歴を残す属性（分析の切り口として過去の値が必要）

# 抽出を許可するソーステーブルと主キー（テーブル名は SQL のプレースホルダにできないので許可リストで守る）
SOURCE_TABLES = {"customers": "customer_id", "orders": "order_id"}

SOURCE_DDL = """
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    prefecture  TEXT NOT NULL,
    tier        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ordered_at  TEXT NOT NULL,
    amount      INTEGER,
    updated_at  TEXT NOT NULL
);
"""

WAREHOUSE_DDL = """
CREATE TABLE dim_customer (
    customer_sk  INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    name         TEXT NOT NULL,
    prefecture   TEXT NOT NULL,
    tier         TEXT NOT NULL,
    valid_from   TEXT NOT NULL,
    valid_to     TEXT,
    is_current   INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    is_inferred  INTEGER NOT NULL DEFAULT 0 CHECK (is_inferred IN (0, 1))
);
CREATE UNIQUE INDEX ux_dim_customer_current ON dim_customer (customer_id) WHERE is_current = 1;
CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,
    full_date    TEXT NOT NULL,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    day_of_week  INTEGER NOT NULL,
    is_weekend   INTEGER NOT NULL
);
CREATE TABLE fact_orders (
    order_id     INTEGER PRIMARY KEY,
    customer_sk  INTEGER NOT NULL REFERENCES dim_customer (customer_sk),
    date_key     INTEGER NOT NULL REFERENCES dim_date (date_key),
    ordered_at   TEXT NOT NULL,
    amount       INTEGER NOT NULL
);
CREATE TABLE etl_state (
    source_table TEXT PRIMARY KEY,
    watermark    TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# 実装済みの補助関数
# ---------------------------------------------------------------------------

def create_source(conn: sqlite3.Connection) -> None:
    conn.executescript(SOURCE_DDL)


def create_warehouse(conn: sqlite3.Connection) -> None:
    conn.executescript(WAREHOUSE_DDL)


def dump_warehouse(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    tables = {
        "dim_customer": "customer_sk",
        "dim_date": "date_key",
        "fact_orders": "order_id",
        "etl_state": "source_table",
    }
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY {pk}").fetchall() for t, pk in tables.items()}


def get_watermark(dw: sqlite3.Connection, table: str) -> str | None:
    row = dw.execute("SELECT watermark FROM etl_state WHERE source_table = ?", (table,)).fetchone()
    return row[0] if row else None


def set_watermark(dw: sqlite3.Connection, table: str, watermark: str) -> None:
    dw.execute("INSERT OR REPLACE INTO etl_state (source_table, watermark) VALUES (?, ?)", (table, watermark))


def ensure_date_key(dw: sqlite3.Connection, timestamp: str) -> int:
    d = dt.date.fromisoformat(timestamp[:10])
    key = d.year * 10000 + d.month * 100 + d.day
    dw.execute(
        "INSERT OR IGNORE INTO dim_date VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, d.isoformat(), d.year, d.month, d.day, d.weekday(), int(d.weekday() >= 5)),
    )
    return key


# ---------------------------------------------------------------------------
# 演習2a: 増分抽出
# ---------------------------------------------------------------------------

def extract_changed(src: sqlite3.Connection, table: str, watermark: str | None) -> list[dict[str, Any]]:
    if table not in SOURCE_TABLES:
        raise ValueError(f"抽出できないテーブルです: {table!r}")
    pk = SOURCE_TABLES[table]
    sql = f"SELECT * FROM {table}"  # table は許可リストで検証済み
    params: tuple[Any, ...] = ()
    if watermark is not None:
        sql += " WHERE updated_at > ?"
        params = (watermark,)
    sql += f" ORDER BY updated_at, {pk}"
    cur = src.execute(sql, params)
    columns = [d[0] for d in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# 演習2b: SCD Type 2 の顧客ディメンション
# ---------------------------------------------------------------------------

def _insert_version(dw: sqlite3.Connection, row: dict[str, Any], valid_from: str, inferred: bool) -> int:
    cur = dw.execute(
        "INSERT INTO dim_customer (customer_id, name, prefecture, tier, valid_from, valid_to,"
        " is_current, is_inferred) VALUES (?, ?, ?, ?, ?, NULL, 1, ?)",
        (row["customer_id"], row["name"], row["prefecture"], row["tier"], valid_from, int(inferred)),
    )
    return cur.lastrowid


def apply_customer_change(dw: sqlite3.Connection, row: dict[str, Any]) -> str:
    current = dw.execute(
        "SELECT customer_sk, name, prefecture, tier, valid_from, is_inferred"
        " FROM dim_customer WHERE customer_id = ? AND is_current = 1",
        (row["customer_id"],),
    ).fetchone()
    if current is None:
        _insert_version(dw, row, MIN_TIME, inferred=False)
        return "inserted"

    sk, name, prefecture, tier, valid_from, is_inferred = current
    if is_inferred:
        # 事実が先に届いて作った仮の行を、本物の属性で埋める。サロゲートキーは変えないので
        # すでにこの行を指している事実を直す必要がない（Kimball の「推定メンバー」パターン）
        dw.execute(
            "UPDATE dim_customer SET name = ?, prefecture = ?, tier = ?, is_inferred = 0 WHERE customer_sk = ?",
            (row["name"], row["prefecture"], row["tier"], sk),
        )
        return "inferred_resolved"

    type1_changed = (name,) != tuple(row[c] for c in TYPE1_COLUMNS)
    type2_changed = (prefecture, tier) != tuple(row[c] for c in TYPE2_COLUMNS)

    if type1_changed:
        # Type 1: 履歴を持たない属性は、過去のバージョンも含めて全部上書きする
        dw.execute("UPDATE dim_customer SET name = ? WHERE customer_id = ?", (row["name"], row["customer_id"]))
    if type2_changed:
        changed_at = row["updated_at"]
        if changed_at <= valid_from:
            raise ValueError(
                f"顧客 {row['customer_id']} の変更時刻 {changed_at} が現バージョンの開始 {valid_from} 以前です"
            )
        # 先に現バージョンを閉じる（部分一意インデックスが「現行は 1 行だけ」を保証している）
        dw.execute(
            "UPDATE dim_customer SET valid_to = ?, is_current = 0 WHERE customer_sk = ?",
            (changed_at, sk),
        )
        _insert_version(dw, row, changed_at, inferred=False)
        return "new_version"
    return "type1_updated" if type1_changed else "unchanged"


def lookup_customer_sk(dw: sqlite3.Connection, customer_id: int, at: str) -> int | None:
    # 半開区間 [valid_from, valid_to) で探す。BETWEEN（閉区間）だと境界の時刻で 2 行に一致してしまう
    row = dw.execute(
        "SELECT customer_sk FROM dim_customer"
        " WHERE customer_id = ? AND valid_from <= ? AND (valid_to IS NULL OR ? < valid_to)",
        (customer_id, at, at),
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# 演習2c: 事実テーブル
# ---------------------------------------------------------------------------

def apply_order_change(dw: sqlite3.Connection, row: dict[str, Any]) -> str:
    amount = row["amount"]
    if not isinstance(amount, int) or isinstance(amount, bool) or amount < 0:
        raise ValueError(f"注文 {row['order_id']} の amount が不正です: {amount!r}")

    sk = lookup_customer_sk(dw, row["customer_id"], row["ordered_at"])
    if sk is None:
        exists = dw.execute(
            "SELECT 1 FROM dim_customer WHERE customer_id = ?", (row["customer_id"],)
        ).fetchone()
        if exists:
            raise RuntimeError(f"顧客 {row['customer_id']} のバージョン期間に隙間があります")
        # 遅れて届くディメンション: 仮の行（推定メンバー）を作って、そのキーを使う
        placeholder = {"customer_id": row["customer_id"], "name": INFERRED, "prefecture": INFERRED, "tier": INFERRED}
        sk = _insert_version(dw, placeholder, MIN_TIME, inferred=True)

    new = (sk, ensure_date_key(dw, row["ordered_at"]), row["ordered_at"], amount)
    existing = dw.execute(
        "SELECT customer_sk, date_key, ordered_at, amount FROM fact_orders WHERE order_id = ?",
        (row["order_id"],),
    ).fetchone()
    if existing is None:
        dw.execute("INSERT INTO fact_orders VALUES (?, ?, ?, ?, ?)", (row["order_id"], *new))
        return "inserted"
    if tuple(existing) == new:
        return "unchanged"
    dw.execute(
        "UPDATE fact_orders SET customer_sk = ?, date_key = ?, ordered_at = ?, amount = ? WHERE order_id = ?",
        (*new, row["order_id"]),
    )
    return "updated"


# ---------------------------------------------------------------------------
# 演習2d: パイプライン全体
# ---------------------------------------------------------------------------

def run_etl(src: sqlite3.Connection, dw: sqlite3.Connection, *, full_refresh: bool = False) -> dict[str, int]:
    stats: dict[str, int] = {}
    # with dw: … 例外なら ROLLBACK、正常終了なら COMMIT。ウォーターマークの更新も同じトランザクションに
    # 入れることで「データは書いたのにウォーターマークが古い／その逆」という中途半端な状態を作らない
    with dw:
        for table, apply in (("customers", apply_customer_change), ("orders", apply_order_change)):
            watermark = get_watermark(dw, table)
            rows = extract_changed(src, table, None if full_refresh else watermark)
            for row in rows:
                action = apply(dw, row)
                key = f"{table}.{action}"
                stats[key] = stats.get(key, 0) + 1
            if rows:
                newest = rows[-1]["updated_at"]  # extract_changed は updated_at 順に返す
                if watermark is None or newest > watermark:  # ウォーターマークは後戻りさせない
                    set_watermark(dw, table, newest)
    return stats
