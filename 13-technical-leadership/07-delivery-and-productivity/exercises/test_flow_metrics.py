"""13.7 デリバリーと生産性 — テスト（フローメトリクス）

実行: python3 tools/check.py 13.7   （またはこのディレクトリで python3 -m unittest -v test_flow_metrics）
注意: flow_metrics は dora_metrics の percentile（演習1）を使います。
"""
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flow_metrics import (
    Event,
    aging_wip,
    cycle_time_percentiles,
    cycle_times_days,
    flow_efficiency,
    load_ticket_events,
    throughput_per_week,
    wip_at,
)

DATA = Path(__file__).parent / "data" / "ticket_events.json"
JST = timezone(timedelta(hours=9))


def t(day, hour=0):
    return datetime(2026, 7, day, hour, tzinfo=JST)


def small_events():
    # A: 着手 1 日 → 完了 3 日 12 時（2.5 日）  B: 着手せず  C: 仕掛かり中
    # D: 着手 2 日 → 差し戻しを経て 6 日に完了（4 日）
    return [
        Event("D", t(6), "Done"),
        Event("A", t(1), "Ready"),
        Event("A", t(1), "In Progress"),
        Event("A", t(3, 12), "Done"),
        Event("B", t(1), "Ready"),
        Event("C", t(4), "In Progress"),
        Event("C", t(5), "Blocked"),
        Event("D", t(2), "In Progress"),
        Event("D", t(3), "Waiting for Review"),
        Event("D", t(4), "In Review"),
        Event("D", t(4, 12), "In Progress"),
        Event("D", t(5), "In Review"),
    ]


class TestExercise3CycleTimeAndThroughput(unittest.TestCase):
    def test_cycle_times_small(self):
        got = cycle_times_days(small_events())
        self.assertEqual(list(got), ["A", "D"])
        self.assertAlmostEqual(got["A"], 2.5)
        self.assertAlmostEqual(got["D"], 4.0)

    def test_done_before_start_is_ignored(self):
        evs = [Event("X", t(1), "Done"), Event("X", t(2), "In Progress"), Event("X", t(4), "Done")]
        self.assertAlmostEqual(cycle_times_days(evs)["X"], 2.0, msg="着手より前の Done は無視する")

    def test_percentiles_fixture(self):
        events, _, _ = load_ticket_events(DATA)
        self.assertEqual(len(cycle_times_days(events)), 88)
        got = cycle_time_percentiles(events)
        self.assertAlmostEqual(got[50], 3.265625, places=6)
        self.assertAlmostEqual(got[85], 6.66135, places=4)
        self.assertAlmostEqual(got[95], 8.46427, places=4)

    def test_percentiles_empty_is_error(self):
        with self.assertRaises(ValueError):
            cycle_time_percentiles([Event("B", t(1), "Ready")])

    def test_throughput_small(self):
        self.assertEqual(throughput_per_week(small_events(), t(1), weeks=2), [2, 0])
        self.assertEqual(throughput_per_week(small_events(), t(4), weeks=1), [1], "範囲外の完了は数えない")

    def test_throughput_fixture(self):
        events, _, _ = load_ticket_events(DATA)
        start = datetime(2026, 7, 6, tzinfo=JST)
        self.assertEqual(throughput_per_week(events, start, 12), [6, 6, 4, 8, 5, 8, 5, 10, 8, 7, 7, 9])

    def test_throughput_invalid(self):
        with self.assertRaises(ValueError):
            throughput_per_week(small_events(), t(1), weeks=0)


class TestExercise4WipEfficiencyAging(unittest.TestCase):
    def test_wip_small(self):
        got = wip_at(small_events(), [t(1), t(2, 12), t(3, 12), t(4, 12), t(7)])
        self.assertEqual(got, [1, 2, 1, 2, 1])

    def test_wip_fixture(self):
        events, now, _ = load_ticket_events(DATA)
        times = [datetime(2026, 8, 1, 12, tzinfo=JST), datetime(2026, 9, 1, 12, tzinfo=JST), now]
        self.assertEqual(wip_at(events, times), [6, 8, 8])

    def test_flow_efficiency_small(self):
        per, overall = flow_efficiency(small_events(), ["In Progress", "In Review"])
        self.assertAlmostEqual(per["A"], 1.0)
        # D: In Progress 1 日 + レビュー待ち 1 日 + In Review 0.5 日 + In Progress 0.5 日 + In Review 1 日
        self.assertAlmostEqual(per["D"], 3.0 / 4.0)
        self.assertAlmostEqual(overall, (2.5 + 3.0) / (2.5 + 4.0))
        self.assertNotIn("C", per)

    def test_flow_efficiency_docstring(self):
        u = lambda d: datetime(2026, 7, d, tzinfo=timezone.utc)
        evs = [Event("A", u(1), "In Progress"), Event("A", u(3), "Waiting for Review"),
               Event("A", u(4), "In Review"), Event("A", u(5), "Done")]
        self.assertEqual(flow_efficiency(evs, ["In Progress", "In Review"]), ({"A": 0.75}, 0.75))

    def test_flow_efficiency_empty(self):
        self.assertEqual(flow_efficiency([Event("B", t(1), "Ready")], ["In Progress"]), ({}, 0.0))

    def test_flow_efficiency_fixture(self):
        events, _, active = load_ticket_events(DATA)
        per, overall = flow_efficiency(events, active)
        self.assertEqual(len(per), 88)
        self.assertAlmostEqual(overall, 0.5633, places=3)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in per.values()))

    def test_aging_small(self):
        got = aging_wip(small_events(), now=t(8), threshold_days=1.0)
        self.assertEqual(got, [("C", 4.0, "Blocked")])

    def test_aging_ignores_future_events(self):
        # t(3) の時点では A（完了は t(3, 12)）も D（完了は t(6)）もまだ仕掛かり中
        got = aging_wip(small_events(), now=t(3), threshold_days=0.5)
        self.assertEqual([x[0] for x in got], ["A", "D"])
        self.assertEqual(got[0], ("A", 2.0, "In Progress"))
        self.assertEqual(got[1], ("D", 1.0, "Waiting for Review"))

    def test_aging_fixture(self):
        events, now, _ = load_ticket_events(DATA)
        threshold = cycle_time_percentiles(events)[85]
        got = aging_wip(events, now, threshold)
        self.assertEqual([x[0] for x in got], ["T-091", "T-092", "T-093", "T-076"])
        self.assertEqual([x[2] for x in got], ["Blocked", "Waiting for Review", "In Progress", "Blocked"])
        self.assertAlmostEqual(got[0][1], 29 + 8 / 24)

    def test_aging_sorted_by_age_then_id(self):
        evs = [Event("B", t(1), "In Progress"), Event("A", t(1), "In Progress"), Event("C", t(2), "In Progress")]
        got = aging_wip(evs, now=t(5), threshold_days=0)
        self.assertEqual([x[0] for x in got], ["A", "B", "C"])


if __name__ == "__main__":
    unittest.main()
