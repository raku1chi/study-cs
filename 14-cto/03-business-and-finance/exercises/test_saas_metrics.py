"""14.3 事業と財務のリテラシー — テスト（saas_metrics.py）

実行: python3 tools/check.py 14.3   （またはこのディレクトリで python3 -m unittest -v test_saas_metrics）
"""
import math
import random
import unittest

from saas_metrics import (
    MrrMovement,
    annual_churn_from_monthly,
    burn_multiple,
    cac,
    cac_payback_months,
    gross_revenue_retention,
    logo_retention,
    ltv,
    mrr_movements,
    net_revenue_retention,
    rule_of_40,
)

# 本文 4 節の例（単位: 万円/月）
SNAPSHOTS = [
    {"A": 100, "B": 50, "C": 30},
    {"A": 120, "B": 50, "C": 30, "D": 40},   # A 拡大 +20、D 新規 +40
    {"A": 120, "B": 35, "D": 40, "E": 60},   # B 縮小 −15、C 解約 −30、E 新規 +60
    {"A": 150, "B": 35, "C": 30, "D": 40, "E": 60},  # A 拡大 +30、C 再開 +30
]


def movement_tuple(m: MrrMovement):
    return (m.period, m.starting, m.new, m.expansion, m.reactivation, m.contraction, m.churned, m.ending)


class TestMrrMovements(unittest.TestCase):
    def test_example(self):
        got = [movement_tuple(m) for m in mrr_movements(SNAPSHOTS)]
        self.assertEqual(
            got,
            [
                (1, 180, 40, 20, 0, 0, 0, 240),
                (2, 240, 60, 0, 0, 15, 30, 255),
                (3, 255, 0, 30, 30, 0, 0, 315),
            ],
        )

    def test_net_new_property(self):
        self.assertEqual([m.net_new for m in mrr_movements(SNAPSHOTS)], [60, 15, 60])

    def test_zero_mrr_is_treated_like_absent(self):
        snaps = [{"A": 100, "B": 0}, {"A": 0, "B": 20}]
        (m,) = mrr_movements(snaps)
        self.assertEqual((m.churned, m.new, m.reactivation), (100, 20, 0))

    def test_customer_active_in_first_snapshot_reactivates(self):
        # A は snapshots[0] で課金していたので、戻ってきたら「新規」ではなく「再開」
        snaps = [{"A": 10}, {}, {}, {"A": 15}]
        moves = mrr_movements(snaps)
        self.assertEqual(moves[0].churned, 10)
        self.assertEqual((moves[2].new, moves[2].reactivation), (0, 15))

    def test_short_inputs(self):
        self.assertEqual(mrr_movements([]), [])
        self.assertEqual(mrr_movements([{"A": 1}]), [])

    def test_negative_mrr_is_rejected(self):
        with self.assertRaises(ValueError):
            mrr_movements([{"A": 10}, {"A": -1}])

    def test_identity_holds_on_random_data(self):
        rng = random.Random(7)
        customers = [f"c{i}" for i in range(30)]
        snaps = []
        for _ in range(12):
            snap = {}
            for c in customers:
                r = rng.random()
                if r < 0.6:
                    snap[c] = rng.choice([0, 5, 10, 20, 40, 80])
            snaps.append(snap)
        for m in mrr_movements(snaps):
            self.assertAlmostEqual(
                m.ending,
                m.starting + m.new + m.expansion + m.reactivation - m.contraction - m.churned,
                msg=f"period {m.period}",
            )
            for value in (m.new, m.expansion, m.reactivation, m.contraction, m.churned):
                self.assertGreaterEqual(value, 0)


