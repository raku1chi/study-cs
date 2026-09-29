"""9.3 ドメイン駆動設計とモジュール分割 — 演習3・4 のテスト（腐敗防止層）

実行: python3 tools/check.py 9.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from datetime import date, datetime, timedelta, timezone

from acl import (
    DEFAULT_MINUTES,
    ImportedReservation,
    LegacyReservationTranslator,
    LegacyTranslationError,
    parse_legacy_date,
    parse_legacy_time,
    parse_party,
    parse_phone,
    parse_yen,
)
from reservation_domain import InvalidValueError, Money, PartySize, ReservationStatus, TimeSlot

JST = timezone(timedelta(hours=9))

GOOD = {
    "YYK_NO": "000123",
    "TNP_CD": "S01",
    "TKB_CD": "T05",
    "YYK_YMD": "R080315",
    "YYK_JKN": "1830",
    "JKN_FUN": "090",
    "NINZU": "４",
    "KYK_NM": "ﾔﾏﾀﾞ　ﾀﾛｳ",
    "TEL_NO": "090-1234-5678",
    "STS_KBN": "1",
    "CRS_KNG": "5,500",
    "BIKO": "  窓際希望  ",
    "DEL_FLG": "0",
}


class TestExercise3Dates(unittest.TestCase):
    def test_seireki(self):
        self.assertEqual(parse_legacy_date("20260315"), date(2026, 3, 15))
        self.assertEqual(parse_legacy_date("2026/03/15"), date(2026, 3, 15))
        self.assertEqual(parse_legacy_date("2026-3-5"), date(2026, 3, 5))
        self.assertEqual(parse_legacy_date("20240229"), date(2024, 2, 29))
        self.assertEqual(parse_legacy_date("２０２６０３１５"), date(2026, 3, 15), "全角数字")

    def test_wareki(self):
        cases = {
            "R080315": date(2026, 3, 15),
            "r080315": date(2026, 3, 15),
            "R8.3.15": date(2026, 3, 15),
            "R08/03/15": date(2026, 3, 15),
            "Ｒ０８．０３．１５": date(2026, 3, 15),
            "令和8年3月15日": date(2026, 3, 15),
            "R01.05.01": date(2019, 5, 1),
            "R元.5.1": date(2019, 5, 1),
            "H31.04.30": date(2019, 4, 30),
            "H010108": date(1989, 1, 8),
            "平成7年1月17日": date(1995, 1, 17),
            "R060229": date(2024, 2, 29),
        }
        for text, expected in cases.items():
            self.assertEqual(parse_legacy_date(text), expected, text)

    def test_invalid_dates(self):
        invalid = {
            "H31.05.01": "平成は 2019-04-30 まで",
            "R01.04.30": "令和は 2019-05-01 から",
            "H010107": "平成は 1989-01-08 から",
            "R070229": "2025 年はうるう年ではない",
            "20230229": "2023 年はうるう年ではない",
            "R000101": "元号の年は 1 以上",
            "S640107": "昭和は扱わない",
            "2026315": "7 桁の西暦",
            "2026/13/01": "13 月",
            "": "空",
            "明日": "日付でない",
            "٢٠٢٦٠٣١٥": "ASCII 以外の数字（アラビア・インド数字）",
        }
        for text, why in invalid.items():
            with self.assertRaises(InvalidValueError, msg=f"{text!r}: {why}"):
                parse_legacy_date(text)


class TestExercise3OtherFields(unittest.TestCase):
    def test_time(self):
        self.assertEqual(parse_legacy_time("1830"), timedelta(hours=18, minutes=30))
        self.assertEqual(parse_legacy_time("18:30"), timedelta(hours=18, minutes=30))
        self.assertEqual(parse_legacy_time("０９００"), timedelta(hours=9))
        self.assertEqual(parse_legacy_time("2530"), timedelta(hours=25, minutes=30), "30 時間制")
        self.assertEqual(parse_legacy_time("2959"), timedelta(hours=29, minutes=59))
        for bad in ("3000", "1860", "930", "12", "ab:cd", "", "18-30", "١٨٣٠"):
            with self.assertRaises(InvalidValueError, msg=repr(bad)):
                parse_legacy_time(bad)

    def test_phone(self):
        self.assertEqual(parse_phone("090-1234-5678"), "09012345678")
        self.assertEqual(parse_phone("０９０（１２３４）５６７８"), "09012345678")
        self.assertEqual(parse_phone("03 1234 5678"), "0312345678")
        self.assertIsNone(parse_phone(""))
        self.assertIsNone(parse_phone("  "))
        for bad in ("12345", "90-1234-5678", "090-1234-56789", "tel:0312345678", "0٩٠١٢٣٤٥٦٧٨"):
            with self.assertRaises(InvalidValueError, msg=repr(bad)):
                parse_phone(bad)

    def test_yen(self):
        self.assertEqual(parse_yen("5,500"), Money(5500))
        self.assertEqual(parse_yen("５５００円"), Money(5500))
        self.assertEqual(parse_yen("0005500"), Money(5500))
        self.assertEqual(parse_yen(""), Money(0))
        for bad in ("-100", "5.5", "約5000", "٥٥٠٠"):
            with self.assertRaises(InvalidValueError, msg=repr(bad)):
                parse_yen(bad)

    def test_party(self):
        self.assertEqual(parse_party("４"), PartySize(4))
        self.assertEqual(parse_party(" 12 "), PartySize(12))
        for bad in ("0", "21", "四", "", "٣"):
            with self.assertRaises(InvalidValueError, msg=repr(bad)):
                parse_party(bad)


class TestExercise4Translator(unittest.TestCase):
    def setUp(self):
        self.t = LegacyReservationTranslator({("S01", "T05"): "tbl-shibuya-05", ("S02", "A1"): "tbl-ueno-a1"})

    def translate_with(self, **changes):
        record = dict(GOOD)
        for k, v in changes.items():
            if v is None:
                record.pop(k, None)
            else:
                record[k] = v
        return self.t.translate(record)

    def assert_field_errors(self, fields, **changes):
        with self.assertRaises(LegacyTranslationError) as cm:
            self.translate_with(**changes)
        self.assertEqual(sorted(e.field for e in cm.exception.errors), sorted(fields))
        return cm.exception

    def test_happy_path(self):
        got = self.t.translate(GOOD)
        self.assertEqual(got, ImportedReservation(
            legacy_id="000123",
            table_id="tbl-shibuya-05",
            slot=TimeSlot(datetime(2026, 3, 15, 18, 30, tzinfo=JST), 90),
            party=PartySize(4),
            status=ReservationStatus.BOOKED,
            customer_name="ヤマダ タロウ",
            phone="09012345678",
            course_price=Money(5500),
            note="窓際希望",
        ))

    def test_late_night_time_becomes_next_calendar_day(self):
        got = self.translate_with(YYK_JKN="2530")
        self.assertEqual(got.slot.start, datetime(2026, 3, 16, 1, 30, tzinfo=JST))

    def test_defaults_and_optional_fields(self):
        got = self.translate_with(JKN_FUN="", TEL_NO=None, CRS_KNG=None, BIKO=None, DEL_FLG=None)
        self.assertEqual(got.slot.minutes, DEFAULT_MINUTES)
        self.assertIsNone(got.phone)
        self.assertEqual(got.course_price, Money(0))
        self.assertEqual(got.note, "")
        self.assertEqual(self.translate_with(DEL_FLG=" ").legacy_id, "000123", "空欄の削除フラグは有効扱い")

    def test_status_mapping(self):
        expected = {"1": ReservationStatus.BOOKED, "2": ReservationStatus.SEATED,
                    "3": ReservationStatus.CANCELLED, "4": ReservationStatus.COMPLETED,
                    "9": ReservationStatus.NO_SHOW}
        for code, status in expected.items():
            self.assertEqual(self.translate_with(STS_KBN=code).status, status)
        self.assert_field_errors(["STS_KBN"], STS_KBN="7")

    def test_table_mapping(self):
        self.assertEqual(self.translate_with(TNP_CD="s02", TKB_CD="ａ１").table_id, "tbl-ueno-a1")
        self.assert_field_errors(["TKB_CD"], TKB_CD="T99")

    def test_deleted_record_is_skipped_even_if_broken(self):
        self.assertIsNone(self.translate_with(DEL_FLG="1", NINZU="?", YYK_YMD="??"))
        self.assert_field_errors(["DEL_FLG"], DEL_FLG="X")

    def test_unknown_fields_are_ignored(self):
        self.assertEqual(self.translate_with(UPD_USR="tanaka", UPD_YMD="R080301").legacy_id, "000123")

    def test_collects_all_errors(self):
        exc = self.assert_field_errors(
            ["NINZU", "STS_KBN", "TEL_NO", "YYK_YMD", "KYK_NM"],
            NINZU="０", YYK_YMD="H31.05.01", STS_KBN="7", TEL_NO="123", KYK_NM=None,
        )
        self.assertEqual(exc.record_no, "000123")
        message = str(exc)
        self.assertIn("000123", message)
        self.assertIn("NINZU", message)
        self.assertIn("人数", message, "人が読める項目の説明を含める")
        missing = [e for e in exc.errors if e.field == "KYK_NM"][0]
        self.assertIsNone(missing.value)

    def test_domain_rule_violations_are_reported_in_legacy_terms(self):
        # 旧システムは 18:10 のような時刻を許していたが、新しいドメインは 15 分単位しか認めない
        exc = self.assert_field_errors(["YYK_JKN"], YYK_JKN="1810")
        self.assertEqual(exc.errors[0].value, "1810")
        self.assert_field_errors(["JKN_FUN"], JKN_FUN="100")
        self.assert_field_errors(["JKN_FUN"], JKN_FUN="九十")
        self.assert_field_errors(["NINZU"], NINZU="25")

    def test_missing_required_fields(self):
        exc = self.assert_field_errors(["YYK_NO", "YYK_JKN"], YYK_NO=None, YYK_JKN="  ")
        self.assertIsNone(exc.record_no)
        self.assert_field_errors(["YYK_NO"], YYK_NO="A-123")

    def test_translate_all(self):
        records = [
            GOOD,
            dict(GOOD, YYK_NO="000124", DEL_FLG="1"),
            dict(GOOD, YYK_NO="000125", NINZU="0"),
            dict(GOOD, YYK_NO="000126", YYK_JKN="2000"),
        ]
        ok, failed = self.t.translate_all(records)
        self.assertEqual([r.legacy_id for r in ok], ["000123", "000126"])
        self.assertEqual([e.record_no for e in failed], ["000125"])


if __name__ == "__main__":
    unittest.main()
