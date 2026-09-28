"""13.4 採用 — テスト

実行: python3 tools/check.py 13.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import unittest

from hiring_funnel import (
    Channel,
    Stage,
    cost_per_hire,
    expected_time_to_fill,
    interviewer_load,
    required_pipeline,
)

# 本文の例: Senior Backend Engineer を 5 人採用する
BOOK_STAGES = [
    Stage("書類選考", 0.30, duration_days=4, interview_hours=0.5),
    Stage("技術面接", 0.40, duration_days=7, interview_hours=2.0),
    Stage("ワークサンプル", 0.50, duration_days=10, interview_hours=5.0),
    Stage("最終面接", 0.60, duration_days=7, interview_hours=3.0),
    Stage("オファー", 0.70, duration_days=10, interview_hours=1.0),
]


class TestExercise1Pipeline(unittest.TestCase):
    def test_docstring_example(self):
        stages = [Stage("書類選考", 0.3), Stage("面接", 0.4), Stage("オファー", 0.7)]
        self.assertEqual(required_pipeline(5, stages), [67, 20, 8])

    def test_book_example(self):
        self.assertEqual(required_pipeline(5, BOOK_STAGES), [234, 70, 28, 14, 8])

    def test_rounds_up_at_every_stage(self):
        # 1 / 0.7 = 1.43 → 2、2 / 0.5 = 4 → 4
        self.assertEqual(required_pipeline(1, [Stage("a", 0.5), Stage("b", 0.7)]), [4, 2])

    def test_float_error_does_not_add_a_candidate(self):
        # 3 / 0.3 は 10.000000000000002 だが、必要なのは 10 人
        self.assertEqual(required_pipeline(3, [Stage("a", 0.3)]), [10])
        self.assertEqual(required_pipeline(7, [Stage("a", 0.7)]), [10])
        self.assertEqual(required_pipeline(6, [Stage("a", 0.6), Stage("b", 0.1)]), [100, 60])

    def test_pass_rate_one_needs_no_extra(self):
        self.assertEqual(required_pipeline(3, [Stage("a", 1.0), Stage("b", 1.0)]), [3, 3])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            required_pipeline(0, BOOK_STAGES)
        with self.assertRaises(ValueError):
            required_pipeline(1, [])
        for bad in (0.0, -0.1, 1.2):
            with self.assertRaises(ValueError, msg=str(bad)):
                required_pipeline(1, [Stage("a", bad)])
        with self.assertRaises(ValueError):
            required_pipeline(1, [Stage("a", 0.5), Stage("a", 0.5)])
        with self.assertRaises(ValueError):
            required_pipeline(1, [Stage("a", 0.5, duration_days=-1)])
        with self.assertRaises(ValueError):
            required_pipeline(1, [Stage("a", 0.5, interview_hours=-1)])


class TestExercise2TimeToFill(unittest.TestCase):
    def test_docstring_example(self):
        stages = [Stage("書類選考", 0.5, duration_days=3), Stage("オファー", 0.5, duration_days=7)]
        # 必要な応募者 8 人 ÷ 週 4 人 = 2 週 = 14 日、選考 3 + 7 = 10 日
        self.assertAlmostEqual(expected_time_to_fill(2, stages, weekly_applicants=4), 24.0)

    def test_book_example_misses_half_year(self):
        # 本文: 週 10 人の応募では半年（182 日）で 5 人は採れない
        days = expected_time_to_fill(5, BOOK_STAGES, weekly_applicants=10)
        self.assertAlmostEqual(days, 234 / 10 * 7 + 38)
        self.assertGreater(days, 182)

    def test_more_applicants_is_faster(self):
        slow = expected_time_to_fill(5, BOOK_STAGES, weekly_applicants=10)
        fast = expected_time_to_fill(5, BOOK_STAGES, weekly_applicants=12)
        self.assertLess(fast, slow)
        self.assertAlmostEqual(fast, 234 / 12 * 7 + 38)

    def test_invalid_inflow(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                expected_time_to_fill(5, BOOK_STAGES, weekly_applicants=bad)


class TestExercise3InterviewerLoad(unittest.TestCase):
    def test_docstring_example(self):
        stages = [Stage("書類選考", 0.5, interview_hours=0.5), Stage("面接", 0.5, interview_hours=2)]
        got = interviewer_load(2, stages, weeks=4, interviewers={"書類選考": 1, "面接": 2})
        self.assertEqual(set(got), {"書類選考", "面接"})
        self.assertAlmostEqual(got["書類選考"], 1.0)
        self.assertAlmostEqual(got["面接"], 1.0)

    def test_book_example(self):
        got = interviewer_load(
            5, BOOK_STAGES, weeks=26,
            interviewers={"書類選考": 3, "技術面接": 6, "ワークサンプル": 6, "最終面接": 2, "オファー": 1},
        )
        self.assertAlmostEqual(got["書類選考"], 234 * 0.5 / 26 / 3)
        self.assertAlmostEqual(got["ワークサンプル"], 28 * 5.0 / 26 / 6)
        self.assertAlmostEqual(got["最終面接"], 14 * 3.0 / 26 / 2)
        self.assertEqual(list(got), [s.name for s in BOOK_STAGES], "段階の順に並ぶ")

    def test_stages_without_interviews_are_skipped(self):
        stages = [Stage("自動テスト", 0.5, interview_hours=0), Stage("面接", 0.5, interview_hours=1)]
        got = interviewer_load(1, stages, weeks=1, interviewers={"面接": 1})
        self.assertEqual(got, {"面接": 2.0})

    def test_missing_interviewers_is_an_error(self):
        with self.assertRaises(ValueError):
            interviewer_load(5, BOOK_STAGES, weeks=26, interviewers={"書類選考": 3})
        with self.assertRaises(ValueError):
            interviewer_load(1, [Stage("面接", 0.5, interview_hours=1)], weeks=1, interviewers={"面接": 0})

    def test_invalid_weeks(self):
        with self.assertRaises(ValueError):
            interviewer_load(1, [Stage("面接", 0.5, interview_hours=1)], weeks=0, interviewers={"面接": 1})


class TestExercise4CostPerHire(unittest.TestCase):
    def test_docstring_example(self):
        chs = [Channel("紹介", 0.5, fee_rate=0.3), Channel("リファラル", 0.5, fee_per_hire=20)]
        got = cost_per_hire(chs, hires=4, annual_salary=1000, internal_cost=40)
        self.assertEqual(list(got), ["紹介", "リファラル", "合計"])
        self.assertAlmostEqual(got["紹介"], 300.0)
        self.assertAlmostEqual(got["リファラル"], 20.0)
        # (300 * 2 + 20 * 2 + 40) / 4
        self.assertAlmostEqual(got["合計"], 170.0)

    def test_book_example(self):
        channels = [
            Channel("リファラル", 0.3, fee_per_hire=30),
            Channel("人材紹介", 0.4, fee_rate=0.35),
            Channel("ダイレクト", 0.3, fixed_cost=300),
        ]
        got = cost_per_hire(channels, hires=10, annual_salary=800, internal_cost=625.8)
        self.assertAlmostEqual(got["リファラル"], 30.0)
        self.assertAlmostEqual(got["人材紹介"], 280.0)
        self.assertAlmostEqual(got["ダイレクト"], 100.0)
        self.assertAlmostEqual(got["合計"], (90 + 1120 + 300 + 625.8) / 10)

    def test_fixed_cost_with_no_hires_is_infinite(self):
        chs = [Channel("媒体", 0.0, fixed_cost=100), Channel("紹介", 1.0, fee_rate=0.3)]
        got = cost_per_hire(chs, hires=2, annual_salary=1000)
        self.assertTrue(math.isinf(got["媒体"]))
        self.assertAlmostEqual(got["紹介"], 300.0)
        self.assertAlmostEqual(got["合計"], (100 + 600) / 2, msg="固定費は合計に含まれる")

    def test_zero_share_without_fixed_cost(self):
        chs = [Channel("イベント", 0.0, fee_per_hire=5), Channel("紹介", 1.0, fee_rate=0.3)]
        got = cost_per_hire(chs, hires=1, annual_salary=1000)
        self.assertAlmostEqual(got["イベント"], 5.0)

    def test_fractional_channel_hires(self):
        chs = [Channel("媒体", 0.25, fixed_cost=100), Channel("紹介", 0.75, fee_rate=0.3)]
        got = cost_per_hire(chs, hires=2, annual_salary=1000)
        self.assertAlmostEqual(got["媒体"], 200.0)   # 100 / 0.5 人
        self.assertAlmostEqual(got["合計"], (100 + 300 * 1.5) / 2)

    def test_invalid_inputs(self):
        ok = [Channel("紹介", 1.0, fee_rate=0.3)]
        with self.assertRaises(ValueError):
            cost_per_hire(ok, hires=0, annual_salary=800)
        with self.assertRaises(ValueError):
            cost_per_hire(ok, hires=1, annual_salary=-1)
        with self.assertRaises(ValueError):
            cost_per_hire(ok, hires=1, annual_salary=800, internal_cost=-1)
        with self.assertRaises(ValueError):
            cost_per_hire([], hires=1, annual_salary=800)
        with self.assertRaises(ValueError):
            cost_per_hire([Channel("a", 0.5), Channel("b", 0.4)], hires=1, annual_salary=800)
        with self.assertRaises(ValueError):
            cost_per_hire([Channel("a", 1.0, fee_rate=-0.1)], hires=1, annual_salary=800)
        with self.assertRaises(ValueError):
            cost_per_hire([Channel("合計", 1.0)], hires=1, annual_salary=800)


if __name__ == "__main__":
    unittest.main()
