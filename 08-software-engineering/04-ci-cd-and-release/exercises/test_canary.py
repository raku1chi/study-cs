"""8.4 演習2 — カナリア分析の自動判定のテスト

実行: python3 tools/check.py 8.4   （またはこのディレクトリで python3 -m unittest -v test_canary）
"""
import math
import statistics
import unittest

from canary import GroupMetrics, Verdict, analyze, percentile, two_proportion_z_test


def latencies(base_ms, n=1000, spread=40):
    """決定的なレイテンシの標本: base_ms から base_ms + spread まで一様に並べたもの。"""
    return [base_ms + spread * i / (n - 1) for i in range(n)]


def reference_z(xb, nb, xc, nc):
    pb, pc, p = xb / nb, xc / nc, (xb + xc) / (nb + nc)
    z = (pc - pb) / math.sqrt(p * (1 - p) * (1 / nb + 1 / nc))
    return z, 1 - statistics.NormalDist().cdf(z)


GOOD = latencies(100)  # p95 は約 138 ms


class TestPercentile(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 101)), 95), 95)
        self.assertEqual(percentile(list(range(1, 101)), 50), 50)
        self.assertEqual(percentile(list(range(1, 101)), 100), 100)
        self.assertEqual(percentile(list(range(1, 101)), 0.5), 1)
        self.assertEqual(percentile([10, 30, 20], 50), 20)
        self.assertEqual(percentile([7], 99), 7)
        self.assertEqual(percentile(list(range(1, 21)), 95), 19)  # ceil(0.95 × 20) = 19 番目

    def test_does_not_modify_input(self):
        values = [3, 1, 2]
        percentile(values, 50)
        self.assertEqual(values, [3, 1, 2])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            percentile([], 50)
        for p in (0, -1, 101):
            with self.assertRaises(ValueError, msg=p):
                percentile([1, 2], p)


class TestZTest(unittest.TestCase):
    def test_matches_reference(self):
        for args in [(10, 1000, 25, 1000), (50, 20000, 70, 20000), (3, 500, 9, 800), (30, 1000, 20, 1000)]:
            z, p = two_proportion_z_test(*args)
            ref_z, ref_p = reference_z(*args)
            self.assertAlmostEqual(z, ref_z, places=9, msg=args)
            self.assertAlmostEqual(p, ref_p, places=9, msg=args)

    def test_known_value(self):
        z, p = two_proportion_z_test(10, 1000, 25, 1000)
        self.assertAlmostEqual(z, 2.558, places=3)
        self.assertAlmostEqual(p, 0.00526, places=4)

    def test_better_canary_has_large_p_value(self):
        _, p = two_proportion_z_test(30, 1000, 10, 1000)
        self.assertGreater(p, 0.99)

    def test_zero_standard_error(self):
        self.assertEqual(two_proportion_z_test(0, 1000, 0, 1000), (0.0, 0.5))
        self.assertEqual(two_proportion_z_test(10, 10, 20, 20), (0.0, 0.5))

    def test_invalid(self):
        for args in [(1, 0, 1, 10), (-1, 10, 1, 10), (11, 10, 1, 10), (1, 10, 5, 4)]:
            with self.assertRaises(ValueError, msg=args):
                two_proportion_z_test(*args)


