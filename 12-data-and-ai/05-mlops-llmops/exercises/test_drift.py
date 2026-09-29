"""12.5 演習1: データドリフトの検出 — テスト

実行: python3 tools/check.py 12.5   （またはこのディレクトリで python3 -m unittest -v test_drift）
"""
import math
import random
import unittest

from drift import (
    DriftThresholds,
    FeatureDrift,
    bin_proportions,
    categorical_psi,
    chi2_sf,
    chi_square_drift,
    evaluate_drift,
    ks_p_value,
    ks_statistic,
    psi,
    psi_from_proportions,
    quantile_edges,
)


def gaussians(seed, n, mean=0.0, sd=1.0):
    rng = random.Random(seed)
    return [rng.gauss(mean, sd) for _ in range(n)]


class TestPSI(unittest.TestCase):
    def test_quantile_edges(self):
        self.assertEqual(quantile_edges(list(range(1, 11)), 4), [3, 6, 8])
        self.assertEqual(quantile_edges([5, 1, 4, 2, 3, 10, 9, 8, 7, 6], 4), [3, 6, 8], "並び順に依存しない")
        self.assertEqual(quantile_edges([1] * 9 + [2], 4), [1], "重なった境界は除く")
        with self.assertRaises(ValueError):
            quantile_edges([], 4)
        with self.assertRaises(ValueError):
            quantile_edges([1, 2, 3], 1)

    def test_bin_proportions(self):
        props = bin_proportions([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [3, 6, 8])
        self.assertEqual(props, [0.3, 0.3, 0.2, 0.2])
        self.assertEqual(bin_proportions([3, 3.5, -100, 100], [3, 6]), [0.5, 0.25, 0.25], "境界の値は下側のビン")
        with self.assertRaises(ValueError):
            bin_proportions([], [1])

    def test_psi_from_proportions(self):
        self.assertAlmostEqual(psi_from_proportions([0.5, 0.5], [0.9, 0.1]), 0.4 * math.log(1.8) + 0.4 * math.log(5))
        self.assertEqual(psi_from_proportions([0.25] * 4, [0.25] * 4), 0.0)
        zero_bin = psi_from_proportions([0.5, 0.5], [1.0, 0.0])
        self.assertTrue(math.isfinite(zero_bin), "割合 0 のビンは eps で置き換えて有限にする")
        self.assertAlmostEqual(zero_bin, 0.5 * math.log(1.0 / 0.5) + (1e-4 - 0.5) * math.log(1e-4 / 0.5))
        with self.assertRaises(ValueError):
            psi_from_proportions([0.5, 0.5], [1.0])

    def test_psi_grows_with_shift(self):
        ref = gaussians(0, 5000)
        self.assertEqual(psi(ref, ref), 0.0)
        no_shift = psi(ref, gaussians(1, 5000))
        small = psi(ref, gaussians(2, 5000, mean=0.2))
        large = psi(ref, gaussians(3, 5000, mean=0.5))
        self.assertLess(no_shift, 0.02)
        self.assertTrue(0.02 < small < 0.1, small)
        self.assertGreater(large, 0.2, "平均が標準偏差の半分ずれると PSI は 0.25 前後")
        self.assertLess(no_shift, small)
        self.assertGreater(psi(ref, gaussians(4, 5000, sd=2.0)), 0.2, "ばらつきの変化も検出する")

    def test_categorical_psi(self):
        self.assertEqual(categorical_psi({"a": 50, "b": 50}, {"a": 10, "b": 10}), 0.0)
        with_new = categorical_psi({"web": 90, "store": 10}, {"web": 50, "store": 10, "app": 40})
        self.assertGreater(with_new, 0.25, "新しいカテゴリの出現もドリフトとして数える")
        with self.assertRaises(ValueError):
            categorical_psi({}, {"a": 1})


class TestKSAndChiSquare(unittest.TestCase):
    def test_ks_statistic(self):
        self.assertEqual(ks_statistic([1, 2, 3], [1, 2, 3]), 0.0)
        self.assertEqual(ks_statistic([1, 2, 3], [10, 11]), 1.0)
        self.assertAlmostEqual(ks_statistic([1, 2, 3], [2, 3, 4]), 1 / 3)
        with self.assertRaises(ValueError):
            ks_statistic([], [1])

    def test_ks_handles_ties(self):
        # 同じ値を 1 つずつ処理すると、途中で 2/3 という誤った差を測ってしまう
        self.assertAlmostEqual(ks_statistic([1, 1, 2], [1, 2, 2]), 1 / 3)
        self.assertEqual(ks_statistic([5, 5, 5, 5], [5, 5]), 0.0)

    def test_ks_detects_shift(self):
        # 実装済みの ks_p_value の性質: 差がなければ 1、大きな差なら非常に小さい
        self.assertEqual(ks_p_value(0.0, 100, 100), 1.0)
        self.assertLess(ks_p_value(0.5, 50, 50), 1e-4)
        ref = gaussians(10, 2000)
        same = ks_statistic(ref, gaussians(11, 2000))
        shifted = ks_statistic(ref, gaussians(12, 2000, mean=0.3))
        self.assertLess(same, 0.05)
        self.assertGreater(shifted, 0.1)
        self.assertLess(ks_p_value(shifted, 2000, 2000), 1e-6)

    def test_chi_square_hand_computed(self):
        # 実装済みの chi2_sf が表の値と一致することの確認（自由度 2 では exp(-x/2) に等しい）
        for x, dof, p in [(3.841459, 1, 0.05), (5.991465, 2, 0.05), (18.307038, 10, 0.05), (6.634897, 1, 0.01)]:
            self.assertAlmostEqual(chi2_sf(x, dof), p, places=6)
        self.assertAlmostEqual(chi2_sf(7.3, 2), math.exp(-7.3 / 2))
        stat, dof, p = chi_square_drift({"a": 30, "b": 10}, {"a": 20, "b": 20})
        self.assertAlmostEqual(stat, 16 / 3)  # (5²/25 + 5²/15) × 2
        self.assertEqual(dof, 1)
        self.assertAlmostEqual(p, chi2_sf(16 / 3, 1))
        self.assertLess(p, 0.05)

    def test_chi_square_identical_and_new_category(self):
        stat, dof, p = chi_square_drift({"a": 40, "b": 60}, {"a": 20, "b": 30})
        self.assertAlmostEqual(stat, 0.0)
        self.assertAlmostEqual(p, 1.0)
        stat, dof, p = chi_square_drift({"web": 900, "store": 100}, {"web": 500, "store": 100, "app": 400})
        self.assertEqual(dof, 2, "カテゴリは両方の和集合")
        self.assertLess(p, 1e-10)
        self.assertEqual(chi_square_drift({"a": 5}, {"a": 7}), (0.0, 0, 1.0), "カテゴリが 1 つでは検定できない")
        with self.assertRaises(ValueError):
            chi_square_drift({"a": 0}, {"a": 3})


class TestEvaluateDrift(unittest.TestCase):
    def test_report(self):
        rng = random.Random(20)
        n = 3000
        reference = {
            "amount": gaussians(21, n, mean=5000, sd=1000),
            "age": gaussians(22, n, mean=40, sd=10),
            "channel": [rng.choice(["web", "store"]) for _ in range(n)],
            "region": [rng.choice(["東日本", "西日本"]) for _ in range(n)],
            "income": gaussians(23, n, mean=500, sd=100),
        }
        current = {
            "amount": gaussians(31, n, mean=5800, sd=1000),  # 平均が標準偏差の 0.8 倍ずれた
            "age": gaussians(32, n, mean=40, sd=10),
            "channel": [rng.choice(["web", "store", "app", "app"]) for _ in range(n)],  # 新しい経路が半分
            "region": [rng.choice(["東日本", "西日本"]) for _ in range(n)],
            "income": [None if rng.random() < 0.3 else v for v in gaussians(33, n, mean=500, sd=100)],
        }
        report = evaluate_drift(reference, current, categorical={"channel", "region"})
        self.assertEqual([r.feature for r in report], ["age", "amount", "channel", "income", "region"])
        by = {r.feature: r for r in report}
        self.assertIsInstance(by["age"], FeatureDrift)
        self.assertEqual((by["age"].kind, by["age"].status), ("numeric", "ok"))
        self.assertEqual((by["amount"].status, by["channel"].status), ("alert", "alert"))
        self.assertEqual(by["channel"].kind, "categorical")
        self.assertEqual(by["region"].status, "ok")
        self.assertEqual(by["income"].status, "alert", "欠損率の急増を検出する")
        self.assertAlmostEqual(by["income"].missing_rate_reference, 0.0)
        self.assertGreater(by["income"].missing_rate_current, 0.25)
        self.assertTrue(any("欠損" in reason for reason in by["income"].reasons))
        self.assertTrue(by["amount"].reasons and "PSI" in by["amount"].reasons[0])
        self.assertLess(by["amount"].p_value, 1e-6)

    def test_warn_level(self):
        ref = {"x": gaussians(40, 5000)}
        cur = {"x": gaussians(41, 5000, mean=0.4)}
        (result,) = evaluate_drift(ref, cur)
        self.assertEqual(result.status, "warn", f"PSI={result.psi:.3f}")

    def test_small_samples_are_not_alerted_by_chance(self):
        # 20 件どうしでは、同じ分布でも PSI が大きくなりやすい。p 値のガードで誤報を防ぐ
        ref = {"x": gaussians(50, 20)}
        cur = {"x": gaussians(51, 20)}
        (result,) = evaluate_drift(ref, cur, n_bins=5)
        self.assertGreater(result.psi, 0.1, "小さな標本では PSI だけ見ると誤報になる")
        self.assertEqual(result.status, "ok")

    def test_large_samples_with_tiny_shift_are_not_alerted(self):
        # 標本が大きいと、実務上意味のない小さな差でも p 値は非常に小さくなる。効果の大きさで判断する
        ref = {"x": gaussians(60, 20000)}
        cur = {"x": gaussians(61, 20000, mean=0.05)}
        (result,) = evaluate_drift(ref, cur)
        self.assertLess(result.p_value, 0.01)
        self.assertEqual(result.status, "ok")

    def test_all_missing_and_errors(self):
        (result,) = evaluate_drift({"x": [1.0, 2.0]}, {"x": [None, None]})
        self.assertEqual(result.status, "alert")
        with self.assertRaises(ValueError):
            evaluate_drift({"x": [1.0]}, {})
        with self.assertRaises(ValueError):
            evaluate_drift({"x": [None]}, {"x": [1.0]})
        custom = evaluate_drift({"x": gaussians(70, 3000)}, {"x": gaussians(71, 3000, mean=0.4)},
                                thresholds=DriftThresholds(psi_warn=0.5, psi_alert=0.9))
        self.assertEqual(custom[0].status, "ok", "閾値は設定できる")


if __name__ == "__main__":
    unittest.main()
