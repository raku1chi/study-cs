"""14.8 AI戦略とAIガバナンス — テスト（ai_usecase_tier）

実行: python3 tools/check.py 14.8   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from ai_usecase_tier import (
    BASE_CONTROLS,
    HIGH_CONTROLS,
    PROHIBITED_CONTROLS,
    QUESTIONS,
    TRANSPARENCY_CONTROLS,
    TierResult,
    classify_use_case,
    summarize_inventory,
)


def answers(*yes):
    """指定した質問だけ True、ほかは False の回答一式を作る。"""
    for key in yes:
        assert key in QUESTIONS, key
    return {key: key in yes for key in QUESTIONS}


class TestExercise1ClassifyUseCase(unittest.TestCase):
    def test_minimal(self):
        r = classify_use_case(answers())  # 例: 社内向けのコードレビュー補助
        self.assertIsInstance(r, TierResult)
        self.assertEqual(r.tier, "minimal")
        self.assertEqual(r.reasons, ())
        self.assertFalse(r.escalated_by_policy)
        self.assertEqual(r.controls, BASE_CONTROLS)

    def test_limited_chatbot(self):
        r = classify_use_case(answers("interacts_with_people"))
        self.assertEqual(r.tier, "limited")
        self.assertEqual(r.reasons, ("interacts_with_people",))
        self.assertEqual(r.controls, BASE_CONTROLS + (TRANSPARENCY_CONTROLS["interacts_with_people"],))

    def test_high_risk_domain(self):
        r = classify_use_case(answers("employment_decision", "interacts_with_people"))
        self.assertEqual(r.tier, "high")
        self.assertFalse(r.escalated_by_policy)
        self.assertEqual(r.reasons, ("employment_decision", "interacts_with_people"), "QUESTIONS の順に並べる")
        expected = BASE_CONTROLS + (TRANSPARENCY_CONTROLS["interacts_with_people"],) + HIGH_CONTROLS
        self.assertEqual(r.controls, expected)

    def test_policy_escalation(self):
        # 規制の類型に当たらなくても、社内基準で high に引き上げる
        r = classify_use_case(answers("fully_automated_significant_decision"))
        self.assertEqual(r.tier, "high")
        self.assertTrue(r.escalated_by_policy)
        r2 = classify_use_case(answers("uses_sensitive_personal_data", "generates_synthetic_media"))
        self.assertEqual(r2.tier, "high")
        self.assertTrue(r2.escalated_by_policy)
        self.assertIn(TRANSPARENCY_CONTROLS["generates_synthetic_media"], r2.controls)

    def test_domain_high_risk_is_not_policy_escalation(self):
        r = classify_use_case(answers("credit_or_insurance_decision", "uses_sensitive_personal_data"))
        self.assertEqual(r.tier, "high")
        self.assertFalse(r.escalated_by_policy, "分野だけで high になるなら社内基準による引き上げではない")

    def test_prohibited_overrides_everything(self):
        r = classify_use_case(answers("workplace_emotion_recognition", "employment_decision"))
        self.assertEqual(r.tier, "prohibited")
        self.assertEqual(r.controls, PROHIBITED_CONTROLS)
        self.assertEqual(r.reasons, ("workplace_emotion_recognition", "employment_decision"))

    def test_every_prohibited_question(self):
        for key in ("manipulative_or_exploitative", "social_scoring",
                    "workplace_emotion_recognition", "untargeted_face_scraping"):
            self.assertEqual(classify_use_case(answers(key)).tier, "prohibited", key)

    def test_missing_answers_are_errors(self):
        partial = answers()
        del partial["biometric_identification"]
        with self.assertRaises(ValueError, msg="未回答を「いいえ」とみなさない"):
            classify_use_case(partial)

    def test_unknown_and_non_bool_answers(self):
        extra = answers()
        extra["is_cool"] = True
        with self.assertRaises(ValueError):
            classify_use_case(extra)
        bad = answers()
        bad["social_scoring"] = "no"
        with self.assertRaises(TypeError):
            classify_use_case(bad)


class TestExercise1SummarizeInventory(unittest.TestCase):
    def test_grouping(self):
        inventory = {
            "採用書類の自動スクリーニング": answers("employment_decision"),
            "サポートチャットボット": answers("interacts_with_people"),
            "社内コード補完": answers(),
            "広告バナー生成": answers("generates_synthetic_media"),
            "議事録の要約": answers(),
        }
        summary = summarize_inventory(inventory)
        self.assertEqual(list(summary), ["prohibited", "high", "limited", "minimal"])
        self.assertEqual(summary["prohibited"], [])
        self.assertEqual(summary["high"], ["採用書類の自動スクリーニング"])
        self.assertEqual(summary["limited"], sorted(["サポートチャットボット", "広告バナー生成"]))
        self.assertEqual(summary["minimal"], sorted(["社内コード補完", "議事録の要約"]))

    def test_empty_inventory(self):
        self.assertEqual(summarize_inventory({}), {"prohibited": [], "high": [], "limited": [], "minimal": []})


if __name__ == "__main__":
    unittest.main()
