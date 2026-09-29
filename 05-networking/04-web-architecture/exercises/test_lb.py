"""5.4 Webの仕組みとネットワーク構成 — テスト（lb）

実行: python3 tools/check.py 5.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import collections
import random
import unittest

from lb import (
    Backend,
    HealthChecker,
    LeastConnections,
    LoadBalancer,
    NoAvailableBackend,
    PowerOfTwoChoices,
    RoundRobin,
    SmoothWeightedRoundRobin,
)


def make(*specs, strategy=None):
    backends = [Backend(name, weight) for name, weight in specs]
    return LoadBalancer(backends, strategy or RoundRobin())


def picks(lb, n, release=True):
    names = []
    for _ in range(n):
        b = lb.acquire()
        names.append(b.name)
        if release:
            lb.release(b)
    return "".join(names)


class TestRoundRobin(unittest.TestCase):
    def test_rotates_in_order(self):
        lb = make(("a", 1), ("b", 1), ("c", 1))
        self.assertEqual(picks(lb, 7), "abcabca")

    def test_skips_unhealthy(self):
        lb = make(("a", 1), ("b", 1), ("c", 1))
        lb.set_health("b", False)
        self.assertEqual(picks(lb, 4), "acac")

    def test_counts_connections(self):
        lb = make(("a", 1), ("b", 1))
        a = lb.acquire()
        lb.acquire()
        lb.acquire()
        self.assertEqual((lb.backend("a").active_connections, lb.backend("b").active_connections), (2, 1))
        lb.release(a)
        lb.release("b")
        self.assertEqual((lb.backend("a").active_connections, lb.backend("b").active_connections), (1, 0))


class TestSmoothWeightedRoundRobin(unittest.TestCase):
    def test_nginx_example(self):
        # nginx の変更履歴にある例: 重み {5, 1, 1} で a a b a c a a（a が 5 回連続しない）
        lb = make(("a", 5), ("b", 1), ("c", 1), strategy=SmoothWeightedRoundRobin())
        self.assertEqual(picks(lb, 7), "aabacaa")
        self.assertEqual(picks(lb, 7), "aabacaa", "7 回ごとに同じ並びを繰り返す")

    def test_other_weights(self):
        lb = make(("a", 3), ("b", 2), ("c", 1), strategy=SmoothWeightedRoundRobin())
        self.assertEqual(picks(lb, 12), "abacbaabacba")

    def test_equal_weights_is_round_robin(self):
        lb = make(("a", 1), ("b", 1), ("c", 1), strategy=SmoothWeightedRoundRobin())
        self.assertEqual(picks(lb, 6), "abcabc")

    def test_distribution_follows_weights(self):
        lb = make(("a", 7), ("b", 2), ("c", 1), strategy=SmoothWeightedRoundRobin())
        counts = collections.Counter(picks(lb, 1000))
        self.assertEqual(counts, {"a": 700, "b": 200, "c": 100})

    def test_unhealthy_backend_is_skipped(self):
        lb = make(("a", 5), ("b", 1), ("c", 1), strategy=SmoothWeightedRoundRobin())
        lb.set_health("a", False)
        seq = picks(lb, 100)
        self.assertNotIn("a", seq)
        self.assertEqual(collections.Counter(seq), {"b": 50, "c": 50})


class TestLeastConnections(unittest.TestCase):
    def test_picks_least_loaded(self):
        lb = make(("a", 1), ("b", 1), ("c", 1), strategy=LeastConnections())
        self.assertEqual(picks(lb, 3, release=False), "abc", "同数なら先に並んでいるもの")
        lb.release("b")
        self.assertEqual(lb.acquire().name, "b")
        lb.release("a")
        lb.release("c")
        self.assertEqual(picks(lb, 2, release=False), "ac")

    def test_long_requests_do_not_pile_up(self):
        lb = make(("a", 1), ("b", 1), strategy=LeastConnections())
        slow = lb.acquire()  # a に長い処理が 1 つ残る
        self.assertEqual(slow.name, "a")
        self.assertEqual(picks(lb, 5), "bbbbb", "短い処理は空いている b に流れる")


class TestPowerOfTwoChoices(unittest.TestCase):
    def test_uses_rng_sample_of_two(self):
        backends = [Backend(n) for n in "abcde"]
        backends[0].active_connections = 5
        backends[1].active_connections = 1
        backends[2].active_connections = 3
        strategy = PowerOfTwoChoices(random.Random(7))
        ref_rng = random.Random(7)
        for _ in range(50):
            x, y = ref_rng.sample(backends, 2)
            expected = y if y.active_connections < x.active_connections else x
            self.assertIs(strategy.choose(backends), expected)

    def test_single_candidate(self):
        only = Backend("only")
        self.assertIs(PowerOfTwoChoices(random.Random(1)).choose([only]), only)

    def test_balances_better_than_random(self):
        # 解放せずに 5,000 回振り分けたときの、最も多いサーバーと最も少ないサーバーの差
        def spread(strategy):
            lb = LoadBalancer([Backend(f"s{i}") for i in range(50)], strategy)
            for _ in range(5000):
                lb.acquire()
            counts = [b.active_connections for b in lb.backends]
            return max(counts) - min(counts)

        class RandomChoice:
            def __init__(self, rng):
                self.rng = rng

            def choose(self, candidates):
                return self.rng.choice(candidates)

        p2c = spread(PowerOfTwoChoices(random.Random(8)))
        rnd = spread(RandomChoice(random.Random(8)))
        self.assertLessEqual(p2c, 6, f"2 つから選ぶだけで偏りは小さくなる（差 {p2c}）")
        self.assertGreater(rnd, 3 * p2c, f"ランダムの差 {rnd} と比べて明らかに小さい")


class TestHealthAndDraining(unittest.TestCase):
    def test_no_available_backend(self):
        lb = make(("a", 1), ("b", 1))
        lb.set_health("a", False)
        lb.set_health("b", False)
        with self.assertRaises(NoAvailableBackend):
            lb.acquire()

    def test_draining(self):
        lb = make(("a", 1), ("b", 1), strategy=LeastConnections())
        conns = [lb.acquire() for _ in range(4)]  # a に 2 本、b に 2 本
        lb.drain("a")
        self.assertFalse(lb.is_drained("a"), "処理中の接続が残っている")
        self.assertEqual(picks(lb, 3, release=False), "bbb", "ドレイン中のサーバーには新しい接続を送らない")
        for c in conns:
            if c.name == "a":
                lb.release(c)
        self.assertTrue(lb.is_drained("a"), "接続がなくなったら取り外してよい")
        self.assertFalse(lb.is_drained("b"), "ドレインしていないサーバーは drained ではない")
        lb.undrain("a")
        self.assertEqual(lb.acquire().name, "a")

    def test_release_errors(self):
        lb = make(("a", 1))
        with self.assertRaises(ValueError):
            lb.release("a")
        with self.assertRaises(KeyError):
            lb.release("zzz")

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            LoadBalancer([], RoundRobin())
        with self.assertRaises(ValueError):
            LoadBalancer([Backend("a"), Backend("a")], RoundRobin())
        with self.assertRaises(ValueError):
            LoadBalancer([Backend("a", 0)], RoundRobin())

    def test_health_checker_hysteresis(self):
        lb = make(("a", 1), ("b", 1))
        hc = HealthChecker(lb, rise=2, fall=3)
        for ok, healthy in [(False, True), (False, True), (True, True),   # 連続していないので外さない
                            (False, True), (False, True), (False, False),  # 3 回連続の失敗で外す
                            (True, False), (False, False), (True, False),  # 回復は 2 回連続の成功から
                            (True, True)]:
            hc.record("a", ok)
            self.assertEqual(lb.backend("a").healthy, healthy)
        self.assertTrue(lb.backend("b").healthy)


if __name__ == "__main__":
    unittest.main()
