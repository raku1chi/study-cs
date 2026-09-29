"""6.2 インデックスとクエリ処理 — 演習3 解答例: インデックス設計とキーセットページネーション

演習の仕様は exercises/index_tuning.py の docstring を参照してください。
"""
from __future__ import annotations

import random
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# 提供済み: スキーマ・データ・問い合わせ（スタブと同じ）
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE customers (
  id         INTEGER PRIMARY KEY,
  email      TEXT NOT NULL,
  name       TEXT NOT NULL,
  prefecture TEXT NOT NULL
);
CREATE TABLE orders (
  id          INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers (id),
  status      TEXT NOT NULL,        -- pending（約 1%）/ paid / shipped / cancelled
  created_at  TEXT NOT NULL,        -- 'YYYY-MM-DD HH:MM:SS'（分単位なので同時刻の注文が多い）
  total       INTEGER NOT NULL,
  note        TEXT
);
"""

INDEX_BUDGET = 5

QUERIES: dict[str, str] = {
    "orders_of_customer": (
        "SELECT id, created_at, total FROM orders "
        "WHERE customer_id = :customer_id ORDER BY created_at DESC LIMIT 20"
    ),
    "recent_order_count": (
        "SELECT COUNT(*) FROM orders WHERE customer_id = :customer_id AND created_at >= :since"
    ),
    "customer_by_email": "SELECT id, name FROM customers WHERE lower(email) = lower(:email)",
    "pending_orders": (
        "SELECT id, customer_id, created_at FROM orders "
        "WHERE status = 'pending' ORDER BY created_at LIMIT 50"
    ),
    "daily_sales": (
        "SELECT date(created_at) AS day, SUM(total) AS sales FROM orders "
        "WHERE created_at >= :since AND created_at < :until GROUP BY date(created_at)"
    ),
    "paid_by_customer": (
        "SELECT customer_id, COUNT(*) AS n, SUM(total) AS amount FROM orders "
        "WHERE status = 'paid' GROUP BY customer_id"
    ),
}

SAMPLE_PARAMS: dict[str, dict[str, Any]] = {
    "orders_of_customer": {"customer_id": 42},
    "recent_order_count": {"customer_id": 42, "since": "2025-07-01"},
    "customer_by_email": {"email": "USER42@example.com"},
    "pending_orders": {},
    "daily_sales": {"since": "2025-03-01", "until": "2025-04-01"},
    "paid_by_customer": {},
}


def create_database(n_customers: int = 2000, n_orders: int = 50_000, seed: int = 62) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    rng = random.Random(seed)
    prefectures = ["東京都", "大阪府", "神奈川県", "愛知県", "福岡県", "北海道", "京都府", "兵庫県"]
    conn.executemany(
        "INSERT INTO customers VALUES (?, ?, ?, ?)",
        [(i, f"User{i}@Example.com", f"user{i}", rng.choice(prefectures)) for i in range(1, n_customers + 1)],
    )
    rows = []
    for i in range(1, n_orders + 1):
        status = rng.choices(["pending", "paid", "shipped", "cancelled"], [1, 30, 60, 9])[0]
        day = rng.randrange(365)
        minute = rng.randrange(24 * 60)
        month, dom = min(12, 1 + day // 31), 1 + day % 28
        created_at = f"2025-{month:02d}-{dom:02d} {minute // 60:02d}:{minute % 60:02d}:00"
        rows.append((i, rng.randrange(1, n_customers + 1), status, created_at, rng.randrange(500, 50_000), None))
    conn.executemany("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?)", rows)
    conn.commit()
    return conn


def explain(conn: sqlite3.Connection, sql: str, params: dict[str, Any] | None = None) -> list[str]:
    return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params or {})]


def apply_indexes(conn: sqlite3.Connection, statements: list[str]) -> None:
    for stmt in statements:
        conn.execute(stmt)
    conn.execute("ANALYZE")  # 統計情報を集める（プランナはこれを使って計画を選ぶ）


def show_plans(statements: list[str] | None = None) -> None:
    conn = create_database()
    if statements:
        apply_indexes(conn, statements)
    for name, sql in QUERIES.items():
        print(f"== {name}")
        for line in explain(conn, sql, SAMPLE_PARAMS[name]):
            print("   ", line)
    conn.close()


# ---------------------------------------------------------------------------
# 演習3-1: インデックスの設計
# ---------------------------------------------------------------------------

def index_statements() -> list[str]:
    return [
        # 等価条件の列（customer_id）を先に、範囲・並べ替えの列（created_at）を後に。
        # orders_of_customer の WHERE と ORDER BY を 1 本で満たし、recent_order_count は
        # この索引だけで答えられる（COUNT(*) に表本体は不要なのでカバリングになる）。
        "CREATE INDEX idx_orders_customer_created ON orders (customer_id, created_at)",
        # 列に関数をかけた条件は、同じ式のインデックス（式インデックス）でしか使えない
        "CREATE INDEX idx_customers_lower_email ON customers (lower(email))",
        # pending は全体の約 1%。その行だけを持つ部分インデックスは小さく、created_at 順に並んでいる。
        # SELECT する customer_id も入れてカバリングにする（id は rowid なので索引に含まれる）。
        # (created_at) だけの部分インデックスでは、SQLite 3.45 はこれを使うが、3.50 は
        # idx_orders_status_customer_total での検索と並べ替え（USE TEMP B-TREE）を選んでしまう。
        # 明らかに有利なインデックスにしておくと、オプティマイザのバージョンが変わっても計画が安定する
        "CREATE INDEX idx_orders_pending ON orders (created_at, customer_id) WHERE status = 'pending'",
        # created_at の範囲で絞り、total まで索引に入れればカバリングになる。id（rowid）を
        # 2 列目に明示すると (created_at, id) の順に並ぶので、キーセットページネーションにも使える
        "CREATE INDEX idx_orders_created_id_total ON orders (created_at, id, total)",
        # 等価条件 status → GROUP BY の customer_id → 集計する total の順。
        # status = 'paid' の範囲の中で customer_id 順に並ぶので、GROUP BY の並べ替えも不要になる
        "CREATE INDEX idx_orders_status_customer_total ON orders (status, customer_id, total)",
    ]


# ---------------------------------------------------------------------------
# 演習3-2: キーセットページネーション
# ---------------------------------------------------------------------------

FIRST_PAGE_SQL = (
    "SELECT id, created_at, total FROM orders ORDER BY created_at DESC, id DESC LIMIT :page_size"
)


def keyset_page_sql() -> str:
    # 行値（row value）の比較 (a, b) < (x, y) は「a < x、または a = x かつ b < y」と同じ意味。
    # created_at だけで比べると、同時刻の注文がページの境目にあったときに取りこぼす。
    return (
        "SELECT id, created_at, total FROM orders "
        "WHERE (created_at, id) < (:last_created_at, :last_id) "
        "ORDER BY created_at DESC, id DESC LIMIT :page_size"
    )


def fetch_page(
    conn: sqlite3.Connection, after: tuple[str, int] | None = None, page_size: int = 20
) -> list[tuple[int, str, int]]:
    if page_size <= 0:
        raise ValueError("page_size は 1 以上にしてください")
    if after is None:
        return conn.execute(FIRST_PAGE_SQL, {"page_size": page_size}).fetchall()
    last_created_at, last_id = after
    return conn.execute(
        keyset_page_sql(),
        {"last_created_at": last_created_at, "last_id": last_id, "page_size": page_size},
    ).fetchall()


if __name__ == "__main__":
    print("### インデックスなし")
    show_plans()
    print("\n### index_statements() を適用")
    show_plans(index_statements())
