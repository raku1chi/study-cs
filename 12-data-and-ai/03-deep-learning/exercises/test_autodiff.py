"""12.3 演習1: 自動微分 — テスト

実行: python3 tools/check.py 12.3   （またはこのディレクトリで python3 -m unittest -v test_autodiff）
"""
import math
import random
import unittest

from autodiff import Value, numerical_gradient, value_and_grad, zero_grad


def reference_numeric_grad(f, xs, h=1e-6):
    """テスト用の中心差分（学習者の numerical_gradient とは独立に計算する）。"""
    def g(vals):
        return f([Value(v) for v in vals]).data

    out = []
    for i in range(len(xs)):
        plus, minus = list(xs), list(xs)
        plus[i] += h
        minus[i] -= h
        out.append((g(plus) - g(minus)) / (2 * h))
    return out


# すべての演算を組み合わせた関数（入力は 0.5〜2.0 の範囲で使う）
FUNCTIONS = {
    "積と累乗": lambda v: v[0] * v[1] + v[0] ** 2,
    "割り算と tanh": lambda v: (v[0] / v[1]).tanh() - 3 * v[0],
    "exp と分数": lambda v: (v[0] * v[1]).exp() / (1 + v[1] ** 2),
    "log と引き算": lambda v: (v[0] ** 2 + 1).log() * v[1] - v[1] / v[0],
    "relu": lambda v: (v[0] - v[1]).relu() + (v[1] - v[0]).relu() * 2,
    "右側の演算子": lambda v: 2 - v[0] + 5 / v[1] - (-v[1]),
    "3 変数": lambda v: ((v[0] * v[1] - v[2]).tanh() ** 3 + v[2].sigmoid()) * v[0],
    "sum() で足す": lambda v: sum(x * x for x in v),
    "softmax の交差エントロピー": lambda v: -(v[0].exp() / (v[0].exp() + v[1].exp() + v[2].exp())).log(),
    "平方根と負の指数": lambda v: v[0] ** 0.5 + v[1] ** -2,
}


class TestForward(unittest.TestCase):
    def test_arithmetic(self):
        a, b = Value(2.0), Value(-3.0)
        self.assertEqual((a * b + 1).data, -5.0)
        self.assertEqual((a - b).data, 5.0)
        self.assertEqual((a / b).data, 2.0 / -3.0)
        self.assertEqual((a ** 3).data, 8.0)
        self.assertEqual((-a).data, -2.0)
        self.assertEqual((10 - a).data, 8.0)
        self.assertEqual((1 / a).data, 0.5)
        self.assertEqual((3 * a).data, 6.0)
        self.assertEqual((a + 0.5).data, 2.5)

    def test_functions(self):
        self.assertAlmostEqual(Value(1.0).exp().data, math.e)
        self.assertAlmostEqual(Value(math.e).log().data, 1.0)
        self.assertAlmostEqual(Value(0.5).tanh().data, math.tanh(0.5))
        self.assertEqual(Value(-2.0).relu().data, 0.0)
        self.assertEqual(Value(3.0).relu().data, 3.0)
        self.assertEqual(Value(0.0).sigmoid().data, 0.5)
        self.assertEqual(Value(-1000.0).sigmoid().data, 0.0, "オーバーフローしない")


