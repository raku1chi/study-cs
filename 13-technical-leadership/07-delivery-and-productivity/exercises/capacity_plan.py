"""13.7 デリバリーと生産性 — 演習: 四半期のチームのキャパシティ計画

祝日・休暇・勤務形態・オンコールの負担・間接作業を考慮して、四半期にチームが使える
「集中して開発に使える人日」を計算し、新機能・技術的負債・運用保守などに配分します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.7
    python3 tools/check.py -v 13.7

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_capacity_plan

祝日は国や年によって変わるので、呼び出し側が holidays として与えます（本文の例は日本の 2026 年の祝日）。
制約: 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

import math  # noqa: F401  allocate で使えます
from dataclasses import dataclass
from datetime import date, timedelta  # noqa: F401  business_days で使えます


@dataclass(frozen=True)
class Member:
    """チームのメンバー。

    fte         : 勤務の割合（1.0 = フルタイム、0.8 = 短時間勤務、0.5 = 他チームと兼務など）
    leave_days  : 期間中の休暇（営業日の日数）
    oncall_weeks: 期間中にオンコールを担当する週の数
    """

    name: str
    fte: float = 1.0
    leave_days: float = 0.0
    oncall_weeks: int = 0


# ---------------------------------------------------------------------------
# 演習5（★☆☆）: 営業日、キャパシティ、配分
# ---------------------------------------------------------------------------

def business_days(start: date, end: date, holidays: set[date] | list[date] = ()) -> int:
    """start から end まで（両端を含む）の営業日（月〜金で、holidays に含まれない日）の数を返す。

    - end < start → ValueError

    >>> business_days(date(2026, 10, 5), date(2026, 10, 18), {date(2026, 10, 12)})
    9
    """
    raise NotImplementedError("演習5: business_days を実装してください")


def member_capacity(
    member: Member, days: int, overhead_ratio: float = 0.2, oncall_cost_days: float = 2.0
) -> float:
    """1 人のメンバーの、期間中に集中して開発に使える人日を返す。

    使える日 = max(0, days − leave_days) × fte
    集中できる日 = 使える日 × (1 − overhead_ratio) − oncall_weeks × oncall_cost_days
    （overhead_ratio は会議・レビュー・割り込みなどの間接作業の割合、
      oncall_cost_days はオンコールを担当する 1 週あたりに開発に使えなくなる日数）
    結果が負なら 0.0 を返す。

    - fte が (0, 1] の範囲外、leave_days・oncall_weeks・days が負、
      overhead_ratio が [0, 1) の範囲外、oncall_cost_days が負 → ValueError

    >>> member_capacity(Member("A", leave_days=3, oncall_weeks=3), 60)
    39.6
    """
    raise NotImplementedError("演習5: member_capacity を実装してください")


def team_capacity(
    members: list[Member], days: int, overhead_ratio: float = 0.2, oncall_cost_days: float = 2.0
) -> float:
    """チーム全員の member_capacity の合計を返す。"""
    raise NotImplementedError("演習5: team_capacity を実装してください")


def allocate(total_days: float, buckets: dict[str, float], step: float = 0.5) -> dict[str, float]:
    """total_days を buckets の割合で配分し、各バケットを step の倍数に丸めて返す。

    1. 配れる単位の数 units = floor(total_days / step)（端数は切り捨てる）
    2. 各バケットにまず floor(units × 割合) 単位を配る
    3. 余った単位を、切り捨てた端数（units × 割合 − 配った単位）の大きいバケットから 1 つずつ配る
       （最大剰余法）。端数が同じなら buckets の順で先のバケットを優先する
    4. 単位 × step を人日として、buckets と同じ順の dict で返す
    これにより、配分の合計はちょうど units × step になる。

    - total_days が負、step が 0 以下、buckets が空、割合が負、割合の合計が 1 でない → ValueError
      （合計の判定には 1e-9 の許容誤差を使う。units の計算でも、floor の前に 1e-9 を足して
       0.1 + 0.2 のような浮動小数点の誤差で 1 単位少なくならないようにする）

    >>> allocate(10, {"新機能": 0.6, "技術的負債": 0.2, "運用": 0.2})
    {'新機能': 6.0, '技術的負債': 2.0, '運用': 2.0}
    >>> allocate(10.8, {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3})
    {'a': 3.5, 'b': 3.5, 'c': 3.5}
    """
    raise NotImplementedError("演習5: allocate を実装してください")
