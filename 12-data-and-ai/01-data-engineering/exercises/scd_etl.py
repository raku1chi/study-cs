"""12.1 データ基盤とデータエンジニアリング — 演習2: 増分・冪等な ETL と SCD Type 2

業務 DB（ソース。sqlite3）から、スタースキーマのデータウェアハウス（DW。これも sqlite3）へ
データを増分ロードするパイプラインを作ります。

    ソース（現在の状態だけを持つ）          DW（スタースキーマ）
    customers(customer_id, name,      →   dim_customer（SCD Type 2 で履歴を持つ）
              prefecture, tier,             dim_date（日付ディメンション）
              updated_at)                   fact_orders（粒度 = 注文 1 件につき 1 行）
    orders(order_id, customer_id,     →    etl_state（テーブルごとのウォーターマーク）
           ordered_at, amount, updated_at)

満たすべき性質:
    - 増分: 前回の実行以降に更新された行（updated_at > ウォーターマーク）だけを処理する。
    - 冪等: 同じソースの状態で何度実行しても DW は変わらない。full_refresh=True で
      全件を再処理しても、増分で積み上げた結果と一致する。
    - 原子性: 1 回の実行は 1 トランザクション。途中で例外が起きたら、DW は実行前の状態のまま。
    - 時点の正しさ: 事実は「注文時点で有効だった」顧客バージョンのサロゲートキーを指す。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.1
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_scd_etl

時刻はすべて 'YYYY-MM-DDTHH:MM:SS' 形式の UTC の文字列です。形式がそろっていれば
文字列の大小比較が時刻の前後と一致するので、SQL でもそのまま比較できます。
DDL と補助関数（create_source など）は実装済みです。スキーマ設計の意図をコメントで読んでください。
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from typing import Any

# 初回に観測したバージョンは「過去全体に対して有効」とみなす（初回ロードより前の履歴は分からないため）
MIN_TIME = "0001-01-01T00:00:00"
# 事実（注文）が顧客より先に届いたときに作る「推定メンバー」の属性値
INFERRED = "(未着)"

TYPE1_COLUMNS = ("name",)  # SCD Type 1: 上書きする属性（誤記の訂正など。履歴に分析上の意味がない）
TYPE2_COLUMNS = ("prefecture", "tier")  # SCD Type 2: 履歴を残す属性（過去の値で集計したい）

# 抽出を許可するソーステーブルと、その主キー
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
    customer_id INTEGER NOT NULL,   -- 外部キー制約はない（業務 DB ではよくある）
    ordered_at  TEXT NOT NULL,
    amount      INTEGER,            -- 円。NULL は不正データ（ETL で検出して止める）
    updated_at  TEXT NOT NULL
);
"""

