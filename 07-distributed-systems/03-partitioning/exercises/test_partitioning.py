"""7.3 パーティショニング — ハッシュ分割とレンジ分割のテスト

実行: python3 tools/check.py 7.3   （またはこのディレクトリで python3 -m unittest -v test_partitioning）
"""
import hashlib
import random
import unittest
from collections import Counter

from partitioning import (
    ConsistentHashRing,
    RangePartitioner,
    mod_n_partition,
    rendezvous_node,
    rendezvous_nodes,
    stable_hash,
)

KEYS = [f"user:{i}" for i in range(10_000)]


def moved_fraction(before: dict, after: dict) -> float:
    return sum(before[k] != after[k] for k in before) / len(before)


def imbalance(assignment: dict) -> float:
    """最も負荷の高いノードのキー数 ÷ 平均。1.0 が完全に均等。"""
    counts = Counter(assignment.values())
    return max(counts.values()) / (len(assignment) / len(counts))


class TestStableHash(unittest.TestCase):
    def test_stable_hash_is_sha256_prefix(self):
        expected = int.from_bytes(hashlib.sha256(b"user:1").digest()[:8], "big")
        self.assertEqual(stable_hash("user:1"), expected)


class TestExercise1ModNAndRendezvous(unittest.TestCase):
    def test_mod_n(self):
        self.assertEqual(mod_n_partition("user:1", 7), stable_hash("user:1") % 7)
        self.assertTrue(all(0 <= mod_n_partition(k, 5) < 5 for k in KEYS[:100]))
        with self.assertRaises(ValueError):
            mod_n_partition("k", 0)

    def test_mod_n_moves_most_keys_when_adding_a_node(self):
        before = {k: mod_n_partition(k, 4) for k in KEYS}
        after = {k: mod_n_partition(k, 5) for k in KEYS}
        self.assertGreater(moved_fraction(before, after), 0.7, "4 台→5 台で約 80% のキーが移動する")

    def test_rendezvous_basics(self):
        nodes = ["n1", "n2", "n3"]
        key = "user:42"
        expected = max((stable_hash(f"{n}:{key}"), n) for n in nodes)[1]
        self.assertEqual(rendezvous_node(key, nodes), expected)
        self.assertEqual(rendezvous_node(key, reversed(nodes)), expected, "ノードの並び順に依存しない")
        with self.assertRaises(LookupError):
            rendezvous_node(key, [])

    def test_rendezvous_minimal_disruption(self):
        nodes = [f"n{i}" for i in range(5)]
        before = {k: rendezvous_node(k, nodes) for k in KEYS}
        after_remove = {k: rendezvous_node(k, nodes[:-1]) for k in KEYS}
        for k in KEYS:
            if before[k] != after_remove[k]:
                self.assertEqual(before[k], "n4", "削除されたノードのキーだけが移動する")
        after_add = {k: rendezvous_node(k, nodes + ["n5"]) for k in KEYS}
        for k in KEYS:
            if before[k] != after_add[k]:
                self.assertEqual(after_add[k], "n5", "移動するキーは新しいノードに行くものだけ")
        self.assertAlmostEqual(moved_fraction(before, after_add), 1 / 6, delta=0.03)
        self.assertLess(imbalance(before), 1.1)

    def test_rendezvous_top_k(self):
        nodes = [f"n{i}" for i in range(6)]
        top = rendezvous_nodes("user:7", nodes, 3)
        self.assertEqual(len(set(top)), 3)
        self.assertEqual(top[0], rendezvous_node("user:7", nodes))
        # 先頭のノードが抜けると、2 番目以降が繰り上がる
        self.assertEqual(rendezvous_nodes("user:7", [n for n in nodes if n != top[0]], 2), top[1:])
        for k in (0, 7):
            with self.assertRaises(ValueError):
                rendezvous_nodes("user:7", nodes, k)


