"""13.7 デリバリーと生産性 — 演習: フローメトリクス

チケットの状態遷移のログから、サイクルタイムの分布、スループット、仕掛かり（WIP）の推移、
フロー効率、滞留している仕掛かりのアラートを計算するツールを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
ファイルの読み込み（load_ticket_events）は実装済みです。
パーセンタイルは dora_metrics の演習1 で作る percentile を再利用します（先に演習1 を解いてください）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.7
    python3 tools/check.py -v 13.7

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_flow_metrics

データ: exercises/data/ticket_events.json（架空の 1 チームの 2026 年 7〜9 月のチケットの状態遷移）
    - events: {"ticket": ID, "at": 時刻, "to": 遷移先の状態}
    - 状態: "Ready"（着手待ち）, "In Progress"（作業中）, "Waiting for Review"（レビュー待ち）,
            "In Review"（レビュー中）, "Blocked"（他チームなどを待っている）, "Done"（完了）
    - active_states: 実際に手が動いている状態（"In Progress", "In Review"）
    - now: 集計の基準時刻

共通の定義:
    - 着手時刻 = そのチケットが最初に "In Progress" に入った時刻
    - 完了時刻 = 着手時刻以降に、最初に "Done" に入った時刻
    - サイクルタイム = 完了時刻 − 着手時刻（日単位の小数）。着手していない・完了していないチケットは除く

制約: 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta  # noqa: F401  演習3で使えます
from pathlib import Path

from dora_metrics import parse_time, percentile  # noqa: F401  演習1 の関数を再利用する

START_STATE = "In Progress"
DONE_STATE = "Done"


@dataclass(frozen=True)
class Event:
    ticket: str
    at: datetime
    to: str


def load_ticket_events(path: str | Path) -> tuple[list[Event], datetime, list[str]]:
    """ログを読み込み、(イベント, 基準時刻 now, active_states) を返す（実装済み）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = [Event(e["ticket"], parse_time(e["at"]), e["to"]) for e in data["events"]]
    return events, parse_time(data["now"]), list(data["active_states"])


# ---------------------------------------------------------------------------
# 演習3（★★☆）: サイクルタイムとスループット
# ---------------------------------------------------------------------------

def cycle_times_days(events: list[Event]) -> dict[str, float]:
    """完了したチケットごとのサイクルタイム（日）を返す（キーはチケット ID の昇順）。

    - events は時刻順に並んでいるとは限らない（チケットごとに時刻順に並べ直してから調べる）
    - 着手していない、または完了していないチケットは含めない

    ヒント: まずチケットごとにイベントをまとめ、時刻順に並べる。
    """
    raise NotImplementedError("演習3: cycle_times_days を実装してください")


def cycle_time_percentiles(events: list[Event], ps: tuple[float, ...] = (50, 85, 95)) -> dict[float, float]:
    """サイクルタイムの各パーセンタイル {p: 値（日）} を返す（percentile を使う）。

    - 完了したチケットが 0 件 → ValueError（percentile が送出する）
    """
    raise NotImplementedError("演習3: cycle_time_percentiles を実装してください")


def throughput_per_week(events: list[Event], start: datetime, weeks: int) -> list[int]:
    """start から 1 週間（7 日）ごとに区切った各週に完了したチケットの数のリストを返す。

    k 番目の週は [start + 7k 日, start + 7(k+1) 日)。範囲外に完了したチケットは数えない。

    - weeks が 1 未満 → ValueError
    """
    raise NotImplementedError("演習3: throughput_per_week を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 仕掛かり（WIP）、フロー効率、滞留アラート
# ---------------------------------------------------------------------------

def wip_at(events: list[Event], times: list[datetime]) -> list[int]:
    """各時刻 t の仕掛かりの数（着手時刻 <= t で、完了していないか完了時刻 > t のチケットの数）を返す。"""
    raise NotImplementedError("演習4: wip_at を実装してください")


def flow_efficiency(events: list[Event], active_states: list[str]) -> tuple[dict[str, float], float]:
    """フロー効率を返す: (チケットごとの効率, 全体の効率)。

    チケットの効率 = 着手から完了までの間に active_states のいずれかにいた時間 ÷ サイクルタイム
    全体の効率 = 全チケットの能動的な時間の合計 ÷ 全チケットのサイクルタイムの合計
    （完了したチケットだけが対象。サイクルタイムが 0 のチケットは除く。対象が 0 件なら全体は 0.0）

    ある状態にいた時間 = その状態に入った時刻から、次のイベントの時刻まで。
    着手より前・完了より後の時間は数えない。

    >>> from datetime import timezone
    >>> t = lambda d: datetime(2026, 7, d, tzinfo=timezone.utc)
    >>> evs = [Event("A", t(1), "In Progress"), Event("A", t(3), "Waiting for Review"),
    ...        Event("A", t(4), "In Review"), Event("A", t(5), "Done")]
    >>> flow_efficiency(evs, ["In Progress", "In Review"])
    ({'A': 0.75}, 0.75)
    """
    raise NotImplementedError("演習4: flow_efficiency を実装してください")


def aging_wip(events: list[Event], now: datetime, threshold_days: float) -> list[tuple[str, float, str]]:
    """now の時点で仕掛かり中のチケットのうち、着手からの経過日数が threshold_days を超えるものを返す。

    - now より後のイベントは無視する（now の時点で分かっていることだけで判断する）
    - 戻り値: (チケット ID, 経過日数, now の時点の状態) のリスト。経過日数の降順、同じならチケット ID の昇順

    ヒント: 閾値にはサイクルタイムの 85 パーセンタイルがよく使われる。「完了したチケットの 85% は
    この日数以内に終わっている」ので、それを超えた仕掛かりは、何か問題が起きている可能性が高い。
    """
    raise NotImplementedError("演習4: aging_wip を実装してください")
