"""12.3 演習2: 小さなニューラルネットワーク — テスト

実行: python3 tools/check.py 12.3   （またはこのディレクトリで python3 -m unittest -v test_tiny_nn）
学習のテストは数秒以内に終わるよう、データとモデルを小さくしています。
"""
import math
import random
import statistics
import unittest

from autodiff import Value
from tiny_nn import (
    MLP,
    SGD,
    Adam,
    Layer,
    Neuron,
    bce_with_logits,
    make_circles,
    make_xor_dataset,
    mse_loss,
    predict,
    predict_proba,
    train_binary_classifier,
)


def accuracy(y_true, y_pred):
    return sum(t == p for t, p in zip(y_true, y_pred)) / len(y_true)


class TestModules(unittest.TestCase):
    def test_neuron(self):
        n = Neuron(3, random.Random(0))
        self.assertEqual(len(n.parameters()), 4, "重み 3 つとバイアス 1 つ")
        out = n([1.0, -2.0, 0.5])
        self.assertIsInstance(out, Value)
        self.assertTrue(-1.0 < out.data < 1.0, "tanh の出力は (-1, 1)")
        self.assertGreaterEqual(Neuron(2, random.Random(0), activation="relu")([-5.0, -5.0]).data, 0.0)
        with self.assertRaises(ValueError):
            n([1.0, 2.0])
        with self.assertRaises(ValueError):
            Neuron(2, random.Random(0), activation="softsign")

    def test_initialization_scale(self):
        w = [p.data for p in Neuron(400, random.Random(1)).parameters()[:-1]]
        self.assertAlmostEqual(statistics.pstdev(w), math.sqrt(1 / 400), delta=0.2 * math.sqrt(1 / 400))
        w = [p.data for p in Neuron(400, random.Random(1), activation="relu").parameters()[:-1]]
        self.assertAlmostEqual(statistics.pstdev(w), math.sqrt(2 / 400), delta=0.2 * math.sqrt(2 / 400))
        self.assertEqual(Neuron(4, random.Random(0)).parameters()[-1].data, 0.0, "バイアスは 0 で初期化")

    def test_layer_and_mlp_shapes(self):
        layer = Layer(3, 5, random.Random(0))
        self.assertEqual(len(layer([1.0, 2.0, 3.0])), 5)
        self.assertEqual(len(MLP(2, [4, 1], random.Random(0)).parameters()), 4 * 3 + 1 * 5)
        mlp = MLP(3, [5, 5, 2], random.Random(0))
        self.assertEqual(len(mlp.parameters()), 5 * 4 + 5 * 6 + 2 * 6)
        self.assertEqual(len(mlp([0.1, 0.2, 0.3])), 2)

    def test_last_layer_is_linear(self):
        mlp = MLP(1, [1], random.Random(3))  # 層が 1 つ（= 最後の層）だけ → 線形関数
        f = [mlp([x])[0].data for x in (0.0, 1.0, 2.0, 10.0)]
        self.assertAlmostEqual(f[2] - f[1], f[1] - f[0])
        self.assertAlmostEqual(f[3] - f[0], 10 * (f[1] - f[0]))

    def test_zero_grad_and_gradients_flow(self):
        mlp = MLP(2, [3, 1], random.Random(0))
        loss = bce_with_logits(mlp([0.5, -1.0])[0], 1)
        loss.backward()
        self.assertTrue(all(p.grad != 0.0 for p in mlp.parameters()), "すべてのパラメータに勾配が届く")
        mlp.zero_grad()
        self.assertTrue(all(p.grad == 0.0 for p in mlp.parameters()))


class TestLosses(unittest.TestCase):
    def test_bce_with_logits_value_and_gradient(self):
        for z, y in [(0.0, 1), (2.0, 0), (-3.0, 1), (0.7, 0)]:
            logit = Value(z)
            loss = bce_with_logits(logit, y)
            p = 1 / (1 + math.exp(-z))
            self.assertAlmostEqual(loss.data, -(y * math.log(p) + (1 - y) * math.log(1 - p)))
            loss.backward()
            self.assertAlmostEqual(logit.grad, p - y, msg="勾配は σ(z) - y")

    def test_bce_with_logits_is_stable(self):
        self.assertAlmostEqual(bce_with_logits(Value(1000.0), 1).data, 0.0)
        self.assertAlmostEqual(bce_with_logits(Value(-1000.0), 1).data, 1000.0)
        self.assertAlmostEqual(bce_with_logits(Value(-1000.0), 0).data, 0.0)
        with self.assertRaises(ValueError):
            bce_with_logits(Value(0.0), 2)

    def test_mse_loss(self):
        pred = Value(3.0)
        loss = mse_loss(pred, 1.0)
        self.assertEqual(loss.data, 4.0)
        loss.backward()
        self.assertEqual(pred.grad, 4.0)


