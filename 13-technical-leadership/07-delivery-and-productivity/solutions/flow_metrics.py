"""13.7 デリバリーと生産性 — 解答例: フローメトリクス

演習の仕様は exercises/flow_metrics.py の docstring を参照してください。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from dora_metrics import parse_time, percentile  # 演習1 の関数を再利用する

START_STATE = "In Progress"
DONE_STATE = "Done"


@dataclass(frozen=True)
class Event:
    ticket: str
    at: datetime
    to: str


def load_ticket_events(path: str | Path) -> tuple[list[Event], datetime, list[str]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = [Event(e["ticket"], parse_time(e["at"]), e["to"]) for e in data["events"]]
    return events, parse_time(data["now"]), list(data["active_states"])


def _by_ticket(events: list[Event]) -> dict[str, list[Event]]:
    groups: dict[str, list[Event]] = {}
    for e in sorted(events, key=lambda e: (e.at, e.ticket)):
        groups.setdefault(e.ticket, []).append(e)
    return groups


def _start_and_done(history: list[Event]) -> tuple[datetime | None, datetime | None]:
    start = next((e.at for e in history if e.to == START_STATE), None)
    if start is None:
        return None, None
    done = next((e.at for e in history if e.to == DONE_STATE and e.at >= start), None)
    return start, done


# ---------------------------------------------------------------------------
# 演習3: サイクルタイムとスループット
# ---------------------------------------------------------------------------

def cycle_times_days(events: list[Event]) -> dict[str, float]:
    result = {}
    for ticket, history in sorted(_by_ticket(events).items()):
        start, done = _start_and_done(history)
        if start is not None and done is not None:
            result[ticket] = (done - start).total_seconds() / 86400
    return result


def cycle_time_percentiles(events: list[Event], ps: tuple[float, ...] = (50, 85, 95)) -> dict[float, float]:
    values = list(cycle_times_days(events).values())
    return {p: percentile(values, p) for p in ps}


def throughput_per_week(events: list[Event], start: datetime, weeks: int) -> list[int]:
    if weeks < 1:
        raise ValueError("weeks は 1 以上にしてください")
    counts = [0] * weeks
    for history in _by_ticket(events).values():
        _, done = _start_and_done(history)
        if done is None or done < start:
            continue
        week = int((done - start) / timedelta(days=7))
        if week < weeks:
            counts[week] += 1
    return counts


# ---------------------------------------------------------------------------
# 演習4: 仕掛かり（WIP）、フロー効率、滞留アラート
# ---------------------------------------------------------------------------

def wip_at(events: list[Event], times: list[datetime]) -> list[int]:
    spans = [_start_and_done(h) for h in _by_ticket(events).values()]
    result = []
    for t in times:
        # 時刻 t に「着手済みで、まだ完了していない」チケットの数
        result.append(sum(1 for s, d in spans if s is not None and s <= t and (d is None or d > t)))
    return result


def flow_efficiency(events: list[Event], active_states: list[str]) -> tuple[dict[str, float], float]:
    active_set = set(active_states)
    per_ticket: dict[str, float] = {}
    total_active = total_cycle = 0.0
    for ticket, history in sorted(_by_ticket(events).items()):
        start, done = _start_and_done(history)
        if start is None or done is None:
            continue
        cycle = (done - start).total_seconds()
        if cycle <= 0:
            continue
        # 着手から完了までの各区間の状態を調べ、能動的な状態にいた時間を合計する
        active = 0.0
        for cur, nxt in zip(history, history[1:]):
            lo, hi = max(cur.at, start), min(nxt.at, done)
            if hi > lo and cur.to in active_set:
                active += (hi - lo).total_seconds()
        per_ticket[ticket] = active / cycle
        total_active += active
        total_cycle += cycle
    overall = total_active / total_cycle if total_cycle > 0 else 0.0
    return per_ticket, overall


def aging_wip(events: list[Event], now: datetime, threshold_days: float) -> list[tuple[str, float, str]]:
    result = []
    for ticket, history in _by_ticket(events).items():
        past = [e for e in history if e.at <= now]
        start, done = _start_and_done(past)
        if start is None or done is not None:
            continue
        age = (now - start).total_seconds() / 86400
        if age > threshold_days:
            result.append((ticket, age, past[-1].to))
    return sorted(result, key=lambda x: (-x[1], x[0]))
