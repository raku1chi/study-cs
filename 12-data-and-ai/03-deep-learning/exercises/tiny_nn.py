"""12.3 深層学習とTransformer — 演習2: 自動微分の上に作る小さなニューラルネットワーク（★★★）

演習1の autodiff.Value だけを使って、多層パーセプトロン（MLP）、損失関数、最適化手法（SGD・Adam）、
学習ループを作り、XOR と同心円のデータを分類できるように学習させます。
（演習1を先に完成させてください。この演習は autodiff.py を import します。）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.3
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_tiny_nn

スカラーの自動微分は遅いので、ネットワークとデータはごく小さくしています（テストは数秒で終わります）。
"""
from __future__ import annotations

import math
import random
from typing import Sequence

from autodiff import Value

Input = Sequence["Value | float"]


# ---------------------------------------------------------------------------
# 実装済み: データセット
# ---------------------------------------------------------------------------

def make_xor_dataset() -> tuple[list[list[float]], list[int]]:
    """XOR の 4 点。直線 1 本では分けられない、最も小さな例。"""
    X = [[-1.0, -1.0], [-1.0, 1.0], [1.0, -1.0], [1.0, 1.0]]
    y = [0, 1, 1, 0]
    return X, y


def make_circles(n: int, *, noise: float = 0.08, factor: float = 0.4, seed: int = 0) -> tuple[list[list[float]], list[int]]:
    """半径 1 の円（ラベル 0）と半径 factor の円（ラベル 1）の上の点を交互に n 個作る。"""
    rng = random.Random(seed)
    X: list[list[float]] = []
    y: list[int] = []
    for i in range(n):
        inner = i % 2
        r = factor if inner else 1.0
        theta = rng.uniform(0, 2 * math.pi)
        X.append([r * math.cos(theta) + rng.gauss(0, noise), r * math.sin(theta) + rng.gauss(0, noise)])
        y.append(inner)
    return X, y


# ---------------------------------------------------------------------------
# 演習2a（★★☆）: 層とモデル
# ---------------------------------------------------------------------------

ACTIVATIONS = ("tanh", "relu", "linear")


class Module:
    """パラメータを持つ部品の基底クラス（実装済み）。"""

    def parameters(self) -> list[Value]:
        return []

    def zero_grad(self) -> None:
        for p in self.parameters():
            p.grad = 0.0


class Neuron(Module):
    """1 つのニューロン: activation(Σ w_i x_i + b)。

    - 重み w は n_in 個の Value。rng.gauss(0, std) で 1 つずつ順に初期化する。
      std は activation が "relu" なら √(2/n_in)（He の初期化）、それ以外は √(1/n_in)（LeCun の初期化）。
    - バイアス b は Value(0.0)。
    - activation は "tanh" / "relu" / "linear" のどれか（それ以外は ValueError）。n_in < 1 も ValueError。
    - __call__ は入力の長さが n_in でなければ ValueError。
    - parameters() は w のリストの後ろに b を付けたもの。
    """

    def __init__(self, n_in: int, rng: random.Random, activation: str = "tanh") -> None:
        raise NotImplementedError("演習2a: Neuron.__init__ を実装してください")

    def __call__(self, x: Input) -> Value:
        raise NotImplementedError("演習2a: Neuron.__call__ を実装してください")

    def parameters(self) -> list[Value]:
        raise NotImplementedError("演習2a: Neuron.parameters を実装してください")


class Layer(Module):
    """n_out 個のニューロンを並べた全結合層。出力は Value のリスト。n_out < 1 なら ValueError。"""

    def __init__(self, n_in: int, n_out: int, rng: random.Random, activation: str = "tanh") -> None:
        raise NotImplementedError("演習2a: Layer.__init__ を実装してください")

    def __call__(self, x: Input) -> list[Value]:
        raise NotImplementedError("演習2a: Layer.__call__ を実装してください")

    def parameters(self) -> list[Value]:
        raise NotImplementedError("演習2a: Layer.parameters を実装してください")


class MLP(Module):
    """多層パーセプトロン。MLP(2, [8, 1], rng) は 2 入力 → 隠れ層 8 → 出力 1。

    - 隠れ層には activation を使い、**最後の層は "linear"**（出力はロジット。シグモイドは損失の側で扱う）。
    - 層は前から順に作る（乱数を使う順番が決まるように）。layer_sizes が空なら ValueError。
    - __call__ は最後の層の出力（Value のリスト）を返す。
    """

    def __init__(self, n_in: int, layer_sizes: Sequence[int], rng: random.Random, activation: str = "tanh") -> None:
        raise NotImplementedError("演習2a: MLP.__init__ を実装してください")

    def __call__(self, x: Input) -> list[Value]:
        raise NotImplementedError("演習2a: MLP.__call__ を実装してください")

    def parameters(self) -> list[Value]:
        raise NotImplementedError("演習2a: MLP.parameters を実装してください")


