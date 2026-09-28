"""6.2 演習1（B+木）のテスト

実行: python3 tools/check.py 6.2   （またはこのディレクトリで python3 -m unittest -v test_bplustree）
発展課題の delete を実装していない場合、削除のテストはスキップされます。
"""
import math
import random
import unittest

from bplustree import BPlusTree, InternalNode, LeafNode


def build(keys, order=4):
    t = BPlusTree(order)
    for k in keys:
        t.insert(k, f"v{k}")
    return t


def leaves_of(tree):
    node = tree.root
    while isinstance(node, InternalNode):
        node = node.children[0]
    out = []
    while node is not None:
        out.append(node)
        node = node.next
    return out


class TestSearchAndInsert(unittest.TestCase):
    def test_order_must_be_at_least_3(self):
        for bad in (0, 1, 2):
            with self.assertRaises(ValueError):
                BPlusTree(bad)

    def test_empty_tree(self):
        t = BPlusTree(4)
        self.assertEqual(len(t), 0)
        self.assertIsNone(t.search(1))
        self.assertEqual(t.search(1, "missing"), "missing")
        self.assertEqual(t.range_scan(), [])

    def test_small_example_from_docstring(self):
        t = build([5, 1, 9, 3, 7])
        self.assertEqual(t.search(7), "v7")
        self.assertIsNone(t.search(4))
        self.assertEqual(len(t), 5)
        self.assertEqual(t.height(), 2)
        self.assertIsInstance(t.root, InternalNode)
        self.assertEqual(t.root.keys, [5], "葉 [1 3 5 9] が分割され、右の葉の先頭 5 が親にコピーされる")
        self.assertEqual([leaf.keys for leaf in leaves_of(t)], [[1, 3], [5, 7, 9]])

    def test_internal_split_moves_middle_key_up(self):
        t = build(range(1, 11), order=4)  # 1..10 を順に挿入
        # 10 を入れた時点で葉 [7 8 9 10] が分割され、ルートの区切りキーが [3 5 7 9]（子が 5 つ）になって
        # あふれる。中央のキー keys[4 // 2] = 7 が新しいルートへ移動し、[3 5] と [9] に分かれる
        self.assertEqual(t.height(), 3)
        self.assertEqual(t.root.keys, [7], "内部ノードの分割では中央のキーが親へ移動する")
        self.assertEqual([c.keys for c in t.root.children], [[3, 5], [9]])
        self.assertEqual([leaf.keys for leaf in leaves_of(t)], [[1, 2], [3, 4], [5, 6], [7, 8], [9, 10]])

    def test_upsert_overwrites_value(self):
        t = build([1, 2, 3])
        t.insert(2, "new")
        self.assertEqual(t.search(2), "new")
        self.assertEqual(len(t), 3)

    def test_random_inserts_against_dict(self):
        for order in (3, 4, 5, 8):
            rng = random.Random(order)
            t = BPlusTree(order)
            model = {}
            for _ in range(800):
                k = rng.randrange(2000)
                t.insert(k, k * 10)
                model[k] = k * 10
            self.assertEqual(len(t), len(model), f"order={order}")
            for k in range(0, 2000, 7):
                self.assertEqual(t.search(k), model.get(k), f"order={order} key={k}")

    def test_string_keys(self):
        words = ["pear", "apple", "fig", "kiwi", "banana", "cherry", "date", "grape", "lemon"]
        t = BPlusTree(3)
        for w in words:
            t.insert(w, len(w))
        self.assertEqual([k for k, _ in t.range_scan()], sorted(words))
        self.assertEqual(t.search("kiwi"), 4)

    def test_search_reads_one_page_per_level(self):
        t = build(range(1000), order=5)
        t.pages_read = 0
        t.search(777)
        self.assertEqual(t.pages_read, t.height(), "検索で読むページ数は木の高さと等しい")

    def test_height_is_logarithmic(self):
        t = build(range(20_000), order=64)
        # 葉は 32 個以上、内部ノードは 32 個以上の子を持つので、2 万件でも 3 段以内に収まる
        self.assertLessEqual(t.height(), 3)
        t3 = build(range(2000), order=3)
        bound = 1 + math.ceil(math.log(2000, 2))
        self.assertLessEqual(t3.height(), bound)


