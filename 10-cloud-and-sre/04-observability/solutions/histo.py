"""10.4 オブザーバビリティ — 演習（Prometheus 風のメトリクス計算）の解答例

演習の仕様は exercises/histo.py の docstring を参照してください。
"""
from __future__ import annotations

import bisect
import math
from typing import Iterable, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

# Prometheus の Go クライアントの既定のバケット（秒）。上限 +Inf のバケットは暗黙に最後に付く
DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


def exact_quantile(values: Sequence[float], q: float) -> float:
    """生の値から分位点を求める（最近順位法: 小さい方から ceil(q × n) 番目）。答え合わせ用。"""
    if not values:
        raise ValueError("values が空です")
    if not 0.0 < q <= 1.0:
        raise ValueError(f"q は 0 < q <= 1: {q}")
    ordered = sorted(values)
    return ordered[max(1, math.ceil(q * len(ordered))) - 1]


# ===========================================================================
# 演習1: カウンタの増分と rate
# ===========================================================================

def counter_increase(samples: Sequence[tuple[float, float]]) -> float:
    if len(samples) < 2:
        raise ValueError("サンプルが 2 つ以上必要です")
    total = 0.0
    prev_t, prev_v = samples[0]
    for t, v in samples[1:]:
        if t <= prev_t:
            raise ValueError("時刻は狭義単調増加にしてください")
        # カウンタは減らない。減っていたらプロセスの再起動でリセットされた（0 から数え直した）とみなす
        total += v if v < prev_v else v - prev_v
        prev_t, prev_v = t, v
    return total


def counter_rate(samples: Sequence[tuple[float, float]]) -> float:
    increase = counter_increase(samples)
    return increase / (samples[-1][0] - samples[0][0])


# ===========================================================================
# 演習2: 累積バケットのヒストグラムと分位点
# ===========================================================================

def histogram_quantile(q: float, buckets: Iterable[tuple[float, float]]) -> float:
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"q は 0〜1: {q}")
    b = sorted(buckets)
    if not b or not math.isinf(b[-1][0]):
        raise ValueError("上限 +Inf のバケットが必要です")
    if any(b[i][1] > b[i + 1][1] for i in range(len(b) - 1)):
        raise ValueError("累積の個数が単調増加になっていません")
    total = b[-1][1]
    if total == 0:
        return math.nan
    rank = q * total
    # rank 番目の観測値が入っているバケット（累積の個数が初めて rank 以上になるもの）を探す
    i = next((j for j in range(len(b) - 1) if b[j][1] >= rank), len(b) - 1)
    if i == len(b) - 1:
        # +Inf のバケットに当たった: 上限が分からないので、有限の最大の上限を返す
        return b[-2][0] if len(b) >= 2 else math.nan
    upper, cum = b[i]
    if i == 0 and upper <= 0:
        return upper
    lower, below = (b[i - 1][0], b[i - 1][1]) if i > 0 else (0.0, 0.0)
    in_bucket = cum - below
    if in_bucket == 0:
        return lower
    # バケットの中では値が一様に分布していると仮定して、線形補間する
    return lower + (upper - lower) * (rank - below) / in_bucket


class Histogram:
    def __init__(self, bounds: Sequence[float] = DEFAULT_BUCKETS) -> None:
        bounds = tuple(float(x) for x in bounds)
        if not bounds or any(math.isinf(x) or math.isnan(x) for x in bounds) or any(
            bounds[i] >= bounds[i + 1] for i in range(len(bounds) - 1)
        ):
            raise ValueError("bounds は有限の値の狭義単調増加の列にしてください")
        self.bounds = bounds
        self.counts = [0] * (len(bounds) + 1)  # 各バケット（非累積）の個数。最後は +Inf
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        if math.isnan(value):
            raise ValueError("NaN は観測できません")
        # value <= 上限 となる最初のバケットに入れる（Prometheus のバケットは「以下」）
        self.counts[bisect.bisect_left(self.bounds, value)] += 1
        self.sum += value
        self.count += 1

    def cumulative(self) -> list[tuple[float, int]]:
        result, running = [], 0
        for upper, c in zip(self.bounds + (math.inf,), self.counts):
            running += c
            result.append((upper, running))
        return result

    def merge(self, other: "Histogram") -> "Histogram":
        if self.bounds != other.bounds:
            raise ValueError("バケットの境界が異なるヒストグラムは足し合わせられません")
        merged = Histogram(self.bounds)
        merged.counts = [a + b for a, b in zip(self.counts, other.counts)]
        merged.sum = self.sum + other.sum
        merged.count = self.count + other.count
        return merged

    def quantile(self, q: float) -> float:
        return histogram_quantile(q, self.cumulative())


def merge_all(histograms: Sequence[Histogram]) -> Histogram:
    if not histograms:
        raise ValueError("ヒストグラムが 1 つ以上必要です")
    merged = histograms[0]
    for h in histograms[1:]:
        merged = merged.merge(h)
    return merged


def average_of_quantiles(histograms: Sequence[Histogram], q: float) -> float:
    if not histograms:
        raise ValueError("ヒストグラムが 1 つ以上必要です")
    # これは誤った集計の例: インスタンスごとの分位点を平均しても、全体の分位点にはならない
    return sum(h.quantile(q) for h in histograms) / len(histograms)
