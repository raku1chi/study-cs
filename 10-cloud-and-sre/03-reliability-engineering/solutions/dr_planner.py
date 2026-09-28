"""10.3 信頼性設計とSLO — 演習（DR 戦略の選択）の解答例

演習の仕様は exercises/dr_planner.py の docstring を参照してください。
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
# 演習4: 要件を満たす最安の戦略と、期待損失
# ===========================================================================

def meets(strategy: Strategy, max_rpo_minutes: float | None, max_rto_minutes: float | None) -> bool:
    return (max_rpo_minutes is None or strategy.rpo_minutes <= max_rpo_minutes) and (
        max_rto_minutes is None or strategy.rto_minutes <= max_rto_minutes
    )


def cheapest_strategy(
    strategies: Sequence[Strategy],
    max_rpo_minutes: float | None,
    max_rto_minutes: float | None,
) -> Strategy | None:
    candidates = [s for s in strategies if meets(s, max_rpo_minutes, max_rto_minutes)]
    if not candidates:
        return None
    return min(candidates, key=lambda s: (s.annual_cost, s.rto_minutes, s.rpo_minutes, s.name))


def expected_annual_loss(strategy: Strategy, service: Service) -> float:
    # 年間期待損失（ALE）= 発生頻度 × 1 回あたりの損失。1 回の損失 = 停止の損失 + データ喪失の損失
    single_loss = (
        strategy.rto_minutes / 60 * service.downtime_cost_per_hour
        + strategy.rpo_minutes / 60 * service.data_loss_cost_per_hour
    )
    return service.disasters_per_year * single_loss


def best_strategy(strategies: Sequence[Strategy], service: Service) -> tuple[Strategy, float]:
    candidates = [s for s in strategies if meets(s, service.max_rpo_minutes, service.max_rto_minutes)]
    if not candidates:
        raise ValueError(f"{service.name} の要件を満たす戦略がありません")
    # 費用と期待損失の合計が最小のもの。同じなら安い方、さらに同じなら名前順
    scored = [(s.annual_cost + expected_annual_loss(s, service), s.annual_cost, s.name, s) for s in candidates]
    total, _, _, best = min(scored, key=lambda x: x[:3])
    return best, total


# ===========================================================================
# 演習5: 予算の制約の下での配分
# ===========================================================================

def allocate_budget(services: Sequence[Service], strategies: Sequence[Strategy], budget: int) -> Allocation:
    # 「グループごとに 1 つ選ぶナップサック問題」を、到達できる費用ごとの最良値で解く動的計画法。
    # states[費用の合計] = (費用 + 期待損失の合計, それまでの選択)
    states: dict[int, tuple[float, list[str]]] = {0: (0.0, [])}
    for svc in services:
        options = [s for s in strategies if meets(s, svc.max_rpo_minutes, svc.max_rto_minutes)]
        if not options:
            raise ValueError(f"{svc.name} の要件を満たす戦略がありません")
        nxt: dict[int, tuple[float, list[str]]] = {}
        for cost, (value, chosen) in states.items():
            for s in options:
                c = cost + s.annual_cost
                if c > budget:
                    continue
                v = value + s.annual_cost + expected_annual_loss(s, svc)
                if c not in nxt or v < nxt[c][0]:
                    nxt[c] = (v, chosen + [s.name])
        if not nxt:
            raise ValueError(f"予算 {budget} 万円では、必須の要件をすべて満たせません")
        states = nxt
    # 費用 + 期待損失が最小の状態（同じなら費用の小さい方）。予算を使い切ることが目的ではない
    cost, (value, chosen) = min(states.items(), key=lambda kv: (kv[1][0], kv[0]))
    return Allocation({svc.name: name for svc, name in zip(services, chosen)}, cost, value)
