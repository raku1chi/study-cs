"""2.4 基本データ構造 — テスト

実行: python3 tools/check.py 2.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import threading
import unittest
from collections import OrderedDict, deque

from structures import (
    BloomFilter,
    ChainedHashMap,
    LinearProbingHashMap,
    LRUCache,
    RingBuffer,
)


def run_with_timeout(testcase: unittest.TestCase, fn, seconds: float = 5.0) -> None:
    """fn() を別スレッドで実行し、seconds 秒で終わらなければテストを失敗させる。

    オープンアドレス法の探査が無限ループする実装でも、テスト全体が止まらないようにするため。
    """
    errors: list[BaseException] = []

    def target() -> None:
        try:
            fn()
        except BaseException as exc:  # noqa: BLE001 — テストスレッドへ例外を運ぶ
            errors.append(exc)

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(seconds)
    if t.is_alive():
        testcase.fail(f"{seconds} 秒以内に終わりません（探査が無限ループしている可能性があります）")
    if errors:
        raise errors[0]


class CollidingKey:
    """ハッシュ値を自由に指定できるキー。わざと衝突を起こすために使う。"""

    def __init__(self, name: str, h: int = 0) -> None:
        self.name = name
        self.h = h

    def __hash__(self) -> int:
        return self.h

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CollidingKey) and self.name == other.name

    def __repr__(self) -> str:
        return f"CollidingKey({self.name!r}, {self.h})"


class TestExercise1RingBuffer(unittest.TestCase):
    def test_fifo_order(self):
        rb = RingBuffer(3)
        for x in (1, 2, 3):
            rb.push(x)
        self.assertEqual([rb.pop(), rb.pop(), rb.pop()], [1, 2, 3])
        self.assertTrue(rb.is_empty())

    def test_wraps_around(self):
        rb = RingBuffer(3)
        rb.push("a")
        rb.push("b")
        rb.push("c")
        self.assertEqual(rb.pop(), "a")
        rb.push("d")  # 配列の先頭に戻って書き込まれる
        self.assertEqual(list(rb), ["b", "c", "d"], "__iter__ は古い順")
        self.assertEqual(rb.peek(), "b")
        self.assertEqual([rb.pop() for _ in range(3)], ["b", "c", "d"])

    def test_len_empty_full(self):
        rb = RingBuffer(2)
        self.assertEqual(rb.capacity, 2)
        self.assertTrue(rb.is_empty())
        self.assertFalse(rb.is_full())
        rb.push(1)
        rb.push(2)
        self.assertEqual(len(rb), 2)
        self.assertTrue(rb.is_full())

    def test_push_to_full_raises_overflow(self):
        rb = RingBuffer(2)
        rb.push(1)
        rb.push(2)
        with self.assertRaises(OverflowError):
            rb.push(3)
        self.assertEqual(list(rb), [1, 2], "失敗した push で中身が変わってはいけない")

    def test_overwrite_mode_keeps_latest(self):
        rb = RingBuffer(3, overwrite=True)
        for x in range(1, 6):
            rb.push(x)
        self.assertEqual(list(rb), [3, 4, 5])
        self.assertEqual(len(rb), 3)
        self.assertEqual(rb.pop(), 3)
        rb.push(6)
        self.assertEqual(list(rb), [4, 5, 6])

    def test_empty_errors(self):
        rb = RingBuffer(1)
        with self.assertRaises(IndexError):
            rb.pop()
        with self.assertRaises(IndexError):
            rb.peek()

    def test_invalid_capacity(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                RingBuffer(bad)

    def test_matches_deque_model(self):
        rng = random.Random(24)
        for overwrite in (False, True):
            rb = RingBuffer(5, overwrite=overwrite)
            model: deque = deque(maxlen=5)
            for step in range(3000):
                if rng.random() < 0.55:
                    x = rng.randrange(1000)
                    if len(model) == 5 and not overwrite:
                        with self.assertRaises(OverflowError):
                            rb.push(x)
                        continue
                    rb.push(x)
                    model.append(x)
                elif model:
                    self.assertEqual(rb.pop(), model.popleft(), f"step={step}")
                self.assertEqual(list(rb), list(model), f"step={step}")
                self.assertEqual(len(rb), len(model))


class HashMapContract:
    """ChainedHashMap と LinearProbingHashMap に共通のテスト。"""

    cls = None
    kwargs: dict = {}

    def make(self, **kw):
        return self.cls(**{**self.kwargs, **kw})

    def test_set_get_update(self):
        m = self.make()
        m["apple"] = 100
        m["banana"] = 200
        self.assertEqual(m["apple"], 100)
        m["apple"] = 150
        self.assertEqual(m["apple"], 150)
        self.assertEqual(len(m), 2, "既存キーの更新で要素数が増えてはいけない")
        self.assertIn("banana", m)
        self.assertNotIn("cherry", m)

    def test_missing_key(self):
        m = self.make()
        with self.assertRaises(KeyError):
            m["nothing"]
        with self.assertRaises(KeyError):
            del m["nothing"]
        self.assertIsNone(m.get("nothing"))
        self.assertEqual(m.get("nothing", -1), -1)

    def test_delete_and_reinsert(self):
        m = self.make()
        m["a"] = 1
        del m["a"]
        self.assertNotIn("a", m)
        self.assertEqual(len(m), 0)
        m["a"] = 2
        self.assertEqual(m["a"], 2)
        self.assertEqual(len(m), 1)

    def test_various_key_types(self):
        m = self.make()
        keys = [0, -1, 2**70, "", "あ", (1, 2), None, 3.5, b"bytes", frozenset({1})]
        for i, k in enumerate(keys):
            m[k] = i
        for i, k in enumerate(keys):
            self.assertEqual(m[k], i, repr(k))
        self.assertEqual(len(m), len(keys))

    def test_colliding_keys(self):
        m = self.make()
        keys = [CollidingKey(f"k{i}", h=7) for i in range(40)]  # 全部同じハッシュ値
        for i, k in enumerate(keys):
            m[k] = i
        for i, k in enumerate(keys):
            self.assertEqual(m[CollidingKey(f"k{i}", h=7)], i)
        for k in keys[::2]:
            del m[k]
        for i, k in enumerate(keys):
            if i % 2:
                self.assertEqual(m[k], i)
            else:
                self.assertNotIn(k, m)
        self.assertEqual(len(m), 20)

    def test_iteration_and_items(self):
        m = self.make()
        expected = {f"key{i}": i * i for i in range(100)}
        for k, v in expected.items():
            m[k] = v
        del m["key5"]
        del expected["key5"]
        keys = list(m)
        self.assertEqual(len(keys), len(set(keys)), "同じキーが 2 回列挙されてはいけない")
        self.assertEqual(set(keys), set(expected))
        self.assertEqual(dict(m.items()), expected)

    def test_grows_and_keeps_load_factor(self):
        m = self.make(initial_capacity=8)
        caps = {m.capacity}
        for i in range(1000):
            m[i] = str(i)
            caps.add(m.capacity)
        self.assertGreater(m.capacity, 8, "要素が増えたら容量を増やすこと")
        self.assertLessEqual(len(m) / m.capacity, self.kwargs.get("max_load_factor", self.default_max_load))
        self.assertAlmostEqual(m.load_factor, len(m) / m.capacity)
        for c in caps:
            self.assertEqual(c % 8, 0, "容量は initial_capacity の 2 のべき乗倍")
            self.assertEqual((c // 8) & (c // 8 - 1), 0, "容量は initial_capacity の 2 のべき乗倍")
        for i in range(1000):
            self.assertEqual(m[i], str(i))

    def test_matches_dict_model(self):
        def body():
            rng = random.Random(2024)
            m = self.make(initial_capacity=4)
            model: dict = {}
            for step in range(6000):
                k = rng.randrange(300)
                op = rng.random()
                if op < 0.5:
                    m[k] = step
                    model[k] = step
                elif op < 0.8:
                    if k in model:
                        del m[k]
                        del model[k]
                    else:
                        with self.assertRaises(KeyError):
                            del m[k]
                else:
                    self.assertEqual(m.get(k), model.get(k), f"step={step} key={k}")
                self.assertEqual(len(m), len(model), f"step={step}")
            self.assertEqual(dict(m.items()), model)

        run_with_timeout(self, body)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            self.make(initial_capacity=0)
        with self.assertRaises(ValueError):
            self.make(max_load_factor=0)


class TestExercise2ChainedHashMap(HashMapContract, unittest.TestCase):
    cls = ChainedHashMap
    kwargs = {"max_load_factor": 0.75}
    default_max_load = 0.75

    def test_resize_happens_exactly_when_load_exceeds_limit(self):
        m = ChainedHashMap(initial_capacity=8, max_load_factor=0.75)
        for i in range(6):
            m[i] = i
        self.assertEqual(m.capacity, 8, "6/8 = 0.75 は上限ちょうどなので、まだ拡張しない")
        m[6] = 6
        self.assertEqual(m.capacity, 16, "7/8 > 0.75 になったら 2 倍に拡張する")

    def test_load_factor_above_one_is_allowed(self):
        # 連鎖法では 1 つのバケットに複数の要素が入れるので、負荷率 1 超えも設定できる
        m = ChainedHashMap(initial_capacity=4, max_load_factor=2.0)
        for i in range(8):
            m[i] = i
        self.assertEqual(m.capacity, 4)
        m[8] = 8
        self.assertEqual(m.capacity, 8)


class TestExercise3LinearProbingHashMap(HashMapContract, unittest.TestCase):
    cls = LinearProbingHashMap
    kwargs = {"max_load_factor": 0.5}
    default_max_load = 0.5

    def test_max_load_factor_must_be_below_one(self):
        for bad in (1.0, 1.5, -0.1):
            with self.assertRaises(ValueError):
                LinearProbingHashMap(max_load_factor=bad)

    def test_delete_keeps_probe_chain_with_tombstone(self):
        def body():
            m = LinearProbingHashMap(initial_capacity=16, max_load_factor=0.5)
            a, b, c = CollidingKey("A", 3), CollidingKey("B", 3), CollidingKey("C", 3)
            m[a], m[b], m[c] = 1, 2, 3  # 同じ位置から始まるので、スロット 3, 4, 5 に並ぶ
            del m[b]
            self.assertEqual(m.tombstones, 1, "削除した位置には墓標を置く")
            self.assertEqual(m[c], 3, "B の位置を空きにすると、その先の C が見つからなくなる")
            self.assertNotIn(b, m)

        run_with_timeout(self, body)

    def test_update_after_delete_does_not_duplicate(self):
        def body():
            m = LinearProbingHashMap(initial_capacity=16, max_load_factor=0.5)
            a, b, c = CollidingKey("A", 3), CollidingKey("B", 3), CollidingKey("C", 3)
            m[a], m[b], m[c] = 1, 2, 3
            del m[b]
            m[CollidingKey("C", 3)] = 30  # 墓標に新しく入れてはいけない（C はこの先にある）
            self.assertEqual(len(m), 2)
            del m[c]
            self.assertNotIn(c, m, "C が 2 か所に入っていると、削除しても残ってしまう")
            self.assertEqual(sorted(k.name for k in m), ["A"])

        run_with_timeout(self, body)

    def test_tombstone_is_reused_for_new_key(self):
        def body():
            m = LinearProbingHashMap(initial_capacity=16, max_load_factor=0.5)
            keys = [CollidingKey(n, 3) for n in "ABC"]
            for i, k in enumerate(keys):
                m[k] = i
            del m[keys[1]]
            self.assertEqual(m.tombstones, 1)
            m[CollidingKey("D", 3)] = 99
            self.assertEqual(m.tombstones, 0, "探査の途中で見つけた墓標を再利用する")
            self.assertEqual(m[CollidingKey("D", 3)], 99)
            self.assertEqual(m[keys[2]], 2)

        run_with_timeout(self, body)

    def test_lookup_terminates_after_many_deletes(self):
        def body():
            m = LinearProbingHashMap(initial_capacity=8, max_load_factor=0.5)
            for i in range(3):
                m[i] = i
            for i in range(3):
                del m[i]
            self.assertNotIn(12345, m)
            self.assertEqual(len(m), 0)

        run_with_timeout(self, body)

    def test_churn_keeps_table_small_and_tombstones_bounded(self):
        def body():
            m = LinearProbingHashMap(initial_capacity=8, max_load_factor=0.5)
            live: list[int] = []
            rng = random.Random(7)
            for i in range(20000):
                m[i] = i
                live.append(i)
                if len(live) > 6:
                    victim = live.pop(rng.randrange(len(live)))
                    del m[victim]
                self.assertLessEqual(
                    len(m) + m.tombstones, m.capacity * 0.5,
                    f"要素数 + 墓標数 が容量 × 負荷率の上限を超えています（i={i}）",
                )
            self.assertLessEqual(m.capacity, 64, "生きている要素は 7 個以下なので、容量が増え続けてはいけない")
            self.assertEqual(sorted(m), sorted(live))

        run_with_timeout(self, body, seconds=10)


class CountingKey:
    """__eq__ が呼ばれた回数を数えるキー（計算量を「比較回数」で確かめるため）。"""

    eq_calls = 0

    def __init__(self, v: int) -> None:
        self.v = v

    def __hash__(self) -> int:
        return hash(self.v)

    def __eq__(self, other: object) -> bool:
        CountingKey.eq_calls += 1
        return isinstance(other, CountingKey) and self.v == other.v

    def __repr__(self) -> str:
        return f"K({self.v})"


class TestExercise4LRUCache(unittest.TestCase):
    def test_basic_eviction(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("c", 3)  # 容量 2 を超えたので、最も長く使われていない a を追い出す
        self.assertNotIn("a", c)
        self.assertEqual(c.get("b"), 2)
        self.assertEqual(c.get("c"), 3)
        self.assertEqual(len(c), 2)

    def test_get_refreshes_recency(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.get("a"), 1)  # a を使ったので、次に追い出されるのは b
        c.put("c", 3)
        self.assertIn("a", c)
        self.assertNotIn("b", c)

    def test_put_existing_updates_and_refreshes(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        c.put("a", 10)
        self.assertEqual(len(c), 2)
        c.put("c", 3)
        self.assertEqual(c.get("a"), 10)
        self.assertNotIn("b", c)

    def test_keys_order_mru_first(self):
        c = LRUCache(3)
        for k in "abc":
            c.put(k, k.upper())
        c.get("a")
        self.assertEqual(c.keys(), ["a", "c", "b"])

    def test_contains_does_not_change_order_or_stats(self):
        c = LRUCache(2)
        c.put("a", 1)
        c.put("b", 2)
        self.assertIn("a", c)
        c.put("c", 3)
        self.assertNotIn("a", c, "in での確認は「使った」ことにしない")
        self.assertEqual((c.hits, c.misses), (0, 0))

    def test_hits_misses_and_default(self):
        c = LRUCache(2)
        c.put("a", 1)
        self.assertEqual(c.get("a"), 1)
        self.assertIsNone(c.get("x"))
        self.assertEqual(c.get("x", "none"), "none")
        self.assertEqual((c.hits, c.misses), (1, 2))

    def test_on_evict_callback(self):
        evicted = []
        c = LRUCache(2, on_evict=lambda k, v: evicted.append((k, v)))
        for i in range(5):
            c.put(i, i * 10)
        self.assertEqual(evicted, [(0, 0), (1, 10), (2, 20)])
        self.assertEqual(c.capacity, 2)

    def test_capacity_one(self):
        c = LRUCache(1)
        c.put("a", 1)
        c.put("b", 2)
        self.assertEqual(c.keys(), ["b"])
        with self.assertRaises(ValueError):
            LRUCache(0)

    def test_matches_ordered_dict_model(self):
        rng = random.Random(99)
        c = LRUCache(8)
        model: OrderedDict = OrderedDict()
        for step in range(5000):
            k = rng.randrange(20)
            if rng.random() < 0.5:
                c.put(k, step)
                model[k] = step
                model.move_to_end(k)
                if len(model) > 8:
                    model.popitem(last=False)
            else:
                expected = model.get(k)
                if k in model:
                    model.move_to_end(k)
                self.assertEqual(c.get(k), expected, f"step={step}")
            self.assertEqual(c.keys(), list(reversed(model)), f"step={step}")

    def test_operations_are_constant_time(self):
        # 連結リストを先頭から探すような O(n) の実装だと、キーの比較回数が操作ごとに数百回になる
        rng = random.Random(5)
        c = LRUCache(1000)
        CountingKey.eq_calls = 0
        ops = 20000
        for _ in range(ops):
            k = CountingKey(rng.randrange(3000))
            if rng.random() < 0.5:
                c.put(k, k.v)
            else:
                c.get(k)
        self.assertLess(
            CountingKey.eq_calls, 3 * ops,
            f"キーの比較が {CountingKey.eq_calls} 回。get/put がキャッシュ全体を走査していませんか",
        )


class TestExercise5BloomFilter(unittest.TestCase):
    def test_positions_follow_the_spec(self):
        bf = BloomFilter(1000, 3)
        self.assertEqual(bf.positions("hello"), [342, 45, 748])
        self.assertEqual(bf.positions(b"hello"), [342, 45, 748], "str は UTF-8 のバイト列として扱う")
        for p in BloomFilter(97, 10).positions("あいう"):
            self.assertTrue(0 <= p < 97)
        self.assertEqual(len(BloomFilter(97, 10).positions("x")), 10)

    def test_positions_are_stable_across_processes(self):
        # 組み込みの hash() は起動ごとに変わるが、hashlib を使えば毎回同じになる
        self.assertEqual(BloomFilter(1 << 20, 4).positions("user:42"), [359778, 835103, 261852, 737177])

    def test_no_false_negatives(self):
        bf = BloomFilter.for_capacity(2000, 0.01)
        items = [f"user-{i}" for i in range(2000)]
        for x in items:
            bf.add(x)
        for x in items:
            self.assertIn(x, bf, "追加した要素は必ず「含まれる」と答えること（偽陰性なし）")

    def test_empty_filter_contains_nothing(self):
        bf = BloomFilter(64, 3)
        self.assertNotIn("anything", bf)
        self.assertEqual(bf.expected_fp_rate(), 0.0)

    def test_for_capacity_parameters(self):
        bf = BloomFilter.for_capacity(1000, 0.01)
        self.assertEqual((bf.num_bits, bf.num_hashes), (9586, 7))
        bf = BloomFilter.for_capacity(1_000_000, 0.001)
        self.assertEqual((bf.num_bits, bf.num_hashes), (14377588, 10))

    def test_expected_fp_rate_formula(self):
        bf = BloomFilter(10_000, 7)
        expected = (1 - math.exp(-7 * 1000 / 10_000)) ** 7
        self.assertAlmostEqual(bf.expected_fp_rate(1000), expected, places=12)
        for i in range(10):
            bf.add(str(i))
        self.assertAlmostEqual(bf.expected_fp_rate(), (1 - math.exp(-7 * 10 / 10_000)) ** 7, places=12)

    def test_empirical_fp_rate_close_to_theory(self):
        bf = BloomFilter.for_capacity(1000, 0.01)
        for i in range(1000):
            bf.add(f"member-{i}")
        theory = bf.expected_fp_rate()
        self.assertAlmostEqual(theory, 0.01, delta=0.002)
        trials = 20000
        fps = sum(f"other-{i}" in bf for i in range(trials))
        rate = fps / trials
        self.assertTrue(
            0.5 * theory <= rate <= 1.5 * theory,
            f"偽陽性率 {rate:.4f} が理論値 {theory:.4f} から離れすぎています",
        )

    def test_overfilled_filter_degrades(self):
        bf = BloomFilter(64, 3)
        for i in range(1000):
            bf.add(i.to_bytes(4, "big"))
        self.assertGreater(bf.expected_fp_rate(), 0.99)
        self.assertIn("never-added", bf, "ビットがほぼ全部 1 なら、何を聞いても「含まれる」になる")

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            BloomFilter(0, 3)
        with self.assertRaises(ValueError):
            BloomFilter(10, 0)
        for n, p in [(0, 0.01), (100, 0.0), (100, 1.0), (100, -0.5)]:
            with self.assertRaises(ValueError, msg=f"for_capacity({n}, {p})"):
                BloomFilter.for_capacity(n, p)
        with self.assertRaises(TypeError):
            BloomFilter(10, 2).add(123)


if __name__ == "__main__":
    unittest.main()
