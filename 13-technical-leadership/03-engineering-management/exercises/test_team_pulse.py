"""13.3 エンジニアリングマネジメントの基礎 — テスト

実行: python3 tools/check.py 13.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from team_pulse import (
    ENTIRE_ORG,
    Response,
    TeamSummary,
    enps,
    favorability,
    item_means,
    low_scoring_items,
    period_trend,
    suppress_small_groups,
    team_report,
)


class TestExercise1Enps(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(enps([10, 10, 10, 10, 7, 7, 7, 3, 3, 3]), 10.0)
        self.assertEqual(enps([9, 8, 6]), 0.0)
        self.assertEqual(enps([10, 9, 8, 7, 6, 0]), 0.0)

    def test_boundaries_of_categories(self):
        self.assertEqual(enps([9]), 100.0, "9 は推奨者")
        self.assertEqual(enps([8]), 0.0, "8 は中立")
        self.assertEqual(enps([7]), 0.0, "7 は中立")
        self.assertEqual(enps([6]), -100.0, "6 は批判者")
        self.assertEqual(enps([0]), -100.0)

    def test_neutral_counts_in_denominator(self):
        # 推奨者 1、中立 3 → 25
        self.assertEqual(enps([10, 8, 8, 7]), 25.0)

    def test_exact_value_without_float_noise(self):
        # 推奨者 6/10、批判者 3/10 → 30（30.000000000000004 にならない）
        self.assertEqual(enps([10] * 6 + [8] + [1] * 3), 30.0)

    def test_invalid_scores(self):
        for bad in ([], [11], [-1], [5.5], [True], ["9"]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                enps(bad)

    def test_favorability(self):
        self.assertEqual(favorability([5, 4, 3, 2, 1]), 40.0)
        self.assertEqual(favorability([4, 4]), 100.0)
        self.assertEqual(favorability([3, 3, 3]), 0.0)
        for bad in ([], [0], [6], [4.0]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                favorability(bad)


def sample_responses():
    return [
        Response("Platform", "2026-Q2", 9, {"心理的安全性": 4, "成長実感": 3, "業務量": 2}),
        Response("Platform", "2026-Q2", 6, {"心理的安全性": 3, "成長実感": 2, "業務量": 2}),
        Response("Platform", "2026-Q3", 10, {"心理的安全性": 5, "成長実感": 4, "業務量": 3}),
        Response("Platform", "2026-Q3", 7, {"心理的安全性": 4, "成長実感": 3}),
        Response("Mobile", "2026-Q3", None, {"心理的安全性": 2, "成長実感": 4, "業務量": 1}),
        Response("Mobile", "2026-Q1", 8, {"心理的安全性": 3}),
    ]


class TestExercise2Items(unittest.TestCase):
    def test_item_means_uses_only_answered(self):
        rs = [
            Response("A", "2026-Q3", items={"成長実感": 4, "心理的安全性": 5}),
            Response("A", "2026-Q3", items={"成長実感": 2}),
        ]
        self.assertEqual(item_means(rs), {"心理的安全性": 5.0, "成長実感": 3.0})

    def test_item_means_sample(self):
        got = item_means(sample_responses())
        self.assertAlmostEqual(got["心理的安全性"], 21 / 6)
        self.assertAlmostEqual(got["成長実感"], 16 / 5)
        self.assertAlmostEqual(got["業務量"], 8 / 4)
        self.assertEqual(list(got), sorted(got), "キーは設問名の昇順")

    def test_item_means_empty_and_invalid(self):
        self.assertEqual(item_means([]), {})
        with self.assertRaises(ValueError):
            item_means([Response("A", "2026-Q3", items={"業務量": 6})])
        with self.assertRaises(ValueError):
            item_means([Response("A", "2026-Q3", items={"業務量": 0})])

    def test_low_scoring_items_sorted_ascending(self):
        got = low_scoring_items(sample_responses(), threshold=3.5)
        self.assertEqual([name for name, _ in got], ["業務量", "成長実感"])
        self.assertAlmostEqual(got[0][1], 2.0)
        self.assertAlmostEqual(got[1][1], 3.2)

    def test_low_scoring_items_threshold_is_strict(self):
        rs = [Response("A", "2026-Q3", items={"X": 3, "Y": 4})]
        self.assertEqual(low_scoring_items(rs, threshold=3.0), [])
        self.assertEqual(low_scoring_items(rs, threshold=3.01), [("X", 3.0)])

    def test_low_scoring_items_ties_by_name(self):
        rs = [Response("A", "2026-Q3", items={"b": 2, "a": 2, "c": 1})]
        self.assertEqual(low_scoring_items(rs), [("c", 1.0), ("a", 2.0), ("b", 2.0)])

    def test_period_trend_enps(self):
        got = period_trend(sample_responses())
        self.assertEqual([p for p, _, _ in got], ["2026-Q1", "2026-Q2", "2026-Q3"])
        self.assertEqual(got[0], ("2026-Q1", 0.0, None))
        self.assertEqual(got[1], ("2026-Q2", 0.0, 0.0))
        self.assertEqual(got[2], ("2026-Q3", 50.0, 50.0), "Mobile の enps=None は除外される")

    def test_period_trend_item(self):
        got = period_trend(sample_responses(), metric="業務量")
        self.assertEqual(len(got), 2, "業務量のデータがない 2026-Q1 は含めない")
        self.assertEqual(got[0], ("2026-Q2", 2.0, None))
        self.assertEqual(got[1][0], "2026-Q3")
        self.assertAlmostEqual(got[1][1], 2.0)
        self.assertAlmostEqual(got[1][2], 0.0)

    def test_period_trend_unknown_metric_is_empty(self):
        self.assertEqual(period_trend(sample_responses(), metric="存在しない設問"), [])


def make_team(team, period, n, enps_score=8, items=None):
    return [Response(team, period, enps_score, dict(items or {"心理的安全性": 4})) for _ in range(n)]


class TestExercise3Anonymity(unittest.TestCase):
    def test_no_suppression_when_all_large(self):
        self.assertEqual(suppress_small_groups({"A": 5, "B": 7}), set())

    def test_single_small_group_triggers_secondary_suppression(self):
        # B だけを隠しても「全体 − A − C」で B が逆算できるので、最小の C も隠す
        self.assertEqual(suppress_small_groups({"A": 12, "B": 3, "C": 8}), {"B", "C"})

    def test_two_small_groups_large_enough_together(self):
        self.assertEqual(suppress_small_groups({"A": 12, "B": 3, "C": 4}), {"B", "C"})

    def test_two_small_groups_still_too_small_together(self):
        self.assertEqual(
            suppress_small_groups({"A": 12, "B": 2, "C": 2, "D": 6}), {"B", "C", "D"}
        )

    def test_secondary_suppression_tie_breaks_by_name(self):
        self.assertEqual(suppress_small_groups({"A": 3, "C": 6, "B": 6}), {"A", "B"})

    def test_everything_suppressed_when_needed(self):
        self.assertEqual(suppress_small_groups({"A": 1, "B": 1}), {"A", "B"})
        self.assertEqual(suppress_small_groups({"A": 3, "B": 20}), {"A", "B"})

    def test_zero_count_groups_are_ignored(self):
        self.assertEqual(suppress_small_groups({"A": 0, "B": 9}), set())

    def test_custom_threshold(self):
        self.assertEqual(suppress_small_groups({"A": 7, "B": 9, "C": 12}, min_responses=10), {"A", "B"})
        self.assertEqual(suppress_small_groups({"A": 1, "B": 1}, min_responses=1), set())

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            suppress_small_groups({"A": 3}, min_responses=0)
        with self.assertRaises(ValueError):
            suppress_small_groups({"A": -1})

    def test_team_report_hides_small_team_and_its_complement(self):
        rs = (
            make_team("Platform", "2026-Q3", 6, 9, {"心理的安全性": 4, "業務量": 2})
            + make_team("Mobile", "2026-Q3", 3, 3, {"心理的安全性": 2})
            + make_team("Web", "2026-Q3", 7, 7, {"心理的安全性": 5})
            + make_team("Mobile", "2026-Q2", 10)  # 別の期は無視される
        )
        report = team_report(rs, "2026-Q3")
        self.assertEqual(list(report), ["Mobile", "Platform", "Web", ENTIRE_ORG])
        self.assertIsNone(report["Mobile"], "3 人のチームは秘匿")
        self.assertIsNone(report["Platform"], "Mobile を逆算させないための二次秘匿")
        web = report["Web"]
        self.assertIsInstance(web, TeamSummary)
        self.assertEqual(web.n, 7)
        self.assertEqual(web.enps, 0.0)
        self.assertEqual(web.item_means, {"心理的安全性": 5.0})
        total = report[ENTIRE_ORG]
        self.assertEqual(total.n, 16)
        self.assertAlmostEqual(total.enps, (6 - 3) * 100 / 16)
        self.assertAlmostEqual(total.item_means["心理的安全性"], (6 * 4 + 3 * 2 + 7 * 5) / 16)
        self.assertAlmostEqual(total.item_means["業務量"], 2.0)

    def test_team_report_enps_none_when_nobody_answered(self):
        rs = make_team("A", "2026-Q3", 5, None) + make_team("B", "2026-Q3", 5, 10)
        report = team_report(rs, "2026-Q3")
        self.assertIsNone(report["A"].enps)
        self.assertEqual(report["B"].enps, 100.0)
        self.assertEqual(report[ENTIRE_ORG].enps, 100.0)

    def test_team_report_small_org_hides_total(self):
        rs = make_team("A", "2026-Q3", 2) + make_team("B", "2026-Q3", 2)
        report = team_report(rs, "2026-Q3")
        self.assertEqual(report, {"A": None, "B": None, ENTIRE_ORG: None})

    def test_team_report_empty_period(self):
        self.assertEqual(team_report(make_team("A", "2026-Q2", 6), "2026-Q3"), {ENTIRE_ORG: None})

    def test_team_report_rejects_reserved_name(self):
        with self.assertRaises(ValueError):
            team_report(make_team(ENTIRE_ORG, "2026-Q3", 6), "2026-Q3")


if __name__ == "__main__":
    unittest.main()
