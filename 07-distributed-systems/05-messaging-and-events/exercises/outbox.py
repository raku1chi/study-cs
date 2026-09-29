"""7.5 メッセージングとイベント駆動 — 演習: Transactional Outbox と冪等なコンシューマ（sqlite3）

「注文をデータベースに保存し、注文イベントをブローカーに送る」という処理を素朴に書くと、
2 つの別々のシステムへの書き込み（二重書き込み）になり、間で落ちるとイベントが失われたり、
存在しない注文のイベントが送られたりします。Transactional Outbox パターンは、イベントを
**業務データと同じデータベースの outbox 表に、同じトランザクションで書き**、別のリレーが後から送ります。

    演習4: 注文と outbox の行を 1 つのトランザクションで書く（place_order）
    演習5: outbox の未送信の行をブローカーに送り、送信済みにするリレー（OutboxRelay）
    演習6: 同じイベントを何度受け取っても 1 回分の効果しか生まない、冪等なコンシューマ（IdempotentConsumer）

リレーは「送信した直後、送信済みを記録する前」に落ちうるので、配送は at-least-once（重複がありうる）です。
だからコンシューマ側で、イベント ID による重複排除を **効果と同じトランザクションで** 行います。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.5
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_outbox

sqlite3 のトランザクション: `with conn:` のブロックは、正常に抜ければコミット、例外で抜ければロールバックします。
"""
from __future__ import annotations

import json  # noqa: F401  演習4・5で使います
import sqlite3
import time
import uuid  # noqa: F401  演習4で使います（uuid.uuid4）
from typing import Callable

# ---------------------------------------------------------------------------
# 実装済み: スキーマ、偽のブローカー、比較用の悪い例
# ---------------------------------------------------------------------------

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
    """注文サービスのデータベース（orders 表と outbox 表）を作る。"""
    conn.executescript(PRODUCER_SCHEMA)


def init_consumer_db(conn: sqlite3.Connection) -> None:
    """請求サービスのデータベース（processed_messages 表と customer_totals 表）を作る。"""
    conn.executescript(CONSUMER_SCHEMA)


class SimulatedCrash(BaseException):
    """プロセスが落ちたことを表す（テスト用）。except Exception では捕まらない。"""


class FakeBroker:
    """メッセージを messages に溜めるだけの偽のブローカー。fail_next(n) で、次の n 回の publish を失敗させる。"""

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
# 演習4（★☆☆）: 注文とイベントを 1 つのトランザクションで書く
# ---------------------------------------------------------------------------


def place_order(
    conn: sqlite3.Connection,
    order_id: str,
    customer: str,
    amount: int,
    event_id: str | None = None,
) -> str:
    """注文を保存し、同じトランザクションで outbox に OrderPlaced イベントを書いて、イベント ID を返す。

    - event_id が None なら str(uuid.uuid4()) を使う。
    - orders に (order_id, customer, amount) を、outbox に
      (event_id, "OrderPlaced", aggregate_id=order_id, payload=JSON 文字列) を INSERT する。
      payload は {"order_id": ..., "customer": ..., "amount": ...} を
      json.dumps(..., ensure_ascii=False, sort_keys=True) した文字列。published_at は NULL のまま。
    - どちらかの INSERT が失敗したら（注文 ID の重複、金額が 0 以下、イベント ID の重複など）、
      **両方とも残らない** こと。sqlite3.IntegrityError はそのまま呼び出し元に伝える。
    """
    raise NotImplementedError("演習4: place_order を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: リレー（outbox からブローカーへ）
# ---------------------------------------------------------------------------


class OutboxRelay:
    """outbox の未送信の行をブローカーに送る（ポーリング方式のリレー）。

    - pending(): published_at が NULL の行の数。
    - run_once(batch_size=100) -> 送信済みにした件数:
        1. published_at が NULL の行を seq の昇順に最大 batch_size 件読む。
        2. 1 行ずつ、メッセージ {"event_id", "event_type", "aggregate_id", "payload": JSON を dict に戻したもの}
           を broker.publish する。
           - ConnectionError が出たら、**そこで止めて** それまでの件数を返す（後ろの行を先に送ると順序が崩れる）。
        3. 送信できたら、crash_after_publish が与えられていて crash_after_publish(event_id) が True なら
           SimulatedCrash を送出する（送信済みの記録の前に落ちる状況の模擬）。
        4. その行の published_at を clock() の値で UPDATE してコミットする。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        broker: FakeBroker,
        crash_after_publish: Callable[[str], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        raise NotImplementedError("演習5: OutboxRelay.__init__ を実装してください")

    def pending(self) -> int:
        raise NotImplementedError("演習5: OutboxRelay.pending を実装してください")

    def run_once(self, batch_size: int = 100) -> int:
        raise NotImplementedError("演習5: OutboxRelay.run_once を実装してください")


# ---------------------------------------------------------------------------
# 演習6（★★☆）: 冪等なコンシューマ（inbox）
# ---------------------------------------------------------------------------


class IdempotentConsumer:
    """請求サービス側のコンシューマ。顧客ごとの合計金額と注文数（customer_totals）を集計する。

    handle(message) -> bool:
        **1 つのトランザクションの中で** 次を行う。
        1. processed_messages に (event_id, clock()) を INSERT する。すでにあれば（重複）、何もせず False を返す。
           ヒント: `INSERT OR IGNORE ...` の後に cursor.rowcount が 0 なら重複。
        2. event_type が "OrderPlaced" なら、customer_totals の payload["customer"] の行に
           total += payload["amount"]、order_count += 1 を反映する（行がなければ作る）。それ以外の種類は記録だけ。
           ヒント: `INSERT ... ON CONFLICT(customer) DO UPDATE SET total = total + excluded.total, ...`
        3. fail_hook が与えられていれば fail_hook(message) を呼ぶ（例外が出たら、1 と 2 はまとめて取り消され、
           例外はそのまま呼び出し元に伝わる。処理の途中で落ちた状況の模擬）。
        4. True を返す。
    totals(customer) -> (total, order_count) | None: 集計結果。

    なぜ同じトランザクションなのか: 「処理済み」だけ記録して効果を書く前に落ちれば取りこぼし、
    効果だけ書いて「処理済み」を記録する前に落ちれば、再配送で二重に処理してしまう。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        fail_hook: Callable[[dict], None] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        raise NotImplementedError("演習6: IdempotentConsumer.__init__ を実装してください")

    def handle(self, message: dict) -> bool:
        raise NotImplementedError("演習6: IdempotentConsumer.handle を実装してください")

    def totals(self, customer: str) -> tuple[int, int] | None:
        raise NotImplementedError("演習6: IdempotentConsumer.totals を実装してください")
