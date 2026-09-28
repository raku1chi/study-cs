"""12.3 深層学習とTransformer — 演習1: スカラーの逆伝播型自動微分（★★★）

深層学習のフレームワーク（PyTorch など）の心臓部である「逆伝播型の自動微分（reverse-mode
automatic differentiation）」を、スカラー（1 つの数）の単位で実装します。

設計（このファイルの約束）:
    各ノード Value は、順伝播で値を計算した時点で、
      - 親ノードのタプル parents（この値を計算するのに使った入力）
      - 局所的な偏微分のタプル local_grads（d 自分 / d 親。親と同じ順番）
    を記録します。例えば c = a * b なら parents = (a, b)、local_grads = (b.data, a.data) です。
    逆伝播では、出力側から入力側へ向かって
        親.grad += 局所的な偏微分 × 自分.grad     （連鎖律）
    を足し込むだけです。同じノードが複数の経路で使われていれば、勾配は自然に足し合わされます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.3
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_autodiff

さらに学ぶ: Andrej Karpathy の micrograd（同じ規模のエンジンを別の設計で書いたもの）と、
その解説動画 "Neural Networks: Zero to Hero" の第 1 回は、この演習の良い比較対象です。
"""
from __future__ import annotations

import math  # noqa: F401
from typing import Callable, Sequence, Union

Number = Union[int, float]


