"""10.5 インシデント対応とポストモーテム — 演習（インシデントの指標と SLA のクレジット）の解答例

演習の仕様は exercises/incident_metrics.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from typing import Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class Incident:
    id: str
    severity: str               # "SEV1"〜"SEV4"
    started_at: datetime        # 影響が始まった時刻（後から調査で判明することが多い）
    detected_at: datetime       # 検知した時刻（アラート・問い合わせ）
    acknowledged_at: datetime   # 担当者が応答した時刻
    mitigated_at: datetime      # 利用者への影響がなくなった時刻（切り戻しなどによる緩和）
    resolved_at: datetime       # インシデントとして解決した時刻


METRICS = ("ttd", "tta", "ttm", "ttr")


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ===========================================================================
# 演習1: 所要時間と分布の要約
# ===========================================================================

def durations(incident: Incident) -> dict[str, float]:
    i = incident
    if not (i.started_at <= i.detected_at <= i.acknowledged_at):
        raise ValueError(f"{i.id}: started <= detected <= acknowledged の順になっていません")
    if not (i.started_at <= i.mitigated_at <= i.resolved_at):
        raise ValueError(f"{i.id}: started <= mitigated <= resolved の順になっていません")

    def minutes(a: datetime, b: datetime) -> float:
        return (b - a).total_seconds() / 60

    return {
        "ttd": minutes(i.started_at, i.detected_at),       # 検知までの時間
        "tta": minutes(i.detected_at, i.acknowledged_at),  # 応答までの時間
        "ttm": minutes(i.started_at, i.mitigated_at),      # 影響がなくなるまでの時間
        "ttr": minutes(i.started_at, i.resolved_at),       # 解決までの時間
    }


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("values が空です")
    if not 0 < p <= 100:
        raise ValueError(f"p は 0 < p <= 100: {p}")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


def summarize(incidents: Sequence[Incident], metric: str) -> dict[str, dict[str, float]]:
    if metric not in METRICS:
        raise ValueError(f"metric は {METRICS} のいずれか: {metric!r}")
    groups: dict[str, list[float]] = defaultdict(list)
    for inc in incidents:
        value = durations(inc)[metric]
        groups[inc.severity].append(value)
        groups["ALL"].append(value)

    def describe(values: list[float]) -> dict[str, float]:
        # 平均は裾の長い分布では 1 件の長いインシデントに引っ張られる。中央値と p90 を主に見る
        return {
            "count": len(values),
            "median": statistics.median(values),
            "p90": percentile(values, 90),
            "mean": statistics.fmean(values),
            "max": max(values),
        }

    return {key: describe(groups[key]) for key in sorted(groups)}


# ===========================================================================
# 演習2: 月間の停止時間と SLA のクレジット
# ===========================================================================

def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    start = utc(year, month, 1)
    end = utc(year + 1, 1, 1) if month == 12 else utc(year, month + 1, 1)
    return start, end


def downtime(intervals: Sequence[tuple[datetime, datetime]], start: datetime, end: datetime) -> timedelta:
    clipped = []
    for s, e in intervals:
        if e < s:
            raise ValueError(f"終了が開始より前です: {s} > {e}")
        s, e = max(s, start), min(e, end)  # 期間の外にはみ出した部分は数えない
        if s < e:
            clipped.append((s, e))
    total = timedelta(0)
    cur_s = cur_e = None
    for s, e in sorted(clipped):
        if cur_e is None or s > cur_e:
            if cur_e is not None:
                total += cur_e - cur_s
            cur_s, cur_e = s, e
        else:
            cur_e = max(cur_e, e)  # 重なる停止は二重に数えない
    if cur_e is not None:
        total += cur_e - cur_s
    return total


def monthly_downtime(intervals: Sequence[tuple[datetime, datetime]], year: int, month: int) -> timedelta:
    return downtime(intervals, *month_range(year, month))


def uptime_percent(down: timedelta, period: timedelta) -> float:
    if period <= timedelta(0) or not timedelta(0) <= down <= period:
        raise ValueError("0 <= down <= period、period > 0 にしてください")
    return (1 - down / period) * 100


def _as_fraction(td: timedelta) -> Fraction:
    # timedelta はマイクロ秒単位の整数で表せるので、誤差なく分数にできる
    return Fraction(td // timedelta(microseconds=1))


def sla_credit_percent(down: timedelta, period: timedelta, tiers: Sequence[tuple[float, int]]) -> int:
    if period <= timedelta(0) or not timedelta(0) <= down <= period:
        raise ValueError("0 <= down <= period、period > 0 にしてください")
    uptime = (1 - _as_fraction(down) / _as_fraction(period)) * 100
    credit = 0
    for threshold, percent in tiers:
        # 浮動小数点の計算は、境界ちょうどの値で誤差により判定が逆転しうる（1.1 章）。契約の判定は分数で厳密に行う
        if uptime < Fraction(str(threshold)):
            credit = max(credit, percent)
    return credit


def credit_yen(monthly_fee_yen: int, credit_percent: int) -> int:
    if monthly_fee_yen < 0 or not 0 <= credit_percent <= 100:
        raise ValueError("料金は 0 以上、クレジットの割合は 0〜100")
    return monthly_fee_yen * credit_percent // 100  # 円未満は切り捨て（契約の定めに従う）