class TestExercise2ConsistentHashRing(unittest.TestCase):
    def test_empty_ring(self):
        ring = ConsistentHashRing()
        self.assertEqual(ring.nodes, [])
        with self.assertRaises(LookupError):
            ring.get_node("k")

    def test_mapping_is_deterministic_and_valid(self):
        ring1 = ConsistentHashRing(["a", "b", "c"], vnodes=50)
        ring2 = ConsistentHashRing(["c", "a", "b"], vnodes=50)
        for k in KEYS[:500]:
            self.assertIn(ring1.get_node(k), {"a", "b", "c"})
            self.assertEqual(ring1.get_node(k), ring2.get_node(k), "追加の順序に依存しない")
        self.assertEqual(ring1.nodes, ["a", "b", "c"])

    def test_successor_rule_with_one_vnode(self):
        ring = ConsistentHashRing(["a", "b", "c"], vnodes=1)
        positions = sorted((stable_hash(f"{n}#0"), n) for n in "abc")
        for k in KEYS[:300]:
            h = stable_hash(k)
            owner = next((n for pos, n in positions if pos >= h), positions[0][1])
            self.assertEqual(ring.get_node(k), owner, "キーの位置以上で最初の仮想ノード（なければ先頭）")

    def test_adding_a_node_moves_about_one_over_n_keys_only_to_it(self):
        ring = ConsistentHashRing([f"n{i}" for i in range(4)], vnodes=200)
        before = {k: ring.get_node(k) for k in KEYS}
        ring.add_node("n4")
        after = {k: ring.get_node(k) for k in KEYS}
        for k in KEYS:
            if before[k] != after[k]:
                self.assertEqual(after[k], "n4", "移動するのは新しいノードへのキーだけ")
        self.assertAlmostEqual(moved_fraction(before, after), 1 / 5, delta=0.05)

    def test_removing_a_node_moves_only_its_keys(self):
        ring = ConsistentHashRing([f"n{i}" for i in range(5)], vnodes=100)
        before = {k: ring.get_node(k) for k in KEYS}
        ring.remove_node("n2")
        after = {k: ring.get_node(k) for k in KEYS}
        for k in KEYS:
            if before[k] != "n2":
                self.assertEqual(before[k], after[k], k)
            else:
                self.assertNotEqual(after[k], "n2")
        self.assertEqual(ring.nodes, ["n0", "n1", "n3", "n4"])

    def test_more_vnodes_means_better_balance(self):
        nodes = [f"n{i}" for i in range(10)]
        rough = ConsistentHashRing(nodes, vnodes=1)
        smooth = ConsistentHashRing(nodes, vnodes=200)
        rough_imb = imbalance({k: rough.get_node(k) for k in KEYS})
        smooth_imb = imbalance({k: smooth.get_node(k) for k in KEYS})
        self.assertLess(smooth_imb, rough_imb)
        self.assertLess(smooth_imb, 1.3, smooth_imb)

    def test_get_nodes_for_replication(self):
        ring = ConsistentHashRing([f"n{i}" for i in range(5)], vnodes=20)
        for k in KEYS[:200]:
            replicas = ring.get_nodes(k, 3)
            self.assertEqual(len(set(replicas)), 3, "物理ノードの重複を除く")
            self.assertEqual(replicas[0], ring.get_node(k))
        self.assertEqual(sorted(ring.get_nodes("x", 5)), ring.nodes)
        for n in (0, 6):
            with self.assertRaises(ValueError):
                ring.get_nodes("x", n)

    def test_errors(self):
        with self.assertRaises(ValueError):
            ConsistentHashRing(vnodes=0)
        ring = ConsistentHashRing(["a"])
        with self.assertRaises(ValueError):
            ring.add_node("a")
        with self.assertRaises(KeyError):
            ring.remove_node("zzz")


