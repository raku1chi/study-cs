"""9.2 アーキテクチャスタイル — 演習: ヘキサゴナルアーキテクチャの注文アプリ（外側のアダプタ）

六角形の「外側」です。アダプタは内側（shop_domain）のポートを実装します。
依存は外 → 内の一方向なので、このファイルは shop_domain を import してよく、その逆はだめです。

演習（このファイル）:
    演習2（★★☆）: InMemoryOrderRepository と FakePaymentGateway.charge
    演習4（★★★）: SqliteOrderRepository（楽観的ロック付き）

2 つのリポジトリには、test_shop_adapters.py の **同じ契約テスト（contract test）** が実行されます。
「テスト用のインメモリ実装は通るのに、本物の DB では動かない」（またはその逆）という事故を防ぐための
仕組みです。

リポジトリの契約（OrderRepository ポートの仕様）:
    add(order)
        新しい注文を保存する。同じ order_id、または同じ request_id の注文がすでにあれば
        DuplicateOrderError（何も保存しない）。成功したら order.version を 1 にする。
    save(order)
        既存の注文の状態（status, payment_id, failure_reason）を更新する。明細は変わらない前提。
        - 注文が存在しなければ OrderNotFoundError
        - 保存済みの版と order.version が違えば ConcurrencyError（楽観的ロック。何も更新しない）
        - 成功したら保存済みの版と order.version を 1 増やす
    get(order_id) / find_by_request_id(request_id)
        保存済みの注文の **独立したコピー** を返す（なければ None）。返したオブジェクトを呼び出し側が
        変更しても、save するまで保存済みの状態は変わらないこと。add に渡したオブジェクトを後から
        変更した場合も同様。
    list_by_customer(customer_id)
        その顧客の注文を (created_at, order_id) の昇順で返す（コピー）。
"""
from __future__ import annotations

import copy  # noqa: F401  演習2で使えます
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from shop_domain import (  # noqa: F401  演習で使います
    ConcurrencyError,
    DuplicateOrderError,
    Order,
    OrderLine,
    OrderNotFoundError,
    OrderStatus,
    PaymentDeclinedError,
)


# ---------------------------------------------------------------------------
# 最初から実装済みの小さなアダプタ
# ---------------------------------------------------------------------------

class FixedClock:
    """テスト用の時計。advance() で時間を進める。"""

    def __init__(self, start: datetime) -> None:
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class InMemoryCatalog:
    def __init__(self, prices: dict[str, int]) -> None:
        self._prices = dict(prices)

    def unit_price(self, sku: str) -> int | None:
        return self._prices.get(sku)


class InMemoryEventPublisher:
    def __init__(self) -> None:
        self.events: list[object] = []

    def publish(self, event: object) -> None:
        self.events.append(event)


class SequentialIds:
    """"ord_0001", "ord_0002", ... を順に返す ID 生成器（テストを決定的にするため）。"""

    def __init__(self, prefix: str = "ord_") -> None:
        self._prefix = prefix
        self._n = 0

    def __call__(self) -> str:
        self._n += 1
        return f"{self._prefix}{self._n:04d}"


# ---------------------------------------------------------------------------
# 演習2（★★☆）: インメモリのアダプタ
# ---------------------------------------------------------------------------

class InMemoryOrderRepository:
    """辞書に注文を保存するリポジトリ。契約はモジュールの docstring を参照。

    ヒント: 保存するときも返すときも copy.deepcopy でコピーする。
    オブジェクトを共有すると、save しなくても保存済みの状態が変わってしまい、
    本物の DB とは違う振る舞いになる（契約テストで検出される典型的なバグ）。
    """

    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._by_request: dict[str, str] = {}

    def add(self, order: Order) -> None:
        raise NotImplementedError("演習2: InMemoryOrderRepository.add を実装してください")

    def save(self, order: Order) -> None:
        raise NotImplementedError("演習2: InMemoryOrderRepository.save を実装してください")

    def get(self, order_id: str) -> Order | None:
        raise NotImplementedError("演習2: InMemoryOrderRepository.get を実装してください")

    def find_by_request_id(self, request_id: str) -> Order | None:
        raise NotImplementedError("演習2: InMemoryOrderRepository.find_by_request_id を実装してください")

    def list_by_customer(self, customer_id: str) -> list[Order]:
        raise NotImplementedError("演習2: InMemoryOrderRepository.list_by_customer を実装してください")


