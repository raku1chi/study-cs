"""12.5 AIシステムの本番運用 — 演習1: データドリフトの検出（解答例）

演習の仕様は exercises/drift.py の docstring を参照してください。
"""
from __future__ import annotations

import bisect
import math
from collections import Counter
from dataclasses import dataclass
from typing import Hashable, Sequence

# ---------------------------------------------------------------------------
# 実装済み: p 値の計算（数値計算の部品）
# ---------------------------------------------------------------------------


def _lower_gamma_series(a: float, x: float) -> float:
    """正則化された下側不完全ガンマ関数 P(a, x) を級数で求める（x < a + 1 で速く収束する）。"""
    term = total = 1.0 / a
    ap = a
    for _ in range(10_000):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _upper_gamma_cf(a: float, x: float) -> float:
    """正則化された上側不完全ガンマ関数 Q(a, x) を連分数（Lentz 法）で求める（x >= a + 1 用）。"""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x: float, dof: int) -> float:
    if dof < 1:
        raise ValueError("自由度は 1 以上")
    if x <= 0:
        return 1.0
    a, y = dof / 2.0, x / 2.0
    if y < a + 1.0:
        return max(0.0, 1.0 - _lower_gamma_series(a, y))
    return min(1.0, _upper_gamma_cf(a, y))


def ks_p_value(d: float, n1: int, n2: int) -> float:
    if n1 < 1 or n2 < 1:
        raise ValueError("標本の大きさは 1 以上")
    en = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d
    total = 0.0
    sign = 1.0
    for j in range(1, 101):
        term = sign * 2.0 * math.exp(-2.0 * j * j * lam * lam)
        total += term
        if abs(term) <= 1e-10 * abs(total) or abs(term) < 1e-300:
            return min(1.0, max(0.0, total))
        sign = -sign
    return 1.0  # λ が小さく級数が収束しない = 分布の差はほぼない


# ---------------------------------------------------------------------------
# 演習1a: PSI（Population Stability Index）
# ---------------------------------------------------------------------------

