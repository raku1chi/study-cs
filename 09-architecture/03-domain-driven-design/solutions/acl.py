"""9.3 ドメイン駆動設計とモジュール分割 — 解答例: 腐敗防止層（ACL）

演習の仕様は exercises/acl.py の docstring を参照してください。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Iterable, Mapping

from reservation_domain import InvalidValueError, Money, PartySize, ReservationStatus, TimeSlot

JST = timezone(timedelta(hours=9), "JST")

LEGACY_FIELDS = {
    "YYK_NO": "予約番号",
    "TNP_CD": "店舗コード",
    "TKB_CD": "卓番",
    "YYK_YMD": "予約日",
    "YYK_JKN": "予約時刻",
    "JKN_FUN": "所要時間（分）",
    "NINZU": "人数",
    "KYK_NM": "顧客名",
    "TEL_NO": "電話番号",
    "STS_KBN": "状態区分",
    "CRS_KNG": "コース金額（1 名あたり）",
    "BIKO": "備考",
    "DEL_FLG": "削除フラグ",
}

STATUS_CODES = {
    "1": ReservationStatus.BOOKED,
    "2": ReservationStatus.SEATED,
    "3": ReservationStatus.CANCELLED,
    "4": ReservationStatus.COMPLETED,
    "9": ReservationStatus.NO_SHOW,
}

DEFAULT_MINUTES = 120  # 旧システムでは所要時間が空欄なら 2 時間とみなしていた


@dataclass(frozen=True)
class FieldError:
    field: str
    value: str | None
    message: str


class LegacyTranslationError(Exception):
    def __init__(self, record_no: str | None, errors: list[FieldError]) -> None:
        self.record_no = record_no
        self.errors = list(errors)
        lines = [f"旧システムの予約 {record_no or '(番号不明)'} を変換できません（{len(self.errors)} 件）"]
        for e in self.errors:
            label = LEGACY_FIELDS.get(e.field, e.field)
            lines.append(f"  - {e.field}（{label}）: {e.message}（値: {e.value!r}）")
        super().__init__("\n".join(lines))


@dataclass(frozen=True)
class ImportedReservation:
    legacy_id: str
    table_id: str
    slot: TimeSlot
    party: PartySize
    status: ReservationStatus
    customer_name: str
    phone: str | None
    course_price: Money
    note: str


# ---------------------------------------------------------------------------
# 演習3: 項目ごとの変換関数
# ---------------------------------------------------------------------------

def normalize_text(text: str) -> str:
    # NFKC: 全角英数字→半角、半角カナ→全角、全角スペース→半角スペース（1.1 の Unicode 正規化）
    return " ".join(unicodedata.normalize("NFKC", text).split())


# 数字は [0-9] で書く。\d は「٣」のような他の文字体系の数字にも一致し、int() もそれを受け付けてしまう
_COMPACT_WAREKI = re.compile(r"^([RH])([0-9]{2})([0-9]{2})([0-9]{2})$")
_SEPARATED_WAREKI = re.compile(r"^(R|H|令和|平成)(元|[0-9]{1,2})[./年-]([0-9]{1,2})[./月-]([0-9]{1,2})日?$")
_COMPACT_SEIREKI = re.compile(r"^([0-9]{4})([0-9]{2})([0-9]{2})$")
_SEPARATED_SEIREKI = re.compile(r"^([0-9]{4})[/-]([0-9]{1,2})[/-]([0-9]{1,2})$")

# 元号: (西暦年 = 元号の年 + offset, 開始日, 終了日)
_ERAS = {
    "R": (2018, date(2019, 5, 1), None),
    "H": (1988, date(1989, 1, 8), date(2019, 4, 30)),
}
_ERA_ALIASES = {"令和": "R", "平成": "H"}


def parse_legacy_date(text: str) -> date:
    s = normalize_text(text).upper()
    m = _COMPACT_WAREKI.match(s) or _SEPARATED_WAREKI.match(s)
    if m:
        era = _ERA_ALIASES.get(m.group(1), m.group(1))
        era_year = 1 if m.group(2) == "元" else int(m.group(2))
        if era_year < 1:
            raise InvalidValueError(f"元号の年は 1 以上です: {text!r}")
        offset, first, last = _ERAS[era]
        d = _make_date(era_year + offset, int(m.group(3)), int(m.group(4)), text)
        if d < first or (last is not None and d > last):
            raise InvalidValueError(f"{text!r} はその元号の期間外です")
        return d
    m = _COMPACT_SEIREKI.match(s) or _SEPARATED_SEIREKI.match(s)
    if m:
        return _make_date(int(m.group(1)), int(m.group(2)), int(m.group(3)), text)
    raise InvalidValueError(f"日付の形式が不正です: {text!r}")


def _make_date(y: int, m: int, d: int, original: str) -> date:
    try:
        return date(y, m, d)
    except ValueError:
        raise InvalidValueError(f"存在しない日付です: {original!r}") from None


_TIME = re.compile(r"^([0-9]{2}):?([0-9]{2})$")


def parse_legacy_time(text: str) -> timedelta:
    m = _TIME.match(normalize_text(text))
    if not m:
        raise InvalidValueError(f"時刻の形式が不正です（HHMM または HH:MM）: {text!r}")
    hours, minutes = int(m.group(1)), int(m.group(2))
    # 飲食店などでは、営業日の深夜を「25:30」のように 24 時以降で表す習慣がある（30 時間制）
    if hours > 29 or minutes > 59:
        raise InvalidValueError(f"時刻の範囲外です（00:00〜29:59）: {text!r}")
    return timedelta(hours=hours, minutes=minutes)


_PHONE = re.compile(r"^0[0-9]{9,10}$")
_ASCII_DIGITS = re.compile(r"^[0-9]+$")  # str.isdigit() は「٣」などの他の文字体系の数字も True にするので使わない


def parse_phone(text: str) -> str | None:
    digits = re.sub(r"[-\s()]", "", normalize_text(text))
    if not digits:
        return None
    if not _PHONE.match(digits):
        raise InvalidValueError(f"電話番号の形式が不正です: {text!r}")
    return digits


def parse_yen(text: str) -> Money:
    s = normalize_text(text).replace(",", "").removesuffix("円").strip()
    if not s:
        return Money(0)
    if not _ASCII_DIGITS.match(s):
        raise InvalidValueError(f"金額の形式が不正です: {text!r}")
    return Money(int(s))


def parse_party(text: str) -> PartySize:
    s = normalize_text(text)
    if not _ASCII_DIGITS.match(s):
        raise InvalidValueError(f"人数は数字で指定してください: {text!r}")
    return PartySize(int(s))  # 1〜20 の範囲はドメインの値オブジェクトが検査する


# ---------------------------------------------------------------------------
# 演習4: レコード全体の変換
# ---------------------------------------------------------------------------

class LegacyReservationTranslator:
    def __init__(self, table_map: Mapping[tuple[str, str], str], tz: tzinfo = JST) -> None:
        self._table_map = dict(table_map)
        self._tz = tz

    def translate(self, record: Mapping[str, str]) -> ImportedReservation | None:
        errors: list[FieldError] = []

        def required(name: str) -> str | None:
            value = record.get(name)
            if value is None or not normalize_text(value):
                errors.append(FieldError(name, value, "必須項目がありません"))
                return None
            return value

        def convert(name: str, func, value):
            # 変換関数やドメインの値オブジェクトが出したエラーを、旧システムの項目名で報告し直す
            if value is None:
                return None
            try:
                return func(value)
            except InvalidValueError as exc:
                errors.append(FieldError(name, value, str(exc)))
                return None

        # 削除済みのレコードは、ほかの項目が壊れていても検査せずに読み飛ばす
        del_flag = normalize_text(record.get("DEL_FLG") or "") or "0"  # 空欄は 0（有効）とみなす
        if del_flag == "1":
            return None
        if del_flag != "0":
            errors.append(FieldError("DEL_FLG", record.get("DEL_FLG"), "削除フラグは 0 か 1 です"))

        legacy_id = None
        record_no = required("YYK_NO")
        if record_no is not None:
            legacy_id = normalize_text(record_no)
            if not _ASCII_DIGITS.match(legacy_id):
                errors.append(FieldError("YYK_NO", record_no, "予約番号は数字です"))

        # 識別子の対応づけ: 旧システムの（店舗コード, 卓番）→ 新システムのテーブル ID
        table_id = None
        store, table_code = required("TNP_CD"), required("TKB_CD")
        if store is not None and table_code is not None:
            key = (normalize_text(store).upper(), normalize_text(table_code).upper())
            table_id = self._table_map.get(key)
            if table_id is None:
                errors.append(FieldError("TKB_CD", table_code,
                                         f"新システムに対応するテーブルがありません（店舗 {key[0]}）"))

        day = convert("YYK_YMD", parse_legacy_date, required("YYK_YMD"))
        offset = convert("YYK_JKN", parse_legacy_time, required("YYK_JKN"))

        minutes: int | None = DEFAULT_MINUTES
        minutes_raw = record.get("JKN_FUN")
        if minutes_raw is not None and normalize_text(minutes_raw):
            s = normalize_text(minutes_raw)
            minutes = int(s) if _ASCII_DIGITS.match(s) else None
            if minutes is None:
                errors.append(FieldError("JKN_FUN", minutes_raw, "所要時間は分単位の数字です"))

        slot = None
        if day is not None and offset is not None and minutes is not None:
            # 30 時間制の「25:30」は、翌日の 1:30 という本当の日時に変換される
            start = datetime.combine(day, time(0), tzinfo=self._tz) + offset
            try:
                slot = TimeSlot(start, minutes)
            except InvalidValueError as exc:
                # 新しいドメインの規則（15 分単位など）に合わないデータを、どの旧項目の問題かで報告する
                name = "YYK_JKN" if start.minute % 15 else "JKN_FUN"
                errors.append(FieldError(name, record.get(name), str(exc)))

        party = convert("NINZU", parse_party, required("NINZU"))

        status = None
        code = required("STS_KBN")
        if code is not None:
            status = STATUS_CODES.get(normalize_text(code))
            if status is None:
                errors.append(FieldError("STS_KBN", code, f"未知の状態区分です（有効: {', '.join(STATUS_CODES)}）"))

        name = required("KYK_NM")
        customer_name = normalize_text(name) if name is not None else None
        phone = convert("TEL_NO", parse_phone, record.get("TEL_NO") or "")
        price = convert("CRS_KNG", parse_yen, record.get("CRS_KNG") or "")
        note = normalize_text(record.get("BIKO") or "")

        if errors:
            raise LegacyTranslationError(legacy_id, errors)
        return ImportedReservation(
            legacy_id=legacy_id,
            table_id=table_id,
            slot=slot,
            party=party,
            status=status,
            customer_name=customer_name,
            phone=phone,
            course_price=price,
            note=note,
        )

    def translate_all(
        self, records: Iterable[Mapping[str, str]]
    ) -> tuple[list[ImportedReservation], list[LegacyTranslationError]]:
        imported: list[ImportedReservation] = []
        failed: list[LegacyTranslationError] = []
        for record in records:
            try:
                result = self.translate(record)
            except LegacyTranslationError as exc:
                failed.append(exc)
                continue
            if result is not None:
                imported.append(result)
        return imported, failed
