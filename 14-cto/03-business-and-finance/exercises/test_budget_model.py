"""14.3 事業と財務のリテラシー — テスト（budget_model.py）

実行: python3 tools/check.py 14.3   （またはこのディレクトリで python3 -m unittest -v test_budget_model）
"""
import math
import unittest

from budget_model import (
    Assumptions,
    Hire,
    delay_sensitivity,
    hire_cost_in_month,
    monthly_burn,
    projected_runway,
    simple_runway,
    steady_monthly_cost,
)

# 手計算しやすい前提: 年収 1200 → 月給 100、法定福利費 25%、福利厚生等 5、一時費用 50
EASY = Assumptions(statutory_welfare_rate=0.25, benefits_monthly=5.0, equipment_one_time=50.0)


def book_example():
    """本文 6.3 節の例（単位: 万円）。"""
    a = Assumptions(statutory_welfare_rate=0.16, benefits_monthly=3.0, equipment_one_time=40.0)
    team = [Hire(f"在籍エンジニア{i}", 800, 0) for i in range(1, 11)]
    plan = [
        Hire("バックエンド", 900, 2, 0.35),
        Hire("フロントエンド", 850, 2, 0.35),
        Hire("SRE", 1000, 3, 0.35),
        Hire("エンジニアリングマネージャー", 1200, 4, 0.35),
        Hire("バックエンド", 900, 5),
        Hire("データエンジニア", 950, 6, 0.35),
        Hire("バックエンド", 900, 7),
        Hire("QA", 750, 9),
    ]
    months = 36
    revenue = [500 * 1.03**m for m in range(months)]
    return a, team + plan, months, 1200.0, revenue


class TestCosts(unittest.TestCase):
    def test_steady_monthly_cost(self):
        self.assertAlmostEqual(steady_monthly_cost(1200, EASY), 130.0)
        self.assertAlmostEqual(steady_monthly_cost(800, Assumptions()), 800 / 12 * 1.16 + 3.0)
        self.assertAlmostEqual(steady_monthly_cost(0, EASY), 5.0)
        with self.assertRaises(ValueError):
            steady_monthly_cost(-1, EASY)

    def test_hire_cost_timeline(self):
        h = Hire("backend", 1200, 3, agency_fee_rate=0.35)
        costs = [hire_cost_in_month(h, m, EASY) for m in range(1, 6)]
        # 入社前 0、入社月は 130 + 一時費用 50 + 紹介手数料 1200 × 0.35 = 420、その後 130
        for got, want in zip(costs, [0, 0, 600, 130, 130]):
            self.assertAlmostEqual(got, want)

    def test_existing_staff_have_no_one_time_costs(self):
        for start in (0, -5):
            h = Hire("existing", 1200, start, agency_fee_rate=0.35)
            self.assertAlmostEqual(hire_cost_in_month(h, 1, EASY), 130.0)

    def test_month_must_be_positive(self):
        with self.assertRaises(ValueError):
            hire_cost_in_month(Hire("x", 1200, 1), 0, EASY)


class TestBurnAndRunway(unittest.TestCase):
    def test_monthly_burn_with_scalars(self):
        hires = [Hire("a", 1200, 0), Hire("b", 1200, 2)]
        burns = monthly_burn(hires, 3, EASY, other_costs=100, revenue=30)
        for got, want in zip(burns, [130 + 100 - 30, 130 + 180 + 100 - 30, 260 + 100 - 30]):
            self.assertAlmostEqual(got, want)

    def test_monthly_burn_with_sequences(self):
        burns = monthly_burn([], 3, EASY, other_costs=[10, 20, 30], revenue=[5, 5, 50])
        self.assertEqual([round(b, 6) for b in burns], [5, 15, -20])

    def test_monthly_burn_rejects_bad_lengths(self):
        with self.assertRaises(ValueError):
            monthly_burn([], 3, EASY, other_costs=[1, 2])
        with self.assertRaises(ValueError):
            monthly_burn([], 3, EASY, revenue=[1, 2, 3, 4])
        with self.assertRaises(ValueError):
            monthly_burn([], 0, EASY)

    def test_projected_runway(self):
        self.assertEqual(projected_runway(100, [30, 30, 30, 30]), 3)
        self.assertIsNone(projected_runway(100, [50, 50]))       # ちょうど 0 はまだ尽きていない
        self.assertEqual(projected_runway(100, [150]), 0)
        self.assertIsNone(projected_runway(100, [50, -20, 60]))  # 収入で戻る月があってもよい
        self.assertEqual(projected_runway(0, [0, 1]), 1)
        with self.assertRaises(ValueError):
            projected_runway(-1, [1])

    def test_simple_runway(self):
        self.assertAlmostEqual(simple_runway(1200, 100), 12.0)
        self.assertEqual(simple_runway(1200, 0), math.inf)
        self.assertEqual(simple_runway(1200, -10), math.inf)
        with self.assertRaises(ValueError):
            simple_runway(-1, 10)

    def test_book_example(self):
        a, hires, months, other, revenue = book_example()
        burns = monthly_burn(hires, months, a, other, revenue)
        self.assertEqual(
            [round(b) for b in burns[:6]], [1503, 2356, 2138, 2311, 1964, 2375]
        )
        self.assertAlmostEqual(simple_runway(30000, burns[0]), 20.0, delta=0.1)
        # 採用で費用が増えるので、計画を織り込んだランウェイは単純ランウェイより短い
        self.assertEqual(projected_runway(30000, burns), 14)


class TestDelaySensitivity(unittest.TestCase):
    def test_book_example(self):
        a, hires, months, other, revenue = book_example()
        result = delay_sensitivity(30000, hires, months, a, other, revenue)
        self.assertEqual(result, {0: 14, 1: 14, 2: 15, 3: 15})

    def test_only_future_hires_are_shifted(self):
        existing = Hire("existing", 1200, 0)
        future = Hire("future", 1200, 2)
        # 在籍者 130/月 + 採用者（2 か月目から 130/月、入社月は 180）。現金 700
        # 遅れなし: 130, 310, 260, 260 → 累計 130, 440, 700, 960 → 3 か月目まで
        # 2 か月遅れ: 130, 130, 130, 310 → 累計 130, 260, 390, 700 → 尽きない
        result = delay_sensitivity(700, [existing, future], 4, EASY, delays=(0, 2))
        self.assertEqual(result, {0: 3, 2: None})

    def test_hires_pushed_beyond_horizon_cost_nothing(self):
        late = Hire("late", 1200, 3)
        result = delay_sensitivity(10, [late], 3, EASY, delays=(0, 1))
        self.assertEqual(result, {0: 2, 1: None})

    def test_inputs_not_mutated_and_negative_delay_rejected(self):
        hires = [Hire("x", 1200, 1)]
        delay_sensitivity(1000, hires, 3, EASY, delays=(2,))
        self.assertEqual(hires[0].start_month, 1)
        with self.assertRaises(ValueError):
            delay_sensitivity(1000, hires, 3, EASY, delays=(-1,))


if __name__ == "__main__":
    unittest.main()
