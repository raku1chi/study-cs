"""2.3 計算量とアルゴリズム解析 — テスト

実行: python3 tools/check.py 2.3   （またはこのディレクトリで python3 -m unittest -v）

計算量のテストは、実行時間ではなく「基本操作の回数」を数えて行います。
"""
import bisect
import math
import random
import unittest

from complexity_lab import (
    ORDER_MODELS,
    DynamicArray,
    count_pairs_with_sum,
    dedupe_preserving_order,
    estimate_order,
    first_true,
    fit_loglog_slope,
    has_duplicates,
    karatsuba_poly,
    lower_bound,
    master_theorem,
    measure_times,
    naive_dc_poly,
    two_sum,
    upper_bound,
)


# ---------------------------------------------------------------------------
# 操作を数えるための道具
# ---------------------------------------------------------------------------

class OpCounter:
    def __init__(self):
        self.count = 0


class Item:
    """==・<・hash() が呼ばれた回数を数える要素。"""

    __slots__ = ("value", "counter")

    def __init__(self, value, counter):
        self.value = value
        self.counter = counter

    def __eq__(self, other):
        self.counter.count += 1
        return isinstance(other, Item) and self.value == other.value

    def __lt__(self, other):
        self.counter.count += 1
        return self.value < other.value

    def __hash__(self):
        self.counter.count += 1
        return hash(self.value)

    def __repr__(self):
        return f"Item({self.value!r})"


class CountingInt(int):
    """足し算・引き算・比較・hash() の回数を数える int。

    `target - x` のように左が普通の int でも、右がこのクラス（int のサブクラス）なら
    Python は先にこのクラスの __rsub__ を呼ぶので、回数を数えられる。
    """

    def __new__(cls, value, counter):
        obj = super().__new__(cls, value)
        obj.counter = counter
        return obj

    def _tick(self):
        self.counter.count += 1

    def __add__(self, other):
        self._tick()
        return int.__add__(self, other)

    def __radd__(self, other):
        self._tick()
        return int.__radd__(self, other)

    def __sub__(self, other):
        self._tick()
        return int.__sub__(self, other)

    def __rsub__(self, other):
        self._tick()
        return int.__rsub__(self, other)

    def __eq__(self, other):
        self._tick()
        return int.__eq__(self, other)

    def __ne__(self, other):
        self._tick()
        return int.__ne__(self, other)

    def __lt__(self, other):
        self._tick()
        return int.__lt__(self, other)

    def __gt__(self, other):
        self._tick()
        return int.__gt__(self, other)

    def __le__(self, other):
        self._tick()
        return int.__le__(self, other)

    def __ge__(self, other):
        self._tick()
        return int.__ge__(self, other)

    def __hash__(self):
        self._tick()
        return int.__hash__(self)


class CountingList(list):
    """a[i] による要素アクセスの回数を数える list。"""

    def __init__(self, *args):
        super().__init__(*args)
        self.reads = 0

    def __getitem__(self, index):
        self.reads += 1
        return super().__getitem__(index)


class OnlyLess:
    """「<」だけを定義した値（==、<= などは使えない）。bisect と同じく「<」だけで探索できるか確かめる。"""

    __slots__ = ("v",)

    def __init__(self, v):
        self.v = v

    def __lt__(self, other):
        return self.v < other.v

    __eq__ = None  # type: ignore[assignment]
    __hash__ = None  # type: ignore[assignment]

    def __le__(self, other):
        raise TypeError("<= は使わないでください（「<」だけで書けます）")

    def __ge__(self, other):
        raise TypeError(">= は使わないでください（「<」だけで書けます）")


def limited(pred, lo, hi):
    """pred の呼び出し回数が二分探索の上限 (hi - lo).bit_length() を超えたら、その場でテストを失敗させる。

    線形探索のような実装だと巨大な範囲で終わらなくなるので、早めに打ち切って理由を伝える。
    """
    limit = (hi - lo).bit_length()
    calls = 0

    def wrapper(i):
        nonlocal calls
        calls += 1
        if calls > limit:
            raise AssertionError(
                f"pred の呼び出しが上限 {limit} 回を超えました（範囲 [{lo}, {hi})）。二分探索になっていますか"
            )
        if not lo <= i < hi:
            raise AssertionError(f"範囲外の {i} で pred を呼んだ（範囲 [{lo}, {hi})）")
        return pred(i)

    return wrapper


