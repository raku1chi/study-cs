"""14.7 技術デューデリジェンスとM&A — テスト

実行: python3 tools/check.py 14.7   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from dataclasses import replace

from dd_scorecard import Finding, Rating, area_scores, overall_rating, remediation_plan

WEIGHTS = {
    "architecture": 2.0,
    "code_quality": 1.0,
    "security": 3.0,
    "privacy": 2.0,
    "ip_oss": 3.0,
    "infrastructure": 1.0,
    "team": 2.0,
    "process": 1.0,
}

F1 = Finding("F1", "security", "本番DBに共有の管理者アカウント", "high", 1.0, effort_days=5)
F2 = Finding("F2", "security", "既知の脆弱性がある依存ライブラリ（推定）", "medium", 0.5, effort_days=3)
F3 = Finding("F3", "ip_oss", "創業期の外注コードの権利譲渡が未確認", "critical", 0.9, red_flag=True, effort_days=20)
F4 = Finding("F4", "team", "決済基盤を理解しているのが1人だけ", "high", 0.8, effort_days=30)
F5 = Finding("F5", "architecture", "単一リージョン構成", "medium", 1.0, effort_days=40)
F6 = Finding("F6", "process", "ポストモーテムを書く習慣がない", "low", 1.0, effort_days=2)
F7 = Finding("F7", "code_quality", "決済の重要経路に自動テストがない", "medium", 0.7, effort_days=15)
SAMPLE = [F1, F2, F3, F4, F5, F6, F7]


class TestExercise1AreaScores(unittest.TestCase):
    def test_sample_scores(self):
        scores = area_scores(SAMPLE, WEIGHTS)
        expected = {
            "architecture": 92.0, "code_quality": 94.4, "security": 76.0, "privacy": 100.0,
            "ip_oss": 64.0, "infrastructure": 100.0, "team": 84.0, "process": 98.0,
        }
        self.assertEqual(set(scores), set(expected), "所見のない領域も 100 点で含めること")
        for area, value in expected.items():
            self.assertAlmostEqual(scores[area], value, places=9, msg=area)

    def test_score_does_not_go_below_zero(self):
        many = [Finding(f"X{i}", "security", "重大な問題", "critical") for i in range(4)]
        self.assertEqual(area_scores(many, ["security"]), {"security": 0.0})

    def test_zero_confidence_has_no_effect(self):
        f = Finding("X", "security", "未確認の噂", "critical", confidence=0.0)
        self.assertEqual(area_scores([f], ["security"]), {"security": 100.0})

    def test_validation(self):
        with self.assertRaises(ValueError, msg="未知の領域"):
            area_scores([Finding("X", "legal", "t", "low")], WEIGHTS)
        with self.assertRaises(ValueError, msg="未知の深刻度"):
            area_scores([Finding("X", "security", "t", "severe")], WEIGHTS)
        for c in (-0.1, 1.5):
            with self.assertRaises(ValueError, msg=f"confidence={c}"):
                area_scores([Finding("X", "security", "t", "low", confidence=c)], WEIGHTS)
        with self.assertRaises(ValueError, msg="負の工数"):
            area_scores([Finding("X", "security", "t", "low", effort_days=-1)], WEIGHTS)


class TestExercise2OverallRating(unittest.TestCase):
    def test_confirmed_red_flag_overrides_good_score(self):
        r = overall_rating(SAMPLE, WEIGHTS)
        self.assertIsInstance(r, Rating)
        self.assertAlmostEqual(r.score, 1264.4 / 15, places=9)
        self.assertGreaterEqual(r.score, 75, "スコアだけなら GREEN の水準")
        self.assertEqual(r.rag, "RED", "確度の高いレッドフラグは平均に埋もれさせない")
        self.assertEqual(r.reasons, ("red_flag:F3",))
        self.assertAlmostEqual(r.coverage, 1.0)

    def test_unconfirmed_red_flag_blocks_green(self):
        findings = [replace(F3, confidence=0.3) if f is F3 else f for f in SAMPLE]
        r = overall_rating(findings, WEIGHTS)
        self.assertAlmostEqual(r.score, 1336.4 / 15, places=9)
        self.assertEqual(r.rag, "AMBER")
        self.assertEqual(r.reasons, ("unconfirmed_red_flag:F3",))

    def test_red_flag_threshold_is_inclusive(self):
        findings = [replace(F3, confidence=0.5)]
        r = overall_rating(findings, WEIGHTS)
        self.assertEqual(r.rag, "RED")
        r2 = overall_rating(findings, WEIGHTS, red_flag_min_confidence=0.6)
        self.assertEqual(r2.rag, "AMBER")

    def test_low_coverage_blocks_green(self):
        clean = [F5, F6]
        reviewed = ["architecture", "code_quality", "security", "ip_oss", "team"]  # 11/15
        r = overall_rating(clean, WEIGHTS, reviewed=reviewed + ["process"])
        self.assertAlmostEqual(r.coverage, 12 / 15)
        self.assertEqual(r.rag, "GREEN", "カバレッジ 0.8 はしきい値ちょうどで不足ではない")
        r2 = overall_rating([F5], WEIGHTS, reviewed=reviewed)
        self.assertAlmostEqual(r2.coverage, 11 / 15)
        self.assertEqual(r2.rag, "AMBER")
        self.assertEqual(r2.reasons, ("low_coverage",))

    def test_score_uses_only_reviewed_areas(self):
        # security だけレビューし、76 点。ほかの領域は計算に入れない
        r = overall_rating([F1, F2], {"security": 3.0, "privacy": 2.0}, reviewed=["security"], min_coverage=0.5)
        self.assertAlmostEqual(r.score, 76.0)
        self.assertAlmostEqual(r.coverage, 0.6)
        self.assertEqual(r.rag, "GREEN")

    def test_score_thresholds(self):
        w = {"security": 1.0}
        cases = [
            ([Finding("A", "security", "t", "critical", 0.625)], 75.0, "GREEN"),
            ([Finding("A", "security", "t", "critical", 0.65)], 74.0, "AMBER"),
            ([Finding("A", "security", "t", "critical"), Finding("B", "security", "t", "high", 0.5)], 50.0, "AMBER"),
            ([Finding("A", "security", "t", "critical"), Finding("B", "security", "t", "high", 0.6)], 48.0, "RED"),
        ]
        for findings, score, rag in cases:
            r = overall_rating(findings, w)
            self.assertAlmostEqual(r.score, score, msg=findings)
            self.assertEqual(r.rag, rag, msg=f"score={score}")
            self.assertEqual(r.reasons, ())

    def test_validation(self):
        with self.assertRaises(ValueError, msg="重みが 0"):
            overall_rating([], {"security": 0.0})
        with self.assertRaises(ValueError, msg="weights が空"):
            overall_rating([], {})
        with self.assertRaises(ValueError, msg="reviewed に未知の領域"):
            overall_rating([], WEIGHTS, reviewed=["legal"])
        with self.assertRaises(ValueError, msg="レビュー済みの領域が空"):
            overall_rating([], WEIGHTS, reviewed=[])
        with self.assertRaises(ValueError, msg="未レビューの領域に所見"):
            overall_rating([F1], WEIGHTS, reviewed=["team"])


class TestExercise3RemediationPlan(unittest.TestCase):
    def test_sample_order(self):
        plan = remediation_plan(SAMPLE, WEIGHTS)
        self.assertEqual([f.id for f in plan], ["F3", "F1", "F4", "F5", "F2", "F7", "F6"])

    def test_red_flags_first_even_with_low_confidence(self):
        weak_flag = Finding("Z", "process", "未確認の不正アクセスの噂", "low", 0.1, red_flag=True)
        plan = remediation_plan([F1, weak_flag], WEIGHTS)
        self.assertEqual([f.id for f in plan], ["Z", "F1"])

    def test_ties_broken_by_effort_then_id(self):
        a = Finding("B-2", "security", "t", "medium", effort_days=10)
        b = Finding("B-1", "security", "t", "medium", effort_days=10)
        c = Finding("A-9", "security", "t", "medium", effort_days=3)
        self.assertEqual([f.id for f in remediation_plan([a, b, c], WEIGHTS)], ["A-9", "B-1", "B-2"])

    def test_input_not_modified_and_validation(self):
        items = [F6, F1]
        remediation_plan(items, WEIGHTS)
        self.assertEqual(items, [F6, F1])
        self.assertEqual(remediation_plan([], WEIGHTS), [])
        with self.assertRaises(ValueError):
            remediation_plan([Finding("X", "legal", "t", "low")], WEIGHTS)


if __name__ == "__main__":
    unittest.main()
