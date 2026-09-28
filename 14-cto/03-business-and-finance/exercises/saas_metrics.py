"""14.3 事業と財務のリテラシー — 演習2・3（saas_metrics.py）

月末時点の「顧客ごとの MRR」（スナップショット）から、MRR の増減分解・NRR/GRR・
ロゴリテンションを計算し、CAC・LTV・CAC 回収期間・Rule of 40・バーンマルチプルといった
SaaS の効率の指標を求める関数を作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.3
    python3 -m unittest -v test_saas_metrics   # このディレクトリで直接

データの形:
    snapshots は「月末ごとの {顧客ID: MRR}」のリスト。snapshots[0] が最初の月末。
    ある月のスナップショットに顧客がいない、または MRR が 0 なら、その月は課金していない。

    例（単位: 万円/月）:
        [{"A": 100, "B": 50}, {"A": 120, "C": 40}]
        → 1 か月目: A が 20 拡大、B が 50 解約、C が 40 新規
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

Snapshot = Mapping[str, float]  # 顧客 ID → その月末の MRR


@dataclass(frozen=True)
class MrrMovement:
    """snapshots[period - 1] から snapshots[period] への MRR の増減（この型は完成しています）。"""

    period: int          # 何番目のスナップショットへの移動か（1 始まり）
    starting: float      # 期首 MRR（snapshots[period - 1] の合計）
    new: float           # 新規: 前月は課金なし、今月は課金あり、過去に一度も課金したことがない
    expansion: float     # 拡大: 前月も今月も課金あり、今月の方が大きい（増分）
    reactivation: float  # 再開: 前月は課金なし、今月は課金あり、過去に課金したことがある
    contraction: float   # 縮小: 前月も今月も課金あり、今月の方が小さい（減少分、正の値）
    churned: float       # 解約: 前月は課金あり、今月は課金なし（前月の MRR、正の値）
    ending: float        # 期末 MRR（snapshots[period] の合計）

    @property
    def net_new(self) -> float:
        """純新規 MRR = 新規 + 拡大 + 再開 − 縮小 − 解約（= 期末 − 期首）。"""
        return self.new + self.expansion + self.reactivation - self.contraction - self.churned


# ---------------------------------------------------------------------------
# 演習2（★★☆）: MRR の増減分解とリテンション
# ---------------------------------------------------------------------------

def mrr_movements(snapshots: Sequence[Snapshot]) -> list[MrrMovement]:
    """連続するスナップショットから、各月の MRR の増減を MrrMovement のリストで返す。

    - 返すリストの長さは len(snapshots) - 1（スナップショットが 1 つ以下なら空リスト）。
    - 「課金あり」は MRR > 0。スナップショットに顧客がいない場合は MRR 0 とみなす。
    - 新規と再開の区別: 「過去に課金したことがある」かどうかは、snapshots[0] から
      前月までのすべてのスナップショットで判断する（snapshots[0] で課金していた顧客も含む）。
    - どのスナップショットにでも MRR が負の値があれば ValueError。
    - 恒等式: ending == starting + new + expansion + reactivation − contraction − churned

    ヒント: 過去に課金したことのある顧客 ID を集合で持ち、月ごとに更新する。
    """
    raise NotImplementedError("演習2: mrr_movements を実装してください")


def net_revenue_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    """NRR（売上継続率、Net Revenue Retention）を返す。

    コホート = snapshots[start] で課金している（MRR > 0）顧客。
    NRR = コホートの顧客の snapshots[end] での MRR の合計 ÷ コホートの snapshots[start] での MRR の合計

    - 新規顧客（コホートにいない顧客）は含めない。拡大・縮小・解約・再開はすべて反映される。
    - 0 <= start < end < len(snapshots) でなければ ValueError。
    - コホートが空（start 時点で課金している顧客がいない）なら ValueError。
    - MRR が負の値があれば ValueError。
    """
    raise NotImplementedError("演習2: net_revenue_retention を実装してください")


def gross_revenue_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    """GRR（Gross Revenue Retention）を返す。拡大分を含めない継続率で、1.0 を超えない。

    GRR = Σ_{コホートの顧客 c} min(end 時点の MRR(c), start 時点の MRR(c)) ÷ start 時点の MRR の合計

    エラーの条件は net_revenue_retention と同じ。
    """
    raise NotImplementedError("演習2: gross_revenue_retention を実装してください")


def logo_retention(snapshots: Sequence[Snapshot], start: int, end: int) -> float:
    """ロゴリテンション（顧客数ベースの継続率）を返す。

    = コホートのうち snapshots[end] で課金している顧客の数 ÷ コホートの顧客の数

    エラーの条件は net_revenue_retention と同じ。
    """
    raise NotImplementedError("演習2: logo_retention を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: ユニットエコノミクスと効率の指標
# ---------------------------------------------------------------------------

def cac(sales_marketing_cost: float, new_customers: int) -> float:
    """CAC（顧客獲得コスト）= 営業・マーケティング費用 ÷ 新規顧客数。

    - sales_marketing_cost < 0 なら ValueError。new_customers <= 0 なら ValueError。
    """
    raise NotImplementedError("演習3: cac を実装してください")


def cac_payback_months(cac_value: float, arpa_monthly: float, gross_margin: float) -> float:
    """CAC 回収期間（月）= CAC ÷ (顧客あたり月次売上 ARPA × 粗利率)。

    回収に使えるのは売上ではなく粗利であることに注意。
    - cac_value < 0、arpa_monthly <= 0、gross_margin が 0 より大きく 1 以下でない場合は ValueError。

    >>> cac_payback_months(120.0, 10.0, 0.8)
    15.0
    """
    raise NotImplementedError("演習3: cac_payback_months を実装してください")


def ltv(arpa_monthly: float, gross_margin: float, monthly_churn: float) -> float:
    """LTV（顧客生涯価値、粗利ベース）= ARPA × 粗利率 ÷ 月次解約率。

    解約率が一定なら、顧客の平均継続期間は 1 / 月次解約率（か月）になることを使った簡略式。
    - arpa_monthly < 0、gross_margin が 0〜1 でない、monthly_churn が 0 より大きく 1 以下でない
      場合は ValueError。

    >>> ltv(10.0, 0.8, 0.02)
    400.0
    """
    raise NotImplementedError("演習3: ltv を実装してください")


def annual_churn_from_monthly(monthly_churn: float) -> float:
    """月次解約率から年間解約率を求める: 1 − (1 − monthly_churn) ** 12。

    月次 2% の解約は年 24% ではなく約 21.5%（毎月「残っている顧客」の 2% が解約するため）。
    monthly_churn が 0〜1 でなければ ValueError。
    """
    raise NotImplementedError("演習3: annual_churn_from_monthly を実装してください")


def rule_of_40(revenue_growth: float, profit_margin: float) -> float:
    """Rule of 40 のスコア = 売上成長率 + 利益率（どちらも比率。0.30 = 30%）。

    0.40 以上なら「成長と収益性のバランスが取れている」目安を満たす。
    利益率には EBITDA マージンや FCF マージンが使われる（どれを使ったかを明記すること）。

    >>> round(rule_of_40(0.55, -0.10), 10)
    0.45
    """
    raise NotImplementedError("演習3: rule_of_40 を実装してください")


def burn_multiple(net_burn: float, net_new_arr: float) -> float:
    """バーンマルチプル = 純バーン（期間中に減った現金）÷ 同じ期間の純新規 ARR。

    1 円の ARR を積み増すのに何円の現金を燃やしたかを表す。小さいほど効率が良い。
    - net_new_arr <= 0 なら ValueError（ARR が増えていないと定義できない）。
    - net_burn が負（現金が増えた）なら負の値を返してよい。
    """
    raise NotImplementedError("演習3: burn_multiple を実装してください")
