"""9.6 システム設計ケーススタディ — 解答例: 座席の仮押さえと確定（売り越しの防止）

演習の仕様は exercises/seat_hold.py の docstring を参照してください。
"""
from __future__ import annotations

import itertools
import threading
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


class SeatError(Exception):
    pass


class UnknownSeatError(SeatError, ValueError):
    pass


class SeatUnavailableError(SeatError):
    def __init__(self, seats: Sequence[str]) -> None:
        self.seats = tuple(sorted(seats))
        super().__init__(f"確保できない座席があります: {', '.join(self.seats)}")


class HoldLimitError(SeatError):
    pass


class HoldNotFoundError(SeatError):
    pass


class HoldExpiredError(SeatError):
    pass


class InvalidHoldStateError(SeatError):
    pass


@dataclass(frozen=True)
class Hold:
    hold_id: str
    user_id: str
    seat_ids: tuple[str, ...]
    expires_at: float


@dataclass(frozen=True)
class Booking:
    booking_id: str
    hold_id: str
    user_id: str
    seat_ids: tuple[str, ...]
    payment_ref: str


class SeatInventory:
    def __init__(
        self,
        seat_ids: Iterable[str],
        *,
        hold_ttl: float = 600.0,
        max_seats_per_user: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        seats = list(seat_ids)
        if len(set(seats)) != len(seats) or not seats:
            raise ValueError("座席 ID は 1 つ以上で、重複してはいけません")
        if hold_ttl <= 0 or max_seats_per_user < 1:
            raise ValueError("hold_ttl は正、max_seats_per_user は 1 以上です")
        self._seats = set(seats)
        self._ttl = hold_ttl
        self._max = max_seats_per_user
        self._clock = clock
        self._holder: dict[str, str] = {}      # 座席 → 仮押さえ中の hold_id
        self._booked: dict[str, str] = {}      # 座席 → booking_id
        self._holds: dict[str, Hold] = {}      # 有効な（未確定の）仮押さえ
        self._bookings: dict[str, Booking] = {}  # hold_id → 確定した予約
        self._expired: set[str] = set()          # 期限切れになった hold_id（確定の問い合わせに正しく答えるため）
        self._hold_ids = itertools.count(1)
        self._booking_ids = itertools.count(1)
        # すべての状態を 1 つのロックで守る。「空いているか調べて押さえる」を分割できない 1 つの操作にするため
        self._lock = threading.Lock()

    # --- 内部 -------------------------------------------------------------------

    def _expire(self, now: float) -> int:
        expired = [h for h in self._holds.values() if now >= h.expires_at]
        for h in expired:
            self._drop(h)
            self._expired.add(h.hold_id)
        return len(expired)

    def _drop(self, hold: Hold) -> None:
        del self._holds[hold.hold_id]
        for seat in hold.seat_ids:
            if self._holder.get(seat) == hold.hold_id:
                del self._holder[seat]

    def _seats_of(self, user_id: str) -> int:
        held = sum(len(h.seat_ids) for h in self._holds.values() if h.user_id == user_id)
        booked = sum(len(b.seat_ids) for b in self._bookings.values() if b.user_id == user_id)
        return held + booked

    # --- 操作 -------------------------------------------------------------------

    def hold(self, user_id: str, seat_ids: Sequence[str]) -> Hold:
        wanted = list(seat_ids)
        if not wanted or len(set(wanted)) != len(wanted):
            raise ValueError("座席を 1 つ以上、重複なく指定してください")
        unknown = [s for s in wanted if s not in self._seats]
        if unknown:
            raise UnknownSeatError(f"存在しない座席: {sorted(unknown)}")
        with self._lock:
            now = self._clock()
            self._expire(now)  # 期限切れの仮押さえは、ここで解放されたものとして扱う
            taken = [s for s in wanted if s in self._booked or s in self._holder]
            if taken:
                raise SeatUnavailableError(taken)  # 1 席でも取れなければ、何も押さえない（全部か無か）
            if self._seats_of(user_id) + len(wanted) > self._max:
                raise HoldLimitError(f"1 人が確保できるのは {self._max} 席までです")
            hold = Hold(f"hold-{next(self._hold_ids):06d}", user_id, tuple(sorted(wanted)), now + self._ttl)
            self._holds[hold.hold_id] = hold
            for seat in hold.seat_ids:
                self._holder[seat] = hold.hold_id
            return hold

    def confirm(self, hold_id: str, payment_ref: str) -> Booking:
        with self._lock:
            done = self._bookings.get(hold_id)
            if done is not None:
                # 確定の再送（決済の完了通知の重複など）には、同じ結果を返す
                if done.payment_ref != payment_ref:
                    raise InvalidHoldStateError(f"{hold_id} は別の決済 {done.payment_ref} で確定済みです")
                return done
            self._expire(self._clock())
            if hold_id in self._expired:
                raise HoldExpiredError(f"{hold_id} は期限切れです。座席は解放されました")
            hold = self._holds.get(hold_id)
            if hold is None:
                raise HoldNotFoundError(hold_id)
            booking = Booking(f"bk-{next(self._booking_ids):06d}", hold_id, hold.user_id, hold.seat_ids,
                              payment_ref)
            self._drop(hold)
            for seat in hold.seat_ids:
                self._booked[seat] = booking.booking_id
            self._bookings[hold_id] = booking
            return booking

    def release(self, hold_id: str) -> None:
        with self._lock:
            if hold_id in self._bookings:
                raise InvalidHoldStateError(f"{hold_id} は確定済みなので、仮押さえとしては解放できません")
            self._expire(self._clock())
            if hold_id in self._expired:
                return  # 期限切れで既に解放済み。何度呼んでもよい
            hold = self._holds.get(hold_id)
            if hold is None:
                raise HoldNotFoundError(hold_id)
            self._drop(hold)

    def expire_holds(self) -> int:
        with self._lock:
            return self._expire(self._clock())

    def seat_state(self, seat_id: str) -> str:
        if seat_id not in self._seats:
            raise UnknownSeatError(seat_id)
        with self._lock:
            if seat_id in self._booked:
                return "booked"
            hold_id = self._holder.get(seat_id)
            if hold_id is not None and self._clock() < self._holds[hold_id].expires_at:
                return "held"
            return "available"

    def available(self) -> set[str]:
        with self._lock:
            now = self._clock()
            held = {s for s, h in self._holder.items() if now < self._holds[h].expires_at}
            return self._seats - set(self._booked) - held
