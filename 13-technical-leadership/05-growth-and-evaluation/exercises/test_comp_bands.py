"""13.5 育成・評価・キャリアラダー — テスト（給与レンジと昇給予算）

実行: python3 tools/check.py 13.5   （またはこのディレクトリで python3 -m unittest -v test_comp_bands）
"""
import unittest

from comp_bands import (
    Adjustment,
    Band,
    Employee,
    band_overlap,
    budget_summary,
    build_bands,
    compa_ratio,
    merit_adjustments,
    out_of_band,
    range_penetration,
)

BOOK_MATRIX = {
    "期待を上回る": [0.08, 0.06, 0.04],
    "期待通り": [0.05, 0.03, 0.02],
    "期待を下回る": [0.00, 0.00, 0.00],
}


def book_bands():
    return build_bands(500, ["L1", "L2", "L3", "L4"], progression=0.2, spread=[0.4, 0.4, 0.5, 0.5])


def book_staff():
    return [
        Employee("A", "L2", 520, "期待を上回る"),
        Employee("B", "L2", 690, "期待通り"),
        Employee("C", "L3", 540, "期待通り"),
        Employee("D", "L3", 700, "期待を下回る"),
        Employee("E", "L4", 1100, "期待通り"),
    ]


class TestExercise3Bands(unittest.TestCase):
    def test_docstring_example(self):
        bands = build_bands(500, ["L1", "L2"], progression=0.2, spread=0.5)
        self.assertEqual([b.level for b in bands], ["L1", "L2"])
        for b, (lo, mid, hi) in zip(bands, [(400, 500, 600), (480, 600, 720)]):
            self.assertAlmostEqual(b.minimum, lo)
            self.assertAlmostEqual(b.midpoint, mid)
            self.assertAlmostEqual(b.maximum, hi)

    def test_definitions_hold(self):
        for b, s in zip(book_bands(), [0.4, 0.4, 0.5, 0.5]):
            self.assertAlmostEqual((b.minimum + b.maximum) / 2, b.midpoint, msg="中央値はレンジの真ん中")
            self.assertAlmostEqual((b.maximum - b.minimum) / b.minimum, s, msg="レンジの幅の定義")

    def test_book_example_values(self):
        bands = book_bands()
        self.assertAlmostEqual(bands[3].midpoint, 864)
        self.assertAlmostEqual(bands[0].minimum, 1000 / 2.4)
        self.assertAlmostEqual(bands[3].maximum, 1036.8)

    def test_per_level_progression(self):
        bands = build_bands(100, ["a", "b", "c"], progression=[0.1, 0.5], spread=0.0)
        self.assertAlmostEqual(bands[1].midpoint, 110)
        self.assertAlmostEqual(bands[2].midpoint, 165)
        self.assertAlmostEqual(bands[2].minimum, 165, msg="spread 0 なら下限 = 中央値 = 上限")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            build_bands(0, ["a"], 0.1, 0.5)
        with self.assertRaises(ValueError):
            build_bands(100, [], 0.1, 0.5)
        with self.assertRaises(ValueError):
            build_bands(100, ["a", "a"], 0.1, 0.5)
        with self.assertRaises(ValueError):
            build_bands(100, ["a", "b", "c"], [0.1], 0.5)
        with self.assertRaises(ValueError):
            build_bands(100, ["a", "b"], 0.1, [0.5])
        with self.assertRaises(ValueError):
            build_bands(100, ["a", "b"], 0.0, 0.5)
        with self.assertRaises(ValueError):
            build_bands(100, ["a", "b"], 0.1, -0.1)

    def test_overlap(self):
        self.assertAlmostEqual(band_overlap(Band("L1", 400, 500, 600), Band("L2", 480, 600, 720)), 0.6)
        bands = book_bands()
        self.assertAlmostEqual(band_overlap(bands[0], bands[1]), 0.5)
        self.assertEqual(band_overlap(Band("L1", 100, 150, 200), Band("L2", 250, 300, 350)), 0.0, "重ならない")
        with self.assertRaises(ValueError):
            band_overlap(Band("L1", 100, 100, 100), Band("L2", 90, 100, 110))


class TestExercise3Position(unittest.TestCase):
    def test_compa_ratio_and_penetration(self):
        band = Band("L2", 480, 600, 720)
        self.assertAlmostEqual(compa_ratio(540, band), 0.9)
        self.assertAlmostEqual(compa_ratio(600, band), 1.0)
        self.assertAlmostEqual(range_penetration(540, band), 0.25)
        self.assertAlmostEqual(range_penetration(480, band), 0.0)
        self.assertAlmostEqual(range_penetration(720, band), 1.0)
        self.assertLess(range_penetration(450, band), 0.0)
        self.assertGreater(range_penetration(800, band), 1.0)
        with self.assertRaises(ValueError):
            range_penetration(100, Band("x", 100, 100, 100))

    def test_out_of_band(self):
        bands = [Band("L2", 480, 600, 720)]
        staff = [Employee("A", "L2", 450, "B"), Employee("B", "L2", 600, "B"),
                 Employee("C", "L2", 480, "B"), Employee("D", "L2", 750, "B"), Employee("E", "L2", 720, "B")]
        self.assertEqual(out_of_band(staff, bands), [("A", "below", 30), ("D", "above", 30)])

    def test_out_of_band_book_example(self):
        got = out_of_band(book_staff(), book_bands())
        self.assertEqual([(n, k) for n, k, _ in got], [("C", "below"), ("E", "above")])
        self.assertAlmostEqual(got[0][2], 36.0)
        self.assertAlmostEqual(got[1][2], 63.2)

    def test_unknown_level(self):
        with self.assertRaises(ValueError):
            out_of_band([Employee("A", "L9", 500, "B")], book_bands())


