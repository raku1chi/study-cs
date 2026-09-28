"""9.3 ドメイン駆動設計とモジュール分割 — 演習: 腐敗防止層（ACL, anticorruption layer）

一部の店舗は、20 年前に作られた予約台帳システムを使い続けています。夜間に受け取るそのデータは、
暗号のような項目名、区分コード、和暦や 30 時間制の時刻、全角・半角の混在した文字列でできています。
これをそのまま新しいドメインに流し込むと、旧システムの都合（言葉・コード・形式）が新しいモデルを
「腐敗」させます。腐敗防止層は、2 つのモデルの間で翻訳だけを担当する境界です。

    演習3（★★☆）: 項目ごとの変換関数 parse_legacy_date / parse_legacy_time / parse_phone / parse_yen / parse_party
    演習4（★★☆）: レコード全体の変換 LegacyReservationTranslator.translate / translate_all

旧システムのレコード（1 件 = 文字列の辞書）の例:

    {
        "YYK_NO": "000123",        # 予約番号（数字の文字列。先頭の 0 も識別子の一部として残す）
        "TNP_CD": "S01",           # 店舗コード
        "TKB_CD": "T05",           # 卓番（テーブルのコード）
        "YYK_YMD": "R080315",      # 予約日（西暦 "20260315" / "2026/03/15"、和暦 "R080315" / "R8.3.15" など）
        "YYK_JKN": "1830",         # 予約時刻（"1830" / "18:30"。深夜は "2530" のような 30 時間制）
        "JKN_FUN": "090",          # 所要時間（分）。空欄なら 120 分（旧システムの仕様）
        "NINZU": "４",             # 人数（全角数字のことがある）
        "KYK_NM": "ﾔﾏﾀﾞ ﾀﾛｳ",       # 顧客名（半角カナのことがある）
        "TEL_NO": "090-1234-5678", # 電話番号（任意）
        "STS_KBN": "1",            # 状態区分: 1=予約 2=来店 3=取消 4=退店済 9=無断キャンセル
        "CRS_KNG": "5,500",        # コース金額（1 名あたり、円。空欄なら 0 円）
        "BIKO": "  窓際希望  ",     # 備考（任意）
        "DEL_FLG": "0",            # 削除フラグ: 0=有効 1=削除済み（空欄は 0 とみなす）
    }

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.3

ヒント: 文字列はまず normalize_text（NFKC 正規化と空白の整理。1.1 章を参照）に通すと、
全角数字・半角カナ・全角スペースの問題の多くが片付きます。
"""
from __future__ import annotations

import re  # noqa: F401  演習3で使えます
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo  # noqa: F401
from typing import Iterable, Mapping

from reservation_domain import InvalidValueError, Money, PartySize, ReservationStatus, TimeSlot  # noqa: F401

JST = timezone(timedelta(hours=9), "JST")

# 旧システムの項目名と意味（エラーメッセージで人が読めるようにするため）
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

# 旧システムの状態区分 → 新しいドメインの状態
STATUS_CODES = {
    "1": ReservationStatus.BOOKED,
    "2": ReservationStatus.SEATED,
    "3": ReservationStatus.CANCELLED,
    "4": ReservationStatus.COMPLETED,
    "9": ReservationStatus.NO_SHOW,
}

DEFAULT_MINUTES = 120  # 旧システムでは所要時間が空欄なら 2 時間とみなしていた


# ---------------------------------------------------------------------------
# 実装済み: エラーと変換結果の型、文字列の正規化
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldError:
    """変換できなかった項目 1 つ。field は旧システムの項目名、value は元の値（なければ None）。"""

    field: str
    value: str | None
    message: str


class LegacyTranslationError(Exception):
    """1 件のレコードの変換エラー。見つかったすべての項目のエラーを errors に持つ。"""

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
    """新しいドメインの言葉に翻訳された予約（旧システムの項目名やコードは一切含まない）。"""

    legacy_id: str
    table_id: str
    slot: TimeSlot
    party: PartySize
    status: ReservationStatus
    customer_name: str
    phone: str | None
    course_price: Money
    note: str


def normalize_text(text: str) -> str:
    """NFKC 正規化し、連続する空白を 1 つの半角スペースにまとめ、前後の空白を除く。

    >>> normalize_text("  ﾔﾏﾀﾞ　ﾀﾛｳ ")
    'ヤマダ タロウ'
    >>> normalize_text("Ｒ０８．０３．１５")
    'R08.03.15'
    """
    return " ".join(unicodedata.normalize("NFKC", text).split())


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 項目ごとの変換関数
# いずれも normalize_text を通してから解釈し、不正なら InvalidValueError を送出する。
# 数字は ASCII の 0〜9 だけを数字として扱うこと（str.isdigit() は他の文字体系の数字も True にする）。
# ---------------------------------------------------------------------------

