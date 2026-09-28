"""6.2 演習2（結合アルゴリズム）のテスト

実行: python3 tools/check.py 6.2   （またはこのディレクトリで python3 -m unittest -v test_joins）
"""
import copy
import math
import random
import unittest

from joins import JoinStats, hash_join, nested_loop_join, sort_merge_join

ALGORITHMS = (nested_loop_join, hash_join, sort_merge_join)


def normalize(pairs):
    """結果を比較できる形にする（行の順序を無視）。"""
    return sorted((l["_id"], r["_id"]) for l, r in pairs)


def expected_pairs(left, right, lk, rk):
    return sorted(
        (l["_id"], r["_id"])
        for l in left
        for r in right
        if l[lk] is not None and l[lk] == r[rk]
    )


def make_rows(rng, n, key, key_range, null_rate=0.0, prefix="r"):
    rows = []
    for i in range(n):
        k = None if rng.random() < null_rate else rng.randrange(key_range)
        rows.append({"_id": f"{prefix}{i}", key: k, "payload": rng.random()})
    return rows


class TestCorrectness(unittest.TestCase):
    def test_small_example(self):
        customers = [{"_id": "c1", "id": 1}, {"_id": "c2", "id": 2}, {"_id": "c3", "id": 3}]
        orders = [
            {"_id": "o1", "cid": 2},
            {"_id": "o2", "cid": 2},
            {"_id": "o3", "cid": 3},
            {"_id": "o4", "cid": 9},
        ]
        for algo in ALGORITHMS:
            got = normalize(algo(customers, orders, "id", "cid"))
            self.assertEqual(got, [("c2", "o1"), ("c2", "o2"), ("c3", "o3")], algo.__name__)

    def test_result_orientation_is_left_then_right(self):
        left = [{"_id": "L", "k": 1, "side": "left"}]
        right = [{"_id": f"R{i}", "k": 1, "side": "right"} for i in range(5)]
        for algo in ALGORITHMS:
            for l_row, r_row in algo(left, right, "k", "k"):
                self.assertEqual((l_row["side"], r_row["side"]), ("left", "right"), algo.__name__)
            # 左の方が大きい場合（ハッシュ結合のビルド側が入れ替わる）
            for l_row, r_row in algo(right, left, "k", "k"):
                self.assertEqual((l_row["side"], r_row["side"]), ("right", "left"), algo.__name__)

    def test_many_to_many(self):
        left = [{"_id": f"l{i}", "k": 1} for i in range(3)] + [{"_id": "l9", "k": 2}]
        right = [{"_id": f"r{i}", "k": 1} for i in range(4)] + [{"_id": "r9", "k": 3}]
        for algo in ALGORITHMS:
            self.assertEqual(len(algo(left, right, "k", "k")), 12, f"{algo.__name__}: キー 1 は 3 × 4 = 12 組")

    def test_nulls_never_match(self):
        left = [{"_id": "l1", "k": None}, {"_id": "l2", "k": 1}]
        right = [{"_id": "r1", "k": None}, {"_id": "r2", "k": 1}]
        for algo in ALGORITHMS:
            self.assertEqual(normalize(algo(left, right, "k", "k")), [("l2", "r2")], algo.__name__)

    def test_empty_inputs(self):
        rows = [{"_id": "x", "k": 1}]
        for algo in ALGORITHMS:
            stats = JoinStats()
            self.assertEqual(algo([], rows, "k", "k", stats), [], algo.__name__)
            self.assertEqual(algo(rows, [], "k", "k", stats), [], algo.__name__)
            self.assertEqual(stats.comparisons, 0, algo.__name__)

    def test_string_keys(self):
        left = [{"_id": "a", "code": "JP"}, {"_id": "b", "code": "US"}]
        right = [{"_id": "x", "cc": "US"}, {"_id": "y", "cc": "JP"}, {"_id": "z", "cc": "FR"}]
        for algo in ALGORITHMS:
            self.assertEqual(normalize(algo(left, right, "code", "cc")), [("a", "y"), ("b", "x")], algo.__name__)

    def test_random_against_bruteforce(self):
        rng = random.Random(62)
        for trial in range(40):
            left = make_rows(rng, rng.randrange(0, 60), "a", rng.choice([5, 20, 100]), 0.1, "l")
            right = make_rows(rng, rng.randrange(0, 60), "b", rng.choice([5, 20, 100]), 0.1, "r")
            expected = expected_pairs(left, right, "a", "b")
            for algo in ALGORITHMS:
                self.assertEqual(normalize(algo(left, right, "a", "b")), expected, f"{algo.__name__} trial={trial}")

    def test_inputs_are_not_modified(self):
        rng = random.Random(7)
        left = make_rows(rng, 50, "k", 10, 0.1, "l")
        right = make_rows(rng, 50, "k", 10, 0.1, "r")
        before = (copy.deepcopy(left), copy.deepcopy(right))
        for algo in ALGORITHMS:
            algo(left, right, "k", "k", JoinStats())
            self.assertEqual((left, right), before, f"{algo.__name__} が入力を書き換えました")

    def test_missing_key_raises_key_error(self):
        for algo in ALGORITHMS:
            with self.assertRaises(KeyError, msg=algo.__name__):
                algo([{"_id": "x", "k": 1}], [{"_id": "y", "k": 1}], "nope", "k")


