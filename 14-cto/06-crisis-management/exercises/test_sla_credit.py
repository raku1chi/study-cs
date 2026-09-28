"""14.6 危機管理 — テスト

実行: python3 tools/check.py 14.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

from sla_credit import (
    Contract,
    Plan,
    availability_percent,
    billing_period,
    compute_credits,
    credit_percent,
    downtime_in_period,
    merge_windows,
)

JST = timezone(timedelta(hours=9), "JST")
UTC = timezone.utc


def jst(month, day, hour, minute=0, second=0, year=2026):
    return datetime(year, month, day, hour, minute, second, tzinfo=JST)


STANDARD = Plan("standard", (("99.5", 10), ("99.0", 25), ("95.0", 50)), cap_percent=50)
ENTERPRISE = Plan("enterprise", (("99.95", 10), ("99.9", 25), ("99.0", 50), ("95.0", 100)))
PLANS = {"standard": STANDARD, "enterprise": ENTERPRISE}


class TestExercise1MergeWindows(unittest.TestCase):
    def test_overlapping_windows_are_merged_and_sorted(self):
        a = (jst(6, 10, 14, 0), jst(6, 10, 14, 30))
        b = (jst(6, 10, 14, 20), jst(6, 10, 15, 10))
        c = (jst(6, 3, 9, 0), jst(6, 3, 9, 5))
        self.assertEqual(merge_windows([a, b, c]), [c, (a[0], b[1])])

    def test_touching_windows_are_merged(self):
        # 半開区間 [s, e) なので、e と次の s が同じなら連続した 1 つの障害
        a = (jst(6, 1, 10), jst(6, 1, 11))
        b = (jst(6, 1, 11), jst(6, 1, 12))
        self.assertEqual(merge_windows([b, a]), [(a[0], b[1])])

    def test_nested_and_duplicate_windows(self):
        outer = (jst(6, 1, 10), jst(6, 1, 18))
        inner = (jst(6, 1, 12), jst(6, 1, 13))
        self.assertEqual(merge_windows([inner, outer, outer]), [outer])

    def test_different_timezones_are_compared_by_instant(self):
        # 10:00 JST は 01:00 UTC。UTC で書かれた記録と JST の記録が重なっている
        a = (jst(6, 1, 10, 0), jst(6, 1, 10, 30))
        b = (datetime(2026, 6, 1, 1, 20, tzinfo=UTC), datetime(2026, 6, 1, 2, 0, tzinfo=UTC))
        merged = merge_windows([a, b])
        self.assertEqual(merged, [(a[0], b[1])])
        self.assertEqual(merged[0][0].utcoffset(), timedelta(0), "結果は UTC にそろえること")

    def test_empty_input(self):
        self.assertEqual(merge_windows([]), [])

    def test_input_list_is_not_modified(self):
        windows = [(jst(6, 2, 10), jst(6, 2, 11)), (jst(6, 1, 10), jst(6, 1, 11))]
        copy = list(windows)
        merge_windows(windows)
        self.assertEqual(windows, copy)

    def test_invalid_windows(self):
        with self.assertRaises(ValueError, msg="開始 >= 終了"):
            merge_windows([(jst(6, 1, 11), jst(6, 1, 10))])
        with self.assertRaises(ValueError, msg="長さ 0 の区間"):
            merge_windows([(jst(6, 1, 11), jst(6, 1, 11))])
        with self.assertRaises(ValueError, msg="タイムゾーンなし（naive）"):
            merge_windows([(datetime(2026, 6, 1, 10), datetime(2026, 6, 1, 11))])


class TestExercise2PeriodAndDowntime(unittest.TestCase):
    def test_billing_period_month_lengths(self):
        start, end = billing_period(2026, 6, JST)
        self.assertEqual(start, jst(6, 1, 0))
        self.assertEqual(end - start, timedelta(days=30))
        start, end = billing_period(2028, 2, JST)  # うるう年
        self.assertEqual(end - start, timedelta(days=29))
        start, end = billing_period(2026, 12, JST)
        self.assertEqual(end, datetime(2027, 1, 1, tzinfo=JST))

    def test_billing_period_invalid_month(self):
        for m in (0, 13):
            with self.assertRaises(ValueError):
                billing_period(2026, m, JST)

    def test_downtime_merges_clips_and_excludes_maintenance(self):
        period = billing_period(2026, 6, JST)
        outages = [
            (jst(6, 10, 14, 0), jst(6, 10, 14, 30)),
            (jst(6, 10, 14, 20), jst(6, 10, 15, 10)),          # 上と重なる → 合計 70 分
            (jst(6, 30, 23, 50), jst(7, 1, 0, 30)),            # 月をまたぐ → 6 月分は 10 分
            (jst(5, 31, 23, 0), jst(5, 31, 23, 59)),           # 期間外 → 0 分
        ]
        maintenance = [(jst(6, 10, 15, 0), jst(6, 10, 16, 0))]  # 障害と 10 分重なる
        self.assertEqual(downtime_in_period(outages, period, maintenance), timedelta(minutes=70))

    def test_downtime_without_maintenance(self):
        period = billing_period(2026, 6, JST)
        outages = [(jst(6, 10, 14, 0), jst(6, 10, 15, 10))]
        self.assertEqual(downtime_in_period(outages, period), timedelta(minutes=70))

    def test_maintenance_covering_whole_outage(self):
        period = billing_period(2026, 6, JST)
        outages = [(jst(6, 10, 2, 0), jst(6, 10, 3, 0))]
        maintenance = [(jst(6, 10, 1, 0), jst(6, 10, 4, 0)), (jst(6, 10, 1, 30), jst(6, 10, 2, 30))]
        self.assertEqual(downtime_in_period(outages, period, maintenance), timedelta(0))

    def test_outage_spanning_whole_period(self):
        period = billing_period(2026, 6, JST)
        outages = [(jst(5, 20, 0), jst(7, 5, 0))]
        self.assertEqual(downtime_in_period(outages, period), timedelta(days=30))


class TestExercise3AvailabilityAndCreditRate(unittest.TestCase):
    def test_availability_is_exact_fraction(self):
        period = billing_period(2026, 6, JST)  # 30 日 = 43,200 分
        a = availability_percent(timedelta(minutes=70), period)
        self.assertIsInstance(a, Fraction)
        self.assertEqual(a, Fraction(100) * Fraction(43200 - 70, 43200))

    def test_exact_boundary_is_not_below_threshold(self):
        # 30 日の 0.1% = 43 分 12 秒。ちょうどなら 99.9% で「下回っていない」
        period = billing_period(2026, 6, JST)
        a = availability_percent(timedelta(minutes=43, seconds=12), period)
        self.assertEqual(a, Fraction("99.9"))
        self.assertEqual(credit_percent(a, ENTERPRISE.tiers), 10, "99.95 は下回るが 99.9 は下回らない")
        a2 = availability_percent(timedelta(minutes=43, seconds=13), period)
        self.assertEqual(credit_percent(a2, ENTERPRISE.tiers), 25)

    def test_availability_extremes(self):
        period = billing_period(2026, 6, JST)
        self.assertEqual(availability_percent(timedelta(0), period), 100)
        self.assertEqual(availability_percent(timedelta(days=30), period), 0)

    def test_availability_invalid_downtime(self):
        period = billing_period(2026, 6, JST)
        with self.assertRaises(ValueError):
            availability_percent(timedelta(seconds=-1), period)
        with self.assertRaises(ValueError):
            availability_percent(timedelta(days=30, seconds=1), period)

    def test_dst_month_uses_elapsed_time(self):
        # 夏時間のある地域の契約では、3 月の実際の長さは 31 日 − 1 時間
        try:
            from zoneinfo import ZoneInfo
            ny = ZoneInfo("America/New_York")
        except Exception:  # タイムゾーンデータがない環境ではスキップ
            self.skipTest("tz データベースが利用できません")
        period = billing_period(2026, 3, ny)
        # 743 時間の 0.1% = 44 分 34.8 秒。壁時計の差（744 時間）で割ると 99.9% を超えてしまう
        a = availability_percent(timedelta(seconds=2674, microseconds=800_000), period)
        self.assertEqual(a, Fraction("99.9"), "UTC に変換して経過時間で計算すること")

    def test_credit_percent_tiers(self):
        tiers = STANDARD.tiers
        self.assertEqual(credit_percent(Fraction("99.9"), tiers), 0)
        self.assertEqual(credit_percent(Fraction("99.5"), tiers), 0, "境界ちょうどは該当しない")
        self.assertEqual(credit_percent(Fraction("99.49"), tiers), 10)
        self.assertEqual(credit_percent(Fraction("98"), tiers), 25)
        self.assertEqual(credit_percent(Fraction("50"), tiers), 50)

    def test_credit_percent_accepts_unsorted_tiers_and_exact_types(self):
        tiers = (("95.0", 50), ("99.5", 10), ("99.0", 25))
        self.assertEqual(credit_percent(Decimal("98.7"), tiers), 25)
        self.assertEqual(credit_percent("99.0", tiers), 10)
        self.assertEqual(credit_percent(100, tiers), 0)
        self.assertEqual(credit_percent(Fraction(1), ()), 0, "段階表が空ならクレジットなし")

    def test_credit_percent_rejects_float(self):
        with self.assertRaises(TypeError):
            credit_percent(99.9, STANDARD.tiers)
        with self.assertRaises(TypeError):
            credit_percent(Fraction(99), ((99.5, 10),))

    def test_credit_percent_invalid_tiers(self):
        with self.assertRaises(ValueError):
            credit_percent(Fraction(99), (("101", 10),))
        with self.assertRaises(ValueError):
            credit_percent(Fraction(99), (("99.5", 120),))
        with self.assertRaises(ValueError):
            credit_percent(Fraction(99), (("99.5", -5),))


class TestExercise4ComputeCredits(unittest.TestCase):
    def setUp(self):
        self.outages = [
            (jst(6, 10, 14, 0), jst(6, 10, 14, 30)),
            (jst(6, 10, 14, 20), jst(6, 10, 15, 10)),
            (jst(6, 30, 23, 50), jst(7, 1, 0, 30)),
        ]
        self.maintenance = [(jst(6, 10, 15, 0), jst(6, 10, 16, 0))]

    def test_credits_depend_on_plan(self):
        # ダウンタイム 70 分 → 稼働率 約 99.838%。standard（99.5% 保証）は対象外、
        # enterprise（99.95% / 99.9% の段階）は 25%
        contracts = [
            Contract("A社", "enterprise", 1_000_000),
            Contract("B社", "standard", 300_000),
            Contract("C社", "enterprise", 123_457),
        ]
        credits = compute_credits(contracts, PLANS, self.outages, 2026, 6, JST, self.maintenance)
        self.assertEqual(credits, {"A社": 250_000, "B社": 0, "C社": 30_864})  # 30,864.25 → 切り捨て

    def test_cap_is_applied(self):
        outages = [(jst(6, 1, 0), jst(6, 3, 0))]  # 48 時間停止 → 稼働率 93.3%
        contracts = [Contract("A社", "enterprise", 500_000), Contract("B社", "standard", 500_000)]
        credits = compute_credits(contracts, PLANS, outages, 2026, 6, JST)
        self.assertEqual(credits, {"A社": 500_000, "B社": 250_000}, "standard は上限 50%")

    def test_no_outage_no_credit(self):
        contracts = [Contract("A社", "enterprise", 1_000_000)]
        self.assertEqual(compute_credits(contracts, PLANS, [], 2026, 6, JST), {"A社": 0})

    def test_invalid_contracts(self):
        with self.assertRaises(ValueError, msg="未知のプラン"):
            compute_credits([Contract("A社", "gold", 1000)], PLANS, [], 2026, 6, JST)
        with self.assertRaises(ValueError, msg="顧客の重複"):
            compute_credits(
                [Contract("A社", "standard", 1000), Contract("A社", "enterprise", 1000)],
                PLANS, [], 2026, 6, JST,
            )
        with self.assertRaises(ValueError, msg="負の料金"):
            compute_credits([Contract("A社", "standard", -1)], PLANS, [], 2026, 6, JST)


if __name__ == "__main__":
    unittest.main()