def parse_legacy_date(text: str) -> date:
    """旧システムの日付文字列を date にする。

    受け付ける形式（英字は大文字・小文字を区別しない）:
    - 西暦: "20260315"（8 桁）、"2026/03/15"、"2026-3-5"（区切りがあれば月日は 1〜2 桁）
    - 和暦: "R080315"（元号 1 文字 + 年月日 2 桁ずつ）、"R8.3.15"、"R08/03/15"、"R8-3-15"、
            "令和8年3月15日"、"R元.5.1"（元年）。元号は R（令和）と H（平成）だけ
    - 令和 n 年 = 西暦 2018 + n 年（2019-05-01 以降のみ有効）
    - 平成 n 年 = 西暦 1988 + n 年（1989-01-08 〜 2019-04-30 のみ有効）

    >>> parse_legacy_date("R080315")
    datetime.date(2026, 3, 15)
    >>> parse_legacy_date("H31.04.30")
    datetime.date(2019, 4, 30)

    不正（形式違い、存在しない日付、元号の期間外、元号の年が 0）なら InvalidValueError。
    例: "H31.05.01"（平成は 4 月 30 日まで）、"R01.04.30"（令和は 5 月 1 日から）、"20230229"。

    ヒント: 正規表現を「区切りなし」と「区切りあり」の 2 本に分けると書きやすい。
    """
    raise NotImplementedError("演習3: parse_legacy_date を実装してください")


def parse_legacy_time(text: str) -> timedelta:
    """"1830" や "18:30" を、その日の 0 時からの経過時間（timedelta）にする。

    時は 00〜29（飲食店などで使われる 30 時間制。"2530" は翌日の 1:30 を表す）、分は 00〜59。
    時・分はそれぞれ 2 桁。範囲外や形式違いは InvalidValueError。

    >>> parse_legacy_time("2530")        # 25 時間 30 分 = 1 日と 1 時間 30 分
    datetime.timedelta(days=1, seconds=5400)
    """
    raise NotImplementedError("演習3: parse_legacy_time を実装してください")


def parse_phone(text: str) -> str | None:
    """電話番号を数字だけの文字列にする（ハイフン・空白・括弧を除く）。空なら None。

    除いた結果が「0 で始まる 10〜11 桁の数字」でなければ InvalidValueError。
    >>> parse_phone("０９０（１２３４）５６７８")
    '09012345678'
    """
    raise NotImplementedError("演習3: parse_phone を実装してください")


def parse_yen(text: str) -> Money:
    """"5,500" や "5500円" を Money にする（カンマと末尾の「円」を除く）。空なら Money(0)。

    数字以外が残れば InvalidValueError。
    """
    raise NotImplementedError("演習3: parse_yen を実装してください")


def parse_party(text: str) -> PartySize:
    """人数の文字列を PartySize にする。数字でなければ InvalidValueError。

    1〜20 の範囲の検査は、ドメインの値オブジェクト（PartySize）に任せること
    （業務ルールを腐敗防止層に重複して書かない）。
    """
    raise NotImplementedError("演習3: parse_party を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: レコード全体の変換
# ---------------------------------------------------------------------------

class LegacyReservationTranslator:
    """旧システムのレコードを ImportedReservation に翻訳する。

    table_map: (店舗コード, 卓番) → 新システムのテーブル ID。コードは大文字に正規化して引く。
    tz: 旧システムの日時が表すタイムゾーン（既定は日本時間）。
    """

    def __init__(self, table_map: Mapping[tuple[str, str], str], tz: tzinfo = JST) -> None:
        self._table_map = dict(table_map)
        self._tz = tz

    def translate(self, record: Mapping[str, str]) -> ImportedReservation | None:
        """1 件のレコードを翻訳する。

        規則:
        - DEL_FLG が "1" なら、ほかの項目を検査せずに None を返す（削除済みは取り込まない）。
          DEL_FLG が "0"・空欄・項目なし以外の値なら、エラーとして記録する。
        - 必須項目: YYK_NO, TNP_CD, TKB_CD, YYK_YMD, YYK_JKN, NINZU, STS_KBN, KYK_NM。
          項目がない、または空白だけなら FieldError(項目名, 元の値, "必須項目がありません")。
        - YYK_NO は数字（正規化した文字列をそのまま legacy_id にする。先頭の 0 も残す）。
        - (TNP_CD, TKB_CD) を table_map で新しいテーブル ID に対応づける。なければ TKB_CD のエラー。
        - 予約日 + 予約時刻（30 時間制）を tz 付きの datetime にし、所要時間（空欄なら DEFAULT_MINUTES）
          とあわせて TimeSlot を作る。TimeSlot が拒否したら（15 分単位でない等）、原因の項目
          （開始の分が 15 分単位でなければ YYK_JKN、そうでなければ JKN_FUN）のエラーとして記録する。
        - STS_KBN は STATUS_CODES で変換。未知のコードはエラー。
        - 顧客名・備考は normalize_text する。TEL_NO と CRS_KNG は任意（空・なしも可）。
        - 知らない項目（旧システムが後から追加した列など）は無視する（寛容な読み手）。
        - **エラーは最初の 1 つで止めず、すべて集めて** LegacyTranslationError(legacy_id, errors) を送出する
          （移行作業では、1 件ごとに全部の問題が分かる方が修正しやすい）。
        """
        raise NotImplementedError("演習4: LegacyReservationTranslator.translate を実装してください")

    def translate_all(
        self, records: Iterable[Mapping[str, str]]
    ) -> tuple[list[ImportedReservation], list[LegacyTranslationError]]:
        """複数のレコードを翻訳し、(成功したもの, 失敗したもののエラー) を返す。削除済みはどちらにも入れない。"""
        raise NotImplementedError("演習4: LegacyReservationTranslator.translate_all を実装してください")
