"""10.4 Prometheus 風のメトリクス計算 — テスト

実行: python3 tools/check.py 10.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import unittest

from histo import (
    DEFAULT_BUCKETS,
    Histogram,
    average_of_quantiles,
    counter_increase,
    counter_rate,
    exact_quantile,
    histogram_quantile,
    merge_all,
)

INF = math.inf


class TestExercise1Counter(unittest.TestCase):
    def test_increase_without_reset(self):
        self.assertEqual(counter_increase([(0, 100), (15, 130), (30, 190)]), 90)

    def test_increase_with_reset(self):
        # 30〜45 秒の間にプロセスが再起動し、カウンタが 0 から数え直した
        samples = [(0, 100), (15, 160), (30, 220), (45, 20), (60, 80)]
        self.assertEqual(counter_increase(samples), 60 + 60 + 20 + 60)
        self.assertAlmostEqual(counter_rate(samples), 200 / 60)

    def test_constant_counter(self):
        self.assertEqual(counter_increase([(0, 5), (10, 5)]), 0)
        self.assertEqual(counter_rate([(0, 5), (10, 5)]), 0)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            counter_increase([(0, 1)])
        with self.assertRaises(ValueError):
            counter_rate([])
        with self.assertRaises(ValueError):
            counter_increase([(10, 1), (10, 2)])


class TestExercise2HistogramQuantile(unittest.TestCase):
    def test_interpolates_within_bucket(self):
        buckets = [(0.1, 50), (0.25, 80), (0.5, 95), (1.0, 100), (INF, 100)]
        # 90 番目の観測値は (0.25, 0.5] のバケットの 10/15 の位置
        self.assertAlmostEqual(histogram_quantile(0.9, buckets), 0.25 + 0.25 * 10 / 15)
        self.assertAlmostEqual(histogram_quantile(0.5, buckets), 0.1, msg="ちょうどバケットの上限")
        self.assertAlmostEqual(histogram_quantile(0.25, buckets), 0.05, msg="最初のバケットの下限は 0")

    def test_order_of_buckets_does_not_matter(self):
        buckets = [(INF, 100), (1.0, 100), (0.1, 50), (0.5, 95), (0.25, 80)]
        self.assertAlmostEqual(histogram_quantile(0.9, buckets), 0.25 + 0.25 * 10 / 15)

    def test_rank_in_inf_bucket_returns_highest_finite_bound(self):
        buckets = [(0.1, 50), (0.25, 80), (0.5, 95), (1.0, 98), (INF, 100)]
        self.assertEqual(histogram_quantile(0.99, buckets), 1.0, "+Inf のバケットは補間できない")

    def test_empty_histogram_is_nan(self):
        self.assertTrue(math.isnan(histogram_quantile(0.5, [(0.1, 0), (INF, 0)])))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            histogram_quantile(0.5, [(0.1, 1), (1.0, 2)])            # +Inf がない
        with self.assertRaises(ValueError):
            histogram_quantile(1.5, [(0.1, 1), (INF, 2)])
        with self.assertRaises(ValueError):
            histogram_quantile(0.5, [(0.1, 5), (1.0, 3), (INF, 6)])  # 累積が減っている

    def test_observe_and_cumulative(self):
        h = Histogram([0.1, 0.5, 1.0])
        for v in (0.05, 0.1, 0.3, 0.7, 2.0, 5.0):
            h.observe(v)
        self.assertEqual(h.cumulative(), [(0.1, 2), (0.5, 3), (1.0, 4), (INF, 6)], "上限ちょうどの値はそのバケットに入る")
        self.assertEqual(h.count, 6)
        self.assertAlmostEqual(h.sum, 8.15)
        with self.assertRaises(ValueError):
            h.observe(math.nan)

    def test_default_buckets(self):
        h = Histogram()
        self.assertEqual(h.bounds, DEFAULT_BUCKETS)
        self.assertEqual(len(h.cumulative()), len(DEFAULT_BUCKETS) + 1)

    def test_invalid_bounds(self):
        for bounds in ([], [0.5, 0.1], [0.1, 0.1], [0.1, INF]):
            with self.assertRaises(ValueError, msg=bounds):
                Histogram(bounds)

    def test_estimate_is_within_bucket_of_exact(self):
        rng = random.Random(404)
        values = [rng.lognormvariate(-2.5, 0.8) for _ in range(5000)]
        h = Histogram()
        for v in values:
            h.observe(v)
        for q in (0.5, 0.9, 0.95, 0.99):
            exact = exact_quantile(values, q)
            estimate = h.quantile(q)
            # 推定値は、正確な値が入っているバケットの範囲内に収まる
            upper = next(b for b in DEFAULT_BUCKETS + (INF,) if exact <= b)
            idx = (DEFAULT_BUCKETS + (INF,)).index(upper)
            lower = DEFAULT_BUCKETS[idx - 1] if idx > 0 else 0.0
            self.assertTrue(lower <= estimate <= upper, (q, exact, estimate, lower, upper))


class TestExercise2Merge(unittest.TestCase):
    def test_merge_sums_buckets(self):
        a, b = Histogram([0.1, 1.0]), Histogram([0.1, 1.0])
        for v in (0.05, 0.5):
            a.observe(v)
        for v in (0.07, 3.0, 4.0):
            b.observe(v)
        m = a.merge(b)
        self.assertEqual(m.cumulative(), [(0.1, 2), (1.0, 3), (INF, 5)])
        self.assertEqual(m.count, 5)
        self.assertAlmostEqual(m.sum, 7.62)
        self.assertEqual(a.count, 2, "merge は元のヒストグラムを変更しない")
        self.assertEqual(merge_all([a, b, a]).count, 7)

    def test_merge_requires_same_bounds(self):
        with self.assertRaises(ValueError):
            Histogram([0.1, 1.0]).merge(Histogram([0.1, 2.0]))
        with self.assertRaises(ValueError):
            merge_all([])

    def test_averaging_quantiles_is_wrong(self):
        # インスタンス A は大量の速いリクエスト、B は少量の遅いリクエストを処理している
        a, b = Histogram(), Histogram()
        for _ in range(980):
            a.observe(0.02)
        for _ in range(20):
            b.observe(2.0)
        averaged = average_of_quantiles([a, b], 0.95)
        merged = merge_all([a, b]).quantile(0.95)
        exact = exact_quantile([0.02] * 980 + [2.0] * 20, 0.95)
        self.assertAlmostEqual(averaged, (0.01 + 0.015 * 931 / 980 + 1.0 + 1.5 * 19 / 20) / 2)
        self.assertAlmostEqual(merged, 0.01 + 0.015 * 950 / 980)
        self.assertEqual(exact, 0.02)
        self.assertGreater(averaged / merged, 40, "p95 の平均は、全体の p95 の 40 倍以上にもなりうる")

    def test_averaging_can_also_underestimate(self):
        a, b = Histogram(), Histogram()
        for _ in range(500):
            a.observe(0.02)
        for _ in range(500):
            b.observe(2.0)
        self.assertLess(average_of_quantiles([a, b], 0.95), merge_all([a, b]).quantile(0.95))


if __name__ == "__main__":
    unittest.main()
