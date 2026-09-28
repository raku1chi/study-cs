"""12.1 演習3: データ品質チェック — テスト

実行: python3 tools/check.py 12.1   （またはこのディレクトリで python3 -m unittest -v test_dq_checks）
"""
import datetime as dt
import functools
import math
import unittest

from dq_checks import (
    FAIL,
    PASS,
    SKIP,
    WARN,
    CheckResult,
    SuiteReport,
    check_accepted_values,
    check_freshness,
    check_not_null,
    check_range,
    check_relationships,
    check_row_count_anomaly,
    check_schema,
    check_unique,
    parse_timestamp,
    run_suite,
)

UTC = dt.timezone.utc
JST = dt.timezone(dt.timedelta(hours=9))

ORDERS = [
    {"order_id": 1, "customer_id": 10, "status": "paid", "amount": 1200, "created_at": "2026-04-01T09:00:00+00:00"},
    {"order_id": 2, "customer_id": 20, "status": "shipped", "amount": 800, "created_at": "2026-04-01T10:00:00+00:00"},
    {"order_id": 3, "customer_id": None, "status": "paid", "amount": -50, "created_at": "2026-04-01T11:00:00+00:00"},
    {"order_id": 3, "customer_id": 99, "status": "refunded?", "amount": 300, "created_at": "2026-04-01T12:00:00+00:00"},
    {"order_id": None, "customer_id": 10, "status": None, "amount": None, "created_at": None},
]
CUSTOMERS = [{"id": 10}, {"id": 20}, {"id": 30}]


class TestColumnChecks(unittest.TestCase):
    def test_not_null(self):
        r = check_not_null(ORDERS, "order_id")
        self.assertEqual((r.name, r.status, r.failures), ("not_null(order_id)", FAIL, 1))
        self.assertEqual(r.samples, (4,), "samples には NULL だった行番号を入れる")
        self.assertEqual(check_not_null(ORDERS[:3], "order_id").status, PASS)
        self.assertEqual(check_not_null(ORDERS, "customer_id").failures, 1)
        self.assertEqual(check_not_null(ORDERS, "no_such_column").failures, 5, "列がない行も NULL 扱い")

    def test_severity_warn(self):
        self.assertEqual(check_not_null(ORDERS, "order_id", severity="warn").status, WARN)
        with self.assertRaises(ValueError):
            check_not_null(ORDERS, "order_id", severity="critical")

    def test_unique_ignores_null(self):
        r = check_unique(ORDERS, "order_id")
        self.assertEqual((r.name, r.status, r.failures, r.samples), ("unique(order_id)", FAIL, 1, (3,)))
        self.assertEqual(check_unique(ORDERS, "amount").status, PASS)
        rows = [{"a": None}, {"a": None}]
        self.assertEqual(check_unique(rows, "a").status, PASS, "NULL どうしは重複とみなさない")

    def test_unique_composite_key(self):
        rows = [{"d": "2026-04-01", "sku": "A"}, {"d": "2026-04-01", "sku": "B"},
                {"d": "2026-04-02", "sku": "A"}, {"d": "2026-04-01", "sku": "A"}]
        r = check_unique(rows, ["d", "sku"])
        self.assertEqual((r.name, r.failures, r.samples), ("unique(d, sku)", 1, (("2026-04-01", "A"),)))
        self.assertEqual(check_unique(rows[:3], ("d", "sku")).status, PASS)

    def test_accepted_values(self):
        r = check_accepted_values(ORDERS, "status", ["paid", "shipped", "refunded"])
        self.assertEqual((r.name, r.status, r.failures, r.samples),
                         ("accepted_values(status)", FAIL, 1, ("refunded?",)))

    def test_range(self):
        r = check_range(ORDERS, "amount", min_value=0)
        self.assertEqual((r.name, r.status, r.failures, r.samples), ("range(amount)", FAIL, 1, (-50,)))
        self.assertEqual(check_range(ORDERS, "amount", min_value=-100, max_value=10_000).status, PASS)
        self.assertEqual(check_range([{"x": 5}], "x", min_value=5, max_value=5).status, PASS, "境界は含む")
        self.assertEqual(check_range([{"x": "5"}], "x", min_value=0).failures, 1, "比較できない値は不合格")
        with self.assertRaises(ValueError):
            check_range(ORDERS, "amount")
        with self.assertRaises(ValueError):
            check_range(ORDERS, "amount", min_value=10, max_value=1)

    def test_relationships(self):
        r = check_relationships(ORDERS, "customer_id", CUSTOMERS, "id")
        self.assertEqual((r.name, r.status, r.failures, r.samples),
                         ("relationships(customer_id -> id)", FAIL, 1, (99,)))
        self.assertEqual(check_relationships(ORDERS[:2], "customer_id", CUSTOMERS, "id").status, PASS)

    def test_samples_are_limited(self):
        rows = [{"v": None} for _ in range(20)]
        r = check_not_null(rows, "v")
        self.assertEqual(r.failures, 20)
        self.assertEqual(r.samples, (0, 1, 2, 3, 4))

    def test_schema(self):
        contract = {"order_id": int, "amount": int, "status": str, "created_at": str}
        self.assertEqual(check_schema(ORDERS, contract).status, PASS, "None は型チェックの対象外")
        bad = [{"order_id": 1, "amount": "1200", "status": "paid", "created_at": "x"},
               {"order_id": 2, "amount": True, "status": "paid", "created_at": "x"},
               {"order_id": 3, "status": "paid", "created_at": "x"},
               {"order_id": 4, "amount": 5, "status": "paid", "created_at": "x", "debug": 1}]
        r = check_schema(bad, contract)
        self.assertEqual((r.status, r.failures), (FAIL, 3), "型違い・bool の混入・列の欠落の 3 行")
        self.assertTrue(any("amount" in s for s in r.samples))
        self.assertEqual(check_schema(bad, contract, allow_extra_columns=False).failures, 4)
        self.assertEqual(check_schema([{"x": 1.5}, {"x": 2}], {"x": (int, float)}).status, PASS)


