"""10.3 信頼性設計とSLO — 演習（SLO 計算機）の解答例

演習の仕様は exercises/slo_calc.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

MINUTES_PER_30_DAYS = 30 * 24 * 60  # 43,200 分


@dataclass(frozen=True)
class BudgetStatus:
    total: int            # 期間中のリクエスト数
    bad: int              # 失敗（SLO を満たさなかった）リクエスト数
    allowed_bad: float    # エラーバジェット（許される失敗の数）
    consumed: float       # 予算の消費割合（1.0 で使い切り。超えることもある）
    remaining: float      # 1 - consumed


@dataclass(frozen=True)
class AlertRule:
    name: str
    long_window: int      # 分
    short_window: int     # 分
    threshold: float      # バーンレートの閾値（これを「超えたら」発火）
    severity: str = "page"


# ===========================================================================
# 演習1: 可用性の合成
# ===========================================================================

def _check(a: Any) -> float:
    if isinstance(a, bool) or not isinstance(a, (int, float)) or not 0.0 <= a <= 1.0:
        raise ValueError(f"可用性は 0〜1 の数値で指定してください: {a!r}")
    return float(a)


def serial(*availabilities: float) -> float:
    if not availabilities:
        raise ValueError("1 つ以上の可用性を指定してください")
    result = 1.0
    for a in availabilities:
        result *= _check(a)  # すべてが同時に動いている確率（独立を仮定）
    return result


def parallel(*availabilities: float) -> float:
    if not availabilities:
        raise ValueError("1 つ以上の可用性を指定してください")
    all_down = 1.0
    for a in availabilities:
        all_down *= 1.0 - _check(a)  # すべてが同時に止まっている確率
    return 1.0 - all_down


def quorum(k: int, availabilities: Sequence[float]) -> float:
    n = len(availabilities)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= n:
        raise ValueError(f"k は 1〜{n} の整数で指定してください: {k!r}")
    # dist[j] = 「ここまでの部品のうち、ちょうど j 個が動いている確率」を 1 部品ずつ更新する
    dist = [1.0]
    for a in availabilities:
        a = _check(a)
        nxt = [0.0] * (len(dist) + 1)
        for j, p in enumerate(dist):
            nxt[j] += p * (1.0 - a)   # この部品は止まっている
            nxt[j + 1] += p * a       # この部品は動いている
        dist = nxt
    return sum(dist[k:])


def composite(structure: Any) -> float:
    if isinstance(structure, (int, float)) and not isinstance(structure, bool):
        return _check(structure)
    if isinstance(structure, tuple) and structure:
        kind = structure[0]
        if kind == "serial" and len(structure) == 2:
            return serial(*[composite(s) for s in structure[1]])
        if kind == "parallel" and len(structure) == 2:
            return parallel(*[composite(s) for s in structure[1]])
        if kind == "quorum" and len(structure) == 3:
            return quorum(structure[1], [composite(s) for s in structure[2]])
    raise ValueError(f"構造を解釈できません: {structure!r}")


# ===========================================================================
# 演習2: ダウンタイム・エラーバジェット・バーンレート
# ===========================================================================

def allowed_downtime(slo: float, period: timedelta = timedelta(days=30)) -> timedelta:
    return period * (1.0 - _check(slo))


def nines(availability: float) -> float:
    a = _check(availability)
    return math.inf if a == 1.0 else -math.log10(1.0 - a)


def _check_slo(slo: float) -> float:
    if isinstance(slo, bool) or not isinstance(slo, (int, float)) or not 0.0 < slo < 1.0:
        raise ValueError(f"SLO は 0 より大きく 1 未満にしてください（100% ではエラーバジェットがゼロ）: {slo!r}")
    return float(slo)


def _check_counts(good: int, total: int) -> None:
    if total < 0 or not 0 <= good <= total:
        raise ValueError(f"0 <= good <= total を満たしてください: good={good}, total={total}")


def error_budget(slo: float, good: int, total: int) -> BudgetStatus:
    slo = _check_slo(slo)
    _check_counts(good, total)
    bad = total - good
    allowed = (1.0 - slo) * total
    consumed = bad / allowed if total else 0.0
    return BudgetStatus(total, bad, allowed, consumed, 1.0 - consumed)


def burn_rate(bad: int, total: int, slo: float) -> float:
    slo = _check_slo(slo)
    _check_counts(total - bad, total)
    if total == 0:
        return 0.0
    # 「エラー率が、SLO が許すエラー率の何倍か」。1 なら期間のちょうど終わりに予算を使い切る速さ
    return (bad / total) / (1.0 - slo)


def window_sli(series: Sequence[tuple[int, int]], max_error_ratio: float) -> float:
    if not series:
        raise ValueError("series が空です")
    good_minutes = 0
    for good, total in series:
        _check_counts(good, total)
        if total == 0 or (total - good) / total <= max_error_ratio:
            good_minutes += 1
    return good_minutes / len(series)


# ===========================================================================
# 演習3: 多窓・多バーンレートのアラート
# ===========================================================================

def threshold_for(budget_fraction: float, long_window: int, period: int = MINUTES_PER_30_DAYS) -> float:
    # 期間 period の予算の budget_fraction を long_window で使い切る速さ = バーンレート
    return budget_fraction * period / long_window


def multiwindow_rules(period: int = MINUTES_PER_30_DAYS) -> list[AlertRule]:
    # Google の SRE ワークブックが推奨する組み合わせ。短い窓は長い窓の 1/12
    return [
        AlertRule("page-1h", 60, 5, threshold_for(0.02, 60, period), "page"),
        AlertRule("page-6h", 360, 30, threshold_for(0.05, 360, period), "page"),
        AlertRule("ticket-3d", 4320, 360, threshold_for(0.10, 4320, period), "ticket"),
    ]


def evaluate_alerts(
    series: Sequence[tuple[int, int]],
    slo: float,
    rules: Sequence[AlertRule],
) -> dict[str, list[tuple[int, int]]]:
    slo = _check_slo(slo)
    # 累積和を作っておけば、任意の窓の合計が O(1) で求まる（毎分・全窓を数え直すと遅い）
    bad_sum, total_sum = [0], [0]
    for good, total in series:
        _check_counts(good, total)
        bad_sum.append(bad_sum[-1] + total - good)
        total_sum.append(total_sum[-1] + total)

    def burn(t: int, window: int) -> float:
        lo = max(0, t - window + 1)  # 系列の先頭では、ある分だけで計算する
        total = total_sum[t + 1] - total_sum[lo]
        if total == 0:
            return 0.0
        return (bad_sum[t + 1] - bad_sum[lo]) / total / (1.0 - slo)

    result: dict[str, list[tuple[int, int]]] = {}
    for rule in rules:
        if rule.short_window <= 0 or rule.long_window <= 0:
            raise ValueError(f"窓の長さは正の整数にしてください: {rule}")
        intervals: list[tuple[int, int]] = []
        start: int | None = None
        for t in range(len(series)):
            # 長い窓で「本当に予算を削っている」ことを、短い窓で「今も続いている」ことを確かめる
            firing = burn(t, rule.long_window) > rule.threshold and burn(t, rule.short_window) > rule.threshold
            if firing and start is None:
                start = t
            elif not firing and start is not None:
                intervals.append((start, t))
                start = None
        if start is not None:
            intervals.append((start, len(series)))
        result[rule.name] = intervals
    return result
