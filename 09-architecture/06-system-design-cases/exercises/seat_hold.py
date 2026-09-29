"""9.6 システム設計ケーススタディ — 演習3（★★☆）: 座席の仮押さえと確定（売り越しの防止）

ケーススタディ 7（チケット・ホテルの予約）の核心部分を実装します。

人気のコンサートの発売開始の瞬間には、同じ座席を大量の利用者が同時に取り合います。
「空いているか調べてから押さえる」を 2 つの別々の操作として実行すると、2 人が同時に
「空いている」と判断して、同じ座席を二重に販売（売り越し）してしまいます。
この演習では、次の 2 段階の流れを、同時実行に対して安全に実装します。

    1. 仮押さえ（hold）: 座席を一定時間（hold_ttl 秒）だけ確保する。期限までに確定しなければ自動的に解放
    2. 確定（confirm）: 決済が済んだら、仮押さえを予約（booking）に変える

本番のシステムでは、データベースの条件付き UPDATE（本文を参照）でこれを実現しますが、この演習では
1 つのロックで「調べて押さえる」を分割できない 1 つの操作にします。考え方は同じです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.6

時刻は clock（偽の時計を渡せる）で測ります。ID は "hold-000001"、"bk-000001" のように、1 から始まる連番です。
"""
from __future__ import annotations

import itertools  # noqa: F401
import threading  # noqa: F401
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


class SeatError(Exception):
    pass


class UnknownSeatError(SeatError, ValueError):
    pass


class SeatUnavailableError(SeatError):
    """確保できない座席があった。seats は確保できなかった座席 ID（昇順のタプル）。"""

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
    seat_ids: tuple[str, ...]   # 昇順
    expires_at: float


@dataclass(frozen=True)
class Booking:
    booking_id: str
    hold_id: str
    user_id: str
    seat_ids: tuple[str, ...]
    payment_ref: str


class SeatInventory:
    """座席の在庫。座席の状態は available（空き）/ held（仮押さえ中）/ booked（確定）のいずれか。

    コンストラクタ: 座席 ID が空、または重複していれば ValueError。hold_ttl は正、max_seats_per_user は 1 以上。

    hold(user_id, seat_ids) -> Hold
        - seat_ids が空・重複あり → ValueError。存在しない座席 → UnknownSeatError
        - 期限切れの仮押さえは、この時点で解放されたものとして扱う
        - 1 席でも booked か（有効な）held なら SeatUnavailableError(取れなかった座席) を送出し、何も押さえない
          （全部か無か。2 席並びで欲しい人に 1 席だけ渡しても意味がない）
        - その利用者の「有効な仮押さえの席数 + 確定済みの席数 + 今回の席数」が max_seats_per_user を超えたら
          HoldLimitError（転売目的の買い占めの抑制）
        - 成功したら、期限 = 現在時刻 + hold_ttl の Hold を返す（seat_ids は昇順のタプル）
    confirm(hold_id, payment_ref) -> Booking
        - すでに確定済みの hold_id: 同じ payment_ref なら同じ Booking を返す（決済通知の重複に対する冪等性）。
          違う payment_ref なら InvalidHoldStateError
        - 期限切れ（現在時刻 >= expires_at）なら HoldExpiredError。座席は解放する。
          期限切れの判定が他の操作で先に済んでいた場合も、同じく HoldExpiredError（HoldNotFoundError ではない）
        - 知らない hold_id（解放済みを含む）は HoldNotFoundError
        - 成功したら座席を booked にし、Booking を返す
    release(hold_id)
        - 有効な仮押さえを取り消して座席を空ける。期限切れのものは何もしない（エラーにしない）。
        - 確定済みは InvalidHoldStateError、知らない hold_id（解放済みを含む）は HoldNotFoundError
    expire_holds() -> int: 期限切れの仮押さえをすべて解放し、その数を返す（定期的な掃除用）
    seat_state(seat_id) -> str: "available" / "held" / "booked"（存在しない座席は UnknownSeatError）
    available() -> set[str]: 空いている座席の集合

    すべての操作は複数のスレッドから同時に呼ばれる。状態の確認と更新は、必ず 1 つのロックの中で行うこと。
    """

    def __init__(
        self,
        seat_ids: Iterable[str],
        *,
        hold_ttl: float = 600.0,
        max_seats_per_user: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        raise NotImplementedError("演習3: SeatInventory.__init__ を実装してください")

    def hold(self, user_id: str, seat_ids: Sequence[str]) -> Hold:
        raise NotImplementedError("演習3: SeatInventory.hold を実装してください")

    def confirm(self, hold_id: str, payment_ref: str) -> Booking:
        raise NotImplementedError("演習3: SeatInventory.confirm を実装してください")

    def release(self, hold_id: str) -> None:
        raise NotImplementedError("演習3: SeatInventory.release を実装してください")

    def expire_holds(self) -> int:
        raise NotImplementedError("演習3: SeatInventory.expire_holds を実装してください")

    def seat_state(self, seat_id: str) -> str:
        raise NotImplementedError("演習3: SeatInventory.seat_state を実装してください")

    def available(self) -> set[str]:
        raise NotImplementedError("演習3: SeatInventory.available を実装してください")
