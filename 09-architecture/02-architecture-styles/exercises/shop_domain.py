"""9.2 アーキテクチャスタイル — 演習: ヘキサゴナルアーキテクチャの注文アプリ（内側）

小さな注文アプリを、ヘキサゴナルアーキテクチャ（ポートとアダプタ）で作ります。

    shop_domain.py   … 六角形の「内側」: ドメインモデル・ポート（Protocol）・アプリケーションサービス
    shop_adapters.py … 六角形の「外側」: インメモリ／SQLite のリポジトリ、偽の決済代行など

依存の向きは「外 → 内」だけです。このファイルは sqlite3 や shop_adapters を import してはいけません
（test_shop_domain.py がそれを検査します。9.1 の適応度関数と同じ考え方です）。

演習（このファイル）:
    演習1（★☆☆）: ドメインモデル（OrderLine の検証、Order の生成・合計・状態遷移）
    演習3（★★☆）: アプリケーションサービス OrderService（冪等な注文受付・支払い・イベント発行）
演習2・4 は shop_adapters.py にあります。演習1 → 2 → 3 → 4 の順に進めてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.2
    python3 tools/check.py -v 9.2

金額はすべて「円」の整数で扱います（1.1 で学んだとおり、float は使いません）。
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
# 例外（ドメインの言葉で失敗を表す）— 実装済み
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """このアプリケーションの業務上のエラーの基底クラス。"""


class InvalidOrderError(DomainError):
    """注文の内容が業務ルールに反している。"""


class InvalidStateError(DomainError):
    """現在の状態では許されない操作をしようとした。"""


class PaymentDeclinedError(DomainError):
    """決済が拒否された（決済代行のポートが送出する）。"""


class OrderNotFoundError(DomainError):
    pass


class DuplicateOrderError(DomainError):
    """同じ order_id または request_id の注文がすでにある（リポジトリのポートが送出する）。"""


class ConcurrencyError(DomainError):
    """楽観的ロックの衝突: 読んだ後に、他の誰かが同じ注文を更新した。"""


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: ドメインモデル
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OrderLine:
    """注文明細（値オブジェクト）。不変で、不正な値では生成できない。

    - sku: 空文字列・空白だけの文字列は不可
    - quantity: 1〜MAX_QUANTITY
    - unit_price: 0 以上の整数（円）
    違反したら InvalidOrderError。
    """

    sku: str
    quantity: int
    unit_price: int

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: OrderLine の検証を実装してください")

    @property
    def subtotal(self) -> int:
        """quantity × unit_price。"""
        raise NotImplementedError("演習1: OrderLine.subtotal を実装してください")


class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PAYMENT_FAILED = "payment_failed"
    CANCELLED = "cancelled"


@dataclass
class Order:
    """注文（エンティティ）。order_id で識別され、状態が遷移する。

    状態遷移（これ以外は InvalidStateError）:

        PENDING_PAYMENT ──mark_paid──────────▶ PAID
        PENDING_PAYMENT ──mark_payment_failed─▶ PAYMENT_FAILED
        PENDING_PAYMENT ──cancel──────────────▶ CANCELLED
        PAYMENT_FAILED  ──cancel──────────────▶ CANCELLED

    version は楽観的ロックのための版番号で、リポジトリが管理する（生成時は 0）。
    """

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
        """新しい注文を「支払い待ち（PENDING_PAYMENT）」の状態で作る（ファクトリメソッド）。

        次の場合は InvalidOrderError:
        - customer_id が空
        - 明細が 0 行、または MAX_LINES 行を超える
        - 同じ SKU の明細が複数ある（数量をまとめるべき）
        - 合計金額が 0 円以下
        lines はタプルにして保持すること（外から渡されたリストを後で変更されても影響を受けないように）。
        """
        raise NotImplementedError("演習1: Order.place を実装してください")

    @property
    def total(self) -> int:
        """明細の小計の合計（円）。"""
        raise NotImplementedError("演習1: Order.total を実装してください")

    def mark_paid(self, payment_id: str) -> None:
        """支払い成功: PENDING_PAYMENT → PAID。payment_id を記録する。"""
        raise NotImplementedError("演習1: Order.mark_paid を実装してください")

    def mark_payment_failed(self, reason: str) -> None:
        """支払い失敗: PENDING_PAYMENT → PAYMENT_FAILED。failure_reason を記録する。"""
        raise NotImplementedError("演習1: Order.mark_payment_failed を実装してください")

    def cancel(self) -> None:
        """取り消し: PENDING_PAYMENT または PAYMENT_FAILED → CANCELLED。

        支払い済み（PAID）の注文は返金の業務フローが必要なので、ここでは取り消せない。
        """
        raise NotImplementedError("演習1: Order.cancel を実装してください")


@dataclass(frozen=True)
class OrderPlaced:
    """ドメインイベント: 注文が確定した（支払いが成功した）。"""

    order_id: str
    customer_id: str
    total: int
    occurred_at: datetime


# ---------------------------------------------------------------------------
# ポート（六角形の縁）— 実装済み
# 内側が「外の世界に求めること」を、内側の言葉でインターフェースとして定義する
# ---------------------------------------------------------------------------

class OrderRepository(Protocol):
    """注文の保存場所。詳しい契約は shop_adapters.py の InMemoryOrderRepository を参照。"""

    def add(self, order: Order) -> None: ...
    def save(self, order: Order) -> None: ...
    def get(self, order_id: str) -> Order | None: ...
    def find_by_request_id(self, request_id: str) -> Order | None: ...
    def list_by_customer(self, customer_id: str) -> list[Order]: ...


class ProductCatalog(Protocol):
    def unit_price(self, sku: str) -> int | None:
        """商品の単価（円）。存在しない商品なら None。"""
        ...


class PaymentGateway(Protocol):
    def charge(self, customer_id: str, amount: int, idempotency_key: str) -> str:
        """課金して決済 ID を返す。拒否されたら PaymentDeclinedError。

        同じ idempotency_key で再度呼ばれたら、二重に課金せず前回の決済 ID を返す。
        通信エラー（TimeoutError など）を送出することもある。
        """
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class EventPublisher(Protocol):
    def publish(self, event: object) -> None: ...


# ---------------------------------------------------------------------------
# 演習3（★★☆）: アプリケーションサービス（ユースケース）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlaceOrderCommand:
    """注文の入力。request_id はクライアントが生成する一意な値（再送の検出に使う）。

    items は (SKU, 数量) の組。価格はクライアントから受け取らない（改ざんを防ぐため）。
    """

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
    """注文のユースケース。ポートにだけ依存し、具体的なアダプタを知らない。"""

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
        """注文を受け付けて課金し、結果を返す。

        手順:
        1. find_by_request_id で同じ request_id の注文を探す。あれば「再送」なので:
           - その注文が PENDING_PAYMENT なら、手順 4 から処理を再開する（前回は課金の途中で失敗した）
           - それ以外なら、その注文の OrderSummary をそのまま返す（課金もイベントも繰り返さない）
        2. 各 SKU の単価を catalog から引いて OrderLine を作り、Order.place で注文を作る
           （ID は new_id()、日時は clock.now()）。存在しない SKU なら InvalidOrderError。
        3. 課金の前に orders.add で「支払い待ち」として保存する。
           add が DuplicateOrderError を送出したら（同じ request_id の同時リクエストに先を越された）、
           find_by_request_id で先に保存された注文を取り直し、手順 1 と同じ扱いで結果を返す。
        4. payments.charge(顧客 ID, 合計金額, idempotency_key=注文 ID) で課金する。
           - PaymentDeclinedError なら mark_payment_failed(エラーの文字列) → save して、その結果を返す
             （例外は送出しない。支払い失敗も「処理された結果」として返す）
           - それ以外の例外（TimeoutError など）はそのまま送出する（注文は PENDING_PAYMENT のまま残る）
        5. 成功したら mark_paid → save してから、OrderPlaced(注文 ID, 顧客 ID, 合計, clock.now()) を
           events.publish する。

        ポイント: 冪等キーに注文 ID を使うので、手順 4 を再実行しても二重課金にならない。
        """
        raise NotImplementedError("演習3: OrderService.place_order を実装してください")

    def cancel_order(self, order_id: str) -> OrderSummary:
        """注文を取り消す。存在しなければ OrderNotFoundError、状態が不正なら InvalidStateError。

        取り消した注文は save して、OrderSummary を返す。
        """
        raise NotImplementedError("演習3: OrderService.cancel_order を実装してください")
