"""14.5 ガバナンス・リスク・コンプライアンスと法務 — テスト（breach_notice.py）

【教育用・簡略化】法的助言ではありません。
実行: python3 tools/check.py 14.5   （またはこのディレクトリで python3 -m unittest -v test_breach_notice）
"""
import unittest
from datetime import date, datetime, timedelta, timezone

from breach_notice import (
    JST,
    Incident,
    appi_final_report_due,
    appi_triggers,
    assess,
    gdpr_obligations,
    is_closed_day,
)

AWARE = datetime(2026, 4, 1, 10, 0, tzinfo=JST)
GOLDEN_WEEK_2026 = {date(2026, 4, 29), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5), date(2026, 5, 6)}


class TestAppiTriggers(unittest.TestCase):
    def test_threshold_is_more_than_1000(self):
        self.assertEqual(appi_triggers(Incident(AWARE, 1000)), [])
        self.assertEqual(appi_triggers(Incident(AWARE, 1001)), ["1,000人超"])

    def test_each_category_triggers_even_for_one_person(self):
        self.assertEqual(appi_triggers(Incident(AWARE, 1, sensitive=True)), ["要配慮個人情報"])
        self.assertEqual(appi_triggers(Incident(AWARE, 1, financial_risk=True)), ["財産的被害のおそれ"])
        self.assertEqual(appi_triggers(Incident(AWARE, 1, malicious=True)), ["不正の目的によるおそれ"])

    def test_order_of_labels(self):
        inc = Incident(AWARE, 5000, sensitive=True, financial_risk=True, malicious=True)
        self.assertEqual(
            appi_triggers(inc),
            ["要配慮個人情報", "財産的被害のおそれ", "不正の目的によるおそれ", "1,000人超"],
        )

    def test_exclusions(self):
        self.assertEqual(appi_triggers(Incident(AWARE, 5000, malicious=True, high_grade_encryption=True)), [])
        self.assertEqual(appi_triggers(Incident(AWARE, 5000, sensitive=True, appi_applies=False)), [])

    def test_validation(self):
        with self.assertRaises(ValueError):
            appi_triggers(Incident(datetime(2026, 4, 1, 10, 0), 10))  # タイムゾーンなし
        with self.assertRaises(ValueError):
            appi_triggers(Incident(AWARE, -1))
        with self.assertRaises(ValueError):
            appi_triggers(Incident(AWARE, 10, gdpr_role="owner"))
        with self.assertRaises(ValueError):
            appi_triggers(Incident(AWARE, 10, gdpr_risk="medium"))


class TestDeadlines(unittest.TestCase):
    def test_closed_days(self):
        self.assertTrue(is_closed_day(date(2026, 5, 30)))    # 土曜
        self.assertTrue(is_closed_day(date(2026, 5, 31)))    # 日曜
        self.assertFalse(is_closed_day(date(2026, 6, 1)))    # 月曜
        self.assertTrue(is_closed_day(date(2025, 12, 29)))   # 年末
        self.assertTrue(is_closed_day(date(2026, 1, 3)))     # 年始
        self.assertFalse(is_closed_day(date(2025, 12, 26)))  # 金曜
        self.assertTrue(is_closed_day(date(2026, 5, 4), GOLDEN_WEEK_2026))
        self.assertFalse(is_closed_day(date(2026, 5, 4)))    # holidays を渡さなければ平日

    def test_day_one_is_the_aware_date(self):
        self.assertEqual(appi_final_report_due(date(2026, 4, 1), False), date(2026, 4, 30))
        self.assertEqual(appi_final_report_due(date(2026, 4, 1), True), date(2026, 6, 1))

    def test_rolls_over_weekends_holidays_and_year_end(self):
        # 30 日目が 5/4（祝日）→ 5/5、5/6 も休み → 5/7
        self.assertEqual(appi_final_report_due(date(2026, 4, 5), False, GOLDEN_WEEK_2026), date(2026, 5, 7))
        # 30 日目が 12/30 → 年末年始（〜1/3）→ 1/4 は日曜 → 1/5
        self.assertEqual(appi_final_report_due(date(2025, 12, 1), False), date(2026, 1, 5))
        # 60 日目が 5/3（日曜・祝日）→ 5/7
        self.assertEqual(appi_final_report_due(date(2026, 3, 5), True, GOLDEN_WEEK_2026), date(2026, 5, 7))


