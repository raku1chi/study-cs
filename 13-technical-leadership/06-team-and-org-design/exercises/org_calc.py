"""13.6 チームと組織の設計 — 演習: 組織の規模の計算

チームの人数とコミュニケーションの経路の関係、管理の幅（1 人のマネージャーが直接見る人数）から
必要になるマネージャーの人数と階層、そしてマネジメントのコストを計算します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.6          # この章の 2 つの演習（org_calc, team_clustering）をテスト
    python3 tools/check.py -v 13.6

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_org_calc

モデルは簡略化しています（実際の組織では、チームごとに人数がばらつき、
テックリードやスタッフエンジニアなど、マネージャー以外のリーダーも存在します）。
制約: 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

import math  # noqa: F401  management_layers で使えます


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: コミュニケーションの経路と、マネージャーの階層
# ---------------------------------------------------------------------------

def communication_paths(n: int) -> int:
    """n 人のチームで、2 人の間のコミュニケーションの経路の数 n(n−1)/2 を返す。

    - n が負 → ValueError

    >>> communication_paths(5), communication_paths(10)
    (10, 45)
    """
    raise NotImplementedError("演習1: communication_paths を実装してください")


def management_layers(engineers: int, ic_span: int, manager_span: int) -> list[int]:
    """各層のマネージャーの人数を、下の層から順に返す。最後の要素は常に 1（組織のトップ）。

    - 1 層目（エンジニアを直接見るマネージャー）: ceil(engineers / ic_span)
    - 2 層目以降（マネージャーを見るマネージャー）: ceil(下の層の人数 / manager_span)
    - 人数が 1 になった層で終わる（1 層目が 1 人ならその時点で終わる）

    - engineers が 1 未満、ic_span が 1 未満、manager_span が 2 未満 → ValueError

    >>> management_layers(150, ic_span=7, manager_span=5)
    [22, 5, 1]
    >>> management_layers(6, ic_span=8, manager_span=5)
    [1]
    """
    raise NotImplementedError("演習1: management_layers を実装してください")


def management_overhead(
    engineers: int,
    ic_span: int,
    manager_span: int,
    engineer_cost: float,
    manager_cost: float,
) -> dict[str, float]:
    """マネジメントの人数とコストの割合を返す。

    戻り値のキー:
        "managers"    : マネージャーの総数（management_layers の合計）
        "layers"      : 階層の数（management_layers の長さ）
        "people_ratio": managers / (engineers + managers)
        "cost_ratio"  : managers × manager_cost / (engineers × engineer_cost + managers × manager_cost)
                        （分母が 0 なら 0.0）

    - コストが負 → ValueError。その他の検証は management_layers と同じ

    >>> o = management_overhead(30, 7, 5, engineer_cost=1000, manager_cost=1300)
    >>> o["managers"], o["layers"], round(o["cost_ratio"], 3)
    (6, 2, 0.206)
    """
    raise NotImplementedError("演習1: management_overhead を実装してください")
