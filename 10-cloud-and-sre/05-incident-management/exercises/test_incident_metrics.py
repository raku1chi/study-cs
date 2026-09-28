"""10.5 インシデントの指標と SLA のクレジット — テスト

実行: python3 tools/check.py 10.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from datetime import timedelta

from incident_metrics import (
    Incident,
    credit_yen,
    downtime,
    durations,
    month_range,
    monthly_downtime,
    percentile,
    sla_credit_percent,
    summarize,
    uptime_percent,
    utc,
)

TIERS = [(99.9, 10), (99.0, 25), (95.0, 100)]  # 稼働率がこれを下回ったら、月額のこの % を返金（例）


def make(iid, severity, start_min, ttd, tta, ttm, ttr):
    s = utc(2026, 7, 1) + timedelta(minutes=start_min)
    return Incident(iid, severity, s, s + timedelta(minutes=ttd), s + timedelta(minutes=ttd + tta),
                    s + timedelta(minutes=ttm), s + timedelta(minutes=ttr))


INCIDENTS = [
    make("INC-1", "SEV2", 0, ttd=5, tta=2, ttm=30, ttr=60),
    make("INC-2", "SEV2", 1000, ttd=3, tta=1, ttm=12, ttr=40),
    make("INC-3", "SEV1", 2000, ttd=1, tta=1, ttm=45, ttr=120),
    make("INC-4", "SEV2", 3000, ttd=10, tta=5, ttm=600, ttr=900),   # 裾の長い 1 件
    make("INC-5", "SEV3", 4000, ttd=30, tta=20, ttm=90, ttr=300),
    make("INC-6", "SEV2", 5000, ttd=4, tta=3, ttm=20, ttr=35),
]


class TestExercise1Durations(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(durations(INCIDENTS[0]), {"ttd": 5.0, "tta": 2.0, "ttm": 30.0, "ttr": 60.0})
        d = durations(INCIDENTS[4])
        self.assertEqual((d["ttd"], d["tta"]), (30.0, 20.0))

    def test_seconds_are_fractional_minutes(self):
        s = utc(2026, 7, 1)
        inc = Incident("x", "SEV3", s, s + timedelta(seconds=90), s + timedelta(seconds=120),
                       s + timedelta(minutes=5), s + timedelta(minutes=5))
        self.assertEqual(durations(inc), {"ttd": 1.5, "tta": 0.5, "ttm": 5.0, "ttr": 5.0})

    def test_auto_mitigation_before_ack_is_allowed(self):
        s = utc(2026, 7, 1)
        inc = Incident("auto", "SEV3", s, s + timedelta(minutes=1), s + timedelta(minutes=10),
                       s + timedelta(minutes=3), s + timedelta(minutes=20))
        self.assertEqual(durations(inc)["ttm"], 3.0, "自動ロールバックで応答より先に緩和されることもある")

    def test_invalid_order(self):
        s = utc(2026, 7, 1)
        bad = [
            Incident("a", "SEV2", s, s - timedelta(minutes=1), s, s, s),
            Incident("b", "SEV2", s, s + timedelta(minutes=5), s + timedelta(minutes=1), s, s),
            Incident("c", "SEV2", s, s, s, s + timedelta(minutes=5), s + timedelta(minutes=1)),
        ]
        for inc in bad:
            with self.assertRaises(ValueError, msg=inc.id):
                durations(inc)

    def test_percentile(self):
        values = [30, 12, 600, 20]
        self.assertEqual(percentile(values, 50), 20)
        self.assertEqual(percentile(values, 90), 600)
        self.assertEqual(percentile([5], 90), 5)
        with self.assertRaises(ValueError):
            percentile([], 90)
        with self.assertRaises(ValueError):
            percentile([1], 101)

    def test_summarize_by_severity(self):
        summary = summarize(INCIDENTS, "ttm")
        self.assertEqual(list(summary), ["ALL", "SEV1", "SEV2", "SEV3"])
        sev2 = summary["SEV2"]
        self.assertEqual(sev2["count"], 4)
        self.assertEqual(sev2["median"], 25.0, "偶数個なら中央の 2 つの平均（20 と 30）")
        self.assertEqual(sev2["p90"], 600.0)
        self.assertAlmostEqual(sev2["mean"], 165.5)
        self.assertEqual(sev2["max"], 600.0)
        self.assertEqual(summary["ALL"]["count"], 6)

    def test_mean_is_misleading_for_heavy_tails(self):
        sev2 = summarize(INCIDENTS, "ttm")["SEV2"]
        self.assertGreater(sev2["mean"], 5 * sev2["median"], "1 件の長いインシデントが平均を 6 倍以上に引き上げる")

    def test_summarize_invalid_metric(self):
        with self.assertRaises(ValueError):
            summarize(INCIDENTS, "mttr")


class TestExercise2Sla(unittest.TestCase):
    def test_month_range(self):
        self.assertEqual(month_range(2026, 9), (utc(2026, 9, 1), utc(2026, 10, 1)))
        self.assertEqual(month_range(2026, 12), (utc(2026, 12, 1), utc(2027, 1, 1)))
        start, end = month_range(2028, 2)
        self.assertEqual(end - start, timedelta(days=29), "うるう年の 2 月")

    def test_overlaps_are_not_double_counted(self):
        s = utc(2026, 9, 10, 12)
        intervals = [(s, s + timedelta(minutes=30)), (s + timedelta(minutes=20), s + timedelta(minutes=50)),
                     (s + timedelta(hours=5), s + timedelta(hours=5, minutes=10))]
        self.assertEqual(downtime(intervals, *month_range(2026, 9)), timedelta(minutes=60))

    def test_clipped_to_month(self):
        # 9/30 23:50 から 10/1 00:20 までの停止は、9 月に 10 分、10 月に 20 分
        interval = [(utc(2026, 9, 30, 23, 50), utc(2026, 10, 1, 0, 20))]
        self.assertEqual(monthly_downtime(interval, 2026, 9), timedelta(minutes=10))
        self.assertEqual(monthly_downtime(interval, 2026, 10), timedelta(minutes=20))
        self.assertEqual(monthly_downtime(interval, 2026, 11), timedelta(0))

    def test_invalid_interval(self):
        with self.assertRaises(ValueError):
            monthly_downtime([(utc(2026, 9, 2), utc(2026, 9, 1))], 2026, 9)

    def test_uptime_percent(self):
        self.assertAlmostEqual(uptime_percent(timedelta(minutes=43, seconds=12), timedelta(days=30)), 99.9)
        self.assertEqual(uptime_percent(timedelta(0), timedelta(days=30)), 100.0)
        with self.assertRaises(ValueError):
            uptime_percent(timedelta(days=31), timedelta(days=30))

    def test_credit_tiers_and_boundaries(self):
        month = timedelta(days=30)
        self.assertEqual(sla_credit_percent(timedelta(0), month, TIERS), 0)
        self.assertEqual(sla_credit_percent(timedelta(minutes=43, seconds=12), month, TIERS), 0,
                         "ちょうど 99.9% は「下回った」ではない")
        self.assertEqual(sla_credit_percent(timedelta(minutes=43, seconds=13), month, TIERS), 10)
        self.assertEqual(sla_credit_percent(timedelta(hours=7, minutes=12), month, TIERS), 10, "ちょうど 99.0%")
        self.assertEqual(sla_credit_percent(timedelta(hours=8), month, TIERS), 25)
        self.assertEqual(sla_credit_percent(timedelta(days=2), month, TIERS), 100)

    def test_month_length_matters(self):
        # 44 分の停止: 30 日の月なら 99.9% を下回るが、31 日の月なら下回らない
        down = timedelta(minutes=44)
        self.assertEqual(sla_credit_percent(down, timedelta(days=30), TIERS), 10)
        self.assertEqual(sla_credit_percent(down, timedelta(days=31), TIERS), 0)
        self.assertEqual(sla_credit_percent(timedelta(minutes=41), timedelta(days=28), TIERS), 10, "2 月は許容が 40.32 分")

    def test_tier_order_does_not_matter(self):
        self.assertEqual(sla_credit_percent(timedelta(hours=8), timedelta(days=30), list(reversed(TIERS))), 25)

    def test_credit_yen(self):
        self.assertEqual(credit_yen(300_000, 10), 30_000)
        self.assertEqual(credit_yen(99_999, 25), 24_999, "円未満は切り捨て")
        self.assertEqual(credit_yen(50_000, 0), 0)
        with self.assertRaises(ValueError):
            credit_yen(1000, 120)
        with self.assertRaises(ValueError):
            credit_yen(-1, 10)

    def test_end_to_end_monthly_credit(self):
        intervals = [
            (utc(2026, 9, 3, 1, 0), utc(2026, 9, 3, 1, 25)),
            (utc(2026, 9, 3, 1, 20), utc(2026, 9, 3, 1, 40)),   # 前と重なる
            (utc(2026, 9, 18, 10, 0), utc(2026, 9, 18, 10, 12)),
        ]
        down = monthly_downtime(intervals, 2026, 9)
        self.assertEqual(down, timedelta(minutes=52))
        start, end = month_range(2026, 9)
        percent = sla_credit_percent(down, end - start, TIERS)
        self.assertEqual((percent, credit_yen(480_000, percent)), (10, 48_000))


if __name__ == "__main__":
    unittest.main()
