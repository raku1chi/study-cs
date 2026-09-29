"""6.1 リレーショナルモデルとSQL — 演習2: SQL の問い合わせを書く

EC サイトのデータベース（data/ecommerce.sql）に対する問い合わせを SQL で書きます。
各関数は「SQL の文字列」を返すだけです。テストがその SQL を SQLite（Python の sqlite3）で
実行し、結果を確かめます。テストはデータを追加した別のデータベースでも実行するので、
答えの値を SQL に直接書き込んでも合格しません。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.1
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_sql_practice

試しながら書くには（このディレクトリで）:
    python3 sql_practice.py                        # 実装済みの問い合わせの結果を表示
    python3 -c "import sql_practice as s; s.print_query('SELECT * FROM orders LIMIT 5')"

スキーマ（詳しくは data/ecommerce.sql）:
    customers  (customer_id, name, email, prefecture, created_at)   -- prefecture は NULL あり
    categories (category_id, name, parent_id)                        -- 木構造。最上位は parent_id が NULL
    products   (product_id, name, category_id, price)                -- price は「現在の」価格
    orders     (order_id, customer_id, ordered_at, status)           -- status: paid / shipped / cancelled
    order_items(order_id, product_id, quantity, unit_price)          -- unit_price は購入時点の単価

共通の約束:
    - 「売上」は order_items の quantity × unit_price の合計。キャンセル（status = 'cancelled'）
      された注文は、特に断りがない限り売上にも注文件数にも含めない。
    - 列の名前と順序、行の並び順は各関数の docstring の指定どおりにすること。
    - SQLite 3.25 以降（ウィンドウ関数に対応）を想定。Python 3.10 以降に同梱の SQLite なら動く。
"""
from __future__ import annotations

import sqlite3
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent / "data" / "ecommerce.sql"
if not DATA_FILE.exists():  # solutions/ から直接実行した場合
    DATA_FILE = Path(__file__).resolve().parent.parent / "exercises" / "data" / "ecommerce.sql"


# ---------------------------------------------------------------------------
# 提供済み: データベースの準備と表示（変更しなくてよい）
# ---------------------------------------------------------------------------

def connect(extra_sql: str = "") -> sqlite3.Connection:
    """data/ecommerce.sql を読み込んだインメモリの SQLite データベースに接続する。

    extra_sql を渡すと、読み込み後に追加で実行する（テストでデータを足すのに使う）。
    """
    conn = sqlite3.connect(":memory:")
    conn.executescript(DATA_FILE.read_text(encoding="utf-8"))
    if extra_sql:
        conn.executescript(extra_sql)
    return conn


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def print_query(sql: str, params: Mapping[str, Any] | Sequence[Any] = (), conn: sqlite3.Connection | None = None) -> None:
    """SQL を実行し、結果を表の形で表示する（試行錯誤用）。"""
    own = conn is None
    conn = conn or connect()
    try:
        cur = conn.execute(sql, params)
        headers = [d[0] for d in cur.description]
        rows = [["NULL" if v is None else str(v) for v in row] for row in cur.fetchall()]
    finally:
        if own:
            conn.close()
    widths = [max([_width(h)] + [_width(r[i]) for r in rows]) for i, h in enumerate(headers)]

    def line(cells: list[str]) -> str:
        return " | ".join(c + " " * (w - _width(c)) for c, w in zip(cells, widths)).rstrip()

    print(line(headers))
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(line(r))
    print(f"({len(rows)} 行)")


# ---------------------------------------------------------------------------
# 演習2-1（★☆☆）: 売上上位の顧客
# ---------------------------------------------------------------------------

