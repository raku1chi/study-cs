"""13.2 技術的意思決定と設計レビュー — 演習: 重み付き意思決定マトリクスと感度分析

技術選定でよく使われる「重み付き意思決定マトリクス」を実装し、その結果が
正規化の方法や重みの置き方にどれだけ左右されるか（感度分析）を確かめます。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.2          # 合格数を表示
    python3 tools/check.py -v 13.2       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

データの形（すべての関数で共通）:
    - scores[i][j]      : 案 i の評価軸 j の「生の値」（例: 月額費用 5 万円、習熟期間 2 週）
    - normalized[i][j]  : 0〜1 に正規化した値（1 が最も良い）
    - directions[j]     : "benefit"（大きいほど良い）か "cost"（小さいほど良い）
    - weights[j]        : 評価軸 j の重み（非負。合計が 1 でなくてもよく、内部で合計 1 に正規化する）

制約:
    - 標準ライブラリのみを使ってください（numpy などは使わない）。
"""
from __future__ import annotations

import random  # noqa: F401  演習4で使います

BENEFIT = "benefit"
COST = "cost"
METHODS = ("minmax", "ratio")


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 正規化
# ---------------------------------------------------------------------------

def normalize(
    scores: list[list[float]], directions: list[str], method: str = "minmax"
) -> list[list[float]]:
    """生の値の行列を、評価軸ごとに 0〜1（1 が最良）へ正規化した新しい行列を返す。

    method == "minmax"（最良を 1、最悪を 0 にそろえる）:
        benefit の軸: (x - min) / (max - min)
        cost の軸   : (max - x) / (max - min)
        その軸で全案が同じ値（max == min）なら、全案 1.0（差がつかない）

    method == "ratio"（最良の案に対する比率）:
        benefit の軸: x / max
        cost の軸   : min / x
        その軸に 0 以下の値があれば ValueError（比率が意味を持たないため）

    次の場合は ValueError:
        - scores が空、または評価軸が 0 個
        - 行ごとに評価軸の数が違う
        - directions の長さが評価軸の数と違う、または "benefit"/"cost" 以外を含む
        - method が "minmax"/"ratio" 以外

    >>> normalize([[1, 10], [3, 20], [5, 30]], ["benefit", "cost"])
    [[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]]
    >>> normalize([[2, 10], [4, 20]], ["benefit", "cost"], method="ratio")
    [[0.5, 1.0], [1.0, 0.5]]

    ヒント: 評価軸（列）ごとに min と max を求めてから、各案の値を変換する。
    """
    raise NotImplementedError("演習1: normalize を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 重み付きスコアと順位
# ---------------------------------------------------------------------------

def weighted_scores(normalized: list[list[float]], weights: list[float]) -> list[float]:
    """各案の重み付きスコア（重みを合計 1 に正規化したうえでの加重和）を返す。

    - weights の長さが評価軸の数と違う、負の重みがある、重みの合計が 0 以下 → ValueError
    - normalized の形が不正（空・行ごとに長さが違う）→ ValueError

    >>> weighted_scores([[1.0, 0.0], [0.0, 1.0]], [3, 1])
    [0.75, 0.25]
    """
    raise NotImplementedError("演習2: weighted_scores を実装してください")


def ranking(scores: list[float]) -> list[int]:
    """スコアの高い順に並べた案の添字のリストを返す。同点の案は添字の小さい順。

    >>> ranking([0.2, 0.9, 0.5])
    [1, 2, 0]
    >>> ranking([0.5, 0.7, 0.7])
    [1, 2, 0]
    """
    raise NotImplementedError("演習2: ranking を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 1 位が入れ替わる重み（1 軸ずつの感度分析）
# ---------------------------------------------------------------------------

def weight_flip_points(
    normalized: list[list[float]], weights: list[float]
) -> list[tuple[float, int] | None]:
    """評価軸ごとに「その軸の重みだけを動かしたとき、1 位が入れ替わる重み」を求める。

    評価軸 k の重みを t（0 <= t <= 1）に変えるとき、他の軸の重みは互いの比率を保ったまま、
    合計が 1 - t になるように一律に拡大・縮小する（重みの合計は常に 1）。

    戻り値は評価軸ごとの要素を持つリストで、各要素は次のどちらか:
        - (t, b): 重みを t にすると、現在の 1 位と案 b が同点になる（それを越えると b が 1 位）。
                  現在の重みから最も近い（|t - 現在の重み| が最小の）点を返す。
                  変化量が同じ挑戦者が複数あれば、添字の小さい案を返す。
        - None  : t を 0〜1 のどこに動かしても 1 位は変わらない。
                  また、その軸の重みが 1（他の軸の重みがすべて 0）の場合も
                  「比率を保って配り直す」ことができないので None とする。

    現在の 1 位は ranking(weighted_scores(...)) の先頭（同点なら添字の小さい案）とする。

    >>> weight_flip_points([[1.0, 0.0], [0.0, 1.0]], [0.6, 0.4])
    [(0.5, 1), (0.5, 1)]

    ヒント: 1 位 a と挑戦者 b のスコア差 D は t の 1 次式になる。
        D(1) = 軸 k の値だけで比べた差              = n[a][k] - n[b][k]
        D(0) = 軸 k を除いた他の軸だけで比べた差    = (S_a - w_k*n[a][k] - (S_b - w_k*n[b][k])) / (1 - w_k)
        D(t) = D(0) + t * (D(1) - D(0))
    D(t) = 0 を解き、t が 0〜1 に入る挑戦者のうち、現在の重みに最も近いものを選ぶ。
    （S は現在のスコア、w_k は合計 1 に正規化した現在の重み）
    """
    raise NotImplementedError("演習3: weight_flip_points を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 重みの揺らぎに対する 1 位の安定性（モンテカルロ法）
# ---------------------------------------------------------------------------

def rank_stability(
    normalized: list[list[float]],
    weights: list[float],
    spread: float = 0.2,
    trials: int = 2000,
    seed: int = 0,
) -> list[float]:
    """重みをランダムに揺らしたとき、各案が 1 位になる割合を返す（合計 1.0）。

    手順（この順序で乱数を使うこと。同じ seed なら同じ結果になる）:
        1. rng = random.Random(seed) を作る
        2. trials 回繰り返す:
           - 合計 1 に正規化した各重み w_j に、rng.uniform(1 - spread, 1 + spread) を
             評価軸の順に 1 つずつ掛ける
           - 揺らした重みでスコアを計算し、1 位（同点なら添字の小さい案）を数える
        3. 各案の 1 位の回数 / trials を返す

    - spread が 0 未満または 1 以上、trials が 1 未満 → ValueError
    - weights・normalized の検証は weighted_scores と同じ

    >>> rank_stability([[1.0, 0.0], [0.0, 1.0]], [0.9, 0.1], spread=0.2, trials=100)
    [1.0, 0.0]

    意味: 1 位になる割合が 100% に近ければ、結論は重みの細かい置き方に左右されにくい。
    50〜80% 程度なら「僅差」であり、数字ではなく論点（何を重視するか）を議論すべきサイン。
    """
    raise NotImplementedError("演習4: rank_stability を実装してください")
