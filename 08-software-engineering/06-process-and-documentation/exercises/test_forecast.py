"""8.6 演習1 — モンテカルロ法による完了日の予測のテスト

実行: python3 tools/check.py 8.6   （またはこのディレクトリで python3 -m unittest -v test_forecast）

乱数の使い方が少し違っても通るように、多くのテストは「確率の計算で答えが分かる」場合の、
十分に余裕のある値で確かめています。
"""
import random
import unittest
from datetime import date, timedelta

from forecast import forecast_completion, forecast_items, percentile, simulate_weeks

START = date(2026, 10, 5)
HISTORY = [3, 5, 2, 6, 4, 4, 0, 5, 3, 6]


class TestPercentile(unittest.TestCase):
    def test_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 101)), 85), 85)
        self.assertEqual(percentile([5, 1, 3], 50), 3)
        self.assertEqual(percentile([5, 1, 3], 100), 5)
        with self.assertRaises(ValueError):
            percentile([], 50)
        with self.assertRaises(ValueError):
            percentile([1], 0)


class TestSimulateWeeks(unittest.TestCase):
    def test_constant_throughput_is_deterministic(self):
        self.assertEqual(simulate_weeks([5, 5, 5], 23, runs=50), [5] * 50, "ceil(23 / 5) = 5 週")
        self.assertEqual(simulate_weeks([5], 25, runs=3), [5, 5, 5], "ちょうど 25 件なら 5 週")

    def test_zero_backlog(self):
        self.assertEqual(simulate_weeks(HISTORY, 0, runs=10), [0] * 10)

    def test_runs_and_seed(self):
        a = simulate_weeks(HISTORY, 40, runs=300, seed=7)
        self.assertEqual(len(a), 300)
        self.assertEqual(a, simulate_weeks(HISTORY, 40, runs=300, seed=7), "同じ seed なら同じ結果")

    def test_uses_only_the_given_seed(self):
        random.seed(1)
        state = random.getstate()
        simulate_weeks(HISTORY, 40, runs=100)
        self.assertEqual(random.getstate(), state, "グローバルな random を使わないこと")

    def test_bounds(self):
        weeks = simulate_weeks(HISTORY, 40, runs=2000)
        self.assertGreaterEqual(min(weeks), 7, "最大 6 件/週なら、40 件には最低 7 週かかる")
        self.assertTrue(all(isinstance(w, int) for w in weeks))

    def test_invalid_inputs(self):
        for kwargs in ({"history": [], "backlog": 5}, {"history": [1, -1], "backlog": 5},
                       {"history": [0, 0], "backlog": 5}, {"history": [1], "backlog": -1}):
            with self.assertRaises(ValueError, msg=kwargs):
                simulate_weeks(kwargs["history"], kwargs["backlog"], runs=10)
        with self.assertRaises(ValueError):
            simulate_weeks([1], 5, runs=0)
        with self.assertRaises(ValueError, msg="現実的でない予測は止める"):
            simulate_weeks([0, 0, 0, 0, 0, 0, 0, 0, 0, 1], 100, runs=10, max_weeks=100)


class TestForecastCompletion(unittest.TestCase):
    def test_constant_throughput(self):
        result = forecast_completion([5, 5, 5], 23, START, runs=100)
        self.assertEqual(result, {50: START + timedelta(weeks=5), 85: START + timedelta(weeks=5),
                                  95: START + timedelta(weeks=5)})

    def test_matches_probability_theory(self):
        # 毎週 0 件か 10 件が半々。20 件終えるのにかかる週数 W は「2 回目の成功」までの回数で、
        # P(W <= w) = 1 - (w + 1) / 2^w。P(W<=5) = 0.81、P(W<=6) = 0.89 なので 85% の点は 6 週、
        # P(W<=7) = 0.94、P(W<=8) = 0.96 なので 95% の点は 8 週。
        result = forecast_completion([0, 10], 20, START, runs=20_000, seed=3)
        self.assertEqual(result[85], START + timedelta(weeks=6))
        self.assertEqual(result[95], START + timedelta(weeks=8))
        self.assertIn(result[50], (START + timedelta(weeks=3), START + timedelta(weeks=4)))

    def test_higher_confidence_means_later_date(self):
        result = forecast_completion(HISTORY, 40, START, confidences=(50, 70, 85, 95))
        dates = [result[c] for c in (50, 70, 85, 95)]
        self.assertEqual(dates, sorted(dates))
        self.assertLess(result[50], result[95], "範囲には幅がある")
        self.assertEqual(result[50].weekday(), START.weekday(), "週単位で進む")


class TestForecastItems(unittest.TestCase):
    def test_constant_throughput(self):
        self.assertEqual(forecast_items([5, 5], 4, runs=50), {50: 20, 85: 20, 95: 20})
        self.assertEqual(forecast_items(HISTORY, 0, runs=10), {50: 0, 85: 0, 95: 0})

    def test_matches_probability_theory(self):
        # 4 週の合計は 10 × 二項分布(4, 1/2): 0 件 1/16、10 件 4/16、20 件 6/16、30 件 4/16、40 件 1/16。
        # 「少なくとも X 件」の確率: 10 件以上 15/16 ≒ 94%、20 件以上 11/16 ≒ 69%
        result = forecast_items([0, 10], 4, runs=20_000, seed=5, confidences=(50, 85, 95))
        self.assertEqual(result, {50: 20, 85: 10, 95: 0})

    def test_higher_confidence_means_fewer_items(self):
        result = forecast_items(HISTORY, 8, confidences=(50, 85, 95, 100))
        self.assertGreaterEqual(result[50], result[85])
        self.assertGreaterEqual(result[85], result[95])
        self.assertGreaterEqual(result[95], result[100])
        self.assertTrue(20 <= result[50] <= 40, result)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            forecast_items(HISTORY, -1)
        with self.assertRaises(ValueError):
            forecast_items([], 3)


if __name__ == "__main__":
    unittest.main()
