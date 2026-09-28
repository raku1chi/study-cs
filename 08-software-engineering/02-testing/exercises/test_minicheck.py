"""8.2 演習1 — ミニ・プロパティベーステスト（minicheck）のテスト

実行: python3 tools/check.py 8.2   （またはこのディレクトリで python3 -m unittest -v test_minicheck）
"""
import math
import random
import unittest

from minicheck import CheckResult, Gen, check, for_all, integers, lists, one_of, text, tuples


def sample(gen, n=500, seed=0):
    rng = random.Random(seed)
    return [gen.generate(rng) for _ in range(n)]


# 反例探しの題材: 数字 1 桁しか想定していないランレングス符号化（バグ入り）
def rle_encode(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        j = i
        while j < len(s) and s[j] == s[i]:
            j += 1
        out.append(f"{j - i}{s[i]}")
        i = j
    return "".join(out)


def rle_decode(encoded: str) -> str:
    # バグ: 「回数は 1 桁」と決めつけている（10 回以上の連続で壊れる）
    return "".join(encoded[k + 1] * int(encoded[k]) for k in range(0, len(encoded), 2))


class TestIntegers(unittest.TestCase):
    def test_values_are_in_range(self):
        values = sample(integers(-5, 5))
        self.assertTrue(all(-5 <= v <= 5 for v in values))
        self.assertTrue(all(type(v) is int for v in values))
        self.assertEqual(set(values), set(range(-5, 6)), "範囲内のすべての値が現れるはず")

    def test_same_seed_same_values(self):
        self.assertEqual(sample(integers(0, 10**9), seed=7), sample(integers(0, 10**9), seed=7))

    def test_uses_only_the_given_rng(self):
        random.seed(12345)
        state = random.getstate()
        sample(integers(0, 100), n=50)
        self.assertEqual(random.getstate(), state, "グローバルな random を使わず、引数の rng だけを使うこと")

    def test_boundary_values_are_generated(self):
        values = set(sample(integers(-10**9, 10**9), n=1000))
        for boundary in (-10**9, 0, 10**9):
            self.assertIn(boundary, values, f"境界値 {boundary} が 1000 回で一度も生成されていません")
        positive = set(sample(integers(5, 10**9), n=1000))
        self.assertIn(5, positive)
        self.assertIn(10**9, positive)

    def test_contains(self):
        g = integers(0, 10)
        self.assertTrue(g.contains(0))
        self.assertTrue(g.contains(10))
        self.assertFalse(g.contains(11))
        self.assertFalse(g.contains(-1))
        self.assertFalse(g.contains(True), "bool は整数として扱わない")
        self.assertFalse(g.contains("3"))

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            integers(10, 0)

    def test_shrink_toward_zero(self):
        self.assertEqual(list(integers(-100, 100).shrink(10)), [0, 5, 8, 9])
        self.assertEqual(list(integers(-100, 100).shrink(-10)), [0, -5, -8, -9])
        self.assertEqual(list(integers(-100, 100).shrink(1)), [0])
        self.assertEqual(list(integers(-100, 100).shrink(0)), [])

    def test_shrink_toward_nearest_bound_when_zero_is_out_of_range(self):
        self.assertEqual(list(integers(5, 100).shrink(37)), [5, 21, 29, 33, 35, 36])
        self.assertEqual(list(integers(-100, -3).shrink(-50)), [-3, -27, -39, -45, -48, -49])
        self.assertEqual(list(integers(5, 100).shrink(5)), [])


class TestCollections(unittest.TestCase):
    def test_lists_sizes_and_elements(self):
        values = sample(lists(integers(0, 3), min_size=2, max_size=4))
        self.assertTrue(all(isinstance(v, list) and 2 <= len(v) <= 4 for v in values))
        self.assertTrue(all(0 <= x <= 3 for v in values for x in v))
        self.assertEqual({len(v) for v in values}, {2, 3, 4})

    def test_lists_invalid_sizes(self):
        for lo, hi in [(-1, 3), (4, 3)]:
            with self.assertRaises(ValueError):
                lists(integers(0, 1), min_size=lo, max_size=hi)

    def test_lists_shrink_order(self):
        self.assertEqual(
            list(lists(integers(0, 10)).shrink([3, 1])),
            [[], [1], [3], [0, 1], [2, 1], [3, 0]],
            "削除（大きな塊から）→ 要素の縮小、の順",
        )

    def test_lists_shrink_respects_min_size(self):
        self.assertEqual(
            list(lists(integers(0, 10), min_size=1).shrink([3, 1])),
            [[1], [3], [0, 1], [2, 1], [3, 0]],
        )
        self.assertEqual(list(lists(integers(0, 10), min_size=2).shrink([0, 0])), [])

    def test_lists_shrink_chunk_sizes(self):
        candidates = list(lists(integers(0, 10)).shrink([0, 0, 0, 0, 0]))
        lengths = [len(c) for c in candidates]
        # k = 5, 2, 1 → 長さ 0 が 1 個、長さ 3 が 4 個、長さ 4 が 5 個
        self.assertEqual(lengths, [0] + [3] * 4 + [4] * 5)

    def test_lists_contains(self):
        g = lists(integers(0, 5), max_size=3)
        self.assertTrue(g.contains([0, 5]))
        self.assertFalse(g.contains([0, 6]))
        self.assertFalse(g.contains([1, 1, 1, 1]))
        self.assertFalse(g.contains((1, 2)))

    def test_text_generation(self):
        values = sample(text("ab", min_size=1, max_size=3))
        self.assertTrue(all(isinstance(s, str) and 1 <= len(s) <= 3 and set(s) <= {"a", "b"} for s in values))
        self.assertEqual({len(s) for s in values}, {1, 2, 3})

    def test_text_shrink(self):
        self.assertEqual(list(text("abc").shrink("ba")), ["", "a", "b", "aa"])
        self.assertEqual(list(text("abc", min_size=2).shrink("ca")), ["aa", "ba"])

    def test_text_contains_and_validation(self):
        g = text("xyz", max_size=2)
        self.assertTrue(g.contains("zy"))
        self.assertFalse(g.contains("a"))
        self.assertFalse(g.contains("xyz"))
        with self.assertRaises(ValueError):
            text("")

    def test_tuples(self):
        g = tuples(integers(0, 10), text("ab", max_size=2))
        for value in sample(g):
            self.assertIsInstance(value, tuple)
            self.assertTrue(g.contains(value))
        self.assertFalse(g.contains((1,)))
        self.assertEqual(list(tuples(integers(0, 10), integers(0, 10)).shrink((3, 0))), [(0, 0), (2, 0)])

    def test_one_of(self):
        g = one_of(integers(0, 9), text("xy", min_size=1, max_size=2))
        values = sample(g)
        self.assertTrue(any(isinstance(v, int) for v in values))
        self.assertTrue(any(isinstance(v, str) for v in values))
        self.assertTrue(all(g.contains(v) for v in values))
        self.assertEqual(list(g.shrink(5)), [0, 3, 4])
        self.assertEqual(list(g.shrink("yx")), ["x", "y", "xx"])
        self.assertEqual(list(g.shrink(3.5)), [], "どの生成器にも含まれない値は縮めない")
        with self.assertRaises(ValueError):
            one_of()

    def test_gen_repr_is_available(self):
        self.assertIsInstance(integers(0, 1), Gen)


class TestForAll(unittest.TestCase):
    def test_true_property_passes(self):
        result = for_all(lambda xs: list(reversed(list(reversed(xs)))) == xs, lists(integers(-50, 50)))
        self.assertIsInstance(result, CheckResult)
        self.assertEqual((result.ok, result.runs, result.counterexample, result.original), (True, 100, None, None))

    def test_runs_parameter_controls_number_of_calls(self):
        calls = []
        result = for_all(lambda x: calls.append(x) or True, integers(0, 10), runs=7)
        self.assertTrue(result.ok)
        self.assertEqual(len(calls), 7)
        self.assertEqual(result.runs, 7)

    def test_none_return_counts_as_success(self):
        def prop(x):
            assert x >= 0

        self.assertTrue(for_all(prop, integers(0, 10)).ok)

    def test_shrinks_integer_to_boundary(self):
        result = for_all(lambda x: x < 1000, integers(0, 10**6))
        self.assertFalse(result.ok)
        self.assertEqual(result.counterexample, (1000,))

    def test_shrinks_list_to_minimal_counterexample(self):
        result = for_all(lambda xs: all(x < 10 for x in xs), lists(integers(0, 100)))
        self.assertEqual(result.counterexample, ([10],))

    def test_minimal_unsorted_list(self):
        for seed in range(5):
            result = for_all(lambda xs: sorted(xs) == xs, lists(integers(0, 100)), seed=seed)
            self.assertEqual(result.counterexample, ([1, 0],), f"seed={seed}")

    def test_multiple_arguments(self):
        result = for_all(lambda a, b: not (a >= 10 and b >= 20), integers(0, 100), integers(0, 100))
        self.assertEqual(result.counterexample, (10, 20))

    def test_exception_is_a_failure(self):
        result = for_all(lambda x: math.sqrt(x - 10) >= 0, integers(0, 100))
        self.assertFalse(result.ok)
        self.assertEqual(result.counterexample, (0,))
        self.assertIn("ValueError", result.error)

    def test_finds_round_trip_bug(self):
        result = for_all(lambda s: rle_decode(rle_encode(s)) == s, text("ab", max_size=40), runs=1000)
        self.assertFalse(result.ok, "10 回以上同じ文字が続く文字列で、往復（round trip）が壊れるはず")
        (s,) = result.counterexample
        self.assertEqual(len(s), 10, f"最小の反例は同じ文字 10 個のはず: {s!r}")
        self.assertEqual(len(set(s)), 1, f"最小の反例は同じ文字 10 個のはず: {s!r}")

    def test_original_and_shrink_steps_are_recorded(self):
        prop = lambda xs: all(x < 10 for x in xs)  # noqa: E731
        result = for_all(prop, lists(integers(0, 100)))
        self.assertIsNotNone(result.original)
        self.assertFalse(prop(*result.original), "original は縮小前の反例（これも性質を破る）")
        if result.original != result.counterexample:
            self.assertGreater(result.shrinks, 0)

    def test_stops_at_first_failure(self):
        calls = []

        def prop(x):
            calls.append(x)
            return x < 1000

        result = for_all(prop, integers(0, 10**6), max_shrinks=0)
        self.assertEqual(len(calls), result.runs, "失敗が見つかったら、それ以上は試行しない")

    def test_max_shrinks_zero_keeps_original(self):
        result = for_all(lambda x: x < 1000, integers(0, 10**6), max_shrinks=0)
        self.assertEqual(result.counterexample, result.original)
        self.assertEqual(result.shrinks, 0)

    def test_deterministic_for_same_seed(self):
        a = for_all(lambda xs: sum(xs) < 150, lists(integers(0, 100)), seed=42)
        b = for_all(lambda xs: sum(xs) < 150, lists(integers(0, 100)), seed=42)
        self.assertEqual(a, b)

    def test_check_raises_assertion_error_with_counterexample(self):
        with self.assertRaises(AssertionError) as ctx:
            check(lambda xs: sorted(xs) == xs, lists(integers(0, 100)))
        self.assertIn("[1, 0]", str(ctx.exception))

    def test_check_passes_silently(self):
        self.assertIsNone(check(lambda x: x * 0 == 0, integers(-10, 10)))


if __name__ == "__main__":
    unittest.main()
