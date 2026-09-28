"""2.5 木・ヒープ・グラフ — テスト（木とヒープ: 演習1〜3）

実行: python3 tools/check.py 2.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from trees import BST, MinHeap, Trie, top_k


class Counted:
    """比較演算の回数を数える値（計算量を「比較回数」で確かめるため）。"""

    comparisons = 0

    def __init__(self, v) -> None:
        self.v = v

    def _cmp(self, other):
        Counted.comparisons += 1
        return self.v, other.v

    def __lt__(self, other):
        a, b = self._cmp(other)
        return a < b

    def __le__(self, other):
        a, b = self._cmp(other)
        return a <= b

    def __gt__(self, other):
        a, b = self._cmp(other)
        return a > b

    def __ge__(self, other):
        a, b = self._cmp(other)
        return a >= b

    def __eq__(self, other):
        return isinstance(other, Counted) and self.v == other.v

    def __hash__(self):
        return hash(self.v)

    def __repr__(self):
        return f"Counted({self.v})"


class TestExercise1BST(unittest.TestCase):
    def test_insert_get_contains(self):
        t = BST()
        for k in (50, 30, 70, 20, 40, 60, 80):
            t.insert(k, str(k))
        self.assertEqual(len(t), 7)
        self.assertEqual(t.get(40), "40")
        self.assertIsNone(t.get(45))
        self.assertEqual(t.get(45, "none"), "none")
        self.assertIn(80, t)
        self.assertNotIn(10, t)

    def test_insert_existing_key_updates_value(self):
        t = BST()
        t.insert("k", 1)
        t.insert("k", 2)
        self.assertEqual(len(t), 1)
        self.assertEqual(t.get("k"), 2)

    def test_inorder_is_sorted(self):
        rng = random.Random(1)
        keys = rng.sample(range(10_000), 500)
        t = BST()
        for k in keys:
            t.insert(k)
        self.assertEqual(t.inorder(), sorted(keys))
        self.assertEqual(BST().inorder(), [])

    def test_delete_leaf_one_child_two_children_root(self):
        t = BST()
        for k in (50, 30, 70, 20, 40, 60, 80, 65):
            t.insert(k)
        t.delete(20)  # 葉
        self.assertEqual(t.inorder(), [30, 40, 50, 60, 65, 70, 80])
        t.delete(60)  # 子が 1 つ（右の子 65）
        self.assertEqual(t.inorder(), [30, 40, 50, 65, 70, 80])
        t.delete(70)  # 子が 2 つ
        self.assertEqual(t.inorder(), [30, 40, 50, 65, 80])
        t.delete(50)  # 根（子が 2 つ）
        self.assertEqual(t.inorder(), [30, 40, 65, 80])
        self.assertEqual(len(t), 4)
        for k in (30, 40, 65, 80):
            self.assertIn(k, t)

    def test_delete_until_empty(self):
        t = BST()
        for k in (2, 1, 3):
            t.insert(k)
        for k in (2, 1, 3):
            t.delete(k)
        self.assertEqual(len(t), 0)
        self.assertEqual(t.height(), 0)
        t.insert(9)
        self.assertEqual(t.inorder(), [9])

    def test_delete_missing_raises_key_error(self):
        t = BST()
        with self.assertRaises(KeyError):
            t.delete(1)
        t.insert(1)
        with self.assertRaises(KeyError):
            t.delete(2)

    def test_random_operations_match_model(self):
        rng = random.Random(2)
        t = BST()
        model: dict = {}
        for step in range(3000):
            k = rng.randrange(200)
            if rng.random() < 0.6:
                t.insert(k, step)
                model[k] = step
            elif k in model:
                t.delete(k)
                del model[k]
            if step % 50 == 0:
                self.assertEqual(t.inorder(), sorted(model), f"step={step}")
        self.assertEqual(len(t), len(model))
        for k, v in model.items():
            self.assertEqual(t.get(k), v)

    def test_height_degenerates_on_sorted_input(self):
        t = BST()
        self.assertEqual(t.height(), 0, "空の木の高さは 0")
        t.insert(1)
        self.assertEqual(t.height(), 1, "根だけなら 1（ノード数で数える）")
        for k in range(2, 301):
            t.insert(k)
        self.assertEqual(t.height(), 300, "昇順に挿入すると連結リストと同じ形（高さ n）になる")

    def test_height_for_random_insertion_order(self):
        # 木の形は挿入順だけで決まるので、同じ順序なら誰の実装でも同じ高さになる
        rng = random.Random(3)
        keys = sorted(range(1000), key=lambda _: rng.random())  # random() の列は Python のバージョンによらず同じ
        t = BST()
        for k in keys:
            t.insert(k)
        self.assertEqual(t.height(), 22, "ランダムな順なら高さは O(log n) 程度（この順序では 1000 個で 22）")

    def test_min_max(self):
        t = BST()
        with self.assertRaises(ValueError):
            t.min()
        with self.assertRaises(ValueError):
            t.max()
        for k in ("m", "c", "x", "a"):
            t.insert(k)
        self.assertEqual((t.min(), t.max()), ("a", "x"))

    def test_range_keys(self):
        rng = random.Random(4)
        keys = rng.sample(range(1000), 300)
        t = BST()
        for k in keys:
            t.insert(k)
        for _ in range(200):
            lo, hi = sorted(rng.sample(range(-10, 1010), 2))
            self.assertEqual(t.range_keys(lo, hi), sorted(k for k in keys if lo <= k < hi), (lo, hi))
        self.assertEqual(t.range_keys(500, 500), [])
        self.assertEqual(t.range_keys(600, 400), [])


class TestExercise2MinHeap(unittest.TestCase):
    def assert_heap_property(self, a: list) -> None:
        for i in range(len(a)):
            for c in (2 * i + 1, 2 * i + 2):
                if c < len(a):
                    self.assertLessEqual(a[i], a[c], f"a[{i}]={a[i]!r} > a[{c}]={a[c]!r}: ヒープ条件違反")

    def test_push_pop_returns_sorted_order(self):
        rng = random.Random(10)
        items = [rng.randrange(100) for _ in range(300)]
        h = MinHeap()
        for x in items:
            h.push(x)
        self.assertEqual(len(h), 300)
        self.assertEqual([h.pop() for _ in range(300)], sorted(items))
        self.assertEqual(len(h), 0)

    def test_peek_and_empty(self):
        h = MinHeap()
        with self.assertRaises(IndexError):
            h.pop()
        with self.assertRaises(IndexError):
            h.peek()
        h.push(5)
        h.push(3)
        self.assertEqual(h.peek(), 3)
        self.assertEqual(len(h), 2, "peek は取り出さない")

    def test_heap_property_is_maintained(self):
        rng = random.Random(11)
        h = MinHeap()
        for _ in range(1000):
            if rng.random() < 0.6 or len(h) == 0:
                h.push(rng.randrange(1000))
            else:
                h.pop()
            self.assert_heap_property(h.to_list())

    def test_heapify_constructor(self):
        rng = random.Random(12)
        items = [rng.randrange(50) for _ in range(200)]
        h = MinHeap(items)
        self.assertEqual(len(h), 200)
        self.assert_heap_property(h.to_list())
        self.assertEqual(sorted(h.to_list()), sorted(items))
        self.assertEqual([h.pop() for _ in range(200)], sorted(items))

    def test_heapify_is_linear_time(self):
        # 降順の入力は「1 個ずつ push」すると毎回根まで上がる最悪ケース（約 n log n 回の比較）。
        # 下から sift down するボトムアップ構築なら、比較は 2n 回以下で済む
        n = 1000
        items = [Counted(v) for v in range(n, 0, -1)]
        Counted.comparisons = 0
        h = MinHeap(items)
        self.assertLessEqual(Counted.comparisons, 2 * n, f"比較 {Counted.comparisons} 回: O(n) のヒープ構築になっていますか")
        self.assertEqual(h.peek().v, 1)

    def test_tuples_as_priority_queue(self):
        h = MinHeap()
        for task in [(3, "backup"), (1, "page on-call"), (2, "send email")]:
            h.push(task)
        self.assertEqual(h.pop(), (1, "page on-call"))
        self.assertEqual(h.pop(), (2, "send email"))


class TestExercise2TopK(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(top_k([5, 1, 9, 3, 7], 2), [9, 7])
        self.assertEqual(top_k([5, 1, 9], 0), [])
        self.assertEqual(top_k([5, 1, 9], 10), [9, 5, 1])
        self.assertEqual(top_k([], 3), [])
        with self.assertRaises(ValueError):
            top_k([1], -1)

    def test_with_key(self):
        words = ["kiwi", "banana", "fig", "cherry", "apple", "date"]
        got = top_k(words, 3, key=len)
        self.assertEqual([len(w) for w in got], [6, 6, 5])
        self.assertEqual(set(got[:2]), {"banana", "cherry"})

    def test_matches_sorted_on_random_data(self):
        rng = random.Random(13)
        for _ in range(50):
            items = [rng.randrange(1000) for _ in range(rng.randrange(0, 200))]
            k = rng.randrange(0, 30)
            self.assertEqual(top_k(items, k), sorted(items, reverse=True)[:k])

    def test_accepts_single_pass_iterator(self):
        gen = (x * 7919 % 10007 for x in range(10_007))  # 0〜10006 の並べ替え
        self.assertEqual(top_k(gen, 3), [10006, 10005, 10004])

    def test_uses_heap_not_full_sort(self):
        # 全体をソートすると約 n log n 回（n=10000 なら十数万回）の比較が必要。
        # サイズ k のヒープなら、ほとんどの要素は根との比較 1 回で捨てられる
        rng = random.Random(14)
        items = [Counted(rng.random()) for _ in range(10_000)]
        Counted.comparisons = 0
        got = top_k(items, 10)
        self.assertLess(Counted.comparisons, 3 * len(items), f"比較 {Counted.comparisons} 回")
        self.assertEqual([c.v for c in got], sorted((c.v for c in items), reverse=True)[:10])


class TestExercise3Trie(unittest.TestCase):
    def make(self, words):
        t = Trie()
        for w in words:
            t.insert(w)
        return t

    def test_insert_contains_len(self):
        t = self.make(["car", "card", "care", "cat", "dog"])
        self.assertEqual(len(t), 5)
        self.assertIn("card", t)
        self.assertNotIn("ca", t, "接頭辞であっても、登録した単語でなければ含まれない")
        self.assertNotIn("cards", t)
        t.insert("car")
        self.assertEqual(len(t), 5, "同じ単語を 2 回入れても数は増えない")

    def test_starts_with(self):
        t = self.make(["car", "card"])
        self.assertTrue(t.starts_with("ca"))
        self.assertTrue(t.starts_with("card"))
        self.assertTrue(t.starts_with(""))
        self.assertFalse(t.starts_with("cb"))

    def test_autocomplete_lexicographic_with_limit(self):
        t = self.make(["care", "cat", "car", "card", "careful", "dog", "cart"])
        self.assertEqual(t.autocomplete("car"), ["car", "card", "care", "careful", "cart"])
        self.assertEqual(t.autocomplete("car", limit=2), ["car", "card"])
        self.assertEqual(t.autocomplete("ca", limit=3), ["car", "card", "care"])
        self.assertEqual(t.autocomplete("x"), [])
        self.assertEqual(t.autocomplete("car", limit=0), [])
        with self.assertRaises(ValueError):
            t.autocomplete("car", limit=-1)

    def test_empty_prefix_and_empty_word(self):
        t = self.make(["b", "a", ""])
        self.assertIn("", t)
        self.assertEqual(t.autocomplete(""), ["", "a", "b"])

    def test_japanese_words(self):
        t = self.make(["とうきょう", "とうきょうと", "とうほく", "おおさか"])
        self.assertEqual(t.autocomplete("とう"), ["とうきょう", "とうきょうと", "とうほく"])

    def test_large_vocabulary(self):
        rng = random.Random(15)
        words = {"".join(rng.choice("abcde") for _ in range(rng.randrange(1, 9))) for _ in range(20_000)}
        t = self.make(words)
        self.assertEqual(len(t), len(words))
        for prefix in ("", "a", "ab", "cde", "eeee", "abcdeab"):
            expected = sorted(w for w in words if w.startswith(prefix))[:7]
            self.assertEqual(t.autocomplete(prefix, limit=7), expected, prefix)


if __name__ == "__main__":
    unittest.main()
