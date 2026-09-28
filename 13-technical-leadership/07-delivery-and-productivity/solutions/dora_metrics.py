"""13.7 デリバリーと生産性 — 解答例: DORA の 4 つの指標

演習の仕様は exercises/dora_metrics.py の docstring を参照してください。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CLUSTERS = ("elite", "high", "medium", "low")

DEFAULT_THRESHOLDS: dict[str, tuple[str, list[tuple[str, float]]]] = {
    "deployment_frequency": ("higher", [("elite", 1.0), ("high", 1 / 7), ("medium", 1 / 30)]),
    "lead_time_median_hours": ("lower", [("elite", 24.0), ("high", 24.0 * 7), ("medium", 24.0 * 30)]),
    "change_failure_rate": ("lower", [("elite", 0.05), ("high", 0.10), ("medium", 0.15)]),
    "time_to_restore_hours": ("lower", [("elite", 1.0), ("high", 24.0), ("medium", 24.0 * 7)]),
}


@dataclass(frozen=True)
class Deployment:
    id: str
    deployed_at: datetime
    commit_times: tuple[datetime, ...]
    status: str


@dataclass(frozen=True)
class Incident:
    id: str
    started_at: datetime
    resolved_at: datetime
    deployment_id: str | None


def parse_time(text: str) -> datetime:
    t = datetime.fromisoformat(text)
    if t.tzinfo is None:
        raise ValueError(f"タイムゾーンのない時刻は扱いません: {text}")
    return t


def load_events(path: str | Path) -> tuple[list[Deployment], list[Incident], datetime, datetime]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    deployments = [
        Deployment(d["id"], parse_time(d["deployed_at"]),
                   tuple(parse_time(c) for c in d["commit_times"]), d["status"])
        for d in data["deployments"]
    ]
    incidents = [
        Incident(i["id"], parse_time(i["started_at"]), parse_time(i["resolved_at"]), i["deployment_id"])
        for i in data["incidents"]
    ]
    period = data["period"]
    return deployments, incidents, parse_time(period["start"]), parse_time(period["end"])


# ---------------------------------------------------------------------------
# 演習1: パーセンタイル、デプロイ頻度、変更のリードタイム
# ---------------------------------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    if not values:
        raise ValueError("値が 0 件です")
    if not 0 <= p <= 100:
        raise ValueError("p は 0〜100 で指定してください")
    xs = sorted(values)
    # 線形補間: 順位 (n-1) * p / 100 の位置の値を、前後の値から内挿する
    rank = (len(xs) - 1) * p / 100
    lo = math.floor(rank)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (rank - lo)


def deployment_frequency(deployments: list[Deployment], start: datetime, end: datetime) -> float:
    if end <= start:
        raise ValueError("end は start より後にしてください")
    count = sum(1 for d in deployments if d.status == "success" and start <= d.deployed_at < end)
    days = (end - start).total_seconds() / 86400
    return count / days


def lead_times_hours(deployments: list[Deployment]) -> list[float]:
    result = []
    for d in deployments:
        if d.status != "success":
            continue  # ロールバックされた変更は「本番で動いている」状態に到達していない
        for c in d.commit_times:
            hours = (d.deployed_at - c).total_seconds() / 3600
            if hours < 0:
                raise ValueError(f"{d.id}: コミットがデプロイより後です")
            result.append(hours)
    return result


def lead_time_summary(deployments: list[Deployment]) -> dict[str, float]:
    hours = lead_times_hours(deployments)
    return {"median": percentile(hours, 50), "p90": percentile(hours, 90)}


# ---------------------------------------------------------------------------
# 演習2: 変更失敗率、復旧時間、パフォーマンスの分類
# ---------------------------------------------------------------------------

def change_failure_rate(deployments: list[Deployment], incidents: list[Incident]) -> float:
    if not deployments:
        raise ValueError("デプロイが 0 件です")
    ids = {d.id for d in deployments}
    failed = {d.id for d in deployments if d.status == "rolled_back"}
    for inc in incidents:
        if inc.deployment_id is None:
            continue  # デプロイと関係のない障害は、変更の失敗に数えない
        if inc.deployment_id not in ids:
            raise ValueError(f"{inc.id}: 未知のデプロイ {inc.deployment_id} を参照しています")
        failed.add(inc.deployment_id)  # 同じデプロイに複数の障害があっても 1 回と数える
    return len(failed) / len(deployments)


def time_to_restore_hours(incidents: list[Incident], deployment_caused_only: bool = False) -> float:
    durations = []
    for inc in incidents:
        if deployment_caused_only and inc.deployment_id is None:
            continue
        hours = (inc.resolved_at - inc.started_at).total_seconds() / 3600
        if hours < 0:
            raise ValueError(f"{inc.id}: 解決が発生より前です")
        durations.append(hours)
    if not durations:
        raise ValueError("対象の障害が 0 件です")
    return percentile(durations, 50)


def classify(
    metrics: dict[str, float],
    thresholds: dict[str, tuple[str, list[tuple[str, float]]]] | None = None,
) -> dict[str, str]:
    table = DEFAULT_THRESHOLDS if thresholds is None else thresholds
    result: dict[str, str] = {}
    for name, value in metrics.items():
        if name not in table:
            raise ValueError(f"しきい値のない指標です: {name}")
        direction, bounds = table[name]
        if direction not in ("higher", "lower"):
            raise ValueError(f"{name}: direction は 'higher' か 'lower'")
        label = "low"
        for cluster, bound in bounds:  # 良いクラスタから順に調べ、最初に満たしたものを採用する
            ok = value >= bound if direction == "higher" else value <= bound
            if ok:
                label = cluster
                break
        result[name] = label
    if result:
        # 全体は最も低い指標に合わせる（簡略化した保守的な見方）
        result["overall"] = max(result.values(), key=CLUSTERS.index)
    return result