@dataclass
class Charge:
    idempotency_key: str
    customer_id: str
    amount: int
    payment_id: str


@dataclass
class FakePaymentGateway:
    """テスト用の偽の決済代行（PaymentGateway ポートの実装）。

    - declined_customers に含まれる顧客、または limit を超える金額は PaymentDeclinedError
    - 成功した課金は charges に Charge として記録し、決済 ID "pay_0001", "pay_0002", ... を返す
      （番号は charges に記録された順）
    - 同じ idempotency_key の再送は、新たに課金せず、記録済みの決済 ID を返す。
      ただし顧客 ID や金額が前回と違えば ValueError（冪等キーの誤用）
    - fail_after_charge_once が True なら、最初の 1 回だけ「課金は記録したのに TimeoutError を送出する」
      （決済代行側では課金されたのに、応答が届かなかった状況の再現）。送出したら False に戻す
    - calls は charge が呼ばれた回数（再送も数える）
    """

    declined_customers: set[str] = field(default_factory=set)
    limit: int | None = None
    fail_after_charge_once: bool = False
    charges: list[Charge] = field(default_factory=list)
    calls: int = 0

    def charge(self, customer_id: str, amount: int, idempotency_key: str) -> str:
        raise NotImplementedError("演習2: FakePaymentGateway.charge を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★★）: SQLite のアダプタ（楽観的ロック付き）
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    order_id       TEXT PRIMARY KEY,
    request_id     TEXT NOT NULL UNIQUE,
    customer_id    TEXT NOT NULL,
    status         TEXT NOT NULL,
    payment_id     TEXT,
    failure_reason TEXT,
    created_at     TEXT NOT NULL,
    version        INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS order_lines (
    order_id   TEXT NOT NULL REFERENCES orders(order_id),
    line_no    INTEGER NOT NULL,
    sku        TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id, created_at, order_id);
"""


class SqliteOrderRepository:
    """SQLite に注文を保存するリポジトリ。契約はモジュールの docstring を参照（インメモリ版と同じ）。

    ヒント:
    - add: orders と order_lines への INSERT を 1 つのトランザクションで行う（`with self._conn:` は
      成功すれば COMMIT、例外なら ROLLBACK する）。主キーや UNIQUE の違反は sqlite3.IntegrityError に
      なるので、DuplicateOrderError に翻訳する（ドメインに sqlite3 の例外を漏らさない）。
    - save: 楽観的ロックは 1 文の UPDATE で書ける:
          UPDATE orders SET ..., version = version + 1 WHERE order_id = ? AND version = ?
      更新された行数（cursor.rowcount）が 0 なら、存在しないのか版が違うのかを調べて例外を選ぶ。
    - created_at は datetime.isoformat() で文字列にして保存し、datetime.fromisoformat() で戻す
      （タイムゾーンの情報も保たれる）。status は OrderStatus(文字列) で戻せる。
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(SCHEMA)

    def add(self, order: Order) -> None:
        raise NotImplementedError("演習4: SqliteOrderRepository.add を実装してください")

    def save(self, order: Order) -> None:
        raise NotImplementedError("演習4: SqliteOrderRepository.save を実装してください")

    def get(self, order_id: str) -> Order | None:
        raise NotImplementedError("演習4: SqliteOrderRepository.get を実装してください")

    def find_by_request_id(self, request_id: str) -> Order | None:
        raise NotImplementedError("演習4: SqliteOrderRepository.find_by_request_id を実装してください")

    def list_by_customer(self, customer_id: str) -> list[Order]:
        raise NotImplementedError("演習4: SqliteOrderRepository.list_by_customer を実装してください")
