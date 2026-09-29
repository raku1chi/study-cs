"""12.2 機械学習の基礎 — 演習: ライブラリなしで作る機械学習

scikit-learn や NumPy を使わず、純粋な Python で機械学習の中核を実装します。
行列は「リストのリスト」（X[i][j] = i 番目のデータの j 番目の特徴量）で表します。

    演習1（★★☆）線形回帰: 閉じた式による単回帰、標準化、勾配降下法による重回帰（L2 正則化）
    演習2（★★☆）ロジスティック回帰: 安定なシグモイド、SGD、L2 正則化
    演習3（★★☆）評価指標: 混同行列、適合率・再現率・F1、ROC-AUC（順位統計量・同点対応）、
                 PR 曲線と平均適合率、log loss、RMSE/MAE、コストに基づくしきい値の選択
    演習4（★★☆）k-means と k-means++ による初期化（シード付き）
    演習5（★★★）決定木（Gini 不純度、max_depth、min_samples_split）と k 分割交差検証

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.2
    python3 tools/check.py -v 12.2
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_ml_scratch

データの生成には ml_datasets.py（実装済み）を使います。
制約: 標準ライブラリ（math, random, collections など）だけを使ってください。
"""
from __future__ import annotations

import math  # noqa: F401
import random  # noqa: F401
from collections import Counter  # noqa: F401  演習5で使えます
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

Matrix = list[list[float]]


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 線形回帰
# ---------------------------------------------------------------------------

def simple_linear_regression(xs: Sequence[float], ys: Sequence[float]) -> tuple[float, float]:
    """単回帰 y = slope·x + intercept を最小二乗法の閉じた式で求め、(slope, intercept) を返す。

    slope = Σ(x - x̄)(y - ȳ) / Σ(x - x̄)²、intercept = ȳ - slope·x̄

    - 長さが違う、2 点未満、x がすべて同じ値（傾きが決まらない）なら ValueError。

    >>> simple_linear_regression([0, 1, 2, 3], [2, 5, 8, 11])
    (3.0, 2.0)
    """
    raise NotImplementedError("演習1: simple_linear_regression を実装してください")


class Standardizer:
    """各特徴量（列）を平均 0・標準偏差 1 に変換する（z = (x - 平均) / 標準偏差）。

    - 標準偏差は母標準偏差（n で割る）。
    - 標準偏差が 0 の列（定数の列）は、0 で割らないように標準偏差を 1 とみなす。
    - fit の前に transform を呼んだら RuntimeError。空のデータで fit したら ValueError。
    """

    def __init__(self) -> None:
        self.means_: list[float] = []
        self.stds_: list[float] = []

    def fit(self, X: Sequence[Sequence[float]]) -> "Standardizer":
        """列ごとの平均と標準偏差を means_ / stds_ に保存し、self を返す。"""
        raise NotImplementedError("演習1: Standardizer.fit を実装してください")

    def transform(self, X: Sequence[Sequence[float]]) -> Matrix:
        """保存した平均・標準偏差で X を変換した新しい行列を返す。"""
        raise NotImplementedError("演習1: Standardizer.transform を実装してください")

    def fit_transform(self, X: Sequence[Sequence[float]]) -> Matrix:
        return self.fit(X).transform(X)


