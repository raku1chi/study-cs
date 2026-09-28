"""13.7 デリバリーと生産性 — テスト（DORA の 4 つの指標）

実行: python3 tools/check.py 13.7   （またはこのディレクトリで python3 -m unittest -v test_dora_metrics）
"""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dora_metrics import (
    DEFAULT_THRESHOLDS,
    Deployment,
    Incident,
    change_failure_rate,
    classify,
    deployment_frequency,
    lead_time_summary,
    lead_times_hours,
    load_events,
    percentile,
    time_to_restore_hours,
)

DATA = Path(__file__).parent / "data" / "delivery_events.json"
JST = timezone(timedelta(hours=9))


def at(day, hour=0, minute=0):
    return datetime(2026, 7, day, hour, minute, tzinfo=JST)


def dep(id_, deployed, commits, status="success"):
    return Deployment(id_, deployed, tuple(commits), status)


class TestExercise1Percentile(unittest.TestCase):
    def test_examples(self):
        self.assertAlmostEqual(percentile([4, 1, 3, 2], 50), 2.5)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 75), 3.25)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 90), 3.7)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 0), 1)
        self.assertAlmostEqual(percentile([1, 2, 3, 4], 100), 4)

    def test_single_value(self):
        for p in (0, 37.5, 100):
            self.assertEqual(percentile([7.0], p), 7.0)

    def test_matches_statistics_quantiles_inclusive(self):
        import statistics
        values = [3.1, 0.5, 9.9, 4.2, 4.2, 7.7, 1.0, 12.5, 6.0]
        cuts = statistics.quantiles(values, n=100, method="inclusive")
        for p in (10, 25, 50, 85, 95):
            self.assertAlmostEqual(percentile(values, p), cuts[p - 1], msg=f"p={p}")

    def test_does_not_modify_input(self):
        values = [3, 1, 2]
        percentile(values, 50)
        self.assertEqual(values, [3, 1, 2])

    def test_invalid(self):
        with self.assertRaises(ValueError):
            percentile([], 50)
        for p in (-1, 101):
            with self.assertRaises(ValueError):
                percentile([1, 2], p)


class TestExercise1FrequencyAndLeadTime(unittest.TestCase):
    def test_frequency_counts_only_success_in_range(self):
        deps = [
            dep("a", at(1, 10), [at(1, 9)]),
            dep("b", at(2, 10), [at(2, 9)], "rolled_back"),
            dep("c", at(3, 10), [at(3, 9)]),
            dep("d", at(11, 0), [at(10)]),   # 終了時刻ちょうどは含まない
        ]
        self.assertAlmostEqual(deployment_frequency(deps, at(1), at(11)), 2 / 10)

    def test_frequency_invalid_period(self):
        with self.assertRaises(ValueError):
            deployment_frequency([], at(2), at(2))

    def test_lead_times(self):
        deps = [
            dep("a", at(2, 12), [at(1, 12), at(2, 6)]),
            dep("b", at(3, 12), [at(1, 0)], "rolled_back"),   # ロールバックは除く
            dep("c", at(4, 0), [at(3, 22, 30)]),
        ]
        self.assertEqual(lead_times_hours(deps), [24.0, 6.0, 1.5])
        summary = lead_time_summary(deps)
        self.assertAlmostEqual(summary["median"], 6.0)
        self.assertAlmostEqual(summary["p90"], 6.0 + (24.0 - 6.0) * 0.8)

    def test_lead_time_negative_is_error(self):
        with self.assertRaises(ValueError):
            lead_times_hours([dep("a", at(1), [at(2)])])

    def test_fixture(self):
        deps, incs, start, end = load_events(DATA)
        self.assertEqual(len(deps), 60)
        self.assertAlmostEqual(deployment_frequency(deps, start, end), 56 / 92)
        self.assertEqual(len(lead_times_hours(deps)), 170)
        summary = lead_time_summary(deps)
        self.assertAlmostEqual(summary["median"], 24.7, places=6)
        self.assertAlmostEqual(summary["p90"], 78.4567, places=3)