def top_customers_sql() -> str:
    """売上の多い顧客の上位 n 人を返す SQL。n は名前付きパラメータ :n で受け取る。

    列: customer_id, name, revenue（その顧客の売上の合計）
    並び: revenue の降順、同額なら customer_id の昇順。上位 :n 行だけ（LIMIT）。
    売上のない顧客（キャンセル以外の注文がない顧客）は含めない（:n が顧客数より大きくても）。

    実行例: conn.execute(top_customers_sql(), {"n": 3})
    （このデータでは 鈴木 一郎 39900、伊藤 さくら 20300、高橋 美咲 20100）
    """
    raise NotImplementedError("演習2-1: top_customers_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-2（★★☆）: 顧客ごとの注文件数
# ---------------------------------------------------------------------------

def order_counts_sql() -> str:
    """すべての顧客について、キャンセルされていない注文の件数を返す SQL。

    列: customer_id, name, orders
    並び: customer_id の昇順
    注文が 1 件もない顧客や、キャンセルした注文しかない顧客も含め、orders を 0 にすること。

    ヒント: LEFT JOIN したあとに WHERE で右側のテーブルの列を絞り込むと何が起きるか。
    COUNT(*) と COUNT(列) の違いは何か。
    """
    raise NotImplementedError("演習2-2: order_counts_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-3（★☆☆）: 一度も注文していない顧客（反結合）
# ---------------------------------------------------------------------------

def customers_without_orders_sql() -> str:
    """注文（ステータスを問わない）が 1 件もない顧客を返す SQL。

    列: customer_id, name
    並び: customer_id の昇順

    ヒント: NOT EXISTS、または LEFT JOIN ... WHERE 右側 IS NULL（反結合）。
    """
    raise NotImplementedError("演習2-3: customers_without_orders_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-4（★★☆）: 子を持たないカテゴリ（NULL の罠）
# ---------------------------------------------------------------------------

def leaf_categories_sql() -> str:
    """どのカテゴリの親にもなっていないカテゴリ（木の葉）を返す SQL。

    列: category_id, name
    並び: category_id の昇順

    まず素朴に `WHERE category_id NOT IN (SELECT parent_id FROM categories)` と書いて
    実行してみよう。結果が 0 行になる理由を説明できたら、正しい書き方に直すこと。
    """
    raise NotImplementedError("演習2-4: leaf_categories_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-5（★★☆）: 月別売上と累計（ウィンドウ関数）
# ---------------------------------------------------------------------------

def monthly_revenue_sql() -> str:
    """月別の売上と、その月までの売上の累計を返す SQL。

    列: month（'YYYY-MM' 形式の文字列）, revenue, running_total
    並び: month の昇順
    売上のある月だけを含める（キャンセルされた注文しかない月は含めない）。

    ヒント: substr(ordered_at, 1, 7) で 'YYYY-MM' が取れる。
    累計は SUM(...) OVER (ORDER BY ...)。
    """
    raise NotImplementedError("演習2-5: monthly_revenue_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-6（★★☆）: カテゴリ内の売上順位
# ---------------------------------------------------------------------------

def rank_within_category_sql() -> str:
    """すべての商品について、所属カテゴリ（products.category_id）内での売上順位を返す SQL。

    列: category_id, product_id, revenue, category_rank
    - revenue: その商品の売上。一度も売れていない商品は 0（NULL ではない）。
    - category_rank: 同じカテゴリの中での revenue の降順の順位。同額は同順位で、
      次の順位は人数分飛ばす（1, 1, 3 …）。
    並び: category_id の昇順、category_rank の昇順、product_id の昇順

    ヒント: RANK() OVER (PARTITION BY ... ORDER BY ...)。
    （列名を rank にしないのは、MySQL 8.0 では RANK が予約語だから）
    """
    raise NotImplementedError("演習2-6: rank_within_category_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-7（★★★）: カテゴリのパス（再帰 CTE）
# ---------------------------------------------------------------------------

def category_paths_sql() -> str:
    """すべてのカテゴリについて、最上位からのパスと深さを返す SQL。

    列: category_id, path, depth
    - path: 最上位から自分までのカテゴリ名を ' > '（空白・大なり・空白）でつないだ文字列。
      例: '本 > コンピュータ > データベース'
    - depth: 最上位カテゴリが 1、その子が 2 …
    並び: category_id の昇順

    ヒント: WITH RECURSIVE。アンカー部で parent_id IS NULL の行を選び、
    再帰部で子カテゴリをつなぐ。文字列の連結は ||。
    """
    raise NotImplementedError("演習2-7: category_paths_sql を実装してください")


# ---------------------------------------------------------------------------
# 演習2-8（★★★）: リピート購入率
# ---------------------------------------------------------------------------

def repeat_purchase_rate_sql() -> str:
    """リピート購入率を 1 行 1 列（列名 rate）で返す SQL。

    リピート購入率 =（キャンセル以外の注文が 2 件以上ある顧客の数）
                   ÷（キャンセル以外の注文が 1 件以上ある顧客の数）
    - 実数（REAL）で返し、ROUND(…, 4) で小数第 4 位に丸めること（このデータでは 0.7143）。
    - 分母が 0（購入者がいない）なら NULL を返すこと。

    ヒント: 整数 ÷ 整数 は SQLite でも PostgreSQL でも整数除算になる（5 / 7 = 0）。
    """
    raise NotImplementedError("演習2-8: repeat_purchase_rate_sql を実装してください")


if __name__ == "__main__":
    for name, fn, params in [
        ("演習2-1 top_customers_sql（n=3）", top_customers_sql, {"n": 3}),
        ("演習2-2 order_counts_sql", order_counts_sql, {}),
        ("演習2-3 customers_without_orders_sql", customers_without_orders_sql, {}),
        ("演習2-4 leaf_categories_sql", leaf_categories_sql, {}),
        ("演習2-5 monthly_revenue_sql", monthly_revenue_sql, {}),
        ("演習2-6 rank_within_category_sql", rank_within_category_sql, {}),
        ("演習2-7 category_paths_sql", category_paths_sql, {}),
        ("演習2-8 repeat_purchase_rate_sql", repeat_purchase_rate_sql, {}),
    ]:
        print(f"== {name}")
        try:
            print_query(fn(), params)
        except NotImplementedError as e:
            print(f"（未実装: {e}）")
        print()
