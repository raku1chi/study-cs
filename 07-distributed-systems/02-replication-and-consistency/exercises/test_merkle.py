"""7.2 レプリケーションと一貫性 — Merkle 木のテスト

実行: python3 tools/check.py 7.2   （またはこのディレクトリで python3 -m unittest -v test_merkle）
"""
import hashlib
import json
import random
import unittest

from merkle import MerkleTree, diff_buckets, find_differences, key_bucket, key_token, leaf_digest


def sample_data(n: int, seed: int = 0) -> dict[str, str]:
    rng = random.Random(seed)
    return {f"user:{i}": f"v{rng.randrange(10**6)}" for i in range(n)}


def brute_force_diff(a: dict, b: dict) -> list[str]:
    return sorted(k for k in a.keys() | b.keys() if a.get(k) != b.get(k))


class TestHashing(unittest.TestCase):
    def test_key_token_and_bucket(self):
        expected = int.from_bytes(hashlib.sha256("user:42".encode()).digest()[:8], "big")
        self.assertEqual(key_token("user:42"), expected)
        self.assertEqual(key_bucket("user:42", 4), expected >> 60, "上位 depth ビットがバケツ番号")
        self.assertEqual(key_bucket("user:42", 0), 0)
        for key in ("a", "b", "日本語のキー", ""):
            for depth in (1, 5, 12):
                self.assertTrue(0 <= key_bucket(key, depth) < 2**depth)

    def test_bucket_depth_validation(self):
        with self.assertRaises(ValueError):
            key_bucket("a", -1)
        with self.assertRaises(ValueError):
            key_bucket("a", 21)

    def test_leaf_digest_is_canonical(self):
        items = [("b", "2"), ("a", "1")]
        expected = hashlib.sha256(json.dumps([["a", "1"], ["b", "2"]], separators=(",", ":")).encode()).digest()
        self.assertEqual(leaf_digest(items), expected, "キー順に並べてから直列化する")
        self.assertEqual(leaf_digest([]), hashlib.sha256(b"[]").digest())
        self.assertEqual(
            leaf_digest([("キー", "値")]),
            hashlib.sha256('[["キー","値"]]'.encode("utf-8")).digest(),
            "ensure_ascii=False の UTF-8",
        )


class TestMerkleTree(unittest.TestCase):
    def test_structure_matches_definition(self):
        data = sample_data(200, seed=1)
        tree = MerkleTree(data, depth=4)
        self.assertEqual(tree.depth, 4)
        for index in range(16):
            items = sorted((k, v) for k, v in data.items() if key_bucket(k, 4) == index)
            self.assertEqual(tree.bucket_items(index), items)
            self.assertEqual(tree.node_hash(4, index), leaf_digest(items).hex())
        for level in range(4):
            for index in range(2**level):
                left = bytes.fromhex(tree.node_hash(level + 1, 2 * index))
                right = bytes.fromhex(tree.node_hash(level + 1, 2 * index + 1))
                self.assertEqual(tree.node_hash(level, index), hashlib.sha256(left + right).hexdigest())
        self.assertEqual(tree.root, tree.node_hash(0, 0))

    def test_same_data_same_root_regardless_of_insertion_order(self):
        data = sample_data(500, seed=2)
        items = list(data.items())
        random.Random(3).shuffle(items)
        self.assertEqual(MerkleTree(data, 6).root, MerkleTree(dict(items), 6).root)
        self.assertEqual(MerkleTree({}, 3).root, MerkleTree({}, 3).root)

    def test_any_change_changes_root(self):
        data = sample_data(300, seed=4)
        base = MerkleTree(data, 5).root
        changed = dict(data, **{"user:7": "different"})
        removed = {k: v for k, v in data.items() if k != "user:7"}
        added = dict(data, **{"user:new": "x"})
        for variant in (changed, removed, added):
            self.assertNotEqual(MerkleTree(variant, 5).root, base)

    def test_depth_zero_is_a_single_bucket(self):
        tree = MerkleTree({"a": "1", "b": "2"}, depth=0)
        self.assertEqual(tree.root, leaf_digest([("a", "1"), ("b", "2")]).hex())

    def test_errors(self):
        with self.assertRaises(ValueError):
            MerkleTree({}, depth=21)
        tree = MerkleTree({}, depth=3)
        with self.assertRaises(IndexError):
            tree.node_hash(4, 0)
        with self.assertRaises(IndexError):
            tree.node_hash(2, 4)
        with self.assertRaises(IndexError):
            tree.bucket_items(8)


class TestDiff(unittest.TestCase):
    def test_identical_trees_need_one_comparison(self):
        data = sample_data(1000, seed=5)
        self.assertEqual(diff_buckets(MerkleTree(data, 8), MerkleTree(dict(data), 8)), ([], 1))

    def test_single_difference_needs_only_one_path(self):
        a = sample_data(5000, seed=6)
        b = dict(a)
        b["user:1234"] = "changed"
        buckets, comparisons = diff_buckets(MerkleTree(a, 10), MerkleTree(b, 10))
        self.assertEqual(buckets, [key_bucket("user:1234", 10)])
        self.assertEqual(comparisons, 1 + 2 * 10, "ルート 1 回 + 各段で子を 2 つずつ比較")
        keys, comparisons2 = find_differences(a, b, depth=10)
        self.assertEqual(keys, ["user:1234"])
        self.assertEqual(comparisons2, 21)

    def test_find_differences_matches_brute_force(self):
        rng = random.Random(7)
        for trial in range(20):
            a = sample_data(rng.randrange(0, 400), seed=trial)
            b = dict(a)
            for _ in range(rng.randrange(0, 15)):
                op = rng.random()
                if op < 0.4 and b:
                    b[rng.choice(sorted(b))] = f"new{rng.random()}"
                elif op < 0.7 and b:
                    del b[rng.choice(sorted(b))]
                else:
                    b[f"extra:{rng.randrange(10**6)}"] = "x"
            depth = rng.randrange(0, 9)
            keys, comparisons = find_differences(a, b, depth)
            self.assertEqual(keys, brute_force_diff(a, b), f"trial={trial}")
            self.assertLessEqual(comparisons, 2 ** (depth + 1) - 1, "比較はノード数を超えない")

    def test_different_depths_cannot_be_compared(self):
        with self.assertRaises(ValueError):
            diff_buckets(MerkleTree({}, 3), MerkleTree({}, 4))


if __name__ == "__main__":
    unittest.main()
