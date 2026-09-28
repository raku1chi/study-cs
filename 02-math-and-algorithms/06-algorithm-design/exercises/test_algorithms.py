"""2.6 アルゴリズム設計技法 — テスト

実行: python3 tools/check.py 2.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import itertools
import math
import os
import random
import tempfile
import time
import unittest

from algorithms import (
    counting_sort,
    edit_distance,
    external_sort,
    knapsack,
    kway_merge,
    lcs,
    line_diff,
    max_non_overlapping,
    merge_sort,
    min_meeting_rooms,
    n_queens,
    quicksort,
    radix_sort,
    reservoir_sample,
    subset_sum,
)


class Counted:
    """比較演算の回数を数える値（アルゴリズムの計算量を「比較回数」で確かめるため）。"""

    comparisons = 0

    def __init__(self, v, tag=None) -> None:
        self.v = v
        self.tag = tag

    def _pair(self, other):
        Counted.comparisons += 1
        return self.v, other.v

    def __lt__(self, other):
        a, b = self._pair(other)
        return a < b

    def __le__(self, other):
        a, b = self._pair(other)
        return a <= b

    def __gt__(self, other):
        a, b = self._pair(other)
        return a > b

    def __ge__(self, other):
        a, b = self._pair(other)
        return a >= b

    def __eq__(self, other):
        return isinstance(other, Counted) and self.v == other.v

    __hash__ = None

    def __repr__(self):
        return f"Counted({self.v}, {self.tag})"


# ---------------------------------------------------------------------------
# 演習1: ソート
# ---------------------------------------------------------------------------

class TestExercise1MergeSort(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(merge_sort([3, 1, 2]), [1, 2, 3])
        self.assertEqual(merge_sort([]), [])
        self.assertEqual(merge_sort([1]), [1])
        self.assertEqual(merge_sort("banana"), list("aaabnn"))

    def test_does_not_modify_input(self):
        data = [5, 4, 3]
        result = merge_sort(data)
        self.assertEqual(data, [5, 4, 3])
        self.assertEqual(result, [3, 4, 5])

    def test_matches_sorted(self):
        rng = random.Random(60)
        for _ in range(100):
            data = [rng.randrange(-50, 50) for _ in range(rng.randrange(0, 200))]
            self.assertEqual(merge_sort(data), sorted(data))

    def test_is_stable_with_key(self):
        records = [("tanaka", 30), ("sato", 25), ("suzuki", 30), ("ito", 25), ("kato", 40)]
        got = merge_sort(records, key=lambda r: r[1])
        self.assertEqual(got, [("sato", 25), ("ito", 25), ("tanaka", 30), ("suzuki", 30), ("kato", 40)])

    def test_stability_on_random_data(self):
        rng = random.Random(61)
        data = [(rng.randrange(10), i) for i in range(500)]
        self.assertEqual(merge_sort(data, key=lambda t: t[0]), sorted(data, key=lambda t: t[0]))

    def test_n_log_n_comparisons(self):
        # マージソートの比較回数は n⌈log2 n⌉ 以下。挿入ソートなら約 n^2/4 回になる
        rng = random.Random(62)
        n = 1024
        data = [Counted(rng.random()) for _ in range(n)]
        Counted.comparisons = 0
        result = merge_sort(data)
        self.assertLessEqual(Counted.comparisons, n * 10, f"比較 {Counted.comparisons} 回")
        self.assertEqual([c.v for c in result], sorted(c.v for c in data))


class TestExercise1Quicksort(unittest.TestCase):
    def test_sorts_in_place(self):
        data = [5, 2, 9, 1, 5, 6]
        self.assertIsNone(quicksort(data, random.Random(0)), "その場で並べ替え、None を返す")
        self.assertEqual(data, [1, 2, 5, 5, 6, 9])

    def test_various_inputs(self):
        rng = random.Random(63)
        cases = [[], [1], [2, 1], list(range(500)), list(range(500, 0, -1)), [7] * 300]
        cases += [[rng.randrange(20) for _ in range(rng.randrange(0, 300))] for _ in range(50)]
        for data in cases:
            expected = sorted(data)
            quicksort(data, random.Random(1))
            self.assertEqual(data, expected)

    def test_default_rng(self):
        data = [3, 1, 2]
        quicksort(data)
        self.assertEqual(data, [1, 2, 3])

    def test_sorted_input_is_not_quadratic(self):
        n = 2000
        data = [Counted(i) for i in range(n)]
        Counted.comparisons = 0
        quicksort(data, random.Random(64))
        self.assertLess(Counted.comparisons, 10 * n * math.log2(n), "ランダムなピボットなら整列済みでも O(n log n)")

    def test_many_duplicates_are_not_quadratic(self):
        # すべて等しい要素。素朴な 2 分割（Lomuto 方式）だと毎回 n-1 個が片側に寄って O(n^2)
        n = 2000
        data = [Counted(7) for _ in range(n)]
        Counted.comparisons = 0
        quicksort(data, random.Random(65))
        self.assertLess(
            Counted.comparisons, 10 * n * math.log2(n),
            f"比較 {Counted.comparisons} 回: 重複の多い入力に弱い分割になっていませんか（3-way 分割を検討）",
        )

    def test_uses_injected_rng(self):
        class SpyRandom(random.Random):
            # randint・randrange・choice は内部で getrandbits を、uniform は random を呼ぶ
            calls = 0

            def random(self):
                SpyRandom.calls += 1
                return super().random()

            def getrandbits(self, k):
                SpyRandom.calls += 1
                return super().getrandbits(k)

        data = list(range(100, 0, -1))
        quicksort(data, SpyRandom(3))
        self.assertEqual(data, list(range(1, 101)))
        self.assertGreater(SpyRandom.calls, 0, "引数で渡された rng を使ってピボットを選ぶこと")

    def test_injected_rng_makes_it_deterministic(self):
        rng = random.Random(66)
        data = [Counted(rng.randrange(1000)) for _ in range(300)]
        counts = []
        for _ in range(2):
            copy = list(data)
            Counted.comparisons = 0
            quicksort(copy, random.Random(12345))
            counts.append(Counted.comparisons)
        self.assertEqual(counts[0], counts[1], "同じシードの乱数なら、同じ比較回数になるはず")


class TestExercise1NonComparisonSorts(unittest.TestCase):
    def test_counting_sort(self):
        self.assertEqual(counting_sort([3, 0, 2, 3, 1]), [0, 1, 2, 3, 3])
        self.assertEqual(counting_sort([]), [])
        self.assertEqual(counting_sort([5, 1], max_value=10), [1, 5])
        with self.assertRaises(ValueError):
            counting_sort([1, -1])
        with self.assertRaises(ValueError):
            counting_sort([11], max_value=10)
        with self.assertRaises(TypeError):
            counting_sort([1.5])

    def test_radix_sort_matches_sorted(self):
        rng = random.Random(67)
        for base in (2, 10, 256, 1 << 16):
            data = [rng.randrange(0, 2**64) for _ in range(300)] + [0, 0, 1]
            self.assertEqual(radix_sort(data, base=base), sorted(data), f"base={base}")
        self.assertEqual(radix_sort([]), [])
        self.assertEqual(radix_sort([0, 0]), [0, 0])

    def test_radix_sort_validation(self):
        with self.assertRaises(ValueError):
            radix_sort([1, 2], base=1)
        with self.assertRaises(ValueError):
            radix_sort([3, -2])
        with self.assertRaises(TypeError):
            radix_sort(["12"])

    def test_radix_does_not_modify_input(self):
        data = [300, 1, 70000]
        radix_sort(data)
        self.assertEqual(data, [300, 1, 70000])


# ---------------------------------------------------------------------------
# 演習2: 貪欲法
# ---------------------------------------------------------------------------

def brute_max_non_overlapping(intervals):
    best = 0
    for r in range(len(intervals), 0, -1):
        for combo in itertools.combinations(intervals, r):
            ordered = sorted(combo)
            if all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])):
                return r
    return best


class TestExercise2Greedy(unittest.TestCase):
    def test_interval_scheduling_example(self):
        meetings = [(9, 12), (10, 11), (11, 13), (12, 14), (13, 15), (9, 10)]
        chosen = max_non_overlapping(meetings)
        self.assertEqual(chosen, [(9, 10), (10, 11), (11, 13), (13, 15)])

    def test_touching_intervals_do_not_overlap(self):
        self.assertEqual(len(max_non_overlapping([(1, 2), (2, 3), (3, 4)])), 3)

    def test_interval_scheduling_is_optimal(self):
        rng = random.Random(70)
        for _ in range(60):
            ivs = []
            for _ in range(rng.randrange(0, 9)):
                s = rng.randrange(0, 20)
                ivs.append((s, s + rng.randrange(1, 8)))
            chosen = max_non_overlapping(ivs)
            self.assertEqual(len(chosen), brute_max_non_overlapping(ivs), ivs)
            for iv in chosen:
                self.assertIn(iv, ivs)
            self.assertEqual(chosen, sorted(chosen, key=lambda iv: (iv[1], iv[0])), "終了時刻の順に返す")
            for a, b in zip(chosen, chosen[1:]):
                self.assertLessEqual(a[1], b[0], "選んだ区間が重なっています")

    def test_meeting_rooms_example(self):
        self.assertEqual(min_meeting_rooms([(9, 10), (9, 12), (10, 11), (11, 12)]), 2)
        self.assertEqual(min_meeting_rooms([(1, 5), (2, 6), (3, 7)]), 3)
        self.assertEqual(min_meeting_rooms([(1, 2), (2, 3)]), 1, "終了と同時に始まる会議は同じ部屋を使える")
        self.assertEqual(min_meeting_rooms([]), 0)

    def test_meeting_rooms_equals_max_overlap(self):
        rng = random.Random(71)
        for _ in range(100):
            ivs = []
            for _ in range(rng.randrange(0, 30)):
                s = rng.randrange(0, 50)
                ivs.append((s, s + rng.randrange(1, 15)))
            depth = max((sum(s <= t < e for s, e in ivs) for t in range(70)), default=0)
            self.assertEqual(min_meeting_rooms(ivs), depth)

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            max_non_overlapping([(3, 3)])
        with self.assertRaises(ValueError):
            min_meeting_rooms([(5, 1)])


# ---------------------------------------------------------------------------
# 演習3: 動的計画法（編集距離・LCS・差分）
# ---------------------------------------------------------------------------

def ref_edit_distance(a, b):
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j - 1] + (a[i - 1] != b[j - 1]), prev[j] + 1, cur[j - 1] + 1)
        prev = cur
    return prev[-1]


def ref_lcs_len(a, b):
    L = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a)):
        for j in range(len(b)):
            L[i + 1][j + 1] = L[i][j] + 1 if a[i] == b[j] else max(L[i][j + 1], L[i + 1][j])
    return L[-1][-1]


def is_subsequence(sub, seq):
    it = iter(seq)
    return all(any(x == y for y in it) for x in sub)


class TestExercise3EditDistance(unittest.TestCase):
    def assert_valid_script(self, a, b, dist, ops):
        self.assertEqual([x for op, x, _ in ops if op != "+"], list(a), "操作列の元の要素を並べると a になること")
        self.assertEqual([y for op, _, y in ops if op != "-"], list(b), "操作列の結果の要素を並べると b になること")
        for op, x, y in ops:
            self.assertIn(op, ("=", "~", "-", "+"))
            if op == "=":
                self.assertEqual(x, y)
            elif op == "~":
                self.assertNotEqual(x, y)
            elif op == "-":
                self.assertIsNone(y)
            else:
                self.assertIsNone(x)
        self.assertEqual(sum(op != "=" for op, _, _ in ops), dist, "「=」以外の操作の数が距離と一致すること")

    def test_examples(self):
        dist, ops = edit_distance("kitten", "sitting")
        self.assertEqual(dist, 3)
        self.assert_valid_script("kitten", "sitting", dist, ops)
        self.assertEqual(edit_distance("", "abc"), (3, [("+", None, "a"), ("+", None, "b"), ("+", None, "c")]))
        self.assertEqual(edit_distance("abc", ""), (3, [("-", "a", None), ("-", "b", None), ("-", "c", None)]))
        self.assertEqual(edit_distance("same", "same")[0], 0)
        self.assertEqual(edit_distance("", ""), (0, []))

    def test_japanese(self):
        dist, ops = edit_distance("しんじゅく", "しぶや")
        self.assertEqual(dist, ref_edit_distance("しんじゅく", "しぶや"))
        self.assert_valid_script("しんじゅく", "しぶや", dist, ops)

    def test_random_against_reference(self):
        rng = random.Random(72)
        for _ in range(200):
            a = "".join(rng.choice("abc") for _ in range(rng.randrange(0, 12)))
            b = "".join(rng.choice("abc") for _ in range(rng.randrange(0, 12)))
            dist, ops = edit_distance(a, b)
            self.assertEqual(dist, ref_edit_distance(a, b), (a, b))
            self.assert_valid_script(a, b, dist, ops)

    def test_works_on_lists(self):
        dist, ops = edit_distance(["GET", "/a"], ["POST", "/a"])
        self.assertEqual(dist, 1)
        self.assertEqual(ops, [("~", "GET", "POST"), ("=", "/a", "/a")])


class TestExercise3Diff(unittest.TestCase):
    def test_lcs_examples(self):
        self.assertEqual("".join(lcs("ABCBDAB", "BDCABA")).__len__(), 4)
        self.assertEqual(lcs("", "abc"), [])
        self.assertEqual(lcs("abc", "abc"), list("abc"))

    def test_lcs_random(self):
        rng = random.Random(73)
        for _ in range(150):
            a = [rng.choice("xyz") for _ in range(rng.randrange(0, 15))]
            b = [rng.choice("xyz") for _ in range(rng.randrange(0, 15))]
            got = lcs(a, b)
            self.assertEqual(len(got), ref_lcs_len(a, b))
            self.assertTrue(is_subsequence(got, a) and is_subsequence(got, b), (a, b, got))

    def check_diff(self, old, new, diff):
        for line in diff:
            self.assertIn(line[:1], (" ", "-", "+"), f"行頭は ' ', '-', '+' のいずれか: {line!r}")
        self.assertEqual([d[1:] for d in diff if d[0] in " -"], list(old), "' ' と '-' の行を並べると old になること")
        self.assertEqual([d[1:] for d in diff if d[0] in " +"], list(new), "' ' と '+' の行を並べると new になること")
        self.assertEqual(sum(d[0] == " " for d in diff), ref_lcs_len(old, new), "共通行の数が最大（=LCS の長さ）であること")
        for prev, cur in zip(diff, diff[1:]):
            self.assertFalse(prev[0] == "+" and cur[0] == "-", f"変更箇所では '-' の行を '+' の行より先に: {prev!r}, {cur!r}")

    def test_line_diff_example(self):
        old = ["def total(xs):", "    s = 0", "    for x in xs:", "        s += x", "    return s"]
        new = ["def total(xs):", "    return sum(xs)"]
        diff = line_diff(old, new)
        self.assertEqual(
            diff,
            [" def total(xs):", "-    s = 0", "-    for x in xs:", "-        s += x", "-    return s", "+    return sum(xs)"],
        )

    def test_line_diff_modify_middle(self):
        old = ["a", "b", "c", "d"]
        new = ["a", "B", "c", "d", "e"]
        self.assertEqual(line_diff(old, new), [" a", "-b", "+B", " c", " d", "+e"])

    def test_line_diff_random(self):
        rng = random.Random(74)
        for _ in range(150):
            old = [rng.choice(["x = 1", "y = 2", "z = 3", "", "pass"]) for _ in range(rng.randrange(0, 12))]
            new = list(old)
            for _ in range(rng.randrange(0, 5)):
                op = rng.random()
                if op < 0.4 and new:
                    del new[rng.randrange(len(new))]
                elif op < 0.8:
                    new.insert(rng.randrange(len(new) + 1), rng.choice(["w = 0", "x = 1", "return"]))
                elif new:
                    new[rng.randrange(len(new))] = "changed"
            self.check_diff(old, new, line_diff(old, new))

    def test_empty_inputs(self):
        self.assertEqual(line_diff([], []), [])
        self.assertEqual(line_diff(["a"], []), ["-a"])
        self.assertEqual(line_diff([], ["a"]), ["+a"])


# ---------------------------------------------------------------------------
# 演習4: 0/1 ナップサック
# ---------------------------------------------------------------------------

def brute_knapsack(items, capacity):
    best = 0
    for r in range(len(items) + 1):
        for combo in itertools.combinations(range(len(items)), r):
            if sum(items[i][0] for i in combo) <= capacity:
                best = max(best, sum(items[i][1] for i in combo))
    return best


class TestExercise4Knapsack(unittest.TestCase):
    def check(self, items, capacity, result):
        value, chosen = result
        self.assertEqual(chosen, sorted(set(chosen)), "添字は重複なしの昇順で返すこと")
        self.assertLessEqual(sum(items[i][0] for i in chosen), capacity, "容量を超えています")
        self.assertEqual(sum(items[i][1] for i in chosen), value, "選んだ品物の価値の合計が最大値と一致すること")

    def test_example(self):
        items = [(1, 1), (3, 4), (4, 5), (5, 7)]  # (重さ, 価値)
        result = knapsack(items, 7)
        self.assertEqual(result[0], 9)
        self.check(items, 7, result)

    def test_greedy_by_ratio_is_not_optimal(self):
        # 価値/重さ の比が最大の品物（0番: 比 6）から詰める貪欲法だと 160 にしかならない
        items = [(10, 60), (20, 100), (30, 120)]
        self.assertEqual(knapsack(items, 50), (220, [1, 2]))

    def test_edge_cases(self):
        self.assertEqual(knapsack([], 10), (0, []))
        self.assertEqual(knapsack([(5, 10)], 0), (0, []))
        self.assertEqual(knapsack([(0, 3), (1, 1)], 0), (3, [0]), "重さ 0 の品物は容量 0 でも入る")
        with self.assertRaises(ValueError):
            knapsack([(1, 1)], -1)
        with self.assertRaises(ValueError):
            knapsack([(-1, 1)], 5)

    def test_random_against_brute_force(self):
        rng = random.Random(75)
        for _ in range(80):
            items = [(rng.randrange(1, 15), rng.randrange(0, 30)) for _ in range(rng.randrange(0, 11))]
            capacity = rng.randrange(0, 40)
            result = knapsack(items, capacity)
            self.assertEqual(result[0], brute_knapsack(items, capacity), (items, capacity))
            self.check(items, capacity, result)

    def test_pseudo_polynomial_size(self):
        rng = random.Random(76)
        items = [(rng.randrange(1, 100), rng.randrange(1, 100)) for _ in range(100)]
        result = knapsack(items, 1000)  # 2^100 通りの全探索は不可能だが、n × W = 10 万マスの表なら一瞬
        self.check(items, 1000, result)


# ---------------------------------------------------------------------------
# 演習5: バックトラッキング
# ---------------------------------------------------------------------------

class TestExercise5Backtracking(unittest.TestCase):
    def test_n_queens_known_counts(self):
        known = {0: 1, 1: 1, 2: 0, 3: 0, 4: 2, 5: 10, 6: 4, 7: 40, 8: 92, 9: 352, 10: 724}
        for n, count in known.items():
            self.assertEqual(n_queens(n), count, f"n={n}")
        with self.assertRaises(ValueError):
            n_queens(-1)

    def test_subset_sum_examples(self):
        nums = [8, 6, 7, 5, 3, 10, 9]
        chosen = subset_sum(nums, 15)
        self.assertIsNotNone(chosen)
        self.assertEqual(sum(nums[i] for i in chosen), 15)
        self.assertEqual(chosen, sorted(set(chosen)))
        self.assertEqual(subset_sum(nums, 0), [])
        self.assertIsNone(subset_sum([4, 6, 10], 7))
        self.assertIsNone(subset_sum([], 1))

    def test_subset_sum_validation(self):
        with self.assertRaises(ValueError):
            subset_sum([3, 0, 2], 5)
        with self.assertRaises(ValueError):
            subset_sum([3, -1], 2)
        with self.assertRaises(ValueError):
            subset_sum([3], -1)

    def test_subset_sum_against_brute_force(self):
        rng = random.Random(77)
        for _ in range(100):
            nums = [rng.randrange(1, 20) for _ in range(rng.randrange(0, 11))]
            target = rng.randrange(0, 60)
            possible = any(
                sum(c) == target for r in range(len(nums) + 1) for c in itertools.combinations(nums, r)
            )
            chosen = subset_sum(nums, target)
            if possible:
                self.assertIsNotNone(chosen, (nums, target))
                self.assertEqual(sum(nums[i] for i in chosen), target)
            else:
                self.assertIsNone(chosen, (nums, target))

    def test_subset_sum_pruning(self):
        # 2^22 ≒ 420 万通り。枝刈りなしの全探索では数秒以上かかるが、
        # 「残りを全部足しても届かない」「足すと超える」で刈り込めば一瞬で終わる
        nums = list(range(1, 23))
        total = sum(nums)
        start = time.perf_counter()
        self.assertEqual(subset_sum(nums, total), list(range(22)))
        self.assertIsNone(subset_sum(nums, total + 1))
        self.assertEqual(sum(nums[i] for i in subset_sum(nums, 1)), 1)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, f"{elapsed:.2f} 秒かかりました。枝刈りを入れましたか")


# ---------------------------------------------------------------------------
# 演習6: 乱択アルゴリズムと外部ソート
# ---------------------------------------------------------------------------

class TestExercise6Reservoir(unittest.TestCase):
    def test_small_stream_returns_all(self):
        self.assertEqual(reservoir_sample([1, 2, 3], 5, random.Random(0)), [1, 2, 3])
        self.assertEqual(reservoir_sample([], 3, random.Random(0)), [])
        self.assertEqual(reservoir_sample(range(10), 0, random.Random(0)), [])
        with self.assertRaises(ValueError):
            reservoir_sample([1], -1, random.Random(0))

    def test_follows_algorithm_r_exactly(self):
        # 決められた値を順に返す「台本どおりの乱数」を注入して、アルゴリズム R の手順を確かめる
        class ScriptedRNG:
            def __init__(self, answers):
                self.answers = list(answers)
                self.calls = []

            def randrange(self, n):
                self.calls.append(n)
                return self.answers.pop(0)

            def randint(self, a, b):  # randint(0, i) は randrange(i + 1) と同じ意味
                assert a == 0
                return self.randrange(b + 1)

        rng = ScriptedRNG([0, 4, 2, 5, 1, 8, 0])
        self.assertEqual(reservoir_sample(range(10), 3, rng), [9, 7, 5])
        self.assertEqual(rng.calls, [4, 5, 6, 7, 8, 9, 10], "i 番目（0 始まり, i >= k）の要素で rng.randrange(i + 1) を 1 回呼ぶ")

    def test_single_pass_over_generator(self):
        gen = (x * x for x in range(10_000))
        sample = reservoir_sample(gen, 10, random.Random(1))
        self.assertEqual(len(sample), 10)
        self.assertEqual(len(set(sample)), 10)
        self.assertTrue(all(math.isqrt(x) ** 2 == x for x in sample))

    def test_uniformity(self):
        rng = random.Random(80)
        counts = [0] * 10
        trials = 20_000
        for _ in range(trials):
            for x in reservoir_sample(range(10), 3, rng):
                counts[x] += 1
        expected = trials * 3 / 10  # 各要素が選ばれる確率は 3/10
        for x, c in enumerate(counts):
            self.assertLess(abs(c - expected), expected * 0.05, f"要素 {x} が選ばれた回数 {c} が偏っています")


class TestExercise6KWayMerge(unittest.TestCase):
    def test_example(self):
        self.assertEqual(list(kway_merge([[1, 4, 7], [2, 5, 8], [3, 6, 9]])), list(range(1, 10)))
        self.assertEqual(list(kway_merge([])), [])
        self.assertEqual(list(kway_merge([[], [1], []])), [1])

    def test_random_against_sorted(self):
        rng = random.Random(81)
        for _ in range(50):
            runs = [sorted(rng.randrange(100) for _ in range(rng.randrange(0, 30))) for _ in range(rng.randrange(0, 8))]
            self.assertEqual(list(kway_merge(runs)), sorted(itertools.chain.from_iterable(runs)))

    def test_is_lazy(self):
        def guarded(start, limit=1000):
            # 事実上「無限」の入力。必要以上に読むと（先に全部 list にするなど）例外にする
            for i in range(limit):
                yield start + 2 * i
            raise AssertionError("入力を必要以上に読んでいます（遅延評価になっていません）")

        merged = kway_merge([guarded(0), guarded(1)])
        self.assertEqual(list(itertools.islice(merged, 7)), [0, 1, 2, 3, 4, 5, 6])

    def test_stable_by_input_order_with_key(self):
        a = [(1, "a1"), (2, "a2")]
        b = [(1, "b1"), (2, "b2")]
        got = list(kway_merge([a, b], key=lambda t: t[0]))
        self.assertEqual(got, [(1, "a1"), (1, "b1"), (2, "a2"), (2, "b2")])

    def test_does_not_compare_elements_with_equal_keys(self):
        class NoCompare:
            def __init__(self, k):
                self.k = k

        runs = [[NoCompare(1), NoCompare(3)], [NoCompare(1), NoCompare(2)]]
        got = [x.k for x in kway_merge(runs, key=lambda x: x.k)]
        self.assertEqual(got, [1, 1, 2, 3])


class TestExercise6ExternalSort(unittest.TestCase):
    def test_sorts_with_small_memory_and_cleans_up(self):
        rng = random.Random(82)
        lines = ["".join(rng.choice("あいうabc123") for _ in range(rng.randrange(0, 12))) for _ in range(5000)]
        with tempfile.TemporaryDirectory() as tmp:
            it = external_sort(iter(lines), 500, tmp)
            first = next(it)
            runs = os.listdir(tmp)
            self.assertGreaterEqual(len(runs), 10, "500 行ずつなら 10 個以上のランを一時ファイルに書き出すはず")
            result = [first] + list(it)
            self.assertEqual(result, sorted(lines))
            self.assertEqual(os.listdir(tmp), [], "最後まで読んだら一時ファイルを削除すること")

    def test_empty_and_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(list(external_sort([], 10, tmp)), [])
            self.assertEqual(list(external_sort(["b", "a", ""], 10, tmp)), ["", "a", "b"])
            self.assertEqual(list(external_sort(["b", "a", "c"], 1, tmp)), ["a", "b", "c"])

    def test_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                list(external_sort(["a"], 0, tmp))
            with self.assertRaises(ValueError):
                list(external_sort(["ok", "bad\nline"], 10, tmp))
            self.assertEqual(os.listdir(tmp), [], "エラーのときも一時ファイルを残さないこと")


if __name__ == "__main__":
    unittest.main()
