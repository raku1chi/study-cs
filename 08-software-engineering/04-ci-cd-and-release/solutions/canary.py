"""8.4 CI/CDとリリースエンジニアリング — 解答例: カナリア分析の自動判定

仕様は exercises/canary.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class GroupMetrics:
    requests: int
    errors: int
    latencies_ms: Sequence[float]


@dataclass(frozen=True)
class Verdict:
    decision: str
    reasons: tuple[str, ...]
    baseline_error_rate: Optional[float] = None
    canary_error_rate: Optional[float] = None
    p_value: Optional[float] = None
    baseline_p95: Optional[float] = None
    canary_p95: Optional[float] = None


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("値が 1 つもありません")
    if not 0 < p <= 100:
        raise ValueError(f"p は 0 より大きく 100 以下にしてください: {p}")
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered))  # 1 始まりの順位
    return ordered[rank - 1]


def two_proportion_z_test(
    baseline_errors: int, baseline_requests: int, canary_errors: int, canary_requests: int
) -> tuple[float, float]:
    for errors, requests in ((baseline_errors, baseline_requests), (canary_errors, canary_requests)):
        if requests <= 0 or not 0 <= errors <= requests:
            raise ValueError(f"不正な観測値です: errors={errors}, requests={requests}")
    p_b = baseline_errors / baseline_requests
    p_c = canary_errors / canary_requests
    pooled = (baseline_errors + canary_errors) / (baseline_requests + canary_requests)
    se = math.sqrt(pooled * (1 - pooled) * (1 / baseline_requests + 1 / canary_requests))
    if se == 0:
        return 0.0, 0.5  # 差を判断する材料がない
    z = (p_c - p_b) / se
    return z, 0.5 * math.erfc(z / math.sqrt(2))  # 片側: P(Z >= z)


def _validate(name: str, group: GroupMetrics) -> None:
    if group.requests < 0 or group.errors < 0 or group.errors > group.requests:
        raise ValueError(f"{name}: requests={group.requests}, errors={group.errors} は不正です")
    if any(latency < 0 for latency in group.latencies_ms):
        raise ValueError(f"{name}: 負のレイテンシがあります")


def analyze(
    baseline: GroupMetrics,
    canary: GroupMetrics,
    *,
    min_requests: int = 1000,
    min_latency_samples: int = 200,
    alpha: float = 0.01,
    min_effect: float = 0.001,
    max_p95_ratio: float = 1.2,
) -> Verdict:
    _validate("baseline", baseline)
    _validate("canary", canary)

    # 1. 標本が足りなければ判断しない（少ない標本での判定は、偶然に振り回される）
    shortages = []
    for name, group in (("baseline", baseline), ("canary", canary)):
        if group.requests < min_requests:
            shortages.append(f"{name} のリクエストが {group.requests} 件（{min_requests} 件必要）")
        if len(group.latencies_ms) < min_latency_samples:
            shortages.append(f"{name} のレイテンシの標本が {len(group.latencies_ms)} 個（{min_latency_samples} 個必要）")
    if shortages:
        return Verdict("CONTINUE", tuple(shortages))

    # 2. エラー率: 統計的な有意性と、実務上の効果量の両方を見る
    rate_b = baseline.errors / baseline.requests
    rate_c = canary.errors / canary.requests
    _, p_value = two_proportion_z_test(baseline.errors, baseline.requests, canary.errors, canary.requests)

    # 3. レイテンシ: p95 の比
    p95_b = percentile(baseline.latencies_ms, 95)
    p95_c = percentile(canary.latencies_ms, 95)
    if p95_b > 0:
        ratio = p95_c / p95_b
    else:
        ratio = 1.0 if p95_c == 0 else math.inf

    reasons = []
    if p_value < alpha and rate_c - rate_b >= min_effect:
        reasons.append(
            f"エラー率が悪化: {rate_b:.3%} → {rate_c:.3%}（p = {p_value:.2g} < {alpha}）"
        )
    if ratio > max_p95_ratio:
        reasons.append(f"p95 レイテンシが悪化: {p95_b:g} ms → {p95_c:g} ms（{ratio:.2f} 倍 > {max_p95_ratio}）")
    decision = "ROLLBACK" if reasons else "PROMOTE"
    return Verdict(decision, tuple(reasons), rate_b, rate_c, p_value, p95_b, p95_c)
