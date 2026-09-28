"""13.5 育成・評価・キャリアラダー — テスト（評価のキャリブレーション）

実行: python3 tools/check.py 13.5   （またはこのディレクトリで python3 -m unittest -v test_calibration）
"""
import math
import unittest

from calibration import (
    ManagerStats,
    Rating,
    distribution_distance,
    leniency_flags,
    manager_stats,
    normalize_within_manager,
    rank_changes,
)

# 本文の例: 4 人のマネージャーの評価（5 段階）
BOOK = {
    "佐藤": [5, 4, 5, 4, 4, 5],
    "鈴木": [3, 4, 3, 3, 2, 4, 3],
    "高橋": [2, 3, 2, 2, 3, 2],
    "田中": [4, 3, 3, 4, 3],
}


def book_ratings():
    return [Rating(f"{m}チーム{i + 1}", m, s) for m, scores in BOOK.items() for i, s in enumerate(scores)]


class TestExercise1Stats(unittest.TestCase):
    def test_docstring_example(self):
        rs = [Rating("a", "M1", 4), Rating("b", "M1", 2), Rating("c", "M2", 3)]
        self.assertEqual(
            manager_stats(rs),
            {"M1": ManagerStats(n=2, mean=3.0, sd=1.0), "M2": ManagerStats(n=1, mean=3.0, sd=0.0)},
        )

    def test_book_example(self):
        got = manager_stats(book_ratings())
        self.assertEqual(list(got), ["佐藤", "田中", "鈴木", "高橋"], "評価者名の昇順")
        self.assertEqual(got["佐藤"].n, 6)
        self.assertAlmostEqual(got["佐藤"].mean, 4.5)
        self.assertAlmostEqual(got["佐藤"].sd, 0.5)
        self.assertAlmostEqual(got["鈴木"].mean, 22 / 7)
        self.assertAlmostEqual(got["高橋"].sd, math.sqrt(2) / 3, msg="母標準偏差（n で割る）")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            manager_stats([])
        with self.assertRaises(ValueError):
            manager_stats([Rating("a", "M1", 3), Rating("a", "M2", 4)])

    def test_distribution_distance_docstring(self):
        rs = [Rating("a", "M1", 5), Rating("b", "M1", 5), Rating("c", "M2", 3), Rating("d", "M2", 5)]
        got = distribution_distance(rs, scale=[1, 2, 3, 4, 5])
        self.assertAlmostEqual(got["M1"], 0.5)
        self.assertAlmostEqual(got["M2"], 0.5)

    def test_distribution_distance_extremes(self):
        same = [Rating("a", "M1", 3), Rating("b", "M1", 4), Rating("c", "M2", 3), Rating("d", "M2", 4)]
        self.assertEqual(distribution_distance(same, scale=[1, 2, 3, 4, 5]), {"M1": 0.0, "M2": 0.0})
        apart = [Rating("a", "M1", 1), Rating("b", "M2", 5)]
        self.assertEqual(distribution_distance(apart, scale=[1, 2, 3, 4, 5]), {"M1": 1.0, "M2": 1.0})

    def test_distribution_distance_excludes_self(self):
        got = distribution_distance(book_ratings(), scale=[1, 2, 3, 4, 5])
        # 佐藤: 自分 {4: 1/2, 5: 1/2}、他の 18 人 {2: 5, 3: 9, 4: 4} → 0.5 * (5/18 + 9/18 + |1/2 - 4/18| + 1/2)
        expected = 0.5 * (5 / 18 + 9 / 18 + abs(0.5 - 4 / 18) + 0.5)
        self.assertAlmostEqual(got["佐藤"], expected)
        for v in got.values():
            self.assertTrue(0.0 <= v <= 1.0)

    def test_distribution_distance_invalid(self):
        with self.assertRaises(ValueError):
            distribution_distance([Rating("a", "M1", 3), Rating("b", "M1", 4)], scale=[1, 2, 3, 4, 5])
        with self.assertRaises(ValueError):
            distribution_distance([Rating("a", "M1", 3), Rating("b", "M2", 6)], scale=[1, 2, 3, 4, 5])


