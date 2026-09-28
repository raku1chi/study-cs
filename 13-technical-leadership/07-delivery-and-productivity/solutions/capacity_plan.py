"""13.7 デリバリーと生産性 — 解答例: 四半期のチームのキャパシティ計画

演習の仕様は exercises/capacity_plan.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Member:
    name: str
    fte: float = 1.0
    leave_days: float = 0.0
    oncall_weeks: int = 0


# ---------------------------------------------------------------------------
# 演習5: 営業日、キャパシティ、配分
# ---------------------------------------------------------------------------

def business_days(start: date, end: date, holidays: set[date] | list[date] = ()) -> int:
    if end < start:
        raise ValueError("end は start 以降にしてください")
    off = set(holidays)
    count = 0
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in off:  # 月〜金で、休日でない日
            count += 1
        d += timedelta(days=1)
    return count


def member_capacity(
    member: Member, days: int, overhead_ratio: float = 0.2, oncall_cost_days: float = 2.0
) -> float:
    if not 0 < member.fte <= 1:
        raise ValueError(f"{member.name}: fte は 0 より大きく 1 以下")
    if member.leave_days < 0 or member.oncall_weeks < 0 or days < 0:
        raise ValueError(f"{member.name}: 日数は 0 以上")
    if not 0 <= overhead_ratio < 1 or oncall_cost_days < 0:
        raise ValueError("overhead_ratio は 0 以上 1 未満、oncall_cost_days は 0 以上")
    available = max(0.0, days - member.leave_days) * member.fte
    # 会議・レビュー・割り込みなどの間接作業を差し引き、オンコールの週の負担を引く
    focus = available * (1 - overhead_ratio) - member.oncall_weeks * oncall_cost_days
    return max(0.0, focus)


def team_capacity(
    members: list[Member], days: int, overhead_ratio: float = 0.2, oncall_cost_days: float = 2.0
) -> float:
    return sum(member_capacity(m, days, overhead_ratio, oncall_cost_days) for m in members)


def allocate(total_days: float, buckets: dict[str, float], step: float = 0.5) -> dict[str, float]:
    if total_days < 0 or step <= 0:
        raise ValueError("total_days は 0 以上、step は正の値")
    if not buckets or any(s < 0 for s in buckets.values()):
        raise ValueError("buckets は空でなく、割合は 0 以上")
    if abs(sum(buckets.values()) - 1.0) > 1e-9:
        raise ValueError("割合の合計は 1 にしてください")
    units = math.floor(total_days / step + 1e-9)  # 配れる単位の数（端数は切り捨て）
    raw = {name: units * share for name, share in buckets.items()}
    alloc = {name: math.floor(v + 1e-9) for name, v in raw.items()}
    # 最大剰余法: 切り捨てで余った単位を、端数の大きいバケットから順に 1 つずつ配る
    rest = units - sum(alloc.values())
    order = sorted(buckets, key=lambda n: (-(raw[n] - alloc[n]), list(buckets).index(n)))
    for name in order[:rest]:
        alloc[name] += 1
    return {name: alloc[name] * step for name in buckets}
