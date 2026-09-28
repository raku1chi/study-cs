"""6.3 トランザクションと同時実行制御 — 演習3: 在庫の引き当てを安全に書く（SQLite）

EC サイトの在庫の引き当てを題材に、アプリケーションで同時実行を正しく扱う定石を実装します。
テストは同じデータベースファイルに 2 つ以上の接続を開き、処理の割り込み（インターリーブ）を
再現して確かめます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.3
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_inventory

約束:
    - 接続は connect() で開く（自動コミットモード: isolation_level=None）。
      1 つの SQL 文はそれだけで 1 つのトランザクションになる。複数の文をまとめるときは
      自分で BEGIN ... COMMIT / ROLLBACK を実行する。
    - 数量（qty）が 0 以下なら ValueError。存在しない商品なら KeyError。

悪い例として、読んでから書く素朴な実装 reserve_naive を提供しています。テストの
test_naive_read_modify_write_loses_update で、更新が失われる様子を確かめてください。
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping

# ---------------------------------------------------------------------------
# 提供済み（変更しなくてよい）
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
    """楽観的並行制御で、再試行の上限まで競合が続いた。"""


def connect(path: str) -> sqlite3.Connection:
    """自動コミットモードの接続を開く（他の接続のロックは最大 10 秒待つ）。"""
    conn = sqlite3.connect(path, isolation_level=None, timeout=10)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def setup(path: str, stocks: Mapping[int, int]) -> None:
    """スキーマを作り、商品 {id: 在庫数} を登録する。"""
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
    """現在の在庫数。存在しない商品なら KeyError。"""
    row = conn.execute("SELECT stock FROM products WHERE id = ?", (product_id,)).fetchone()
    if row is None:
        raise KeyError(product_id)
    return row[0]


def reserve_naive(
    conn: sqlite3.Connection, product_id: int, qty: int, *, between: Callable[[], None] | None = None
) -> bool:
    """【悪い例】在庫を読み、足りれば「読んだ値 − qty」を書き込む。

    between は、読んでから書くまでの間に呼ばれる（テストで、他の接続の処理を割り込ませるため）。
    読んだ値が古くなっていても気づかずに上書きするので、同時に実行すると更新が失われる。
    """
    stock = get_stock(conn, product_id)
    if stock < qty:
        return False
    if between is not None:
        between()
    conn.execute("UPDATE products SET stock = ? WHERE id = ?", (stock - qty, product_id))
    return True


# ---------------------------------------------------------------------------
# 演習3-1（★☆☆）: 条件付きの UPDATE 1 文で引き当てる
# ---------------------------------------------------------------------------

def reserve_atomic(conn: sqlite3.Connection, product_id: int, qty: int) -> bool:
    """在庫が qty 以上なら qty 減らして True、足りなければ何もせず False。

    「在庫を読んで判断してから書く」のではなく、判断と更新を 1 つの UPDATE 文で行うこと:
        UPDATE products SET stock = stock - ?, ... WHERE id = ? AND stock >= ?
    変更された行数（cursor.rowcount）で成否が分かる。
    - 在庫を変えるときは version も 1 増やすこと（演習3-2 の楽観的並行制御と併用しても
      安全にするため。在庫を変える更新が 1 つでも version を増やさないと、検査をすり抜ける）。
    - 在庫が足りないのか商品が存在しないのかは rowcount だけでは区別できない。
      0 行だったら、商品の存在を確かめて、存在しなければ KeyError。
    """
    raise NotImplementedError("演習3-1: reserve_atomic を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★★☆）: バージョン列による楽観的並行制御
# ---------------------------------------------------------------------------

def reserve_optimistic(
    conn: sqlite3.Connection,
    product_id: int,
    qty: int,
    *,
    max_retries: int = 3,
    on_read: Callable[[int], None] | None = None,
) -> bool:
    """version 列を使った楽観的並行制御で在庫を引き当てる。

    各試行（attempt = 0, 1, 2, ...）で:
      1. SELECT stock, version で現在の値を読む（なければ KeyError）。
      2. stock < qty なら False を返す（再試行しない）。
      3. on_read が渡されていれば on_read(attempt) を呼ぶ（テストが他の更新を割り込ませる）。
      4. UPDATE products SET stock = 読んだ stock − qty, version = version + 1
         WHERE id = ? AND version = 読んだ version
         を実行し、1 行更新されたら True を返す。0 行なら、読んだ後に誰かが更新したので、やり直す。
    最初の試行と、max_retries 回の再試行（合計 max_retries + 1 回）で成功しなければ ConflictError。

    ロックを取らずに進み、書くときに「読んだときから変わっていないこと」を確かめる方式。
    競合が少ない場面では待ちが発生せず速いが、競合が多いと再試行が増える。
    """
    raise NotImplementedError("演習3-2: reserve_optimistic を実装してください")


# ---------------------------------------------------------------------------
# 演習3-3（★★☆）: 複数商品の注文を、全部かゼロかで、1 回だけ
# ---------------------------------------------------------------------------

def place_order(conn: sqlite3.Connection, request_id: str, items: Mapping[int, int]) -> str:
    """注文 {商品 ID: 数量} を 1 つのトランザクションで処理し、結果を文字列で返す。

    - "created": orders に 1 行（request_id）、order_items に商品ごとの行を追加し、
      各商品の在庫を減らした（version も増やす）。
    - "insufficient_stock": どれか 1 つでも在庫が足りなかった。何も変更しない
      （途中まで減らした在庫も元に戻す＝原子性）。
    - "duplicate": 同じ request_id の注文がすでにある（二重送信・再試行）。何も変更しない。
    - 存在しない商品を含むなら、何も変更せずに KeyError。items が空・数量が 0 以下なら ValueError。
    - どの結果でも、関数から戻るときにトランザクションを開いたままにしないこと。

    ヒント:
    - `BEGIN IMMEDIATE` でトランザクションを始める（SQLite で、最初から書き込みのロックを取る）。
    - 重複の検出は「先に SELECT で確かめる」のではなく、orders.request_id の UNIQUE 制約に任せる。
      INSERT が sqlite3.IntegrityError になったら重複（事前の SELECT は、同時に 2 つの要求が来ると
      両方とも「まだない」と判断してしまう）。
    - 在庫の更新は演習3-1 と同じ条件付き UPDATE。0 行なら ROLLBACK。
    - 失敗した（ロールバックした）注文は記録されないので、同じ request_id で再試行できる。
    """
    raise NotImplementedError("演習3-3: place_order を実装してください")