class TestFreshness(unittest.TestCase):
    NOW = dt.datetime(2026, 4, 1, 14, 0, tzinfo=UTC)

    def run_check(self, rows, now=None):
        return check_freshness(rows, "created_at", now=now or self.NOW,
                               warn_after=dt.timedelta(hours=1), error_after=dt.timedelta(hours=6))

    def test_fresh_warn_and_stale(self):
        self.assertEqual(self.run_check(ORDERS).status, WARN)  # 最新は 12:00、2 時間前
        self.assertEqual(self.run_check(ORDERS, now=dt.datetime(2026, 4, 1, 12, 30, tzinfo=UTC)).status, PASS)
        r = self.run_check(ORDERS, now=dt.datetime(2026, 4, 2, 0, 0, tzinfo=UTC))
        self.assertEqual((r.name, r.status), ("freshness(created_at)", FAIL))

    def test_accepts_datetime_and_z_suffix(self):
        rows = [{"created_at": "2026-04-01T13:30:00Z"}, {"created_at": dt.datetime(2026, 4, 1, 13, 0, tzinfo=UTC)}]
        self.assertEqual(self.run_check(rows).status, PASS)
        self.assertEqual(parse_timestamp("2026-04-01T13:30:00Z"), dt.datetime(2026, 4, 1, 13, 30, tzinfo=UTC))

    def test_timezones_are_compared_correctly(self):
        rows = [{"created_at": "2026-04-01T22:30:00+09:00"}]  # = 13:30 UTC
        self.assertEqual(self.run_check(rows).status, PASS)

    def test_future_timestamps_are_suspicious(self):
        # JST の時刻に誤って UTC のオフセットを付けると 9 時間未来に見える
        rows = [{"created_at": "2026-04-01T22:30:00+00:00"}]
        r = self.run_check(rows)
        self.assertEqual(r.status, WARN)
        self.assertIn("未来", r.message)

    def test_no_data_is_failure(self):
        self.assertEqual(self.run_check([]).status, FAIL)
        self.assertEqual(self.run_check([{"created_at": None}]).status, FAIL)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            check_freshness(ORDERS, "created_at", now=self.NOW,
                            warn_after=dt.timedelta(hours=7), error_after=dt.timedelta(hours=6))
        with self.assertRaises(ValueError):
            self.run_check([{"created_at": "2026-04-01T13:00:00"}])  # タイムゾーンなしと混在


