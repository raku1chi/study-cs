"""9.3 ドメイン駆動設計とモジュール分割 — 演習: レストラン予約のドメインモデル

レストランの予約を題材に、DDD の戦術的設計（値オブジェクト・エンティティ・集約・ドメインイベント）を
実装します。本文の「ユビキタス言語」の表と見比べながら進めてください。

    演習1（★☆☆）: 値オブジェクト PartySize / TimeSlot / Money / CancellationPolicy / Table
    演習2（★★★）: 集約ルート TableSchedule（二重予約の禁止・状態遷移・キャンセル料・ドメインイベント）
演習3（ACL）は acl.py にあります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.3
    python3 tools/check.py -v 9.3

設計上の約束:
    - 値オブジェクトは不変（frozen）で、不正な値では生成できない（InvalidValueError）。
    - 日時はタイムゾーン付きの datetime で扱う。
    - 金額は円の整数。割合の計算の端数は切り捨て。
    - 集約の外に内部のエンティティをそのまま渡さない（読み取りはコピーを返す）。
"""
from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum


# ---------------------------------------------------------------------------
# 例外 — 実装済み
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """予約ドメインの業務エラーの基底クラス。"""


class InvalidValueError(DomainError, ValueError):
    """値オブジェクトに不正な値を渡した。"""


class CapacityError(DomainError):
    """テーブルの定員に合わない人数。"""


class DoubleBookingError(DomainError):
    """同じテーブルで時間帯が重なる有効な予約がすでにある。"""


class BookingWindowError(DomainError):
    """予約できない日時（過去、または台帳と別の日）。"""


class InvalidTransitionError(DomainError):
    """現在の状態・時刻では許されない状態遷移。"""


class ReservationNotFoundError(DomainError):
    pass


class DuplicateReservationError(DomainError):
    pass


def _is_int(value: object) -> bool:
    """bool を除く int かどうか（True が 1 人として通らないように）。"""
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 値オブジェクト
# ---------------------------------------------------------------------------

MAX_PARTY = 20


@dataclass(frozen=True)
class PartySize:
    """来店人数。1〜MAX_PARTY の int（bool は不可）。違反は InvalidValueError。"""

    value: int

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: PartySize の検証を実装してください")


@dataclass(frozen=True)
class TimeSlot:
    """予約の時間枠 [start, end)。

    - start: タイムゾーン付きの datetime（utcoffset() が None なら不可）。分は 15 分単位、秒・マイクロ秒は 0
    - minutes: 30〜240 の 15 の倍数（int）
    違反は InvalidValueError。
    """

    start: datetime
    minutes: int

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: TimeSlot の検証を実装してください")

    @property
    def end(self) -> datetime:
        """start + minutes 分。"""
        raise NotImplementedError("演習1: TimeSlot.end を実装してください")

    def overlaps(self, other: "TimeSlot") -> bool:
        """半開区間どうしが重なるか。18:00〜19:30 と 19:30〜21:00 は重ならない。"""
        raise NotImplementedError("演習1: TimeSlot.overlaps を実装してください")


@dataclass(frozen=True)
class Money:
    """金額。amount は 0 以上の int（bool は不可）、currency は "JPY" のような 3 文字の大文字 ASCII。

    - a + b: 同じ通貨なら新しい Money、違う通貨なら InvalidValueError
    - times(n): n 倍（n は 0 以上の int）
    - percent(p): p% の金額（p は 0〜100 の int）。端数は切り捨て（Money(999).percent(50) は 499 円）
    """

    amount: int
    currency: str = "JPY"

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: Money の検証を実装してください")

    def __add__(self, other: "Money") -> "Money":
        raise NotImplementedError("演習1: Money.__add__ を実装してください")

    def times(self, n: int) -> "Money":
        raise NotImplementedError("演習1: Money.times を実装してください")

    def percent(self, p: int) -> "Money":
        raise NotImplementedError("演習1: Money.percent を実装してください")