class LinearRegressionGD:
    """勾配降下法（全データを使う最急降下法）による線形回帰。

    損失: L(w, b) = (1/n) Σ (b + w·z_i - y_i)² + l2·‖w‖²   （z_i は標準化した特徴量。b は正則化しない）
    勾配: ∂L/∂w_j = (2/n) Σ err_i·z_ij + 2·l2·w_j、 ∂L/∂b = (2/n) Σ err_i   （err_i = 予測 - 正解）

    fit の手順:
    1. standardize=True なら Standardizer で X を標準化する（False ならそのまま使う）。
    2. w = 0, b = 0 から始め、n_epochs 回、「損失を計算して loss_history_ に追加 → 勾配で更新」
       を繰り返す（loss_history_[0] は初期値での損失）。
       損失が有限でなくなったら（発散）、その値（inf や nan）を追加したところで打ち切る。
       注意: 発散すると誤差が非常に大きくなる。float の `err ** 2` や math.pow は範囲を超えると
       OverflowError を送出するが、`err * err` なら inf になるので、二乗は掛け算で計算すること。
    3. 学習した (w, b) を **元の特徴量のスケール** に戻して coef_ / intercept_ に保存する:
       b + Σ w_j (x_j - μ_j)/σ_j = (b - Σ w_j μ_j/σ_j) + Σ (w_j/σ_j) x_j

    - X が空、X と y の件数が違う、X の行の長さがそろっていなければ ValueError。
    - fit の前に predict を呼んだら RuntimeError。
    """

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
        raise NotImplementedError("演習1: LinearRegressionGD.fit を実装してください")

    def predict(self, X: Sequence[Sequence[float]]) -> list[float]:
        """intercept_ + coef_·x を返す（元のスケールの X をそのまま受け取る）。"""
        raise NotImplementedError("演習1: LinearRegressionGD.predict を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ロジスティック回帰（SGD + L2）
# ---------------------------------------------------------------------------

def sigmoid(z: float) -> float:
    """σ(z) = 1 / (1 + e^(-z)) を、オーバーフローしないように計算する。

    ヒント: z が大きな負の数だと e^(-z) が巨大になり OverflowError になる。
    z < 0 のときは同じ値を e^z / (1 + e^z) で計算する。

    >>> sigmoid(0)
    0.5
    >>> sigmoid(-1000)     # OverflowError にならない
    0.0
    """
    raise NotImplementedError("演習2: sigmoid を実装してください")


class LogisticRegressionSGD:
    """確率的勾配降下法（SGD、1 件ずつ更新）によるロジスティック回帰。

    目的関数: J = (1/n) Σ ℓ_i + (l2/2)·‖w‖²、ℓ_i = -[y log p + (1-y) log(1-p)]、p = σ(b + w·z_i)
    1 件ぶんの更新（g = p - y_i）:
        w_j ← w_j - learning_rate·(g·z_ij + l2·w_j)
        b   ← b   - learning_rate·g              （切片は正則化しない）

    fit の手順:
    1. y が 0/1 以外を含めば ValueError（形のチェックは線形回帰と同じ）。
    2. standardize=True なら標準化する。
    3. rng = random.Random(seed) を 1 つ作り、各エポックの最初にデータの順番を rng.shuffle で並べ替え、
       その順に 1 件ずつ更新する。エポックの終わりに、学習データ全体の log_loss（正則化項なし）を
       loss_history_ に追加する。
    4. 線形回帰と同じ方法で、coef_ / intercept_ を元の特徴量のスケールに戻して保存する。
    """

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
        raise NotImplementedError("演習2: LogisticRegressionSGD.fit を実装してください")

    def decision_function(self, X: Sequence[Sequence[float]]) -> list[float]:
        """ロジット intercept_ + coef_·x を返す。fit 前なら RuntimeError。"""
        raise NotImplementedError("演習2: decision_function を実装してください")

    def predict_proba(self, X: Sequence[Sequence[float]]) -> list[float]:
        """クラス 1 である確率 σ(ロジット) を返す。"""
        raise NotImplementedError("演習2: predict_proba を実装してください")

    def predict(self, X: Sequence[Sequence[float]], threshold: float = 0.5) -> list[int]:
        """確率が threshold 以上なら 1、それ以外は 0。"""
        raise NotImplementedError("演習2: predict を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 評価指標（2 値分類は正例 = 1、負例 = 0）
# ---------------------------------------------------------------------------
# 共通: 長さが違う・空・y_true に 0/1 以外がある場合は ValueError。

def accuracy(y_true: Sequence[Any], y_pred: Sequence[Any]) -> float:
    """正解率。ラベルは 0/1 に限らない（多クラス・文字列でもよい）。"""
    raise NotImplementedError("演習3: accuracy を実装してください")


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int]) -> dict[str, int]:
    """{"tp": 真陽性, "fp": 偽陽性, "fn": 偽陰性, "tn": 真陰性} を返す。y_pred も 0/1 のみ。"""
    raise NotImplementedError("演習3: confusion_matrix を実装してください")