WAREHOUSE_DDL = """
-- 顧客ディメンション（SCD Type 2）。1 顧客が複数行（バージョン）を持ちうる
CREATE TABLE dim_customer (
    customer_sk  INTEGER PRIMARY KEY,   -- サロゲートキー（DW 内で採番。バージョンごとに別の値）
    customer_id  INTEGER NOT NULL,      -- ナチュラルキー（業務キー）
    name         TEXT NOT NULL,         -- Type 1
    prefecture   TEXT NOT NULL,         -- Type 2
    tier         TEXT NOT NULL,         -- Type 2
    valid_from   TEXT NOT NULL,         -- 有効期間は半開区間 [valid_from, valid_to)
    valid_to     TEXT,                  -- NULL = 現在も有効
    is_current   INTEGER NOT NULL CHECK (is_current IN (0, 1)),
    is_inferred  INTEGER NOT NULL DEFAULT 0 CHECK (is_inferred IN (0, 1))  -- 推定メンバーか
);
-- 「現行バージョンは顧客ごとに 1 行だけ」を DB に保証させる（部分一意インデックス）
CREATE UNIQUE INDEX ux_dim_customer_current ON dim_customer (customer_id) WHERE is_current = 1;
-- 日付ディメンション（曜日・週末フラグなどの切り口を事前計算して持つ）
CREATE TABLE dim_date (
    date_key     INTEGER PRIMARY KEY,   -- 20260401 の形式
    full_date    TEXT NOT NULL,
    year         INTEGER NOT NULL,
    month        INTEGER NOT NULL,
    day          INTEGER NOT NULL,
    day_of_week  INTEGER NOT NULL,      -- 月曜=0 … 日曜=6
    is_weekend   INTEGER NOT NULL
);
-- 事実テーブル。粒度（grain）は「注文 1 件」
CREATE TABLE fact_orders (
    order_id     INTEGER PRIMARY KEY,   -- 退化ディメンション（ディメンション表を持たない識別子）
    customer_sk  INTEGER NOT NULL REFERENCES dim_customer (customer_sk),
    date_key     INTEGER NOT NULL REFERENCES dim_date (date_key),
    ordered_at   TEXT NOT NULL,
    amount       INTEGER NOT NULL       -- 加算可能な尺度（additive measure）
);
-- 増分ロードの進捗（どの updated_at まで処理したか）
CREATE TABLE etl_state (
    source_table TEXT PRIMARY KEY,
    watermark    TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# 実装済みの補助関数
# ---------------------------------------------------------------------------

def create_source(conn: sqlite3.Connection) -> None:
    """ソースのテーブルを作る。"""
    conn.executescript(SOURCE_DDL)


def create_warehouse(conn: sqlite3.Connection) -> None:
    """DW のテーブルを作る。"""
    conn.executescript(WAREHOUSE_DDL)


def dump_warehouse(conn: sqlite3.Connection) -> dict[str, list[tuple]]:
    """DW の全テーブルの内容を主キー順に返す（冪等性のテスト用）。"""
    tables = {
        "dim_customer": "customer_sk",
        "dim_date": "date_key",
        "fact_orders": "order_id",
        "etl_state": "source_table",
    }
    return {t: conn.execute(f"SELECT * FROM {t} ORDER BY {pk}").fetchall() for t, pk in tables.items()}


def get_watermark(dw: sqlite3.Connection, table: str) -> str | None:
    """table のウォーターマーク（未実行なら None）を返す。"""
    row = dw.execute("SELECT watermark FROM etl_state WHERE source_table = ?", (table,)).fetchone()
    return row[0] if row else None


def set_watermark(dw: sqlite3.Connection, table: str, watermark: str) -> None:
    """table のウォーターマークを書き込む（コミットはしない）。"""
    dw.execute("INSERT OR REPLACE INTO etl_state (source_table, watermark) VALUES (?, ?)", (table, watermark))


def ensure_date_key(dw: sqlite3.Connection, timestamp: str) -> int:
    """timestamp の日付の dim_date 行がなければ作り、date_key（例: 20260401）を返す。"""
    d = dt.date.fromisoformat(timestamp[:10])
    key = d.year * 10000 + d.month * 100 + d.day
    dw.execute(
        "INSERT OR IGNORE INTO dim_date VALUES (?, ?, ?, ?, ?, ?, ?)",
        (key, d.isoformat(), d.year, d.month, d.day, d.weekday(), int(d.weekday() >= 5)),
    )
    return key


# ---------------------------------------------------------------------------
# 演習2a（★☆☆）: 増分抽出
# ---------------------------------------------------------------------------

def extract_changed(src: sqlite3.Connection, table: str, watermark: str | None) -> list[dict[str, Any]]:
    """ソースの table から、updated_at > watermark の行を辞書のリストで返す。

    - watermark が None なら全件を返す。
    - 並び順は (updated_at, 主キー) の昇順。
    - table が SOURCE_TABLES にない名前なら ValueError（テーブル名はプレースホルダ ? で
      渡せないので、文字列を SQL に埋め込む前に許可リストで検証する。SQL インジェクション対策）。
    - 辞書のキーは列名（cursor.description から取れる）。

    >>> extract_changed(src, "customers", "2026-04-01T09:05:00")   # doctest: +SKIP
    [{'customer_id': 3, 'name': '高橋', 'prefecture': '福岡県', 'tier': 'regular', 'updated_at': '2026-04-01T09:10:00'}]
    """
    raise NotImplementedError("演習2a: extract_changed を実装してください")


# ---------------------------------------------------------------------------
# 演習2b（★★★）: SCD Type 2 の顧客ディメンション
# ---------------------------------------------------------------------------

def apply_customer_change(dw: sqlite3.Connection, row: dict[str, Any]) -> str:
    """ソースの顧客 1 行（extract_changed の要素）を dim_customer に反映し、行った操作を返す。

    現行バージョン（is_current = 1）と比べて、次のどれか 1 つを返す:

    - "inserted": 現行バージョンがない。valid_from=MIN_TIME, valid_to=NULL, is_current=1,
      is_inferred=0 で挿入する。
    - "inferred_resolved": 現行バージョンが推定メンバー（is_inferred = 1）。その行の
      name / prefecture / tier をソースの値で上書きし、is_inferred = 0 にする
      （新しいバージョンは作らない。サロゲートキーが変わらないので事実を直さなくてよい）。
    - "new_version": Type 2 属性（prefecture, tier）のどれかが変わった。
      現行行を valid_to = row["updated_at"], is_current = 0 で閉じてから、
      valid_from = row["updated_at"] の新しい現行行を挿入する（name も新しい値にする）。
      row["updated_at"] が現行行の valid_from 以前なら ValueError（期間が壊れるため）。
    - "type1_updated": Type 1 属性（name）だけが変わった。その顧客の **すべてのバージョン** の
      name を上書きする。
    - "unchanged": 何も変わっていない（→ 同じ行を何度適用しても DW は変わらない = 冪等）。

    Type 1 と Type 2 が同時に変わったら、すべてのバージョンの name を上書きしたうえで
    新しいバージョンを作り、"new_version" を返す。

    注意: 部分一意インデックスがあるので、新しい現行行を挿入する前に古い行を閉じること。
    コミットはしない（トランザクションの管理は run_etl の責任）。
    """
    raise NotImplementedError("演習2b: apply_customer_change を実装してください")


def lookup_customer_sk(dw: sqlite3.Connection, customer_id: int, at: str) -> int | None:
    """時刻 at に有効だった顧客バージョンの customer_sk を返す（なければ None）。

    有効期間は半開区間: valid_from <= at かつ (valid_to IS NULL または at < valid_to)。
    ちょうど valid_to の時刻は、次のバージョンに属する。
    """
    raise NotImplementedError("演習2b: lookup_customer_sk を実装してください")


# ---------------------------------------------------------------------------
# 演習2c（★★☆）: 事実テーブル
# ---------------------------------------------------------------------------

def apply_order_change(dw: sqlite3.Connection, row: dict[str, Any]) -> str:
    """ソースの注文 1 行を fact_orders に反映し、"inserted" / "updated" / "unchanged" を返す。

    1. amount が int でない（None や bool を含む）か負なら ValueError。
    2. lookup_customer_sk(dw, row["customer_id"], row["ordered_at"]) で顧客のキーを引く。
       見つからず、その顧客の行が dim_customer に 1 行もなければ、推定メンバー
       （name / prefecture / tier = INFERRED, valid_from = MIN_TIME, valid_to = NULL,
       is_current = 1, is_inferred = 1）を挿入し、そのキーを使う（遅れて届くディメンション）。
       行はあるのに期間が見つからない場合は、データの不整合なので RuntimeError。
    3. ensure_date_key() で date_key を得る。
    4. order_id の行がなければ挿入（"inserted"）。あれば (customer_sk, date_key, ordered_at,
       amount) を比べ、同じなら "unchanged"、違えば更新して "updated"（アップサート）。
    """
    raise NotImplementedError("演習2c: apply_order_change を実装してください")


# ---------------------------------------------------------------------------
# 演習2d（★★☆）: パイプライン全体
# ---------------------------------------------------------------------------

def run_etl(src: sqlite3.Connection, dw: sqlite3.Connection, *, full_refresh: bool = False) -> dict[str, int]:
    """ETL を 1 回実行し、操作の件数を {"テーブル名.操作": 件数} で返す（0 件の操作は含めない）。

    手順（全体を 1 つのトランザクションで行う。ヒント: `with dw:` は正常終了で COMMIT、
    例外で ROLLBACK する）:
    1. "customers" → "orders" の順に処理する（事実より先にディメンションを更新する）。
    2. 各テーブルについて、ウォーターマークを読み、extract_changed で変更行を取り出す
       （full_refresh=True なら watermark=None として全件）。
    3. 各行に apply_customer_change / apply_order_change を適用し、戻り値を数える。
       例: {"customers.new_version": 1, "orders.inserted": 2}
    4. 抽出した行があれば、その最大の updated_at でウォーターマークを更新する。
       ただしウォーターマークを後戻りさせてはいけない（full_refresh でも同様）。

    >>> run_etl(src, dw)                     # doctest: +SKIP
    {'customers.inserted': 3, 'orders.inserted': 3}
    >>> run_etl(src, dw)                     # 変更がなければ何も起きない  # doctest: +SKIP
    {}
    """
    raise NotImplementedError("演習2d: run_etl を実装してください")
