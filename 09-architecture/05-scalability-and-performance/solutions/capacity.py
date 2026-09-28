"""9.5 スケーラビリティとパフォーマンス — 解答例: 概算見積もりと性能モデルの道具箱

演習の仕様は exercises/capacity.py の docstring を参照してください。
"""
from __future__ import annotations

import math

SECONDS_PER_DAY = 86_400
DAYS_PER_YEAR = 365
EPSILON = 1e-9


def _positive(**values: float) -> None:
    for name, v in values.items():
        if not v > 0:
            raise ValueError(f"{name} は正の数です: {v!r}")


def _non_negative(**values: float) -> None:
    for name, v in values.items():
        if not v >= 0:
            raise ValueError(f"{name} は 0 以上です: {v!r}")


def average_qps(daily_active_users: float, requests_per_user_per_day: float) -> float:
    _non_negative(daily_active_users=daily_active_users, requests_per_user_per_day=requests_per_user_per_day)
    return daily_active_users * requests_per_user_per_day / SECONDS_PER_DAY


def peak_qps(average: float, peak_factor: float) -> float:
    _non_negative(average=average)
    if peak_factor < 1:
        raise ValueError(f"ピーク係数は 1 以上です: {peak_factor!r}")
    return average * peak_factor


def storage_per_year(items_per_day: float, bytes_per_item: float, *, replication: int = 1,
                     overhead: float = 1.0) -> float:
    _non_negative(items_per_day=items_per_day, bytes_per_item=bytes_per_item)
    if replication < 1 or overhead < 1:
        raise ValueError("replication と overhead は 1 以上です")
    return items_per_day * bytes_per_item * DAYS_PER_YEAR * replication * overhead


def bandwidth_bps(qps: float, bytes_per_response: float) -> float:
    _non_negative(qps=qps, bytes_per_response=bytes_per_response)
    return qps * bytes_per_response * 8  # バイトではなくビット（1.1 章の単位の落とし穴）


def servers_needed(peak: float, qps_per_server: float, *, target_utilization: float = 0.6, spare: int = 1) -> int:
    _non_negative(peak=peak)
    _positive(qps_per_server=qps_per_server)
    if not 0 < target_utilization <= 1:
        raise ValueError(f"目標使用率は (0, 1] の範囲です: {target_utilization!r}")
    if spare < 0:
        raise ValueError("spare は 0 以上です")
    # 4900 / (700 * 0.7) は浮動小数点では 10.000000000000002 になる。
    # そのまま切り上げると 11 台になるので、誤差の分だけ引いてから切り上げる
    needed = math.ceil(peak / (qps_per_server * target_utilization) - EPSILON)
    return max(needed, 0) + spare


def littles_law_concurrency(throughput: float, latency_seconds: float) -> float:
    _non_negative(throughput=throughput, latency_seconds=latency_seconds)
    return throughput * latency_seconds  # L = λW


def amdahl_speedup(parallel_fraction: float, n: int) -> float:
    if not 0 <= parallel_fraction <= 1:
        raise ValueError("並列化できる割合は 0〜1 です")
    if n < 1:
        raise ValueError("n は 1 以上です")
    return 1 / ((1 - parallel_fraction) + parallel_fraction / n)


def usl_throughput(n: float, lam: float, sigma: float, kappa: float) -> float:
    if n < 1:
        raise ValueError("n は 1 以上です")
    _positive(lam=lam)
    _non_negative(sigma=sigma, kappa=kappa)
    return lam * n / (1 + sigma * (n - 1) + kappa * n * (n - 1))


def usl_peak_concurrency(sigma: float, kappa: float) -> float:
    if not 0 <= sigma < 1:
        raise ValueError("sigma は 0 以上 1 未満です")
    _positive(kappa=kappa)
    return math.sqrt((1 - sigma) / kappa)


def mm1_response_time(service_time: float, utilization: float) -> float:
    _positive(service_time=service_time)
    if not 0 <= utilization < 1:
        raise ValueError("使用率は 0 以上 1 未満です（1 以上では待ち行列が無限に伸びる）")
    return service_time / (1 - utilization)


def format_si(value: float, unit: str) -> str:
    for factor, prefix in ((1e15, "P"), (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= factor:
            return f"{value / factor:.1f} {prefix}{unit}"
    return f"{value:.1f} {unit}"
