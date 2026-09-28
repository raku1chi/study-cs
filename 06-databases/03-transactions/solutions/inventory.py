"""6.3 トランザクションと同時実行制御 — 演習3 解答例: 在庫の引き当て（SQLite）

演習の仕様は exercises/inventory.py の docstring を参照してください。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping

# ---------------------------------------------------------------------------
# 提供済み（スタブと同じ）
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE products (
  id      INTEGER PRIMARY KEY,
  name    TEXT NOT NULL,
  stock   INTEGER NOT NULL CHECK (stock >= 0),
  version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE orders (
  id         INTEGER PRIMARY KEY,
  request_id TEXT NOT NULL UNIQUE
);
CREATE TABLE order_items (
  order_id   INTEGER NOT NULL REFERENCES orders (id),
  product_id INTEGER NOT NULL REFERENCES products (id),
  quantity   INTEGER NOT NULL CHECK (quantity > 0),
  PRIMARY KEY (order_id, product_id)
);
"""


class ConflictError(Exception):
    pass


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup(path: str, stocks: Mapping[int, int]) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO products (id, name, stock) VALUES (?, ?, ?)",
            [(pid, f"product-{pid}", stock) for pid, stock in stocks.items()],
        )
    finally:
        conn.close()


def get_stock(conn: sqlite3.Connection, product_id: int) -> int:
    row = conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise KeyError(product_id)
    return row[0]


def reserve_naive(
    conn: sqlite3.Connection, product_id: int, qty: int, *, between: Callable[[], None] | None = None
) -> bool:
    stock = get_stock(conn, product_id)
    if stock < qty:
        return False
    if between is not None:
        between()
    conn.execute("UPDATE products SET stock = ? WHERE id = ?", (stock - qty, product_id))
    return True


def _check_qty(qty: int) -> None:
    if qty <= 0:
        raise ValueError(f"数量は 1 以上にしてください: {qty}")


# ---------------------------------------------------------------------------
# 演習3-1: 条件付きの UPDATE 1 文で引き当てる
# ---------------------------------------------------------------------------

def reserve_atomic(conn: sqlite3.Connection, product_id: int, qty: int) -> bool:
    _check_qty(qty)
    # 「読んで、判断して、書く」を DB の中の 1 文で行う。条件の判定と更新の間に
    # 他のトランザクションが割り込む隙がない（行は更新の間ロックされる）
    # version も増やしておく。楽観的並行制御（演習3-2）と併用するなら、在庫を変える
    # すべての更新が version を増やさないと、version の検査をすり抜けてしまう
    cur = conn.execute(
        "UPDATE products SET stock = stock - ?, version = version + 1 WHERE id = ? AND stock >= ?",
        (qty, product_id, qty),
    )
    if cur.rowcount == 1:
        return True
    get_stock(conn, product_id)  # 存在しない商品なら KeyError
    return False


# ---------------------------------------------------------------------------
# 演習3-2: バージョン列による楽観的並行制御
# ---------------------------------------------------------------------------

def reserve_optimistic(
    conn: sqlite3.Connection,
    product_id: int,
    qty: int,
    *,
    max_retries: int = 3,
    on_read: Callable[[int], None] | None = None,
) -> bool:
    _check_qty(qty)
    for attempt in range(max_retries + 1):
        row = conn.execute("SELECT stock, version FROM products WHERE id = ?", (product_id,)).fetchone()
        if row is None:
            raise KeyError(product_id)
        stock, version = row
        if stock < qty:
            return False
        if on_read is not None:
            on_read(attempt)  # テスト用: 読んでから書くまでの間に、他の更新を割り込ませる
        # 読んだときと version が同じ（＝誰も更新していない）ときだけ書く
        cur = conn.execute(
            "UPDATE products SET stock = ?, version = version + 1 WHERE id = ? AND version = ?",
            (stock - qty, product_id, version),
        )
        if cur.rowcount == 1:
            return True
        # 0 行: 読んだ後に誰かが更新した。最新の値を読み直してやり直す
    raise ConflictError(f"{max_retries} 回再試行しても競合が解消しませんでした")


# ---------------------------------------------------------------------------
# 演習3-3: 複数商品の注文を、全部かゼロかで、1 回だけ
# ---------------------------------------------------------------------------

def place_order(conn: sqlite3.Connection, request_id: str, items: Mapping[int, int]) -> str:
    if not items:
        raise ValueError("注文する商品がありません")
    for qty in items.values():
        _check_qty(qty)
    # BEGIN IMMEDIATE: 最初に書き込みのロックを取る（SQLite で、読み取りから書き込みへの
    # 格上げの競合による SQLITE_BUSY を避ける定石）
    conn.execute("BEGIN IMMEDIATE")
    try:
        try:
            cur = conn.execute("INSERT INTO orders (request_id) VALUES (?)", (request_id,))
        except sqlite3.IntegrityError:
            # 一意制約が「同じ要求は 1 回だけ」を保証する。アプリでの事前チェックは競合に弱い
            conn.execute("ROLLBACK")
            return "duplicate"
        order_id = cur.lastrowid
        for product_id, qty in sorted(items.items()):  # 常に同じ順で更新するとデッドロックしにくい
            cur = conn.execute(
                "UPDATE products SET stock = stock - ?, version = version + 1 WHERE id = ? AND stock >= ?",
                (qty, product_id, qty),
            )
            if cur.rowcount == 0:
                exists = conn.execute("SELECT 1 FROM products WHERE id = ?", (product_id,)).fetchone()
                conn.execute("ROLLBACK")  # 途中までの更新もすべて取り消す（原子性）
                if exists is None:
                    raise KeyError(product_id)
                return "insufficient_stock"
            conn.execute(
                "INSERT INTO order_items (order_id, product_id, quantity) VALUES (?, ?, ?)",
                (order_id, product_id, qty),
            )
        conn.execute("COMMIT")
        return "created"
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
