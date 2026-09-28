"""9.2 アーキテクチャスタイル — 解答例: ヘキサゴナルアーキテクチャの注文アプリ（内側）

演習の仕様は exercises/shop_domain.py の docstring を参照してください。
このモジュールは「六角形の内側」です。sqlite3 も shop_adapters も import していないことに注目してください。
外の世界とのやり取りは、すべてこのファイルで定義したポート（Protocol）を通して行います。
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Protocol

MAX_LINES = 20
MAX_QUANTITY = 99


# ---------------------------------------------------------------------------
# 例外（ドメインの言葉で失敗を表す）
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """このアプリケーションの業務上のエラーの基底クラス。"""


class InvalidOrderError(DomainError):
    pass


class InvalidStateError(DomainError):
    pass


class PaymentDeclinedError(DomainError):
    pass


class OrderNotFoundError(DomainError):
    pass


class DuplicateOrderError(DomainError):
    pass


class ConcurrencyError(DomainError):
    pass


# ---------------------------------------------------------------------------
# 演習1: ドメインモデル
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderLine:
    sku: str
    quantity: int
    unit_price: int

    def __post_init__(self) -> None:
        # 値オブジェクトは「不正な状態では生まれてこない」ようにする
        if not self.sku or not self.sku.strip():
            raise InvalidOrderError("SKU が空です")
        if not 1 <= self.quantity <= MAX_QUANTITY:
            raise InvalidOrderError(f"数量は 1〜{MAX_QUANTITY}: {self.quantity}")
        if self.unit_price < 0:
            raise InvalidOrderError(f"単価が負です: {self.unit_price}")

    @property
    def subtotal(self) -> int:
        return self.quantity * self.unit_price


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    CANCELLED = "cancelled"


@dataclass
class Order:
    order_id: str
    customer_id: str
    request_id: str
    lines: tuple[OrderLine, ...]
    created_at: datetime
    status: OrderStatus = OrderStatus.PENDING_PAYMENT
    payment_id: str | None = None
    failure_reason: str | None = None
    version: int = 0

    @classmethod
    def place(
        cls,
        order_id: str,
        customer_id: str,
        request_id: str,
        lines: list[OrderLine] | tuple[OrderLine, ...],
        created_at: datetime,
    ) -> "Order":
        lines = tuple(lines)
        if not customer_id:
            raise InvalidOrderError("顧客 ID が空です")
        if not 1 <= len(lines) <= MAX_LINES:
            raise InvalidOrderError(f"明細は 1〜{MAX_LINES} 行: {len(lines)}")
        skus = [line.sku for line in lines]
        if len(set(skus)) != len(skus):
            raise InvalidOrderError("同じ SKU の明細が複数あります（数量をまとめてください）")
        order = cls(order_id, customer_id, request_id, lines, created_at)
        if order.total <= 0:
            raise InvalidOrderError("合計金額が 0 円の注文は受け付けません")
        return order

    @property
    def total(self) -> int:
        return sum(line.subtotal for line in self.lines)

    # 状態遷移はエンティティ自身が守る。外から status を直接書き換えさせない
    def _require(self, *allowed: OrderStatus) -> None:
        if self.status not in allowed:
            names = ", ".join(s.value for s in allowed)
            raise InvalidStateError(f"{self.status.value} の注文にはこの操作はできません（許可: {names}）")

    def mark_paid(self, payment_id: str) -> None:
        self._require(OrderStatus.PENDING_PAYMENT)
        self.status = OrderStatus.PAID
        self.payment_id = payment_id

    def mark_payment_failed(self, reason: str) -> None:
        self._require(OrderStatus.PENDING_PAYMENT)
        self.status = OrderStatus.PAYMENT_FAILED
        self.failure_reason = reason

    def cancel(self) -> None:
        self._require(OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_FAILED)
        self.status = OrderStatus.CANCELLED


@dataclass(frozen=True)
class OrderPlaced:
    """ドメインイベント: 注文が確定した（支払いが成功した）。"""

    order_id: str
    customer_id: str
    total: int
    occurred_at: datetime


# ---------------------------------------------------------------------------
# ポート（六角形の縁）: 内側が「外の世界に求めること」をインターフェースで表す
# ---------------------------------------------------------------------------

class OrderRepository(Protocol):
    def add(self, order: Order) -> None: ...
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Order | None: ...
    def find_by_request_id(self, request_id: str) -> Order | None: ...
    def list_by_customer(self, customer_id: str) -> list[Order]: ...


class ProductCatalog(Protocol):
    def unit_price(self, sku: str) -> int | None: ...


class PaymentGateway(Protocol):
    def charge(self, customer_id: str, amount: int, idempotency_key: str) -> str: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class EventPublisher(Protocol):
    def publish(self, event: object) -> None: ...


# ---------------------------------------------------------------------------
# 演習3: アプリケーションサービス（ユースケース）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlaceOrderCommand:
    request_id: str
    customer_id: str
    items: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class OrderSummary:
    """アプリケーション層の外に返す読み取り専用の結果（DTO）。ドメインオブジェクトそのものは渡さない。"""

    order_id: str
    status: str
    total: int
    payment_id: str | None
    failure_reason: str | None

    @classmethod
    def of(cls, order: Order) -> "OrderSummary":
        return cls(order.order_id, order.status.value, order.total, order.payment_id, order.failure_reason)


class OrderService:
    def __init__(
        self,
        orders: OrderRepository,
        catalog: ProductCatalog,
        payments: PaymentGateway,
        clock: Clock,
        events: EventPublisher,
        new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    ) -> None:
        self._orders = orders
        self._catalog = catalog
        self._payments = payments
        self._clock = clock
        self._events = events
        self._new_id = new_id

    def place_order(self, cmd: PlaceOrderCommand) -> OrderSummary:
        # 1. 同じリクエストの再送なら、前回の結果を返す（途中で止まっていたら続きから再開する）
        existing = self._orders.find_by_request_id(cmd.request_id)
        if existing is not None:
            return self._resume(existing)

        # 2. 価格はクライアントから受け取らず、カタログ（ポート）から引く
        lines = []
        for sku, quantity in cmd.items:
            price = self._catalog.unit_price(sku)
            if price is None:
                raise InvalidOrderError(f"存在しない商品です: {sku}")
            lines.append(OrderLine(sku, quantity, price))
        order = Order.place(self._new_id(), cmd.customer_id, cmd.request_id, lines, self._clock.now())

        # 3. 課金の前に「支払い待ち」として記録する。課金の途中で落ちても痕跡が残り、再開できる
        try:
            self._orders.add(order)
        except DuplicateOrderError:
            # 同じ request_id の同時リクエストに先を越された。先に保存された方の結果に合流する
            winner = self._orders.find_by_request_id(cmd.request_id)
            if winner is None:
                raise
            return self._resume(winner)
        return self._complete_payment(order)

    def _resume(self, order: Order) -> OrderSummary:
        if order.status is OrderStatus.PENDING_PAYMENT:
            return self._complete_payment(order)
        return OrderSummary.of(order)

    def _complete_payment(self, order: Order) -> OrderSummary:
        # 4. 課金。冪等キーに注文 ID を使うので、再開して 2 回呼んでも決済代行側で二重課金にならない
        try:
            payment_id = self._payments.charge(order.customer_id, order.total, order.order_id)
        except PaymentDeclinedError as exc:
            order.mark_payment_failed(str(exc))
            self._orders.save(order)
            return OrderSummary.of(order)
        order.mark_paid(payment_id)
        # save は楽観的ロックで守られている。同時に同じ注文を完了させようとした側は ConcurrencyError になる
        self._orders.save(order)
        # 5. 確定を保存できてからイベントを出す（本番では outbox パターンで保存と発行を原子的にする）
        self._events.publish(OrderPlaced(order.order_id, order.customer_id, order.total, self._clock.now()))
        return OrderSummary.of(order)

    def cancel_order(self, order_id: str) -> OrderSummary:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        order.cancel()
        self._orders.save(order)
        return OrderSummary.of(order)
