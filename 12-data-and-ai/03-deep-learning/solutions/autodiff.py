"""12.3 深層学習とTransformer — 演習1: スカラーの逆伝播型自動微分（解答例）

演習の仕様は exercises/autodiff.py の docstring を参照してください。

設計: 各ノード（Value）は、順伝播の時点で「親ノード」と「親に対する局所的な偏微分」を記録します。
逆伝播では、出力側から順に dL/d親 += (dL/d自分) × (d自分/d親) を足し込むだけです（連鎖律）。
"""
from __future__ import annotations

import math
from typing import Callable, Sequence, Union

Number = Union[int, float]


class Value:
    __slots__ = ("data", "grad", "_parents", "_local_grads", "op", "label")

    def __init__(
        self,
        data: Number,
        parents: tuple["Value", ...] = (),
        local_grads: tuple[float, ...] = (),
        op: str = "",
        label: str = "",
    ) -> None:
        if len(parents) != len(local_grads):
            raise ValueError("parents と local_grads の長さが違います")
        self.data = float(data)
        self.grad = 0.0
        self._parents = tuple(parents)
        self._local_grads = tuple(float(g) for g in local_grads)
        self.op = op
        self.label = label

    def __repr__(self) -> str:
        return f"Value(data={self.data:.6g}, grad={self.grad:.6g})"

    @staticmethod
    def _lift(x: "Value | Number") -> "Value":
        if isinstance(x, Value):
            return x
        if isinstance(x, (int, float)):
            return Value(x)
        raise TypeError(f"Value と演算できない型です: {type(x).__name__}")

    # --- 二項演算: 局所的な偏微分を順伝播の時点で計算しておく -----------------
    def __add__(self, other: "Value | Number") -> "Value":
        o = Value._lift(other)
        return Value(self.data + o.data, (self, o), (1.0, 1.0), "+")

    def __radd__(self, other: Number) -> "Value":
        return self + other

    def __sub__(self, other: "Value | Number") -> "Value":
        o = Value._lift(other)
        return Value(self.data - o.data, (self, o), (1.0, -1.0), "-")

    def __rsub__(self, other: Number) -> "Value":
        return Value._lift(other) - self

    def __mul__(self, other: "Value | Number") -> "Value":
        o = Value._lift(other)
        return Value(self.data * o.data, (self, o), (o.data, self.data), "*")

    def __rmul__(self, other: Number) -> "Value":
        return self * other

    def __truediv__(self, other: "Value | Number") -> "Value":
        o = Value._lift(other)
        out = self.data / o.data  # o.data == 0 なら ZeroDivisionError
        # d(a/b)/da = 1/b、d(a/b)/db = -a/b²
        return Value(out, (self, o), (1.0 / o.data, -self.data / (o.data * o.data)), "/")

    def __rtruediv__(self, other: Number) -> "Value":
        return Value._lift(other) / self

    def __neg__(self) -> "Value":
        return Value(-self.data, (self,), (-1.0,), "neg")

    def __pow__(self, exponent: Number) -> "Value":
        if isinstance(exponent, Value) or not isinstance(exponent, (int, float)):
            raise TypeError("指数は int か float にしてください")
        if self.data < 0 and not float(exponent).is_integer():
            raise ValueError("負の数の非整数乗は実数になりません")
        out = self.data ** exponent
        local = 0.0 if exponent == 0 else exponent * self.data ** (exponent - 1)
        return Value(out, (self,), (local,), f"**{exponent}")

    # --- 単項の関数 ----------------------------------------------------------------
    def exp(self) -> "Value":
        e = math.exp(self.data)
        return Value(e, (self,), (e,), "exp")  # (e^x)' = e^x

    def log(self) -> "Value":
        if self.data <= 0:
            raise ValueError(f"log の引数は正の数: {self.data}")
        return Value(math.log(self.data), (self,), (1.0 / self.data,), "log")

    def tanh(self) -> "Value":
        t = math.tanh(self.data)
        return Value(t, (self,), (1.0 - t * t,), "tanh")  # tanh' = 1 - tanh²

    def relu(self) -> "Value":
        # x = 0 での微分は 0 とする（慣例）
        return Value(max(0.0, self.data), (self,), (1.0 if self.data > 0 else 0.0,), "relu")

    def sigmoid(self) -> "Value":
        x = self.data
        s = 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))
        return Value(s, (self,), (s * (1.0 - s),), "sigmoid")

    # --- 逆伝播 ----------------------------------------------------------------------
    def _topological_order(self) -> list["Value"]:
        """self に至る全ノードを「親が子より先」の順に並べる（反復的な深さ優先探索）。

        再帰で書くと、長い鎖（数千段の足し算など）で RecursionError になるので、
        明示的なスタックを使う。
        """
        order: list[Value] = []
        visited: set[int] = set()
        stack: list[tuple[Value, bool]] = [(self, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                order.append(node)  # 親をすべて処理し終えた（帰りがけ順）
                continue
            if id(node) in visited:
                continue
            visited.add(id(node))
            stack.append((node, True))
            for parent in node._parents:
                if id(parent) not in visited:
                    stack.append((parent, False))
        return order

    def backward(self) -> None:
        order = self._topological_order()
        # 途中のノードの勾配はこの逆伝播の中だけで使うので 0 から数え直す。
        # 葉（パラメータ・入力）の勾配は累積する（PyTorch と同じ約束。ミニバッチの勾配の足し合わせに使える）
        for node in order:
            if node._parents:
                node.grad = 0.0
        self.grad += 1.0  # dL/dL = 1
        for node in reversed(order):  # 出力側から入力側へ。node.grad はこの時点で確定している
            for parent, local in zip(node._parents, node._local_grads):
                parent.grad += local * node.grad  # 連鎖律。同じ親に複数の経路があれば足し合わさる


def zero_grad(values: Sequence[Value]) -> None:
    for v in values:
        v.grad = 0.0


def value_and_grad(f: Callable[[list[Value]], Value], xs: Sequence[float]) -> tuple[float, list[float]]:
    inputs = [Value(x) for x in xs]
    out = f(inputs)
    out.backward()
    return out.data, [v.grad for v in inputs]


def numerical_gradient(f: Callable[[list[float]], float], xs: Sequence[float], h: float = 1e-6) -> list[float]:
    grads = []
    for i in range(len(xs)):
        plus = list(xs)
        minus = list(xs)
        plus[i] += h
        minus[i] -= h
        # 中心差分: 誤差は O(h²)。前進差分 (f(x+h) - f(x)) / h の O(h) より正確
        grads.append((f(plus) - f(minus)) / (2 * h))
    return grads
