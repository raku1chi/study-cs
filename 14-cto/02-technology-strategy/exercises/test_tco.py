"""14.2 技術戦略の立て方 — テスト（tco.py）

実行: python3 tools/check.py 14.2   （またはこのディレクトリで python3 -m unittest -v test_tco）
"""
import unittest

from tco import (
    Option,
    annual_costs,
    break_even,
    present_value,
    rank_options,
    tornado,
    total_cost_of_ownership,
)


def scenario():
    """本文 5.4 節の例: 請求・課金基盤（単位: 万円）。"""
    build = Option("Build", upfront=5000, fte=1.5, cost_per_fte=1200, wage_growth=0.03,
                   infra=150, exit_cost=1000)
    buy = Option("Buy", upfront=1500, fte=0.5, cost_per_fte=1200, wage_growth=0.03,
                 license=1300, license_escalator=0.20, exit_cost=2500)
    partner = Option("Partner", upfront=3500, fte=0.5, cost_per_fte=1200, wage_growth=0.03,
                     license=1800, license_escalator=0.03, exit_cost=2000)
    return [build, buy, partner]


class TestExercise1PresentValueAndAnnualCosts(unittest.TestCase):
    def test_present_value_examples(self):
        self.assertAlmostEqual(present_value(110.0, 0.10, 1), 100.0)
        self.assertAlmostEqual(present_value(121.0, 0.10, 2), 100.0)
        self.assertEqual(present_value(100.0, 0.10, 0), 100.0)
        self.assertAlmostEqual(present_value(100.0, 0.0, 5), 100.0)

    def test_present_value_negative_rate_is_allowed_above_minus_one(self):
        # マイナス金利のような状況も計算できる（-1 より大きければよい）
        self.assertAlmostEqual(present_value(99.0, -0.01, 1), 100.0)

    def test_present_value_rejects_invalid_inputs(self):
        with self.assertRaises(ValueError):
            present_value(100.0, -1.0, 1)
        with self.assertRaises(ValueError):
            present_value(100.0, -1.5, 1)
        with self.assertRaises(ValueError):
            present_value(100.0, 0.1, -1)

    def test_annual_costs_docstring_example(self):
        o = Option("x", upfront=100, license=10, license_escalator=0.5, exit_cost=7)
        costs = annual_costs(o, 2)
        self.assertEqual(len(costs), 3)
        for got, want in zip(costs, [100.0, 10.0, 22.0]):
            self.assertAlmostEqual(got, want)

    def test_annual_costs_people_and_escalators_compound_from_year_one(self):
        o = Option("x", fte=2, cost_per_fte=1000, wage_growth=0.10, license=500,
                   license_escalator=0.20, infra=30, other=20)
        costs = annual_costs(o, 3)
        expected = [
            0.0,
            2000 + 500 + 50,                      # 1 年目: 上昇なし
            2000 * 1.1 + 500 * 1.2 + 50,          # 2 年目: 1 回上昇
            2000 * 1.1**2 + 500 * 1.2**2 + 50,    # 3 年目: 2 回上昇
        ]
        for t, (got, want) in enumerate(zip(costs, expected)):
            self.assertAlmostEqual(got, want, msg=f"{t} 年目")

    def test_exit_cost_only_in_final_year(self):
        o = Option("x", infra=100, exit_cost=1000)
        self.assertEqual([round(c, 6) for c in annual_costs(o, 4)], [0, 100, 100, 100, 1100])
        self.assertEqual([round(c, 6) for c in annual_costs(o, 1)], [0, 1100])

    def test_scenario_annual_costs(self):
        build, buy, partner = scenario()
        self.assertEqual([round(c) for c in annual_costs(build, 5)], [5000, 1950, 2004, 2060, 2117, 3176])
        self.assertEqual([round(c) for c in annual_costs(buy, 5)], [1500, 1900, 2178, 2509, 2902, 5871])
        self.assertEqual([round(c) for c in annual_costs(partner, 5)], [3500, 2400, 2472, 2546, 2623, 4701])

    def test_annual_costs_rejects_non_positive_years(self):
        with self.assertRaises(ValueError):
            annual_costs(Option("x", infra=1), 0)


class TestExercise2Tco(unittest.TestCase):
    def test_zero_rate_equals_simple_sum(self):
        for o in scenario():
            self.assertAlmostEqual(
                total_cost_of_ownership(o, 5, 0.0), sum(annual_costs(o, 5)), places=6, msg=o.name
            )

    def test_hand_computed_tco(self):
        o = Option("x", upfront=100, infra=110)
        # 100 + 110/1.1 = 200
        self.assertAlmostEqual(total_cost_of_ownership(o, 1, 0.10), 200.0)
        # 100 + 110/1.1 + 110/1.21 = 290.909...
        self.assertAlmostEqual(total_cost_of_ownership(o, 2, 0.10), 100 + 100 + 110 / 1.21)

    def test_scenario_ranking_and_discounting_changes_the_answer(self):
        options = scenario()
        ranked = rank_options(options, 5, 0.08)
        self.assertEqual([name for name, _ in ranked], ["Buy", "Build", "Partner"])
        self.assertAlmostEqual(ranked[0][1], 13247, delta=1)
        self.assertAlmostEqual(ranked[1][1], 13876, delta=1)
        self.assertAlmostEqual(ranked[2][1], 14990, delta=1)
        # 割り引かない単純合計では Build の方が安い（Buy のコストは後年に偏っている）
        undiscounted = rank_options(options, 5, 0.0)
        self.assertEqual(undiscounted[0][0], "Build")

    def test_ties_are_sorted_by_name(self):
        a = Option("b-option", infra=100)
        b = Option("a-option", infra=100)
        self.assertEqual([n for n, _ in rank_options([a, b], 3, 0.05)], ["a-option", "b-option"])

    def test_rank_options_rejects_empty_and_duplicates(self):
        with self.assertRaises(ValueError):
            rank_options([], 3, 0.05)
        with self.assertRaises(ValueError):
            rank_options([Option("same", infra=1), Option("same", infra=2)], 3, 0.05)