def precision_recall_f1(y_true: Sequence[int], y_pred: Sequence[int]) -> tuple[float, float, float]:
    """(適合率, 再現率, F1) を返す。分母が 0 になる指標は 0.0 とする。

    適合率 = TP/(TP+FP)、再現率 = TP/(TP+FN)、F1 = 2PR/(P+R)
    """
    raise NotImplementedError("演習3: precision_recall_f1 を実装してください")


def rmse(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """二乗平均平方根誤差 √(mean((y - ŷ)²))。"""
    raise NotImplementedError("演習3: rmse を実装してください")


def mae(y_true: Sequence[float], y_pred: Sequence[float]) -> float:
    """平均絶対誤差 mean(|y - ŷ|)。"""
    raise NotImplementedError("演習3: mae を実装してください")


def log_loss(y_true: Sequence[int], probs: Sequence[float], eps: float = 1e-15) -> float:
    """平均の交差エントロピー -mean(y log p + (1-y) log(1-p))。

    p は [eps, 1-eps] にクリップしてから log をとる（log(0) を避ける）。
    """
    raise NotImplementedError("演習3: log_loss を実装してください")


def roc_auc(y_true: Sequence[int], scores: Sequence[float]) -> float:
    """ROC 曲線の下の面積（AUC）を、順位統計量（Mann–Whitney の U）で計算する。

    AUC は「ランダムに選んだ正例のスコアが、ランダムに選んだ負例のスコアより高い確率」
    （同点は 0.5 と数える）に等しい。O(n²) の総当たりではなく、次の手順で O(n log n) にする:
    1. 全スコアを昇順に並べて順位（1 始まり）を付ける。同じスコアには順位の平均を与える
       （例: 2 位と 3 位が同点なら両方 2.5 位）。
    2. R = 正例の順位の和、U = R - n_pos(n_pos + 1)/2、AUC = U / (n_pos · n_neg)

    - 正例か負例のどちらかがなければ ValueError。
    """
    raise NotImplementedError("演習3: roc_auc を実装してください")


def pr_curve(y_true: Sequence[int], scores: Sequence[float]) -> list[tuple[float, float, float]]:
    """適合率-再現率曲線。異なるスコアの値を大きい順にしきい値とし、各しきい値 t について
    「score >= t なら陽性」と予測したときの (t, 適合率, 再現率) を並べたリストを返す。

    - 正例がなければ ValueError。

    >>> pr_curve([1, 0, 1, 1, 0], [0.9, 0.8, 0.7, 0.7, 0.1])   # doctest: +SKIP
    [(0.9, 1.0, 0.333...), (0.8, 0.5, 0.333...), (0.7, 0.75, 1.0), (0.1, 0.6, 1.0)]
    """
    raise NotImplementedError("演習3: pr_curve を実装してください")


def average_precision(y_true: Sequence[int], scores: Sequence[float]) -> float:
    """平均適合率 AP = Σ_k (R_k - R_{k-1})·P_k（pr_curve の順に。R_0 = 0）。PR-AUC の代表的な推定値。"""
    raise NotImplementedError("演習3: average_precision を実装してください")


def best_threshold(
    y_true: Sequence[int], scores: Sequence[float], *, cost_fp: float, cost_fn: float
) -> tuple[float, float]:
    """誤検知 1 件のコスト cost_fp と見逃し 1 件のコスト cost_fn から、総コストが最小のしきい値を選ぶ。

    - 候補は +inf（すべて陰性）と、各スコアの値（score >= t なら陽性）。
    - 総コスト = FP 数 × cost_fp + FN 数 × cost_fn。戻り値は (しきい値, 総コスト)。
    - 総コストが同じなら、大きい方のしきい値を選ぶ。コストが負なら ValueError。
    """
    raise NotImplementedError("演習3: best_threshold を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: k-means と k-means++
# ---------------------------------------------------------------------------

def squared_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """ユークリッド距離の 2 乗。"""
    raise NotImplementedError("演習4: squared_distance を実装してください")


def kmeans_plus_plus_init(points: Sequence[Sequence[float]], k: int, rng: random.Random) -> Matrix:
    """k-means++ で k 個の初期中心を選ぶ（Arthur & Vassilvitskii, 2007）。

    1. 最初の中心を points から一様に 1 つ選ぶ（rng.randrange）。
    2. 各点について、選んだ中心のうち最も近いものまでの距離の 2 乗 D(x)² を求める。
    3. 次の中心を、確率 D(x)² / ΣD² で選ぶ（ヒント: r = rng.random() × ΣD² を求め、
       D² を先頭から足していって初めて r を超えた点を選ぶ）。ΣD² = 0 なら一様に選ぶ。
    4. k 個になるまで 2〜3 を繰り返す。中心は点のコピー（list）で返す。

    - points が空、次元がそろっていない、k が 1 未満または点の数より大きい場合は ValueError。
    """
    raise NotImplementedError("演習4: kmeans_plus_plus_init を実装してください")


@dataclass
class KMeansResult:
    """k-means の結果（実装済み）。"""

    centroids: Matrix  # k 個の中心
    labels: list[int]  # 各点が属するクラスタの番号
    inertia: float  # 慣性（各点と所属する中心の距離の 2 乗の総和）
    n_iter: int  # 実行した反復の回数
    inertia_history: list[float] = field(default_factory=list)  # 各反復の割り当て直後の慣性


def kmeans(
    points: Sequence[Sequence[float]],
    k: int,
    *,
    seed: int = 0,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> KMeansResult:
    """Lloyd のアルゴリズムによる k-means。

    1. rng = random.Random(seed) で kmeans_plus_plus_init を呼び、初期中心を決める。
    2. 最大 max_iter 回、次を繰り返す（反復の回数を n_iter とする）:
       a. 割り当て: 各点を最も近い中心に割り当てる（同じ距離なら番号の小さい中心）。
          この時点の慣性を inertia_history に追加する。
       b. 更新: 各クラスタの中心を、属する点の平均にする。
          点が 1 つもないクラスタは、現在の中心から最も遠い点（割り当て先の中心との距離が
          最大の点）の位置へ移す（空のクラスタが複数あれば、遠い順に別々の点へ）。
       c. 中心の移動距離の最大値が tol 以下なら終了。
    3. 最後の中心で割り当て直し、labels と inertia を求めて KMeansResult を返す。

    この手順では、inertia_history は単調に減少する（増えない）。テストで確かめる。
    """
    raise NotImplementedError("演習4: kmeans を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: 決定木と k 分割交差検証
# ---------------------------------------------------------------------------

def gini(labels: Sequence[Any]) -> float:
    """Gini 不純度 1 - Σ_c p_c²（p_c はクラス c の割合）。空なら 0.0。

    >>> gini([0, 1, 0, 1])
    0.5
    """
    raise NotImplementedError("演習5: gini を実装してください")


@dataclass
class TreeNode:
    """決定木のノード（実装済み）。葉なら feature / threshold / left / right は None。"""

    prediction: Any  # このノードに来たデータの多数派のクラス
    n_samples: int
    impurity: float  # このノードの Gini 不純度
    feature: int | None = None  # 分割に使う特徴量の番号
    threshold: float | None = None  # x[feature] <= threshold なら左、それ以外は右
    left: "TreeNode | None" = None
    right: "TreeNode | None" = None

    @property
    def is_leaf(self) -> bool:
        return self.left is None


class DecisionTreeClassifier:
    """CART 流の分類木（Gini 不純度で 2 分割を繰り返す）。

    ノードの作り方（再帰）:
    - prediction は多数派のクラス（同数なら小さいラベル）。impurity は gini。
    - 次のどれかなら葉にする: 不純度が 0、深さが max_depth に達した（根の深さは 0）、
      サンプル数が min_samples_split 未満、分割の候補がない。
    - 最良の分割: すべての特徴量 j と、x_j の **隣り合う異なる値の中点** をしきい値の候補とし、
      分割後の重み付き Gini（(n_左·Gini_左 + n_右·Gini_右) / n）が最小のものを選ぶ。
      同じ値なら、特徴量の番号が小さい方、次にしきい値が小さい方を選ぶ。
    - 不純度の減少量 decrease = (ノードのサンプル数 / 全サンプル数) × (impurity - 分割後の重み付き Gini)
      が min_impurity_decrease 未満なら葉にする（既定の 0.0 では、減少量 0 の分割も行う。
      XOR のように 1 回目の分割では改善しない問題を解くため。scikit-learn と同じ扱い）。
    - feature_importances_[j] は、特徴量 j の分割による decrease の合計を、全体の合計で割った値
      （分割が 1 つもなければすべて 0.0）。

    ヒント: 特徴量ごとにデータをソートし、1 点ずつ左に移しながらクラスの個数を差分更新すると、
    しきい値の候補すべてを O(n log n) で評価できる。

    - fit の前に predict / depth / n_leaves を呼んだら RuntimeError。
    """

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
        raise NotImplementedError("演習5: DecisionTreeClassifier.fit を実装してください")

    def predict(self, X: Sequence[Sequence[float]]) -> list[Any]:
        """根から、x[feature] <= threshold なら左・それ以外は右へたどり、葉の prediction を返す。"""
        raise NotImplementedError("演習5: DecisionTreeClassifier.predict を実装してください")

    def depth(self) -> int:
        """木の深さ（根だけなら 0）。"""
        raise NotImplementedError("演習5: DecisionTreeClassifier.depth を実装してください")

    def n_leaves(self) -> int:
        """葉の数。"""
        raise NotImplementedError("演習5: DecisionTreeClassifier.n_leaves を実装してください")


def k_fold_indices(n: int, k: int, *, shuffle: bool = True, seed: int = 0) -> list[tuple[list[int], list[int]]]:
    """0〜n-1 の添字を k 個の分割に分け、(学習用の添字, 検証用の添字) のリストを返す。

    - shuffle=True なら random.Random(seed).shuffle で添字を並べ替えてから分ける。
    - 検証用は、並べた添字を先頭から連続して切り出す。サイズの差は最大 1 で、大きい分割を先頭側に置く。
    - 学習用は、検証用以外の添字（並べた順）。
    - k < 2 または k > n なら ValueError。

    >>> k_fold_indices(6, 3, shuffle=False)[0]
    ([2, 3, 4, 5], [0, 1])
    """
    raise NotImplementedError("演習5: k_fold_indices を実装してください")


def cross_val_score(
    model_factory: Callable[[], Any],
    X: Sequence[Sequence[float]],
    y: Sequence[Any],
    *,
    k: int = 5,
    seed: int = 0,
    metric: Callable[[Sequence[Any], Sequence[Any]], float] = accuracy,
) -> list[float]:
    """k 分割交差検証。分割は k_fold_indices(len(X), k, seed=seed)（shuffle=True）で作る。
    分割ごとに model_factory() で **新しい** モデルを作り、学習用で fit し、
    検証用で predict して metric(正解, 予測) を計算する。k 個のスコアのリストを返す。

    >>> cross_val_score(lambda: DecisionTreeClassifier(max_depth=3), X, y, k=5)   # doctest: +SKIP
    [0.85, 0.95, 0.866..., 0.966..., 0.9]
    """
    raise NotImplementedError("演習5: cross_val_score を実装してください")
