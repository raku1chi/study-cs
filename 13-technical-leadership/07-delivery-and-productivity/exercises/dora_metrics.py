"""13.7 デリバリーと生産性 — 演習: DORA の 4 つの指標

デプロイと障害のイベントログから、DORA の 4 つの指標（デプロイ頻度・変更のリードタイム・
変更失敗率・復旧時間）を計算し、しきい値で分類するツールを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
ファイルの読み込み（load_events・parse_time）は実装済みです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.7          # この章の 3 つの演習（dora_metrics, flow_metrics, capacity_plan）
    python3 tools/check.py -v 13.7

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_dora_metrics

データ: exercises/data/delivery_events.json（架空の 1 チームの 2026 年 7〜9 月の本番のイベント）
    - 時刻はタイムゾーン付きの ISO 8601 形式（例: "2026-07-02T18:00+09:00"）。
      Python 3.10 の datetime.fromisoformat は末尾の "Z" を解釈できないので、データでは "+09:00" の
      ようにオフセットを書いている
    - deployments: デプロイごとに、デプロイ時刻・含まれるコミットの時刻・状態
      （"success" = 本番で動いている、"rolled_back" = ロールバックされた）
    - incidents: 障害ごとに、発生・解決の時刻と、原因となったデプロイの ID（デプロイと関係ない障害は null）

指標の定義（この演習での簡略化した定義。実際の定義は組織ごとに決める）:
    - デプロイ頻度: 期間中の status == "success" のデプロイの数 ÷ 期間の日数（1 日あたりの回数）
    - 変更のリードタイム: success のデプロイに含まれる各コミットの「コミットからデプロイまで」の時間
    - 変更失敗率: 「ロールバックされた、または障害の原因になった」デプロイの数 ÷ 全デプロイの数
    - 復旧時間: 障害の発生から解決までの時間の中央値

制約: 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

import json
import math  # noqa: F401  percentile で使えます
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

CLUSTERS = ("elite", "high", "medium", "low")

# 分類のしきい値の例（教材用に単純化した値。各年の State of DevOps レポートの値とは異なる）
# 指標名: (良い方向, [(クラスタ, 境界), ...])。良いクラスタから順に並べる
DEFAULT_THRESHOLDS: dict[str, tuple[str, list[tuple[str, float]]]] = {
    "deployment_frequency": ("higher", [("elite", 1.0), ("high", 1 / 7), ("medium", 1 / 30)]),
    "lead_time_median_hours": ("lower", [("elite", 24.0), ("high", 24.0 * 7), ("medium", 24.0 * 30)]),
    "change_failure_rate": ("lower", [("elite", 0.05), ("high", 0.10), ("medium", 0.15)]),
    "time_to_restore_hours": ("lower", [("elite", 1.0), ("high", 24.0), ("medium", 24.0 * 7)]),
}


@dataclass(frozen=True)
class Deployment:
    id: str
    deployed_at: datetime
    commit_times: tuple[datetime, ...]
    status: str  # "success" または "rolled_back"


@dataclass(frozen=True)
class Incident:
    id: str
    started_at: datetime
    resolved_at: datetime
    deployment_id: str | None


def parse_time(text: str) -> datetime:
    """タイムゾーン付きの ISO 8601 の文字列を datetime にする（実装済み）。"""
    t = datetime.fromisoformat(text)
    if t.tzinfo is None:
        raise ValueError(f"タイムゾーンのない時刻は扱いません: {text}")
    return t


def load_events(path: str | Path) -> tuple[list[Deployment], list[Incident], datetime, datetime]:
    """イベントログを読み込み、(デプロイ, 障害, 期間の開始, 期間の終了) を返す（実装済み）。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    deployments = [
        Deployment(d["id"], parse_time(d["deployed_at"]),
                   tuple(parse_time(c) for c in d["commit_times"]), d["status"])
        for d in data["deployments"]
    ]
    incidents = [
        Incident(i["id"], parse_time(i["started_at"]), parse_time(i["resolved_at"]), i["deployment_id"])
        for i in data["incidents"]
    ]
    period = data["period"]
    return deployments, incidents, parse_time(period["start"]), parse_time(period["end"])


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: パーセンタイル、デプロイ頻度、変更のリードタイム
# ---------------------------------------------------------------------------

