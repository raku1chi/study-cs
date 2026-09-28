"""9.5 スケーラビリティとパフォーマンス — 演習1: 概算見積もりと性能モデルの道具箱

設計の議論の前に「桁」を確かめるための、小さな関数の集まりです。どれも数行で書けますが、
単位（秒・バイト・ビット）と、前提（平均かピークか、使用率をどこまで上げるか）を正しく扱うことが肝心です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.5

共通の約束: 負の値など意味のない入力は ValueError。
"""
from __future__ import annotations

import math  # noqa: F401

SECONDS_PER_DAY = 86_400
DAYS_PER_YEAR = 365
EPSILON = 1e-9


def average_qps(daily_active_users: float, requests_per_user_per_day: float) -> float:
    """1 日のアクティブユーザー数 × 1 人あたりの 1 日のリクエスト数 ÷ 86,400 秒。

    >>> round(average_qps(1_000_000, 20))
    231
    """
    raise NotImplementedError("演習1: average_qps を実装してください")


def peak_qps(average: float, peak_factor: float) -> float:
    """平均 × ピーク係数。ピーク係数は 1 以上（1 未満なら ValueError）。"""
    raise NotImplementedError("演習1: peak_qps を実装してください")


def storage_per_year(items_per_day: float, bytes_per_item: float, *, replication: int = 1,
                     overhead: float = 1.0) -> float:
    """1 年（365 日）で増えるバイト数 = 件数/日 × バイト/件 × 365 × 複製数 × オーバーヘッド係数。

    replication（レプリカの数）と overhead（インデックスなどの係数）は 1 以上。
    """
    raise NotImplementedError("演習1: storage_per_year を実装してください")


def bandwidth_bps(qps: float, bytes_per_response: float) -> float:
    """必要な帯域をビット毎秒で返す（バイトではない。1 バイト = 8 ビット）。"""
    raise NotImplementedError("演習1: bandwidth_bps を実装してください")


def servers_needed(peak: float, qps_per_server: float, *, target_utilization: float = 0.6, spare: int = 1) -> int:
    """ピーク時の負荷を、目標使用率以下で処理するのに必要なサーバーの台数（予備 spare 台を含む）。

    台数 = ⌈peak ÷ (1 台あたりの処理能力 × 目標使用率)⌉ + spare
    - target_utilization は (0, 1]、qps_per_server は正、spare は 0 以上。違反は ValueError。
    - 浮動小数点の誤差に注意: 4900 / (700 * 0.7) は 10.000000000000002 になり、そのまま切り上げると
      1 台多くなる。EPSILON を引いてから切り上げること。

    >>> servers_needed(4900, 700, target_utilization=0.7, spare=0)
    10
    """
    raise NotImplementedError("演習1: servers_needed を実装してください")


def littles_law_concurrency(throughput: float, latency_seconds: float) -> float:
    """Little の法則 L = λW: 系の中に同時に存在する平均の要求数（= 必要な同時実行数）。

    >>> littles_law_concurrency(1000, 0.2)   # 1,000 件/秒 × 0.2 秒
    200.0
    """
    raise NotImplementedError("演習1: littles_law_concurrency を実装してください")


def amdahl_speedup(parallel_fraction: float, n: int) -> float:
    """Amdahl の法則: 並列化できる割合 p の処理を n 並列にしたときの速度向上 1 / ((1 - p) + p / n)。

    p は 0〜1、n は 1 以上。
    """
    raise NotImplementedError("演習1: amdahl_speedup を実装してください")


def usl_throughput(n: float, lam: float, sigma: float, kappa: float) -> float:
    """Gunther の普遍的スケーラビリティ則（USL）によるスループット。

        X(N) = λN / (1 + σ(N − 1) + κN(N − 1))

    λ（lam）は 1 並列のときのスループット、σ（sigma）は競合（直列化される部分）、
    κ（kappa）は一貫性を保つための調整（ノード間の同期）のコスト。n は 1 以上、lam は正、sigma・kappa は 0 以上。
    """
    raise NotImplementedError("演習1: usl_throughput を実装してください")


def usl_peak_concurrency(sigma: float, kappa: float) -> float:
    """USL でスループットが最大になる並列度 N* = √((1 − σ) / κ)。sigma は [0, 1)、kappa は正。"""
    raise NotImplementedError("演習1: usl_peak_concurrency を実装してください")


def mm1_response_time(service_time: float, utilization: float) -> float:
    """M/M/1 待ち行列の平均応答時間 R = S / (1 − ρ)。使用率 ρ は [0, 1)、S（service_time）は正。

    使用率が 1 に近づくと応答時間が発散することを確かめよう（ρ = 0.9 なら処理時間の 10 倍）。
    """
    raise NotImplementedError("演習1: mm1_response_time を実装してください")


def format_si(value: float, unit: str) -> str:
    """SI 接頭辞（k, M, G, T, P = 10³ 〜 10¹⁵）で小数 1 桁に整形する（実装済み）。

    >>> format_si(36_500_000_000, "B")
    '36.5 GB'
    """
    for factor, prefix in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= factor:
            return f"{value / factor:.1f} {prefix}{unit}"
    return f"{value:.1f} {unit}"
