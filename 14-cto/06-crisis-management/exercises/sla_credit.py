"""14.6 危機管理 — 演習: SLAクレジットの計算

大規模障害の後、CTO は「契約上いくら返金（クレジット）が発生するか」を、財務・営業・
法務と一緒に速く正確に確定させる必要があります。顧客への説明、売上の修正、
取締役会への報告は、すべてこの数字に依存します。この演習では、障害の時間帯
（ウィンドウ）の記録から月間稼働率を求め、契約プランごとのクレジット額を計算します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.6          # 合格数を表示
    python3 tools/check.py -v 14.6       # 各テストの結果を詳しく表示

この演習の「サンプル約款」（教材用に簡略化したもの。実際の契約の定義は契約ごとに確認すること）:
    - 月間稼働率(%) = (請求期間の長さ − ダウンタイム) ÷ 請求期間の長さ × 100
    - ダウンタイム = 障害ウィンドウを重複なく合計したもの。ただし、事前に告知した計画
      メンテナンスの時間帯と重なる部分は除く。
    - 請求期間 = 契約のタイムゾーンでの暦月（当月 1 日 0:00 から翌月 1 日 0:00 まで）。
    - クレジット率 = プランごとの段階表で決まる。「稼働率がしきい値を下回ったら」適用し、
      境界ちょうど（例: 99.9% ちょうど）は下回っていないとみなす。
    - クレジット額 = 月額料金 × クレジット率（プランの上限率を超えない）。1 円未満は切り捨て。

制約（学びのための縛り）:
    - 稼働率とその比較に float を使わないこと。fractions.Fraction で厳密に計算する。
      float では 99.9 / 100 が 0.9990000000000001 になり、境界ちょうどの月に
      「SLA 違反」と誤判定することがある（本文 6.3 節を参照）。
    - timedelta.total_seconds() は float を返す。厳密に扱うなら
      `td // timedelta(microseconds=1)` でマイクロ秒単位の整数にする。
    - すべての datetime はタイムゾーン付き（aware）であること。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo  # noqa: F401  timezone は UTC 変換に使えます
from decimal import Decimal
from fractions import Fraction
from typing import Iterable, Mapping, Sequence, Union

# 障害や計画メンテナンスの時間帯。[開始, 終了) の半開区間（開始を含み、終了を含まない）
Window = tuple[datetime, datetime]
# 厳密な数値として受け付ける型（float は受け付けない）
Exact = Union[int, Fraction, Decimal, str]


@dataclass(frozen=True)
class Plan:
    """契約プラン。

    tiers: (しきい値, クレジット率%) の並び。しきい値は "99.9" のような文字列で書く。
           例: (("99.95", 10), ("99.9", 25), ("99.0", 50), ("95.0", 100))
    cap_percent: クレジット率の上限（%）。
    """

    name: str
    tiers: tuple[tuple[str, int], ...]
    cap_percent: int = 100


@dataclass(frozen=True)
class Contract:
    """顧客の契約。monthly_fee は月額料金（円、整数）。"""

    customer_id: str
    plan: str
    monthly_fee: int


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 区間の統合
# ---------------------------------------------------------------------------

def merge_windows(windows: Iterable[Window]) -> list[Window]:
    """重なる、または接している区間を 1 つにまとめ、開始時刻の昇順で返す。

    - 各区間は [start, end) の半開区間。end と次の start が等しければ連続とみなしてまとめる。
    - 返す区間の datetime は UTC（timezone.utc）にそろえる。
    - タイムゾーンのない（naive）datetime が含まれていたら ValueError。
      （日本時間の記録と UTC の記録が混ざっても、aware なら正しく比較できる）
    - start >= end の区間は ValueError。
    - 入力のリストは変更しない。空の入力には空のリストを返す。

    例（JST = timezone(timedelta(hours=9))）:
        10:00〜10:30 と 10:20〜11:00 → 10:00〜11:00 の 1 区間
        10:00〜11:00 と 11:00〜12:00 → 10:00〜12:00 の 1 区間

    ヒント: 開始時刻でソートすると、「直前にまとめた区間と重なるか」だけを
    調べればよくなる。
    """
    raise NotImplementedError("演習1: merge_windows を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 請求期間とダウンタイム
# ---------------------------------------------------------------------------

def billing_period(year: int, month: int, tz: tzinfo) -> Window:
    """契約のタイムゾーン tz での暦月 [当月 1 日 0:00, 翌月 1 日 0:00) を返す。

    - month が 1〜12 以外なら ValueError。
    - 12 月の終わりは翌年 1 月 1 日 0:00。

    >>> start, end = billing_period(2026, 6, timezone(timedelta(hours=9)))
    >>> end - start
    datetime.timedelta(days=30)
    """
    raise NotImplementedError("演習2: billing_period を実装してください")


def downtime_in_period(
    outages: Iterable[Window],
    period: Window,
    maintenance: Iterable[Window] = (),
) -> timedelta:
    """請求期間 period の中のダウンタイムを返す。

    1. 障害ウィンドウの重複をなくす（同じ時間を二重に数えない）。
    2. 請求期間の外にはみ出した部分を切り落とす（月をまたぐ障害に注意）。
    3. 計画メンテナンスのウィンドウと重なる部分を差し引く（メンテナンス同士が
       重なっていても、二重に差し引かない）。

    例: 6/10 14:00〜14:30 と 14:20〜15:10 の障害（合計 70 分）に、15:00〜16:00 の
    計画メンテナンスが重なる → この部分のダウンタイムは 60 分。

    ヒント: 期間の長さなどの引き算は、UTC に変換してから行う。同じ tzinfo を持つ
    aware datetime 同士の引き算は「壁時計の差」になり、夏時間の切り替えを無視する。
    """
    raise NotImplementedError("演習2: downtime_in_period を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: 稼働率とクレジット率
# ---------------------------------------------------------------------------

def availability_percent(downtime: timedelta, period: Window) -> Fraction:
    """月間稼働率（%）を Fraction で返す。

    - 期間の長さは実際の経過時間（UTC に変換して計算）。
    - downtime が負、または期間の長さを超えるなら ValueError。

    >>> JST = timezone(timedelta(hours=9))
    >>> availability_percent(timedelta(minutes=43, seconds=12), billing_period(2026, 6, JST))
    Fraction(999, 10)
    """
    raise NotImplementedError("演習3: availability_percent を実装してください")


def credit_percent(availability: Exact, tiers: Sequence[tuple[Exact, int]]) -> int:
    """段階表 tiers から、稼働率 availability に対するクレジット率（%）を返す。

    - tiers は (しきい値, クレジット率) の並び。順序は問わない。
    - 「availability < しきい値」を満たす段階のうち、最大のクレジット率を返す。
      どれにも該当しなければ 0。境界ちょうどは該当しない。
    - availability としきい値は int・Fraction・Decimal・文字列（"99.9" など）で受け付け、
      Fraction に変換して比較する。float が渡されたら TypeError。
    - しきい値が 0〜100 の範囲外、クレジット率が 0〜100 の整数でなければ ValueError。

    >>> tiers = (("99.5", 10), ("99.0", 25), ("95.0", 50))
    >>> credit_percent(Fraction("99.5"), tiers), credit_percent(Fraction("98"), tiers)
    (0, 25)
    """
    raise NotImplementedError("演習3: credit_percent を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 契約ごとのクレジット額
# ---------------------------------------------------------------------------

def compute_credits(
    contracts: Iterable[Contract],
    plans: Mapping[str, Plan],
    outages: Iterable[Window],
    year: int,
    month: int,
    tz: tzinfo,
    maintenance: Iterable[Window] = (),
) -> dict[str, int]:
    """year 年 month 月（タイムゾーン tz）の、顧客ごとのクレジット額（円）を返す。

    - 稼働率はサービス全体で 1 つとする（この演習では全顧客が同じ障害の影響を受ける前提）。
    - クレジット額 = monthly_fee × min(クレジット率, プランの cap_percent) ÷ 100。
      1 円未満は切り捨て。float を経由せず整数で計算すること。
    - 戻り値は {customer_id: クレジット額}。
    - 未知のプラン、customer_id の重複、monthly_fee が負の場合は ValueError。

    例: 6 月のダウンタイム 70 分（稼働率 約 99.838%）の場合、
        standard（99.5% 未満で 10%）は 0 円、enterprise（99.9% 未満で 25%）の
        月額 100 万円の顧客は 25 万円。
    """
    raise NotImplementedError("演習4: compute_credits を実装してください")
