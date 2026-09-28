"""14.3 事業と財務のリテラシー — 解答例（budget_model.py）

採用計画から、フルロードコスト（給与 + 法定福利費 + 福利厚生等 + 一時費用）で月次の費用を
積み上げ、月次バーン・ランウェイ・採用が遅れた場合の感度を計算します。
演習の仕様は exercises/budget_model.py の docstring を参照してください。
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Hire:
    role: str
    annual_salary: float          # 年収（賞与込み）。単位は万円など任意
    start_month: int              # 入社月（1 = 計画の初月。0 以下は計画開始時点で在籍）
    agency_fee_rate: float = 0.0  # 人材紹介手数料率（年収に対する比率。直接採用なら 0）


@dataclass(frozen=True)
class Assumptions:
    statutory_welfare_rate: float = 0.16  # 法定福利費率（会社負担の社会保険料等）
    benefits_monthly: float = 3.0         # 1 人あたり月額の福利厚生・ツール・研修など
    equipment_one_time: float = 40.0      # 入社月の一時費用（PC など）


def steady_monthly_cost(annual_salary: float, assumptions: Assumptions) -> float:
    if annual_salary < 0:
        raise ValueError("年収が負です")
    # 月給に法定福利費を上乗せし、1 人あたりの月額費用を足す
    monthly_salary = annual_salary / 12
    return monthly_salary * (1 + assumptions.statutory_welfare_rate) + assumptions.benefits_monthly


def hire_cost_in_month(hire: Hire, month: int, assumptions: Assumptions) -> float:
    if month < 1:
        raise ValueError(f"month は 1 以上です: {month}")
    if month < hire.start_month:
        return 0.0
    cost = steady_monthly_cost(hire.annual_salary, assumptions)
    if month == hire.start_month:
        # 入社月だけ、機器などの一時費用と人材紹介手数料がかかる
        cost += assumptions.equipment_one_time + hire.agency_fee_rate * hire.annual_salary
    return cost


def _series(value: float | Sequence[float], months: int, name: str) -> list[float]:
    if isinstance(value, (int, float)):
        return [float(value)] * months
    values = [float(v) for v in value]
    if len(values) != months:
        raise ValueError(f"{name} の長さ（{len(values)}）が months（{months}）と一致しません")
    return values


def monthly_burn(
    hires: Sequence[Hire],
    months: int,
    assumptions: Assumptions,
    other_costs: float | Sequence[float] = 0.0,
    revenue: float | Sequence[float] = 0.0,
) -> list[float]:
    if months < 1:
        raise ValueError(f"months は 1 以上です: {months}")
    other = _series(other_costs, months, "other_costs")
    income = _series(revenue, months, "revenue")
    burns = []
    for m in range(1, months + 1):
        people = sum(hire_cost_in_month(h, m, assumptions) for h in hires)
        # 純バーン = 出ていくお金 − 入ってくるお金（正ならキャッシュが減る）
        burns.append(people + other[m - 1] - income[m - 1])
    return burns


def projected_runway(opening_cash: float, burns: Sequence[float]) -> int | None:
    if opening_cash < 0:
        raise ValueError("期首の現金が負です")
    cash = opening_cash
    for i, burn in enumerate(burns):
        cash -= burn
        if cash < 0:
            return i  # 1〜i か月目までは資金が足りた
    return None  # 計画期間内には尽きない


def simple_runway(cash: float, net_burn: float) -> float:
    if cash < 0:
        raise ValueError("現金が負です")
    if net_burn <= 0:
        return math.inf  # キャッシュが減っていない
    return cash / net_burn


def delay_sensitivity(
    opening_cash: float,
    hires: Sequence[Hire],
    months: int,
    assumptions: Assumptions,
    other_costs: float | Sequence[float] = 0.0,
    revenue: float | Sequence[float] = 0.0,
    delays: Sequence[int] = (0, 1, 2, 3),
) -> dict[int, int | None]:
    result: dict[int, int | None] = {}
    for d in delays:
        if d < 0:
            raise ValueError(f"遅れは 0 以上です: {d}")
        # 計画期間中に入社する人だけを遅らせる（在籍者はそのまま）
        shifted = [
            dataclasses.replace(h, start_month=h.start_month + d) if h.start_month >= 1 else h
            for h in hires
        ]
        burns = monthly_burn(shifted, months, assumptions, other_costs, revenue)
        result[d] = projected_runway(opening_cash, burns)
    return result


if __name__ == "__main__":
    # 本文 6.3 節の例（単位: 万円）
    a = Assumptions(statutory_welfare_rate=0.16, benefits_monthly=3.0, equipment_one_time=40.0)
    team = [Hire(f"在籍エンジニア{i}", 800, 0) for i in range(1, 11)]
    plan = [
        Hire("バックエンド", 900, 2, 0.35),
        Hire("フロントエンド", 850, 2, 0.35),
        Hire("SRE", 1000, 3, 0.35),
        Hire("エンジニアリングマネージャー", 1200, 4, 0.35),
        Hire("バックエンド", 900, 5),
        Hire("データエンジニア", 950, 6, 0.35),
        Hire("バックエンド", 900, 7),
        Hire("QA", 750, 9),
    ]
    hires = team + plan
    months = 36
    cash = 30000.0                                        # 期首の現金 3 億円
    other = 1200.0                                        # エンジニア以外の月額費用
    revenue = [500 * 1.03 ** m for m in range(months)]    # 月 500 万円から月 3% で伸びる売上
    burns = monthly_burn(hires, months, a, other, revenue)
    print(f"1 人あたり定常月額（年収 800 万円）: {steady_monthly_cost(800, a):.1f} 万円")
    print("月次純バーン（1〜12 か月目）:", [round(b) for b in burns[:12]])
    print(f"今月の純バーンでの単純ランウェイ: {simple_runway(cash, burns[0]):.1f} か月")
    print(f"採用計画を織り込んだランウェイ  : {projected_runway(cash, burns)} か月")
    print("採用が d か月遅れた場合のランウェイ:", delay_sensitivity(cash, hires, months, a, other, revenue))