# 演習1 の遅い参照実装（答え合わせ用）

def slow_two_sum(nums, target):
    for j in range(len(nums)):
        for i in range(j):
            if nums[i] + nums[j] == target:
                return (i, j)
    return None


def slow_count_pairs(nums, k):
    return sum(1 for i in range(len(nums)) for j in range(i + 1, len(nums)) if nums[i] + nums[j] == k)


N_OPS = 2000          # 操作回数を数えるテストの入力サイズ
LINEAR_LIMIT = 30     # 1 要素あたりに許す操作回数（O(n log n) の実装も通るが、O(n^2) は通らない）


# ---------------------------------------------------------------------------
# 演習1
# ---------------------------------------------------------------------------

class TestExercise1AccidentallyQuadratic(unittest.TestCase):
    def test_has_duplicates(self):
        self.assertTrue(has_duplicates([3, 1, 4, 1, 5]))
        self.assertFalse(has_duplicates([3, 1, 4, 5]))
        self.assertFalse(has_duplicates([]))
        self.assertFalse(has_duplicates(["x"]))
        self.assertTrue(has_duplicates(["a", "b", "a"]))
        self.assertTrue(has_duplicates([(1, 2), (1, 2)]))

    def test_has_duplicates_is_linear(self):
        counter = OpCounter()
        items = [Item(v, counter) for v in random.Random(1).sample(range(10**9), N_OPS)]  # 重複なし = 最悪
        self.assertFalse(has_duplicates(items))
        self.assertLessEqual(
            counter.count, LINEAR_LIMIT * N_OPS,
            f"{N_OPS} 要素で比較・ハッシュが {counter.count} 回。すべての組を比べる O(n^2) になっていませんか（set を使う）",
        )

    def test_dedupe(self):
        self.assertEqual(dedupe_preserving_order(["b", "a", "b", "c", "a"]), ["b", "a", "c"])
        self.assertEqual(dedupe_preserving_order([]), [])
        self.assertEqual(dedupe_preserving_order(iter([3, 3, 3])), [3], "イテレータも受け付ける")
        rng = random.Random(2)
        for _ in range(100):
            data = [rng.randrange(20) for _ in range(rng.randrange(0, 50))]
            expected = []
            for x in data:
                if x not in expected:
                    expected.append(x)
            self.assertEqual(dedupe_preserving_order(data), expected)

    def test_dedupe_is_linear(self):
        counter = OpCounter()
        rng = random.Random(3)
        items = [Item(rng.randrange(N_OPS), counter) for _ in range(N_OPS)]
        result = dedupe_preserving_order(items)
        self.assertEqual(len(result), len({it.value for it in items}))
        self.assertLessEqual(counter.count, LINEAR_LIMIT * N_OPS, f"比較・ハッシュが {counter.count} 回")

    def test_two_sum_examples(self):
        self.assertEqual(two_sum([2, 7, 11, 15], 9), (0, 1))
        self.assertEqual(two_sum([3, 3, 4, 3], 6), (0, 1))
        self.assertEqual(two_sum([1, 2, 3, 3], 6), (2, 3))
        self.assertEqual(two_sum([4, 1, 2, 5], 6), (0, 2), "j が最小の組を返す（(1, 3) ではない）")
        self.assertEqual(two_sum([1, 5, 5, 5], 10), (1, 2), "j が最小、その中で i が最小")
        self.assertIsNone(two_sum([1, 2, 3], 100))
        self.assertIsNone(two_sum([], 0))
        self.assertIsNone(two_sum([5], 10), "同じ要素を 2 回使ってはいけない")
        self.assertEqual(two_sum([-3, 8, 3], 0), (0, 2))

    def test_two_sum_matches_reference(self):
        rng = random.Random(4)
        for _ in range(300):
            nums = [rng.randrange(-20, 20) for _ in range(rng.randrange(0, 30))]
            target = rng.randrange(-30, 30)
            self.assertEqual(two_sum(nums, target), slow_two_sum(nums, target), (nums, target))

    def test_two_sum_is_linear(self):
        counter = OpCounter()
        nums = [CountingInt(2 * v, counter) for v in range(N_OPS)]   # 偶数だけ
        self.assertIsNone(two_sum(nums, 1))                          # 奇数の和は作れない = 最悪ケース
        self.assertLessEqual(
            counter.count, LINEAR_LIMIT * N_OPS,
            f"足し算・比較・ハッシュが {counter.count} 回。dict を使って O(n) にしてください",
        )

    def test_count_pairs(self):
        self.assertEqual(count_pairs_with_sum([1, 5, 7, -1, 5], 6), 3)
        self.assertEqual(count_pairs_with_sum([3, 3, 3], 6), 3)
        self.assertEqual(count_pairs_with_sum([], 0), 0)
        self.assertEqual(count_pairs_with_sum([0, 0, 0, 0], 0), 6)
        rng = random.Random(5)
        for _ in range(300):
            nums = [rng.randrange(-10, 10) for _ in range(rng.randrange(0, 40))]
            k = rng.randrange(-15, 15)
            self.assertEqual(count_pairs_with_sum(nums, k), slow_count_pairs(nums, k), (nums, k))

    def test_count_pairs_is_linear(self):
        counter = OpCounter()
        rng = random.Random(6)
        nums = [CountingInt(rng.randrange(-N_OPS, N_OPS), counter) for _ in range(N_OPS)]
        count_pairs_with_sum(nums, 7)
        self.assertLessEqual(counter.count, LINEAR_LIMIT * N_OPS, f"操作が {counter.count} 回")


