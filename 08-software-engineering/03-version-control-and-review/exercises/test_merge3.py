"""8.3 演習2 — 3 方向マージ（diff3）のテスト

実行: python3 tools/check.py 8.3   （またはこのディレクトリで python3 -m unittest -v test_merge3）

期待値は、本物の git merge-file -p --diff3（Git 2.43）の出力と一致することを確かめてあります。
"""
import random
import unittest

from merge3 import MergeResult, lcs_pairs, merge3

BASE = [
    "def total(items):",
    "    s = 0",
    "    for x in items:",
    "        s += x",
    "    return s",
]


def replace(lines, index, *new):
    return lines[:index] + list(new) + lines[index + 1:]


def lcs_length(a, b):
    """テスト用の参照実装（長さだけを求める）。"""
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


class TestLcs(unittest.TestCase):
    def test_example(self):
        self.assertEqual(lcs_pairs(["a", "b", "c", "d"], ["a", "c", "d", "e"]), [(0, 0), (2, 1), (3, 2)])

    def test_empty_and_identical(self):
        self.assertEqual(lcs_pairs([], ["a"]), [])
        self.assertEqual(lcs_pairs(["a"], []), [])
        self.assertEqual(lcs_pairs(["x", "y"], ["x", "y"]), [(0, 0), (1, 1)])
        self.assertEqual(lcs_pairs(["x"], ["y"]), [])

    def test_tie_breaking_skips_a_first(self):
        # LCS は "a" でも "b" でも長さ 1。同点では a 側を先に進めるので、b の "b" と a の "b" が対応する
        self.assertEqual(lcs_pairs(["a", "b"], ["b", "a"]), [(1, 0)])

    def test_pairs_are_valid_and_maximal_on_random_inputs(self):
        rng = random.Random(83)
        for _ in range(300):
            a = [rng.choice("abcd") for _ in range(rng.randrange(0, 12))]
            b = [rng.choice("abcd") for _ in range(rng.randrange(0, 12))]
            pairs = lcs_pairs(a, b)
            self.assertEqual(len(pairs), lcs_length(a, b), (a, b))
            for (i1, j1), (i2, j2) in zip(pairs, pairs[1:]):
                self.assertTrue(i1 < i2 and j1 < j2, (a, b, pairs))
            self.assertTrue(all(a[i] == b[j] for i, j in pairs), (a, b, pairs))


class TestCleanMerges(unittest.TestCase):
    def test_no_changes(self):
        result = merge3(BASE, BASE, BASE)
        self.assertIsInstance(result, MergeResult)
        self.assertEqual((result.lines, result.conflicts, result.clean), (BASE, 0, True))

    def test_only_ours_changed(self):
        ours = replace(BASE, 1, "    s = 0.0")
        self.assertEqual(merge3(BASE, ours, BASE).lines, ours)

    def test_only_theirs_changed(self):
        theirs = replace(BASE, 4, "    return round(s, 2)")
        self.assertEqual(merge3(BASE, BASE, theirs).lines, theirs)

    def test_both_changed_different_places(self):
        ours = replace(BASE, 1, "    s = 0.0")
        theirs = replace(BASE, 4, "    return round(s, 2)")
        result = merge3(BASE, ours, theirs)
        self.assertTrue(result.clean)
        self.assertEqual(result.lines, [
            "def total(items):",
            "    s = 0.0",
            "    for x in items:",
            "        s += x",
            "    return round(s, 2)",
        ])

    def test_same_change_on_both_sides_is_not_a_conflict(self):
        ours = replace(BASE, 1, "    s = 0.0")
        self.assertEqual(merge3(BASE, ours, list(ours)).lines, ours)
        self.assertEqual(merge3(["a", "b", "c"], ["a", "c"], ["a", "c"]).lines, ["a", "c"], "両方が同じ行を削除")
        self.assertEqual(merge3(["a", "b"], ["a", "x", "b"], ["a", "x", "b"]).lines, ["a", "x", "b"], "両方が同じ挿入")

    def test_insert_at_top_and_delete_at_bottom(self):
        result = merge3(BASE, ["import math"] + BASE, BASE[:4])
        self.assertEqual(result.lines, ["import math"] + BASE[:4])
        self.assertTrue(result.clean)

    def test_delete_and_append_in_different_places(self):
        result = merge3(["a", "b", "c", "d"], ["a", "c", "d"], ["a", "b", "c", "d", "e"])
        self.assertEqual(result.lines, ["a", "c", "d", "e"])


