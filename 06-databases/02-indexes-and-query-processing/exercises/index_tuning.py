"""6.2 インデックスとクエリ処理 — 演習3: インデックスを設計する（SQLite）

注文データ（顧客 2,000 人・注文 50,000 件）に対する 6 つの問い合わせ QUERIES が、
すべて全件走査にならず効率よく実行されるように、CREATE INDEX 文を設計します。
続いて、OFFSET を使わない「キーセットページネーション」を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.2
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_index_tuning

実行計画を見ながら試すには（このディレクトリで）:
    python3 index_tuning.py      # インデックスなし／あり の EXPLAIN QUERY PLAN を表示

EXPLAIN QUERY PLAN の読み方（SQLite。3.36 より前のバージョンでは "SCAN TABLE orders" のように
TABLE が入る）:
    SCAN orders                               表の全件走査（遅い）
    SEARCH orders USING INDEX idx (a=?)       インデックスで範囲を絞ってから表を読む
    SEARCH orders USING COVERING INDEX idx    インデックスだけで答えられる（表を読まない）
    SCAN orders USING INDEX idx               インデックスを先頭から順に読む（部分インデックスなら小さい）
    USE TEMP B-TREE FOR ORDER BY / GROUP BY   結果を並べ替えるための一時的な作業が発生している

テストは、データを作り → index_statements() の文を実行し → ANALYZE で統計情報を集めてから、
各問い合わせの実行計画を確かめます。
"""
from __future__ import annotations

import random
import sqlite3
from typing import Any

# ---------------------------------------------------------------------------
# 提供済み: スキーマ・データ・問い合わせ（変更しなくてよい）
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

# 作ってよいインデックスの数の上限（インデックスは書き込みを遅くし、容量も使うため）
INDEX_BUDGET = 5

QUERIES: dict[str, str] = {
    # ある顧客の最新 20 件の注文
    "orders_of_customer": (
        "SELECT id, created_at, total FROM orders "
        "WHERE customer_id = :customer_id ORDER BY created_at DESC LIMIT 20"
    ),
    # ある顧客の、ある日時以降の注文数
    "recent_order_count": (
        "SELECT COUNT(*) FROM orders WHERE customer_id = :customer_id AND created_at >= :since"
    ),
    # メールアドレスでログイン（大文字・小文字を区別しない）
    "customer_by_email": "SELECT id, name FROM customers WHERE lower(email) = lower(:email)",
    # 未処理（pending）の注文を古い順に 50 件（管理画面）
    "pending_orders": (
        "SELECT id, customer_id, created_at FROM orders "
        "WHERE status = 'pending' ORDER BY created_at LIMIT 50"
    ),
    # 期間内の日別売上（レポート）
    "daily_sales": (
        "SELECT date(created_at) AS day, SUM(total) AS sales FROM orders "
        "WHERE created_at >= :since AND created_at < :until GROUP BY date(created_at)"
    ),
    # 支払い済み（paid）の注文の、顧客別の件数と金額
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
    """スキーマを作り、決まった乱数の種でデータを入れたインメモリの DB を返す（インデックスなし）。"""
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
    """EXPLAIN QUERY PLAN の各行の説明（detail 列）をリストで返す。"""
    return [row[3] for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params or {})]


def apply_indexes(conn: sqlite3.Connection, statements: list[str]) -> None:
    """インデックスを作り、ANALYZE で統計情報を集める（テストと同じ手順）。"""
    for stmt in statements:
        conn.execute(stmt)
    conn.execute("ANALYZE")


def show_plans(statements: list[str] | None = None) -> None:
    """（試行錯誤用）各問い合わせの実行計画を表示する。"""
    conn = create_database()
    if statements:
        apply_indexes(conn, statements)
    for name, sql in QUERIES.items():
        print(f"== {name}")
        for line in explain(conn, sql, SAMPLE_PARAMS[name]):
            print("   ", line)
    conn.close()


