"""11.1 リスク登録簿（risk_register）— テスト

実行: python3 tools/check.py 11.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from risk_register import (
    Assessment,
    Control,
    Risk,
    annualized_loss_expectancy,
    assess,
    combined_effectiveness,
    control_net_benefit,
    heat_map,
    inherent_score,
    render_report,
    residual_likelihood,
    risk_level,
    single_loss_expectancy,
    top_risks,
)


def sample_risks() -> list[Risk]:
    return [
        Risk("R-01", "ランサムウェアで基幹業務が停止する", "CIO", 4, 5,
             (Control("全社MFA", 0.5), Control("パッチ管理", 0.4))),
        Risk("R-02", "退職者アカウントからの情報持ち出し", "人事部長", 3, 4,
             (Control("アカウント棚卸し", 0.6),)),
        Risk("R-03", "経費データのメール誤送信", "経理部長", 4, 2),
        Risk("R-04", "クラウドの設定ミスによるデータ公開", "CTO", 3, 5, (Control("CSPM", 0.5),)),
        Risk("R-05", "DDoS によるサービス停止", "SREリード", 2, 3, (Control("CDN", 0.9),)),
        Risk("R-06", "依存パッケージへのサプライチェーン攻撃", "CTO", 2, 5),
    ]


class TestExercise1Ale(unittest.TestCase):
    def test_sle_ale_and_net_benefit(self):
        sle = single_loss_expectancy(50_000_000, 0.4)
        self.assertAlmostEqual(sle, 20_000_000)
        ale_before = annualized_loss_expectancy(sle, 0.25)  # 4 年に 1 回
        self.assertAlmostEqual(ale_before, 5_000_000)
        ale_after = annualized_loss_expectancy(sle, 0.05)  # 20 年に 1 回に下がる
        self.assertAlmostEqual(ale_after, 1_000_000)
        self.assertAlmostEqual(control_net_benefit(ale_before, ale_after, 1_500_000), 2_500_000)
        self.assertLess(control_net_benefit(ale_before, ale_after, 6_000_000), 0,
                        "対策コストが削減額を上回るなら純便益はマイナス")

    def test_boundaries(self):
        self.assertEqual(single_loss_expectancy(1000, 0.0), 0.0)
        self.assertEqual(single_loss_expectancy(1000, 1.0), 1000.0)
        self.assertEqual(annualized_loss_expectancy(1000, 0), 0)

    def test_invalid(self):
        for args in [(-1, 0.5), (100, -0.1), (100, 1.1)]:
            with self.assertRaises(ValueError, msg=str(args)):
                single_loss_expectancy(*args)
        with self.assertRaises(ValueError):
            annualized_loss_expectancy(100, -1)
        with self.assertRaises(ValueError):
            annualized_loss_expectancy(-100, 1)


class TestExercise2Residual(unittest.TestCase):
    def test_combined_effectiveness(self):
        self.assertEqual(combined_effectiveness(()), 0.0)
        self.assertAlmostEqual(combined_effectiveness((Control("a", 0.5),)), 0.5)
        # すり抜ける確率 0.5 × 0.6 = 0.3 → 効果 0.7（0.5 + 0.4 = 0.9 ではない）
        self.assertAlmostEqual(combined_effectiveness((Control("a", 0.5), Control("b", 0.4))), 0.7)
        self.assertAlmostEqual(combined_effectiveness((Control("a", 1.0), Control("b", 0.4))), 1.0)
        for bad in (-0.1, 1.5):
            with self.assertRaises(ValueError):
                combined_effectiveness((Control("x", bad),))

    def test_inherent_score(self):
        self.assertEqual(inherent_score(Risk("r", "t", "o", 4, 5)), 20)
        self.assertEqual(inherent_score(Risk("r", "t", "o", 1, 1)), 1)
        for l, i in [(0, 3), (6, 3), (3, 0), (3, 6), (True, 3)]:
            with self.assertRaises(ValueError, msg=str((l, i))):
                inherent_score(Risk("r", "t", "o", l, i))

    def test_residual_likelihood_rounds_up(self):
        self.assertEqual(residual_likelihood(Risk("r", "t", "o", 4, 5, (Control("a", 0.5), Control("b", 0.4)))), 2)
        self.assertEqual(residual_likelihood(Risk("r", "t", "o", 3, 4, (Control("a", 0.3),))), 3)  # 2.1 → 3
        self.assertEqual(residual_likelihood(Risk("r", "t", "o", 4, 2)), 4, "対策がなければ下がらない")
        self.assertEqual(residual_likelihood(Risk("r", "t", "o", 5, 5, (Control("a", 1.0),))), 1, "下限は 1")

    def test_residual_likelihood_is_robust_to_float_error(self):
        # 5 × (1 - 0.2) × (1 - 0.25) = 3（ちょうど）。素朴な float 計算では 3.0000000000000004
        risk = Risk("r", "t", "o", 5, 3, (Control("a", 0.2), Control("b", 0.25)))
        self.assertEqual(residual_likelihood(risk), 3)

    def test_risk_level_bands(self):
        expected = {1: "低", 4: "低", 5: "中", 9: "中", 10: "高", 16: "高", 17: "重大", 20: "重大", 25: "重大"}
        for score, level in expected.items():
            self.assertEqual(risk_level(score), level, score)
        for bad in (0, 26, -1, True):
            with self.assertRaises(ValueError):
                risk_level(bad)

    def test_assess(self):
        a = assess(sample_risks()[0])
        self.assertIsInstance(a, Assessment)
        self.assertEqual(
            (a.risk_id, a.inherent_score, a.residual_likelihood, a.residual_score, a.level, a.needs_treatment),
            ("R-01", 20, 2, 10, "高", True),
        )
        b = assess(sample_risks()[1])
        self.assertEqual((b.residual_score, b.level, b.needs_treatment), (8, "中", False))
        self.assertTrue(assess(sample_risks()[1], appetite=7).needs_treatment, "許容水準を下げると要対応になる")


class TestExercise3Report(unittest.TestCase):
    def test_heat_map_residual(self):
        self.assertEqual(
            heat_map(sample_risks()),
            {(2, 5): ["R-01", "R-04", "R-06"], (2, 4): ["R-02"], (4, 2): ["R-03"], (1, 3): ["R-05"]},
        )

    def test_heat_map_inherent(self):
        self.assertEqual(
            heat_map(sample_risks(), residual=False),
            {(4, 5): ["R-01"], (3, 4): ["R-02"], (4, 2): ["R-03"], (3, 5): ["R-04"], (2, 3): ["R-05"], (2, 5): ["R-06"]},
        )

    def test_top_risks_order(self):
        ranked = top_risks(sample_risks(), n=6)
        # 残存スコアの降順 → 固有スコアの降順 → ID の昇順
        self.assertEqual([a.risk_id for a in ranked], ["R-01", "R-04", "R-06", "R-02", "R-03", "R-05"])
        self.assertEqual([a.risk_id for a in top_risks(sample_risks(), n=2)], ["R-01", "R-04"])
        self.assertEqual(top_risks([], n=3), [])

    def test_render_report(self):
        text = render_report(sample_risks(), n=3)
        self.assertEqual(
            text,
            "| ID | リスク | オーナー | 固有 | 残存 | レベル | 対応 |\n"
            "|---|---|---|---|---|---|---|\n"
            "| R-01 | ランサムウェアで基幹業務が停止する | CIO | 20 | 10 | 高 | 要対応 |\n"
            "| R-04 | クラウドの設定ミスによるデータ公開 | CTO | 15 | 10 | 高 | 要対応 |\n"
            "| R-06 | 依存パッケージへのサプライチェーン攻撃 | CTO | 10 | 10 | 高 | 要対応 |\n",
        )

    def test_render_report_accept(self):
        text = render_report(sample_risks(), n=6, appetite=10)
        self.assertIn("| R-01 | ランサムウェアで基幹業務が停止する | CIO | 20 | 10 | 高 | 受容可 |", text)
        self.assertIn("| R-05 | DDoS によるサービス停止 | SREリード | 6 | 3 | 低 | 受容可 |", text)


if __name__ == "__main__":
    unittest.main()