def percentile(values: list[float], p: float) -> float:
    """p パーセンタイル（0 <= p <= 100）を線形補間で返す。

    値を昇順に並べた xs について、順位 r = (n − 1) × p / 100 を求め、
    r の整数部 i と小数部 f を使って xs[i] + (xs[i+1] − xs[i]) × f を返す（i が最後なら xs[i]）。
    これは statistics.quantiles(method="inclusive") や、NumPy の既定の方法と同じ考え方。

    - values が空、または p が範囲外 → ValueError

    >>> percentile([4, 1, 3, 2], 50)
    2.5
    >>> percentile([1, 2, 3, 4], 75)
    3.25
    """
    raise NotImplementedError("演習1: percentile を実装してください")


def deployment_frequency(deployments: list[Deployment], start: datetime, end: datetime) -> float:
    """1 日あたりのデプロイ回数を返す。

    数えるのは status == "success" で、start <= deployed_at < end のデプロイ。
    日数は (end − start) を日単位の小数にしたもの。

    - end <= start → ValueError
    """
    raise NotImplementedError("演習1: deployment_frequency を実装してください")


def lead_times_hours(deployments: list[Deployment]) -> list[float]:
    """status == "success" のデプロイに含まれる各コミットについて、
    「コミットからデプロイまで」の時間（時間単位の小数）のリストを返す。

    - 順序はデプロイの入力順、その中はコミットの入力順
    - コミットの時刻がデプロイより後（負の時間）→ ValueError（データの誤り）
    """
    raise NotImplementedError("演習1: lead_times_hours を実装してください")


def lead_time_summary(deployments: list[Deployment]) -> dict[str, float]:
    """変更のリードタイムの {"median": 中央値, "p90": 90 パーセンタイル}（時間）を返す。

    lead_times_hours と percentile を使う。平均ではなくパーセンタイルを使うのは、
    リードタイムの分布は長い尾を持ち、平均は少数の極端な値に大きく引っ張られるから。
    """
    raise NotImplementedError("演習1: lead_time_summary を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 変更失敗率、復旧時間、パフォーマンスの分類
# ---------------------------------------------------------------------------

def change_failure_rate(deployments: list[Deployment], incidents: list[Incident]) -> float:
    """変更失敗率を返す。

    失敗したデプロイ = status が "rolled_back" のデプロイ ∪ いずれかの障害の deployment_id が指すデプロイ
    （同じデプロイがロールバックされ、かつ障害の原因にもなっていても 1 回と数える）
    変更失敗率 = 失敗したデプロイの数 ÷ 全デプロイの数（status によらず）

    - deployments が空、障害が存在しないデプロイの ID を指している → ValueError
    """
    raise NotImplementedError("演習2: change_failure_rate を実装してください")


def time_to_restore_hours(incidents: list[Incident], deployment_caused_only: bool = False) -> float:
    """障害の発生から解決までの時間（時間単位）の中央値を返す。

    deployment_caused_only が True なら、deployment_id が None でない障害だけを対象にする
    （DORA の 2023 年以降の「失敗したデプロイからの復旧時間」に近い見方）。

    - 対象の障害が 0 件、解決が発生より前 → ValueError
    """
    raise NotImplementedError("演習2: time_to_restore_hours を実装してください")


def classify(
    metrics: dict[str, float],
    thresholds: dict[str, tuple[str, list[tuple[str, float]]]] | None = None,
) -> dict[str, str]:
    """指標ごとに "elite" / "high" / "medium" / "low" のクラスタを判定する。

    thresholds（None なら DEFAULT_THRESHOLDS）の各指標について、境界のリストを先頭から調べ、
    最初に条件を満たしたクラスタにする。どれも満たさなければ "low"。
        良い方向が "higher": 値 >= 境界 なら満たす
        良い方向が "lower" : 値 <= 境界 なら満たす
    戻り値には metrics の各指標のクラスタに加えて、"overall"（全指標のうち最も低いクラスタ）を含める。
    metrics が空なら空の dict を返す。

    - thresholds にない指標がある、良い方向が "higher"/"lower" 以外 → ValueError

    >>> classify({"change_failure_rate": 0.10, "deployment_frequency": 2.0})
    {'change_failure_rate': 'high', 'deployment_frequency': 'elite', 'overall': 'high'}
    """
    raise NotImplementedError("演習2: classify を実装してください")
