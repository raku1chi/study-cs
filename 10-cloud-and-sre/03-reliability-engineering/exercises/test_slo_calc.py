"""10.3 SLO 計算機 — テスト

実行: python3 tools/check.py 10.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import unittest
from datetime import timedelta

from slo_calc import (
    AlertRule,
    BudgetStatus,
    allowed_downtime,
    burn_rate,
    composite,
    error_budget,
    evaluate_alerts,
    multiwindow_rules,
    nines,
    parallel,
    quorum,
    serial,
    threshold_for,
    window_sli,
)

WARMUP = 3 * 24 * 60  # 3 日の窓が埋まるまでの助走（分）


def synthetic(minutes, incidents=(), per_minute=1000):
    """毎分 per_minute 件。平常時は奇数分に 1 件のエラー（平均 0.05%、99.9% の SLO ならバーンレート 0.5）。

    incidents: [(開始分, 終了分（含まない）, エラー率)]
    """
    series = []
    for t in range(minutes):
        bad = 1 if t % 2 == 1 else 0
        for start, end, ratio in incidents:
            if start <= t < end:
                bad = round(per_minute * ratio)
        series.append((per_minute - bad, per_minute))
    return series


class TestExercise1Availability(unittest.TestCase):
    def test_serial(self):
        self.assertAlmostEqual(serial(0.999, 0.999), 0.998001)
        self.assertAlmostEqual(serial(0.9999), 0.9999)
        self.assertAlmostEqual(serial(0.999, 0.999, 0.9995), 0.9975019995)
        self.assertEqual(serial(1.0, 0.0), 0.0)

    def test_dependencies_cap_availability(self):
        # 直列の依存は、最も弱い部品より必ず低い
        self.assertLess(serial(0.9999, 0.999, 0.9999), 0.999)

    def test_parallel(self):
        self.assertAlmostEqual(parallel(0.99, 0.99), 0.9999)
        self.assertAlmostEqual(parallel(0.9, 0.9, 0.9), 0.999)
        self.assertAlmostEqual(parallel(0.5), 0.5)

    def test_quorum(self):
        self.assertAlmostEqual(quorum(2, [0.99, 0.99, 0.99]), 0.999702)
        self.assertAlmostEqual(quorum(3, [0.99] * 5), 0.9999901494, places=10)
        self.assertAlmostEqual(quorum(1, [0.9, 0.9]), parallel(0.9, 0.9), msg="1-of-n は並列と同じ")
        self.assertAlmostEqual(quorum(3, [0.9, 0.95, 0.99]), serial(0.9, 0.95, 0.99), msg="n-of-n は直列と同じ")
        self.assertAlmostEqual(quorum(2, [0.9, 0.95, 0.99]), 0.9936, msg="部品ごとに可用性が違ってもよい")

    def test_composite(self):
        structure = ("serial", [0.9999, ("parallel", [0.999, 0.999]), ("quorum", 2, [0.99, 0.99, 0.99])])
        expected = 0.9999 * (1 - 0.001 ** 2) * 0.999702
        self.assertAlmostEqual(composite(structure), expected)
        self.assertAlmostEqual(composite(0.95), 0.95)
        self.assertAlmostEqual(composite(("parallel", [("serial", [0.99, 0.99]), ("serial", [0.99, 0.99])])),
                               1 - (1 - 0.99 * 0.99) ** 2)

    def test_invalid(self):
        for bad in [(), (1.2,), (-0.1,), (True,), ("0.9",)]:
            with self.assertRaises(ValueError, msg=bad):
                serial(*bad)
            with self.assertRaises(ValueError, msg=bad):
                parallel(*bad)
        with self.assertRaises(ValueError):
            quorum(0, [0.9])
        with self.assertRaises(ValueError):
            quorum(3, [0.9, 0.9])
        for bad in [("serial",), ("mirror", [0.9]), ("quorum", 2, [0.9]), [0.9], "0.9", ("serial", [1.5])]:
            with self.assertRaises(ValueError, msg=bad):
                composite(bad)


class TestExercise2Budget(unittest.TestCase):
    def test_allowed_downtime(self):
        self.assertEqual(allowed_downtime(0.999), timedelta(minutes=43, seconds=12))
        self.assertEqual(allowed_downtime(0.99), timedelta(hours=7, minutes=12))
        self.assertEqual(allowed_downtime(0.9999, timedelta(days=365)), timedelta(minutes=52, seconds=33.6))
        self.assertEqual(allowed_downtime(1.0), timedelta(0))
        with self.assertRaises(ValueError):
            allowed_downtime(1.5)

    def test_nines(self):
        self.assertAlmostEqual(nines(0.999), 3.0)
        self.assertAlmostEqual(nines(0.9995), 3.30103, places=5)
        self.assertEqual(nines(1.0), math.inf)
        self.assertAlmostEqual(nines(0.0), 0.0)

    def test_error_budget(self):
        status = error_budget(0.999, good=999_400, total=1_000_000)
        self.assertIsInstance(status, BudgetStatus)
        self.assertEqual((status.total, status.bad), (1_000_000, 600))
        self.assertAlmostEqual(status.allowed_bad, 1000)
        self.assertAlmostEqual(status.consumed, 0.6)
        self.assertAlmostEqual(status.remaining, 0.4)

    def test_budget_can_be_overspent(self):
        status = error_budget(0.99, good=970, total=1000)
        self.assertAlmostEqual(status.consumed, 3.0)
        self.assertAlmostEqual(status.remaining, -2.0)

    def test_no_traffic(self):
        status = error_budget(0.999, good=0, total=0)
        self.assertEqual((status.consumed, status.remaining), (0.0, 1.0))

    def test_invalid_budget(self):
        for slo in (1.0, 0.0, 1.5, True):
            with self.assertRaises(ValueError, msg=slo):
                error_budget(slo, 10, 10)
        with self.assertRaises(ValueError):
            error_budget(0.99, good=11, total=10)
        with self.assertRaises(ValueError):
            error_budget(0.99, good=-1, total=10)

    def test_burn_rate(self):
        self.assertAlmostEqual(burn_rate(50, 1000, 0.999), 50.0)
        self.assertAlmostEqual(burn_rate(1, 1000, 0.999), 1.0, msg="SLO ちょうどのエラー率ならバーンレート 1")
        self.assertAlmostEqual(burn_rate(1, 100, 0.99), 1.0)
        self.assertEqual(burn_rate(0, 0, 0.999), 0.0)
        with self.assertRaises(ValueError):
            burn_rate(11, 10, 0.99)
        with self.assertRaises(ValueError):
            burn_rate(1, 10, 1.0)

    def test_window_sli(self):
        series = [(1000, 1000), (990, 1000), (1, 2), (0, 0), (1000, 1000)]
        # 1% のエラーの分は、閾値 1.5% なら良い分。2 件中 1 件の失敗（50%）の分は悪い分。トラフィック 0 の分は良い分
        self.assertAlmostEqual(window_sli(series, 0.015), 4 / 5)
        self.assertAlmostEqual(window_sli(series, 0.005), 3 / 5)
        with self.assertRaises(ValueError):
            window_sli([], 0.01)

    def test_request_vs_window_based(self):
        # 30 分間の全面停止: リクエストベースでは 30 分 × 1000 件、ウィンドウベースでは 30 分が悪い分
        month = synthetic(43_200, incidents=[(10_000, 10_030, 1.0)])
        total = sum(t for _, t in month)
        good = sum(g for g, _ in month)
        self.assertAlmostEqual(good / total, 1 - (30_000 + 21_585) / total)
        self.assertAlmostEqual(window_sli(month, 0.002), 1 - 30 / 43_200)


class TestExercise3Alerts(unittest.TestCase):
    def test_thresholds(self):
        self.assertAlmostEqual(threshold_for(0.02, 60), 14.4)
        self.assertAlmostEqual(threshold_for(0.05, 360), 6.0)
        self.assertAlmostEqual(threshold_for(0.10, 4320), 1.0)
        self.assertAlmostEqual(threshold_for(0.02, 60, period=28 * 24 * 60), 13.44)

    def test_multiwindow_rules(self):
        rules = multiwindow_rules()
        self.assertEqual([(r.name, r.long_window, r.short_window, r.severity) for r in rules], [
            ("page-1h", 60, 5, "page"), ("page-6h", 360, 30, "page"), ("ticket-3d", 4320, 360, "ticket"),
        ])
        for rule, expected in zip(rules, (14.4, 6.0, 1.0)):
            self.assertAlmostEqual(rule.threshold, expected)

    def test_small_hand_computed_example(self):
        # SLO 90%（許容エラー率 10%）、長い窓 4 分・短い窓 2 分、バーンレート 2 を超えたら発火
        series = [(10, 10), (10, 10), (5, 10), (5, 10), (10, 10), (10, 10), (10, 10), (10, 10)]
        rule = AlertRule("r", long_window=4, short_window=2, threshold=2.0)
        # t=2: 長い窓 5/30 → 1.67（発火しない）。t=3: 10/40 → 2.5 と 10/20 → 5（発火）
        # t=4: 10/40 → 2.5 と 5/20 → 2.5（発火）。t=5: 短い窓 0/20（止まる）
        self.assertEqual(evaluate_alerts(series, 0.9, [rule]), {"r": [(3, 5)]})

    def test_interval_open_at_the_end(self):
        series = [(10, 10), (0, 10), (0, 10)]
        rule = AlertRule("r", long_window=2, short_window=1, threshold=5.0)
        self.assertEqual(evaluate_alerts(series, 0.9, [rule]), {"r": [(1, 3)]})
        self.assertEqual(evaluate_alerts([], 0.9, [rule]), {"r": []})

    def test_quiet_baseline_never_alerts(self):
        series = synthetic(WARMUP + 2 * 1440)
        self.assertEqual(evaluate_alerts(series, 0.999, multiwindow_rules()),
                         {"page-1h": [], "page-6h": [], "ticket-3d": []})

    def test_full_outage_pages_fast_and_resets_fast(self):
        start, end = WARMUP + 600, WARMUP + 660
        series = synthetic(WARMUP + 1440, incidents=[(start, end, 1.0)])
        alerts = evaluate_alerts(series, 0.999, multiwindow_rules())
        (fire, stop), = alerts["page-1h"]
        self.assertLessEqual(fire - start, 1, "全面停止なら 1 分以内にページする")
        self.assertGreater(stop, end)
        self.assertLessEqual(stop - end, 5, "短い窓（5 分）があるので、回復後すぐに止まる")
        # 長い窓だけのアラートは、回復した後も 1 時間近く鳴り続ける
        (lfire, lstop), = evaluate_alerts(series, 0.999, [AlertRule("long-only", 60, 60, 14.4)])["long-only"]
        self.assertGreater(lstop - end, 45)

    def test_detection_time_depends_on_error_rate(self):
        delays = {}
        for ratio in (1.0, 0.1, 0.02):
            start = WARMUP + 600
            series = synthetic(WARMUP + 1440, incidents=[(start, start + 120, ratio)])
            fired = evaluate_alerts(series, 0.999, [multiwindow_rules()[0]])["page-1h"]
            delays[ratio] = fired[0][0] - start
        self.assertLessEqual(delays[1.0], 1)
        self.assertTrue(7 <= delays[0.1] <= 9, delays)    # 60 分 × 14.4 / 100 ≈ 8.6 分
        self.assertTrue(40 <= delays[0.02] <= 44, delays)  # 60 分 × 14.4 / 20 ≈ 43 分

    def test_slow_burn_opens_a_ticket_not_a_page(self):
        # エラー率 0.2%（バーンレート 2）が 2 日続く: 30 日の予算を 15 日で使い切るペース
        start = WARMUP
        series = synthetic(WARMUP + 3 * 1440, incidents=[(start, start + 2 * 1440, 0.002)])
        alerts = evaluate_alerts(series, 0.999, multiwindow_rules())
        self.assertEqual(alerts["page-1h"], [])
        self.assertEqual(alerts["page-6h"], [])
        self.assertTrue(alerts["ticket-3d"], "チケットは起票される")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            evaluate_alerts([(10, 10)], 1.0, multiwindow_rules())
        with self.assertRaises(ValueError):
            evaluate_alerts([(11, 10)], 0.99, multiwindow_rules())
        with self.assertRaises(ValueError):
            evaluate_alerts([(10, 10)], 0.99, [AlertRule("bad", 0, 1, 1.0)])


if __name__ == "__main__":
    unittest.main()
