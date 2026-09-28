"""7.1 分散システムの本質 — 故障検出器のテスト

実行: python3 tools/check.py 7.1   （またはこのディレクトリで python3 -m unittest -v test_failure_detector）

時計は注入可能（FakeClock）なので、テストは実時間を待たずに一瞬で終わります。
"""
import math
import random
import unittest

from failure_detector import HeartbeatFailureDetector, PhiAccrualFailureDetector


class FakeClock:
    """テスト用の時計。呼び出すと現在時刻（秒）を返す。advance で進める。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, dt: float) -> None:
        self.now += dt


class TestExercise6HeartbeatDetector(unittest.TestCase):
    def test_alive_within_timeout_and_suspected_after(self):
        clock = FakeClock()
        fd = HeartbeatFailureDetector(timeout=3.0, clock=clock)
        fd.heartbeat("n1")
        clock.advance(2.0)
        self.assertTrue(fd.is_alive("n1"))
        clock.advance(1.0)
        self.assertTrue(fd.is_alive("n1"), "ちょうど timeout 秒はまだ生存とみなす（<=）")
        clock.advance(0.001)
        self.assertFalse(fd.is_alive("n1"))
        self.assertEqual(fd.suspects(), ["n1"])

    def test_new_heartbeat_revives(self):
        clock = FakeClock()
        fd = HeartbeatFailureDetector(timeout=1.0, clock=clock)
        fd.heartbeat("n1")
        clock.advance(5.0)
        self.assertFalse(fd.is_alive("n1"))
        fd.heartbeat("n1")
        self.assertTrue(fd.is_alive("n1"), "遅れていただけのノードは、便りが来れば生存に戻る")

    def test_multiple_nodes(self):
        clock = FakeClock()
        fd = HeartbeatFailureDetector(timeout=2.0, clock=clock)
        for n in ("c", "a", "b"):
            fd.heartbeat(n)
        clock.advance(1.5)
        fd.heartbeat("b")
        clock.advance(1.0)
        self.assertEqual(fd.suspects(), ["a", "c"])
        self.assertEqual(fd.alive_nodes(), ["b"])

    def test_unknown_node_is_not_alive_and_not_listed(self):
        fd = HeartbeatFailureDetector(timeout=1.0, clock=FakeClock())
        self.assertFalse(fd.is_alive("never-seen"))
        self.assertEqual(fd.suspects(), [])
        self.assertEqual(fd.alive_nodes(), [])

    def test_clock_going_backwards_is_rejected(self):
        clock = FakeClock()
        fd = HeartbeatFailureDetector(timeout=1.0, clock=clock)
        fd.heartbeat("n1")
        clock.advance(-0.5)  # 壁時計なら NTP の補正やうるう秒で起こりうる
        with self.assertRaises(ValueError):
            fd.heartbeat("n1")

    def test_invalid_timeout(self):
        for t in (0, -1.0):
            with self.assertRaises(ValueError):
                HeartbeatFailureDetector(timeout=t, clock=FakeClock())


def feed(fd: PhiAccrualFailureDetector, clock: FakeClock, intervals) -> None:
    fd.heartbeat()
    for dt in intervals:
        clock.advance(dt)
        fd.heartbeat()


class TestExercise7PhiAccrual(unittest.TestCase):
    def test_no_heartbeat_yet(self):
        fd = PhiAccrualFailureDetector(clock=FakeClock())
        self.assertEqual(fd.phi(), 0.0)
        self.assertTrue(fd.is_available(), "監視を始める前のノードは疑わない")

    def test_first_heartbeat_uses_estimate(self):
        clock = FakeClock()
        fd = PhiAccrualFailureDetector(first_heartbeat_estimate=2.0, clock=clock)
        fd.heartbeat()
        self.assertAlmostEqual(fd.mean(), 2.0)
        self.assertAlmostEqual(fd.std(), 0.5, msg="推定値 ± 1/4 の 2 標本 → 標準偏差は推定値の 1/4")
        clock.advance(2.0)
        self.assertAlmostEqual(fd.phi(), -math.log10(0.5), places=6)
        clock.advance(10.0)
        self.assertFalse(fd.is_available(), "1 回だけ来て止まったノードも、いずれ疑われる")

    def test_phi_formula_with_regular_heartbeats(self):
        clock = FakeClock()
        fd = PhiAccrualFailureDetector(window_size=10, min_std=0.1, clock=clock)
        feed(fd, clock, [1.0] * 20)  # 窓には 1.0 が 10 個だけ残る
        self.assertAlmostEqual(fd.mean(), 1.0)
        self.assertAlmostEqual(fd.std(), 0.1, msg="ばらつき 0 でも min_std で下限を設ける")
        clock.advance(1.0)  # 平均ちょうど → P_later = 0.5
        self.assertAlmostEqual(fd.phi(), 0.30103, places=5)
        clock.advance(0.2)  # 平均 + 2σ → P_later ≈ 0.02275
        self.assertAlmostEqual(fd.phi(), 1.64302, places=4)
        clock.advance(0.8)  # 平均 + 10σ
        self.assertGreater(fd.phi(), 20.0)
        self.assertFalse(fd.is_available())

    def test_phi_is_non_decreasing_while_silent(self):
        clock = FakeClock()
        rng = random.Random(7)
        fd = PhiAccrualFailureDetector(clock=clock)
        feed(fd, clock, [rng.gauss(1.0, 0.1) for _ in range(50)])
        previous = -1.0
        for _ in range(200):
            clock.advance(0.05)
            value = fd.phi()
            self.assertGreaterEqual(value, previous)
            previous = value
        self.assertEqual(previous, math.inf, "十分長く沈黙すると φ は無限大になる（例外にしない）")

    def test_low_phi_right_after_heartbeat(self):
        clock = FakeClock()
        rng = random.Random(8)
        fd = PhiAccrualFailureDetector(clock=clock)
        for _ in range(100):
            clock.advance(max(0.01, rng.gauss(1.0, 0.2)))
            fd.heartbeat()
            self.assertLess(fd.phi(), 0.1)
            self.assertTrue(fd.is_available())

    def test_adapts_to_each_nodes_rhythm(self):
        # 同じ「3 秒の沈黙」でも、1 秒ごとに来るノードでは異常、5 秒ごとのノードでは正常
        fast_clock, slow_clock = FakeClock(), FakeClock()
        fast = PhiAccrualFailureDetector(clock=fast_clock, min_std=0.2)
        slow = PhiAccrualFailureDetector(clock=slow_clock, min_std=0.2)
        rng = random.Random(9)
        feed(fast, fast_clock, [rng.gauss(1.0, 0.1) for _ in range(150)])
        feed(slow, slow_clock, [rng.gauss(5.0, 0.5) for _ in range(150)])
        fast_clock.advance(3.0)
        slow_clock.advance(3.0)
        self.assertFalse(fast.is_available(), fast.phi())
        self.assertTrue(slow.is_available(), slow.phi())

    def test_window_forgets_old_intervals(self):
        clock = FakeClock()
        fd = PhiAccrualFailureDetector(window_size=5, clock=clock)
        feed(fd, clock, [10.0] * 5 + [1.0] * 5)
        self.assertAlmostEqual(fd.mean(), 1.0, msg="窓の外に出た古い間隔は使わない")

    def test_acceptable_pause_shifts_the_distribution(self):
        clock_a, clock_b = FakeClock(), FakeClock()
        plain = PhiAccrualFailureDetector(window_size=10, clock=clock_a)
        tolerant = PhiAccrualFailureDetector(window_size=10, acceptable_pause=2.0, clock=clock_b)
        feed(plain, clock_a, [1.0] * 10)
        feed(tolerant, clock_b, [1.0] * 10)
        clock_a.advance(3.0)
        clock_b.advance(3.0)
        self.assertFalse(plain.is_available())
        self.assertAlmostEqual(tolerant.phi(), 0.30103, places=5, msg="平均 + 2 秒まで GC 停止などを許容")

    def test_threshold_decides_availability(self):
        clock = FakeClock()
        fd = PhiAccrualFailureDetector(threshold=1.0, window_size=10, clock=clock)
        feed(fd, clock, [1.0] * 10)
        clock.advance(1.1)  # 平均 + 1σ → φ ≈ 0.80
        self.assertTrue(fd.is_available())
        clock.advance(0.1)  # 平均 + 2σ → φ ≈ 1.64
        self.assertFalse(fd.is_available())

    def test_clock_going_backwards_is_rejected(self):
        clock = FakeClock()
        fd = PhiAccrualFailureDetector(clock=clock)
        fd.heartbeat()
        clock.advance(-1.0)
        with self.assertRaises(ValueError):
            fd.heartbeat()

    def test_mean_before_heartbeat_raises(self):
        fd = PhiAccrualFailureDetector(clock=FakeClock())
        with self.assertRaises(ValueError):
            fd.mean()
        with self.assertRaises(ValueError):
            fd.std()

    def test_invalid_parameters(self):
        for kwargs in (
            {"threshold": 0},
            {"window_size": 0},
            {"min_std": 0},
            {"acceptable_pause": -1},
            {"first_heartbeat_estimate": 0},
        ):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                PhiAccrualFailureDetector(clock=FakeClock(), **kwargs)


if __name__ == "__main__":
    unittest.main()