class TestRowCountAnomaly(unittest.TestCase):
    HISTORY = [1000, 1020, 980, 1010, 990, 1005, 995]

    def test_normal_and_anomalous(self):
        self.assertEqual(check_row_count_anomaly(self.HISTORY, 1015).status, PASS)
        r = check_row_count_anomaly(self.HISTORY, 400)
        self.assertEqual((r.name, r.status), ("row_count_anomaly", FAIL))
        self.assertIn("z =", r.message)
        self.assertEqual(check_row_count_anomaly(self.HISTORY, 1300, severity="warn").status, WARN)

    def test_z_score_uses_sample_stdev(self):
        # 平均 1000, 標本標準偏差 ≈ 13.23。1040 は z ≈ 3.02 で閾値 3 を超える
        history = [1000, 1020, 980, 1010, 990, 1005, 995]
        self.assertEqual(check_row_count_anomaly(history, 1039).status, PASS)
        self.assertEqual(check_row_count_anomaly(history, 1040).status, FAIL)
        self.assertIn("3.02", check_row_count_anomaly(history, 1040).message)

    def test_constant_history(self):
        self.assertEqual(check_row_count_anomaly([500] * 7, 500).status, PASS)
        r = check_row_count_anomaly([500] * 7, 501)
        self.assertEqual(r.status, FAIL, "ばらつきゼロの履歴からの変化は異常とみなす")

    def test_short_history_is_skipped(self):
        self.assertEqual(check_row_count_anomaly([1, 2, 3], 100).status, SKIP)
        self.assertEqual(check_row_count_anomaly([1, 2, 3], 100, min_history=3).status, FAIL)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            check_row_count_anomaly(self.HISTORY, 1, z_threshold=0)
        with self.assertRaises(ValueError):
            check_row_count_anomaly(self.HISTORY, 1, min_history=1)


class TestSuite(unittest.TestCase):
    def test_report(self):
        report = SuiteReport([
            CheckResult("not_null(a)", PASS),
            CheckResult("unique(a)", WARN, 1, "重複", (3,)),
            CheckResult("row_count_anomaly", SKIP),
        ])
        self.assertEqual(report.status, WARN)
        self.assertFalse(report.should_block)
        self.assertEqual(report.counts(), {PASS: 1, WARN: 1, FAIL: 0, SKIP: 1})
        text = report.to_text()
        lines = text.splitlines()
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("[PASS] not_null(a)"))
        self.assertTrue(lines[1].startswith("[WARN] unique(a)"))
        self.assertIn("重複", lines[1])
        self.assertTrue(lines[2].startswith("[SKIP] row_count_anomaly"))
        self.assertTrue(lines[3].startswith("結果: WARN"))

    def test_empty_and_skip_only(self):
        self.assertEqual(SuiteReport([]).status, PASS)
        self.assertEqual(SuiteReport([CheckResult("x", SKIP)]).status, PASS)

    def test_run_suite_blocks_on_failure_and_survives_exceptions(self):
        def broken():
            raise RuntimeError("接続できません")

        report = run_suite([
            functools.partial(check_not_null, ORDERS, "order_id"),
            functools.partial(check_unique, ORDERS[:2], "order_id"),
            broken,
            functools.partial(check_freshness, ORDERS, "created_at", now=dt.datetime(2026, 4, 1, 13, tzinfo=UTC),
                              warn_after=dt.timedelta(hours=2), error_after=dt.timedelta(hours=6)),
        ])
        self.assertEqual([r.status for r in report.results], [FAIL, PASS, FAIL, PASS])
        self.assertEqual(report.results[2].name, "error:broken")
        self.assertIn("接続できません", report.results[2].message)
        self.assertTrue(report.should_block)
        self.assertEqual(report.status, FAIL)
        self.assertTrue(report.to_text().splitlines()[-1].startswith("結果: FAIL"))


if __name__ == "__main__":
    unittest.main()