class TestExercise3Sensitivity(unittest.TestCase):
    def test_rows_are_sorted_by_swing(self):
        ranges = {
            "Build.fte": (1.0, 2.5),
            "Buy.license_escalator": (0.05, 0.35),
            "discount_rate": (0.04, 0.12),
            "Partner.license": (1400, 2200),
        }
        rows = tornado(scenario(), 5, 0.08, ranges)
        self.assertEqual(
            [r.parameter for r in rows],
            ["Buy.license_escalator", "Build.fte", "discount_rate", "Partner.license"],
        )
        swings = [r.swing for r in rows]
        self.assertEqual(swings, sorted(swings, reverse=True))

    def test_margins_and_winners(self):
        rows = {r.parameter: r for r in tornado(
            scenario(), 5, 0.08,
            {"Buy.license_escalator": (0.05, 0.35), "Build.fte": (1.0, 2.5), "discount_rate": (0.04, 0.12)},
        )}
        esc = rows["Buy.license_escalator"]
        self.assertAlmostEqual(esc.margin_low, 2449, delta=1)
        self.assertAlmostEqual(esc.margin_high, -1736, delta=1)
        self.assertEqual((esc.winner_low, esc.winner_high), ("Buy", "Build"))
        self.assertTrue(esc.flips)

        fte = rows["Build.fte"]
        self.assertAlmostEqual(fte.margin_low, -1903, delta=1)
        self.assertAlmostEqual(fte.margin_high, 1743, delta=1)  # 上限は Partner との差で頭打ち
        self.assertEqual((fte.winner_low, fte.winner_high), ("Build", "Buy"))

        rate = rows["discount_rate"]
        self.assertFalse(rate.flips)
        self.assertEqual((rate.winner_low, rate.winner_high), ("Buy", "Buy"))
        self.assertAlmostEqual(rate.margin_low, 102, delta=1)
        self.assertAlmostEqual(rate.margin_high, 1058, delta=1)

    def test_inputs_are_not_mutated(self):
        options = scenario()
        before = list(options)
        tornado(options, 5, 0.08, {"Build.fte": (0.1, 9.0)})
        self.assertEqual(options, before)

    def test_ties_in_swing_are_sorted_by_name(self):
        a = Option("A", infra=100)
        b = Option("B", infra=200)
        # A.other と A.infra は同じ効果（年額に加算）なので swing が等しい
        rows = tornado([a, b], 3, 0.0, {"A.other": (0, 50), "A.infra": (100, 150)})
        self.assertEqual([r.parameter for r in rows], ["A.infra", "A.other"])
        self.assertAlmostEqual(rows[0].swing, rows[1].swing)

    def test_invalid_parameters(self):
        options = scenario()
        for bad in ["fte", "Nothing.fte", "Build.name", "Build.unknown", "rate", "Build."]:
            with self.assertRaises(ValueError, msg=bad):
                tornado(options, 5, 0.08, {bad: (0, 1)})
        with self.assertRaises(ValueError):
            tornado(options[:1], 5, 0.08, {"Build.fte": (1, 2)})

    def test_break_even_escalator(self):
        options = scenario()
        x = break_even(options, 5, 0.08, "Buy.license_escalator", 0.0, 0.5)
        self.assertAlmostEqual(x, 0.2438, delta=0.0002)
        # 境界の少し手前では Buy、少し先では別の案が最良になる
        import dataclasses

        def winner(value):
            opts = [dataclasses.replace(o, license_escalator=value) if o.name == "Buy" else o
                    for o in options]
            return rank_options(opts, 5, 0.08)[0][0]

        self.assertEqual(winner(x - 0.001), "Buy")
        self.assertEqual(winner(x + 0.001), "Build")

    def test_break_even_fte_linear_case(self):
        # 2 案、割引なし、3 年: A の人件費 1000×fte×3 と B の 6000 が等しくなるのは fte = 2
        a = Option("A", fte=1.0, cost_per_fte=1000)
        b = Option("B", license=2000)
        self.assertAlmostEqual(break_even([a, b], 3, 0.0, "A.fte", 0.0, 5.0), 2.0, places=6)

    def test_break_even_works_in_either_direction(self):
        a = Option("A", fte=1.0, cost_per_fte=1000)
        b = Option("B", license=2000)
        self.assertAlmostEqual(break_even([a, b], 3, 0.0, "A.fte", 5.0, 0.0), 2.0, places=6)

    def test_break_even_without_crossing_raises(self):
        with self.assertRaises(ValueError):
            break_even(scenario(), 5, 0.08, "discount_rate", 0.04, 0.12)
        with self.assertRaises(ValueError):
            break_even(scenario(), 5, 0.08, "Build.nope", 0, 1)


if __name__ == "__main__":
    unittest.main()