class TestCosts(unittest.TestCase):
    def setUp(self):
        rng = random.Random(2)
        self.left = make_rows(rng, 300, "k", 1000, 0.1, "l")
        self.right = make_rows(rng, 500, "k", 1000, 0.1, "r")
        self.nl = sum(1 for r in self.left if r["k"] is not None)
        self.nr = sum(1 for r in self.right if r["k"] is not None)

    def test_nested_loop_compares_every_pair(self):
        stats = JoinStats()
        nested_loop_join(self.left, self.right, "k", "k", stats)
        self.assertEqual(stats.comparisons, self.nl * self.nr)
        self.assertEqual((stats.hash_inserts, stats.hash_probes), (0, 0))

    def test_hash_join_builds_on_smaller_input(self):
        stats = JoinStats()
        hash_join(self.left, self.right, "k", "k", stats)
        self.assertEqual(stats.hash_inserts, self.nl, "ビルド側は非 NULL 行の少ない left")
        self.assertEqual(stats.hash_probes, self.nr)
        stats = JoinStats()
        hash_join(self.right, self.left, "k", "k", stats)
        self.assertEqual(stats.hash_inserts, self.nl, "left と right を入れ替えても、小さい方でビルドする")
        self.assertEqual(stats.hash_probes, self.nr)

    def test_hash_join_tie_builds_on_right(self):
        left = [{"_id": f"l{i}", "k": i} for i in range(10)]
        right = [{"_id": f"r{i}", "k": i} for i in range(10)] + [{"_id": "rn", "k": None}]
        stats = JoinStats()
        hash_join(left, right, "k", "k", stats)
        self.assertEqual((stats.hash_inserts, stats.hash_probes), (10, 10))

    def test_sort_merge_comparisons_are_n_log_n(self):
        stats = JoinStats()
        sort_merge_join(self.left, self.right, "k", "k", stats)
        n, m = self.nl, self.nr
        sort_bound = n * math.log2(n) + m * math.log2(m)
        self.assertGreater(stats.comparisons, n + m, "並べ替えの比較も数えること")
        self.assertLessEqual(stats.comparisons, sort_bound + 3 * (n + m))
        self.assertLess(stats.comparisons, n * m / 10, "入れ子ループよりずっと少ないはず")

    def test_presorted_input_skips_sorting(self):
        left = [{"_id": f"l{i}", "k": i // 2} for i in range(1000)]    # 0,0,1,1,2,2,...
        right = [{"_id": f"r{i}", "k": i} for i in range(0, 1500, 3)]  # 0,3,6,...
        stats = JoinStats()
        result = sort_merge_join(left, right, "k", "k", stats, presorted=True)
        self.assertEqual(normalize(result), expected_pairs(left, right, "k", "k"))
        self.assertLessEqual(stats.comparisons, 3 * (len(left) + len(right)),
                             "整列済みの入力ならマージの比較だけで済む（並べ替えない）")

    def test_cost_comparison_at_scale(self):
        n = 2000
        left = [{"_id": f"l{i}", "k": i} for i in range(n)]
        right = [{"_id": f"r{i}", "k": (i * 7919) % n} for i in range(n)]  # 同じキーを別の順序で
        s_nl, s_hash, s_sm = JoinStats(), JoinStats(), JoinStats()
        self.assertEqual(len(hash_join(left, right, "k", "k", s_hash)), n)
        self.assertEqual(len(sort_merge_join(left, right, "k", "k", s_sm)), n)
        self.assertEqual(len(nested_loop_join(left[:200], right, "k", "k", s_nl)), 200)
        self.assertEqual(s_nl.comparisons, 200 * n)
        self.assertEqual(s_hash.hash_inserts + s_hash.hash_probes, 2 * n)
        self.assertLess(s_sm.comparisons, 2 * n * math.log2(n) + 3 * 2 * n)


if __name__ == "__main__":
    unittest.main()