class TestExercise3RangePartitioner(unittest.TestCase):
    def test_routing_with_split_points(self):
        rp = RangePartitioner(split_points=["g", "p"])
        self.assertEqual(rp.num_partitions, 3)
        cases = {"apple": 0, "fig": 0, "g": 1, "grape": 1, "orange": 1, "p": 2, "zebra": 2, "": 0}
        for key, expected in cases.items():
            self.assertEqual(rp.partition_for(key), expected, key)

    def test_validation(self):
        for points in (["p", "g"], ["g", "g"]):
            with self.assertRaises(ValueError):
                RangePartitioner(split_points=points)
        with self.assertRaises(ValueError):
            RangePartitioner(max_partition_size=1)

    def test_put_get_and_auto_split(self):
        rng = random.Random(1)
        rp = RangePartitioner(max_partition_size=50)
        data = {f"k{rng.randrange(10**9):09d}": i for i in range(1000)}
        for k, v in data.items():
            rp.put(k, v)
        self.assertGreater(rp.num_partitions, 1)
        sizes = rp.partition_sizes()
        self.assertTrue(all(1 <= s <= 50 for s in sizes), sizes)
        self.assertEqual(sum(sizes), len(data))
        b = rp.boundaries
        self.assertEqual(b, sorted(set(b)), "境界は重複なく昇順")
        for k, v in data.items():
            self.assertEqual(rp.get(k), v)
        self.assertIsNone(rp.get("not-there"))

    def test_split_at_median_and_explicit_point(self):
        rp = RangePartitioner(max_partition_size=100)
        for k in ["a", "b", "c", "d", "e"]:
            rp.put(k, k.upper())
        self.assertEqual(rp.split(0), "c", "中央値（ソート順で len//2 番目）で分割")
        self.assertEqual(rp.boundaries, ["c"])
        self.assertEqual(rp.partition_sizes(), [2, 3])
        self.assertEqual(rp.split(1, at="e"), "e")
        self.assertEqual(rp.boundaries, ["c", "e"])
        self.assertEqual(rp.partition_sizes(), [2, 2, 1])
        for bad in ("b", "c", "e", "z"):
            with self.assertRaises(ValueError, msg=bad):
                rp.split(1, at=bad)  # パーティション 1 は ["c", "e")
        with self.assertRaises(ValueError):
            rp.split(2)  # キーが 1 つしかない
        with self.assertRaises(IndexError):
            rp.split(3)

    def test_sequential_keys_create_a_hot_spot(self):
        # 連番（や時刻）のように単調増加するキーを、固定の境界でレンジ分割する
        rp = RangePartitioner(max_partition_size=10**6, split_points=[f"order:{i:08d}" for i in (500, 1000, 1500)])
        for i in range(2000):
            rp.put(f"order:{i:08d}", i)
        self.assertEqual(rp.partition_sizes(), [500, 500, 500, 500])
        rp.reset_loads()
        for i in range(2000, 2050):
            rp.put(f"order:{i:08d}", i)
        self.assertEqual(rp.loads(), [0, 0, 0, 50], "新しい書き込みはすべて最後のパーティションに集中する")
        self.assertEqual(rp.hottest(), 3)

    def test_hashed_prefix_spreads_writes(self):
        rp = RangePartitioner(max_partition_size=10**6, split_points=[f"{i:03d}" for i in range(100, 1000, 100)])
        for i in range(2000, 2200):
            rp.put(f"{stable_hash(str(i)) % 1000:03d}:order:{i:08d}", i)
        loads = rp.loads()
        self.assertEqual(sum(loads), 200)
        self.assertEqual(sum(1 for load in loads if load > 0), 10, "キーの先頭をハッシュにすると書き込みが分散する")
        self.assertLess(max(loads), 40)

    def test_scan_touches_only_relevant_partitions(self):
        rp = RangePartitioner(max_partition_size=10)
        for i in range(200):
            rp.put(f"{i:04d}", i)
        items = rp.scan("0050", "0060")
        self.assertEqual(items, [(f"{i:04d}", i) for i in range(50, 60)])
        touched = rp.partitions_for_range("0050", "0060")
        self.assertLessEqual(len(touched), 3)
        self.assertEqual(touched, sorted(touched))
        self.assertEqual(rp.partitions_for_range("0050", "0050"), [])
        self.assertEqual(rp.partitions_for_range("", "\U0010ffff"), list(range(rp.num_partitions)))
        with self.assertRaises(ValueError):
            rp.scan("9", "1")

    def test_range_end_on_boundary_is_exclusive(self):
        rp = RangePartitioner(split_points=["m"])
        self.assertEqual(rp.partitions_for_range("a", "m"), [0], "end は含まないので右側は不要")
        self.assertEqual(rp.partitions_for_range("a", "ma"), [0, 1])

    def test_hottest_prefers_lowest_index_on_ties(self):
        rp = RangePartitioner(split_points=["m"])
        self.assertEqual(rp.hottest(), 0)
        rp.get("z")
        self.assertEqual(rp.hottest(), 1)
        self.assertEqual(rp.loads(), [0, 1])


if __name__ == "__main__":
    unittest.main()