# ---------------------------------------------------------------------------
# 演習2
# ---------------------------------------------------------------------------

class TestExercise2BinarySearch(unittest.TestCase):
    def test_examples(self):
        a = [1, 2, 2, 2, 3]
        self.assertEqual(lower_bound(a, 2), 1)
        self.assertEqual(upper_bound(a, 2), 4)
        self.assertEqual(lower_bound(a, 0), 0)
        self.assertEqual(upper_bound(a, 0), 0)
        self.assertEqual(lower_bound(a, 4), 5)
        self.assertEqual(upper_bound(a, 3), 5)
        self.assertEqual(lower_bound([], 1), 0)
        self.assertEqual(upper_bound([], 1), 0)

    def test_matches_bisect(self):
        rng = random.Random(7)
        for _ in range(500):
            a = sorted(rng.randrange(0, 20) for _ in range(rng.randrange(0, 30)))
            x = rng.randrange(-2, 22)
            self.assertEqual(lower_bound(a, x), bisect.bisect_left(a, x), (a, x))
            self.assertEqual(upper_bound(a, x), bisect.bisect_right(a, x), (a, x))
            lo = rng.randrange(0, len(a) + 1)
            hi = rng.randrange(lo, len(a) + 1)
            self.assertEqual(lower_bound(a, x, lo, hi), bisect.bisect_left(a, x, lo, hi), (a, x, lo, hi))
            self.assertEqual(upper_bound(a, x, lo, hi), bisect.bisect_right(a, x, lo, hi), (a, x, lo, hi))

    def test_count_occurrences(self):
        a = [1, 3, 3, 3, 3, 5, 8, 8]
        for x, expected in [(3, 4), (8, 2), (4, 0), (1, 1)]:
            self.assertEqual(upper_bound(a, x) - lower_bound(a, x), expected, x)

    def test_logarithmic_reads(self):
        for n in (1, 2, 3, 100, 1000, 10**5):
            a = CountingList(range(n))
            for x in (-1, 0, n // 2, n - 1, n + 5):
                for func in (lower_bound, upper_bound):
                    a.reads = 0
                    func(a, x)
                    limit = n.bit_length() + 1
                    self.assertLessEqual(a.reads, limit, f"{func.__name__}: n={n} で {a.reads} 回アクセス（上限 {limit}）")

    def test_uses_only_less_than(self):
        a = [OnlyLess(v) for v in (1, 2, 2, 5, 9)]
        self.assertEqual(lower_bound(a, OnlyLess(2)), 1)
        self.assertEqual(upper_bound(a, OnlyLess(2)), 3)
        self.assertEqual(lower_bound(a, OnlyLess(6)), 4)
        self.assertEqual(upper_bound(a, OnlyLess(9)), 5)

    def test_invalid_range(self):
        a = [1, 2, 3]
        for lo, hi in [(-1, 3), (2, 1), (0, 4)]:
            with self.assertRaises(ValueError, msg=(lo, hi)):
                lower_bound(a, 2, lo, hi)
            with self.assertRaises(ValueError, msg=(lo, hi)):
                upper_bound(a, 2, lo, hi)

    def test_first_true(self):
        self.assertEqual(first_true(0, 100, lambda i: i * i >= 50), 8)
        self.assertEqual(first_true(0, 10, lambda i: False), 10)
        self.assertEqual(first_true(0, 10, lambda i: True), 0)
        self.assertEqual(first_true(5, 5, lambda i: True), 5, "空の範囲なら hi")
        self.assertEqual(first_true(-50, 50, lambda i: i >= -7), -7)
        with self.assertRaises(ValueError):
            first_true(3, 2, lambda i: True)

    def test_first_true_applications(self):
        # 整数平方根
        for n in list(range(200)) + [10**12 + 7, 2**64]:
            pred = limited(lambda r: r * r > n, 0, n + 2)
            self.assertEqual(first_true(0, n + 2, pred) - 1, math.isqrt(n), n)
        # git bisect: 最初に壊れたコミット
        first_bad = 7_654
        self.assertEqual(first_true(0, 10_000, limited(lambda c: c >= first_bad, 0, 10_000)), first_bad)
        # 容量計画: 1 台 350 件/秒のサーバーで 10,000 件/秒を捌くのに必要な最小台数
        self.assertEqual(first_true(1, 1000, limited(lambda k: k * 350 >= 10_000, 1, 1000)), 29)

    def test_first_true_calls_predicate_logarithmically(self):
        rng = random.Random(8)
        for _ in range(200):
            lo = rng.randrange(-10**6, 10**6)
            hi = lo + rng.randrange(0, 10**6)
            boundary = rng.randrange(lo, hi + 1)
            pred = limited(lambda i, b=boundary: i >= b, lo, hi)   # 上限を超えたら即失敗する
            self.assertEqual(first_true(lo, hi, pred), boundary, (lo, hi, boundary))


# ---------------------------------------------------------------------------
# 演習3
# ---------------------------------------------------------------------------

class TestExercise3DynamicArray(unittest.TestCase):
    def test_basic_operations(self):
        arr = DynamicArray()
        self.assertEqual(len(arr), 0)
        self.assertEqual(arr.capacity, 1)
        self.assertEqual(arr.copies, 0)
        for i in range(5):
            arr.append(i * 10)
        self.assertEqual(len(arr), 5)
        self.assertEqual([arr[i] for i in range(5)], [0, 10, 20, 30, 40])
        self.assertEqual(arr[-1], 40)
        self.assertEqual(arr[-5], 0)
        arr[2] = 99
        arr[-1] = 77
        self.assertEqual(list(arr), [0, 10, 99, 30, 77])
        self.assertEqual(arr.pop(), 77)
        self.assertEqual(len(arr), 4)

    def test_behaves_like_list(self):
        rng = random.Random(9)
        arr, ref = DynamicArray(rng.choice([1, 2, 3])), []
        for _ in range(3000):
            r = rng.random()
            if r < 0.55 or not ref:
                v = rng.randrange(1000)
                arr.append(v)
                ref.append(v)
            elif r < 0.85:
                self.assertEqual(arr.pop(), ref.pop())
            else:
                i = rng.randrange(-len(ref), len(ref))
                v = rng.randrange(1000)
                arr[i] = v
                ref[i] = v
            self.assertEqual(len(arr), len(ref))
        self.assertEqual([arr[i] for i in range(len(arr))], ref)

    def test_index_errors(self):
        arr = DynamicArray()
        with self.assertRaises(IndexError):
            arr.pop()
        with self.assertRaises(IndexError):
            arr[0]
        arr.append("a")
        for bad in (1, 5, -2):
            with self.assertRaises(IndexError, msg=bad):
                arr[bad]
            with self.assertRaises(IndexError, msg=bad):
                arr[bad] = "x"
        with self.assertRaises(ValueError):
            DynamicArray(0)

    def test_growth_policy_and_copies(self):
        expected = {1: (1, 0), 2: (2, 1), 3: (4, 3), 5: (8, 7), 9: (16, 15), 1024: (1024, 1023), 1025: (2048, 2047)}
        for n, (capacity, copies) in expected.items():
            arr = DynamicArray()
            for i in range(n):
                arr.append(i)
            self.assertEqual((arr.capacity, arr.copies), (capacity, copies), f"n={n}: (容量, コピー回数)")
        arr = DynamicArray(3)
        for i in range(7):
            arr.append(i)
        self.assertEqual((arr.capacity, arr.copies), (12, 3 + 6))

    def test_amortized_bound_for_appends(self):
        for n in (1, 10, 100, 1000, 4097, 10_000):
            arr = DynamicArray()
            for i in range(n):
                arr.append(i)
            self.assertLessEqual(arr.copies + n, 3 * n, f"n={n}: 総書き込み回数（append + コピー）は 3n 以下のはず")

    def test_shrink_policy(self):
        arr = DynamicArray()
        for i in range(64):
            arr.append(i)
        self.assertEqual(arr.capacity, 64)
        while len(arr) > 17:
            arr.pop()
        self.assertEqual(arr.capacity, 64, "len > capacity // 4 の間は縮めない")
        arr.pop()  # len = 16 = 64 // 4
        self.assertEqual(arr.capacity, 32)
        while len(arr) > 0:
            arr.pop()
        self.assertEqual(arr.capacity, 1, "空になれば初期容量まで縮む")
        arr8 = DynamicArray(8)
        for i in range(100):
            arr8.append(i)
        for _ in range(100):
            arr8.pop()
        self.assertEqual(arr8.capacity, 8, "初期容量より小さくはしない")

    def test_memory_stays_proportional(self):
        rng = random.Random(10)
        arr = DynamicArray()
        for _ in range(5000):
            if rng.random() < 0.5 or len(arr) == 0:
                arr.append(0)
            else:
                arr.pop()
            self.assertLessEqual(len(arr), arr.capacity)
            self.assertLessEqual(arr.capacity, max(1, 4 * len(arr)), "容量は要素数の 4 倍以下に保たれるはず")

    def test_no_thrashing_at_boundary(self):
        arr = DynamicArray()
        for i in range(1024):
            arr.append(i)  # ちょうど満杯
        before = arr.copies
        for _ in range(1000):
            arr.append(0)
            arr.pop()
        extra = arr.copies - before
        self.assertLessEqual(
            extra, 2 * 1024,
            f"境界での append/pop 1,000 往復でコピーが {extra} 回。縮小の条件が早すぎて振動していませんか",
        )

    def test_amortized_bound_for_mixed_sequences(self):
        for seed in range(30):
            rng = random.Random(seed)
            arr = DynamicArray()
            ops = 0
            p_append = rng.choice([0.3, 0.5, 0.7, 0.9])
            for _ in range(rng.randrange(100, 3000)):
                if len(arr) == 0 or rng.random() < p_append:
                    arr.append(0)
                else:
                    arr.pop()
                ops += 1
            self.assertLessEqual(arr.copies, 3 * ops, f"seed={seed}: コピー {arr.copies} 回、操作 {ops} 回")


# ---------------------------------------------------------------------------
# 演習4
# ---------------------------------------------------------------------------

class FakeClock:
    """呼ばれるたびに現在の「時刻」を返す偽の時計。advance() で時刻を進める。"""

    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, dt):
        self.now += dt


