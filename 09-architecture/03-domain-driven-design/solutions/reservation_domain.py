"""9.3 ドメイン駆動設計とモジュール分割 — 解答例: レストラン予約のドメインモデル

演習の仕様は exercises/reservation_domain.py の docstring を参照してください。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


# ---------------------------------------------------------------------------
# 例外
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """予約ドメインの業務エラーの基底クラス。"""


class InvalidValueError(DomainError, ValueError):
    """値オブジェクトに不正な値を渡した。"""


class CapacityError(DomainError):
    pass


class DoubleBookingError(DomainError):
    pass


class BookingWindowError(DomainError):
    pass


class InvalidTransitionError(DomainError):
    pass


class ReservationNotFoundError(DomainError):
    pass


class DuplicateReservationError(DomainError):
    pass


def _is_int(value: object) -> bool:
    # bool は int のサブクラスなので、True が 1 人として通らないように除外する
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# 演習1: 値オブジェクト
# ---------------------------------------------------------------------------

MAX_PARTY = 20


@dataclass(frozen=True)
class PartySize:
    value: int

    def __post_init__(self) -> None:
        if not _is_int(self.value) or not 1 <= self.value <= MAX_PARTY:
            raise InvalidValueError(f"人数は 1〜{MAX_PARTY} の整数です: {self.value!r}")


@dataclass(frozen=True)
class TimeSlot:
    start: datetime
    minutes: int

    def __post_init__(self) -> None:
        if not isinstance(self.start, datetime) or self.start.utcoffset() is None:
            raise InvalidValueError("開始日時はタイムゾーン付きの datetime で指定してください")
        if self.start.minute % 15 or self.start.second or self.start.microsecond:
            raise InvalidValueError(f"開始時刻は 15 分単位です: {self.start.time()}")
        if not _is_int(self.minutes) or not 30 <= self.minutes <= 240 or self.minutes % 15:
            raise InvalidValueError(f"所要時間は 30〜240 分の 15 分単位です: {self.minutes!r}")

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.minutes)

    def overlaps(self, other: "TimeSlot") -> bool:
        # 半開区間 [start, end) どうしの重なり。19:30 に終わる枠と 19:30 に始まる枠は重ならない
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class Money:
    amount: int
    currency: str = "JPY"

    def __post_init__(self) -> None:
        if not _is_int(self.amount) or self.amount < 0:
            raise InvalidValueError(f"金額は 0 以上の整数です: {self.amount!r}")
        if not (isinstance(self.currency, str) and len(self.currency) == 3
                and self.currency.isascii() and self.currency.isupper()):
            raise InvalidValueError(f"通貨は ISO 4217 の 3 文字の大文字コードです: {self.currency!r}")

    def __add__(self, other: "Money") -> "Money":
        if not isinstance(other, Money):
            return NotImplemented
        if other.currency != self.currency:
            raise InvalidValueError(f"通貨が異なる金額は足せません: {self.currency} と {other.currency}")
        return Money(self.amount + other.amount, self.currency)

    def times(self, n: int) -> "Money":
        if not _is_int(n) or n < 0:
            raise InvalidValueError(f"倍数は 0 以上の整数です: {n!r}")
        return Money(self.amount * n, self.currency)

    def percent(self, p: int) -> "Money":
        if not _is_int(p) or not 0 <= p <= 100:
            raise InvalidValueError(f"割合は 0〜100 の整数です: {p!r}")
        # 端数は切り捨て（顧客に不利にならない側）。端数処理は業務ルールとして明文化しておく
        return Money(self.amount * p // 100, self.currency)


@dataclass(frozen=True)
class CancellationPolicy:
    tiers: tuple[tuple[timedelta, int], ...]

    def __post_init__(self) -> None:
        if not self.tiers:
            raise InvalidValueError("キャンセル規定が空です")
        prev_lead: timedelta | None = None
        prev_pct = -1
        for lead, pct in self.tiers:
            if lead < timedelta(0) or not _is_int(pct) or not 0 <= pct <= 100:
                raise InvalidValueError(f"不正な段階です: {lead}, {pct}%")
            if prev_lead is not None and lead >= prev_lead:
                raise InvalidValueError("段階は「何時間前か」の大きい順（狭義単調減少）に並べてください")
            if pct < prev_pct:
                raise InvalidValueError("直前になるほど料率が下がる規定は不正です")
            prev_lead, prev_pct = lead, pct
        if self.tiers[-1][0] != timedelta(0):
            raise InvalidValueError("最後の段階は 0 時間前（直前・開始後）を含める必要があります")

    def fee_percent(self, lead_time: timedelta) -> int:
        for lead, pct in self.tiers:
            if lead_time >= lead:
                return pct
        return self.tiers[-1][1]  # 開始後（lead_time が負）は最後の段階

    def fee(self, base: Money, lead_time: timedelta) -> Money:
        return base.percent(self.fee_percent(lead_time))


# 既定のキャンセル規定: 24 時間以上前は無料、3 時間以上前は 50%、それ以降（開始後を含む）は 100%
DEFAULT_TIERS: tuple[tuple[timedelta, int], ...] = (
    (timedelta(hours=24), 0),
    (timedelta(hours=3), 50),
    (timedelta(0), 100),
)


def default_policy() -> CancellationPolicy:
    return CancellationPolicy(DEFAULT_TIERS)


@dataclass(frozen=True)
class Table:
    table_id: str
    min_party: int
    max_party: int

    def accepts(self, party: PartySize) -> bool:
        return self.min_party <= party.value <= self.max_party


# ---------------------------------------------------------------------------
# エンティティとドメインイベント
# ---------------------------------------------------------------------------

class ReservationStatus(Enum):
    BOOKED = "booked"
    SEATED = "seated"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


ACTIVE_STATUSES = frozenset({ReservationStatus.BOOKED, ReservationStatus.SEATED})


@dataclass
class Reservation:
    reservation_id: str
    customer_id: str
    party: PartySize
    slot: TimeSlot
    course_price: Money
    status: ReservationStatus = ReservationStatus.BOOKED
    fee: Money | None = None


@dataclass(frozen=True)
class ReservationBooked:
    reservation_id: str
    table_id: str
    slot: TimeSlot
    party: PartySize


@dataclass(frozen=True)
class ReservationRescheduled:
    reservation_id: str
    table_id: str
    old_slot: TimeSlot
    new_slot: TimeSlot


@dataclass(frozen=True)
class ReservationCancelled:
    reservation_id: str
    table_id: str
    fee: Money


@dataclass(frozen=True)
class GuestsSeated:
    reservation_id: str
    table_id: str
    at: datetime


@dataclass(frozen=True)
class ReservationCompleted:
    reservation_id: str
    table_id: str


@dataclass(frozen=True)
class ReservationMarkedNoShow:
    reservation_id: str
    table_id: str
    fee: Money


# ---------------------------------------------------------------------------
# 演習2: 集約ルート
# ---------------------------------------------------------------------------

class TableSchedule:
    """1 つのテーブルの 1 日分の予約台帳（集約ルート）。

    「同じテーブルで時間帯が重なる有効な予約は 1 つまで」という不変条件は、同じテーブル・同じ日の
    予約どうしにまたがる。だから整合性の境界（集約）は予約 1 件ではなく、この台帳になる。
    """

    SEAT_EARLY = timedelta(minutes=15)
    NO_SHOW_GRACE = timedelta(minutes=15)

    def __init__(self, table: Table, day: date, policy: CancellationPolicy | None = None) -> None:
        self.table = table
        self.day = day
        self.policy = policy if policy is not None else default_policy()
        self._reservations: dict[str, Reservation] = {}
        self._events: list[object] = []

    # --- 読み取り（内部のエンティティは渡さず、コピーを返す） -------------------

    def reservation(self, reservation_id: str) -> Reservation:
        return copy.deepcopy(self._get(reservation_id))

    def reservations(self) -> list[Reservation]:
        items = sorted(self._reservations.values(), key=lambda r: (r.slot.start, r.reservation_id))
        return [copy.deepcopy(r) for r in items]

    def pull_events(self) -> list[object]:
        events, self._events = self._events, []
        return events

    # --- コマンド ---------------------------------------------------------------

    def book(self, reservation_id: str, customer_id: str, party: PartySize, slot: TimeSlot,
             course_price: Money, now: datetime) -> Reservation:
        if reservation_id in self._reservations:
            raise DuplicateReservationError(reservation_id)
        self._check_window(slot, now)
        if not self.table.accepts(party):
            raise CapacityError(
                f"テーブル {self.table.table_id} は {self.table.min_party}〜{self.table.max_party} 名用です"
                f"（{party.value} 名）"
            )
        self._check_no_overlap(slot, exclude=None)
        r = Reservation(reservation_id, customer_id, party, slot, course_price)
        self._reservations[reservation_id] = r
        self._events.append(ReservationBooked(reservation_id, self.table.table_id, slot, party))
        return copy.deepcopy(r)

    def reschedule(self, reservation_id: str, new_slot: TimeSlot, now: datetime) -> None:
        r = self._get(reservation_id)
        self._require(r, ReservationStatus.BOOKED)
        self._check_window(new_slot, now)
        self._check_no_overlap(new_slot, exclude=reservation_id)  # 自分自身とは重なってよい
        old = r.slot
        r.slot = new_slot
        self._events.append(ReservationRescheduled(reservation_id, self.table.table_id, old, new_slot))

    def cancel(self, reservation_id: str, now: datetime) -> Money:
        r = self._get(reservation_id)
        self._require(r, ReservationStatus.BOOKED)
        if now >= r.slot.start:
            raise InvalidTransitionError("開始時刻を過ぎた予約はキャンセルできません（無断キャンセルとして扱う）")
        fee = self.policy.fee(self._base(r), r.slot.start - now)
        r.status = ReservationStatus.CANCELLED
        r.fee = fee
        self._events.append(ReservationCancelled(reservation_id, self.table.table_id, fee))
        return fee

    def seat(self, reservation_id: str, now: datetime) -> None:
        r = self._get(reservation_id)
        self._require(r, ReservationStatus.BOOKED)
        if not r.slot.start - self.SEAT_EARLY <= now < r.slot.end:
            raise InvalidTransitionError("着席できるのは開始 15 分前から終了時刻までです")
        r.status = ReservationStatus.SEATED
        self._events.append(GuestsSeated(reservation_id, self.table.table_id, now))

    def complete(self, reservation_id: str) -> None:
        r = self._get(reservation_id)
        self._require(r, ReservationStatus.SEATED)
        r.status = ReservationStatus.COMPLETED
        self._events.append(ReservationCompleted(reservation_id, self.table.table_id))

    def mark_no_show(self, reservation_id: str, now: datetime) -> Money:
        r = self._get(reservation_id)
        self._require(r, ReservationStatus.BOOKED)
        if now < r.slot.start + self.NO_SHOW_GRACE:
            raise InvalidTransitionError("無断キャンセルと判定できるのは開始 15 分後からです")
        fee = self._base(r).percent(100)
        r.status = ReservationStatus.NO_SHOW
        r.fee = fee
        self._events.append(ReservationMarkedNoShow(reservation_id, self.table.table_id, fee))
        return fee

    # --- 内部の検査 -------------------------------------------------------------

    def _get(self, reservation_id: str) -> Reservation:
        try:
            return self._reservations[reservation_id]
        except KeyError:
            raise ReservationNotFoundError(reservation_id) from None

    @staticmethod
    def _require(r: Reservation, status: ReservationStatus) -> None:
        if r.status is not status:
            raise InvalidTransitionError(f"{r.reservation_id} は {r.status.value} なので、この操作はできません")

    def _check_window(self, slot: TimeSlot, now: datetime) -> None:
        if slot.start.date() != self.day:
            raise BookingWindowError(f"この台帳は {self.day} のものです（{slot.start.date()} は別の台帳）")
        if slot.start <= now:
            raise BookingWindowError("過去の時刻には予約できません")

    def _check_no_overlap(self, slot: TimeSlot, exclude: str | None) -> None:
        for other in self._reservations.values():
            if other.reservation_id == exclude or other.status not in ACTIVE_STATUSES:
                continue
            if other.slot.overlaps(slot):
                raise DoubleBookingError(
                    f"テーブル {self.table.table_id} は {other.slot.start:%H:%M}〜{other.slot.end:%H:%M} に"
                    f"予約 {other.reservation_id} があります"
                )

    @staticmethod
    def _base(r: Reservation) -> Money:
        return r.course_price.times(r.party.value)
