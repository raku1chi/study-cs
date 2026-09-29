"""7.5 メッセージングとイベント駆動 — 演習: Transactional Outbox と冪等なコンシューマ（解答例）

演習の仕様は exercises/outbox.py の docstring を参照してください。
"""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Callable

PRODUCER_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id       TEXT PRIMARY KEY,
    customer TEXT NOT NULL,
    amount   INTEGER NOT NULL CHECK (amount > 0)
);
CREATE TABLE IF NOT EXISTS outbox (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT NOT NULL UNIQUE,
    event_type   TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    payload      TEXT NOT NULL,
    published_at REAL
);
"""

CONSUMER_SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_messages (
    event_id     TEXT PRIMARY KEY,
    processed_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_totals (
    customer    TEXT PRIMARY KEY,
    total       INTEGER NOT NULL,
    order_count INTEGER NOT NULL
);
"""


def init_producer_db(conn: sqlite3.Connection) -> None:
    conn.executescript(PRODUCER_SCHEMA)


def init_consumer_db(conn: sqlite3.Connection) -> None:
    conn.executescript(CONSUMER_SCHEMA)


class SimulatedCrash(BaseException):
    """プロセスが落ちたことを表す（テスト用）。"""


class FakeBroker:
    def __init__(self) -> None:
        self.messages: list[dict] = []
        self._failures = 0

    def fail_next(self, n: int = 1) -> None:
        self._failures += n

    def publish(self, message: dict) -> None:
        if self._failures:
            self._failures -= 1
            raise ConnectionError("ブローカーに接続できません")
        self.messages.append(dict(message))


def place_order_dual_write(
    conn: sqlite3.Connection,
    broker: FakeBroker,
    order_id: str,
    customer: str,
    amount: int,
    crash_before_publish: bool = False,
) -> None:
    """悪い例: データベースへのコミットとメッセージの送信を別々に行う（二重書き込み）。"""
    with conn:
        conn.execute("INSERT INTO orders (id, customer, amount) VALUES (?, ?, ?)", (order_id, customer, amount))
    if crash_before_publish:
        raise SimulatedCrash()  # ここで落ちると、注文はあるのにイベントは永遠に送られない
    broker.publish({"event_type": "OrderPlaced", "payload": {"order_id": order_id, "customer": customer, "amount": amount}})


# ---------------------------------------------------------------------------
# 演習4: 注文とイベントを 1 つのトランザクションで書く
# ---------------------------------------------------------------------------


def place_order(
    conn: sqlite3.Connection,
    order_id: str,
    customer: str,
    amount: int,
    event_id: str | None = None,
) -> str:
    event_id = event_id or str(uuid.uuid4())
    payload = json.dumps(
        {"order_id": order_id, "customer": customer, "amount": amount}, ensure_ascii=False, sort_keys=True
    )
    # 業務データとイベントを同じローカルトランザクションで書く。両方残るか、両方残らないかのどちらか
    with conn:
        conn.execute("INSERT INTO orders (id, customer, amount) VALUES (?, ?, ?)", (order_id, customer, amount))
        conn.execute(
            "INSERT INTO outbox (event_id, event_type, aggregate_id, payload) VALUES (?, ?, ?, ?)",
            (event_id, "OrderPlaced", order_id, payload),
        )
    return event_id


# ---------------------------------------------------------------------------
# 演習5: リレー（outbox からブローカーへ）
# ---------------------------------------------------------------------------


class OutboxRelay:
    def __init__(
        self,
        conn: sqlite3.Connection,
        broker: FakeBroker,
        crash_after_publish: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.conn = conn
        self.broker = broker
        self.crash_after_publish = crash_after_publish
        self.clock = clock

    def pending(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM outbox WHERE published_at IS NULL").fetchone()[0]

    def run_once(self, batch_size: int = 100) -> int:
        rows = self.conn.execute(
            "SELECT seq, event_id, event_type, aggregate_id, payload FROM outbox"
            " WHERE published_at IS NULL ORDER BY seq LIMIT ?",
            (batch_size,),
        ).fetchall()
        published = 0
        for seq, event_id, event_type, aggregate_id, payload in rows:
            message = {
                "event_id": event_id,
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "payload": json.loads(payload),
            }
            try:
                self.broker.publish(message)
            except ConnectionError:
                break  # 順序を守るため、失敗したらそこで止めて次回やり直す
            if self.crash_after_publish is not None and self.crash_after_publish(event_id):
                # 送信した直後、「送信済み」を記録する前に落ちる → 再起動後にもう一度送る（重複）
                raise SimulatedCrash()
            with self.conn:
                self.conn.execute("UPDATE outbox SET published_at = ? WHERE seq = ?", (self.clock(), seq))
            published += 1
        return published


# ---------------------------------------------------------------------------
# 演習6: 冪等なコンシューマ（inbox）
# ---------------------------------------------------------------------------


class IdempotentConsumer:
    def __init__(
        self,
        conn: sqlite3.Connection,
        fail_hook: Callable[[dict], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.conn = conn
        self.fail_hook = fail_hook
        self.clock = clock

    def handle(self, message: dict) -> bool:
        # 「処理済みの記録」と「処理の効果」を同じトランザクションで書く。どちらか一方だけが残ることはない
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO processed_messages (event_id, processed_at) VALUES (?, ?)",
                (message["event_id"], self.clock()),
            )
            if cur.rowcount == 0:
                return False  # 処理済み（重複）。効果は適用しない
            if message["event_type"] == "OrderPlaced":
                p = message["payload"]
                self.conn.execute(
                    "INSERT INTO customer_totals (customer, total, order_count) VALUES (?, ?, 1)"
                    " ON CONFLICT(customer) DO UPDATE SET"
                    " total = total + excluded.total, order_count = order_count + 1",
                    (p["customer"], p["amount"]),
                )
            if self.fail_hook is not None:
                self.fail_hook(message)  # 途中で落ちたら、上の 2 つの書き込みはまとめて取り消される
        return True

    def totals(self, customer: str) -> tuple[int, int] | None:
        row = self.conn.execute(
            "SELECT total, order_count FROM customer_totals WHERE customer = ?", (customer,)
        ).fetchone()
        return None if row is None else (row[0], row[1])