class TestExercise4Merit(unittest.TestCase):
    def test_book_example(self):
        got = merit_adjustments(book_staff(), book_bands(), BOOK_MATRIX)
        by_name = {a.name: a for a in got}
        self.assertEqual([a.name for a in got], ["A", "B", "C", "D", "E"])
        # A: コンパレシオ 0.87 → ゾーン 0 → 8%
        self.assertAlmostEqual(by_name["A"].merit, 41.6)
        self.assertAlmostEqual(by_name["A"].new_salary, 561.6)
        # B: 690 × 1.02 = 703.8 → 上限 700 で止め、3.8 を一時金に
        self.assertAlmostEqual(by_name["B"].merit, 13.8)
        self.assertAlmostEqual(by_name["B"].new_salary, 700.0)
        self.assertAlmostEqual(by_name["B"].lump_sum, 3.8)
        # C: 540 × 1.05 = 567 → 下限 576 まで 9 引き上げ
        self.assertAlmostEqual(by_name["C"].merit, 27.0)
        self.assertAlmostEqual(by_name["C"].catch_up, 9.0)
        self.assertAlmostEqual(by_name["C"].new_salary, 576.0)
        # D: 期待を下回る → 昇給なし
        self.assertEqual((by_name["D"].merit, by_name["D"].new_salary), (0.0, 700))
        # E: すでに上限超え → 基本給は据え置き、昇給分はすべて一時金
        self.assertAlmostEqual(by_name["E"].new_salary, 1100.0)
        self.assertAlmostEqual(by_name["E"].lump_sum, 22.0)

    def test_zone_boundaries(self):
        band = Band("L", 800, 1000, 1200)
        matrix = {"R": [0.10, 0.05, 0.01]}
        staff = [Employee("x", "L", 899, "R"), Employee("y", "L", 900, "R"),
                 Employee("z", "L", 1100, "R")]
        got = merit_adjustments(staff, [band], matrix)
        self.assertAlmostEqual(got[0].merit, 89.9, msg="0.899 はゾーン 0")
        self.assertAlmostEqual(got[1].merit, 45.0, msg="0.9 ちょうどはゾーン 1")
        self.assertAlmostEqual(got[2].merit, 11.0, msg="1.1 ちょうどはゾーン 2")

    def test_custom_zone_edges(self):
        band = Band("L", 800, 1000, 1200)
        got = merit_adjustments([Employee("x", "L", 1000, "R")], [band], {"R": [0.1, 0.02]}, zone_edges=[1.0])
        self.assertAlmostEqual(got[0].merit, 20.0)

    def test_invalid_inputs(self):
        band = Band("L", 800, 1000, 1200)
        with self.assertRaises(ValueError):
            merit_adjustments([Employee("x", "L", 1000, "Z")], [band], {"R": [0.1, 0.05, 0.0]})
        with self.assertRaises(ValueError):
            merit_adjustments([Employee("x", "M", 1000, "R")], [band], {"R": [0.1, 0.05, 0.0]})
        with self.assertRaises(ValueError):
            merit_adjustments([Employee("x", "L", 1000, "R")], [band], {"R": [0.1, 0.05]})
        with self.assertRaises(ValueError):
            merit_adjustments([Employee("x", "L", 1000, "R")], [band], {"R": [0.1, 0.05, 0.0]},
                              zone_edges=[1.1, 0.9])

    def test_budget_summary(self):
        got = budget_summary(merit_adjustments(book_staff(), book_bands(), BOOK_MATRIX))
        self.assertAlmostEqual(got["payroll"], 3550.0)
        self.assertAlmostEqual(got["base_increase"], 41.6 + 10 + 36 + 0 + 0)
        self.assertAlmostEqual(got["lump_sum"], 3.8 + 22.0)
        self.assertAlmostEqual(got["total_cost"], 87.6 + 25.8)
        self.assertAlmostEqual(got["increase_rate"], 87.6 / 3550)

    def test_budget_summary_invalid(self):
        with self.assertRaises(ValueError):
            budget_summary([])
        with self.assertRaises(ValueError):
            budget_summary([Adjustment("x", 0, 0, 0, 0, 0)])


if __name__ == "__main__":
    unittest.main()
