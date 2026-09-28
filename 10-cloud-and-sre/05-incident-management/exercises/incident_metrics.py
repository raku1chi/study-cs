"""10.5 インシデント対応とポストモーテム — 演習: インシデントの指標と SLA のクレジット

インシデントの記録から、検知・応答・緩和・解決までの時間を重大度ごとに要約し、
月間の停止時間から SLA の返金（サービスクレジット）を計算します。平均値がなぜ誤解を
招くのか、停止時間の重なりや月の長さがなぜ金額を変えるのかを、実装を通して確かめます。

- 演習1（★☆☆〜★★☆）: durations, percentile, summarize
- 演習2（★★☆）: month_range, downtime, monthly_downtime, uptime_percent, sla_credit_percent, credit_yen
（演習3・4 は oncall.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.5

用語（この演習での定義。組織によって定義が違うので、社内では必ず定義を明文化すること）:
    ttd = 検知 - 影響開始、tta = 応答 - 検知、ttm = 緩和 - 影響開始、ttr = 解決 - 影響開始（すべて分）
"""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from typing import Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class Incident:
    id: str
    severity: str               # "SEV1"〜"SEV4"
    started_at: datetime        # 影響が始まった時刻（後から調査で判明することが多い）
    detected_at: datetime       # 検知した時刻（アラート・問い合わせ）
    acknowledged_at: datetime   # 担当者が応答した時刻
    mitigated_at: datetime      # 利用者への影響がなくなった時刻（切り戻しなどによる緩和）
    resolved_at: datetime       # インシデントとして解決した時刻


METRICS = ("ttd", "tta", "ttm", "ttr")


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


# ===========================================================================
# 演習1（★☆☆〜★★☆）: 所要時間と分布の要約
# ===========================================================================

def durations(incident: Incident) -> dict[str, float]:
    """{"ttd": ..., "tta": ..., "ttm": ..., "ttr": ...} を分単位の float で返す。

    時刻の順序の検証（満たさなければ ValueError）:
    - started_at <= detected_at <= acknowledged_at
    - started_at <= mitigated_at <= resolved_at
    （自動ロールバックなどで、応答より先に緩和されることはありうるので、acknowledged と mitigated の順は問わない）
    """
    raise NotImplementedError("演習1: durations を実装してください")


def percentile(values: Sequence[float], p: float) -> float:
    """最近順位法の p パーセンタイル（昇順に並べて ceil(p/100 × n) 番目）。

    values が空、または p が 0 < p <= 100 でなければ ValueError。
    """
    raise NotImplementedError("演習1: percentile を実装してください")


def summarize(incidents: Sequence[Incident], metric: str) -> dict[str, dict[str, float]]:
    """metric（"ttd" / "tta" / "ttm" / "ttr"）を重大度ごとと全体（キー "ALL"）で要約する。

    返り値: {キー: {"count": 件数, "median": 中央値, "p90": percentile(90), "mean": 平均, "max": 最大}}
    キーは昇順（"ALL", "SEV1", "SEV2", ...）。中央値は statistics.median（偶数個なら中央の 2 つの平均）。
    metric が上記以外なら ValueError。

    インシデントの継続時間は、ごく一部の長いものが平均を大きく引き上げる「裾の長い」分布になりやすい。
    平均（いわゆる MTTR）だけを報告すると、改善も悪化も見誤る。
    """
    raise NotImplementedError("演習1: summarize を実装してください")


# ===========================================================================
# 演習2（★★☆）: 月間の停止時間と SLA のクレジット
# ===========================================================================

def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """その月の [開始, 翌月の開始) を UTC の datetime で返す（12 月の翌月は翌年 1 月）。"""
    raise NotImplementedError("演習2: month_range を実装してください")


def downtime(intervals: Sequence[tuple[datetime, datetime]], start: datetime, end: datetime) -> timedelta:
    """停止区間 [(開始, 終了), ...] の、期間 [start, end) に含まれる部分の合計の長さ。

    - 各区間を期間に切り詰めてから、重なる区間は 1 つにまとめる（同じ時間を二重に数えない）。
    - 終了 < 開始 の区間があれば ValueError。
    """
    raise NotImplementedError("演習2: downtime を実装してください")


def monthly_downtime(intervals: Sequence[tuple[datetime, datetime]], year: int, month: int) -> timedelta:
    """downtime(intervals, *month_range(year, month))。"""
    raise NotImplementedError("演習2: monthly_downtime を実装してください")


def uptime_percent(down: timedelta, period: timedelta) -> float:
    """稼働率（%）= (1 - down / period) × 100。表示用の float。

    period <= 0、または down が 0〜period の外なら ValueError。
    """
    raise NotImplementedError("演習2: uptime_percent を実装してください")


def sla_credit_percent(down: timedelta, period: timedelta, tiers: Sequence[tuple[float, int]]) -> int:
    """SLA のクレジットの割合（%）を返す。

    tiers は [(閾値の稼働率 %, クレジット %), ...]。稼働率が閾値を「下回った」（<）段のうち、
    最大のクレジットを返す。どれにも当てはまらなければ 0。tiers の順序は問わない。
    例: [(99.9, 10), (99.0, 25), (95.0, 100)] なら、99.9% ちょうどは 0、99.5% は 10、98% は 25。
    検証は uptime_percent と同じ。

    ヒント: 浮動小数点の計算は、境界ちょうどの値で誤差により判定が逆転しうる（1.1 章）。
    お金に関わる境界の判定では、fractions.Fraction で厳密に計算するのが安全:
    稼働率 = (1 - Fraction(停止のマイクロ秒) / Fraction(期間のマイクロ秒)) × 100、閾値は Fraction(str(閾値))。
    """
    raise NotImplementedError("演習2: sla_credit_percent を実装してください")


def credit_yen(monthly_fee_yen: int, credit_percent: int) -> int:
    """返金額（円）= 月額 × クレジット % ÷ 100（円未満は切り捨て、整数演算で）。

    月額が負、またはクレジットが 0〜100 の外なら ValueError。
    """
    raise NotImplementedError("演習2: credit_yen を実装してください")
