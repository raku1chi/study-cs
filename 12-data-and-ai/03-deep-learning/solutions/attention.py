"""12.3 深層学習とTransformer — 演習3: 注意機構（アテンション）を行列演算から作る（解答例）

演習の仕様は exercises/attention.py の docstring を参照してください。
行列は「リストのリスト」で、X[i] が i 番目のトークンのベクトル（行ベクトル）です。
"""
from __future__ import annotations

import math
from typing import Sequence

Matrix = list[list[float]]
Mask = Sequence[Sequence[bool]]


def _shape(A: Sequence[Sequence[float]]) -> tuple[int, int]:
    if not A or not A[0]:
        raise ValueError("空の行列です")
    cols = len(A[0])
    if any(len(row) != cols for row in A):
        raise ValueError("行の長さがそろっていません")
    return len(A), cols


def matmul(A: Sequence[Sequence[float]], B: Sequence[Sequence[float]]) -> Matrix:
    n, k = _shape(A)
    k2, m = _shape(B)
    if k != k2:
        raise ValueError(f"形が合いません: ({n}×{k}) @ ({k2}×{m})")
    cols = list(zip(*B))
    return [[sum(a * b for a, b in zip(row, col)) for col in cols] for row in A]


def transpose(A: Sequence[Sequence[float]]) -> Matrix:
    _shape(A)
    return [list(col) for col in zip(*A)]


def softmax(xs: Sequence[float]) -> list[float]:
    if not xs:
        raise ValueError("空のベクトルです")
    m = max(xs)
    if m == -math.inf:
        raise ValueError("すべての要素が -inf です（どこにも注意を向けられない）")
    # 最大値を引いてから exp をとる。softmax の値は変わらず、exp のオーバーフローを防げる
    exps = [math.exp(x - m) for x in xs]  # exp(-inf) = 0.0
    total = sum(exps)
    return [e / total for e in exps]


def causal_mask(n: int) -> list[list[bool]]:
    if n < 1:
        raise ValueError("n は 1 以上")
    return [[j <= i for j in range(n)] for i in range(n)]  # 自分と過去だけを見てよい


def scaled_dot_product_attention(
    Q: Sequence[Sequence[float]],
    K: Sequence[Sequence[float]],
    V: Sequence[Sequence[float]],
    mask: Mask | None = None,
) -> tuple[Matrix, Matrix]:
    n_q, d_k = _shape(Q)
    n_k, d_k2 = _shape(K)
    n_v, _ = _shape(V)
    if d_k != d_k2:
        raise ValueError("Q と K の次元が違います")
    if n_k != n_v:
        raise ValueError("K と V の行数が違います")
    if mask is not None and (len(mask) != n_q or any(len(row) != n_k for row in mask)):
        raise ValueError("mask の形が (Q の行数 × K の行数) ではありません")
    scale = 1.0 / math.sqrt(d_k)
    # scores[i][j] = q_i · k_j / √d_k : クエリ i がキー j にどれだけ「似ているか」
    scores = [[s * scale for s in row] for row in matmul(Q, transpose(K))]
    if mask is not None:
        scores = [[s if allowed else -math.inf for s, allowed in zip(row, mrow)] for row, mrow in zip(scores, mask)]
    weights = [softmax(row) for row in scores]  # 各行の和が 1 になる注意の重み
    return matmul(weights, V), weights  # 値ベクトルの重み付き平均


def split_heads(X: Sequence[Sequence[float]], n_heads: int) -> list[Matrix]:
    _, d_model = _shape(X)
    if n_heads < 1 or d_model % n_heads:
        raise ValueError(f"d_model={d_model} は n_heads={n_heads} で割り切れません")
    d_head = d_model // n_heads
    return [[list(row[h * d_head:(h + 1) * d_head]) for row in X] for h in range(n_heads)]


def merge_heads(heads: Sequence[Sequence[Sequence[float]]]) -> Matrix:
    if not heads:
        raise ValueError("ヘッドがありません")
    n = len(heads[0])
    if any(len(h) != n for h in heads):
        raise ValueError("ヘッドごとの行数が違います")
    return [[v for h in heads for v in h[i]] for i in range(n)]


def multi_head_attention(
    X: Sequence[Sequence[float]],
    W_q: Sequence[Sequence[float]],
    W_k: Sequence[Sequence[float]],
    W_v: Sequence[Sequence[float]],
    W_o: Sequence[Sequence[float]],
    n_heads: int,
    *,
    causal: bool = False,
) -> Matrix:
    n, _ = _shape(X)
    Q, K, V = matmul(X, W_q), matmul(X, W_k), matmul(X, W_v)  # 線形の射影
    mask = causal_mask(n) if causal else None
    outputs = [
        scaled_dot_product_attention(q, k, v, mask)[0]
        for q, k, v in zip(split_heads(Q, n_heads), split_heads(K, n_heads), split_heads(V, n_heads))
    ]
    return matmul(merge_heads(outputs), W_o)  # ヘッドの出力を連結して、もう一度射影する


def sinusoidal_positional_encoding(n_positions: int, d_model: int) -> Matrix:
    if n_positions < 1 or d_model < 1:
        raise ValueError("n_positions と d_model は 1 以上")
    pe = []
    for pos in range(n_positions):
        row = []
        for j in range(d_model):
            angle = pos / 10000 ** (2 * (j // 2) / d_model)
            row.append(math.sin(angle) if j % 2 == 0 else math.cos(angle))
        pe.append(row)
    return pe


def layer_norm(x: Sequence[float], eps: float = 1e-5) -> list[float]:
    if not x:
        raise ValueError("空のベクトルです")
    mean = sum(x) / len(x)
    var = sum((v - mean) ** 2 for v in x) / len(x)
    return [(v - mean) / math.sqrt(var + eps) for v in x]


class KVCache:
    """自己回帰の生成で、過去のトークンの K と V を保存して再利用する（因果的な注意 1 ヘッド分）。"""

    def __init__(self) -> None:
        self.keys: Matrix = []
        self.values: Matrix = []

    def __len__(self) -> int:
        return len(self.keys)

    def append(self, k: Sequence[float], v: Sequence[float]) -> None:
        if self.keys and (len(k) != len(self.keys[0]) or len(v) != len(self.values[0])):
            raise ValueError("次元が既存のエントリと違います")
        self.keys.append(list(k))
        self.values.append(list(v))

    def attend(self, q: Sequence[float]) -> tuple[list[float], list[float]]:
        if not self.keys:
            raise ValueError("キャッシュが空です")
        # 新しいトークンのクエリ 1 本だけを、保存済みの全キーと比べる。過去の K, V を計算し直さない
        out, weights = scaled_dot_product_attention([list(q)], self.keys, self.values)
        return out[0], weights[0]
