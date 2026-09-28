"""14.3 事業と財務のリテラシー — テスト（npv.py）

実行: python3 tools/check.py 14.3   （またはこのディレクトリで python3 -m unittest -v test_npv）
"""
import random
import unittest

from npv import discounted_payback_period, irr, npv, payback_period

# 本文 7.1 節の例: 3,000 万円の移行で、クラウド費用が年 1,200 万円下がる（5 年間）
MIGRATION = [-3000, 1200, 1200, 1200, 1200, 1200]


class TestNpv(unittest.TestCase):
    def test_zero_rate_is_simple_sum(self):
        self.assertAlmostEqual(npv(0.0, [-100, 60, 60]), 20.0)
        self.assertAlmostEqual(npv(0.0, MIGRATION), 3000.0)

    def test_hand_computed_values(self):
        self.assertAlmostEqual(npv(0.10, [-100, 110]), 0.0)
        self.assertAlmostEqual(npv(0.10, [0, 0, 121]), 100.0)
        self.assertAlmostEqual(npv(0.10, [50]), 50.0)

    def test_migration_example(self):
        # 年金現価係数 (1 - 1.08^-5) / 0.08 ≈ 3.99271 → -3000 + 1200 × 3.99271 ≈ 1791.25
        self.assertAlmostEqual(npv(0.08, MIGRATION), 1791.25, delta=0.01)

    def test_higher_rate_lowers_npv_of_conventional_investment(self):
        values = [npv(r, MIGRATION) for r in (0.0, 0.05, 0.10, 0.20, 0.40)]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            npv(-1.0, [1, 2])
        with self.assertRaises(ValueError):
            npv(0.1, [])


class TestIrr(unittest.TestCase):
    def test_simple(self):
        self.assertAlmostEqual(irr([-100, 110]), 0.10, places=8)
        self.assertAlmostEqual(irr([-100, 0, 121]), 0.10, places=8)

    def test_migration_example(self):
        r = irr(MIGRATION)
        self.assertAlmostEqual(r, 0.2865, places=4)
        self.assertAlmostEqual(npv(r, MIGRATION), 0.0, places=5)

    def test_negative_irr(self):
        # 回収額が投資額より少ないと IRR は負になる
        r = irr([-100, 45, 45])
        self.assertLess(r, 0)
        self.assertAlmostEqual(npv(r, [-100, 45, 45]), 0.0, places=6)

    def test_random_cashflows_have_zero_npv_at_irr(self):
        rng = random.Random(42)
        for _ in range(100):
            invest = -rng.uniform(100, 1000)
            flows = [invest] + [rng.uniform(10, 600) for _ in range(rng.randint(1, 8))]
            if sum(flows) <= 0 and npv(-0.99, flows) <= 0:
                continue
            try:
                r = irr(flows)
            except ValueError:
                continue
            self.assertAlmostEqual(npv(r, flows) / abs(invest), 0.0, places=6, msg=str(flows))

    def test_requires_sign_change(self):
        with self.assertRaises(ValueError):
            irr([100, 100])
        with self.assertRaises(ValueError):
            irr([-100, -100])
        with self.assertRaises(ValueError):
            irr([-100])

    def test_root_outside_bracket(self):
        # IRR は 10% だが、探索範囲を 20%〜50% に限定すると見つからない
        with self.assertRaises(ValueError):
            irr([-100, 110], lo=0.2, hi=0.5)


class TestPayback(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(payback_period([-300, 100, 100, 100, 100]), 3.0)
        self.assertAlmostEqual(payback_period([-300, 120, 120, 120]), 2.5)
        self.assertAlmostEqual(payback_period(MIGRATION), 2.5)
        self.assertEqual(payback_period([0, 10]), 0.0)
        self.assertEqual(payback_period([50, -10]), 0.0)

    def test_never_recovered(self):
        self.assertIsNone(payback_period([-300, 100]))
        self.assertIsNone(payback_period([-300, -100, 100, 100]))

    def test_uneven_flows(self):
        # 累積: -500, -400, -100, +300 → 3 期目の途中（2 + 100/400 = 2.25）
        self.assertAlmostEqual(payback_period([-500, 100, 300, 400]), 2.25)

    def test_empty(self):
        with self.assertRaises(ValueError):
            payback_period([])

    def test_discounted_payback(self):
        self.assertAlmostEqual(discounted_payback_period(0.0, MIGRATION), 2.5)
        d = discounted_payback_period(0.08, MIGRATION)
        # 割引後の累積: 1111.1, 2139.9, 3092.5 → 2 + (3000 - 2139.9) / 952.6 ≈ 2.903
        self.assertAlmostEqual(d, 2.903, places=3)
        self.assertGreater(d, payback_period(MIGRATION))

    def test_discounting_can_prevent_recovery(self):
        flows = [-300, 100, 100, 100]
        self.assertAlmostEqual(payback_period(flows), 3.0)
        self.assertIsNone(discounted_payback_period(0.10, flows))

    def test_discounted_invalid_rate(self):
        with self.assertRaises(ValueError):
            discounted_payback_period(-1.0, MIGRATION)


if __name__ == "__main__":
    unittest.main()
