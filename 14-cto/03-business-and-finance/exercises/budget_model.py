"""14.3 事業と財務のリテラシー — 演習4（budget_model.py）

採用計画から、フルロードコスト（給与 + 法定福利費 + 福利厚生等 + 入社時の一時費用）で
月次の費用を積み上げ、月次バーン・ランウェイ・採用が遅れた場合の感度を計算します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.3
    python3 -m unittest -v test_budget_model   # このディレクトリで直接

モデルの前提（簡略化しています。本文 6 節を参照）:
    - 月は 1 始まり（1 = 計画の初月）。
    - 給与は年収 ÷ 12 を毎月支払う（賞与の支給月の偏りは無視する）。
    - 法定福利費は給与に一定率を掛けて概算する（実際には保険料の算定基礎に上限などがある）。
    - 入社月にだけ、機器などの一時費用と人材紹介手数料がかかる。
    - 退職・昇給・採用の失敗（見送り）は考えない。
    - 金額の単位は任意（本文では万円）。
"""
from __future__ import annotations

import dataclasses  # noqa: F401  delay_sensitivity で dataclasses.replace が使えます
import math  # noqa: F401  simple_runway で math.inf が使えます
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Hire:
    """1 人分の採用（または在籍者）。この型は完成しています。"""

    role: str
    annual_salary: float          # 年収（賞与込み）
    start_month: int              # 入社月（1 = 計画の初月。0 以下は計画開始時点で在籍）
    agency_fee_rate: float = 0.0  # 人材紹介手数料率（年収に対する比率。直接採用なら 0）


@dataclass(frozen=True)
class Assumptions:
    """1 人あたりのコストの前提。この型は完成しています。"""

    statutory_welfare_rate: float = 0.16  # 法定福利費率（会社負担の社会保険料等。給与に対する比率）
    benefits_monthly: float = 3.0         # 1 人あたり月額の福利厚生・ツール・研修など
    equipment_one_time: float = 40.0      # 入社月の一時費用（PC など）


def steady_monthly_cost(annual_salary: float, assumptions: Assumptions) -> float:
    """定常月（入社月以外）の 1 人あたり費用を返す。

    = 年収 / 12 × (1 + 法定福利費率) + 1 人あたり月額の福利厚生等

    annual_salary < 0 なら ValueError。

    >>> steady_monthly_cost(1200, Assumptions(statutory_welfare_rate=0.25, benefits_monthly=5))
    130.0
    >>> round(steady_monthly_cost(800, Assumptions()), 2)   # 800/12 × 1.16 + 3
    80.33
    """
    raise NotImplementedError("演習4: steady_monthly_cost を実装してください")


def hire_cost_in_month(hire: Hire, month: int, assumptions: Assumptions) -> float:
    """month（1 始まり）に hire にかかる費用を返す。

    - month < hire.start_month（入社前）: 0
    - month == hire.start_month（入社月）: 定常月の費用 + 一時費用 + 年収 × 紹介手数料率
    - month > hire.start_month: 定常月の費用
    - start_month が 0 以下（計画開始時点で在籍）の人は、1 か月目から定常月の費用だけがかかる。
    - month < 1 なら ValueError。
    """
    raise NotImplementedError("演習4: hire_cost_in_month を実装してください")


def monthly_burn(
    hires: Sequence[Hire],
    months: int,
    assumptions: Assumptions,
    other_costs: float | Sequence[float] = 0.0,
    revenue: float | Sequence[float] = 0.0,
) -> list[float]:
    """1〜months か月目の月次純バーン（費用 − 収入）のリストを返す。

    月 m の純バーン = Σ hire_cost_in_month(h, m) + other_costs[m] − revenue[m]
    （正ならその月に現金が減る）

    - other_costs と revenue は、数値（毎月同じ額）または長さ months のシーケンス（月ごとの額）。
      シーケンスの長さが months と違えば ValueError。
    - months < 1 なら ValueError。
    """
    raise NotImplementedError("演習4: monthly_burn を実装してください")


def projected_runway(opening_cash: float, burns: Sequence[float]) -> int | None:
    """期首の現金と月次純バーンの列から、資金が何か月もつかを返す。

    月 1, 2, ... の順に現金から純バーンを引いていき、初めて現金が負になった月を m とすると、
    m − 1 を返す（1〜m−1 か月目までは資金が足りた）。期間内に一度も負にならなければ None。
    ちょうど 0 になった月は、まだ尽きていないとみなす。
    opening_cash < 0 なら ValueError。

    >>> projected_runway(100, [30, 30, 30, 30])
    3
    >>> projected_runway(100, [50, 50]) is None
    True
    """
    raise NotImplementedError("演習4: projected_runway を実装してください")


def simple_runway(cash: float, net_burn: float) -> float:
    """単純ランウェイ（か月）= 現金 ÷ 現在の月次純バーン。

    今の純バーンがずっと続くと仮定した見積もり。採用で費用が増えていく計画では過大になる。
    - net_burn <= 0（現金が減っていない）なら math.inf を返す。
    - cash < 0 なら ValueError。
    """
    raise NotImplementedError("演習4: simple_runway を実装してください")


def delay_sensitivity(
    opening_cash: float,
    hires: Sequence[Hire],
    months: int,
    assumptions: Assumptions,
    other_costs: float | Sequence[float] = 0.0,
    revenue: float | Sequence[float] = 0.0,
    delays: Sequence[int] = (0, 1, 2, 3),
) -> dict[int, int | None]:
    """採用が d か月遅れた場合のランウェイを、delays の各 d について辞書で返す。

    - 計画期間中に入社する人（start_month >= 1）だけ、start_month を d だけ後ろにずらす。
      在籍者（start_month <= 0）はずらさない。
    - ずらした結果、入社月が months を超えた人は、計画期間中の費用が 0 になる（それで正しい）。
    - 各 d について monthly_burn → projected_runway を計算する。
    - d < 0 なら ValueError。元の hires を書き換えないこと。

    ヒント: Hire は frozen な dataclass なので dataclasses.replace(h, start_month=...) を使う。
    """
    raise NotImplementedError("演習4: delay_sensitivity を実装してください")