class TestExercise2Leniency(unittest.TestCase):
    def test_book_example(self):
        got = leniency_flags(book_ratings(), z_threshold=2.0)
        self.assertEqual({m: label for m, (_, label) in got.items()},
                         {"佐藤": "lenient", "田中": "ok", "鈴木": "ok", "高橋": "severe"})
        self.assertAlmostEqual(got["佐藤"][0], 5.41, places=2)
        self.assertAlmostEqual(got["高橋"][0], -4.00, places=2)

    def test_formula(self):
        rs = [Rating("a", "M1", 4), Rating("b", "M1", 4), Rating("c", "M1", 4), Rating("d", "M1", 4),
              Rating("e", "M2", 2), Rating("f", "M2", 4)]
        got = leniency_flags(rs)
        # M1: 平均 4、他（M2）の平均 3・標準偏差 1 → z = (4 - 3) / (1 / √4) = 2
        self.assertAlmostEqual(got["M1"][0], 2.0)
        self.assertEqual(got["M1"][1], "lenient", "z がしきい値ちょうどなら lenient")
        # M2: 平均 3、他（M1）の標準偏差 0 → 差が負なので -inf
        self.assertEqual(got["M2"], (-math.inf, "severe"))

    def test_same_distribution_is_ok(self):
        rs = [Rating("a", "M1", 3), Rating("b", "M2", 3), Rating("c", "M3", 3)]
        self.assertEqual(leniency_flags(rs), {"M1": (0.0, "ok"), "M2": (0.0, "ok"), "M3": (0.0, "ok")})

    def test_small_team_needs_bigger_gap(self):
        # 同じ平均の差でも、評価した人数が少ないほど z は小さい（偶然で説明できる）
        others = [Rating(f"o{i}", "他", s) for i, s in enumerate([2, 3, 4] * 10)]
        small = others + [Rating("s1", "小", 4), Rating("s2", "小", 3.5)]
        large = others + [Rating(f"l{i}", "大", s) for i, s in enumerate([4, 3.5] * 10)]
        z_small = leniency_flags(small)["小"][0]
        z_large = leniency_flags(large)["大"][0]
        self.assertGreater(z_large, z_small)
        self.assertEqual(leniency_flags(small)["小"][1], "ok")
        self.assertEqual(leniency_flags(large)["大"][1], "lenient")

    def test_threshold_changes_labels(self):
        got = leniency_flags(book_ratings(), z_threshold=6.0)
        self.assertTrue(all(label == "ok" for _, label in got.values()))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            leniency_flags([Rating("a", "M1", 3)])
        with self.assertRaises(ValueError):
            leniency_flags(book_ratings(), z_threshold=0)


class TestExercise2Normalization(unittest.TestCase):
    def test_docstring_example(self):
        rs = [Rating("a", "M1", 5), Rating("b", "M1", 3), Rating("c", "M2", 3), Rating("d", "M2", 1)]
        got = normalize_within_manager(rs)
        self.assertAlmostEqual(got["a"], 3 + math.sqrt(2))
        self.assertAlmostEqual(got["b"], 3 - math.sqrt(2))
        self.assertAlmostEqual(got["c"], 3 + math.sqrt(2), msg="M2 の最上位は M1 の最上位と同じ値になる")
        self.assertAlmostEqual(got["d"], 3 - math.sqrt(2))

    def test_uniform_team_maps_to_overall_mean(self):
        rs = [Rating("a", "M1", 4), Rating("b", "M1", 4), Rating("c", "M2", 2), Rating("d", "M2", 4)]
        got = normalize_within_manager(rs)
        self.assertAlmostEqual(got["a"], 3.5)
        self.assertAlmostEqual(got["b"], 3.5)

    def test_normalization_preserves_overall_mean(self):
        rs = book_ratings()
        got = normalize_within_manager(rs)
        overall = sum(r.score for r in rs) / len(rs)
        self.assertAlmostEqual(sum(got.values()) / len(got), overall)

    def test_book_example_extreme_shift(self):
        # 本文の例: 標準偏差の小さいチームでは、標準化の影響が極端になる
        got = normalize_within_manager(book_ratings())
        self.assertAlmostEqual(got["佐藤チーム2"], 2.39, places=2)
        self.assertAlmostEqual(got["高橋チーム2"], 4.67, places=2)

    def test_rank_changes_docstring(self):
        rs = [Rating("a", "M1", 5), Rating("b", "M1", 3), Rating("c", "M2", 3), Rating("d", "M2", 1)]
        self.assertEqual(rank_changes(rs), {"a": (1, 1), "b": (2, 3), "c": (3, 2), "d": (4, 4)})

    def test_rank_changes_book_example(self):
        got = rank_changes(book_ratings())
        self.assertEqual(len(got), 24)
        self.assertEqual(list(got), sorted(got))
        self.assertEqual(got["佐藤チーム2"], (4, 21))
        self.assertEqual(got["高橋チーム2"], (18, 1))
        self.assertEqual(sorted(after for _, after in got.values()), list(range(1, 25)))


if __name__ == "__main__":
    unittest.main()