# ---------------------------------------------------------------------------
# 演習2b（★★☆）: 損失関数
# ---------------------------------------------------------------------------

def bce_with_logits(logit: Value, target: int) -> Value:
    """ロジット z と正解 y（0 か 1）の 2 値交差エントロピー: -[y log σ(z) + (1-y) log(1-σ(z))]。

    数値的に安定な形 max(z, 0) - z·y + log(1 + e^(-|z|)) で値を計算し、
    局所勾配 σ(z) - y を与えた「融合した演算」として Value(損失, (logit,), (σ(z) - y,)) を返す。
    （log や exp の Value 演算を組み合わせると、|z| が大きいときに log(0) やオーバーフローが起きる）
    target が 0/1 以外なら ValueError。
    """
    raise NotImplementedError("演習2b: bce_with_logits を実装してください")


def mse_loss(pred: Value, target: float) -> Value:
    """二乗誤差 (pred - target)²（Value の演算で書けばよい）。"""
    raise NotImplementedError("演習2b: mse_loss を実装してください")


# ---------------------------------------------------------------------------
# 演習2c（★★☆）: 最適化手法
# ---------------------------------------------------------------------------

class SGD:
    """モメンタム付き確率的勾配降下法（PyTorch と同じ形）。

        v ← momentum·v + grad
        p ← p - lr·v

    lr <= 0 または momentum が [0, 1) の外なら ValueError。
    """

    def __init__(self, params: Sequence[Value], lr: float = 0.1, momentum: float = 0.0) -> None:
        raise NotImplementedError("演習2c: SGD.__init__ を実装してください")

    def zero_grad(self) -> None:
        """全パラメータの grad を 0 にする。"""
        raise NotImplementedError("演習2c: SGD.zero_grad を実装してください")

    def step(self) -> None:
        """各パラメータの grad を使って data を更新する。"""
        raise NotImplementedError("演習2c: SGD.step を実装してください")


class Adam:
    """Adam（Kingma & Ba, 2015）。ステップ数 t を 1 から数え、パラメータごとに:

        m ← β1·m + (1-β1)·g           （勾配の移動平均）
        v ← β2·v + (1-β2)·g²          （勾配の二乗の移動平均）
        m̂ = m / (1 - β1^t)、 v̂ = v / (1 - β2^t)   （0 初期化による偏りの補正）
        p ← p - lr·m̂ / (√v̂ + eps)

    lr <= 0 または β1, β2 が [0, 1) の外なら ValueError。
    """

    def __init__(
        self, params: Sequence[Value], lr: float = 0.01, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8
    ) -> None:
        raise NotImplementedError("演習2c: Adam.__init__ を実装してください")

    def zero_grad(self) -> None:
        raise NotImplementedError("演習2c: Adam.zero_grad を実装してください")

    def step(self) -> None:
        raise NotImplementedError("演習2c: Adam.step を実装してください")


# ---------------------------------------------------------------------------
# 演習2d（★★☆）: 学習と予測
# ---------------------------------------------------------------------------

def train_binary_classifier(
    model: MLP,
    X: Sequence[Sequence[float]],
    y: Sequence[int],
    *,
    optimizer: SGD | Adam,
    epochs: int,
    batch_size: int,
    rng: random.Random,
) -> list[float]:
    """ミニバッチ学習で 2 値分類器を学習させ、エポックごとの平均損失のリストを返す。

    各エポックで:
    1. データの順番（添字のリスト）を rng.shuffle で並べ替える。
    2. 先頭から batch_size 件ずつ取り出し、各バッチで
       optimizer.zero_grad() → 損失 = バッチ内の bce_with_logits(model(x)[0], y) の平均
       → 損失.backward() → optimizer.step()
    3. そのエポックの損失の平均（各バッチの損失 × 件数の合計 ÷ データ数）を記録する。

    X と y の件数が違う・空、epochs < 1、batch_size < 1 なら ValueError。
    """
    raise NotImplementedError("演習2d: train_binary_classifier を実装してください")


def predict_proba(model: MLP, X: Sequence[Sequence[float]]) -> list[float]:
    """各入力について σ(ロジット) を float で返す（学習しないので勾配の計算は不要）。"""
    raise NotImplementedError("演習2d: predict_proba を実装してください")


def predict(model: MLP, X: Sequence[Sequence[float]], threshold: float = 0.5) -> list[int]:
    """確率が threshold 以上なら 1、それ以外は 0。"""
    raise NotImplementedError("演習2d: predict を実装してください")
