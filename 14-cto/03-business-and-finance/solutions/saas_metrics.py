"""14.3 事業と財務のリテラシー — 解答例（saas_metrics.py）

月末時点の顧客ごとの MRR（スナップショット）から、MRR の増減分解・NRR/GRR・
ロゴリテンションを計算し、CAC・LTV・Rule of 40・バーンマルチプルといった
効率の指標を求めます。演習の仕様は exercises/saas_metrics.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

Snapshot = Mapping[str, float]  # 顧客 ID → その月末の MRR


@dataclass(frozen=True)
class MrrMovement:
    """snapshots[period - 1] から snapshots[period] への MRR の増減。"""

    period: int
    starting: float
    new: float
    expansion: float
    reactivation: float
    contraction: float
    churned: float
    ending: float

    @property
    def net_new(self) -> float:
        return self.new + self.expansion + self.reactivation - self.contraction - self.churned


# ---------------------------------------------------------------------------
# 演習2: MRR の増減分解とリテンション
# ---------------------------------------------------------------------------

def _validate(snapshots: Sequence[Snapshot]) -> None:
    for i, snap in enumerate(snapshots):
        for customer, mrr in snap.items():
            if mrr < 0:
                raise ValueError(f"MRR が負です: snapshots[{i}][{customer!r}] = {mrr}")


def mrr_movements(snapshots: Sequence[Snapshot]) -> list[MrrMovement]:
    _validate(snapshots)
    if not snapshots:
        return []
    # 「過去に一度でも課金していた顧客」を覚えておくと、新規と再開を区別できる
    ever_active = {c for c, m in snapshots[0].items() if m > 0}
    result: list[MrrMovement] = []
    for period in range(1, len(snapshots)):
        prev, curr = snapshots[period - 1], snapshots[period]
        new = expansion = reactivation = contraction = churned = 0.0
        for customer in sorted(set(prev) | set(curr)):  # 順序を固定して結果を決定的にする
            before = prev.get(customer, 0.0)
            after = curr.get(customer, 0.0)
            if before > 0 and after > 0:
                if after > before:
                    expansion += after - before
                elif after < before:
                    contraction += before - after
            elif before > 0:  # after == 0
                churned += before
            elif after > 0:  # before == 0
                if customer in ever_active:
                    reactivation += after
                else:
                    new += after
        ever_active |= {c for c, m in curr.items() if m > 0}
        result.append(
            MrrMovement(
                period=period,
                starting=sum(prev.values()),
                new=new,
                expansion=expansion,
                reactivation=reactivation,
                contraction=contraction,
                churned=churned,
                ending=sum(curr.values()),
            )
        )
    return result


def _cohort(snapshots: Sequence[Snapshot], start: int, end: int) -> dict[str, float]:
    if not 0 <= start < end < len(snapshots):
        raise ValueError(f"0 <= start < end < {len(snapshots)} である必要があります: start={start}, end={end}")
    _validate(snapshots)
    cohort = {c: m for c, m in snapshots[start].items() if m > 0}
    if not cohort:
        raise ValueError(f"start={start} の時点で課金している顧客がいません")
    return cohort


def net_revenue_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    cohort = _cohort(snapshots, start, end)
    # 新規顧客は含めない。コホートの顧客の end 時点の MRR（拡大も縮小も含む）で比べる
    return sum(snapshots[end].get(c, 0.0) for c in cohort) / sum(cohort.values())


def gross_revenue_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    cohort = _cohort(snapshots, start, end)
    # 拡大分は数えない: 各顧客の end 時点の MRR を、start 時点の MRR で頭打ちにする
    kept = sum(min(snapshots[end].get(c, 0.0), m) for c, m in cohort.items())
    return kept / sum(cohort.values())


def logo_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    cohort = _cohort(snapshots, start, end)
    # 金額ではなく「社数」で数える。end 時点で課金していれば残存とみなす
    alive = sum(1 for c in cohort if snapshots[end].get(c, 0.0) > 0)
    return alive / len(cohort)


# ---------------------------------------------------------------------------
# 演習3: ユニットエコノミクスと効率の指標
# ---------------------------------------------------------------------------

def cac(sales_marketing_cost: float, new_customers: int) -> float:
    if sales_marketing_cost < 0:
        raise ValueError("営業・マーケティング費用が負です")
    if new_customers <= 0:
        raise ValueError("新規顧客数は 1 以上にしてください")
    return sales_marketing_cost / new_customers


def cac_payback_months(cac_value: float, arpa_monthly: float, gross_margin: float) -> float:
    if cac_value < 0:
        raise ValueError("CAC が負です")
    if arpa_monthly <= 0:
        raise ValueError("ARPA は正の値にしてください")
    if not 0 < gross_margin <= 1:
        raise ValueError("粗利率は 0 より大きく 1 以下にしてください")
    # 1 か月に回収できるのは売上ではなく「粗利」
    return cac_value / (arpa_monthly * gross_margin)


def ltv(arpa_monthly: float, gross_margin: float, monthly_churn: float) -> float:
    if arpa_monthly < 0:
        raise ValueError("ARPA が負です")
    if not 0 <= gross_margin <= 1:
        raise ValueError("粗利率は 0〜1 にしてください")
    if not 0 < monthly_churn <= 1:
        raise ValueError("月次解約率は 0 より大きく 1 以下にしてください")
    # 解約率が一定なら平均継続期間は 1 / 解約率（か月）
    return arpa_monthly * gross_margin / monthly_churn


def annual_churn_from_monthly(monthly_churn: float) -> float:
    if not 0 <= monthly_churn <= 1:
        raise ValueError("月次解約率は 0〜1 にしてください")
    # 12 倍ではない。毎月「残った顧客」のうちの一定割合が解約する（複利で効く）
    return 1 - (1 - monthly_churn) ** 12


def rule_of_40(revenue_growth: float, profit_margin: float) -> float:
    return revenue_growth + profit_margin


def burn_multiple(net_burn: float, net_new_arr: float) -> float:
    if net_new_arr <= 0:
        raise ValueError("純新規 ARR が 0 以下のときバーンマルチプルは定義できません")
    return net_burn / net_new_arr


if __name__ == "__main__":
    # 本文 4 節の例（単位: 万円/月）
    snapshots = [
        {"A": 100, "B": 50, "C": 30},
        {"A": 120, "B": 50, "C": 30, "D": 40},
        {"A": 120, "B": 35, "D": 40, "E": 60},
        {"A": 150, "B": 35, "C": 30, "D": 40, "E": 60},
    ]
    print("月  期首  新規  拡大  再開  縮小  解約  期末  純増")
    for m in mrr_movements(snapshots):
        print(f"{m.period:>2} {m.starting:5.0f} {m.new:5.0f} {m.expansion:5.0f} {m.reactivation:5.0f}"
              f" {m.contraction:5.0f} {m.churned:5.0f} {m.ending:5.0f} {m.net_new:5.0f}")
    print(f"NRR（0→3）: {net_revenue_retention(snapshots, 0, 3):.1%}")
    print(f"GRR（0→3）: {gross_revenue_retention(snapshots, 0, 3):.1%}")
    print(f"ロゴリテンション（0→3）: {logo_retention(snapshots, 0, 3):.1%}")
