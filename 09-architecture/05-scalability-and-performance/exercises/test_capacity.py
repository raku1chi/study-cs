"""9.5 スケーラビリティとパフォーマンス — 演習1 のテスト（概算見積もり）

実行: python3 tools/check.py 9.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import unittest

from capacity import (
    amdahl_speedup,
    average_qps,
    bandwidth_bps,
    format_si,
    littles_law_concurrency,
    mm1_response_time,
    peak_qps,
    servers_needed,
    storage_per_year,
    usl_peak_concurrency,
    usl_throughput,
)


class TestExercise1Estimates(unittest.TestCase):
    def test_qps(self):
        self.assertAlmostEqual(average_qps(1_000_000, 20), 231.48148, places=4)
        self.assertEqual(average_qps(86_400, 1), 1.0)
        self.assertAlmostEqual(peak_qps(231.5, 3), 694.5)
        self.assertEqual(peak_qps(100, 1), 100)
        with self.assertRaises(ValueError):
            peak_qps(100, 0.5)
        with self.assertRaises(ValueError):
            average_qps(-1, 10)

    def test_storage_and_bandwidth(self):
        self.assertEqual(storage_per_year(50_000, 2_000), 36_500_000_000)
        self.assertEqual(format_si(storage_per_year(50_000, 2_000), "B"), "36.5 GB")
        self.assertEqual(storage_per_year(1_000, 1_000, replication=3, overhead=1.5), 1_642_500_000)
        self.assertEqual(bandwidth_bps(1_000, 125_000), 1e9, "125KB × 1,000 回/秒 = 1Gbps")
        with self.assertRaises(ValueError):
            storage_per_year(1, 1, replication=0)
        with self.assertRaises(ValueError):
            storage_per_year(1, 1, overhead=0.5)

    def test_servers_needed(self):
        self.assertEqual(servers_needed(1_000, 100, target_utilization=0.5, spare=0), 20)
        self.assertEqual(servers_needed(1_001, 100, target_utilization=0.5, spare=0), 21)
        self.assertEqual(servers_needed(4_900, 700, target_utilization=0.7, spare=0), 10,
                         "浮動小数点の誤差で 1 台多く見積もらないこと")
        self.assertEqual(servers_needed(4_900, 700, target_utilization=0.7), 11, "既定で予備 1 台")
        self.assertEqual(servers_needed(0, 700), 1)
        for kwargs in ({"target_utilization": 0}, {"target_utilization": 1.2}, {"spare": -1}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                servers_needed(100, 10, **kwargs)
        with self.assertRaises(ValueError):
            servers_needed(100, 0)

    def test_littles_law(self):
        self.assertEqual(littles_law_concurrency(1_000, 0.2), 200)
        self.assertEqual(littles_law_concurrency(50, 0.04), 2.0)


class TestExercise1Models(unittest.TestCase):
    def test_amdahl(self):
        self.assertEqual(amdahl_speedup(1.0, 8), 8.0)
        self.assertEqual(amdahl_speedup(0.0, 64), 1.0)
        self.assertAlmostEqual(amdahl_speedup(0.95, 20), 1 / (0.05 + 0.95 / 20))
        self.assertLess(amdahl_speedup(0.95, 10**9), 20.0, "5% が直列なら、何並列にしても 20 倍未満")
        for args in ((1.5, 2), (-0.1, 2), (0.5, 0)):
            with self.assertRaises(ValueError, msg=str(args)):
                amdahl_speedup(*args)

    def test_usl(self):
        self.assertEqual(usl_throughput(1, 100, 0.1, 0.01), 100)
        self.assertEqual(usl_throughput(10, 100, 0.0, 0.0), 1000, "σ = κ = 0 なら線形にスケールする")
        # 競合だけ（κ = 0）なら頭打ちになるが、減りはしない
        self.assertGreater(usl_throughput(64, 100, 0.05, 0.0), usl_throughput(32, 100, 0.05, 0.0))
        # 一貫性のコスト（κ > 0）があると、ある並列度を超えるとスループットが下がる（逆行）
        peak = usl_peak_concurrency(0.05, 0.001)
        self.assertAlmostEqual(peak, math.sqrt(0.95 / 0.001))
        best = usl_throughput(round(peak), 100, 0.05, 0.001)
        self.assertGreater(best, usl_throughput(round(peak) * 2, 100, 0.05, 0.001))
        self.assertGreater(best, usl_throughput(round(peak) // 2, 100, 0.05, 0.001))
        with self.assertRaises(ValueError):
            usl_peak_concurrency(0.1, 0)
        with self.assertRaises(ValueError):
            usl_peak_concurrency(1.0, 0.01)
        with self.assertRaises(ValueError):
            usl_throughput(0, 100, 0.1, 0.1)

    def test_mm1(self):
        self.assertEqual(mm1_response_time(0.01, 0.0), 0.01)
        self.assertAlmostEqual(mm1_response_time(0.01, 0.5), 0.02)
        self.assertAlmostEqual(mm1_response_time(0.01, 0.9), 0.1)
        self.assertAlmostEqual(mm1_response_time(0.01, 0.99), 1.0)
        for u in (1.0, 1.2, -0.1):
            with self.assertRaises(ValueError, msg=str(u)):
                mm1_response_time(0.01, u)


if __name__ == "__main__":
    unittest.main()
