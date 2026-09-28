"""13.2 技術的意思決定と設計レビュー — 解答例: 重み付き意思決定マトリクスと感度分析

演習の仕様は exercises/decision_matrix.py の docstring を参照してください。
ここでは「なぜそう計算するのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import random

BENEFIT = "benefit"
COST = "cost"
METHODS = ("minmax", "ratio")


# ---------------------------------------------------------------------------
# 演習1: 正規化
# ---------------------------------------------------------------------------

def _check_matrix(scores: list[list[float]]) -> tuple[int, int]:
    if not scores or not scores[0]:
        raise ValueError("scores は 1 案以上・1 評価軸以上の行列にしてください")
    n_criteria = len(scores[0])
    for i, row in enumerate(scores):
        if len(row) != n_criteria:
            raise ValueError(f"案 {i} の評価軸の数が他と違います: {len(row)} != {n_criteria}")
    return len(scores), n_criteria


def normalize(
    scores: list[list[float]], directions: list[str], method: str = "minmax"
) -> list[list[float]]:
    n_alt, n_crit = _check_matrix(scores)
    if len(directions) != n_crit:
        raise ValueError("directions の長さが評価軸の数と一致しません")
    if method not in METHODS:
        raise ValueError(f"未知の正規化方法です: {method!r}")
    for d in directions:
        if d not in (BENEFIT, COST):
            raise ValueError(f"direction は 'benefit' か 'cost': {d!r}")

    result = [[0.0] * n_crit for _ in range(n_alt)]
    for j, direction in enumerate(directions):
        column = [row[j] for row in scores]
        lo, hi = min(column), max(column)
        for i, x in enumerate(column):
            if method == "minmax":
                # 最良の案を 1、最悪の案を 0 にそろえる。差がつかない軸は全案 1.0
                if hi == lo:
                    value = 1.0
                elif direction == BENEFIT:
                    value = (x - lo) / (hi - lo)
                else:
                    value = (hi - x) / (hi - lo)
            else:
                # 比率: 最良の案を 1 とした相対値。0 の比が「何倍良いか」を表すので、正の値が必要
                if lo <= 0:
                    raise ValueError(f"ratio 正規化には正の値が必要です（評価軸 {j}）")
                value = x / hi if direction == BENEFIT else lo / x
            result[i][j] = value
    return result


# ---------------------------------------------------------------------------
# 演習2: 重み付きスコアと順位
# ---------------------------------------------------------------------------

def _normalized_weights(weights: list[float], n_crit: int) -> list[float]:
    if len(weights) != n_crit:
        raise ValueError("weights の長さが評価軸の数と一致しません")
    if any(w < 0 for w in weights):
        raise ValueError("重みに負の値は使えません")
    total = sum(weights)
    if total <= 0:
        raise ValueError("重みの合計は正にしてください")
    return [w / total for w in weights]


def weighted_scores(normalized: list[list[float]], weights: list[float]) -> list[float]:
    _, n_crit = _check_matrix(normalized)
    w = _normalized_weights(weights, n_crit)
    return [sum(wj * x for wj, x in zip(w, row)) for row in normalized]


def ranking(scores: list[float]) -> list[int]:
    # sorted は安定ソートなので、同点の案は入力順（添字の小さい順）のまま残る
    return sorted(range(len(scores)), key=lambda i: -scores[i])


# ---------------------------------------------------------------------------
# 演習3: 1 位が入れ替わる重み（1 軸ずつの感度分析）
# ---------------------------------------------------------------------------

def weight_flip_points(
    normalized: list[list[float]], weights: list[float]
) -> list[tuple[float, int] | None]:
    n_alt, n_crit = _check_matrix(normalized)
    w = _normalized_weights(weights, n_crit)
    scores = [sum(wj * x for wj, x in zip(w, row)) for row in normalized]
    winner = ranking(scores)[0]

    results: list[tuple[float, int] | None] = []
    for k in range(n_crit):
        if w[k] >= 1.0:
            # 他の軸の重みがすべて 0 なので「比率を保って配り直す」ことができない
            results.append(None)
            continue
        best: tuple[float, float, int] | None = None  # (|変化量|, 新しい重み, 新しい1位)
        for b in range(n_alt):
            if b == winner:
                continue
            # 軸 k の重みを t にし、他の軸は比率を保ったまま合計 (1 - t) に縮める。
            # 1 位 a と挑戦者 b のスコア差は t の 1 次式になる:
            #   D(t) = d0 + t * (d1 - d0)
            #   d1 = D(1)  : 軸 k だけで比べたときの差
            #   d0 = D(0)  : 軸 k を除いた他の軸だけで比べたときの差（重みは再正規化）
            rest_a = scores[winner] - w[k] * normalized[winner][k]
            rest_b = scores[b] - w[k] * normalized[b][k]
            d0 = (rest_a - rest_b) / (1.0 - w[k])
            d1 = normalized[winner][k] - normalized[b][k]
            slope = d1 - d0
            if slope == 0:
                continue  # 差が t によらず一定なので、この挑戦者とは入れ替わらない
            t = -d0 / slope  # D(t) = 0 となる重み（同点になる点）
            if not 0.0 <= t <= 1.0:
                continue
            candidate = (abs(t - w[k]), t, b)
            # 最初に同点に追いつく挑戦者を選ぶ。変化量が同じなら添字の小さい方
            if best is None or candidate[0] < best[0] or (
                candidate[0] == best[0] and b < best[2]
            ):
                best = candidate
        results.append(None if best is None else (best[1], best[2]))
    return results


# ---------------------------------------------------------------------------
# 演習4: 重みの揺らぎに対する 1 位の安定性（モンテカルロ法）
# ---------------------------------------------------------------------------

def rank_stability(
    normalized: list[list[float]],
    weights: list[float],
    spread: float = 0.2,
    trials: int = 2000,
    seed: int = 0,
) -> list[float]:
    n_alt, n_crit = _check_matrix(normalized)
    base = _normalized_weights(weights, n_crit)
    if not 0.0 <= spread < 1.0:
        raise ValueError("spread は 0 以上 1 未満にしてください")
    if trials <= 0:
        raise ValueError("trials は 1 以上にしてください")

    rng = random.Random(seed)
    wins = [0] * n_alt
    for _ in range(trials):
        # 各重みを独立に ±spread の範囲で揺らす（掛け算なので 0 の重みは 0 のまま）
        perturbed = [wj * rng.uniform(1.0 - spread, 1.0 + spread) for wj in base]
        scores = weighted_scores(normalized, perturbed)
        wins[ranking(scores)[0]] += 1
    return [c / trials for c in wins]
