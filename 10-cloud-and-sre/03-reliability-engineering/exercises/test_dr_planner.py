"""10.3 DR 戦略の選択 — テスト

実行: python3 tools/check.py 10.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import itertools
import random
import unittest

from dr_planner import (
    EXAMPLE_STRATEGIES,
    Allocation,
    Service,
    Strategy,
    allocate_budget,
    best_strategy,
    cheapest_strategy,
    expected_annual_loss,
    meets,
)

S = {s.name: s for s in EXAMPLE_STRATEGIES}
PAYMENTS = Service("payments", disasters_per_year=0.1, downtime_cost_per_hour=500, data_loss_cost_per_hour=300,
                   max_rto_minutes=60)
CATALOG = Service("catalog", disasters_per_year=0.1, downtime_cost_per_hour=100, data_loss_cost_per_hour=20)
REPORTS = Service("reports", disasters_per_year=0.1, downtime_cost_per_hour=5, data_loss_cost_per_hour=2)


class TestExercise4Choose(unittest.TestCase):
    def test_meets(self):
        self.assertTrue(meets(S["pilot-light"], 15, 240), "ちょうどは満たす")
        self.assertFalse(meets(S["pilot-light"], 14, 240))
        self.assertTrue(meets(S["backup-restore"], None, None), "要件なしなら何でもよい")
        self.assertFalse(meets(S["backup-restore"], None, 60))

    def test_cheapest(self):
        self.assertEqual(cheapest_strategy(EXAMPLE_STRATEGIES, 60, 240).name, "pilot-light")
        self.assertEqual(cheapest_strategy(EXAMPLE_STRATEGIES, 5, 60).name, "warm-standby")
        self.assertEqual(cheapest_strategy(EXAMPLE_STRATEGIES, None, None).name, "backup-restore")
        self.assertEqual(cheapest_strategy(EXAMPLE_STRATEGIES, 0, 5).name, "active-active")
        self.assertIsNone(cheapest_strategy(EXAMPLE_STRATEGIES, 0, 0), "RTO 0 はどの戦略でも満たせない")

    def test_cheapest_tie_breaks(self):
        a = Strategy("b-slow", 10, 60, 100)
        b = Strategy("a-fast", 10, 30, 100)
        c = Strategy("c-fast", 5, 30, 100)
        self.assertEqual(cheapest_strategy([a, b, c], None, None).name, "c-fast", "同額なら RTO、次に RPO の小さい方")
        d = Strategy("d", 5, 30, 100)
        self.assertEqual(cheapest_strategy([d, c], None, None).name, "c-fast", "それも同じなら名前順")

    def test_expected_annual_loss(self):
        self.assertAlmostEqual(expected_annual_loss(S["backup-restore"], PAYMENTS), 0.1 * (24 * 500 + 24 * 300))
        self.assertAlmostEqual(expected_annual_loss(S["pilot-light"], PAYMENTS), 207.5)
        self.assertAlmostEqual(expected_annual_loss(S["warm-standby"], PAYMENTS), 25.5)
        self.assertAlmostEqual(expected_annual_loss(S["active-active"], PAYMENTS), 0.1 * 500 / 60)

    def test_best_strategy_balances_cost_and_risk(self):
        strategy, total = best_strategy(EXAMPLE_STRATEGIES, CATALOG)
        self.assertEqual(strategy.name, "pilot-light")
        self.assertAlmostEqual(total, 340.5)
        strategy, total = best_strategy(EXAMPLE_STRATEGIES, REPORTS)
        self.assertEqual(strategy.name, "backup-restore", "損失の小さいサービスに高価な DR は割に合わない")
        self.assertAlmostEqual(total, 76.8)

    def test_best_strategy_respects_hard_requirements(self):
        # 要件がなければ pilot-light（300 + 207.5）が最良だが、RTO 60 分の必須要件がある
        free = Service("p", 0.1, 500, 300)
        self.assertEqual(best_strategy(EXAMPLE_STRATEGIES, free)[0].name, "pilot-light")
        strategy, total = best_strategy(EXAMPLE_STRATEGIES, PAYMENTS)
        self.assertEqual(strategy.name, "warm-standby")
        self.assertAlmostEqual(total, 925.5)
        with self.assertRaises(ValueError):
            best_strategy(EXAMPLE_STRATEGIES, Service("x", 1, 1, 1, max_rto_minutes=0))


def brute_force(services, strategies, budget):
    best = None
    options = [[s for s in strategies if meets(s, v.max_rpo_minutes, v.max_rto_minutes)] for v in services]
    for combo in itertools.product(*options):
        cost = sum(s.annual_cost for s in combo)
        if cost > budget:
            continue
        value = sum(s.annual_cost + expected_annual_loss(s, v) for s, v in zip(combo, services))
        if best is None or (value, cost) < best[:2]:
            best = (value, cost, combo)
    return best


class TestExercise5Allocate(unittest.TestCase):
    def test_ample_budget_gives_each_its_best(self):
        result = allocate_budget([PAYMENTS, CATALOG, REPORTS], EXAMPLE_STRATEGIES, budget=5000)
        self.assertIsInstance(result, Allocation)
        self.assertEqual(result.choices, {"payments": "warm-standby", "catalog": "pilot-light",
                                          "reports": "backup-restore"})
        self.assertEqual(result.annual_cost, 1260, "予算を使い切ることが目的ではない")
        self.assertAlmostEqual(result.expected_total, 925.5 + 340.5 + 76.8)

    def test_tight_budget_downgrades_where_it_hurts_least(self):
        result = allocate_budget([PAYMENTS, CATALOG, REPORTS], EXAMPLE_STRATEGIES, budget=1200)
        self.assertEqual(result.choices, {"payments": "warm-standby", "catalog": "backup-restore",
                                          "reports": "backup-restore"})
        self.assertEqual(result.annual_cost, 1020)
        self.assertAlmostEqual(result.expected_total, 925.5 + 348.0 + 76.8)

    def test_infeasible(self):
        with self.assertRaises(ValueError):
            allocate_budget([PAYMENTS, CATALOG, REPORTS], EXAMPLE_STRATEGIES, budget=1000)
        with self.assertRaises(ValueError):
            allocate_budget([Service("x", 1, 1, 1, max_rpo_minutes=-1)], EXAMPLE_STRATEGIES, budget=10_000)

    def test_empty(self):
        self.assertEqual(allocate_budget([], EXAMPLE_STRATEGIES, budget=0), Allocation({}, 0, 0.0))

    def test_matches_brute_force(self):
        rng = random.Random(1003)
        for _ in range(60):
            strategies = [
                Strategy(f"s{i}", rpo_minutes=rng.choice([0, 1, 5, 15, 60, 240, 1440]),
                         rto_minutes=rng.choice([1, 10, 30, 60, 240, 1440]), annual_cost=rng.randrange(10, 1000))
                for i in range(rng.randrange(2, 6))
            ]
            services = [
                Service(f"v{j}", disasters_per_year=rng.choice([0.05, 0.1, 0.5, 1.0]),
                        downtime_cost_per_hour=rng.randrange(1, 2000), data_loss_cost_per_hour=rng.randrange(0, 2000),
                        max_rto_minutes=rng.choice([None, None, 60, 240]))
                for j in range(rng.randrange(1, 5))
            ]
            budget = rng.randrange(0, 3000)
            expected = brute_force(services, strategies, budget)
            if expected is None:
                with self.assertRaises(ValueError):
                    allocate_budget(services, strategies, budget)
                continue
            result = allocate_budget(services, strategies, budget)
            self.assertLessEqual(result.annual_cost, budget)
            self.assertAlmostEqual(result.expected_total, expected[0], places=6)
            by_name = {s.name: s for s in strategies}
            recomputed = sum(by_name[result.choices[v.name]].annual_cost
                             + expected_annual_loss(by_name[result.choices[v.name]], v) for v in services)
            self.assertAlmostEqual(recomputed, result.expected_total, places=6, msg="choices と合計が一致すること")


if __name__ == "__main__":
    unittest.main()