@dataclass(frozen=True)
class CancellationPolicy:
    """キャンセル規定。tiers は (この時間以上前なら, 料率%) の組を「時間の大きい順」に並べたもの。

    例（既定）: ((24 時間, 0), (3 時間, 50), (0 時間, 100))
        開始の 24 時間以上前 → 0%、3 時間以上前 → 50%、それ以降 → 100%

    検証（違反は InvalidValueError）:
    - 空でない。時間は 0 以上、料率は 0〜100 の int
    - 時間は狭義単調減少（同じ時間の段階が 2 つあってはいけない）
    - 料率は直前になるほど下がってはいけない（単調非減少）
    - 最後の段階の時間は 0（どんな直前のキャンセルにも料率が決まるように）
    """

    tiers: tuple[tuple[timedelta, int], ...]

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: CancellationPolicy の検証を実装してください")

    def fee_percent(self, lead_time: timedelta) -> int:
        """開始までの残り時間 lead_time に対する料率。lead_time が負（開始後）なら最後の段階の料率。"""
        raise NotImplementedError("演習1: CancellationPolicy.fee_percent を実装してください")

    def fee(self, base: Money, lead_time: timedelta) -> Money:
        """base に fee_percent の料率を掛けた金額（端数は切り捨て）。"""
        raise NotImplementedError("演習1: CancellationPolicy.fee を実装してください")


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
    """テーブル（席）。min_party〜max_party 名のグループを受け入れる。"""

    table_id: str
    min_party: int
    max_party: int

    def accepts(self, party: PartySize) -> bool:
        raise NotImplementedError("演習1: Table.accepts を実装してください")


# ---------------------------------------------------------------------------
# エンティティとドメインイベント — 実装済み
# ---------------------------------------------------------------------------

class ReservationStatus(Enum):
    BOOKED = "booked"          # 予約済み
    SEATED = "seated"          # 着席（来店）
    COMPLETED = "completed"    # 退店済み
    CANCELLED = "cancelled"    # キャンセル
    NO_SHOW = "no_show"        # 無断キャンセル


# テーブルを「ふさいでいる」状態。これ以外の予約は時間枠を解放している
ACTIVE_STATUSES = frozenset({ReservationStatus.BOOKED, ReservationStatus.SEATED})


@dataclass
class Reservation:
    """予約（集約内部のエンティティ）。reservation_id で識別される。fee は請求するキャンセル料。"""

    reservation_id: str
    customer_id: str
    party: PartySize
    slot: TimeSlot
    course_price: Money   # 1 名あたりのコース料金
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
# 演習2（★★★）: 集約ルート
# ---------------------------------------------------------------------------

