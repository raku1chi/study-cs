"""12.2 機械学習の基礎 — 解答例

演習の仕様は exercises/ml_scratch.py の docstring を参照してください。
ライブラリを使わずに、線形回帰・ロジスティック回帰・評価指標・k-means・決定木・交差検証を実装します。
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

Matrix = list[list[float]]


def _validate_xy(X: Sequence[Sequence[float]], y: Sequence[Any]) -> int:
    """X と y の形を確かめ、特徴量の次元を返す。"""
    if len(X) == 0:
        raise ValueError("データが空です")
    if len(X) != len(y):
        raise ValueError(f"X と y の件数が違います: {len(X)} != {len(y)}")
    d = len(X[0])
    if d == 0 or any(len(row) != d for row in X):
        raise ValueError("X の各行は同じ長さ（1 以上）にしてください")
    return d


def _dot(w: Sequence[float], x: Sequence[float]) -> float:
    return sum(wi * xi for wi, xi in zip(w, x))


# ---------------------------------------------------------------------------
# 演習1: 線形回帰
# ---------------------------------------------------------------------------

def simple_linear_regression(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    n = len(xs)
    if n != len(ys):
        raise ValueError("xs と ys の件数が違います")
    if n < 2:
        raise ValueError("2 点以上が必要です")
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("x がすべて同じ値なので傾きが決まりません")
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx  # 共分散 / 分散
    return slope, my - slope * mx  # 回帰直線は必ず (x̄, ȳ) を通る


class Standardizer:
    """各特徴量を平均 0・標準偏差 1 に変換する。"""

    def __init__(self) -> None:
        self.means_: list[float] = []
        self.stds_: list[float] = []

    def fit(self, X: Sequence[Sequence[float]]) -> "Standardizer":
        if not X:
            raise ValueError("データが空です")
        n, d = len(X), len(X[0])
        self.means_ = [sum(row[j] for row in X) / n for j in range(d)]
        self.stds_ = []
        for j in range(d):
            var = sum((row[j] - self.means_[j]) ** 2 for row in X) / n
            std = math.sqrt(var)
            self.stds_.append(std if std > 0 else 1.0)  # 定数の列は割らない
        return self

    def transform(self, X: Sequence[Sequence[float]]) -> Matrix:
        if not self.means_:
            raise RuntimeError("fit を先に呼んでください")
        return [[(v - m) / s for v, m, s in zip(row, self.means_, self.stds_)] for row in X]

    def fit_transform(self, X: Sequence[Sequence[float]]) -> Matrix:
        return self.fit(X).transform(X)


def _to_original_scale(w: list[float], b: float, scaler: Standardizer | None) -> tuple[list[float], float]:
    """標準化した空間の重み (w, b) を、元の特徴量の空間の (coef, intercept) に戻す。

    b + Σ w_j (x_j - μ_j) / σ_j = (b - Σ w_j μ_j / σ_j) + Σ (w_j / σ_j) x_j
    """
    if scaler is None:
        return list(w), b
    coef = [wj / s for wj, s in zip(w, scaler.stds_)]
    intercept = b - sum(wj * m / s for wj, m, s in zip(w, scaler.means_, scaler.stds_))
    return coef, intercept


class LinearRegressionGD:
    def __init__(self, learning_rate: float = 0.1, n_epochs: int = 500, l2: float = 0.0, standardize: bool = True):
        if learning_rate <= 0 or n_epochs < 1 or l2 < 0:
            raise ValueError("learning_rate > 0, n_epochs >= 1, l2 >= 0 にしてください")
        self.learning_rate = learning_rate
        self.n_epochs = n_epochs
        self.l2 = l2
        self.standardize = standardize
        self.coef_: list[float] = []
        self.intercept_: float = 0.0
        self.loss_history_: list[float] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[float]) -> "LinearRegressionGD":
        d = _validate_xy(X, y)
        scaler = Standardizer().fit(X) if self.standardize else None
        Z = scaler.transform(X) if scaler else [list(row) for row in X]
        n = len(Z)
        w = [0.0] * d
        b = 0.0
        self.loss_history_ = []
        for _ in range(self.n_epochs):
            grad_w = [0.0] * d
            grad_b = 0.0
            sq = 0.0
            for z, target in zip(Z, y):
                err = b + _dot(w, z) - target  # 予測 - 正解
                sq += err * err
                grad_b += err
                for j in range(d):
                    grad_w[j] += err * z[j]
            loss = sq / n + self.l2 * sum(wj * wj for wj in w)
            self.loss_history_.append(loss)
            if not math.isfinite(loss):
                break  # 発散した（学習率が大きすぎる、特徴量のスケールが揃っていない）
            # L = (1/n) Σ err² + λ‖w‖² の勾配: ∂L/∂w_j = (2/n) Σ err·z_j + 2λ w_j
            for j in range(d):
                w[j] -= self.learning_rate * (2 * grad_w[j] / n + 2 * self.l2 * w[j])
            b -= self.learning_rate * 2 * grad_b / n  # 切片は正則化しない
        self._scaler = scaler
        self.coef_, self.intercept_ = _to_original_scale(w, b, scaler)
        return self

    def predict(self, X: Sequence[Sequence[float]]) -> list[float]:
        if not self.coef_:
            raise RuntimeError("fit を先に呼んでください")
        return [self.intercept_ + _dot(self.coef_, row) for row in X]


# ---------------------------------------------------------------------------
# 演習2: ロジスティック回帰（SGD + L2）
# ---------------------------------------------------------------------------

def sigmoid(z: float) -> float:
    # exp の引数が大きな正の数にならないよう、z の符号で式を使い分ける
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class LogisticRegressionSGD:
    def __init__(
        self,
        learning_rate: float = 0.1,
        n_epochs: int = 50,
        l2: float = 0.0,
        seed: int = 0,
        standardize: bool = True,
    ):
        if learning_rate <= 0 or n_epochs < 1 or l2 < 0:
            raise ValueError("learning_rate > 0, n_epochs >= 1, l2 >= 0 にしてください")
        self.learning_rate = learning_rate
        self.n_epochs = n_epochs
        self.l2 = l2
        self.seed = seed
        self.standardize = standardize
        self.coef_: list[float] = []
        self.intercept_: float = 0.0
        self.loss_history_: list[float] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "LogisticRegressionSGD":
        d = _validate_xy(X, y)
        if any(t not in (0, 1) for t in y):
            raise ValueError("y は 0 か 1 にしてください")
        scaler = Standardizer().fit(X) if self.standardize else None
        Z = scaler.transform(X) if scaler else [list(row) for row in X]
        rng = random.Random(self.seed)
        order = list(range(len(Z)))
        w = [0.0] * d
        b = 0.0
        self.loss_history_ = []
        for _ in range(self.n_epochs):
            rng.shuffle(order)  # 毎エポック順番を変える（同じ順だと周期的な偏りが出る）
            for i in order:
                z = Z[i]
                # 交差エントロピー損失の勾配は (p - y)·x という簡単な形になる
                g = sigmoid(b + _dot(w, z)) - y[i]
                for j in range(d):
                    w[j] -= self.learning_rate * (g * z[j] + self.l2 * w[j])
                b -= self.learning_rate * g
            probs = [sigmoid(b + _dot(w, z)) for z in Z]
            self.loss_history_.append(log_loss(list(y), probs))
        self.coef_, self.intercept_ = _to_original_scale(w, b, scaler)
        return self

    def decision_function(self, X: Sequence[Sequence[float]]) -> list[float]:
        if not self.coef_:
            raise RuntimeError("fit を先に呼んでください")
        return [self.intercept_ + _dot(self.coef_, row) for row in X]

    def predict_proba(self, X: Sequence[Sequence[float]]) -> list[float]:
        return [sigmoid(z) for z in self.decision_function(X)]

    def predict(self, X: Sequence[Sequence[float]], threshold: float = 0.5) -> list[int]:
        return [int(p >= threshold) for p in self.predict_proba(X)]


# ---------------------------------------------------------------------------
# 演習3: 評価指標
# ---------------------------------------------------------------------------

def _check_binary(y_true: Sequence[int], other: Sequence[Any]) -> None:
    if len(y_true) != len(other):
        raise ValueError("長さが違います")
    if len(y_true) == 0:
        raise ValueError("データが空です")
    if any(t not in (0, 1) for t in y_true):
        raise ValueError("y_true は 0 か 1 にしてください")


def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("長さが違うか、空です")
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    _check_binary(y_true, y_pred)
    if any(p not in (0, 1) for p in y_pred):
        raise ValueError("y_pred は 0 か 1 にしてください")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for t, p in zip(y_true, y_pred):
        key = ("t" if t == p else "f") + ("p" if p == 1 else "n")
        cm[key] += 1
    return cm


def precision_recall_f1(y_true: Sequence[int], y_pred: Sequence[int]) -> tuple[float, float, float]:
    cm = confusion_matrix(y_true, y_pred)
    tp, fp, fn = cm["tp"], cm["fp"], cm["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("長さが違うか、空です")
    return math.sqrt(sum((t - p) ** 2 for t, p in zip(y_true, y_pred)) / len(y_true))


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    if len(y_true) != len(y_pred) or not y_true:
        raise ValueError("長さが違うか、空です")
    return sum(abs(t - p) for t, p in zip(y_true, y_pred)) / len(y_true)


def log_loss(y_true: Sequence[int], probs: Sequence[float], eps: float = 1e-15) -> float:
    _check_binary(y_true, probs)
    total = 0.0
    for t, p in zip(y_true, probs):
        p = min(max(p, eps), 1 - eps)  # log(0) を避ける
        total += -math.log(p) if t == 1 else -math.log(1 - p)
    return total / len(y_true)


def _average_ranks(values: Sequence[float]) -> list[float]:
    """昇順の順位（1 始まり）。同じ値には順位の平均を与える。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # 順位 i+1 〜 j+1 の平均
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def roc_auc(y_true: Sequence[int], scores: Sequence[float]) -> float:
    _check_binary(y_true, scores)
    n_pos = sum(y_true)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        raise ValueError("正例と負例の両方が必要です")
    ranks = _average_ranks(scores)
    rank_sum_pos = sum(r for r, t in zip(ranks, y_true) if t == 1)
    # Mann–Whitney の U 統計量 = 「正例のスコア > 負例のスコア」となるペアの数（同点は 0.5）
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2
    return u / (n_pos * n_neg)