class Value:
    """自動微分に対応したスカラー値。

    属性:
        data: 値（float）
        grad: 逆伝播で計算された、出力に対するこの値の偏微分（初期値 0.0）
        op:   この値を作った演算の名前（デバッグ用。"+" など）
        label: 任意の名前（デバッグ用）

    コンストラクタ（実装済み）は、tiny_nn.py のように「局所勾配を自分で与えた演算」を
    作るためにも使えます: Value(値, (親,), (局所勾配,), op="名前")
    """

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
        """数値なら Value に包んで返す（実装済み）。int / float / Value 以外は TypeError。"""
        if isinstance(x, Value):
            return x
        if isinstance(x, (int, float)):
            return Value(x)
        raise TypeError(f"Value と演算できない型です: {type(x).__name__}")

    # --- 演習1a（★★☆）: 演算 -----------------------------------------------------
    # 各演算は、新しい Value(結果, 親のタプル, 局所勾配のタプル, op) を返す。
    # 相手が数値のとき（a + 2、2 * a、2 - a、1 / a など）も動くよう、_lift と __r演算__ を使う。

    def __add__(self, other: "Value | Number") -> "Value":
        """a + b。局所勾配は (1, 1)。"""
        raise NotImplementedError("演習1a: __add__ を実装してください")

    def __radd__(self, other: Number) -> "Value":
        """2 + a（sum() は 0 + a から始まるのでこれが必要）。"""
        raise NotImplementedError("演習1a: __radd__ を実装してください")

    def __sub__(self, other: "Value | Number") -> "Value":
        """a - b。局所勾配は (1, -1)。"""
        raise NotImplementedError("演習1a: __sub__ を実装してください")

    def __rsub__(self, other: Number) -> "Value":
        """2 - a。"""
        raise NotImplementedError("演習1a: __rsub__ を実装してください")

    def __mul__(self, other: "Value | Number") -> "Value":
        """a * b。局所勾配は (b, a)。"""
        raise NotImplementedError("演習1a: __mul__ を実装してください")

    def __rmul__(self, other: Number) -> "Value":
        """2 * a。"""
        raise NotImplementedError("演習1a: __rmul__ を実装してください")

    def __truediv__(self, other: "Value | Number") -> "Value":
        """a / b。局所勾配は (1/b, -a/b²)。b = 0 なら ZeroDivisionError（Python の除算に任せてよい）。"""
        raise NotImplementedError("演習1a: __truediv__ を実装してください")

    def __rtruediv__(self, other: Number) -> "Value":
        """2 / a。"""
        raise NotImplementedError("演習1a: __rtruediv__ を実装してください")

    def __neg__(self) -> "Value":
        """-a。局所勾配は (-1,)。"""
        raise NotImplementedError("演習1a: __neg__ を実装してください")

    def __pow__(self, exponent: Number) -> "Value":
        """a ** n（n は int か float の定数）。局所勾配は n·a^(n-1)。

        - 指数が Value（や数値以外）なら TypeError。
        - a < 0 で n が整数でなければ ValueError（実数にならない）。
        - n = 0 のときは局所勾配を 0 とする（a = 0 でも 0 の負のべき乗を計算しないように）。
        """
        raise NotImplementedError("演習1a: __pow__ を実装してください")

    def exp(self) -> "Value":
        """e^a。局所勾配は e^a。"""
        raise NotImplementedError("演習1a: exp を実装してください")

    def log(self) -> "Value":
        """自然対数 log(a)。局所勾配は 1/a。a <= 0 なら ValueError。"""
        raise NotImplementedError("演習1a: log を実装してください")

    def tanh(self) -> "Value":
        """tanh(a)。局所勾配は 1 - tanh(a)²。"""
        raise NotImplementedError("演習1a: tanh を実装してください")

    def relu(self) -> "Value":
        """max(0, a)。局所勾配は a > 0 なら 1、それ以外（a = 0 を含む）は 0。"""
        raise NotImplementedError("演習1a: relu を実装してください")

    def sigmoid(self) -> "Value":
        """σ(a) = 1/(1 + e^(-a))。局所勾配は σ(a)(1 - σ(a))。a が大きな負の数でもオーバーフローしないこと。"""
        raise NotImplementedError("演習1a: sigmoid を実装してください")

    # --- 演習1b（★★★）: 逆伝播 ---------------------------------------------------------

    def backward(self) -> None:
        """self（スカラーの出力 L）から逆伝播し、グラフ中の全ノードの grad を計算する。

        手順:
        1. self に至るすべてのノードを、トポロジカル順（どのノードも、その親より後に来る順）に並べる。
           **再帰を使わず**、明示的なスタックで深さ優先探索すること（5,000 段の鎖でも動くように。
           Python の再帰の上限は既定で 1,000 程度）。同じノードは 1 回だけ並べる（id() で識別するとよい）。
        2. 親を持つノード（途中のノード）の grad を 0 にリセットする。
           葉（親のないノード。パラメータや入力）の grad はリセットしない（累積させる）。
        3. self.grad に 1.0 を足す（dL/dL = 1）。
        4. トポロジカル順の **逆順** に各ノードを訪れ、親.grad += 局所勾配 × ノード.grad を行う。
           逆順に処理すれば、ノードを訪れた時点でその grad は確定している。

        この約束により、backward を 2 回呼ぶと葉の勾配はちょうど 2 倍になり（ミニバッチの勾配の
        足し合わせに使える）、途中のノードの勾配が二重に数えられることはない。
        """
        raise NotImplementedError("演習1b: backward を実装してください")


# ---------------------------------------------------------------------------
# 演習1c（★☆☆）: 補助関数
# ---------------------------------------------------------------------------

def zero_grad(values: Sequence[Value]) -> None:
    """各 Value の grad を 0.0 にする。"""
    raise NotImplementedError("演習1c: zero_grad を実装してください")


def value_and_grad(f: Callable[[list[Value]], Value], xs: Sequence[float]) -> tuple[float, list[float]]:
    """xs を Value に包んで f に渡し、backward して (f の値, 各入力の勾配のリスト) を返す。

    >>> value_and_grad(lambda v: v[0] ** 2 * v[1], [3.0, 4.0])
    (36.0, [24.0, 9.0])
    """
    raise NotImplementedError("演習1c: value_and_grad を実装してください")


def numerical_gradient(f: Callable[[list[float]], float], xs: Sequence[float], h: float = 1e-6) -> list[float]:
    """中心差分 (f(x + h·e_i) - f(x - h·e_i)) / (2h) で各入力の偏微分を近似する（検算用）。

    f は float のリストを受け取り float を返す普通の関数。
    """
    raise NotImplementedError("演習1c: numerical_gradient を実装してください")