class TableSchedule:
    """1 つのテーブルの 1 日分の予約台帳（集約ルート）。

    不変条件:
    - 有効な予約（ACTIVE_STATUSES）どうしの時間枠は重ならない（二重予約の禁止）
    - 予約の人数はテーブルの定員に合う
    - 予約の開始日（slot.start.date()）はこの台帳の日付 day と同じ
    - 状態遷移は次の図のとおり（それ以外は InvalidTransitionError）

        BOOKED ──seat──▶ SEATED ──complete──▶ COMPLETED
        BOOKED ──cancel──▶ CANCELLED        （開始時刻より前のみ。キャンセル料は規定による）
        BOOKED ──mark_no_show──▶ NO_SHOW     （開始 15 分後以降のみ。料率 100%）

    キャンセル料の基準額は「コース料金 × 人数」。
    状態が変わるたびに、対応するドメインイベントを内部のリストに記録する（pull_events で取り出す）。
    """

    SEAT_EARLY = timedelta(minutes=15)      # 開始の何分前から着席できるか
    NO_SHOW_GRACE = timedelta(minutes=15)   # 開始の何分後から無断キャンセルと判定できるか

    def __init__(self, table: Table, day: date, policy: CancellationPolicy | None = None) -> None:
        self.table = table
        self.day = day
        self.policy = policy if policy is not None else default_policy()
        self._reservations: dict[str, Reservation] = {}
        self._events: list[object] = []

    # --- 読み取り（実装済み。内部のエンティティは渡さず、コピーを返す） -----------

    def reservation(self, reservation_id: str) -> Reservation:
        return copy.deepcopy(self._get(reservation_id))

    def reservations(self) -> list[Reservation]:
        """すべての予約のコピーを (開始時刻, 予約 ID) の順に返す。"""
        items = sorted(self._reservations.values(), key=lambda r: (r.slot.start, r.reservation_id))
        return [copy.deepcopy(r) for r in items]

    def pull_events(self) -> list[object]:
        """記録したドメインイベントを発生順に返し、内部のリストを空にする。"""
        events, self._events = self._events, []
        return events

    def _get(self, reservation_id: str) -> Reservation:
        try:
            return self._reservations[reservation_id]
        except KeyError:
            raise ReservationNotFoundError(reservation_id) from None

    # --- コマンド（演習2） --------------------------------------------------------

    def book(self, reservation_id: str, customer_id: str, party: PartySize, slot: TimeSlot,
             course_price: Money, now: datetime) -> Reservation:
        """予約を受け付け、BOOKED の予約のコピーを返す。ReservationBooked を記録する。

        検査の順序と例外:
        1. 同じ reservation_id がすでにある → DuplicateReservationError
        2. slot の開始日が台帳の日付と違う、または開始が now 以前 → BookingWindowError
        3. 人数がテーブルの定員外 → CapacityError
        4. 有効な予約と時間枠が重なる → DoubleBookingError
        失敗したときは台帳を一切変更しない。
        """
        raise NotImplementedError("演習2: TableSchedule.book を実装してください")

    def reschedule(self, reservation_id: str, new_slot: TimeSlot, now: datetime) -> None:
        """BOOKED の予約の時間枠を変更する。ReservationRescheduled を記録する。

        - BOOKED 以外 → InvalidTransitionError
        - new_slot が台帳の日付と違う・過去 → BookingWindowError
        - 「自分以外の」有効な予約と重なる → DoubleBookingError（自分の元の枠とは重なってよい）
        """
        raise NotImplementedError("演習2: TableSchedule.reschedule を実装してください")

    def cancel(self, reservation_id: str, now: datetime) -> Money:
        """BOOKED の予約をキャンセルし、キャンセル料を返す。ReservationCancelled を記録する。

        - BOOKED 以外、または now が開始時刻以降 → InvalidTransitionError
        - キャンセル料 = policy.fee(コース料金 × 人数, 開始時刻 - now)。予約の fee に記録する
        """
        raise NotImplementedError("演習2: TableSchedule.cancel を実装してください")

    def seat(self, reservation_id: str, now: datetime) -> None:
        """来店: BOOKED → SEATED。開始の SEAT_EARLY 前から終了時刻（slot.end、含まない）まで。

        それ以外の時刻や状態 → InvalidTransitionError。GuestsSeated(…, at=now) を記録する。
        """
        raise NotImplementedError("演習2: TableSchedule.seat を実装してください")

    def complete(self, reservation_id: str) -> None:
        """退店: SEATED → COMPLETED。ReservationCompleted を記録する。"""
        raise NotImplementedError("演習2: TableSchedule.complete を実装してください")

    def mark_no_show(self, reservation_id: str, now: datetime) -> Money:
        """無断キャンセル: BOOKED → NO_SHOW。now が開始 + NO_SHOW_GRACE 以降のときだけ。

        料金はコース料金 × 人数の 100%。予約の fee に記録し、ReservationMarkedNoShow を記録して返す。
        """
        raise NotImplementedError("演習2: TableSchedule.mark_no_show を実装してください")
