"""9.2 アーキテクチャスタイル — 解答例: ヘキサゴナルアーキテクチャの注文アプリ（外側のアダプタ）

演習の仕様は exercises/shop_adapters.py の docstring を参照してください。
アダプタは内側（shop_domain）に依存しますが、内側はアダプタを知りません（依存は外から内へ）。
"""
from __future__ import annotations

import copy
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from shop_domain import (
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
# 演習2: インメモリのアダプタ
# ---------------------------------------------------------------------------

class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[str, Order] = {}
        self._by_request: dict[str, str] = {}

    def add(self, order: Order) -> None:
        if order.order_id in self._orders or order.request_id in self._by_request:
            raise DuplicateOrderError(order.order_id)
        order.version = 1
        # 保存するのは「コピー」。呼び出し側のオブジェクトと共有すると、save しなくても
        # 状態が変わってしまい、本物の DB と違う振る舞いになる（契約テストで検出される典型的なバグ）
        self._orders[order.order_id] = copy.deepcopy(order)
        self._by_request[order.request_id] = order.order_id

    def save(self, order: Order) -> None:
        stored = self._orders.get(order.order_id)
        if stored is None:
            raise OrderNotFoundError(order.order_id)
        if stored.version != order.version:
            raise ConcurrencyError(
                f"{order.order_id}: 保存済みの版 {stored.version} と、手元の版 {order.version} が一致しません"
            )
        order.version += 1
        self._orders[order.order_id] = copy.deepcopy(order)

    def get(self, order_id: str) -> Order | None:
        stored = self._orders.get(order_id)
        return copy.deepcopy(stored) if stored is not None else None

    def find_by_request_id(self, request_id: str) -> Order | None:
        order_id = self._by_request.get(request_id)
        return self.get(order_id) if order_id is not None else None

    def list_by_customer(self, customer_id: str) -> list[Order]:
        found = [o for o in self._orders.values() if o.customer_id == customer_id]
        return [copy.deepcopy(o) for o in sorted(found, key=lambda o: (o.created_at, o.order_id))]


@dataclass
class Charge:
    idempotency_key: str
    customer_id: str
    amount: int
    payment_id: str


@dataclass
class FakePaymentGateway:
    declined_customers: set[str] = field(default_factory=set)
    limit: int | None = None
    fail_after_charge_once: bool = False
    charges: list[Charge] = field(default_factory=list)
    calls: int = 0

    def charge(self, customer_id: str, amount: int, idempotency_key: str) -> str:
        self.calls += 1
        for c in self.charges:
            if c.idempotency_key == idempotency_key:
                if c.amount != amount or c.customer_id != customer_id:
                    raise ValueError(f"冪等キー {idempotency_key} が別の内容で再利用されました")
                return c.payment_id  # 同じキーの再送: 課金せずに前回の結果を返す
        if customer_id in self.declined_customers:
            raise PaymentDeclinedError("カードが利用できません")
        if self.limit is not None and amount > self.limit:
            raise PaymentDeclinedError(f"利用限度額（{self.limit} 円）を超えています")
        payment = Charge(idempotency_key, customer_id, amount, f"pay_{len(self.charges) + 1:04d}")
        self.charges.append(payment)
        if self.fail_after_charge_once:
            # 「決済代行側では課金されたのに、応答がタイムアウトで届かなかった」状況を再現する
            self.fail_after_charge_once = False
            raise TimeoutError("決済代行からの応答がタイムアウトしました")
        return payment.payment_id


# ---------------------------------------------------------------------------
# 演習4: SQLite のアダプタ（楽観的ロック付き）
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
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._conn.executescript(SCHEMA)

    def add(self, order: Order) -> None:
        try:
            # with conn: は成功すれば COMMIT、例外なら ROLLBACK する（注文と明細を原子的に保存）
            with self._conn:
                self._conn.execute(
                    "INSERT INTO orders (order_id, request_id, customer_id, status, payment_id,"
                    " failure_reason, created_at, version) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                    (order.order_id, order.request_id, order.customer_id, order.status.value,
                     order.payment_id, order.failure_reason, order.created_at.isoformat()),
                )
                self._conn.executemany(
                    "INSERT INTO order_lines (order_id, line_no, sku, quantity, unit_price)"
                    " VALUES (?, ?, ?, ?, ?)",
                    [(order.order_id, i, ln.sku, ln.quantity, ln.unit_price) for i, ln in enumerate(order.lines)],
                )
        except sqlite3.IntegrityError as exc:
            # 主キー（order_id）や UNIQUE（request_id）の違反を、ドメインの言葉に翻訳する
            raise DuplicateOrderError(order.order_id) from exc
        order.version = 1

    def save(self, order: Order) -> None:
        with self._conn:
            # 楽観的ロック: 「読んだときの版」のままなら更新し、版を 1 進める。
            # 誰かが先に更新していれば WHERE に一致せず、rowcount が 0 になる
            cur = self._conn.execute(
                "UPDATE orders SET status = ?, payment_id = ?, failure_reason = ?, version = version + 1"
                " WHERE order_id = ? AND version = ?",
                (order.status.value, order.payment_id, order.failure_reason, order.order_id, order.version),
            )
        if cur.rowcount == 0:
            exists = self._conn.execute("SELECT 1 FROM orders WHERE order_id = ?", (order.order_id,)).fetchone()
            if exists is None:
                raise OrderNotFoundError(order.order_id)
            raise ConcurrencyError(f"{order.order_id}: 他の更新と衝突しました（版 {order.version}）")
        order.version += 1

    def _load(self, row: tuple) -> Order:
        order_id, request_id, customer_id, status, payment_id, failure_reason, created_at, version = row
        lines = tuple(
            OrderLine(sku, quantity, unit_price)
            for sku, quantity, unit_price in self._conn.execute(
                "SELECT sku, quantity, unit_price FROM order_lines WHERE order_id = ? ORDER BY line_no",
                (order_id,),
            )
        )
        return Order(
            order_id=order_id,
            customer_id=customer_id,
            request_id=request_id,
            lines=lines,
            created_at=datetime.fromisoformat(created_at),
            status=OrderStatus(status),
            payment_id=payment_id,
            failure_reason=failure_reason,
            version=version,
        )

    _COLUMNS = "order_id, request_id, customer_id, status, payment_id, failure_reason, created_at, version"

    def get(self, order_id: str) -> Order | None:
        row = self._conn.execute(f"SELECT {self._COLUMNS} FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        return self._load(row) if row else None

    def find_by_request_id(self, request_id: str) -> Order | None:
        row = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM orders WHERE request_id = ?", (request_id,)
        ).fetchone()
        return self._load(row) if row else None

    def list_by_customer(self, customer_id: str) -> list[Order]:
        rows = self._conn.execute(
            f"SELECT {self._COLUMNS} FROM orders WHERE customer_id = ?", (customer_id,)
        ).fetchall()
        orders = [self._load(r) for r in rows]
        # 並べ替えは datetime で行う（ISO 文字列の辞書順は、タイムゾーンが混在すると時刻順にならない）
        return sorted(orders, key=lambda o: (o.created_at, o.order_id))
