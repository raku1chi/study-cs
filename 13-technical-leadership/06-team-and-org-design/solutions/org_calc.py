"""13.6 チームと組織の設計 — 解答例: 組織の規模の計算

演習の仕様は exercises/org_calc.py の docstring を参照してください。
"""
from __future__ import annotations

import math


# ---------------------------------------------------------------------------
# 演習1: コミュニケーションの経路と、マネージャーの階層
# ---------------------------------------------------------------------------

def communication_paths(n: int) -> int:
    if n < 0:
        raise ValueError("人数は 0 以上にしてください")
    # n 人から 2 人を選ぶ組み合わせ: nC2 = n(n-1)/2
    return n * (n - 1) // 2


def management_layers(engineers: int, ic_span: int, manager_span: int) -> list[int]:
    if engineers < 1:
        raise ValueError("エンジニアは 1 人以上にしてください")
    if ic_span < 1 or manager_span < 2:
        raise ValueError("ic_span は 1 以上、manager_span は 2 以上にしてください")
    # 1 層目: エンジニアを直接見るマネージャー
    layers = [math.ceil(engineers / ic_span)]
    # 2 層目以降: 1 人になるまで、下の層のマネージャーを manager_span 人ずつ束ねる
    while layers[-1] > 1:
        layers.append(math.ceil(layers[-1] / manager_span))
    return layers


def management_overhead(
    engineers: int,
    ic_span: int,
    manager_span: int,
    engineer_cost: float,
    manager_cost: float,
) -> dict[str, float]:
    if engineer_cost < 0 or manager_cost < 0:
        raise ValueError("コストは 0 以上にしてください")
    layers = management_layers(engineers, ic_span, manager_span)
    managers = sum(layers)
    total_cost = engineers * engineer_cost + managers * manager_cost
    return {
        "managers": managers,
        "layers": len(layers),
        "people_ratio": managers / (engineers + managers),
        "cost_ratio": managers * manager_cost / total_cost if total_cost > 0 else 0.0,
    }