class TestGdpr(unittest.TestCase):
    def test_not_applicable(self):
        self.assertEqual(gdpr_obligations(Incident(AWARE, 10)), [])

    def test_controller_with_risk(self):
        obs = gdpr_obligations(Incident(AWARE, 10, eu_data_subjects=True, gdpr_risk="risk"))
        self.assertEqual([o.action for o in obs], ["侵害を記録する", "監督機関へ通知"])
        self.assertEqual(obs[1].due, AWARE + timedelta(hours=72))
        self.assertIsNone(obs[0].due)
        self.assertTrue(all(o.regime == "GDPR" for o in obs))

    def test_controller_high_risk_and_encryption(self):
        high = gdpr_obligations(Incident(AWARE, 10, eu_data_subjects=True, gdpr_risk="high"))
        self.assertEqual([o.action for o in high], ["侵害を記録する", "監督機関へ通知", "本人へ通知"])
        encrypted = gdpr_obligations(
            Incident(AWARE, 10, eu_data_subjects=True, gdpr_risk="high", high_grade_encryption=True)
        )
        self.assertEqual([o.action for o in encrypted], ["侵害を記録する", "監督機関へ通知"])

    def test_controller_unlikely_risk_only_records(self):
        obs = gdpr_obligations(Incident(AWARE, 10, eu_data_subjects=True, gdpr_risk="unlikely"))
        self.assertEqual([o.action for o in obs], ["侵害を記録する"])

    def test_processor_notifies_controller(self):
        obs = gdpr_obligations(Incident(AWARE, 10, eu_data_subjects=True, gdpr_role="processor", gdpr_risk="high"))
        self.assertEqual([(o.regime, o.action, o.due) for o in obs], [("GDPR", "管理者（controller）へ通知", None)])

    def test_72_hours_is_absolute_time(self):
        utc = datetime(2026, 4, 1, 1, 0, tzinfo=timezone.utc)
        obs = gdpr_obligations(Incident(utc, 10, eu_data_subjects=True))
        self.assertEqual(obs[1].due, datetime(2026, 4, 4, 1, 0, tzinfo=timezone.utc))


class TestAssess(unittest.TestCase):
    def test_book_example(self):
        inc = Incident(datetime(2026, 3, 5, 18, 30, tzinfo=JST), 2300, malicious=True,
                       eu_data_subjects=True, gdpr_risk="high")
        obs = assess(inc, holidays=GOLDEN_WEEK_2026)
        self.assertEqual(
            [(o.regime, o.action) for o in obs],
            [
                ("APPI", "個人情報保護委員会へ速報"),
                ("APPI", "個人情報保護委員会へ確報"),
                ("APPI", "本人へ通知"),
                ("GDPR", "侵害を記録する"),
                ("GDPR", "監督機関へ通知"),
                ("GDPR", "本人へ通知"),
            ],
        )
        self.assertEqual(obs[0].due, datetime(2026, 3, 10, 18, 30, tzinfo=JST))
        self.assertIn("不正の目的によるおそれ", obs[0].note)
        self.assertIn("1,000人超", obs[0].note)
        self.assertEqual(obs[1].due, datetime(2026, 5, 7, 23, 59, 59, tzinfo=JST))
        self.assertEqual(obs[1].due.utcoffset(), timedelta(hours=9))
        self.assertIsNone(obs[2].due)
        self.assertEqual(obs[4].due, datetime(2026, 3, 8, 18, 30, tzinfo=JST))

    def test_utc_input_uses_japanese_date(self):
        # 2026-03-31 16:00 UTC は日本時間では 4 月 1 日 1:00。確報の起算日は 4 月 1 日
        utc = datetime(2026, 3, 31, 16, 0, tzinfo=timezone.utc)
        obs = assess(Incident(utc, 1, sensitive=True))
        self.assertEqual(obs[1].due.date(), date(2026, 4, 30))
        self.assertEqual(obs[0].due, datetime(2026, 4, 6, 1, 0, tzinfo=JST))

    def test_nothing_to_report(self):
        self.assertEqual(assess(Incident(AWARE, 50)), [])
        self.assertEqual(assess(Incident(AWARE, 50_000, high_grade_encryption=True)), [])

    def test_gdpr_only(self):
        obs = assess(Incident(AWARE, 10, appi_applies=False, eu_data_subjects=True))
        self.assertEqual([o.regime for o in obs], ["GDPR", "GDPR"])


if __name__ == "__main__":
    unittest.main()