def pr_curve(y_true: Sequence[int], scores: Sequence[float]) -> list[tuple[float, float, float]]:
    _check_binary(y_true, scores)
    n_pos = sum(y_true)
    if n_pos == 0:
        raise ValueError("正例が必要です")
    pairs = sorted(zip(scores, y_true), key=lambda p: p[0], reverse=True)
    curve: list[tuple[float, float, float]] = []
    tp = fp = 0
    i = 0
    while i < len(pairs):
        threshold = pairs[i][0]
        # 同じスコアはまとめて「陽性」に加える（しきい値 = そのスコア、score >= threshold）
        while i < len(pairs) and pairs[i][0] == threshold:
            if pairs[i][1] == 1:
                tp += 1
            else:
                fp += 1
            i += 1
        curve.append((threshold, tp / (tp + fp), tp / n_pos))
    return curve


def average_precision(y_true: Sequence[int], scores: Sequence[float]) -> float:
    ap = 0.0
    prev_recall = 0.0
    for _, precision, recall in pr_curve(y_true, scores):
        ap += (recall - prev_recall) * precision
        prev_recall = recall
    return ap


def best_threshold(
    y_true: Sequence[int], scores: Sequence[float], *, cost_fp: float, cost_fn: float
) -> tuple[float, float]:
    _check_binary(y_true, scores)
    if cost_fp < 0 or cost_fn < 0:
        raise ValueError("コストは 0 以上にしてください")
    # しきい値 +inf（すべて陰性と予測）から始め、スコアの高い順に陽性へ加えていく
    fp, fn = 0, sum(y_true)
    best_t, best_cost = math.inf, fn * cost_fn
    pairs = sorted(zip(scores, y_true), key=lambda p: p[0], reverse=True)
    i = 0
    while i < len(pairs):
        t = pairs[i][0]
        while i < len(pairs) and pairs[i][0] == t:
            if pairs[i][1] == 1:
                fn -= 1
            else:
                fp += 1
            i += 1
        cost = fp * cost_fp + fn * cost_fn
        if cost < best_cost:  # 同じコストなら先に見つかった（大きい）しきい値を残す
            best_t, best_cost = t, cost
    return best_t, best_cost