class TestExercise4EstimateOrder(unittest.TestCase):
    def test_slope_exact_power_laws(self):
        sizes = [1000, 2000, 4000, 8000]
        for k in (0.5, 1, 2, 3):
            times = [3e-9 * n**k for n in sizes]
            self.assertAlmostEqual(fit_loglog_slope(sizes, times), k, places=9)
        self.assertAlmostEqual(fit_loglog_slope([10, 100], [1.0, 1.0]), 0.0)

    def test_slope_of_n_log_n_is_slightly_above_one(self):
        sizes = [2**k for k in range(10, 21)]
        slope = fit_loglog_slope(sizes, [n * math.log(n) for n in sizes])
        self.assertTrue(1.05 < slope < 1.15, slope)

    def test_classifies_synthetic_timings(self):
        sizes = [2**k for k in range(10, 21, 2)]
        for seed in range(5):
            rng = random.Random(seed)
            for label, g in ORDER_MODELS:
                c = rng.uniform(1e-9, 1e-3)
                times = [c * g(n) * (1 + rng.uniform(-0.05, 0.05)) for n in sizes]
                self.assertEqual(estimate_order(sizes, times), label, f"seed={seed}, 正解 {label}")

    def test_distinguishes_n_and_n_log_n(self):
        sizes = [1000, 2000, 4000, 8000, 16000, 32000]
        self.assertEqual(estimate_order(sizes, [2e-7 * n for n in sizes]), "O(n)")
        self.assertEqual(estimate_order(sizes, [2e-8 * n * math.log(n) for n in sizes]), "O(n log n)")

    def test_real_measurement_from_text(self):
        # 本文で has_duplicates の遅い版を計測した結果（ミリ秒を秒に直したもの）
        self.assertEqual(estimate_order([500, 1000, 2000, 4000], [0.0032, 0.0118, 0.0466, 0.1881]), "O(n^2)")

    def test_invalid(self):
        for sizes, times in [([], []), ([100], [1.0]), ([100, 200], [1.0]), ([1, 200], [1.0, 2.0]),
                             ([100, 200], [0.0, 1.0]), ([100, 100], [1.0, 2.0])]:
            with self.assertRaises(ValueError, msg=(sizes, times)):
                fit_loglog_slope(sizes, times)
            with self.assertRaises(ValueError, msg=(sizes, times)):
                estimate_order(sizes, times)

    def test_measure_times_with_fake_clock(self):
        clock = FakeClock()
        made = []

        def make_input(n):
            made.append(n)
            clock.advance(1_000_000)          # 入力の生成に時間がかかっても計測に含まれないこと
            return list(range(n))

        def func(data):
            clock.advance(len(data) ** 2)      # 「n^2 秒かかる処理」

        sizes = [10, 20, 40]
        times = measure_times(func, make_input, sizes, repeat=4, timer=clock)
        self.assertEqual(times, [100.0, 400.0, 1600.0])
        self.assertEqual(made, sizes, "make_input は n ごとに 1 回だけ呼ぶこと")
        self.assertEqual(estimate_order(sizes, times), "O(n^2)")

    def test_measure_times_takes_minimum(self):
        clock = FakeClock()
        noise = iter([5.0, 0.0, 2.0, 7.0, 1.0, 0.0])

        def func(data):
            clock.advance(10 + next(noise))    # たまに他の処理に割り込まれる

        self.assertEqual(measure_times(func, lambda n: n, [1, 2], repeat=3, timer=clock), [10.0, 10.0])
        with self.assertRaises(ValueError):
            measure_times(func, lambda n: n, [1], repeat=0, timer=clock)


