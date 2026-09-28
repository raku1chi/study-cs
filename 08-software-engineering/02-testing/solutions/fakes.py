"""8.2 テスト戦略 — 解答例: テストダブル（fake・stub・spy）

仕様は exercises/fakes.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, Optional

from subscriptions import (
    DUE_STATUSES,
    DuplicateSubscriptionError,
    Subscription,
    SubscriptionNotFoundError,
)


def _require_aware(dt: datetime, what: str) -> None:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{what} には timezone 付きの datetime を指定してください: {dt!r}")


# ---------------------------------------------------------------------------
# 演習3-1: インメモリのリポジトリ（fake）
# ---------------------------------------------------------------------------

class InMemorySubscriptionRepository:
    def __init__(self) -> None:
        self._items: dict[str, Subscription] = {}

    def add(self, sub: Subscription) -> None:
        _require_aware(sub.current_period_end, "current_period_end")
        if sub.id in self._items:
            raise DuplicateSubscriptionError(sub.id)
        # 本物の DB と同じく「値」を保存する。参照を保存すると、呼び出し側の変更が漏れ込む
        self._items[sub.id] = replace(sub)

    def get(self, sub_id: str) -> Optional[Subscription]:
        sub = self._items.get(sub_id)
        return replace(sub) if sub is not None else None

    def update(self, sub: Subscription) -> None:
        _require_aware(sub.current_period_end, "current_period_end")
        if sub.id not in self._items:
            raise SubscriptionNotFoundError(sub.id)
        self._items[sub.id] = replace(sub)

    def list_due(self, now: datetime) -> list[Subscription]:
        _require_aware(now, "now")
        due = [
            s for s in self._items.values()
            if s.status in DUE_STATUSES and s.current_period_end <= now
        ]
        # 本物は ORDER BY current_period_end, id。並び順も契約の一部
        due.sort(key=lambda s: (s.current_period_end, s.id))
        return [replace(s) for s in due]


# ---------------------------------------------------------------------------
# 演習3-2: テスト用の時計（fake）
# ---------------------------------------------------------------------------

class FakeClock:
    def __init__(self, start: datetime) -> None:
        _require_aware(start, "start")
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        if delta < timedelta(0):
            raise ValueError(f"時計を戻すことはできません（set を使ってください）: {delta}")
        self._now += delta

    def set(self, when: datetime) -> None:
        _require_aware(when, "when")
        self._now = when


# ---------------------------------------------------------------------------
# 演習3-3: 決済ゲートウェイ（stub + spy）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Charge:
    user_id: str
    amount: int
    idempotency_key: str


class RecordingPaymentGateway:
    def __init__(self, declined_users: Iterable[str] = ()) -> None:
        self.declined_users: set[str] = set(declined_users)  # stub: 返す結果を決める
        self.charges: list[Charge] = []  # spy: 呼び出しを記録する

    def charge(self, user_id: str, amount: int, idempotency_key: str) -> bool:
        self.charges.append(Charge(user_id, amount, idempotency_key))
        return user_id not in self.declined_users