# ---------------------------------------------------------------------------
# 演習4: k-means（k-means++ 初期化）
# ---------------------------------------------------------------------------

def squared_distance(a: Sequence[float], b: Sequence[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b))


def _validate_points(points: Sequence[Sequence[float]], k: int) -> None:
    if not points:
        raise ValueError("点がありません")
    d = len(points[0])
    if d == 0 or any(len(p) != d for p in points):
        raise ValueError("点の次元がそろっていません")
    if not 1 <= k <= len(points):
        raise ValueError(f"k は 1 以上 点の数以下: k={k}, 点の数={len(points)}")


def kmeans_plus_plus_init(points: Sequence[Sequence[float]], k: int, rng: random.Random) -> Matrix:
    _validate_points(points, k)
    n = len(points)
    centers = [list(points[rng.randrange(n)])]
    d2 = [squared_distance(p, centers[0]) for p in points]
    while len(centers) < k:
        total = sum(d2)
        if total == 0:
            idx = rng.randrange(n)  # 残りの点がすべて既存の中心と重なっている
        else:
            # 既存の中心から遠い点ほど選ばれやすい（確率 ∝ 距離の 2 乗）
            r = rng.random() * total
            acc = 0.0
            idx = n - 1
            for i, w in enumerate(d2):
                acc += w
                if acc > r:
                    idx = i
                    break
        centers.append(list(points[idx]))
        d2 = [min(old, squared_distance(p, centers[-1])) for old, p in zip(d2, points)]
    return centers


