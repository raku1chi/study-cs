"""12.2 機械学習の基礎 — 演習用のデータ生成（実装済み。編集は不要です）

テストと本文のコード例で使う合成データを、シード付きの乱数で決定的に作ります。
実データの代わりに合成データを使うと、「正解（真のパラメータ）」が分かっているので、
アルゴリズムが正しく学習できたかを確かめられます。
"""
from __future__ import annotations

import math
import random

Matrix = list[list[float]]


def make_regression(
    n: int,
    coefs: list[float],
    intercept: float,
    *,
    noise: float = 0.1,
    scales: list[float] | None = None,
    seed: int = 0,
) -> tuple[Matrix, list[float]]:
    """y = intercept + Σ coefs[j]·x[j] + ノイズ を満たすデータを n 件作る。

    x[j] は平均 0・標準偏差 scales[j] の正規分布（既定はすべて 1）。
    """
    rng = random.Random(seed)
    scales = scales or [1.0] * len(coefs)
    X = [[rng.gauss(0.0, 1.0) * s for s in scales] for _ in range(n)]
    y = [intercept + sum(c * x for c, x in zip(coefs, row)) + rng.gauss(0.0, noise) for row in X]
    return X, y


def make_two_gaussians(
    n: int,
    *,
    distance: float = 2.0,
    positive_ratio: float = 0.5,
    seed: int = 0,
) -> tuple[Matrix, list[int]]:
    """2 次元の 2 クラス分類データ。クラス 1 は (+d/2, +d/2)、クラス 0 は (-d/2, -d/2) が中心。

    標準偏差は 1。positive_ratio でクラス 1 の割合（不均衡の度合い）を指定する。
    """
    rng = random.Random(seed)
    X: Matrix = []
    y: list[int] = []
    h = distance / 2
    for _ in range(n):
        label = 1 if rng.random() < positive_ratio else 0
        c = h if label else -h
        X.append([rng.gauss(c, 1.0), rng.gauss(c, 1.0)])
        y.append(label)
    return X, y


def make_blobs(
    centers: list[list[float]],
    n_per_center: int,
    *,
    std: float = 1.0,
    seed: int = 0,
) -> tuple[Matrix, list[int]]:
    """各中心のまわりに正規分布で n_per_center 点ずつ作る。戻り値は (点, 正解のクラスタ番号)。"""
    rng = random.Random(seed)
    X: Matrix = []
    labels: list[int] = []
    for k, center in enumerate(centers):
        for _ in range(n_per_center):
            X.append([rng.gauss(c, std) for c in center])
            labels.append(k)
    order = list(range(len(X)))
    rng.shuffle(order)
    return [X[i] for i in order], [labels[i] for i in order]


def make_xor(n: int, *, margin: float = 0.1, seed: int = 0) -> tuple[Matrix, list[int]]:
    """[-1, 1]² の点を、x と y の符号が同じなら 0、違えば 1 とラベル付けする（XOR）。

    軸の近く（|x| < margin または |y| < margin）の点は作らない。
    線形モデルでは分離できないが、決定木なら深さ 2 で分離できる。
    """
    rng = random.Random(seed)
    X: Matrix = []
    y: list[int] = []
    while len(X) < n:
        a, b = rng.uniform(-1, 1), rng.uniform(-1, 1)
        if abs(a) < margin or abs(b) < margin:
            continue
        X.append([a, b])
        y.append(int((a > 0) != (b > 0)))
    return X, y


def train_test_split(
    X: Matrix, y: list, *, test_ratio: float = 0.25, seed: int = 0
) -> tuple[Matrix, Matrix, list, list]:
    """シャッフルしてから末尾 test_ratio を検証用に分ける。(X_train, X_test, y_train, y_test) を返す。"""
    if not 0 < test_ratio < 1:
        raise ValueError("test_ratio は 0 より大きく 1 より小さくしてください")
    idx = list(range(len(X)))
    random.Random(seed).shuffle(idx)
    n_test = max(1, math.floor(len(X) * test_ratio))
    tr, te = idx[:-n_test], idx[-n_test:]
    return [X[i] for i in tr], [X[i] for i in te], [y[i] for i in tr], [y[i] for i in te]
