"""12.2 機械学習の基礎 — テスト

実行: python3 tools/check.py 12.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import statistics
import unittest

from ml_datasets import make_blobs, make_regression, make_two_gaussians, make_xor, train_test_split
from ml_scratch import (
    DecisionTreeClassifier,
    KMeansResult,
    LinearRegressionGD,
    LogisticRegressionSGD,
    Standardizer,
    accuracy,
    average_precision,
    best_threshold,
    confusion_matrix,
    cross_val_score,
    gini,
    k_fold_indices,
    kmeans,
    kmeans_plus_plus_init,
    log_loss,
    mae,
    pr_curve,
    precision_recall_f1,
    rmse,
    roc_auc,
    sigmoid,
    simple_linear_regression,
    squared_distance,
)


def least_squares(X, y):
    """正規方程式 (AᵀA) β = Aᵀy をガウスの消去法で解く（A = [1, X]）。テストの基準値。"""
    A = [[1.0] + list(row) for row in X]
    m = len(A[0])
    M = [[sum(a[i] * a[j] for a in A) for j in range(m)] + [sum(a[i] * t for a, t in zip(A, y))] for i in range(m)]
    for c in range(m):
        p = max(range(c, m), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(m):
            if r != c:
                f = M[r][c] / M[c][c]
                M[r] = [v - f * w for v, w in zip(M[r], M[c])]
    beta = [M[i][m] / M[i][i] for i in range(m)]
    return beta[1:], beta[0]


class TestExercise1LinearRegression(unittest.TestCase):
    def test_simple_regression_exact_line(self):
        slope, intercept = simple_linear_regression([0, 1, 2, 3], [2, 5, 8, 11])
        self.assertAlmostEqual(slope, 3.0)
        self.assertAlmostEqual(intercept, 2.0)

    def test_simple_regression_matches_statistics_module(self):
        rng = random.Random(0)
        xs = [rng.uniform(0, 10) for _ in range(50)]
        ys = [1.5 * x - 4 + rng.gauss(0, 1) for x in xs]
        expected = statistics.linear_regression(xs, ys)
        slope, intercept = simple_linear_regression(xs, ys)
        self.assertAlmostEqual(slope, expected.slope, places=9)
        self.assertAlmostEqual(intercept, expected.intercept, places=9)

    def test_simple_regression_errors(self):
        for xs, ys in [([1], [1]), ([1, 2], [1]), ([3, 3, 3], [1, 2, 3])]:
            with self.assertRaises(ValueError):
                simple_linear_regression(xs, ys)

    def test_standardizer(self):
        X = [[1.0, 10.0, 5.0], [2.0, 20.0, 5.0], [3.0, 30.0, 5.0]]
        Z = Standardizer().fit_transform(X)
        for j in range(2):
            col = [row[j] for row in Z]
            self.assertAlmostEqual(sum(col) / 3, 0.0)
            self.assertAlmostEqual(statistics.pstdev(col), 1.0)
        self.assertEqual([row[2] for row in Z], [0.0, 0.0, 0.0], "定数の列は 0 にする（0 で割らない）")

    def test_gradient_descent_matches_least_squares(self):
        # スケールの大きく違う特徴量。標準化しているので同じ学習率で収束する
        X, y = make_regression(200, [2.0, -3.0, 0.5], 1.0, noise=0.1, scales=[1.0, 100.0, 0.01], seed=1)
        model = LinearRegressionGD(learning_rate=0.1, n_epochs=200).fit(X, y)
        coef, intercept = least_squares(X, y)
        for got, want in zip(model.coef_, coef):
            self.assertAlmostEqual(got, want, delta=1e-3 * max(1.0, abs(want)))
        self.assertAlmostEqual(model.intercept_, intercept, delta=1e-3)
        preds = model.predict(X)
        self.assertLess(rmse(y, preds), 0.12)

    def test_loss_decreases_monotonically(self):
        X, y = make_regression(100, [1.0, 2.0], 0.5, seed=2)
        model = LinearRegressionGD(learning_rate=0.1, n_epochs=100).fit(X, y)
        h = model.loss_history_
        self.assertEqual(len(h), 100)
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(h, h[1:])), "凸な損失の最急降下では損失は増えない")

    def test_without_standardization_it_diverges(self):
        X, y = make_regression(200, [2.0, -3.0, 0.5], 1.0, scales=[1.0, 100.0, 0.01], seed=1)
        model = LinearRegressionGD(learning_rate=0.1, n_epochs=50, standardize=False).fit(X, y)
        last = model.loss_history_[-1]
        self.assertTrue(not math.isfinite(last) or last > 1e6 * model.loss_history_[0])

    def test_l2_shrinks_coefficients(self):
        X, y = make_regression(200, [2.0, -3.0, 0.5], 1.0, noise=0.5, seed=3)
        ols = LinearRegressionGD(n_epochs=200).fit(X, y)
        ridge = LinearRegressionGD(n_epochs=200, l2=1.0).fit(X, y)
        norm = lambda m: math.sqrt(sum(c * c for c in m.coef_))  # noqa: E731
        self.assertLess(norm(ridge), 0.7 * norm(ols))

    def test_errors(self):
        with self.assertRaises(ValueError):
            LinearRegressionGD().fit([], [])
        with self.assertRaises(ValueError):
            LinearRegressionGD().fit([[1.0], [2.0]], [1.0])
        with self.assertRaises(RuntimeError):
            LinearRegressionGD().predict([[1.0]])


class TestExercise2LogisticRegression(unittest.TestCase):
    def test_sigmoid_is_stable(self):
        self.assertEqual(sigmoid(0), 0.5)
        self.assertEqual(sigmoid(1000), 1.0)
        self.assertEqual(sigmoid(-1000), 0.0)  # OverflowError にならない
        for z in (-5.0, -0.3, 2.0, 30.0):
            self.assertAlmostEqual(sigmoid(-z), 1 - sigmoid(z))

    def setUp(self):
        X, y = make_two_gaussians(400, distance=2.0, seed=3)
        self.split = train_test_split(X, y, test_ratio=0.25, seed=0)

    def test_learns_separating_direction(self):
        Xtr, Xte, ytr, yte = self.split
        model = LogisticRegressionSGD(learning_rate=0.05, n_epochs=30, seed=0).fit(Xtr, ytr)
        self.assertGreater(model.coef_[0], 0.5)
        self.assertGreater(model.coef_[1], 0.5)
        self.assertGreaterEqual(accuracy(yte, model.predict(Xte)), 0.85)
        probs = model.predict_proba(Xte)
        self.assertTrue(all(0.0 < p < 1.0 for p in probs))
        self.assertLess(log_loss(yte, probs), 0.3)
        self.assertEqual(len(model.loss_history_), 30)

    def test_threshold_changes_predictions(self):
        Xtr, Xte, ytr, _ = self.split
        model = LogisticRegressionSGD(n_epochs=10).fit(Xtr, ytr)
        low = sum(model.predict(Xte, threshold=0.1))
        high = sum(model.predict(Xte, threshold=0.9))
        self.assertGreater(low, high, "しきい値を下げると陽性と予測する数が増える")

    def test_l2_shrinks_weights(self):
        Xtr, _, ytr, _ = self.split
        plain = LogisticRegressionSGD(n_epochs=20, seed=0).fit(Xtr, ytr)
        reg = LogisticRegressionSGD(n_epochs=20, seed=0, l2=0.5).fit(Xtr, ytr)
        self.assertLess(sum(abs(c) for c in reg.coef_), 0.5 * sum(abs(c) for c in plain.coef_))

    def test_deterministic_with_seed(self):
        Xtr, _, ytr, _ = self.split
        a = LogisticRegressionSGD(n_epochs=5, seed=7).fit(Xtr, ytr)
        b = LogisticRegressionSGD(n_epochs=5, seed=7).fit(Xtr, ytr)
        self.assertEqual(a.coef_, b.coef_)
        self.assertEqual(a.intercept_, b.intercept_)

    def test_invalid_labels(self):
        with self.assertRaises(ValueError):
            LogisticRegressionSGD().fit([[0.0], [1.0]], [0, 2])


class TestExercise3Metrics(unittest.TestCase):
    Y_TRUE = [1, 1, 1, 0, 0, 0, 0, 1]
    Y_PRED = [1, 0, 1, 0, 1, 0, 0, 1]

    def test_confusion_matrix_and_prf(self):
        self.assertEqual(confusion_matrix(self.Y_TRUE, self.Y_PRED), {"tp": 3, "fp": 1, "fn": 1, "tn": 3})
        p, r, f = precision_recall_f1(self.Y_TRUE, self.Y_PRED)
        self.assertAlmostEqual(p, 0.75)
        self.assertAlmostEqual(r, 0.75)
        self.assertAlmostEqual(f, 0.75)
        self.assertEqual(accuracy(self.Y_TRUE, self.Y_PRED), 0.75)
        self.assertEqual(precision_recall_f1([1, 0], [0, 0]), (0.0, 0.0, 0.0), "0 で割る場合は 0.0")

    def test_accuracy_paradox_under_imbalance(self):
        y_true = [1] * 10 + [0] * 990
        always_negative = [0] * 1000
        self.assertAlmostEqual(accuracy(y_true, always_negative), 0.99)
        self.assertEqual(precision_recall_f1(y_true, always_negative)[1], 0.0, "再現率は 0")

    def test_regression_metrics(self):
        self.assertAlmostEqual(rmse([1, 2, 3], [1, 2, 7]), math.sqrt(16 / 3))
        self.assertAlmostEqual(mae([1, 2, 3], [1, 2, 7]), 4 / 3)

    def test_log_loss(self):
        self.assertAlmostEqual(log_loss([1, 0], [0.8, 0.2]), -math.log(0.8))
        self.assertLess(log_loss([1], [0.0]), 40, "確率 0 でも無限大にしない（eps でクリップ）")

    def test_roc_auc_known_values(self):
        self.assertEqual(roc_auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertEqual(roc_auc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]), 0.0)
        self.assertEqual(roc_auc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]), 0.5, "全部同点なら 0.5")
        self.assertAlmostEqual(roc_auc([0, 0, 1, 1], [0.1, 0.4, 0.35, 0.8]), 0.75)

    def test_roc_auc_matches_pairwise_definition_with_ties(self):
        rng = random.Random(5)
        for _ in range(30):
            n = rng.randrange(5, 40)
            y = [rng.randrange(2) for _ in range(n)]
            if len(set(y)) < 2:
                continue
            s = [rng.randrange(6) / 5 for _ in range(n)]  # 同点が多い
            pos = [si for si, yi in zip(s, y) if yi == 1]
            neg = [si for si, yi in zip(s, y) if yi == 0]
            brute = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg) / (len(pos) * len(neg))
            self.assertAlmostEqual(roc_auc(y, s), brute, places=12)

    def test_roc_auc_needs_both_classes(self):
        with self.assertRaises(ValueError):
            roc_auc([1, 1], [0.2, 0.3])

    def test_pr_curve(self):
        curve = pr_curve([1, 0, 1, 1, 0], [0.9, 0.8, 0.7, 0.7, 0.1])
        self.assertEqual(curve, [(0.9, 1.0, 1 / 3), (0.8, 0.5, 1 / 3), (0.7, 0.75, 1.0), (0.1, 0.6, 1.0)])

    def test_average_precision(self):
        self.assertAlmostEqual(average_precision([1, 0, 1, 1, 0], [0.9, 0.8, 0.7, 0.7, 0.1]),
                               1 / 3 * 1.0 + 2 / 3 * 0.75)
        rng = random.Random(6)
        y = [int(rng.random() < 0.2) for _ in range(200)]
        s = [rng.random() + 0.3 * yi for yi in y]
        ap = average_precision(y, s)
        self.assertTrue(sum(y) / len(y) < ap < 1.0, "ランダムより良く、完璧ではない")
        self.assertAlmostEqual(average_precision(y, [float(v) for v in y]), 1.0)

    def test_best_threshold_uses_costs(self):
        y = [0, 0, 0, 1, 0, 1, 1, 1]
        s = [0.1, 0.2, 0.3, 0.35, 0.4, 0.6, 0.7, 0.9]
        t, cost = best_threshold(y, s, cost_fp=1, cost_fn=1)
        self.assertEqual((t, cost), (0.6, 1))
        # 見逃し（FN）が 10 倍高くつくなら、しきい値を下げて見逃しをなくす
        t, cost = best_threshold(y, s, cost_fp=1, cost_fn=10)
        self.assertEqual((t, cost), (0.35, 1))
        # 誤検知が 100 倍高くつくなら、誤検知が出ない範囲で最も低いしきい値
        self.assertEqual(best_threshold(y, s, cost_fp=100, cost_fn=1), (0.6, 1))
        # スコアが当てにならず誤検知が高くつくなら、誰も陽性にしない（しきい値 +inf）
        self.assertEqual(best_threshold([0, 1], [0.9, 0.1], cost_fp=100, cost_fn=1), (math.inf, 1))


class TestExercise4KMeans(unittest.TestCase):
    CENTERS = [[0.0, 0.0], [10.0, 10.0], [-10.0, 10.0]]

    def test_recovers_well_separated_blobs(self):
        X, truth = make_blobs(self.CENTERS, 50, std=1.0, seed=2)
        result = kmeans(X, 3, seed=0)
        self.assertIsInstance(result, KMeansResult)
        mapping = {}
        for label, t in zip(result.labels, truth):
            mapping.setdefault(label, set()).add(t)
        self.assertEqual(sorted(len(v) for v in mapping.values()), [1, 1, 1], "クラスタと正解が 1 対 1 に対応する")
        for c in result.centroids:
            self.assertLess(min(math.dist(c, t) for t in self.CENTERS), 0.5)

    def test_inertia_is_consistent_and_non_increasing(self):
        X, _ = make_blobs([[0, 0], [3, 3], [0, 4], [5, 0]], 40, std=1.5, seed=9)
        result = kmeans(X, 4, seed=1)
        expected = sum(squared_distance(p, result.centroids[l]) for p, l in zip(X, result.labels))
        self.assertAlmostEqual(result.inertia, expected)
        h = result.inertia_history
        self.assertEqual(len(h), result.n_iter)
        self.assertTrue(all(b <= a + 1e-9 for a, b in zip(h, h[1:])), f"慣性が増えた: {h}")
        self.assertLessEqual(result.inertia, h[-1] + 1e-9)
        for p, l in zip(X, result.labels):  # 各点は最も近い中心に属する
            self.assertAlmostEqual(squared_distance(p, result.centroids[l]),
                                   min(squared_distance(p, c) for c in result.centroids))

    def test_edge_cases(self):
        X = [[1.0, 2.0], [3.0, 4.0], [5.0, 9.0]]
        one = kmeans(X, 1)
        self.assertEqual(one.labels, [0, 0, 0])
        self.assertAlmostEqual(one.centroids[0][0], 3.0)
        self.assertAlmostEqual(one.centroids[0][1], 5.0)
        self.assertAlmostEqual(kmeans(X, 3).inertia, 0.0)
        for bad_k in (0, 4):
            with self.assertRaises(ValueError):
                kmeans(X, bad_k)
        with self.assertRaises(ValueError):
            kmeans([[1.0], [1.0, 2.0]], 1)

    def test_deterministic(self):
        X, _ = make_blobs(self.CENTERS, 30, seed=3)
        a, b = kmeans(X, 3, seed=42), kmeans(X, 3, seed=42)
        self.assertEqual(a.centroids, b.centroids)
        self.assertEqual(a.labels, b.labels)

    def test_kmeans_plus_plus_spreads_initial_centers(self):
        X, truth = make_blobs([[0.0, 0.0], [100.0, 0.0], [0.0, 100.0]], 50, std=1.0, seed=4)
        for seed in range(20):
            centers = kmeans_plus_plus_init(X, 3, random.Random(seed))
            self.assertEqual(len(centers), 3)
            for c in centers:
                self.assertIn(c, X, "初期中心はデータ点から選ぶ")
            blobs = {min(range(3), key=lambda k: math.dist(c, [[0, 0], [100, 0], [0, 100]][k])) for c in centers}
            self.assertEqual(blobs, {0, 1, 2}, f"seed={seed}: 遠い点が選ばれやすいはず")

    def test_duplicate_points(self):
        X = [[1.0, 1.0]] * 5 + [[2.0, 2.0]]
        result = kmeans(X, 3, seed=0)
        self.assertAlmostEqual(result.inertia, 0.0)


class TestExercise5TreeAndCV(unittest.TestCase):
    def test_gini(self):
        self.assertEqual(gini([1, 1, 1]), 0.0)
        self.assertAlmostEqual(gini([0, 1, 0, 1]), 0.5)
        self.assertAlmostEqual(gini(["a", "b", "c"]), 2 / 3)
        self.assertEqual(gini([]), 0.0)

    def test_xor_needs_depth_two(self):
        X = [[0, 0], [0, 1], [1, 0], [1, 1]]
        y = [0, 1, 1, 0]
        tree = DecisionTreeClassifier().fit(X, y)
        self.assertEqual(tree.predict(X), y)
        self.assertEqual(tree.depth(), 2)
        self.assertEqual(tree.n_leaves(), 4)
        self.assertEqual(tree.root_.feature, 0, "同点なら番号の小さい特徴量")
        self.assertEqual(tree.root_.threshold, 0.5, "しきい値は隣り合う値の中点")

    def test_threshold_and_stump(self):
        with self.assertRaises(RuntimeError):
            DecisionTreeClassifier().predict([[1.0]])  # fit の前
        tree = DecisionTreeClassifier(max_depth=1).fit([[1], [2], [3], [10]], [0, 0, 1, 1])
        self.assertEqual((tree.root_.feature, tree.root_.threshold), (0, 2.5))
        self.assertEqual(tree.predict([[2.4], [2.6], [100]]), [0, 1, 1])
        self.assertEqual(tree.depth(), 1)

    def test_limits(self):
        X, y = make_xor(200, seed=4)
        self.assertEqual(DecisionTreeClassifier(max_depth=0).fit(X, y).n_leaves(), 1)
        self.assertEqual(DecisionTreeClassifier(min_samples_split=500).fit(X, y).n_leaves(), 1)
        stump = DecisionTreeClassifier(max_depth=1).fit(X, y)
        self.assertLessEqual(accuracy(y, stump.predict(X)), 0.7, "XOR は 1 回の分割では解けない")
        full = DecisionTreeClassifier().fit(X, y)
        self.assertEqual(accuracy(y, full.predict(X)), 1.0, "深さ無制限なら学習データを丸暗記できる")
        self.assertEqual(DecisionTreeClassifier(min_impurity_decrease=1.0).fit(X, y).n_leaves(), 1)

    def test_majority_and_string_labels(self):
        tree = DecisionTreeClassifier(max_depth=0).fit([[0], [1], [2]], ["猫", "犬", "猫"])
        self.assertEqual(tree.predict([[5]]), ["猫"])
        tie = DecisionTreeClassifier(max_depth=0).fit([[0], [1]], ["b", "a"])
        self.assertEqual(tie.predict([[0]]), ["a"], "同数なら小さいラベル")

    def test_feature_importances(self):
        rng = random.Random(8)
        X = [[rng.random(), rng.random()] for _ in range(200)]
        y = [int(x0 > 0.5) for x0, _ in X]  # 特徴量 0 だけが効く
        tree = DecisionTreeClassifier(max_depth=3).fit(X, y)
        self.assertAlmostEqual(sum(tree.feature_importances_), 1.0)
        self.assertGreater(tree.feature_importances_[0], 0.95)

    def test_k_fold_indices(self):
        folds = k_fold_indices(23, 5, seed=1)
        self.assertEqual(len(folds), 5)
        self.assertEqual(sorted(len(te) for _, te in folds), [4, 4, 5, 5, 5])
        all_test = [i for _, te in folds for i in te]
        self.assertEqual(sorted(all_test), list(range(23)), "各点はちょうど 1 回だけ検証に使われる")
        for tr, te in folds:
            self.assertEqual(set(tr) | set(te), set(range(23)))
            self.assertFalse(set(tr) & set(te), "学習と検証が重なってはいけない")
        self.assertEqual(k_fold_indices(23, 5, seed=1), folds, "決定的")
        self.assertEqual(k_fold_indices(6, 3, shuffle=False)[0], ([2, 3, 4, 5], [0, 1]))
        for n, k in [(5, 1), (5, 6)]:
            with self.assertRaises(ValueError):
                k_fold_indices(n, k)

    def test_cross_val_score(self):
        X, y = make_two_gaussians(300, distance=2.0, seed=5)
        scores = cross_val_score(lambda: DecisionTreeClassifier(max_depth=3), X, y, k=5, seed=0)
        self.assertEqual(len(scores), 5)
        self.assertTrue(all(0.0 <= s <= 1.0 for s in scores))
        self.assertGreater(statistics.fmean(scores), 0.8)
        created = []

        def factory():
            created.append(1)
            return DecisionTreeClassifier(max_depth=1)

        cross_val_score(factory, X, y, k=4)
        self.assertEqual(len(created), 4, "分割ごとに新しいモデルを作る")


if __name__ == "__main__":
    unittest.main()
