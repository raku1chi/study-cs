"""10.6 クラウド費用の計算 — テスト

実行: python3 tools/check.py 10.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import unittest

from cloudcost import (
    HOURS_PER_MONTH,
    InstanceType,
    allocate,
    breakeven_utilization,
    commitment_cost,
    commitment_savings,
    coverage_and_utilization,
    expected_runtime,
    monthly_savings,
    optimal_commitment,
    rightsize,
    spot_vs_on_demand,
    tiered_cost,
    unit_cost,
)

EGRESS_TIERS = [(10_000, 15.0), (50_000, 12.0), (math.inf, 10.0)]  # GB あたりの円（架空）

CATALOG = [
    InstanceType("gp.large", 2, 8, 14), InstanceType("gp.xlarge", 4, 16, 28), InstanceType("gp.2xlarge", 8, 32, 56),
    InstanceType("cpu.xlarge", 4, 8, 24), InstanceType("cpu.2xlarge", 8, 16, 48),
    InstanceType("mem.large", 2, 16, 18), InstanceType("mem.xlarge", 4, 32, 36),
]


def weekly_usage(weeks=4):
    """夜 20 台、平日の昼 60 台、朝夕 40 台。週末の昼は 30 台、朝夕は 25 台。"""
    usage = []
    for day in range(7 * weeks):
        weekend = day % 7 in (5, 6)
        for hour in range(24):
            if 9 <= hour < 21:
                usage.append(30 if weekend else 60)
            elif 7 <= hour < 9 or 21 <= hour < 23:
                usage.append(25 if weekend else 40)
            else:
                usage.append(20)
    return usage


class TestExercise1Tiered(unittest.TestCase):
    def test_tiers(self):
        self.assertEqual(tiered_cost(0, EGRESS_TIERS), 0)
        self.assertEqual(tiered_cost(5_000, EGRESS_TIERS), 75_000)
        self.assertEqual(tiered_cost(10_000, EGRESS_TIERS), 150_000)
        self.assertEqual(tiered_cost(30_000, EGRESS_TIERS), 150_000 + 20_000 * 12)
        self.assertEqual(tiered_cost(120_000, EGRESS_TIERS), 150_000 + 40_000 * 12 + 70_000 * 10)

    def test_single_tier(self):
        self.assertEqual(tiered_cost(3.5, [(math.inf, 2.0)]), 7.0)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            tiered_cost(-1, EGRESS_TIERS)
        with self.assertRaises(ValueError):
            tiered_cost(1, [(100, 1.0)])                      # 最後が inf でない
        with self.assertRaises(ValueError):
            tiered_cost(1, [(100, 1.0), (50, 1.0), (math.inf, 1.0)])
        with self.assertRaises(ValueError):
            tiered_cost(1, [])


class TestExercise2Commitment(unittest.TestCase):
    def test_breakeven(self):
        self.assertAlmostEqual(breakeven_utilization(100, 62), 0.62, msg="38% 割引なら稼働率 62% が分岐点")
        self.assertAlmostEqual(breakeven_utilization(100, 100), 1.0)
        with self.assertRaises(ValueError):
            breakeven_utilization(0, 10)

    def test_savings(self):
        self.assertAlmostEqual(commitment_savings(100, 62, 1.0), 38 * HOURS_PER_MONTH)
        self.assertAlmostEqual(commitment_savings(100, 62, 0.62), 0.0)
        self.assertAlmostEqual(commitment_savings(100, 62, 0.5), -12 * HOURS_PER_MONTH, msg="使わない確約は損")
        self.assertAlmostEqual(commitment_savings(100, 62, 1.0, hours=8760), 38 * 8760)
        with self.assertRaises(ValueError):
            commitment_savings(100, 62, 1.2)


class TestExercise3Spot(unittest.TestCase):
    def test_no_interruptions(self):
        self.assertEqual(expected_runtime(10, 0.0), 10)
        self.assertEqual(expected_runtime(10, 0.0, 0.5, checkpoint_hours=1), 10)

    def test_formula(self):
        lam, L, R = 0.1, 24, 0.25
        self.assertAlmostEqual(expected_runtime(L, lam, R), (math.exp(lam * L) - 1) * (1 / lam + R))
        self.assertAlmostEqual(expected_runtime(6, 0.2), (math.exp(1.2) - 1) / 0.2)

    def test_checkpoints_split_the_work(self):
        lam, R = 0.1, 0.25
        seg = (math.exp(lam * 2) - 1) * (1 / lam + R)
        self.assertAlmostEqual(expected_runtime(24, lam, R, checkpoint_hours=2), 12 * seg)
        last = (math.exp(lam * 1) - 1) * (1 / lam + R)
        self.assertAlmostEqual(expected_runtime(7, lam, R, checkpoint_hours=2), 3 * seg + last, msg="端数の区間")

    def test_matches_simulation(self):
        rng = random.Random(606)

        def simulate(work, lam, restart, checkpoint, trials=4000):
            total = 0.0
            for _ in range(trials):
                remaining = work
                while remaining > 1e-12:
                    seg = min(checkpoint, remaining) if checkpoint else remaining
                    while True:
                        x = rng.expovariate(lam)
                        if x >= seg:
                            total += seg
                            break
                        total += x + restart   # 中断されたら、その区間の最初からやり直す
                    remaining -= seg
            return total / trials

        for work, lam, restart, checkpoint in [(10, 0.05, 0.1, None), (24, 0.1, 0.25, 2.0), (6, 0.2, 0.0, None)]:
            expected = expected_runtime(work, lam, restart, checkpoint)
            self.assertAlmostEqual(simulate(work, lam, restart, checkpoint) / expected, 1.0, delta=0.05)

    def test_spot_vs_on_demand(self):
        spot, od = spot_vs_on_demand(24, 100, 30, 0.1, 0.25)
        self.assertEqual(od, 2400)
        self.assertGreater(spot, od, "長いジョブをチェックポイントなしでスポットに載せると、かえって高くつく")
        spot_ckpt, _ = spot_vs_on_demand(24, 100, 30, 0.1, 0.25, checkpoint_hours=2)
        self.assertLess(spot_ckpt, 0.4 * od, "2 時間ごとにチェックポイントを取れば 6 割以上安い")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            expected_runtime(-1, 0.1)
        with self.assertRaises(ValueError):
            expected_runtime(1, -0.1)
        with self.assertRaises(ValueError):
            expected_runtime(1, 0.1, checkpoint_hours=0)
        with self.assertRaises(ValueError):
            spot_vs_on_demand(1, -1, 1, 0.1)


class TestExercise4Allocate(unittest.TestCase):
    def test_proportional_sums_exactly(self):
        result = allocate(1_000_000, {"a": 1, "b": 1, "c": 1})
        self.assertEqual(result, {"a": 333_334, "b": 333_333, "c": 333_333})
        self.assertEqual(sum(result.values()), 1_000_000, "端数を丸めても合計は請求額と一致する")
        self.assertEqual(allocate(100, {"a": 2, "b": 1}), {"a": 67, "b": 33})

    def test_largest_remainder_goes_first(self):
        # 正確な値: a 14.2857…、b 28.5714…、c 57.1428… → 切り捨て 14, 28, 57（計 99）。端数最大の b に 1 円
        self.assertEqual(allocate(100, {"a": 1, "b": 2, "c": 4}), {"a": 14, "b": 29, "c": 57})

    def test_even_and_weighted(self):
        self.assertEqual(allocate(90, {"x": 500, "y": 300, "z": 200}, "even"), {"x": 30, "y": 30, "z": 30})
        self.assertEqual(allocate(1000, {"a": 0, "b": 0, "c": 0}, "weighted", {"a": 5, "b": 3, "c": 2}),
                         {"a": 500, "b": 300, "c": 200})

    def test_random_totals_always_match(self):
        rng = random.Random(10)
        for _ in range(300):
            usage = {f"t{i}": rng.random() * 100 for i in range(rng.randint(1, 8))}
            total = rng.randrange(0, 10_000_000)
            result = allocate(total, usage)
            self.assertEqual(sum(result.values()), total)
            for name, value in result.items():
                exact = total * usage[name] / sum(usage.values())
                self.assertLess(abs(value - exact), 1.0, "各テナントの誤差は 1 円未満")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            allocate(100, {})
        with self.assertRaises(ValueError):
            allocate(100, {"a": 0, "b": 0})
        with self.assertRaises(ValueError):
            allocate(100, {"a": 1}, "magic")
        with self.assertRaises(ValueError):
            allocate(100, {"a": 1, "b": 1}, "weighted", {"a": 1})
        with self.assertRaises(ValueError):
            allocate(-1, {"a": 1})

    def test_unit_cost(self):
        self.assertAlmostEqual(unit_cost(2_400_000, 120_000), 20.0)
        with self.assertRaises(ValueError):
            unit_cost(100, 0)


class TestExercise5Rightsize(unittest.TestCase):
    def test_rightsize(self):
        rng = random.Random(606)
        cpu = [max(0.1, rng.gauss(1.0, 0.3)) for _ in range(24 * 14)]
        mem = [rng.uniform(8.5, 10.0) for _ in range(24 * 14)]
        rec = rightsize(cpu, mem, CATALOG)
        self.assertEqual(rec.name, "mem.large", "CPU 2 コア・メモリ 12 GiB 以上で最安")
        self.assertEqual(monthly_savings(CATALOG[2], rec, count=10), (56 - 18) * 10 * HOURS_PER_MONTH)

    def test_memory_uses_max_not_percentile(self):
        cpu = [0.5] * 100
        mem = [4.0] * 99 + [14.0]   # 1 回だけのメモリの山
        self.assertEqual(rightsize(cpu, mem, CATALOG, headroom=0.1).name, "mem.large",
                         "14 × 1.1 = 15.4 GiB 以上が必要（p95 の 4 GiB で選ぶと 8 GiB の gp.large になり OOM）")

    def test_cpu_uses_percentile(self):
        cpu = [1.0] * 95 + [6.0] * 5          # p95 は 1.0。上位 5% の短い山は許容する
        mem = [4.0] * 100
        self.assertEqual(rightsize(cpu, mem, CATALOG).name, "gp.large")
        self.assertEqual(rightsize(cpu, mem, CATALOG, percentile=99).name, "cpu.2xlarge", "6.0 × 1.2 = 7.2 コア")

    def test_nothing_fits(self):
        self.assertIsNone(rightsize([16.0], [8.0], CATALOG))

    def test_tie_break(self):
        catalog = [InstanceType("b", 4, 8, 10), InstanceType("a", 2, 8, 10)]
        self.assertEqual(rightsize([1.0], [1.0], catalog).name, "a", "同額なら vCPU の少ない方")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            rightsize([], [1.0], CATALOG)
        with self.assertRaises(ValueError):
            rightsize([1.0], [], CATALOG)
        with self.assertRaises(ValueError):
            rightsize([1.0], [1.0], CATALOG, headroom=-0.1)


class TestExercise6CommitmentSizing(unittest.TestCase):
    def test_cost(self):
        usage = [10, 20, 30]
        self.assertEqual(commitment_cost(usage, 0, 100, 60), 60 * 100)
        self.assertEqual(commitment_cost(usage, 20, 100, 60), 3 * 20 * 60 + 10 * 100)
        self.assertEqual(commitment_cost(usage, 30, 100, 60), 3 * 30 * 60)

    def test_coverage_and_utilization(self):
        coverage, utilization = coverage_and_utilization([10, 20, 30], 20)
        self.assertAlmostEqual(coverage, (10 + 20 + 20) / 60)
        self.assertAlmostEqual(utilization, (10 + 20 + 20) / 60)
        self.assertEqual(coverage_and_utilization([10, 20], 0), (0.0, 0.0))
        with self.assertRaises(ValueError):
            coverage_and_utilization([], 1)

    def test_optimal_commitment(self):
        usage = weekly_usage()
        level, saving = optimal_commitment(usage, 100, 60)
        self.assertEqual(level, 30)
        self.assertAlmostEqual(saving, commitment_cost(usage, 0, 100, 60) - commitment_cost(usage, 30, 100, 60))
        coverage, utilization = coverage_and_utilization(usage, level)
        self.assertLess(utilization, 1.0, "最適な確約でも、利用率 100% にはならない")
        self.assertLess(coverage, 1.0)

    def test_newsvendor_rule(self):
        # 最適な水準では「使用量が水準を超える時間の割合」が、単価の比（60/100）をまたぐ
        usage = weekly_usage()
        level, _ = optimal_commitment(usage, 100, 60)
        above = lambda x: sum(1 for u in usage if u > x) / len(usage)  # noqa: E731
        self.assertGreaterEqual(above(level - 1), 0.6)
        self.assertLessEqual(above(level), 0.6)

    def test_matches_brute_force_on_random_usage(self):
        rng = random.Random(66)
        for _ in range(40):
            usage = [rng.randint(0, 40) for _ in range(rng.randint(1, 200))]
            od, cm = 100.0, rng.choice([40.0, 55.0, 70.0, 90.0])
            level, saving = optimal_commitment(usage, od, cm)
            costs = {L: commitment_cost(usage, L, od, cm) for L in range(0, max(usage) + 1)}
            best = min(costs.values())
            self.assertAlmostEqual(costs[level], best)
            self.assertEqual(level, min(L for L, c in costs.items() if abs(c - best) < 1e-9), "同じなら小さい方")
            self.assertAlmostEqual(saving, costs[0] - best)

    def test_step(self):
        level, _ = optimal_commitment(weekly_usage(), 100, 60, step=4)
        self.assertEqual(level % 4, 0)
        with self.assertRaises(ValueError):
            optimal_commitment([1.0], 100, 60, step=0)
        with self.assertRaises(ValueError):
            optimal_commitment([], 100, 60)


if __name__ == "__main__":
    unittest.main()
