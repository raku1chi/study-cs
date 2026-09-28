"""14.4 経営陣・取締役会・投資家とのコミュニケーション — テスト（kpi_report.py）

実行: python3 tools/check.py 14.4   （またはこのディレクトリで python3 -m unittest -v test_kpi_report）
"""
import unittest

from kpi_report import Metric, format_value, overall_status, rag_status, render_report, trend


def board_metrics():
    """本文 3.4 節の例。"""
    return [
        Metric("変更のリードタイム（中央値）", 30, 24, False, 6, 36, "時間", "デリバリー", 1),
        Metric("ロードマップ達成率", 70, 80, True, 5, 78, "%", "デリバリー", 2),
        Metric("可用性（主要 API）", 99.95, 99.9, True, 0.05, 99.82, "%", "信頼性", 0.01),
        Metric("重大インシデント", 3, 2, False, 1, 5, "件", "信頼性"),
        Metric("重大な脆弱性の修正日数（中央値）", 9, 14, False, 3, 12, "日", "セキュリティ", 1),
        Metric("多要素認証の適用率", 100, 100, True, 1, 97, "%", "セキュリティ"),
        Metric("採用計画の達成率", 60, 90, True, 10, 70, "%", "人と組織", 5),
        Metric("惜しまれる離職（年率）", 6, 8, False, 2, 7, "%", "人と組織", 0.5),
        Metric("売上に対するクラウド費用", 13.5, 12, False, 2, 12.8, "%", "コスト", 0.2),
    ]


class TestRagStatus(unittest.TestCase):
    def test_higher_is_better(self):
        cases = [(80, "green"), (85, "green"), (79, "amber"), (75, "amber"), (74.5, "red"), (0, "red")]
        for value, expected in cases:
            self.assertEqual(rag_status(Metric("x", value, 80, amber_band=5)), expected, value)

    def test_lower_is_better(self):
        cases = [(2, "green"), (0, "green"), (2.5, "amber"), (3, "amber"), (3.5, "red")]
        for value, expected in cases:
            m = Metric("x", value, 2, higher_is_better=False, amber_band=1)
            self.assertEqual(rag_status(m), expected, value)

    def test_zero_band_means_any_shortfall_is_red(self):
        self.assertEqual(rag_status(Metric("x", 99, 100)), "red")
        self.assertEqual(rag_status(Metric("x", 100, 100)), "green")
        self.assertEqual(rag_status(Metric("x", 0.1, 0, higher_is_better=False)), "red")

    def test_negative_band_is_rejected(self):
        with self.assertRaises(ValueError):
            rag_status(Metric("x", 1, 1, amber_band=-1))

    def test_board_example(self):
        got = [rag_status(m) for m in board_metrics()]
        self.assertEqual(
            got, ["amber", "red", "green", "amber", "green", "green", "red", "green", "amber"]
        )


class TestTrend(unittest.TestCase):
    def test_direction_depends_on_metric(self):
        self.assertEqual(trend(Metric("up", 90, 80, previous=85)), "improving")
        self.assertEqual(trend(Metric("up", 80, 80, previous=85)), "worsening")
        self.assertEqual(trend(Metric("down", 3, 2, False, previous=5)), "improving")
        self.assertEqual(trend(Metric("down", 6, 2, False, previous=5)), "worsening")

    def test_noise_and_missing_previous(self):
        self.assertEqual(trend(Metric("x", 10, 10)), "n/a")
        self.assertEqual(trend(Metric("x", 10.5, 10, previous=10, noise=0.5)), "flat")
        self.assertEqual(trend(Metric("x", 11, 10, previous=10, noise=0.5)), "improving")
        self.assertEqual(trend(Metric("x", 10, 10, previous=10)), "flat")
        with self.assertRaises(ValueError):
            trend(Metric("x", 10, 10, previous=9, noise=-1))

    def test_board_example(self):
        got = [trend(m) for m in board_metrics()]
        self.assertEqual(
            got,
            ["improving", "worsening", "improving", "improving", "improving",
             "improving", "worsening", "improving", "worsening"],
        )


class TestOverall(unittest.TestCase):
    def test_worst_status_wins(self):
        green = Metric("g", 1, 1)
        amber = Metric("a", 9, 10, amber_band=1)
        red = Metric("r", 0, 10)
        self.assertEqual(overall_status([green]), "green")
        self.assertEqual(overall_status([green, amber]), "amber")
        self.assertEqual(overall_status([amber, red, green]), "red")
        with self.assertRaises(ValueError):
            overall_status([])


class TestRender(unittest.TestCase):
    def test_format_value(self):
        self.assertEqual(format_value(1234.0), "1,234")
        self.assertEqual(format_value(70, "%"), "70%")
        self.assertEqual(format_value(99.95, "%"), "99.95%")
        self.assertEqual(format_value(13.50, "%"), "13.5%")
        self.assertEqual(format_value(1234567.891), "1,234,567.89")
        self.assertEqual(format_value(-2.0, "件"), "-2件")

    def test_board_report_structure(self):
        report = render_report("技術 KPI サマリー", "2026 年度 第 2 四半期", board_metrics())
        lines = report.splitlines()
        self.assertEqual(lines[0], "# 技術 KPI サマリー（2026 年度 第 2 四半期）")
        self.assertIn("**総合: 赤**（赤 2 / 黄 3 / 緑 4）", lines)
        self.assertTrue(report.endswith("\n") and not report.endswith("\n\n"))
        exc_start = lines.index("## 要対応・要注意（赤・黄）")
        all_start = lines.index("## 全指標")
        exception_rows = [l for l in lines[exc_start:all_start] if l.startswith("| 赤") or l.startswith("| 黄")]
        self.assertEqual(
            exception_rows,
            [
                "| 赤 | デリバリー | ロードマップ達成率 | 70% | 80% | 悪化（前期 78%） |",
                "| 赤 | 人と組織 | 採用計画の達成率 | 60% | 90% | 悪化（前期 70%） |",
                "| 黄 | デリバリー | 変更のリードタイム（中央値） | 30時間 | 24時間 | 改善（前期 36時間） |",
                "| 黄 | 信頼性 | 重大インシデント | 3件 | 2件 | 改善（前期 5件） |",
                "| 黄 | コスト | 売上に対するクラウド費用 | 13.5% | 12% | 悪化（前期 12.8%） |",
            ],
        )
        table = [l for l in lines[all_start:] if l.startswith("| ") and not l.startswith("| 区分")]
        self.assertEqual(len(table), 9)
        self.assertEqual(table[2], "| 信頼性 | 可用性（主要 API） | 緑 | 99.95% | 99.9% | 改善（前期 99.82%） |")

    def test_all_green_and_missing_previous(self):
        metrics = [Metric("可用性", 99.99, 99.9, unit="%", category="信頼性")]
        report = render_report("週次", "第 1 週", metrics)
        self.assertIn("**総合: 緑**（赤 0 / 黄 0 / 緑 1）", report)
        self.assertIn("赤・黄の指標はありません。", report)
        self.assertIn("| 信頼性 | 可用性 | 緑 | 99.99% | 99.9% | — |", report)

    def test_empty_metrics(self):
        with self.assertRaises(ValueError):
            render_report("x", "y", [])


if __name__ == "__main__":
    unittest.main()
