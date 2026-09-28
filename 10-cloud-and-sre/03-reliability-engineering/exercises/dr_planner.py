"""10.3 信頼性設計とSLO — 演習: DR（災害対策）戦略の選択

RPO（どこまでのデータを失ってよいか）と RTO（どれだけで復旧すべきか）の要件、
戦略ごとの費用、災害の頻度と損失の見積もりから、合理的な DR 戦略を選びます。
「全部をアクティブ・アクティブに」も「全部をバックアップだけで」も、多くの場合は誤りです。

- 演習4（★★☆）: meets, cheapest_strategy, expected_annual_loss, best_strategy
- 演習5（★★★）: allocate_budget — 予算の制約の下で、複数のサービスに戦略を配分する

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.3

金額の単位は万円。EXAMPLE_STRATEGIES の数値は説明用の架空のものです。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class Strategy:
    name: str
    rpo_minutes: float    # 災害時に失いうるデータの時間幅（最悪値）
    rto_minutes: float    # 災害の発生からサービス再開までの時間（最悪値）
    annual_cost: int      # 年間の費用（万円）


@dataclass(frozen=True)
class Service:
    name: str
    disasters_per_year: float        # DR 環境への切り替えが必要になる事象の年間発生頻度（期待値）
    downtime_cost_per_hour: float    # 停止 1 時間あたりの損失（万円）
    data_loss_cost_per_hour: float   # 失ったデータ 1 時間分あたりの損失（万円）
    max_rpo_minutes: float | None = None   # 必須の要件（契約・規制など）。なければ None
    max_rto_minutes: float | None = None


@dataclass(frozen=True)
class Allocation:
    choices: dict[str, str]    # サービス名 → 戦略名
    annual_cost: int           # 選んだ戦略の費用の合計（万円/年）
    expected_total: float      # 費用 + 期待損失の合計（万円/年）


# 架空の数値による例（実際の費用・性能はシステムと事業者によって大きく異なる）
EXAMPLE_STRATEGIES = [
    Strategy("backup-restore", rpo_minutes=24 * 60, rto_minutes=24 * 60, annual_cost=60),
    Strategy("pilot-light", rpo_minutes=15, rto_minutes=4 * 60, annual_cost=300),
    Strategy("warm-standby", rpo_minutes=1, rto_minutes=30, annual_cost=900),
    Strategy("active-active", rpo_minutes=0, rto_minutes=1, annual_cost=2400),
]


# ===========================================================================
# 演習4（★★☆）: 要件を満たす最安の戦略と、期待損失
# ===========================================================================

def meets(strategy: Strategy, max_rpo_minutes: float | None, max_rto_minutes: float | None) -> bool:
    """strategy の RPO が max_rpo_minutes 以下、かつ RTO が max_rto_minutes 以下なら True。

    None の要件は「制約なし」。ちょうど等しい場合は満たす。
    """
    raise NotImplementedError("演習4: meets を実装してください")


def cheapest_strategy(
    strategies: Sequence[Strategy],
    max_rpo_minutes: float | None,
    max_rto_minutes: float | None,
) -> Strategy | None:
    """要件を満たす戦略のうち、年間費用が最小のものを返す。なければ None。

    同額なら RTO の小さいもの、次に RPO の小さいもの、次に名前の昇順。
    """
    raise NotImplementedError("演習4: cheapest_strategy を実装してください")


def expected_annual_loss(strategy: Strategy, service: Service) -> float:
    """年間期待損失（ALE, Annualized Loss Expectancy）を返す（単位: 万円/年）。

    ALE = 年間発生頻度 × 1 回あたりの損失
    1 回あたりの損失 = RTO（時間） × 停止 1 時間あたりの損失 + RPO（時間） × データ 1 時間分の喪失の損失
    （RTO・RPO は分で持っているので 60 で割る）
    """
    raise NotImplementedError("演習4: expected_annual_loss を実装してください")


def best_strategy(strategies: Sequence[Strategy], service: Service) -> tuple[Strategy, float]:
    """service の必須要件（max_rpo_minutes / max_rto_minutes）を満たす戦略のうち、
    年間費用 + 年間期待損失 が最小のものを (戦略, その合計) で返す。

    同じ合計なら年間費用の小さいもの、次に名前の昇順。要件を満たす戦略がなければ ValueError。
    """
    raise NotImplementedError("演習4: best_strategy を実装してください")


# ===========================================================================
# 演習5（★★★）: 予算の制約の下での配分
# ===========================================================================

def allocate_budget(services: Sequence[Service], strategies: Sequence[Strategy], budget: int) -> Allocation:
    """各サービスに 1 つずつ戦略を割り当て、合計の (年間費用 + 年間期待損失) を最小にする。

    制約:
    - 各サービスの必須要件（max_rpo_minutes / max_rto_minutes）を満たす戦略だけを選べる
    - 選んだ戦略の年間費用の合計 <= budget
    返り値: Allocation(choices={サービス名: 戦略名}, annual_cost=費用の合計, expected_total=費用 + 期待損失の合計)
    最小値が複数あるときは、費用の合計が小さいものを選ぶ（それも同じならどれでもよい）。
    要件を満たす戦略がないサービスがある、または予算内に収まる割り当てがなければ ValueError。
    services が空なら Allocation({}, 0, 0.0)。

    注意: 予算を使い切ることが目的ではない。予算が十分なら、各サービスが best_strategy の結果になる。

    ヒント: サービス数 × 戦略数の全組み合わせ（戦略数^サービス数）を試すと、サービスが増えると爆発する。
    「ここまでのサービスで、費用の合計が c になる割り当てのうち最良の値」を c ごとに覚えておき、
    サービスを 1 つずつ加えて更新する（グループごとに 1 つ選ぶナップサック問題の動的計画法）。
    """
    raise NotImplementedError("演習5: allocate_budget を実装してください")