def quantile_edges(reference: Sequence[float], n_bins: int = 10) -> list[float]:
    if n_bins < 2:
        raise ValueError("n_bins は 2 以上")
    if not reference:
        raise ValueError("基準データが空です")
    ordered = sorted(reference)
    n = len(ordered)
    edges: list[float] = []
    for i in range(1, n_bins):
        edge = ordered[(i * n) // n_bins]
        if not edges or edge > edges[-1]:  # 同じ値が多いと境界が重なるので除く
            edges.append(edge)
    return edges


def bin_proportions(values: Sequence[float], edges: Sequence[float]) -> list[float]:
    if not values:
        raise ValueError("データが空です")
    counts = [0] * (len(edges) + 1)
    for v in values:
        # bisect_left: v <= edges[0] なら 0 番、edges[i-1] < v <= edges[i] なら i 番、最後の境界より大きければ末尾
        counts[bisect.bisect_left(edges, v)] += 1
    return [c / len(values) for c in counts]


def psi_from_proportions(expected: Sequence[float], actual: Sequence[float], eps: float = 1e-4) -> float:
    if len(expected) != len(actual) or not expected:
        raise ValueError("ビンの数が違うか、空です")
    total = 0.0
    for e, a in zip(expected, actual):
        # 割合 0 のビンがあると log(0) になるので、ごく小さな値で置き換える
        e, a = max(e, eps), max(a, eps)
        total += (a - e) * math.log(a / e)
    return total


def psi(reference: Sequence[float], current: Sequence[float], *, n_bins: int = 10, eps: float = 1e-4) -> float:
    edges = quantile_edges(reference, n_bins)  # ビンは基準データで決め、現在のデータにも同じビンを使う
    return psi_from_proportions(bin_proportions(reference, edges), bin_proportions(current, edges), eps)


def categorical_psi(reference_counts: dict[Hashable, int], current_counts: dict[Hashable, int], *, eps: float = 1e-4) -> float:
    categories = sorted(set(reference_counts) | set(current_counts), key=str)
    ref_total = sum(reference_counts.values())
    cur_total = sum(current_counts.values())
    if ref_total <= 0 or cur_total <= 0:
        raise ValueError("件数が 0 です")
    expected = [reference_counts.get(c, 0) / ref_total for c in categories]
    actual = [current_counts.get(c, 0) / cur_total for c in categories]
    return psi_from_proportions(expected, actual, eps)


# ---------------------------------------------------------------------------
# 演習1b: 2 標本 KS 統計量とカイ二乗検定
# ---------------------------------------------------------------------------

def ks_statistic(reference: Sequence[float], current: Sequence[float]) -> float:
    if not reference or not current:
        raise ValueError("データが空です")
    a, b = sorted(reference), sorted(current)
    n1, n2 = len(a), len(b)
    i = j = 0
    d = 0.0
    while i < n1 and j < n2:
        v = min(a[i], b[j])
        # 同じ値はまとめて進める（同点の途中で差を測ると、実際より大きな値になる）
        while i < n1 and a[i] == v:
            i += 1
        while j < n2 and b[j] == v:
            j += 1
        d = max(d, abs(i / n1 - j / n2))
    return d


def chi_square_drift(reference_counts: dict[Hashable, int], current_counts: dict[Hashable, int]) -> tuple[float, int, float]:
    ref_total = sum(reference_counts.values())
    cur_total = sum(current_counts.values())
    if ref_total <= 0 or cur_total <= 0:
        raise ValueError("件数が 0 です")
    categories = [c for c in sorted(set(reference_counts) | set(current_counts), key=str)
                  if reference_counts.get(c, 0) + current_counts.get(c, 0) > 0]
    if len(categories) < 2:
        return 0.0, 0, 1.0
    n = ref_total + cur_total
    stat = 0.0
    # 2 × k の分割表で「基準と現在は同じ分布から来ている」という帰無仮説を検定する（独立性の検定）
    for c in categories:
        col = reference_counts.get(c, 0) + current_counts.get(c, 0)
        for observed, row_total in ((reference_counts.get(c, 0), ref_total), (current_counts.get(c, 0), cur_total)):
            expected = row_total * col / n
            stat += (observed - expected) ** 2 / expected
    dof = len(categories) - 1
    return stat, dof, chi2_sf(stat, dof)


# ---------------------------------------------------------------------------
# 演習1c: 特徴量ごとの判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftThresholds:
    psi_warn: float = 0.1
    psi_alert: float = 0.25
    p_value: float = 0.01
    missing_rate_increase: float = 0.05


@dataclass(frozen=True)
class FeatureDrift:
    feature: str
    kind: str
    psi: float
    statistic: float
    p_value: float
    missing_rate_reference: float
    missing_rate_current: float
    status: str
    reasons: tuple[str, ...] = ()



def evaluate_drift(
    reference: dict[str, Sequence],
    current: dict[str, Sequence],
    *,
    categorical: frozenset[str] | set[str] = frozenset(),
    n_bins: int = 10,
    thresholds: DriftThresholds = DriftThresholds(),
) -> list[FeatureDrift]:
    results: list[FeatureDrift] = []
    for feature in sorted(reference):
        if feature not in current:
            raise ValueError(f"現在のデータに特徴量 {feature!r} がありません")
        ref_all, cur_all = list(reference[feature]), list(current[feature])
        if not ref_all or not cur_all:
            raise ValueError(f"{feature}: データが空です")
        ref = [v for v in ref_all if v is not None]
        cur = [v for v in cur_all if v is not None]
        if not ref:
            raise ValueError(f"{feature}: 基準データがすべて欠損しています")
        miss_ref = 1 - len(ref) / len(ref_all)
        miss_cur = 1 - len(cur) / len(cur_all)
        kind = "categorical" if feature in categorical else "numeric"
        status, reasons = "ok", []
        if not cur:
            results.append(FeatureDrift(feature, kind, math.inf, math.inf, 0.0, miss_ref, miss_cur, "alert",
                                        ("現在のデータに値がありません（すべて欠損）",)))
            continue
        if kind == "categorical":
            ref_counts, cur_counts = Counter(ref), Counter(cur)
            value = categorical_psi(ref_counts, cur_counts)
            statistic, _, p = chi_square_drift(ref_counts, cur_counts)
        else:
            value = psi(ref, cur, n_bins=n_bins)
            statistic = ks_statistic(ref, cur)
            p = ks_p_value(statistic, len(ref), len(cur))
        # 効果の大きさ（PSI）と統計的な有意さ（p 値）の両方を満たしたときだけ警告する。
        # 小さな標本では PSI が偶然大きくなり、大きな標本では無意味に小さな差でも p 値が小さくなるため
        if p < thresholds.p_value and value >= thresholds.psi_alert:
            status = "alert"
            reasons.append(f"PSI={value:.3f} ≥ {thresholds.psi_alert}（p={p:.2g}）")
        elif p < thresholds.p_value and value >= thresholds.psi_warn:
            status = "warn"
            reasons.append(f"PSI={value:.3f} ≥ {thresholds.psi_warn}（p={p:.2g}）")
        if miss_cur - miss_ref > thresholds.missing_rate_increase:
            status = "alert"  # 欠損の急増は、上流のパイプラインの障害であることが多い
            reasons.append(f"欠損率が {miss_ref:.1%} → {miss_cur:.1%} に増加")
        results.append(FeatureDrift(feature, kind, value, statistic, p, miss_ref, miss_cur, status, tuple(reasons)))
    return results
