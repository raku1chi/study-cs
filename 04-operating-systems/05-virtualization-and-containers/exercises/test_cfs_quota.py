"""4.5 仮想化とコンテナ — cfs_quota のテスト

実行: python3 tools/check.py 4.5   （またはこのディレクトリで python3 -m unittest -v test_cfs_quota）
"""
import random
import unittest

from cfs_quota import Burst, CfsResult, latencies, min_quota_without_throttling, simulate

B = Burst
FOUR_BUSY = [B(f"T{i}", 0, 50) for i in range(4)]


class TestExercise2Simulate(unittest.TestCase):
    def test_no_quota_runs_in_parallel(self):
        r = simulate(FOUR_BUSY, quota=None, period=100, cpus=4)
        self.assertEqual(r, CfsResult({f"T{i}": 50 for i in range(4)}, 1, 0, 0))

    def test_four_busy_threads_with_one_cpu_quota_are_throttled(self):
        r = simulate(FOUR_BUSY, quota=100, period=100, cpus=4)
        # 4 スレッドが並列に走ると、25 ms でクォータ（CPU 1 個分 × 100 ms）を使い切り、残り 75 ms は止められる
        self.assertEqual(r.finish, {f"T{i}": 125 for i in range(4)}, "制限がなければ 50 ms で終わる仕事")
        self.assertEqual((r.nr_periods, r.nr_throttled, r.throttled_time), (2, 1, 75))

    def test_enough_quota_means_no_throttling(self):
        self.assertEqual(simulate(FOUR_BUSY, quota=400, period=100, cpus=4).nr_throttled, 0)
        self.assertEqual(simulate(FOUR_BUSY, quota=200, period=100, cpus=4).nr_throttled, 0)
        r = simulate(FOUR_BUSY, quota=199, period=100, cpus=4)
        self.assertEqual((r.nr_throttled, max(r.finish.values())), (1, 101), "1 ms 足りないだけで次の周期まで待つ")

    def test_single_thread_is_never_throttled_by_one_cpu_quota(self):
        r = simulate([B("solo", 0, 150)], quota=100, period=100, cpus=4)
        self.assertEqual(r, CfsResult({"solo": 150}, 2, 0, 0))

    def test_cpus_limit_parallelism(self):
        r = simulate(FOUR_BUSY, quota=None, period=100, cpus=2)
        self.assertEqual(max(r.finish.values()), 100, "CPU が 2 個なら、4 つの仕事は 2 つずつしか走れない")

    def test_fair_sharing_prefers_the_one_that_received_less(self):
        bursts = [B("long", 0, 30), B("short", 10, 5)]
        r = simulate(bursts, quota=None, period=100, cpus=1)
        self.assertEqual(r.finish, {"short": 15, "long": 35}, "後から来た short は、CPU をまだもらっていないので優先される")

    def test_short_request_stalls_behind_a_burst(self):
        # 8 本の GC スレッドが一斉に動いてクォータを使い切った後に、5 ms の小さなリクエストが来る
        bursts = [B(f"gc{i}", 0, 12) for i in range(8)] + [B("req", 10, 5)]
        unlimited = simulate(bursts, quota=None, period=100, cpus=8)
        limited = simulate(bursts, quota=50, period=100, cpus=8)
        self.assertEqual(latencies(bursts, unlimited)["req"], 5)
        self.assertEqual(latencies(bursts, limited)["req"], 95, "次の周期までクォータの補充を待たされる")
        self.assertEqual((limited.nr_periods, limited.nr_throttled, limited.throttled_time), (3, 2, 186))

    def test_matching_parallelism_to_the_quota_avoids_the_stall(self):
        # GOMAXPROCS を小さくするのと同じ: 仕事の総量は同じでも、並列度を下げると小さなリクエストが止められない
        bursts = [B(f"gc{i}", 0, 48) for i in range(2)] + [B("req", 10, 5)]
        r = simulate(bursts, quota=50, period=100, cpus=8)
        self.assertEqual(latencies(bursts, r)["req"], 5)
        self.assertEqual(max(r.finish.values()), 201, "GC 自体の完了時刻は 8 並列のときと変わらない")

    def test_idle_periods_are_not_counted(self):
        r = simulate([B("a", 0, 10), B("b", 350, 10)], quota=100, period=100, cpus=1)
        self.assertEqual(r.finish, {"a": 10, "b": 360})
        self.assertEqual((r.nr_periods, r.nr_throttled), (2, 0), "誰も実行可能でない周期は数えない")

    def test_conservation_on_random_inputs(self):
        rng = random.Random(51)
        for _ in range(100):
            bursts = [B(f"j{i}", rng.randrange(0, 200), rng.randrange(1, 40)) for i in range(rng.randrange(1, 6))]
            quota = rng.choice([None, 20, 50, 100, 250])
            period = rng.choice([50, 100])
            cpus = rng.randrange(1, 5)
            r = simulate(bursts, quota=quota, period=period, cpus=cpus)
            self.assertEqual(set(r.finish), {b.name for b in bursts})
            for b in bursts:
                self.assertGreaterEqual(r.finish[b.name] - b.start, b.work, b)
            unlimited = simulate(bursts, quota=None, period=period, cpus=cpus)
            self.assertLessEqual(max(unlimited.finish.values()), max(r.finish.values()), "制限で速くなることはない")
            if quota is None:
                self.assertEqual((r.nr_throttled, r.throttled_time), (0, 0))

    def test_invalid_arguments(self):
        for kwargs in ({"quota": 0}, {"quota": 10, "period": 0}, {"quota": 10, "cpus": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                simulate(FOUR_BUSY, **kwargs)
        for bursts in ([B("a", 0, 0)], [B("a", -1, 5)], [B("a", 0, 5), B("a", 1, 5)]):
            with self.assertRaises(ValueError, msg=str(bursts)):
                simulate(bursts, quota=None)


class TestExercise3MinQuota(unittest.TestCase):
    def test_four_busy_threads_need_two_cpus_worth(self):
        self.assertEqual(min_quota_without_throttling(FOUR_BUSY, period=100, cpus=4), 200)

    def test_single_thread(self):
        self.assertEqual(min_quota_without_throttling([B("solo", 0, 150)], period=100, cpus=4), 100)

    def test_bursty_workload_needs_much_more_than_its_average(self):
        # 1 秒ごとに 8 スレッドが 20 ms ずつ並列に動くだけ。平均の CPU 使用量は 0.16 個分にすぎない
        bursts = [B(f"b{k}_{i}", k * 1000, 20) for k in range(3) for i in range(8)]
        average_cpus = sum(b.work for b in bursts) / 3000
        self.assertAlmostEqual(average_cpus, 0.16)
        self.assertEqual(min_quota_without_throttling(bursts, period=100, cpus=8), 160,
                         "必要なクォータは平均ではなく、1 周期の中のピーク（CPU 1.6 個分）で決まる")

    def test_result_is_exactly_the_threshold(self):
        rng = random.Random(52)
        for _ in range(40):
            bursts = [B(f"j{i}", rng.randrange(0, 150), rng.randrange(1, 30)) for i in range(rng.randrange(1, 6))]
            cpus = rng.randrange(1, 5)
            q = min_quota_without_throttling(bursts, period=50, cpus=cpus)
            self.assertEqual(simulate(bursts, quota=q, period=50, cpus=cpus).nr_throttled, 0, bursts)
            if q > 1:
                self.assertGreater(simulate(bursts, quota=q - 1, period=50, cpus=cpus).nr_throttled, 0, bursts)

    def test_empty_is_an_error(self):
        with self.assertRaises(ValueError):
            min_quota_without_throttling([])


if __name__ == "__main__":
    unittest.main()
