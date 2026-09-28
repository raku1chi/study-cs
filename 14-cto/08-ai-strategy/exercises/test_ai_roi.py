"""14.8 AI戦略とAIガバナンス — テスト（ai_roi）

実行: python3 tools/check.py 14.8   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from dataclasses import replace

from ai_roi import (
    AIFeatureModel,
    MonthlyResult,
    break_even,
    cost_per_request,
    monthly_result,
    payback_month,
    run_scenarios,
    sensitivity,
)

# 本文の例: 問い合わせへの一次回答の下書きを AI が作る機能（数値はすべて仮定）
BASE = AIFeatureModel(
    eligible_requests=20_000,   # 月 2 万件の問い合わせ
    adoption=0.6,               # うち 6 割で AI を使う
    input_tokens=3_000,         # 検索した社内文書を含む入力
    output_tokens=500,
    price_in_per_mtok=300,      # 100 万トークンあたり 300 円（仮定）
    price_out_per_mtok=1_500,   # 100 万トークンあたり 1,500 円（仮定）
    accuracy=0.85,
    review_rate=0.3,
    review_minutes=2,
    minutes_saved=6,
    hourly_cost=4_000,
    calls_per_request=2,
    error_cost=1_000,
    fixed_monthly=800_000,
    build_cost=6_000_000,
)


class TestExercise2CostPerRequest(unittest.TestCase):
    def test_base(self):
        # 2 回 × (3,000 × 300 + 500 × 1,500) ÷ 100 万 = 3.3 円
        self.assertAlmostEqual(cost_per_request(BASE), 3.3, places=9)

    def test_single_call_and_zero_output(self):
        m = replace(BASE, calls_per_request=1, output_tokens=0)
        self.assertAlmostEqual(cost_per_request(m), 0.9, places=9)

    def test_validation(self):
        with self.assertRaises(ValueError):
            cost_per_request(replace(BASE, input_tokens=-1))
        with self.assertRaises(ValueError):
            cost_per_request(replace(BASE, accuracy=1.2))
        with self.assertRaises(TypeError):
            cost_per_request(replace(BASE, output_tokens="500"))


class TestExercise2MonthlyResult(unittest.TestCase):
    def test_base_breakdown(self):
        r = monthly_result(BASE)
        self.assertIsInstance(r, MonthlyResult)
        expected = {
            "handled": 12_000, "model_cost": 39_600, "review_cost": 480_000,
            "error_cost": 1_260_000, "fixed_cost": 800_000, "savings": 4_080_000, "revenue": 0,
        }
        for name, value in expected.items():
            self.assertAlmostEqual(getattr(r, name), value, places=6, msg=name)
        self.assertAlmostEqual(r.total_cost, 2_579_600, places=6)
        self.assertAlmostEqual(r.total_value, 4_080_000, places=6)
        self.assertAlmostEqual(r.net, 1_500_400, places=6)

    def test_token_cost_is_small_compared_with_people_and_errors(self):
        r = monthly_result(BASE)
        self.assertLess(r.model_cost, r.review_cost / 10, "この例ではトークン代よりレビューの人件費が桁違いに大きい")

    def test_revenue_only_from_correct_results(self):
        r = monthly_result(replace(BASE, revenue_per_success=100))
        self.assertAlmostEqual(r.revenue, 12_000 * 0.85 * 100, places=6)

    def test_full_review_means_no_escaped_errors(self):
        r = monthly_result(replace(BASE, review_rate=1.0))
        self.assertEqual(r.error_cost, 0)
        self.assertAlmostEqual(r.review_cost, 12_000 * 2 / 60 * 4_000, places=6)

    def test_zero_adoption(self):
        r = monthly_result(replace(BASE, adoption=0))
        self.assertEqual(r.handled, 0)
        self.assertAlmostEqual(r.net, -800_000, places=6, msg="固定費だけが残る")

    def test_scenarios(self):
        results = run_scenarios(BASE, {
            "悲観": {"adoption": 0.3, "accuracy": 0.75},
            "基本": {},
            "楽観": {"adoption": 0.8, "accuracy": 0.92},
        })
        self.assertEqual(list(results), ["悲観", "基本", "楽観"])
        self.assertAlmostEqual(results["基本"].net, 1_500_400, places=6)
        # 悲観: 6,000 件。節約 6,000×0.75×400 − (19,800 + 240,000 + 6,000×0.25×0.7×1,000 + 800,000)
        self.assertAlmostEqual(results["悲観"].net, 1_800_000 - 2_109_800, places=6)
        self.assertGreater(results["楽観"].net, results["基本"].net)
        with self.assertRaises(ValueError, msg="未知のパラメータ"):
            run_scenarios(BASE, {"x": {"adoptoin": 0.5}})


class TestExercise3BreakEvenAndPayback(unittest.TestCase):
    def test_break_even_accuracy(self):
        # net = 13,200,000 × accuracy − 9,719,600
        a = break_even(BASE, "accuracy", 0.0, 1.0)
        self.assertAlmostEqual(a, 9_719_600 / 13_200_000, places=7)

    def test_break_even_adoption(self):
        # 1 件あたりの利益 191.7 円 × 2 万件 × adoption = 固定費 80 万円
        a = break_even(BASE, "adoption", 0.0, 1.0)
        self.assertAlmostEqual(a, 800_000 / (20_000 * 191.7), places=7)

    def test_no_sign_change_returns_none(self):
        # 時給 5,000〜8,000 円の範囲ではずっと黒字
        self.assertIsNone(break_even(BASE, "hourly_cost", 5_000, 8_000))

    def test_break_even_at_endpoint(self):
        m = replace(BASE, fixed_monthly=0, error_cost=0, review_rate=0, minutes_saved=0)
        # 節約がゼロで出力トークンの単価が残っているので、入力単価を動かしてもずっと赤字
        self.assertIsNone(break_even(m, "price_in_per_mtok", 0.0, 1.0))
        # 呼び出し回数 0 回なら費用もゼロ → 区間の端点がちょうど損益分岐点
        self.assertEqual(break_even(m, "calls_per_request", 0.0, 3.0), 0.0)

    def test_break_even_validation(self):
        with self.assertRaises(ValueError):
            break_even(BASE, "accuracy", 1.0, 0.0)
        with self.assertRaises(ValueError):
            break_even(BASE, "no_such_field", 0.0, 1.0)

    def test_payback_with_ramp(self):
        # 利用率が 3 か月かけて立ち上がる場合、6 か月目に初期投資 600 万円を回収
        self.assertEqual(payback_month(BASE, horizon_months=24, ramp_months=3), 6)
        self.assertIsNone(payback_month(BASE, horizon_months=5, ramp_months=3))

    def test_payback_without_ramp(self):
        self.assertEqual(payback_month(BASE, horizon_months=24), 4)
        self.assertEqual(payback_month(replace(BASE, build_cost=0), horizon_months=1), 1)

    def test_payback_never_when_losing_money(self):
        loss = replace(BASE, accuracy=0.6)
        self.assertLess(monthly_result(loss).net, 0)
        self.assertIsNone(payback_month(loss, horizon_months=60, ramp_months=3))

    def test_payback_validation(self):
        with self.assertRaises(ValueError):
            payback_month(BASE, horizon_months=0)
        with self.assertRaises(ValueError):
            payback_month(BASE, horizon_months=12, ramp_months=-1)


class TestExercise4Sensitivity(unittest.TestCase):
    def test_tornado_order_and_values(self):
        rows = sensitivity(BASE, ["price_in_per_mtok", "error_cost", "adoption", "minutes_saved", "accuracy"])
        self.assertEqual([r[0] for r in rows],
                         ["accuracy", "minutes_saved", "adoption", "error_cost", "price_in_per_mtok"])
        name, low, high = rows[0]
        self.assertAlmostEqual(low, 13_200_000 * 0.68 - 9_719_600, places=5)
        self.assertAlmostEqual(high, 13_200_000 * 1.0 - 9_719_600, places=5, msg="精度は 1.0 で頭打ち")
        name, low, high = rows[-1]
        self.assertAlmostEqual(high - low, -8_640, places=5, msg="単価が上がると利益は減る")

    def test_values_match_monthly_result(self):
        for name, low, high in sensitivity(BASE, ["hourly_cost", "review_rate"], delta=0.1):
            v = getattr(BASE, name)
            self.assertAlmostEqual(low, monthly_result(replace(BASE, **{name: v * 0.9})).net, places=6)
            self.assertAlmostEqual(high, monthly_result(replace(BASE, **{name: v * 1.1})).net, places=6)

    def test_ties_sorted_by_name(self):
        m = replace(BASE, price_in_per_mtok=0, price_out_per_mtok=0)
        rows = sensitivity(m, ["price_out_per_mtok", "price_in_per_mtok"])
        self.assertEqual([r[0] for r in rows], ["price_in_per_mtok", "price_out_per_mtok"])

    def test_validation(self):
        with self.assertRaises(ValueError):
            sensitivity(BASE, ["accuracy"], delta=0)
        with self.assertRaises(ValueError):
            sensitivity(BASE, ["accuracy"], delta=1.5)
        with self.assertRaises(ValueError):
            sensitivity(BASE, ["unknown"])


if __name__ == "__main__":
    unittest.main()