@dataclass
class KMeansResult:
    centroids: Matrix
    labels: list[int]
    inertia: float
    n_iter: int
    inertia_history: list[float] = field(default_factory=list)


def _assign(points: Sequence[Sequence[float]], centroids: Matrix) -> list[int]:
    labels = []
    for p in points:
        dists = [squared_distance(p, c) for c in centroids]
        labels.append(dists.index(min(dists)))  # 同じ距離なら番号の小さい方
    return labels


def _inertia(points: Sequence[Sequence[float]], centroids: Matrix, labels: list[int]) -> float:
    return sum(squared_distance(p, centroids[l]) for p, l in zip(points, labels))


def kmeans(
    points: Sequence[Sequence[float]],
    k: int,
    *,
    seed: int = 0,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> KMeansResult:
    _validate_points(points, k)
    rng = random.Random(seed)
    centroids = kmeans_plus_plus_init(points, k, rng)
    d = len(points[0])
    history: list[float] = []
    n_iter = 0
    for n_iter in range(1, max_iter + 1):
        labels = _assign(points, centroids)  # 割り当てステップ
        history.append(_inertia(points, centroids, labels))
        sums = [[0.0] * d for _ in range(k)]
        counts = [0] * k
        for p, l in zip(points, labels):
            counts[l] += 1
            for j in range(d):
                sums[l][j] += p[j]
        new_centroids = [
            [s / counts[c] for s in sums[c]] if counts[c] else list(centroids[c]) for c in range(k)
        ]
        # 空になったクラスタは、今の中心から最も遠い点へ移す（慣性は増えない）
        empty = [c for c in range(k) if counts[c] == 0]
        if empty:
            far = sorted(range(len(points)), key=lambda i: -squared_distance(points[i], centroids[labels[i]]))
            for c, i in zip(empty, far):
                new_centroids[c] = list(points[i])
        shift = max(math.sqrt(squared_distance(a, b)) for a, b in zip(centroids, new_centroids))
        centroids = new_centroids  # 更新ステップ
        if shift <= tol:
            break
    labels = _assign(points, centroids)
    return KMeansResult(centroids, labels, _inertia(points, centroids, labels), n_iter, history)


# ---------------------------------------------------------------------------
# 演習5: 決定木と k 分割交差検証
# ---------------------------------------------------------------------------

def gini(labels: Sequence[Any]) -> float:
    n = len(labels)
    if n == 0:
        return 0.0
    return 1.0 - sum((c / n) ** 2 for c in Counter(labels).values())


def _gini_counts(counts: Counter, n: int) -> float:
    return 1.0 - sum((c / n) ** 2 for c in counts.values()) if n else 0.0


@dataclass
class TreeNode:
    prediction: Any
    n_samples: int
    impurity: float
    feature: int | None = None
    threshold: float | None = None
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None


class DecisionTreeClassifier:
    def __init__(self, max_depth: int | None = None, min_samples_split: int = 2, min_impurity_decrease: float = 0.0):
        if max_depth is not None and max_depth < 0:
            raise ValueError("max_depth は 0 以上か None")
        if min_samples_split < 2:
            raise ValueError("min_samples_split は 2 以上")
        self.max_depth = max_depth
        self.min_samples_split = min_samples_split
        self.min_impurity_decrease = min_impurity_decrease
        self.root_: TreeNode | None = None
        self.feature_importances_: list[float] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[Any]) -> "DecisionTreeClassifier":
        d = _validate_xy(X, y)
        self._X, self._y, self._n_total = X, y, len(y)
        self._importance = [0.0] * d
        self.root_ = self._build(list(range(len(y))), depth=0)
        total = sum(self._importance)
        self.feature_importances_ = [v / total if total > 0 else 0.0 for v in self._importance]
        del self._X, self._y
        return self

    def _best_split(self, idx: list[int]) -> tuple[int, float, float] | None:
        """(特徴量, しきい値, 分割後の重み付き Gini) のうち Gini が最小のもの。"""
        X, y = self._X, self._y
        n = len(idx)
        parent = Counter(y[i] for i in idx)
        best: tuple[int, float, float] | None = None
        for j in range(len(X[0])):
            order = sorted(idx, key=lambda i: X[i][j])
            left: Counter = Counter()
            right = parent.copy()
            # ソート済みの順に 1 点ずつ左へ移しながら、クラスの数を差分で更新する（O(n log n)）
            for pos in range(n - 1):
                label = y[order[pos]]
                left[label] += 1
                right[label] -= 1
                xv, x_next = X[order[pos]][j], X[order[pos + 1]][j]
                if xv == x_next:
                    continue  # 同じ値の間では切れない
                n_left = pos + 1
                n_right = n - n_left
                g = (n_left * _gini_counts(left, n_left) + n_right * _gini_counts(right, n_right)) / n
                if best is None or g < best[2] - 1e-12:  # 同点なら先に見つかったもの
                    best = (j, (xv + x_next) / 2, g)
        return best

    def _build(self, idx: list[int], depth: int) -> TreeNode:
        labels = [self._y[i] for i in idx]
        counts = Counter(labels)
        top = max(counts.values())
        prediction = min(c for c, v in counts.items() if v == top)  # 同数なら小さいラベル
        node = TreeNode(prediction, len(idx), gini(labels))
        if (
            node.impurity == 0.0
            or (self.max_depth is not None and depth >= self.max_depth)
            or len(idx) < self.min_samples_split
        ):
            return node
        split = self._best_split(idx)
        if split is None:
            return node
        j, threshold, child_impurity = split
        decrease = len(idx) / self._n_total * (node.impurity - child_impurity)
        if decrease < self.min_impurity_decrease:
            return node
        self._importance[j] += decrease
        left_idx = [i for i in idx if self._X[i][j] <= threshold]
        right_idx = [i for i in idx if self._X[i][j] > threshold]
        node.feature, node.threshold = j, threshold
        node.left = self._build(left_idx, depth + 1)
        node.right = self._build(right_idx, depth + 1)
        return node

    def predict(self, X: Sequence[Sequence[float]]) -> list[Any]:
        if self.root_ is None:
            raise RuntimeError("fit を先に呼んでください")
        out = []
        for row in X:
            node = self.root_
            while not node.is_leaf:
                node = node.left if row[node.feature] <= node.threshold else node.right
            out.append(node.prediction)
        return out

    def depth(self) -> int:
        if self.root_ is None:
            raise RuntimeError("fit を先に呼んでください")

        def rec(node: TreeNode) -> int:
            return 0 if node.is_leaf else 1 + max(rec(node.left), rec(node.right))

        return rec(self.root_)

    def n_leaves(self) -> int:
        if self.root_ is None:
            raise RuntimeError("fit を先に呼んでください")

        def rec(node: TreeNode) -> int:
            return 1 if node.is_leaf else rec(node.left) + rec(node.right)

        return rec(self.root_)


