"""6.1 リレーショナルモデルとSQL — 演習2 解答例: SQL の問い合わせ

演習の仕様は exercises/sql_practice.py の docstring を参照してください。
別解も多くあります。コメントで代表的な別解と、陥りやすい誤りを示しています。
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
# 提供済み: データベースの準備と表示（スタブと同じ）
# ---------------------------------------------------------------------------

def connect(extra_sql: str = "") -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(DATA_FILE.read_text(encoding="utf-8"))
    if extra_sql:
        conn.executescript(extra_sql)
    return conn


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def print_query(sql: str, params: Mapping[str, Any] | Sequence[Any] = (), conn: sqlite3.Connection | None = None) -> None:
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
# 演習2-1: 売上上位の顧客
# ---------------------------------------------------------------------------

def top_customers_sql() -> str:
    # 売上は order_items の quantity × unit_price（購入時点の単価）で計算する。
    # products.price は「現在の価格」なので、売上の計算に使ってはいけない。
    return """
        SELECT c.customer_id, c.name, SUM(oi.quantity * oi.unit_price) AS revenue
        FROM customers AS c
        JOIN orders AS o       ON o.customer_id = c.customer_id
        JOIN order_items AS oi ON oi.order_id = o.order_id
        WHERE o.status <> 'cancelled'
        GROUP BY c.customer_id, c.name
        ORDER BY revenue DESC, c.customer_id
        LIMIT :n
    """


# ---------------------------------------------------------------------------
# 演習2-2: 顧客ごとの注文件数（LEFT JOIN と COUNT の落とし穴）
# ---------------------------------------------------------------------------

def order_counts_sql() -> str:
    # 誤り1: WHERE o.status <> 'cancelled' と書くと、注文のない顧客（o.status が NULL）が
    #        WHERE で落ち、LEFT JOIN が INNER JOIN と同じ結果になる。条件は ON に書く。
    # 誤り2: COUNT(*) は「行数」なので、注文のない顧客も（NULL で埋めた 1 行があるため）1 になる。
    #        COUNT(o.order_id) なら NULL を数えないので 0 になる。
    return """
        SELECT c.customer_id, c.name, COUNT(o.order_id) AS orders
        FROM customers AS c
        LEFT JOIN orders AS o
          ON o.customer_id = c.customer_id AND o.status <> 'cancelled'
        GROUP BY c.customer_id, c.name
        ORDER BY c.customer_id
    """


# ---------------------------------------------------------------------------
# 演習2-3: 一度も注文していない顧客（反結合）
# ---------------------------------------------------------------------------

def customers_without_orders_sql() -> str:
    # 別解1: LEFT JOIN orders AS o ON ... WHERE o.order_id IS NULL
    # 別解2: WHERE c.customer_id NOT IN (SELECT customer_id FROM orders)
    #        （orders.customer_id は NOT NULL なのでここでは正しく動くが、NULL を含みうる列に
    #         対して NOT IN を使う癖はつけない方がよい。演習2-4 を参照）
    return """
        SELECT c.customer_id, c.name
        FROM customers AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM orders AS o WHERE o.customer_id = c.customer_id
        )
        ORDER BY c.customer_id
    """


# ---------------------------------------------------------------------------
# 演習2-4: 子を持たないカテゴリ（NOT IN と NULL の罠）
# ---------------------------------------------------------------------------

def leaf_categories_sql() -> str:
    # 素朴な書き方: WHERE category_id NOT IN (SELECT parent_id FROM categories)
    # parent_id には最上位カテゴリの NULL が含まれるため、x NOT IN (..., NULL) は
    # 「x <> ... AND x <> NULL」＝ TRUE か UNKNOWN にしかならず、1 行も返らない。
    # NOT EXISTS は NULL の影響を受けない（相関サブクエリが 0 行かどうかだけを見る）。
    return """
        SELECT c.category_id, c.name
        FROM categories AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM categories AS child WHERE child.parent_id = c.category_id
        )
        ORDER BY c.category_id
    """


# ---------------------------------------------------------------------------
# 演習2-5: 月別売上と累計（ウィンドウ関数）
# ---------------------------------------------------------------------------

def monthly_revenue_sql() -> str:
    # 月ごとに集約してから（CTE）、その結果にウィンドウ関数をかける。
    # ウィンドウ関数は GROUP BY の後（SELECT の段階）に評価されるので、
    # SUM(SUM(...)) OVER (ORDER BY ...) と 1 段で書くこともできる。
    # フレームを ROWS で明示しておくと、ORDER BY の値が重複しても 1 行ずつ累積される
    # （既定の RANGE フレームでは同じ値の行がまとめて足される）。
    return """
        WITH monthly AS (
            SELECT substr(o.ordered_at, 1, 7) AS month,
                   SUM(oi.quantity * oi.unit_price) AS revenue
            FROM orders AS o
            JOIN order_items AS oi ON oi.order_id = o.order_id
            WHERE o.status <> 'cancelled'
            GROUP BY substr(o.ordered_at, 1, 7)
        )
        SELECT month, revenue,
               SUM(revenue) OVER (ORDER BY month
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running_total
        FROM monthly
        ORDER BY month
    """


# ---------------------------------------------------------------------------
# 演習2-6: カテゴリ内の売上順位（RANK）
# ---------------------------------------------------------------------------

def rank_within_category_sql() -> str:
    # 先に「売れた分」を商品ごとに集計し、それを products に LEFT JOIN する。
    # products と order_items と orders を 1 段で LEFT JOIN して WHERE で status を絞ると、
    # 一度も売れていない商品（status が NULL）が落ちてしまう。
    return """
        WITH sold AS (
            SELECT oi.product_id, SUM(oi.quantity * oi.unit_price) AS revenue
            FROM order_items AS oi
            JOIN orders AS o ON o.order_id = oi.order_id
            WHERE o.status <> 'cancelled'
            GROUP BY oi.product_id
        ),
        product_revenue AS (
            SELECT p.category_id, p.product_id, COALESCE(s.revenue, 0) AS revenue
            FROM products AS p
            LEFT JOIN sold AS s ON s.product_id = p.product_id
        )
        SELECT category_id, product_id, revenue,
               RANK() OVER (PARTITION BY category_id ORDER BY revenue DESC) AS category_rank
        FROM product_revenue
        ORDER BY category_id, category_rank, product_id
    """


# ---------------------------------------------------------------------------
# 演習2-7: カテゴリのパス（再帰 CTE）
# ---------------------------------------------------------------------------

def category_paths_sql() -> str:
    # アンカー部で最上位（parent_id IS NULL）を選び、再帰部で子をつなげていく。
    # 木の深さの分だけ再帰部が繰り返され、新しい行が生まれなくなったら止まる。
    # （データに循環があると止まらないので、実務では depth に上限を設けることも多い）
    return """
        WITH RECURSIVE tree(category_id, path, depth) AS (
            SELECT category_id, name, 1
            FROM categories
            WHERE parent_id IS NULL
            UNION ALL
            SELECT c.category_id, t.path || ' > ' || c.name, t.depth + 1
            FROM categories AS c
            JOIN tree AS t ON c.parent_id = t.category_id
        )
        SELECT category_id, path, depth
        FROM tree
        ORDER BY category_id
    """


# ---------------------------------------------------------------------------
# 演習2-8: リピート購入率（整数除算の罠）
# ---------------------------------------------------------------------------

def repeat_purchase_rate_sql() -> str:
    # 整数どうしの割り算は、SQLite でも PostgreSQL でも切り捨ての整数除算になる（5 / 7 = 0）。
    # 1.0 * を掛けるか CAST(... AS REAL) で実数にしてから割る。
    # NULLIF(COUNT(*), 0) は、購入者が 0 人のときにゼロ除算を避けて NULL を返すため
    # （SQLite は x / 0 を NULL にするが、PostgreSQL はエラーになる）。
    return """
        WITH per_customer AS (
            SELECT customer_id, COUNT(*) AS n
            FROM orders
            WHERE status <> 'cancelled'
            GROUP BY customer_id
        )
        SELECT ROUND(1.0 * SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0), 4) AS rate
        FROM per_customer
    """


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
