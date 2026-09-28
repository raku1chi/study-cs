"""14.6 危機管理 — 解答例: SLAクレジットの計算

演習の仕様は exercises/sla_credit.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from fractions import Fraction
from typing import Iterable, Mapping, Sequence, Union

Window = tuple[datetime, datetime]
Exact = Union[int, Fraction, Decimal, str]

_US = timedelta(microseconds=1)


@dataclass(frozen=True)
class Plan:
    name: str
    tiers: tuple[tuple[str, int], ...]
    cap_percent: int = 100


@dataclass(frozen=True)
class Contract:
    customer_id: str
    plan: str
    monthly_fee: int


# ---------------------------------------------------------------------------
# 補助関数
# ---------------------------------------------------------------------------

def _check_aware(dt: datetime) -> None:
    # タイムゾーンのない時刻は「日本時間なのか UTC なのか」が分からない。
    # 障害記録でこれを曖昧にすると、ダウンタイムが 9 時間ずれることさえある。
    if not isinstance(dt, datetime):
        raise TypeError(f"datetime を指定してください: {dt!r}")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"タイムゾーン付きの datetime を指定してください: {dt!r}")


def _to_utc(window: Window) -> Window:
    start, end = window
    _check_aware(start)
    _check_aware(end)
    if start >= end:
        raise ValueError(f"開始が終了以降になっています: {start} >= {end}")
    # 同じ tzinfo の aware datetime 同士の引き算は「壁時計の差」になり、夏時間の
    # 切り替えを無視する。すべて UTC にそろえてから計算すれば、常に経過時間になる。
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _clip(window: Window, lo: datetime, hi: datetime) -> Window | None:
    start, end = max(window[0], lo), min(window[1], hi)
    return (start, end) if start < end else None


def _total(windows: Iterable[Window]) -> timedelta:
    return sum((end - start for start, end in windows), timedelta())


# ---------------------------------------------------------------------------
# 演習1: 区間の統合
# ---------------------------------------------------------------------------

def merge_windows(windows: Iterable[Window]) -> list[Window]:
    items = [_to_utc(w) for w in windows]
    merged: list[Window] = []
    # 開始時刻の順に並べると、「直前にまとめた区間と重なるか」だけを見ればよい（O(n log n)）
    for start, end in sorted(items):
        if merged and start <= merged[-1][1]:
            # 重なる、または接している（半開区間 [s, e) なので e == 次の s なら連続）
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


# ---------------------------------------------------------------------------
# 演習2: 請求期間とダウンタイム
# ---------------------------------------------------------------------------

def billing_period(year: int, month: int, tz: tzinfo) -> Window:
    if not 1 <= month <= 12:
        raise ValueError(f"month は 1〜12 で指定してください: {month}")
    if tz is None:
        raise ValueError("契約のタイムゾーンを指定してください")
    start = datetime(year, month, 1, tzinfo=tz)
    end = datetime(year + 1, 1, 1, tzinfo=tz) if month == 12 else datetime(year, month + 1, 1, tzinfo=tz)
    return start, end


def downtime_in_period(
    outages: Iterable[Window],
    period: Window,
    maintenance: Iterable[Window] = (),
) -> timedelta:
    lo, hi = _to_utc(period)
    # 1. 重複をなくしてから（同じ時間を二重に数えない）、請求期間の外を切り落とす
    down = [w for w in (_clip(w, lo, hi) for w in merge_windows(outages)) if w]
    maint = [w for w in (_clip(w, lo, hi) for w in merge_windows(maintenance)) if w]
    # 2. 計画メンテナンスと重なる部分を差し引く。
    #    down どうし・maint どうしは互いに重ならないので、ペアごとの重なりの合計が
    #    「down ∩ maint」の長さに等しい（件数が少ないので二重ループで十分）。
    overlap = timedelta()
    for d in down:
        for m in maint:
            both = _clip(d, m[0], m[1])
            if both:
                overlap += both[1] - both[0]
    return _total(down) - overlap


# ---------------------------------------------------------------------------
# 演習3: 稼働率とクレジット率
# ---------------------------------------------------------------------------

def _exact(value: Exact, what: str) -> Fraction:
    # float は 0.1 のような値を正確に表せない。境界判定がぶれないよう受け付けない。
    if isinstance(value, float):
        raise TypeError(f"{what} に float は使えません（文字列・int・Fraction・Decimal で指定）: {value!r}")
    if isinstance(value, bool) or not isinstance(value, (int, Fraction, Decimal, str)):
        raise TypeError(f"{what} の型が不正です: {value!r}")
    return Fraction(value)


def availability_percent(downtime: timedelta, period: Window) -> Fraction:
    lo, hi = _to_utc(period)
    length = hi - lo
    if downtime < timedelta() or downtime > length:
        raise ValueError(f"ダウンタイムが 0 〜 期間の長さ の範囲外です: {downtime}")
    # timedelta.total_seconds() は float を返すので使わない。
    # マイクロ秒単位の整数にしてから Fraction で割れば、誤差はまったく出ない。
    return 100 * (1 - Fraction(downtime // _US, length // _US))


def credit_percent(availability: Exact, tiers: Sequence[tuple[Exact, int]]) -> int:
    a = _exact(availability, "availability")
    rate = 0
    for threshold, pct in tiers:
        t = _exact(threshold, "しきい値")
        if not 0 <= t <= 100:
            raise ValueError(f"しきい値は 0〜100: {threshold}")
        if isinstance(pct, bool) or not isinstance(pct, int) or not 0 <= pct <= 100:
            raise ValueError(f"クレジット率は 0〜100 の整数: {pct!r}")
        # 「しきい値を下回ったら」なので、ちょうど等しいときは該当しない
        if a < t:
            rate = max(rate, pct)
    return rate


# ---------------------------------------------------------------------------
# 演習4: 契約ごとのクレジット額
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
    period = billing_period(year, month, tz)
    # 稼働率はサービス全体で 1 つ（この演習の前提）。顧客ごとに再計算しない。
    availability = availability_percent(downtime_in_period(outages, period, maintenance), period)
    credits: dict[str, int] = {}
    for c in contracts:
        if c.customer_id in credits:
            raise ValueError(f"customer_id が重複しています: {c.customer_id}")
        if isinstance(c.monthly_fee, bool) or not isinstance(c.monthly_fee, int) or c.monthly_fee < 0:
            raise ValueError(f"monthly_fee は 0 以上の整数（円）: {c.monthly_fee!r}")
        plan = plans.get(c.plan)
        if plan is None:
            raise ValueError(f"未知のプランです: {c.plan}")
        if not 0 <= plan.cap_percent <= 100:
            raise ValueError(f"cap_percent は 0〜100: {plan.cap_percent}")
        pct = min(credit_percent(availability, plan.tiers), plan.cap_percent)
        # 金額は整数の円で計算し、1 円未満は切り捨てる（float を経由しない）
        credits[c.customer_id] = c.monthly_fee * pct // 100
    return credits
