"""10.5 インシデント対応とポストモーテム — 演習: 公平なオンコール表

複数の拠点（東京・ダブリン・サンフランシスコなど）で昼間だけオンコールを担当する
「フォロー・ザ・サン」の体制で、24 時間のカバー範囲を確かめ、休暇・連続担当の禁止・
祝日の重み付けを守りながら、負荷が公平になるように担当者を割り当てます。

- 演習3（★★☆）: utc_coverage, coverage_gaps — 拠点ごとの勤務時間と UTC のカバー範囲
- 演習4（★★★）: slot_weight, build_schedule, load_spread — 制約付きの公平な割り当て
（演習1・2 は incident_metrics.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.5

簡略化している点: 時差は固定（夏時間は考えない）。実務では tz データベース（zoneinfo）を使い、
夏時間の切り替えでカバーに穴が空かないか確かめる必要があります。割り当ては「1 週 × 1 拠点 = 1 人」の
プライマリーだけで、セカンダリー（予備の担当）は扱いません。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class Site:
    name: str
    utc_offset: int      # UTC からの時差（時間）。夏時間は考えない
    day_start: int = 9   # 現地時刻で担当を始められる時（この時を含む）
    day_end: int = 17    # 現地時刻で担当を終える時（この時を含まない）


@dataclass(frozen=True)
class Engineer:
    name: str
    site: str
    unavailable_weeks: frozenset[int] = field(default_factory=frozenset)


@dataclass
class Schedule:
    assignments: dict[tuple[int, str], str]   # (週, 拠点) → 担当者
    load: dict[str, float]                    # 担当者 → 重み付きの負荷の合計
    warnings: list[str]


class ScheduleError(Exception):
    """制約を満たす担当者がいない。"""


# ===========================================================================
# 演習3（★★☆）: フォロー・ザ・サンのカバー範囲
# ===========================================================================

def utc_coverage(sites: Sequence[Site]) -> list[list[str]]:
    """UTC の各時（0〜23）について、その時に勤務時間中の拠点名のリスト（名前の昇順）を返す。

    拠点の現地時刻 = (UTC の時 + utc_offset) mod 24。day_start <= 現地時刻 < day_end なら勤務時間中。
    0 <= day_start < day_end <= 24 でない拠点があれば ValueError（日付をまたぐ勤務時間は扱わない）。

    例: 東京（+9、9〜17 時）は UTC 0〜7 時、サンフランシスコ（-8、9〜17 時）は UTC 17〜24 時と 0 時。
    """
    raise NotImplementedError("演習3: utc_coverage を実装してください")


def coverage_gaps(sites: Sequence[Site]) -> list[tuple[int, int]]:
    """どの拠点も勤務時間でない UTC の時間帯を、[(開始, 終了), ...]（終了は含まない、0〜24）で返す。

    連続する空き時間は 1 つの区間にまとめる。日付の境目（24 時 = 0 時）ではまとめず分割する。
    例: ダブリンだけ（UTC 9〜17 時）なら [(0, 9), (17, 24)]。拠点がなければ [(0, 24)]。
    """
    raise NotImplementedError("演習3: coverage_gaps を実装してください")


# ===========================================================================
# 演習4（★★★）: 公平なオンコール表
# ===========================================================================

def slot_weight(site: str, week: int, holidays: Mapping[tuple[str, int], int], holiday_weight: float,
                days_per_week: int = 7) -> float:
    """その拠点のその週の担当の重み = 通常の日数 + holiday_weight × 祝日の日数。

    holidays は {(拠点, 週): 祝日の日数}（なければ 0）。祝日の日数が 0〜days_per_week の外なら ValueError。
    例: 祝日 3 日、holiday_weight 2.0 → 4 + 3 × 2.0 = 10.0
    """
    raise NotImplementedError("演習4: slot_weight を実装してください")


def build_schedule(
    engineers: Sequence[Engineer],
    weeks: int,
    *,
    holidays: Mapping[tuple[str, int], int] | None = None,
    holiday_weight: float = 2.0,
) -> Schedule:
    """週 0〜weeks-1 の各拠点のオンコール担当を決める。

    週の順に、各週の中では拠点名の昇順に、1 枠ずつ次の手順で決める:
    1. その拠点の担当者のうち、その週が unavailable_weeks に入っていない人が候補。
       1 人もいなければ ScheduleError。
    2. 前の週の同じ拠点の担当者を候補から外す（2 週連続にしない）。外すと誰もいなくなる場合に限り、
       外さずに進め、warnings に「第{週}週 {拠点}: {名前} が 2 週連続になります」の形の文を追加する。
    3. 候補のうち (これまでの重み付き負荷, これまでの担当回数, 名前) が最小の人を選ぶ。
    4. 選んだ人の負荷に slot_weight(...) を足し、担当回数を 1 増やす。

    返り値: Schedule(assignments={(週, 拠点): 名前}, load={名前: 負荷}（担当のない人も 0.0 で含める）, warnings)
    担当者の名前が重複していれば ValueError。

    これは貪欲法による近似的な公平で、最適とは限らない（連続禁止のために、負荷が最小の人を選べない週がある）。
    """
    raise NotImplementedError("演習4: build_schedule を実装してください")


def load_spread(schedule: Schedule, engineers: Sequence[Engineer]) -> dict[str, float]:
    """拠点ごとの負荷の差（最大 - 最小）を、拠点名の昇順の dict で返す。"""
    raise NotImplementedError("演習4: load_spread を実装してください")
