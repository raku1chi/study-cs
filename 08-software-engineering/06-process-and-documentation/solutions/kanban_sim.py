"""8.6 開発プロセスとドキュメンテーション — 解答例: カンバンのシミュレーター

仕様は exercises/kanban_sim.py の docstring を参照してください。
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Stage:
    name: str
    workers: int
    wip_limit: Optional[int] = None


@dataclass(frozen=True)
class Item:
    id: str
    arrival_day: int
    work: tuple[int, ...]


@dataclass(frozen=True)
class Completed:
    id: str
    start_day: int
    finish_day: int

    @property
    def lead_time(self) -> int:
        return self.finish_day - self.start_day


@dataclass(frozen=True)
class SimulationResult:
    days: int
    completed: tuple[Completed, ...]
    wip_by_day: tuple[int, ...]
    throughput: float
    average_wip: float
    average_lead_time: float


def generate_items(
    n: int, work_ranges: Sequence[tuple[int, int]], *, arrivals_per_day: int = 1, seed: int = 0
) -> list[Item]:
    rng = random.Random(seed)
    return [
        Item(f"item-{i:04d}", i // arrivals_per_day, tuple(rng.randint(lo, hi) for lo, hi in work_ranges))
        for i in range(n)
    ]


def _validate(stages: Sequence[Stage], items: Sequence[Item], days: Optional[int], until_empty: bool) -> None:
    if not stages:
        raise ValueError("工程が 1 つもありません")
    for s in stages:
        if s.workers < 1 or (s.wip_limit is not None and s.wip_limit < 1):
            raise ValueError(f"工程 {s.name!r} の workers・wip_limit が不正です")
    ids = set()
    for item in items:
        if len(item.work) != len(stages) or any(w < 1 for w in item.work) or item.arrival_day < 0:
            raise ValueError(f"項目 {item.id!r} の作業量または到着日が不正です")
        if item.id in ids:
            raise ValueError(f"項目の id が重複しています: {item.id!r}")
        ids.add(item.id)
    if (days is None) == (not until_empty):
        raise ValueError("days と until_empty は、どちらか一方だけを指定してください")
    if days is not None and days < 1:
        raise ValueError(f"days は 1 以上にしてください: {days}")


def simulate(
    stages: Sequence[Stage],
    items: Sequence[Item],
    *,
    days: Optional[int] = None,
    until_empty: bool = False,
) -> SimulationResult:
    _validate(stages, items, days, until_empty)
    last = len(stages) - 1
    arrivals: dict[int, list[Item]] = {}
    for item in items:
        arrivals.setdefault(item.arrival_day, []).append(item)

    backlog: deque[Item] = deque()
    # 工程ごとに、入った順の [項目, 残りの作業量]
    board: list[list[list]] = [[] for _ in stages]
    started: dict[str, int] = {}
    completed: list[Completed] = []
    wip_by_day: list[int] = []

    def has_room(i: int) -> bool:
        limit = stages[i].wip_limit
        return limit is None or len(board[i]) < limit

    day = 0
    while True:
        if days is not None and day >= days:
            break
        # 1. 到着
        backlog.extend(arrivals.get(day, []))
        # 2. 引き取り: 下流から処理するので、同じ日に下流が空けた枠を上流が使える
        for i in range(last, -1, -1):
            remaining_in_stage = []
            for entry in board[i]:
                item, remaining = entry
                if remaining == 0 and i == last:
                    completed.append(Completed(item.id, started[item.id], day))
                elif remaining == 0 and has_room(i + 1):
                    board[i + 1].append([item, item.work[i + 1]])
                else:
                    remaining_in_stage.append(entry)
            board[i] = remaining_in_stage
        # 3. 開始（ここがコミットメントポイント）
        while backlog and has_room(0):
            item = backlog.popleft()
            started[item.id] = day
            board[0].append([item, item.work[0]])
        # 4. 作業: 入った順に、作業の残っている項目へ作業者を割り当てる
        for i, stage in enumerate(stages):
            busy = 0
            for entry in board[i]:
                if busy == stage.workers:
                    break
                if entry[1] > 0:
                    entry[1] -= 1
                    busy += 1
        # 5. 記録
        wip_by_day.append(sum(len(column) for column in board))
        day += 1
        if until_empty and len(completed) == len(items):
            break

    n_days = len(wip_by_day)
    lead_times = [c.lead_time for c in completed]
    return SimulationResult(
        days=n_days,
        completed=tuple(completed),
        wip_by_day=tuple(wip_by_day),
        throughput=len(completed) / n_days,
        average_wip=sum(wip_by_day) / n_days,
        average_lead_time=sum(lead_times) / len(lead_times) if lead_times else 0.0,
    )
