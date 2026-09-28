"""14.3 事業と財務のリテラシー — 解答例（npv.py）

技術投資（例: クラウド費用を削減する移行プロジェクト）を、NPV・IRR・回収期間で評価します。
演習の仕様は exercises/npv.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import Sequence


def npv(rate: float, cashflows: Sequence[float]) -> float:
    if rate <= -1:
        raise ValueError(f"割引率は -1 より大きくしてください: {rate}")
    if not cashflows:
        raise ValueError("キャッシュフローが空です")
    # cashflows[t] は t 期末のキャッシュフロー。t = 0 は「今」なので割り引かない
    return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))


def irr(
    cashflows: Sequence[float],
    lo: float = -0.99,
    hi: float = 10.0,
    tol: float = 1e-10,
    max_iter: int = 500,
) -> float:
    if len(cashflows) < 2:
        raise ValueError("キャッシュフローは 2 期以上必要です")
    if not (any(cf < 0 for cf in cashflows) and any(cf > 0 for cf in cashflows)):
        raise ValueError("正と負のキャッシュフローが両方ないと IRR は定まりません")
    f_lo, f_hi = npv(lo, cashflows), npv(hi, cashflows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError(f"[{lo}, {hi}] の範囲で NPV の符号が変わりません")
    # 二分法: NPV(rate) は連続なので、符号が変わる区間を半分ずつ狭めれば根に近づく
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = npv(mid, cashflows)
        if f_mid == 0 or (hi - lo) / 2 < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def payback_period(cashflows: Sequence[float]) -> float | None:
    if not cashflows:
        raise ValueError("キャッシュフローが空です")
    cumulative = cashflows[0]
    if cumulative >= 0:
        return 0.0
    for t in range(1, len(cashflows)):
        before = cumulative
        cumulative += cashflows[t]
        if cumulative >= 0:
            # t 期のキャッシュフローが期中に均等に入ると仮定して、0 を超える時点を補間する。
            # before < 0 <= cumulative なので cashflows[t] > 0 が保証されている
            return (t - 1) + (-before) / cashflows[t]
    return None


def discounted_payback_period(rate: float, cashflows: Sequence[float]) -> float | None:
    # 各期のキャッシュフローを現在価値に直してから、同じ方法で回収時点を求める
    if rate <= -1:
        raise ValueError(f"割引率は -1 より大きくしてください: {rate}")
    discounted = [cf / (1 + rate) ** t for t, cf in enumerate(cashflows)]
    return payback_period(discounted)


if __name__ == "__main__":
    # 本文 7.1 節の例: 3,000 万円の移行で、クラウド費用が年 1,200 万円下がる（5 年間）
    flows = [-3000, 1200, 1200, 1200, 1200, 1200]
    print(f"NPV（割引率 8%）   : {npv(0.08, flows):,.1f} 万円")
    print(f"IRR                : {irr(flows):.2%}")
    print(f"回収期間           : {payback_period(flows):.2f} 年")
    print(f"割引回収期間（8%） : {discounted_payback_period(0.08, flows):.2f} 年")