class TestConflicts(unittest.TestCase):
    def test_same_line_changed_differently(self):
        ours = replace(BASE, 1, "    s = 0.0")
        theirs = replace(BASE, 1, "    s = Decimal(0)")
        result = merge3(BASE, ours, theirs)
        self.assertEqual(result.conflicts, 1)
        self.assertFalse(result.clean)
        self.assertEqual(result.lines, [
            "def total(items):",
            "<<<<<<< ours",
            "    s = 0.0",
            "||||||| base",
            "    s = 0",
            "=======",
            "    s = Decimal(0)",
            ">>>>>>> theirs",
            "    for x in items:",
            "        s += x",
            "    return s",
        ])

    def test_adjacent_changes_conflict(self):
        ours = replace(BASE, 1, "    s = 0.0")
        theirs = replace(BASE, 2, "    for x in sorted(items):")
        result = merge3(BASE, ours, theirs)
        self.assertEqual(result.conflicts, 1, "隣り合う行の変更も衝突になる（Git と同じ）")
        self.assertEqual(result.lines[1:9], [
            "<<<<<<< ours",
            "    s = 0.0",
            "    for x in items:",
            "||||||| base",
            "    s = 0",
            "    for x in items:",
            "=======",
            "    s = 0",
        ])

    def test_delete_versus_modify(self):
        ours = BASE[:3] + BASE[4:]  # s += x を削除
        theirs = replace(BASE, 3, "        s += x * 2")
        result = merge3(BASE, ours, theirs)
        self.assertEqual(result.conflicts, 1)
        start = result.lines.index("<<<<<<< ours")
        self.assertEqual(result.lines[start:start + 6], [
            "<<<<<<< ours",
            "||||||| base",
            "        s += x",
            "=======",
            "        s += x * 2",
            ">>>>>>> theirs",
        ])

    def test_both_append_different_lines(self):
        result = merge3(BASE, BASE + ["# ours"], BASE + ["# theirs"])
        self.assertEqual(result.lines, BASE + [
            "<<<<<<< ours", "# ours", "||||||| base", "=======", "# theirs", ">>>>>>> theirs",
        ])

    def test_add_add_with_empty_base(self):
        result = merge3([], ["a", "b"], ["a", "c"])
        self.assertEqual(result.lines, ["<<<<<<< ours", "a", "b", "||||||| base", "=======", "a", "c", ">>>>>>> theirs"])

    def test_two_separate_conflicts(self):
        base = ["1", "2", "3", "4", "5", "6", "7"]
        result = merge3(base, ["1", "X", "3", "4", "5", "Y", "7"], ["1", "P", "3", "4", "5", "Q", "7"])
        self.assertEqual(result.conflicts, 2)
        self.assertEqual(result.lines.count("======="), 2)
        self.assertEqual(result.lines[0], "1")
        self.assertEqual(result.lines[-1], "7")
        self.assertIn("4", result.lines)

    def test_custom_labels(self):
        ours = replace(BASE, 1, "    s = 0.0")
        theirs = replace(BASE, 1, "    s = Decimal(0)")
        result = merge3(BASE, ours, theirs, labels=("HEAD", "merged common ancestors", "feature/decimal"))
        self.assertIn("<<<<<<< HEAD", result.lines)
        self.assertIn("||||||| merged common ancestors", result.lines)
        self.assertIn(">>>>>>> feature/decimal", result.lines)
        self.assertIn("=======", result.lines)


if __name__ == "__main__":
    unittest.main()
