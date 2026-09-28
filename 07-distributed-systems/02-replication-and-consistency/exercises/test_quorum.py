"""7.2 レプリケーションと一貫性 — クォーラム読み書きのテスト

実行: python3 tools/check.py 7.2   （またはこのディレクトリで python3 -m unittest -v test_quorum）
"""
import random
import unittest

from quorum import QuorumCluster, QuorumError, Replica, Versioned


def holders(cluster: QuorumCluster, key: str) -> list[int]:
    return [i for i, rep in enumerate(cluster.replicas) if key in rep.store]


class TestReplica(unittest.TestCase):
    def test_keeps_only_newer_versions(self):
        rep = Replica("r0")
        self.assertTrue(rep.write("k", Versioned("a", 2)))
        self.assertFalse(rep.write("k", Versioned("old", 1)), "遅れて届いた古い書き込みで巻き戻らない")
        self.assertFalse(rep.write("k", Versioned("same", 2)))
        self.assertEqual(rep.read("k"), Versioned("a", 2))
        self.assertTrue(rep.write("k", Versioned("b", 3)))
        self.assertEqual(rep.read("k").value, "b")
        self.assertIsNone(rep.read("missing"))
        self.assertTrue(rep.up)


class TestQuorumCluster(unittest.TestCase):
    def test_validation(self):
        for n, w, r in [(0, 1, 1), (3, 0, 2), (3, 4, 1), (3, 2, 0), (3, 2, 4)]:
            with self.assertRaises(ValueError, msg=(n, w, r)):
                QuorumCluster(n, w, r)

    def test_is_strict_quorum(self):
        self.assertTrue(QuorumCluster(3, 2, 2).is_strict_quorum)
        self.assertTrue(QuorumCluster(3, 3, 1).is_strict_quorum)
        self.assertFalse(QuorumCluster(3, 1, 1).is_strict_quorum)
        self.assertFalse(QuorumCluster(4, 2, 2).is_strict_quorum)

    def test_put_writes_exactly_w_replicas_with_increasing_versions(self):
        c = QuorumCluster(5, 3, 3, seed=1)
        self.assertEqual(c.put("a", "x"), 1)
        self.assertEqual(c.put("b", "y"), 2)
        self.assertEqual(c.put("a", "z"), 3)
        self.assertEqual(len(holders(c, "b")), 3)
        self.assertIsNone(c.get("never-written"))

    def test_down_replicas_receive_nothing(self):
        c = QuorumCluster(3, 2, 2, seed=2)
        c.fail(2)
        for i in range(20):
            c.put(f"k{i}", i)
        self.assertEqual(c.replicas[2].store, {})
        self.assertFalse(c.replicas[2].up)

    def test_not_enough_replicas_raises(self):
        c = QuorumCluster(3, 2, 2, seed=3)
        c.put("k", 1)
        c.fail(0)
        c.fail(1)
        with self.assertRaises(QuorumError):
            c.put("k", 2)
        with self.assertRaises(QuorumError):
            c.get("k")
        c.recover(1)
        c.put("k", 3)
        self.assertEqual(c.get("k").value, 3)

    def check_always_latest(self, n: int, w: int, r: int, max_down: int, seed: int) -> None:
        c = QuorumCluster(n, w, r, seed=seed)
        rng = random.Random(seed)
        latest: dict[str, int] = {}
        for step in range(600):
            action = rng.random()
            down = [i for i, rep in enumerate(c.replicas) if not rep.up]
            if action < 0.1 and len(down) < max_down:
                c.fail(rng.choice([i for i in range(n) if i not in down]))
            elif action < 0.2 and down:
                c.recover(rng.choice(down))
            elif action < 0.6:
                key = f"k{rng.randrange(10)}"
                latest[key] = c.put(key, step)
            elif latest:
                key = rng.choice(sorted(latest))
                got = c.get(key)
                self.assertIsNotNone(got, key)
                self.assertEqual(got.version, latest[key], f"W+R>N なら最新が読める: step={step}")

    def test_w_plus_r_greater_than_n_returns_latest_n3(self):
        for seed in range(5):
            self.check_always_latest(3, 2, 2, max_down=1, seed=seed)

    def test_w_plus_r_greater_than_n_returns_latest_n5(self):
        for seed in range(5):
            self.check_always_latest(5, 3, 3, max_down=2, seed=100 + seed)

    def count_stale(self, n: int, w: int, r: int, seed: int) -> tuple[int, int]:
        c = QuorumCluster(n, w, r, seed=seed)
        stale = fresh = 0
        for i in range(300):
            key = f"k{i}"
            c.put(key, "old")
            version = c.put(key, "new")
            got = c.get(key)
            if got is not None and got.version == version:
                fresh += 1
            else:
                stale += 1
        return stale, fresh

    def test_w1_r1_can_read_stale_data(self):
        stale, fresh = self.count_stale(3, 1, 1, seed=4)
        self.assertGreater(stale, 0, "W+R<=N では、書き込んでいないレプリカだけを読むことがある")
        self.assertGreater(fresh, 0)

    def test_w_plus_r_equal_n_is_not_enough(self):
        stale, fresh = self.count_stale(4, 2, 2, seed=5)
        self.assertGreater(stale, 0, "W+R=N でも重ならない組み合わせがある")
        self.assertGreater(fresh, stale)

    def test_recovered_replica_with_old_data_does_not_break_strict_quorum(self):
        c = QuorumCluster(3, 2, 2, seed=6)
        c.put("k", "v1")
        c.fail(0)
        v2 = c.put("k", "v2")
        self.assertEqual(c.replicas[1].read("k").version, v2, "停止中は残りの 2 台に書かれる")
        self.assertEqual(c.replicas[2].read("k").version, v2)
        c.recover(0)  # 0 番は v1 のまま（または何も持たずに）戻ってくる
        for _ in range(50):
            self.assertEqual(c.get("k").value, "v2")

    def test_read_repair_fixes_stale_replicas(self):
        c = QuorumCluster(3, 1, 3, seed=7)
        c.put("k", "v")
        self.assertEqual(len(holders(c, "k")), 1)
        self.assertEqual(c.get("k").value, "v")
        self.assertEqual(c.read_repairs, 2)
        for rep in c.replicas:
            self.assertEqual(rep.read("k"), Versioned("v", 1))
        c.get("k")
        self.assertEqual(c.read_repairs, 2, "すでに最新なら修復しない")

    def test_anti_entropy_converges_all_up_replicas(self):
        c = QuorumCluster(3, 1, 1, seed=8)
        expected = {}
        for i in range(50):
            key = f"k{i % 20}"
            expected[key] = c.put(key, i)
        self.assertGreater(c.anti_entropy(), 0)
        for rep in c.replicas:
            self.assertEqual({k: v.version for k, v in rep.store.items()}, expected)
        self.assertEqual(c.anti_entropy(), 0, "収束した後は何も直さない")

        c.fail(2)
        expected["k0"] = c.put("k0", "while-down")
        self.assertEqual(c.anti_entropy(), 1, "稼働中の 2 台のうち、持っていない 1 台だけを直す")
        self.assertNotEqual(c.replicas[2].read("k0").version, expected["k0"], "停止中のレプリカは直せない")
        c.recover(2)
        self.assertEqual(c.anti_entropy(), 1)
        for rep in c.replicas:
            self.assertEqual({k: v.version for k, v in rep.store.items()}, expected)


if __name__ == "__main__":
    unittest.main()
