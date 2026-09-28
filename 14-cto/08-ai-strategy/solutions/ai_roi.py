"""14.8 AI戦略とAIガバナンス — 解答例: AI機能のROIモデル

演習の仕様は exercises/ai_roi.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace
from typing import Iterable, Mapping

RATE_FIELDS = ("adoption", "accuracy", "review_rate")
TOKENS_PER_UNIT = 1_000_000  # 単価は「100万トークンあたり」


@dataclass(frozen=True)
class AIFeatureModel:
    eligible_requests: float
    adoption: float
    input_tokens: float
    output_tokens: float
    price_in_per_mtok: float
    price_out_per_mtok: float
    accuracy: float
    review_rate: float
    review_minutes: float
    minutes_saved: float
    hourly_cost: float
    calls_per_request: float = 1.0
    revenue_per_success: float = 0.0
    error_cost: float = 0.0
    fixed_monthly: float = 0.0
    build_cost: float = 0.0


@dataclass(frozen=True)
class MonthlyResult:
    handled: float
    model_cost: float
    review_cost: float
    error_cost: float
    fixed_cost: float
    savings: float
    revenue: float

    @property
    def total_cost(self) -> float:
        return self.model_cost + self.review_cost + self.error_cost + self.fixed_cost

    @property
    def total_value(self) -> float:
        return self.savings + self.revenue

    @property
    def net(self) -> float:
        return self.total_value - self.total_cost


_FIELD_NAMES = tuple(f.name for f in fields(AIFeatureModel))


def _validate(m: AIFeatureModel) -> None:
    for name in _FIELD_NAMES:
        value = getattr(m, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{name} は数値で指定してください: {value!r}")
        if value < 0:
            raise ValueError(f"{name} は 0 以上: {value}")
    for name in RATE_FIELDS:
        if getattr(m, name) > 1:
            raise ValueError(f"{name} は 0〜1: {getattr(m, name)}")


def _check_field(name: str) -> None:
    if name not in _FIELD_NAMES:
        raise ValueError(f"未知のパラメータです: {name}")


# ---------------------------------------------------------------------------
# 演習1: 1件あたりのモデル利用料
# ---------------------------------------------------------------------------

def cost_per_request(m: AIFeatureModel) -> float:
    _validate(m)
    per_call = (m.input_tokens * m.price_in_per_mtok + m.output_tokens * m.price_out_per_mtok) / TOKENS_PER_UNIT
    return m.calls_per_request * per_call


# ---------------------------------------------------------------------------
# 演習2: 月次の損益
# ---------------------------------------------------------------------------

def monthly_result(m: AIFeatureModel) -> MonthlyResult:
    _validate(m)
    handled = m.eligible_requests * m.adoption
    correct = handled * m.accuracy
    # レビューされなかった誤りだけが顧客に届く（レビューは誤りを必ず見つける、と単純化）
    escaped = handled * (1 - m.accuracy) * (1 - m.review_rate)
    per_minute = m.hourly_cost / 60
    return MonthlyResult(
        handled=handled,
        model_cost=handled * cost_per_request(m),
        review_cost=handled * m.review_rate * m.review_minutes * per_minute,
        error_cost=escaped * m.error_cost,
        fixed_cost=m.fixed_monthly,
        # 誤った結果（レビューで見つかったものも含む）からは節約も収益も生まれない
        savings=correct * m.minutes_saved * per_minute,
        revenue=correct * m.revenue_per_success,
    )


def run_scenarios(base: AIFeatureModel, scenarios: Mapping[str, Mapping[str, float]]) -> dict[str, MonthlyResult]:
    results: dict[str, MonthlyResult] = {}
    for name, overrides in scenarios.items():
        for key in overrides:
            _check_field(key)
        results[name] = monthly_result(replace(base, **overrides))
    return results


# ---------------------------------------------------------------------------
# 演習3: 損益分岐点と回収期間
# ---------------------------------------------------------------------------

def _net_with(m: AIFeatureModel, field: str, value: float) -> float:
    return monthly_result(replace(m, **{field: value})).net


def break_even(m: AIFeatureModel, field: str, lo: float, hi: float, tol: float = 1e-9) -> float | None:
    _check_field(field)
    if not lo < hi:
        raise ValueError(f"lo < hi である必要があります: lo={lo}, hi={hi}")
    if tol <= 0:
        raise ValueError(f"tol は正の数: {tol}")
    f_lo, f_hi = _net_with(m, field, lo), _net_with(m, field, hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        return None  # 範囲内で符号が変わらない = この範囲には損益分岐点がない
    # 二分法: 符号が変わる区間を半分ずつ狭めていく（net はこのパラメータについて単調と仮定）
    while hi - lo > tol:
        mid = (lo + hi) / 2
        f_mid = _net_with(m, field, mid)
        if f_mid == 0:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def payback_month(m: AIFeatureModel, horizon_months: int, ramp_months: int = 0) -> int | None:
    if horizon_months <= 0:
        raise ValueError(f"horizon_months は 1 以上: {horizon_months}")
    if ramp_months < 0:
        raise ValueError(f"ramp_months は 0 以上: {ramp_months}")
    _validate(m)
    cumulative = -m.build_cost
    for t in range(1, horizon_months + 1):
        # 利用率は ramp_months かけて目標値まで直線的に立ち上がる
        ramp = 1.0 if ramp_months == 0 else min(1.0, t / ramp_months)
        cumulative += monthly_result(replace(m, adoption=m.adoption * ramp)).net
        if cumulative >= 0:
            return t
    return None


# ---------------------------------------------------------------------------
# 演習4: 感度分析（トルネード図のデータ）
# ---------------------------------------------------------------------------

def sensitivity(m: AIFeatureModel, field_names: Iterable[str], delta: float = 0.2) -> list[tuple[str, float, float]]:
    if not 0 < delta < 1:
        raise ValueError(f"delta は 0 より大きく 1 未満: {delta}")
    rows: list[tuple[str, float, float]] = []
    for name in field_names:
        _check_field(name)
        value = getattr(m, name)
        low, high = value * (1 - delta), value * (1 + delta)
        if name in RATE_FIELDS:
            # 割合は 1 を超えられない（精度 0.85 の +20% は 1.0 で頭打ち）
            low, high = min(low, 1.0), min(high, 1.0)
        rows.append((name, _net_with(m, name, low), _net_with(m, name, high)))
    # 振れ幅の大きい順。同じならパラメータ名の順
    rows.sort(key=lambda r: (-abs(r[2] - r[1]), r[0]))
    return rows