# ---------------------------------------------------------------------------
# 演習3-1（★★☆）: インデックスの設計
# ---------------------------------------------------------------------------

def index_statements() -> list[str]:
    """QUERIES を効率よく実行するための CREATE INDEX 文のリストを返す（INDEX_BUDGET 個以内）。

    テストが確かめる条件（ANALYZE 実行後の EXPLAIN QUERY PLAN）:
      - orders_of_customer: customer_id の等価条件でインデックスを使い、ORDER BY のための
        一時的な並べ替え（USE TEMP B-TREE）がない
      - recent_order_count: インデックスだけで答える（COVERING INDEX）。customer_id と
        created_at の両方の条件がインデックスで使われる
      - customer_by_email: customers を全件走査しない
      - pending_orders: orders を全件走査せず、一時的な並べ替えもない
      - daily_sales: created_at の範囲をインデックスで絞り、COVERING INDEX で答える
        （date() でのグループ化のための TEMP B-TREE は許す）
      - paid_by_customer: COVERING INDEX で答え、一時的な並べ替えがない
      - （演習3-2 の keyset_page_sql() も、ここで作ったインデックスで並べ替えなしに実行できること）

    6 つの問い合わせとページネーションに対して、インデックスは 5 個まで。
    複合インデックスの「左端の列から順に使われる」性質を活かして、1 つのインデックスで
    複数の問い合わせを満たす工夫が必要になる。

    ヒント: 複合インデックスの列の順序は「等価条件の列 → 範囲条件や ORDER BY / GROUP BY の列
    → SELECT で読むだけの列（カバリング用）」。関数をかけた列には式インデックス、
    ごく一部の行だけを対象にする条件には部分インデックス（CREATE INDEX ... WHERE ...）が使える。
    """
    raise NotImplementedError("演習3-1: index_statements を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★★☆）: キーセットページネーション
# ---------------------------------------------------------------------------

# 先頭ページの SQL（提供済み）: 新しい順。同時刻の注文は id の大きい順
FIRST_PAGE_SQL = (
    "SELECT id, created_at, total FROM orders ORDER BY created_at DESC, id DESC LIMIT :page_size"
)


def keyset_page_sql() -> str:
    """2 ページ目以降を取得する SQL を返す。

    - 並び順は FIRST_PAGE_SQL と同じ（created_at の降順、同時刻なら id の降順）。
    - 前のページの最後の行の (created_at, id) を名前付きパラメータ :last_created_at と :last_id で、
      ページの行数を :page_size で受け取る。
    - 列は id, created_at, total。
    - OFFSET を使わないこと（OFFSET n は n 行を読み飛ばすために n 行を読む）。
    - 同時刻（created_at が等しい）の注文がページの境目にあっても、取りこぼしや重複がないこと。

    ヒント: SQLite 3.15 以降・PostgreSQL・MySQL では行値（row value）の比較
    (created_at, id) < (:last_created_at, :last_id) が書ける。
    """
    raise NotImplementedError("演習3-2: keyset_page_sql を実装してください")


def fetch_page(
    conn: sqlite3.Connection, after: tuple[str, int] | None = None, page_size: int = 20
) -> list[tuple[int, str, int]]:
    """1 ページ分の (id, created_at, total) のリストを返す。

    - after が None なら先頭ページ（FIRST_PAGE_SQL）。
    - after が (created_at, id) なら、その行の「次」から（keyset_page_sql()）。
      呼び出し側は、前のページの最後の行の (created_at, id) を after に渡す。
    - page_size が 0 以下なら ValueError。
    - 最後のページの次を求めたら空リスト。
    """
    raise NotImplementedError("演習3-2: fetch_page を実装してください")


if __name__ == "__main__":
    print("### インデックスなし")
    show_plans()
    try:
        statements = index_statements()
    except NotImplementedError:
        print("\n（index_statements() はまだ実装されていません）")
    else:
        print("\n### index_statements() を適用")
        show_plans(statements)