class TestRetention(unittest.TestCase):
    def test_nrr_grr_logo_example(self):
        # コホート（0 月目）: A 100, B 50, C 30 = 180
        # 3 月目: A 150, B 35, C 30 = 215 → NRR = 215/180
        self.assertAlmostEqual(net_revenue_retention(SNAPSHOTS, 0, 3), 215 / 180)
        # GRR: min(150,100) + min(35,50) + min(30,30) = 165 → 165/180
        self.assertAlmostEqual(gross_revenue_retention(SNAPSHOTS, 0, 3), 165 / 180)
        # C は一度解約したが 3 月目には戻っている → 3/3
        self.assertAlmostEqual(logo_retention(SNAPSHOTS, 0, 3), 1.0)

    def test_new_customers_are_excluded(self):
        # 1→2: コホート A,B,C,D = 240。2 月目の A,B,D = 195（E は新規なので含めない）
        self.assertAlmostEqual(net_revenue_retention(SNAPSHOTS, 1, 2), 195 / 240)
        self.assertAlmostEqual(gross_revenue_retention(SNAPSHOTS, 1, 2), 195 / 240)
        self.assertAlmostEqual(logo_retention(SNAPSHOTS, 1, 2), 3 / 4)

    def test_grr_never_exceeds_one_and_nrr_can(self):
        snaps = [{"A": 10}, {"A": 50}]
        self.assertAlmostEqual(net_revenue_retention(snaps, 0, 1), 5.0)
        self.assertAlmostEqual(gross_revenue_retention(snaps, 0, 1), 1.0)

    def test_invalid_ranges(self):
        for start, end in [(0, 0), (2, 1), (-1, 2), (0, 4)]:
            with self.assertRaises(ValueError, msg=(start, end)):
                net_revenue_retention(SNAPSHOTS, start, end)
        with self.assertRaises(ValueError):
            gross_revenue_retention([{}, {"A": 1}], 0, 1)  # コホートが空
        with self.assertRaises(ValueError):
            logo_retention([{"A": 0}, {"A": 1}], 0, 1)
        with self.assertRaises(ValueError):
            net_revenue_retention([{"A": 5}, {"A": -5}], 0, 1)


class TestUnitEconomics(unittest.TestCase):
    def test_cac(self):
        self.assertAlmostEqual(cac(3000, 25), 120.0)
        with self.assertRaises(ValueError):
            cac(3000, 0)
        with self.assertRaises(ValueError):
            cac(-1, 10)

    def test_cac_payback(self):
        self.assertAlmostEqual(cac_payback_months(120, 10, 0.8), 15.0)
        # 粗利率が下がると回収期間は延びる
        self.assertAlmostEqual(cac_payback_months(120, 10, 0.6), 20.0)
        for args in [(120, 0, 0.8), (120, 10, 0.0), (120, 10, 1.2), (-1, 10, 0.8)]:
            with self.assertRaises(ValueError, msg=args):
                cac_payback_months(*args)

    def test_ltv(self):
        self.assertAlmostEqual(ltv(10, 0.8, 0.02), 400.0)
        self.assertAlmostEqual(ltv(10, 0.8, 1.0), 8.0)
        self.assertAlmostEqual(ltv(10, 0.8, 0.02) / cac(3000, 25), 400 / 120)
        for args in [(10, 0.8, 0.0), (10, 0.8, 1.5), (10, 1.1, 0.02), (-1, 0.8, 0.02)]:
            with self.assertRaises(ValueError, msg=args):
                ltv(*args)

    def test_annual_churn(self):
        self.assertAlmostEqual(annual_churn_from_monthly(0.02), 1 - 0.98**12)
        self.assertAlmostEqual(annual_churn_from_monthly(0.02), 0.2153, places=4)
        self.assertLess(annual_churn_from_monthly(0.02), 0.24)
        self.assertEqual(annual_churn_from_monthly(0.0), 0.0)
        self.assertEqual(annual_churn_from_monthly(1.0), 1.0)
        with self.assertRaises(ValueError):
            annual_churn_from_monthly(1.1)

    def test_rule_of_40(self):
        self.assertAlmostEqual(rule_of_40(0.55, -0.10), 0.45)
        self.assertAlmostEqual(rule_of_40(0.20, 0.15), 0.35)

    def test_burn_multiple(self):
        self.assertAlmostEqual(burn_multiple(3.0, 2.0), 1.5)
        self.assertAlmostEqual(burn_multiple(-1.0, 2.0), -0.5)
        with self.assertRaises(ValueError):
            burn_multiple(3.0, 0.0)
        with self.assertRaises(ValueError):
            burn_multiple(3.0, -1.0)
        self.assertTrue(math.isfinite(burn_multiple(0.0, 1.0)))


if __name__ == "__main__":
    unittest.main()