class TestOptimizers(unittest.TestCase):
    def test_sgd(self):
        p = Value(1.0)
        opt = SGD([p], lr=0.1)
        p.grad = 2.0
        opt.step()
        self.assertAlmostEqual(p.data, 0.8)
        opt.zero_grad()
        self.assertEqual(p.grad, 0.0)

    def test_sgd_momentum(self):
        p = Value(1.0)
        opt = SGD([p], lr=0.1, momentum=0.9)
        for _ in range(2):
            p.grad = 2.0
            opt.step()
        # v1 = 2 → p = 0.8、v2 = 0.9·2 + 2 = 3.8 → p = 0.8 - 0.38 = 0.42
        self.assertAlmostEqual(p.data, 0.42)

    def test_adam_first_step_is_about_lr(self):
        for g in (0.01, 1.0, 1e4):
            p = Value(1.0)
            opt = Adam([p], lr=0.01)
            p.grad = g
            opt.step()
            self.assertAlmostEqual(p.data, 0.99, places=6, msg="偏り補正により、最初の一歩は勾配の大きさによらず約 lr")

    def test_adam_minimizes_quadratic(self):
        x = Value(5.0)
        opt = Adam([x], lr=0.1)
        for _ in range(300):
            opt.zero_grad()
            ((x - 2) ** 2).backward()
            opt.step()
        self.assertAlmostEqual(x.data, 2.0, delta=0.05)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            SGD([Value(0.0)], lr=0)
        with self.assertRaises(ValueError):
            Adam([Value(0.0)], lr=0.01, beta1=1.0)


class TestTraining(unittest.TestCase):
    def test_xor(self):
        X, y = make_xor_dataset()
        for seed in range(3):
            rng = random.Random(seed)
            model = MLP(2, [4, 1], rng)
            history = train_binary_classifier(model, X, y, optimizer=Adam(model.parameters(), lr=0.1),
                                              epochs=150, batch_size=4, rng=rng)
            self.assertEqual(len(history), 150)
            self.assertLess(history[-1], 0.1, f"seed={seed}")
            self.assertEqual(predict(model, X), y, f"seed={seed}")

    def test_linear_model_cannot_solve_xor(self):
        X, y = make_xor_dataset()
        rng = random.Random(0)
        model = MLP(2, [1], rng)  # 隠れ層なし = ロジスティック回帰
        train_binary_classifier(model, X, y, optimizer=Adam(model.parameters(), lr=0.1),
                                epochs=150, batch_size=4, rng=rng)
        self.assertLessEqual(accuracy(y, predict(model, X)), 0.75, "直線 1 本では XOR を分けられない")

    def test_concentric_circles(self):
        X, y = make_circles(100, seed=0)
        rng = random.Random(0)
        model = MLP(2, [8, 1], rng)
        history = train_binary_classifier(model, X, y, optimizer=Adam(model.parameters(), lr=0.05),
                                          epochs=30, batch_size=10, rng=rng)
        self.assertLess(history[-1], 0.3 * history[0], "損失が十分に下がる")
        X_test, y_test = make_circles(200, seed=100)
        self.assertGreaterEqual(accuracy(y_test, predict(model, X_test)), 0.9)
        probs = predict_proba(model, X_test)
        self.assertTrue(all(0.0 <= p <= 1.0 for p in probs))

    def test_training_with_sgd_momentum(self):
        X, y = make_circles(60, seed=1)
        rng = random.Random(1)
        model = MLP(2, [8, 1], rng)
        history = train_binary_classifier(model, X, y, optimizer=SGD(model.parameters(), lr=0.2, momentum=0.9),
                                          epochs=40, batch_size=6, rng=rng)
        self.assertLess(history[-1], 0.5 * history[0])

    def test_train_errors(self):
        model = MLP(2, [2, 1], random.Random(0))
        opt = SGD(model.parameters())
        with self.assertRaises(ValueError):
            train_binary_classifier(model, [[0.0, 0.0]], [0, 1], optimizer=opt, epochs=1, batch_size=1,
                                    rng=random.Random(0))
        with self.assertRaises(ValueError):
            train_binary_classifier(model, [[0.0, 0.0]], [0], optimizer=opt, epochs=0, batch_size=1,
                                    rng=random.Random(0))


if __name__ == "__main__":
    unittest.main()