class TestExercise2FailureAndRestore(unittest.TestCase):
    def test_change_failure_rate_counts_each_deployment_once(self):
        deps = [dep(i, at(1), [at(1)]) for i in "abcd"] + [dep("e", at(1), [at(1)], "rolled_back")]
        incs = [
            Incident("i1", at(2), at(2, 1), "a"),
            Incident("i2", at(3), at(3, 1), "a"),      # 同じデプロイの 2 件目
            Incident("i3", at(4), at(4, 1), "e"),      # ロールバック済みのデプロイ
            Incident("i4", at(5), at(5, 1), None),     # デプロイと無関係
        ]
        self.assertAlmostEqual(change_failure_rate(deps, incs), 2 / 5)

    def test_change_failure_rate_errors(self):
        with self.assertRaises(ValueError):
            change_failure_rate([], [])
        with self.assertRaises(ValueError):
            change_failure_rate([dep("a", at(1), [at(1)])], [Incident("i", at(1), at(2), "zzz")])

    def test_time_to_restore(self):
        incs = [
            Incident("i1", at(1, 10), at(1, 10, 30), "a"),
            Incident("i2", at(2, 10), at(2, 14), None),
            Incident("i3", at(3, 10), at(3, 11), "b"),
        ]
        self.assertAlmostEqual(time_to_restore_hours(incs), 1.0)
        self.assertAlmostEqual(time_to_restore_hours(incs, deployment_caused_only=True), 0.75)

    def test_time_to_restore_errors(self):
        with self.assertRaises(ValueError):
            time_to_restore_hours([])
        with self.assertRaises(ValueError):
            time_to_restore_hours([Incident("i", at(1), at(2), None)], deployment_caused_only=True)
        with self.assertRaises(ValueError):
            time_to_restore_hours([Incident("i", at(2), at(1), None)])

    def test_fixture(self):
        deps, incs, _, _ = load_events(DATA)
        self.assertAlmostEqual(change_failure_rate(deps, incs), 7 / 60)
        self.assertAlmostEqual(time_to_restore_hours(incs), 40 / 60)
        self.assertAlmostEqual(time_to_restore_hours(incs, deployment_caused_only=True), 40 / 60)


class TestExercise2Classify(unittest.TestCase):
    def test_docstring_example(self):
        got = classify({"change_failure_rate": 0.10, "deployment_frequency": 2.0})
        self.assertEqual(got, {"change_failure_rate": "high", "deployment_frequency": "elite", "overall": "high"})

    def test_boundaries_are_inclusive(self):
        self.assertEqual(classify({"lead_time_median_hours": 24.0})["lead_time_median_hours"], "elite")
        self.assertEqual(classify({"lead_time_median_hours": 24.01})["lead_time_median_hours"], "high")
        self.assertEqual(classify({"deployment_frequency": 1 / 7})["deployment_frequency"], "high")
        self.assertEqual(classify({"deployment_frequency": 0.01})["deployment_frequency"], "low")
        self.assertEqual(classify({"time_to_restore_hours": 500})["time_to_restore_hours"], "low")

    def test_fixture_profile(self):
        deps, incs, start, end = load_events(DATA)
        metrics = {
            "deployment_frequency": deployment_frequency(deps, start, end),
            "lead_time_median_hours": lead_time_summary(deps)["median"],
            "change_failure_rate": change_failure_rate(deps, incs),
            "time_to_restore_hours": time_to_restore_hours(incs),
        }
        self.assertEqual(classify(metrics), {
            "deployment_frequency": "high",
            "lead_time_median_hours": "high",
            "change_failure_rate": "medium",
            "time_to_restore_hours": "elite",
            "overall": "medium",
        })

    def test_custom_thresholds(self):
        thresholds = {"coverage": ("higher", [("elite", 0.9), ("high", 0.7)])}
        self.assertEqual(classify({"coverage": 0.8}, thresholds), {"coverage": "high", "overall": "high"})
        self.assertEqual(classify({"coverage": 0.5}, thresholds), {"coverage": "low", "overall": "low"})

    def test_empty_and_errors(self):
        self.assertEqual(classify({}), {})
        with self.assertRaises(ValueError):
            classify({"unknown_metric": 1.0})
        with self.assertRaises(ValueError):
            classify({"x": 1.0}, {"x": ("sideways", [("elite", 1.0)])})

    def test_default_thresholds_not_modified(self):
        before = {k: (d, list(b)) for k, (d, b) in DEFAULT_THRESHOLDS.items()}
        classify({"change_failure_rate": 0.2})
        self.assertEqual({k: (d, list(b)) for k, (d, b) in DEFAULT_THRESHOLDS.items()}, before)


if __name__ == "__main__":
    unittest.main()