def k_fold_indices(n: int, k: int, *, shuffle: bool = True, seed: int = 0) -> list[tuple[list[int], list[int]]]:
    if k < 2 or k > n:
        raise ValueError(f"k は 2 以上 n 以下: k={k}, n={n}")
    idx = list(range(n))
    if shuffle:
        random.Random(seed).shuffle(idx)
    base, extra = divmod(n, k)
    folds = []
    start = 0
    for f in range(k):
        size = base + (1 if f < extra else 0)
        test = idx[start:start + size]
        train = idx[:start] + idx[start + size:]
        folds.append((train, test))
        start += size
    return folds


def cross_val_score(
    model_factory: Callable[[], Any],
    X: Sequence[Sequence[float]],
    y: Sequence[Any],
    *,
    k: int = 5,
    seed: int = 0,
    metric: Callable[[Sequence[Any], Sequence[Any]], float] = accuracy,
) -> list[float]:
    _validate_xy(X, y)
    scores = []
    for train, test in k_fold_indices(len(X), k, seed=seed):
        model = model_factory()  # 分割ごとに新しいモデル（前の分割の学習結果を持ち越さない）
        model.fit([X[i] for i in train], [y[i] for i in train])
        pred = model.predict([X[i] for i in test])
        scores.append(metric([y[i] for i in test], pred))
    return scores