class TestAnalyze(unittest.TestCase):
    def test_not_enough_requests(self):
        v = analyze(GroupMetrics(5000, 5, GOOD), GroupMetrics(300, 0, GOOD))
        self.assertIsInstance(v, Verdict)
        self.assertEqual(v.decision, "CONTINUE")
        self.assertTrue(v.reasons)

    def test_not_enough_latency_samples(self):
        v = analyze(GroupMetrics(5000, 5, GOOD), GroupMetrics(5000, 5, GOOD[:50]))
        self.assertEqual(v.decision, "CONTINUE")

    def test_healthy_canary_is_promoted(self):
        v = analyze(GroupMetrics(20000, 20, GOOD), GroupMetrics(20000, 22, latencies(101)))
        self.assertEqual((v.decision, v.reasons), ("PROMOTE", ()))
        self.assertAlmostEqual(v.baseline_error_rate, 0.001)
        self.assertAlmostEqual(v.canary_error_rate, 0.0011)
        self.assertAlmostEqual(v.baseline_p95, 138.0, places=1)
        self.assertIsNotNone(v.p_value)

    def test_error_rate_regression_rolls_back(self):
        v = analyze(GroupMetrics(10000, 10, GOOD), GroupMetrics(10000, 45, GOOD))
        self.assertEqual(v.decision, "ROLLBACK")
        self.assertEqual(len(v.reasons), 1)
        self.assertLess(v.p_value, 0.01)

    def test_noise_is_not_a_regression(self):
        # 0.30% → 0.45% は、この標本数では偶然の範囲（p ≈ 0.14 > 0.01）
        v = analyze(GroupMetrics(4000, 12, GOOD), GroupMetrics(4000, 18, GOOD))
        self.assertEqual(v.decision, "PROMOTE")
        self.assertGreater(v.p_value, 0.01)

    def test_significant_but_tiny_difference_is_promoted(self):
        # 100 万件ずつなら 0.100% → 0.115% でも「有意」になるが、差は 0.015 ポイントで効果量の下限（0.1）未満
        v = analyze(GroupMetrics(1_000_000, 1000, GOOD), GroupMetrics(1_000_000, 1150, GOOD))
        self.assertLess(v.p_value, 0.01, "統計的には有意")
        self.assertEqual(v.decision, "PROMOTE", "実務上は無視できる差")

    def test_latency_regression_rolls_back(self):
        v = analyze(GroupMetrics(5000, 5, GOOD), GroupMetrics(5000, 5, latencies(150)))  # p95 138 → 188
        self.assertEqual(v.decision, "ROLLBACK")
        self.assertIn("p95", "".join(v.reasons))

    def test_latency_ratio_at_threshold_is_ok(self):
        v = analyze(GroupMetrics(5000, 5, [100.0] * 300), GroupMetrics(5000, 5, [120.0] * 300))
        self.assertEqual(v.decision, "PROMOTE", "1.2 倍ちょうどは許容（> で判定）")

    def test_both_regressions_give_two_reasons(self):
        v = analyze(GroupMetrics(10000, 10, GOOD), GroupMetrics(10000, 60, latencies(200)))
        self.assertEqual((v.decision, len(v.reasons)), ("ROLLBACK", 2))

    def test_zero_baseline_latency(self):
        v = analyze(GroupMetrics(5000, 0, [0.0] * 300), GroupMetrics(5000, 0, [0.0] * 300))
        self.assertEqual(v.decision, "PROMOTE")
        v = analyze(GroupMetrics(5000, 0, [0.0] * 300), GroupMetrics(5000, 0, [5.0] * 300))
        self.assertEqual(v.decision, "ROLLBACK")

    def test_custom_thresholds(self):
        base, canary = GroupMetrics(5000, 5, GOOD), GroupMetrics(5000, 5, latencies(115))  # p95 138 → 153（1.11 倍）
        self.assertEqual(analyze(base, canary).decision, "PROMOTE")
        self.assertEqual(analyze(base, canary, max_p95_ratio=1.1).decision, "ROLLBACK")
        self.assertEqual(analyze(base, canary, min_requests=10_000).decision, "CONTINUE")

    def test_invalid_input(self):
        for bad in (GroupMetrics(-1, 0, GOOD), GroupMetrics(10, 11, GOOD), GroupMetrics(10, 1, [1.0, -2.0])):
            with self.assertRaises(ValueError):
                analyze(GroupMetrics(5000, 5, GOOD), bad)


if __name__ == "__main__":
    unittest.main()
