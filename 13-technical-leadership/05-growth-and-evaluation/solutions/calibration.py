"""13.5 育成・評価・キャリアラダー — 解答例: 評価のキャリブレーション（評価者による偏りの検出）

演習の仕様は exercises/calibration.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Rating:
    employee: str
    manager: str
    score: float


@dataclass(frozen=True)
class ManagerStats:
    n: int
    mean: float
    sd: float


def _mean_sd(values: list[float]) -> tuple[float, float]:
    """平均と母標準偏差（n で割る）を返す。"""
    n = len(values)
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(var)


def _by_manager(ratings: list[Rating]) -> dict[str, list[float]]:
    if not ratings:
        raise ValueError("評価が 0 件です")
    seen: set[str] = set()
    groups: dict[str, list[float]] = {}
    for r in ratings:
        if r.employee in seen:
            raise ValueError(f"同じ社員の評価が重複しています: {r.employee}")
        seen.add(r.employee)
        groups.setdefault(r.manager, []).append(r.score)
    return groups


# ---------------------------------------------------------------------------
# 演習1: 評価者ごとの統計と分布の比較
# ---------------------------------------------------------------------------

def manager_stats(ratings: list[Rating]) -> dict[str, ManagerStats]:
    groups = _by_manager(ratings)
    result = {}
    for manager in sorted(groups):
        mean, sd = _mean_sd(groups[manager])
        result[manager] = ManagerStats(len(groups[manager]), mean, sd)
    return result


def distribution_distance(ratings: list[Rating], scale: list[float]) -> dict[str, float]:
    groups = _by_manager(ratings)
    if len(groups) < 2:
        raise ValueError("比較には評価者が 2 人以上必要です")
    allowed = set(scale)
    for r in ratings:
        if r.score not in allowed:
            raise ValueError(f"尺度にない評価です: {r.score}")

    def dist(values: list[float]) -> dict[float, float]:
        return {k: sum(1 for v in values if v == k) / len(values) for k in scale}

    result = {}
    for manager in sorted(groups):
        rest = [s for m, vs in groups.items() if m != manager for s in vs]
        p, q = dist(groups[manager]), dist(rest)
        # 全変動距離: 2 つの分布の「ずれ」を 0（同じ）〜1（まったく重ならない）で表す
        result[manager] = 0.5 * sum(abs(p[k] - q[k]) for k in scale)
    return result


# ---------------------------------------------------------------------------
# 演習2: 寛大化・厳格化の検出
# ---------------------------------------------------------------------------

def leniency_flags(ratings: list[Rating], z_threshold: float = 2.0) -> dict[str, tuple[float, str]]:
    if z_threshold <= 0:
        raise ValueError("z_threshold は正の値にしてください")
    groups = _by_manager(ratings)
    if len(groups) < 2:
        raise ValueError("比較には評価者が 2 人以上必要です")
    result = {}
    for manager in sorted(groups):
        own = groups[manager]
        rest = [s for m, vs in groups.items() if m != manager for s in vs]
        own_mean = sum(own) / len(own)
        rest_mean, rest_sd = _mean_sd(rest)
        diff = own_mean - rest_mean
        if rest_sd == 0:
            z = 0.0 if diff == 0 else math.copysign(math.inf, diff)
        else:
            # 「他の評価者の分布から n 人を無作為に選んだら、平均はこれくらい揺れる」という
            # 標準誤差 sd / sqrt(n) で差を割る。小さなチームの平均は揺れやすいことを考慮できる
            z = diff / (rest_sd / math.sqrt(len(own)))
        if z >= z_threshold:
            label = "lenient"
        elif z <= -z_threshold:
            label = "severe"
        else:
            label = "ok"
        result[manager] = (z, label)
    return result


# ---------------------------------------------------------------------------
# 演習2（続き）: 評価者ごとの標準化と、その影響
# ---------------------------------------------------------------------------

def normalize_within_manager(ratings: list[Rating]) -> dict[str, float]:
    groups = _by_manager(ratings)
    overall_mean, overall_sd = _mean_sd([r.score for r in ratings])
    stats = {m: _mean_sd(vs) for m, vs in groups.items()}
    result = {}
    for r in ratings:
        mean, sd = stats[r.manager]
        # 評価者の中での相対的な位置（z スコア）を、全体の平均と標準偏差の尺度に戻す
        z = 0.0 if sd == 0 else (r.score - mean) / sd
        result[r.employee] = overall_mean + z * overall_sd
    return result


def _ranks(scores: dict[str, float]) -> dict[str, int]:
    order = sorted(scores, key=lambda e: (-scores[e], e))
    return {e: i + 1 for i, e in enumerate(order)}


def rank_changes(ratings: list[Rating]) -> dict[str, tuple[int, int]]:
    normalized = normalize_within_manager(ratings)
    original = {r.employee: r.score for r in ratings}
    before, after = _ranks(original), _ranks(normalized)
    return {e: (before[e], after[e]) for e in sorted(original)}