class TestRangeScan(unittest.TestCase):
    def test_inclusive_bounds(self):
        t = build(range(0, 100, 2), order=4)
        self.assertEqual([k for k, _ in t.range_scan(10, 20)], [10, 12, 14, 16, 18, 20])
        self.assertEqual([k for k, _ in t.range_scan(11, 19)], [12, 14, 16, 18])
        self.assertEqual(t.range_scan(50, 50), [(50, "v50")])

    def test_open_bounds(self):
        t = build(range(10), order=3)
        self.assertEqual([k for k, _ in t.range_scan(None, 2)], [0, 1, 2])
        self.assertEqual([k for k, _ in t.range_scan(7, None)], [7, 8, 9])
        self.assertEqual([k for k, _ in t.range_scan()], list(range(10)))

    def test_empty_ranges(self):
        t = build(range(10), order=3)
        self.assertEqual(t.range_scan(5, 4), [])
        self.assertEqual(t.range_scan(100, 200), [])
        self.assertEqual(t.range_scan(-10, -1), [])

    def test_random_ranges_against_sorted_list(self):
        rng = random.Random(62)
        keys = rng.sample(range(10_000), 1500)
        t = build(keys, order=6)
        ordered = sorted(keys)
        for _ in range(100):
            lo, hi = sorted(rng.sample(range(-100, 10_100), 2))
            expected = [(k, f"v{k}") for k in ordered if lo <= k <= hi]
            self.assertEqual(t.range_scan(lo, hi), expected, f"range_scan({lo}, {hi})")

    def test_range_scan_reads_only_needed_leaves(self):
        t = build(range(100_000), order=50)
        leaves = len(leaves_of(t))
        t.pages_read = 0
        result = t.range_scan(50_000, 50_099)  # 100 件
        self.assertEqual(len(result), 100)
        # 下る分（高さ）＋ 100 件が入る葉の数（1 つの葉に 25 件以上）＋ 端数の 1 枚まで
        self.assertLessEqual(t.pages_read, t.height() + math.ceil(100 / 25) + 1,
                             "範囲検索は葉の next をたどり、必要な葉だけを読むこと")
        self.assertLess(t.pages_read, leaves / 100)


class TestInvariants(unittest.TestCase):
    def test_valid_trees_pass(self):
        for order in (3, 4, 5, 9):
            rng = random.Random(100 + order)
            t = BPlusTree(order)
            t.check_invariants()  # 空の木
            for _ in range(400):
                t.insert(rng.randrange(1000), None)
                t.check_invariants()

    def test_detects_unsorted_keys_in_leaf(self):
        t = build(range(50))
        leaf = leaves_of(t)[3]
        leaf.keys[0], leaf.keys[1] = leaf.keys[1], leaf.keys[0]
        with self.assertRaises(AssertionError):
            t.check_invariants()

    def test_detects_key_outside_separator_range(self):
        t = build(range(50))
        leaves_of(t)[2].keys[-1] = 10_000  # 右の区切りキーより大きい（しかも昇順は保っている）
        with self.assertRaises(AssertionError):
            t.check_invariants()

    def test_detects_broken_leaf_chain(self):
        t = build(range(50))
        leaves_of(t)[4].next = None
        with self.assertRaises(AssertionError):
            t.check_invariants()

    def test_detects_underfull_leaf(self):
        t = build(range(50))  # order=4 なので、ルート以外の葉は 2 個以上のキーを持つ必要がある
        leaf = leaves_of(t)[1]
        removed = len(leaf.keys) - 1
        del leaf.keys[1:]
        del leaf.values[1:]
        t._size -= removed  # 件数の検査ではなく、充填率の検査で見つかるようにする
        with self.assertRaises(AssertionError):
            t.check_invariants()

    def test_detects_uneven_depth(self):
        t = build(range(50))
        # ルートの子の 1 つを、同じキーを持つ 1 段浅い葉に置き換える
        child = t.root.children[0]
        first_leaf = leaves_of(t)[0]
        if isinstance(child, InternalNode):
            flat = LeafNode(keys=list(first_leaf.keys), values=list(first_leaf.values), next=first_leaf.next)
            t.root.children[0] = flat
            with self.assertRaises(AssertionError):
                t.check_invariants()

    def test_detects_wrong_size(self):
        t = build(range(50))
        t.insert(10, "overwrite")  # 上書きなので件数は 50 のまま
        t.check_invariants()
        leaves_of(t)[-1].keys.append(1_000)
        leaves_of(t)[-1].values.append("extra")  # 木の外で行を足す → len と一致しない
        with self.assertRaises(AssertionError):
            t.check_invariants()


class TestDeleteBonus(unittest.TestCase):
    """発展課題: delete。未実装（NotImplementedError）ならスキップする。"""

    def delete_or_skip(self, tree, key):
        try:
            return tree.delete(key)
        except NotImplementedError:
            self.skipTest("発展課題（delete）は未実装")

    def test_delete_basic(self):
        t = build(range(20), order=4)
        self.assertTrue(self.delete_or_skip(t, 7))
        self.assertFalse(t.delete(7), "2 回目の削除は False")
        self.assertFalse(t.delete(100))
        self.assertIsNone(t.search(7))
        self.assertEqual(len(t), 19)
        t.check_invariants()

    def test_delete_everything_shrinks_tree(self):
        t = build(range(200), order=4)
        self.delete_or_skip(t, 0)
        for k in range(1, 200):
            self.assertTrue(t.delete(k), k)
            t.check_invariants()
        self.assertEqual(len(t), 0)
        self.assertEqual(t.height(), 1)
        self.assertEqual(t.range_scan(), [])

    def test_random_insert_delete_against_dict(self):
        for order in (3, 4, 5, 7):
            rng = random.Random(order * 7)
            t = BPlusTree(order)
            model = {}
            for step in range(1500):
                k = rng.randrange(300)
                if rng.random() < 0.55:
                    t.insert(k, step)
                    model[k] = step
                else:
                    self.assertEqual(self.delete_or_skip(t, k), k in model, f"order={order} key={k}")
                    model.pop(k, None)
                t.check_invariants()
            self.assertEqual(t.range_scan(), sorted(model.items()), f"order={order}")


if __name__ == "__main__":
    unittest.main()