class TestBackward(unittest.TestCase):
    def test_simple_gradients(self):
        a, b, c = Value(2.0), Value(-3.0), Value(10.0)
        y = a * b + c
        y.backward()
        self.assertEqual((a.grad, b.grad, c.grad, y.grad), (-3.0, 2.0, 1.0, 1.0))

    def test_local_derivatives(self):
        cases = [
            (lambda x: x.exp(), 1.0, math.e),
            (lambda x: x.log(), 2.0, 0.5),
            (lambda x: x.tanh(), 0.0, 1.0),
            (lambda x: x.sigmoid(), 0.0, 0.25),
            (lambda x: x.relu(), 3.0, 1.0),
            (lambda x: x.relu(), -3.0, 0.0),
            (lambda x: x.relu(), 0.0, 0.0),  # x = 0 での微分は 0 とする
            (lambda x: x ** 3, 2.0, 12.0),
            (lambda x: 1 / x, 2.0, -0.25),
            (lambda x: x ** 0, 0.0, 0.0),
        ]
        for f, x0, expected in cases:
            x = Value(x0)
            f(x).backward()
            self.assertAlmostEqual(x.grad, expected, msg=f"x={x0}")

    def test_same_node_used_twice_accumulates(self):
        a = Value(3.0)
        (a * a).backward()
        self.assertEqual(a.grad, 6.0, "d(a·a)/da = 2a。2 つの経路の勾配を足す")
        b = Value(1.0)
        (b + b + b).backward()
        self.assertEqual(b.grad, 3.0)

    def test_diamond_graph(self):
        a = Value(3.0)
        b = a * 2
        c = a + 1
        d = b * c  # d = 2a(a+1) → d' = 4a + 2 = 14
        d.backward()
        self.assertEqual(a.grad, 14.0)
        self.assertEqual(b.grad, 4.0)
        self.assertEqual(c.grad, 6.0)

    def test_matches_finite_differences(self):
        rng = random.Random(0)
        for name, f in FUNCTIONS.items():
            for _ in range(5):
                xs = [rng.uniform(0.5, 2.0) for _ in range(3)]
                _, grads = value_and_grad(f, xs)
                expected = reference_numeric_grad(f, xs)
                for g, e in zip(grads, expected):
                    self.assertAlmostEqual(g, e, delta=1e-5 * max(1.0, abs(e)), msg=f"{name} xs={xs}")

    def test_backward_on_leaf(self):
        x = Value(5.0)
        x.backward()
        self.assertEqual(x.grad, 1.0)

    def test_deep_graph_does_not_hit_recursion_limit(self):
        x = Value(1.0)
        y = x
        for _ in range(5000):
            y = y + x  # 深さ 5000 の鎖
        y.backward()
        self.assertEqual(y.data, 5001.0)
        self.assertEqual(x.grad, 5001.0)

    def test_leaf_gradients_accumulate_across_backward_calls(self):
        a, b = Value(2.0), Value(5.0)
        out = a * b + a
        out.backward()
        out.backward()
        self.assertEqual(a.grad, 2 * (5.0 + 1.0), "葉の勾配は backward のたびに累積する")
        self.assertEqual(b.grad, 2 * 2.0)
        zero_grad([a, b])
        self.assertEqual((a.grad, b.grad), (0.0, 0.0))
        out.backward()
        self.assertEqual(a.grad, 6.0, "途中のノードの勾配は累積させない（二重計上しない）")

    def test_custom_operation_via_constructor(self):
        a = Value(2.0)
        custom = Value(10.0, (a,), (3.0,), op="custom")  # 局所勾配を自分で与えた演算
        (custom * 2).backward()
        self.assertEqual(a.grad, 6.0)
        with self.assertRaises(ValueError):
            Value(1.0, (a,), ())


class TestHelpersAndErrors(unittest.TestCase):
    def test_value_and_grad(self):
        value, grads = value_and_grad(lambda v: v[0] ** 2 * v[1], [3.0, 4.0])
        self.assertEqual(value, 36.0)
        self.assertEqual(grads, [24.0, 9.0])

    def test_numerical_gradient(self):
        grads = numerical_gradient(lambda xs: xs[0] ** 2 * xs[1] + math.sin(xs[1]), [3.0, 4.0])
        self.assertAlmostEqual(grads[0], 24.0, places=5)
        self.assertAlmostEqual(grads[1], 9.0 + math.cos(4.0), places=5)

    def test_errors(self):
        with self.assertRaises(ValueError):
            Value(0.0).log()
        with self.assertRaises(ValueError):
            Value(-1.0).log()
        with self.assertRaises(TypeError):
            Value(2.0) ** Value(3.0)
        with self.assertRaises(ValueError):
            Value(-8.0) ** 0.5
        with self.assertRaises(ZeroDivisionError):
            Value(1.0) / 0
        with self.assertRaises(TypeError):
            Value(1.0) + "a"


if __name__ == "__main__":
    unittest.main()
