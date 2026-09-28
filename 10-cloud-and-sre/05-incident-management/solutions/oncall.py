"""10.5 インシデント対応とポストモーテム — 演習（公平なオンコール表）の解答例

演習の仕様は exercises/oncall.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class Site:
    name: str
    utc_offset: int      # UTC からの時差（時間）。夏時間は考えない
    day_start: int = 9   # 現地時刻で担当を始められる時（この時を含む）
    day_end: int = 17    # 現地時刻で担当を終える時（この時を含まない）


@dataclass(frozen=True)
class Engineer:
    name: str
    site: str
    unavailable_weeks: frozenset[int] = field(default_factory=frozenset)


@dataclass
class Schedule:
    assignments: dict[tuple[int, str], str]   # (週, 拠点) → 担当者
    load: dict[str, float]                    # 担当者 → 重み付きの負荷の合計
    warnings: list[str]


class ScheduleError(Exception):
    """制約を満たす担当者がいない。"""


# ===========================================================================
# 演習3: フォロー・ザ・サンのカバー範囲
# ===========================================================================

def utc_coverage(sites: Sequence[Site]) -> list[list[str]]:
    coverage: list[list[str]] = [[] for _ in range(24)]
    for site in sites:
        if not 0 <= site.day_start < site.day_end <= 24:
            raise ValueError(f"{site.name}: 0 <= day_start < day_end <= 24 にしてください")
        for utc_hour in range(24):
            local = (utc_hour + site.utc_offset) % 24  # 負の時差でも % 24 で 0〜23 に収まる
            if site.day_start <= local < site.day_end:
                coverage[utc_hour].append(site.name)
    return [sorted(names) for names in coverage]


def coverage_gaps(sites: Sequence[Site]) -> list[tuple[int, int]]:
    gaps: list[tuple[int, int]] = []
    start = None
    for hour, names in enumerate(utc_coverage(sites) + [["sentinel"]]):
        if not names and start is None:
            start = hour
        elif names and start is not None:
            gaps.append((start, hour))
            start = None
    return gaps


# ===========================================================================
# 演習4: 公平なオンコール表
# ===========================================================================

def slot_weight(site: str, week: int, holidays: Mapping[tuple[str, int], int], holiday_weight: float,
                days_per_week: int = 7) -> float:
    days = holidays.get((site, week), 0)
    if not 0 <= days <= days_per_week:
        raise ValueError(f"祝日の日数が不正です: {site} 第{week}週 {days}日")
    return (days_per_week - days) + holiday_weight * days


def build_schedule(
    engineers: Sequence[Engineer],
    weeks: int,
    *,
    holidays: Mapping[tuple[str, int], int] | None = None,
    holiday_weight: float = 2.0,
) -> Schedule:
    holidays = holidays or {}
    names = [e.name for e in engineers]
    if len(set(names)) != len(names):
        raise ValueError("担当者の名前が重複しています")
    by_site: dict[str, list[Engineer]] = defaultdict(list)
    for e in engineers:
        by_site[e.site].append(e)

    load = {e.name: 0.0 for e in engineers}
    shifts = {e.name: 0 for e in engineers}
    assignments: dict[tuple[int, str], str] = {}
    warnings: list[str] = []
    for week in range(weeks):
        for site in sorted(by_site):
            weight = slot_weight(site, week, holidays, holiday_weight)
            previous = assignments.get((week - 1, site))
            available = [e for e in by_site[site] if week not in e.unavailable_weeks]
            if not available:
                raise ScheduleError(f"第{week}週の {site} に担当できる人がいません")
            # 制約: 2 週連続にしない。守れないときだけ緩め、警告を残す（休みの予定は絶対に破らない）
            candidates = [e for e in available if e.name != previous]
            if not candidates:
                candidates = available
                warnings.append(f"第{week}週 {site}: {previous} が 2 週連続になります")
            # 公平性: これまでの重み付きの負荷が最も小さい人。同じなら担当回数が少ない人、次に名前順
            chosen = min(candidates, key=lambda e: (load[e.name], shifts[e.name], e.name))
            assignments[(week, site)] = chosen.name
            load[chosen.name] += weight
            shifts[chosen.name] += 1
    return Schedule(assignments, load, warnings)


def load_spread(schedule: Schedule, engineers: Sequence[Engineer]) -> dict[str, float]:
    by_site: dict[str, list[float]] = defaultdict(list)
    for e in engineers:
        by_site[e.site].append(schedule.load[e.name])
    return {site: max(v) - min(v) for site, v in sorted(by_site.items())}
