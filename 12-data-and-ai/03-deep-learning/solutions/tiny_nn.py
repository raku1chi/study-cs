"""12.3 深層学習とTransformer — 演習2: 自動微分の上に作る小さなニューラルネットワーク（解答例）

演習の仕様は exercises/tiny_nn.py の docstring を参照してください。
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
    X = [[-1.0, -1.0], [-1.0, 1.0], [1.0, -1.0], [1.0, 1.0]]
    y = [0, 1, 1, 0]
    return X, y


def make_circles(n: int, *, noise: float = 0.08, factor: float = 0.4, seed: int = 0) -> tuple[list[list[float]], list[int]]:
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
# 演習2a: 層とモデル
# ---------------------------------------------------------------------------

ACTIVATIONS = ("tanh", "relu", "linear")


class Module:
    def parameters(self) -> list[Value]:
        return []

    def zero_grad(self) -> None:
        for p in self.parameters():
            p.grad = 0.0


class Neuron(Module):
    def __init__(self, n_in: int, rng: random.Random, activation: str = "tanh") -> None:
        if n_in < 1:
            raise ValueError("n_in は 1 以上")
        if activation not in ACTIVATIONS:
            raise ValueError(f"未知の活性化関数: {activation}")
        # 入力の数に応じて初期値の大きさを決める。大きすぎると tanh が飽和し、小さすぎると信号が消える。
        # tanh・線形は LeCun の初期化（分散 1/n_in）、ReLU は He の初期化（分散 2/n_in）
        std = math.sqrt(2.0 / n_in) if activation == "relu" else math.sqrt(1.0 / n_in)
        self.w = [Value(rng.gauss(0.0, std)) for _ in range(n_in)]
        self.b = Value(0.0)
        self.activation = activation

    def __call__(self, x: Input) -> Value:
        if len(x) != len(self.w):
            raise ValueError(f"入力の次元が違います: {len(x)} != {len(self.w)}")
        z = self.b
        for wi, xi in zip(self.w, x):
            z = z + wi * xi
        if self.activation == "tanh":
            return z.tanh()
        if self.activation == "relu":
            return z.relu()
        return z

    def parameters(self) -> list[Value]:
        return self.w + [self.b]


class Layer(Module):
    def __init__(self, n_in: int, n_out: int, rng: random.Random, activation: str = "tanh") -> None:
        if n_out < 1:
            raise ValueError("n_out は 1 以上")
        self.neurons = [Neuron(n_in, rng, activation) for _ in range(n_out)]

    def __call__(self, x: Input) -> list[Value]:
        return [neuron(x) for neuron in self.neurons]

    def parameters(self) -> list[Value]:
        return [p for n in self.neurons for p in n.parameters()]


class MLP(Module):
    def __init__(self, n_in: int, layer_sizes: Sequence[int], rng: random.Random, activation: str = "tanh") -> None:
        if not layer_sizes:
            raise ValueError("layer_sizes は 1 つ以上")
        sizes = [n_in, *layer_sizes]
        self.layers = [
            # 最後の層は線形（出力はロジットや回帰値。活性化は損失関数の側で扱う）
            Layer(sizes[i], sizes[i + 1], rng, activation if i < len(layer_sizes) - 1 else "linear")
            for i in range(len(layer_sizes))
        ]

    def __call__(self, x: Input) -> list[Value]:
        out: Input = x
        for layer in self.layers:
            out = layer(out)
        return list(out)

    def parameters(self) -> list[Value]:
        return [p for layer in self.layers for p in layer.parameters()]


# ---------------------------------------------------------------------------
# 演習2b: 損失関数
# ---------------------------------------------------------------------------

def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def bce_with_logits(logit: Value, target: int) -> Value:
    if target not in (0, 1):
        raise ValueError("target は 0 か 1")
    z = logit.data
    # loss = log(1 + e^z) - y·z を、e^z があふれない形で計算する
    loss = max(z, 0.0) - z * target + math.log1p(math.exp(-abs(z)))
    # 勾配は σ(z) - y という簡単な形。複数の演算を組み合わせる代わりに「融合した演算」として
    # 自分で局所勾配を与える（深層学習フレームワークの BCEWithLogits と同じ考え方）
    return Value(loss, (logit,), (_sigmoid(z) - target,), "bce_with_logits")


def mse_loss(pred: Value, target: float) -> Value:
    return (pred - target) ** 2


# ---------------------------------------------------------------------------
# 演習2c: 最適化手法
# ---------------------------------------------------------------------------

class SGD:
    def __init__(self, params: Sequence[Value], lr: float = 0.1, momentum: float = 0.0) -> None:
        if lr <= 0 or not 0 <= momentum < 1:
            raise ValueError("lr > 0, 0 <= momentum < 1")
        self.params = list(params)
        self.lr = lr
        self.momentum = momentum
        self.velocity = [0.0] * len(self.params)

    def zero_grad(self) -> None:
        for p in self.params:
            p.grad = 0.0

    def step(self) -> None:
        for i, p in enumerate(self.params):
            # 慣性（モメンタム）: 過去の勾配の指数移動和の方向へ進む。谷底の振動を抑え、平らな所で加速する
            self.velocity[i] = self.momentum * self.velocity[i] + p.grad
            p.data -= self.lr * self.velocity[i]


class Adam:
    def __init__(
        self, params: Sequence[Value], lr: float = 0.01, beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8
    ) -> None:
        if lr <= 0 or not (0 <= beta1 < 1 and 0 <= beta2 < 1):
            raise ValueError("lr > 0, 0 <= beta1, beta2 < 1")
        self.params = list(params)
        self.lr, self.beta1, self.beta2, self.eps = lr, beta1, beta2, eps
        self.m = [0.0] * len(self.params)  # 勾配の 1 次モーメント（平均）の推定
        self.v = [0.0] * len(self.params)  # 勾配の 2 次モーメント（二乗の平均）の推定
        self.t = 0

    def zero_grad(self) -> None:
        for p in self.params:
            p.grad = 0.0

    def step(self) -> None:
        self.t += 1
        for i, p in enumerate(self.params):
            g = p.grad
            self.m[i] = self.beta1 * self.m[i] + (1 - self.beta1) * g
            self.v[i] = self.beta2 * self.v[i] + (1 - self.beta2) * g * g
            # 0 で初期化した移動平均は最初のうち小さく偏るので補正する
            m_hat = self.m[i] / (1 - self.beta1 ** self.t)
            v_hat = self.v[i] / (1 - self.beta2 ** self.t)
            # パラメータごとに、勾配の大きさで正規化した歩幅で進む
            p.data -= self.lr * m_hat / (math.sqrt(v_hat) + self.eps)


# ---------------------------------------------------------------------------
# 演習2d: 学習と予測
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
    if len(X) != len(y) or not X:
        raise ValueError("X と y の件数が違うか、空です")
    if epochs < 1 or batch_size < 1:
        raise ValueError("epochs と batch_size は 1 以上")
    order = list(range(len(X)))
    history = []
    for _ in range(epochs):
        rng.shuffle(order)
        total = 0.0
        for start in range(0, len(order), batch_size):
            batch = order[start:start + batch_size]
            optimizer.zero_grad()
            losses = [bce_with_logits(model(X[i])[0], y[i]) for i in batch]
            loss = sum(losses[1:], losses[0]) / len(batch)  # ミニバッチの平均損失
            loss.backward()
            optimizer.step()
            total += loss.data * len(batch)
        history.append(total / len(X))
    return history


def predict_proba(model: MLP, X: Sequence[Sequence[float]]) -> list[float]:
    return [_sigmoid(model(x)[0].data) for x in X]


def predict(model: MLP, X: Sequence[Sequence[float]], threshold: float = 0.5) -> list[int]:
    return [int(p >= threshold) for p in predict_proba(model, X)]