# ---------------------------------------------------------------------------
# 演習5
# ---------------------------------------------------------------------------

def schoolbook(p, q):
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        for j, b in enumerate(q):
            out[i + j] += a * b
    return out


class TestExercise5DivideAndConquer(unittest.TestCase):
    def check_master(self, args, case, p, k):
        got = master_theorem(*args)
        self.assertEqual(got[0], case, f"T(n) = {args[0]}T(n/{args[1]}) + n^{args[2]} の場合の番号")
        self.assertAlmostEqual(got[1], p, places=9, msg=f"{args} の指数")
        self.assertEqual(got[2], k, f"{args} の log の指数")

    def test_master_theorem_classic_recurrences(self):
        self.check_master((1, 2, 0), 2, 0.0, 1)                # 二分探索: log n
        self.check_master((2, 2, 1), 2, 1.0, 1)                # マージソート: n log n
        self.check_master((2, 2, 0), 1, 1.0, 0)                # 二分木の走査: n
        self.check_master((3, 2, 1), 1, math.log2(3), 0)       # カラツバ法
        self.check_master((4, 2, 1), 1, 2.0, 0)                # 素朴な分割統治の掛け算: n^2
        self.check_master((7, 2, 2), 1, math.log2(7), 0)       # シュトラッセン法
        self.check_master((1, 2, 1), 3, 1.0, 0)                # T(n) = T(n/2) + n: n
        self.check_master((2, 2, 2), 3, 2.0, 0)                # 根が支配的: n^2

    def test_master_theorem_floating_point_boundaries(self):
        self.check_master((1000, 10, 3), 2, 3.0, 1)            # math.log(1000, 10) は 2.9999999999999996
        self.check_master((9, 3, 2), 2, 2.0, 1)
        self.check_master((2, 4, 0.5), 2, 0.5, 1)
        self.check_master((8, 2, 3), 2, 3.0, 1)

    def test_master_theorem_invalid(self):
        for args in [(0.5, 2, 1), (2, 1, 1), (2, 0.5, 1), (2, 2, -1)]:
            with self.assertRaises(ValueError, msg=args):
                master_theorem(*args)

    def test_products_are_correct(self):
        rng = random.Random(11)
        for k in range(0, 7):
            n = 2**k
            for _ in range(10):
                p = [rng.randrange(-50, 50) for _ in range(n)]
                q = [rng.randrange(-50, 50) for _ in range(n)]
                expected = schoolbook(p, q)
                self.assertEqual(karatsuba_poly(p, q)[0], expected, (p, q))
                self.assertEqual(naive_dc_poly(p, q)[0], expected, (p, q))

    def test_multiplication_counts(self):
        rng = random.Random(12)
        for k in range(0, 9):
            n = 2**k
            p = [rng.randrange(1, 10) for _ in range(n)]
            q = [rng.randrange(1, 10) for _ in range(n)]
            self.assertEqual(karatsuba_poly(p, q)[1], 3**k, f"n={n}: カラツバ法の掛け算は 3^k 回")
            if k <= 7:
                self.assertEqual(naive_dc_poly(p, q)[1], 4**k, f"n={n}: 素朴な分割統治は 4^k = n^2 回")

    def test_counts_match_master_theorem(self):
        # 掛け算の回数の増え方（両対数の傾き）が、マスター定理の指数と一致する
        sizes = [2**k for k in range(1, 9)]
        ones = [[1] * n for n in sizes]
        karatsuba_counts = [karatsuba_poly(v, v)[1] for v in ones]
        naive_counts = [naive_dc_poly(v, v)[1] for v in ones[:6]]
        for counts, ns, args in [(karatsuba_counts, sizes, (3, 2, 1)), (naive_counts, sizes[:6], (4, 2, 1))]:
            slope = (math.log(counts[-1]) - math.log(counts[0])) / (math.log(ns[-1]) - math.log(ns[0]))
            self.assertAlmostEqual(slope, master_theorem(*args)[1], places=9)

    def test_invalid_lengths(self):
        for p, q in [([], []), ([1, 2, 3], [1, 2, 3]), ([1, 2], [1, 2, 3, 4]), ([1], [])]:
            with self.assertRaises(ValueError, msg=(p, q)):
                karatsuba_poly(p, q)
            with self.assertRaises(ValueError, msg=(p, q)):
                naive_dc_poly(p, q)


if __name__ == "__main__":
    unittest.main()
