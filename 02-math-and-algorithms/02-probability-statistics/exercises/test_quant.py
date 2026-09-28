"""2.2 確率・統計と定量的思考 — テスト

実行: python3 tools/check.py 2.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import statistics
import unittest
from fractions import Fraction

from quant import (
    AlertStats,
    alert_confusion,
    bayes_posterior,
    birthday_collision_approx,
    birthday_collision_exact,
    items_for_collision_probability,
    max_arrival_rate_for_latency,
    mean,
    median,
    mm1_metrics,
    per_call_budget,
    percentile,
    prob_at_least_one,
    sample_size_per_group,
    simulate_mm1,
    srm_p_value,
    stdev,
    two_proportion_ztest,
    variance,
)

LATENCIES = [12, 15, 11, 14, 13, 250, 12, 16, 13, 14]


# ---------------------------------------------------------------------------
# 演習1
# ---------------------------------------------------------------------------

class TestExercise1Descriptive(unittest.TestCase):
    def test_mean(self):
        self.assertAlmostEqual(mean([1, 2, 3, 4]), 2.5)
        self.assertAlmostEqual(mean(LATENCIES), 37.0)
        self.assertAlmostEqual(mean([5]), 5.0)
        self.assertAlmostEqual(mean([0.1] * 10), 0.1)

    def test_median(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([4, 1, 3, 2]), 2.5)
        self.assertEqual(median([7]), 7)
        self.assertEqual(median(LATENCIES), 13.5)
        data = [5, 3, 9, 1]
        median(data)
        self.assertEqual(data, [5, 3, 9, 1], "入力のリストを変更しないこと（sorted() を使う）")

    def test_mean_vs_median_on_skewed_latency(self):
        # 1 件の外れ値で平均は 37 ms に引っ張られるが、中央値は 13.5 ms のまま
        self.assertGreater(mean(LATENCIES), 2.5 * median(LATENCIES))

    def test_percentile_examples(self):
        self.assertAlmostEqual(percentile(LATENCIES, 50), 13.5)
        self.assertAlmostEqual(percentile(LATENCIES, 90), 39.4)
        self.assertAlmostEqual(percentile(LATENCIES, 99), 228.94)
        self.assertAlmostEqual(percentile(LATENCIES, 0), 11)
        self.assertAlmostEqual(percentile(LATENCIES, 100), 250)
        self.assertAlmostEqual(percentile([42], 99), 42)
        self.assertAlmostEqual(percentile([1, 2], 25), 1.25)

    def test_percentile_matches_linear_interpolation(self):
        rng = random.Random(1)
        for _ in range(100):
            data = [rng.lognormvariate(3, 1) for _ in range(rng.randrange(2, 60))]
            expected = statistics.quantiles(data, n=100, method="inclusive")
            for i in range(1, 100):
                self.assertAlmostEqual(percentile(data, i), expected[i - 1], places=9, msg=(len(data), i))

    def test_percentile_definition_is_not_exclusive(self):
        # statistics.quantiles の既定（exclusive）では p90 = 226.6 になる。定義の違いに注意
        self.assertAlmostEqual(statistics.quantiles(LATENCIES, n=10)[8], 226.6)
        self.assertAlmostEqual(percentile(LATENCIES, 90), 39.4, msg="線形補間（inclusive / NumPy の既定）で計算すること")

    def test_variance_and_stdev(self):
        self.assertAlmostEqual(variance([4, 7, 13, 16]), 30.0)
        self.assertAlmostEqual(variance([4, 7, 13, 16], sample=False), 22.5)
        self.assertAlmostEqual(stdev([4, 7, 13, 16]), math.sqrt(30))
        self.assertAlmostEqual(stdev([4, 7, 13, 16], sample=False), math.sqrt(22.5))
        self.assertAlmostEqual(variance([3.0], sample=False), 0.0)
        rng = random.Random(2)
        for _ in range(50):
            data = [rng.gauss(10, 3) for _ in range(rng.randrange(2, 100))]
            self.assertAlmostEqual(variance(data), statistics.variance(data), places=9)
            self.assertAlmostEqual(variance(data, sample=False), statistics.pvariance(data), places=9)

    def test_variance_is_numerically_stable(self):
        big = [1e9 + x for x in (4, 7, 13, 16)]
        self.assertAlmostEqual(
            variance(big), 30.0, places=6,
            msg="「2 乗の平均 − 平均の 2 乗」は桁落ちする。平均を先に求めてから偏差の 2 乗を足すこと",
        )
        self.assertAlmostEqual(variance(big, sample=False), 22.5, places=6)

    def test_invalid(self):
        for func in (mean, median):
            with self.assertRaises(ValueError, msg=func.__name__):
                func([])
        for p in (-1, 100.5):
            with self.assertRaises(ValueError, msg=p):
                percentile([1, 2, 3], p)
        with self.assertRaises(ValueError):
            percentile([], 50)
        with self.assertRaises(ValueError):
            variance([1.0])  # 標本分散には 2 個以上必要
        with self.assertRaises(ValueError):
            variance([], sample=False)
        with self.assertRaises(ValueError):
            stdev([1.0])


# ---------------------------------------------------------------------------
# 演習2
# ---------------------------------------------------------------------------

class TestExercise2TailsAndCollisions(unittest.TestCase):
    def test_prob_at_least_one(self):
        self.assertAlmostEqual(prob_at_least_one(0.01, 1), 0.01)
        self.assertAlmostEqual(prob_at_least_one(0.01, 10), 1 - 0.99**10)
        self.assertAlmostEqual(prob_at_least_one(0.01, 100), 0.6339676587267709, places=12)
        self.assertEqual(prob_at_least_one(0.3, 0), 0.0)
        self.assertEqual(prob_at_least_one(0.0, 1000), 0.0)
        self.assertEqual(prob_at_least_one(1.0, 3), 1.0)

    def test_prob_at_least_one_tiny_probability(self):
        value = prob_at_least_one(1e-18, 1000)
        self.assertGreater(value, 0.0, "(1 - 1e-18) は 1.0 に丸められる。log1p と expm1 を使うこと")
        self.assertAlmostEqual(value / 1e-15, 1.0, places=9)

    def test_per_call_budget(self):
        q = per_call_budget(0.01, 100)
        self.assertAlmostEqual(q, 1.0049830824165884e-4, places=15)
        self.assertAlmostEqual(prob_at_least_one(q, 100), 0.01, places=12)
        self.assertAlmostEqual(per_call_budget(0.25, 1), 0.25)
        self.assertEqual(per_call_budget(0.0, 50), 0.0)
        for target in (0.001, 0.05, 0.5, 0.9):
            for n in (2, 10, 1000):
                self.assertAlmostEqual(prob_at_least_one(per_call_budget(target, n), n), target, places=12)

    def test_birthday_exact(self):
        self.assertAlmostEqual(birthday_collision_exact(23, 365), 0.5072972343239857, places=12)
        self.assertEqual(birthday_collision_exact(0, 365), 0.0)
        self.assertEqual(birthday_collision_exact(1, 365), 0.0)
        self.assertEqual(birthday_collision_exact(366, 365), 1.0, "n > m なら鳩の巣原理で必ず衝突")
        self.assertAlmostEqual(birthday_collision_exact(2, 1000), 1 / 1000)
        for n, m in [(10, 100), (30, 1000), (57, 365), (200, 10**6)]:
            no_collision = Fraction(1)
            for i in range(n):
                no_collision *= Fraction(m - i, m)
            self.assertAlmostEqual(birthday_collision_exact(n, m), float(1 - no_collision), places=12, msg=(n, m))

    def test_birthday_approx(self):
        self.assertAlmostEqual(birthday_collision_approx(23, 365), 1 - math.exp(-23 * 22 / 730), places=12)
        uuid = birthday_collision_approx(10**12, 2**122)
        self.assertAlmostEqual(uuid / 9.403954806568455e-14, 1.0, places=9, msg="UUIDv4 を 1 兆個（1 - exp(-x) ではなく -expm1(-x) で計算すること）")
        tiny = birthday_collision_approx(10**9, 2**122)
        self.assertGreater(tiny, 0.0, "expm1 を使えば 1e-20 程度の確率も表せる")
        self.assertAlmostEqual(tiny / 9.403954797174345e-20, 1.0, places=9)
        self.assertEqual(birthday_collision_approx(0, 10), 0.0)
        self.assertEqual(birthday_collision_approx(1, 10), 0.0)
        # m が大きいとき、近似は厳密な値によく一致する
        self.assertAlmostEqual(birthday_collision_approx(1000, 10**9), birthday_collision_exact(1000, 10**9), places=6)

    def test_items_for_collision_probability(self):
        self.assertEqual(items_for_collision_probability(0.5, 365), 23)
        self.assertEqual(items_for_collision_probability(0.5, 2**32), 77164)
        cases = [(0.5, 365), (0.01, 10**6), (0.99, 10**4), (0.5, 62**6), (1e-6, 2**40), (0.5, 10**12), (0.9, 1)]
        for p, m in cases:
            n = items_for_collision_probability(p, m)
            self.assertGreaterEqual(birthday_collision_approx(n, m), p, (p, m, n))
            self.assertLess(birthday_collision_approx(n - 1, m), p, f"最小の n ではない: {(p, m, n)}")

    def test_items_for_collision_uuid(self):
        n = items_for_collision_probability(0.5, 2**122)
        expected = math.sqrt(2 * 2**122 * math.log(2))  # ≈ 2.7e18
        self.assertAlmostEqual(n / expected, 1.0, places=9)

    def test_invalid(self):
        for args in [(-0.1, 5), (1.1, 5), (0.5, -1)]:
            with self.assertRaises(ValueError, msg=args):
                prob_at_least_one(*args)
        for args in [(-0.1, 5), (1.1, 5), (0.5, 0)]:
            with self.assertRaises(ValueError, msg=args):
                per_call_budget(*args)
        for func in (birthday_collision_exact, birthday_collision_approx):
            for args in [(-1, 10), (5, 0)]:
                with self.assertRaises(ValueError, msg=(func.__name__, args)):
                    func(*args)
        for args in [(0.0, 10), (1.0, 10), (-0.5, 10), (0.5, 0)]:
            with self.assertRaises(ValueError, msg=args):
                items_for_collision_probability(*args)


# ---------------------------------------------------------------------------
# 演習3
# ---------------------------------------------------------------------------

class TestExercise3Bayes(unittest.TestCase):
    def test_monitoring_alert_example(self):
        # 本文 1.3 節: 障害の基準率 0.1%、感度 99%、偽陽性率 1% → 適合率は約 9%
        self.assertAlmostEqual(bayes_posterior(0.001, 0.99, 0.01), 0.00099 / (0.00099 + 0.00999), places=12)

    def test_edge_cases(self):
        self.assertEqual(bayes_posterior(0.0, 0.99, 0.01), 0.0)
        self.assertEqual(bayes_posterior(1.0, 0.99, 0.01), 1.0)
        self.assertEqual(bayes_posterior(0.2, 0.5, 0.0), 1.0, "偽陽性がなければ、鳴ったら必ず本物")
        self.assertAlmostEqual(bayes_posterior(0.3, 0.7, 0.7), 0.3, msg="感度 = 偽陽性率なら、アラートは情報を持たない")

    def test_improving_fpr_beats_improving_sensitivity_at_low_base_rate(self):
        base = bayes_posterior(0.001, 0.90, 0.01)
        better_sensitivity = bayes_posterior(0.001, 0.99, 0.01)
        better_fpr = bayes_posterior(0.001, 0.90, 0.001)
        self.assertGreater(better_fpr - base, 5 * (better_sensitivity - base))

    def test_alert_confusion(self):
        s = alert_confusion(1_000_000, 0.00001, 0.99, 0.001)
        self.assertIsInstance(s, AlertStats)
        self.assertAlmostEqual(s.true_positives, 9.9)
        self.assertAlmostEqual(s.false_negatives, 0.1)
        self.assertAlmostEqual(s.false_positives, 999.99)
        self.assertAlmostEqual(s.true_negatives, 998_990.01, places=4)
        self.assertAlmostEqual(s.precision, 9.9 / (9.9 + 999.99))
        total = s.true_positives + s.false_positives + s.false_negatives + s.true_negatives
        self.assertAlmostEqual(total, 1_000_000)

    def test_alert_confusion_agrees_with_bayes(self):
        rng = random.Random(3)
        for _ in range(200):
            base, sens, fpr = rng.random() * 0.1, rng.random(), rng.random() * 0.1
            s = alert_confusion(10_000, base, sens, fpr)
            if s.true_positives + s.false_positives > 0:
                self.assertAlmostEqual(s.precision, bayes_posterior(base, sens, fpr), places=9)

    def test_no_alerts_gives_nan_precision(self):
        s = alert_confusion(1000, 0.0, 0.9, 0.0)
        self.assertTrue(math.isnan(s.precision))

    def test_invalid(self):
        for args in [(-0.1, 0.9, 0.1), (0.1, 1.5, 0.1), (0.1, 0.9, -0.01)]:
            with self.assertRaises(ValueError, msg=args):
                bayes_posterior(*args)
        with self.assertRaises(ValueError, msg="P(E) = 0"):
            bayes_posterior(0.0, 0.9, 0.0)
        with self.assertRaises(ValueError):
            alert_confusion(-1, 0.1, 0.9, 0.1)
        with self.assertRaises(ValueError):
            alert_confusion(100, 1.2, 0.9, 0.1)


# ---------------------------------------------------------------------------
# 演習4
# ---------------------------------------------------------------------------

class TestExercise4ABTest(unittest.TestCase):
    def test_example(self):
        r = two_proportion_ztest(1000, 10_000, 1100, 10_000)
        self.assertAlmostEqual(r.rate_a, 0.10)
        self.assertAlmostEqual(r.rate_b, 0.11)
        self.assertAlmostEqual(r.diff, 0.01)
        self.assertAlmostEqual(r.z, 2.3066, places=4)
        self.assertAlmostEqual(r.p_value, 0.021075, places=5)
        self.assertAlmostEqual(r.ci_low, 0.0015041, places=6)
        self.assertAlmostEqual(r.ci_high, 0.0184959, places=6)

    def test_same_rates_smaller_sample_is_not_significant(self):
        r = two_proportion_ztest(100, 1000, 110, 1000)
        self.assertAlmostEqual(r.diff, 0.01)
        self.assertGreater(r.p_value, 0.4)
        # 「有意でない」≠「効果がない」: 区間は 0 をまたぐが、+3.7 ポイントの効果も否定できないほど広い
        self.assertLess(r.ci_low, 0)
        self.assertGreater(r.ci_high, 0.03)

    def test_symmetry_and_alpha(self):
        r1 = two_proportion_ztest(1000, 10_000, 1100, 10_000)
        r2 = two_proportion_ztest(1100, 10_000, 1000, 10_000)
        self.assertAlmostEqual(r1.z, -r2.z)
        self.assertAlmostEqual(r1.p_value, r2.p_value)
        r99 = two_proportion_ztest(1000, 10_000, 1100, 10_000, alpha=0.01)
        self.assertLess(r99.ci_low, r1.ci_low, "信頼水準 99% の区間は 95% より広い")
        self.assertGreater(r99.ci_high, r1.ci_high)
        self.assertAlmostEqual(r99.p_value, r1.p_value, msg="p 値は alpha に依存しない")

    def test_unequal_group_sizes(self):
        r = two_proportion_ztest(300, 5000, 700, 10_000)
        pooled = 1000 / 15_000
        se0 = math.sqrt(pooled * (1 - pooled) * (1 / 5000 + 1 / 10_000))
        self.assertAlmostEqual(r.z, (0.07 - 0.06) / se0)

    def test_null_hypothesis_false_positive_rate(self):
        # 差のない A/A テストを繰り返すと、p < 0.05 になる割合は約 5%
        rng = random.Random(4)
        hits = 0
        trials = 400
        for _ in range(trials):
            ca = sum(rng.random() < 0.2 for _ in range(1000))
            cb = sum(rng.random() < 0.2 for _ in range(1000))
            hits += two_proportion_ztest(ca, 1000, cb, 1000).p_value < 0.05
        self.assertLess(abs(hits / trials - 0.05), 0.035)

    def test_invalid(self):
        bad = [(0, 0, 1, 10), (11, 10, 1, 10), (-1, 10, 1, 10), (1, 10, 1, 0)]
        for args in bad:
            with self.assertRaises(ValueError, msg=args):
                two_proportion_ztest(*args)
        with self.assertRaises(ValueError):
            two_proportion_ztest(1, 10, 2, 10, alpha=1.5)
        with self.assertRaises(ValueError, msg="両群とも率 0 では検定できない"):
            two_proportion_ztest(0, 100, 0, 100)

    def test_sample_size(self):
        self.assertEqual(sample_size_per_group(0.10, 0.01), 14751)
        self.assertEqual(sample_size_per_group(0.10, 0.02), 3841)
        self.assertEqual(sample_size_per_group(0.10, 0.005), 57763)
        self.assertEqual(sample_size_per_group(0.02, 0.002), 80682)
        self.assertEqual(sample_size_per_group(0.10, 0.01, power=0.9), 19747)
        self.assertEqual(sample_size_per_group(0.10, 0.01, alpha=0.01), 21950)

    def test_sample_size_scaling(self):
        # 検出したい差を半分にすると、必要なサンプルはおよそ 4 倍
        n1 = sample_size_per_group(0.30, 0.02)
        n2 = sample_size_per_group(0.30, 0.01)
        self.assertAlmostEqual(n2 / n1, 4, delta=0.2)
        # ざっくり公式 n ≈ 16 p(1-p) / mde^2（α=0.05, 検出力 80%）とも近い
        self.assertAlmostEqual(sample_size_per_group(0.5, 0.01) / (16 * 0.25 / 0.01**2), 1, delta=0.03)

    def test_sample_size_invalid(self):
        for args in [(0.0, 0.01), (0.99, 0.02), (0.1, 0.0), (0.1, -0.2)]:
            with self.assertRaises(ValueError, msg=args):
                sample_size_per_group(*args)
        with self.assertRaises(ValueError):
            sample_size_per_group(0.1, 0.01, power=1.0)

    def test_srm(self):
        self.assertAlmostEqual(srm_p_value(50_000, 49_000), 0.0014819, places=6)
        self.assertAlmostEqual(srm_p_value(50_000, 49_800), 0.52668, places=4)
        self.assertAlmostEqual(srm_p_value(1000, 1000), 1.0)
        self.assertAlmostEqual(srm_p_value(90_000, 10_000, expected_share_a=0.9), 1.0)
        self.assertLess(srm_p_value(50_000, 50_000, expected_share_a=0.52), 1e-30)
        for args in [(-1, 10), (0, 0)]:
            with self.assertRaises(ValueError, msg=args):
                srm_p_value(*args)
        with self.assertRaises(ValueError):
            srm_p_value(10, 10, expected_share_a=1.0)


# ---------------------------------------------------------------------------
# 演習5
# ---------------------------------------------------------------------------

def reference_mm1(arrival_rate, service_rate, num_customers, seed):
    """テスト用の参照実装（リンドレーの漸化式）。仕様どおりの順序で乱数を引く。"""
    rng = random.Random(seed)
    arrivals, services = [], []
    t = 0.0
    for _ in range(num_customers):
        t += rng.expovariate(arrival_rate)
        arrivals.append(t)
        services.append(rng.expovariate(service_rate))
    departures, waits = [], []
    free_at = 0.0
    for a, s in zip(arrivals, services):
        start = max(a, free_at)
        waits.append(start - a)
        free_at = start + s
        departures.append(free_at)
    duration = departures[-1]
    sojourns = [d - a for a, d in zip(arrivals, departures)]
    # 系内人数の最大値: 到着と退去を時刻順に合わせて数える（同時刻なら退去が先）
    events = sorted([(a, 1) for a in arrivals] + [(d, 0) for d in departures])
    count = max_count = 0
    for _, kind in events:
        count += 1 if kind else -1
        max_count = max(max_count, count)
    return {
        "duration": duration,
        "mean_wait": sum(waits) / num_customers,
        "mean_sojourn": sum(sojourns) / num_customers,
        "mean_in_system": sum(sojourns) / duration,
        "utilization": sum(services) / duration,
        "max_in_system": max_count,
    }


class TestExercise5Queueing(unittest.TestCase):
    def test_mm1_formulas(self):
        m = mm1_metrics(80, 100)
        self.assertAlmostEqual(m.utilization, 0.8)
        self.assertAlmostEqual(m.mean_sojourn, 0.05)
        self.assertAlmostEqual(m.mean_wait, 0.04)
        self.assertAlmostEqual(m.mean_in_system, 4.0)
        self.assertAlmostEqual(m.mean_in_queue, 3.2)

    def test_littles_law_and_hockey_stick(self):
        mu = 100.0
        previous = 0.0
        for rho in (0.5, 0.7, 0.8, 0.9, 0.95, 0.99):
            m = mm1_metrics(rho * mu, mu)
            self.assertAlmostEqual(m.mean_in_system, rho * mu * m.mean_sojourn, msg="L = λW")
            self.assertAlmostEqual(m.mean_in_queue, rho * mu * m.mean_wait, msg="Lq = λWq")
            self.assertAlmostEqual(m.mean_sojourn, m.mean_wait + 1 / mu, msg="W = Wq + 1/μ")
            self.assertAlmostEqual(m.mean_sojourn, (1 / mu) / (1 - rho))
            self.assertGreater(m.mean_sojourn, previous)
            previous = m.mean_sojourn
        # 利用率 90% → 99% で平均滞在時間は 10 倍になる
        self.assertAlmostEqual(mm1_metrics(99, 100).mean_sojourn / mm1_metrics(90, 100).mean_sojourn, 10)

    def test_mm1_invalid(self):
        for args in [(100, 100), (120, 100), (0, 100), (10, 0), (-1, 5)]:
            with self.assertRaises(ValueError, msg=args):
                mm1_metrics(*args)

    def test_max_arrival_rate_for_latency(self):
        self.assertAlmostEqual(max_arrival_rate_for_latency(100, 0.05), 80.0)
        lam = max_arrival_rate_for_latency(250, 0.02)
        self.assertAlmostEqual(mm1_metrics(lam, 250).mean_sojourn, 0.02)
        for args in [(100, 0.01), (100, 0.005), (0, 1), (100, 0)]:
            with self.assertRaises(ValueError, msg=args):
                max_arrival_rate_for_latency(*args)

    def assert_matches_reference(self, lam, mu, n, seed):
        r = simulate_mm1(lam, mu, n, seed)
        ref = reference_mm1(lam, mu, n, seed)
        self.assertEqual(r.num_customers, n)
        for key in ("duration", "mean_wait", "mean_sojourn", "mean_in_system", "utilization"):
            value, expected = getattr(r, key), ref[key]
            msg = f"{key} = {value}、期待値 {expected}（乱数を引く順序は docstring の仕様どおりに）"
            if expected == 0:
                self.assertEqual(value, 0, msg)
            else:
                self.assertAlmostEqual(value / expected, 1.0, places=9, msg=msg)
        self.assertEqual(r.max_in_system, ref["max_in_system"])

    def test_simulation_matches_reference(self):
        self.assert_matches_reference(0.7, 1.0, 2000, seed=7)
        self.assert_matches_reference(5.0, 4.0, 500, seed=8)   # 過負荷（ρ > 1）
        self.assert_matches_reference(1.0, 3.0, 1, seed=9)     # 客が 1 人だけ

    def test_single_customer(self):
        r = simulate_mm1(1.0, 2.0, 1, seed=3)
        self.assertEqual(r.mean_wait, 0.0)
        self.assertEqual(r.max_in_system, 1)
        self.assertAlmostEqual(r.mean_in_system, r.utilization, msg="1 人なら系内人数 = 処理中かどうか")

    def test_reproducible(self):
        a = simulate_mm1(0.9, 1.0, 3000, seed=42)
        b = simulate_mm1(0.9, 1.0, 3000, seed=42)
        c = simulate_mm1(0.9, 1.0, 3000, seed=43)
        self.assertEqual(a, b, "同じ seed なら同じ結果になること")
        self.assertNotEqual(a.mean_sojourn, c.mean_sojourn)

    def test_littles_law_on_sample_path(self):
        # 空で始まり空で終わる観測では、L = (観測期間の到着率) × W が厳密に成り立つ
        for lam, mu, seed in [(0.5, 1.0, 1), (0.95, 1.0, 2), (1.5, 1.0, 3)]:
            r = simulate_mm1(lam, mu, 5000, seed)
            throughput = r.num_customers / r.duration
            self.assertAlmostEqual(r.mean_in_system / (throughput * r.mean_sojourn), 1.0, places=9)
            self.assertAlmostEqual(r.mean_sojourn - r.mean_wait, 1 / mu, delta=0.1 / mu, msg="W - Wq ≈ 1/μ")

    def check_against_theory(self, lam, mu, n, seed, tol):
        theory = mm1_metrics(lam, mu)
        r = simulate_mm1(lam, mu, n, seed)
        for key, t in (("mean_sojourn", tol["W"]), ("mean_wait", tol["Wq"]),
                       ("mean_in_system", tol["L"]), ("utilization", tol["U"])):
            expected = getattr(theory, key)
            self.assertLess(abs(getattr(r, key) - expected) / expected, t,
                            f"ρ={lam / mu}: {key} = {getattr(r, key):.4f}、理論値 {expected:.4f}")

    def test_converges_to_theory_at_50_percent(self):
        self.check_against_theory(0.5, 1.0, 100_000, seed=11, tol={"W": 0.06, "Wq": 0.10, "L": 0.07, "U": 0.03})

    def test_converges_to_theory_at_80_percent(self):
        self.check_against_theory(0.8, 1.0, 200_000, seed=12, tol={"W": 0.10, "Wq": 0.12, "L": 0.10, "U": 0.03})

    def test_overload_grows_without_bound(self):
        r = simulate_mm1(1.2, 1.0, 5000, seed=5)
        self.assertGreater(r.max_in_system, 400, "ρ > 1 では待ち行列が伸び続ける")
        self.assertGreater(r.utilization, 0.97)

    def test_simulate_invalid(self):
        for args in [(0, 1, 10, 1), (1, 0, 10, 1), (1, 2, 0, 1)]:
            with self.assertRaises(ValueError, msg=args):
                simulate_mm1(*args)


if __name__ == "__main__":
    unittest.main()
