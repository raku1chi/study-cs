"""10.4 オブザーバビリティ — 演習: Prometheus 風のメトリクス計算

Prometheus のカウンタの rate() と、累積バケットのヒストグラムからの分位点の推定
（histogram_quantile()）を実装し、「インスタンスごとの p95 を平均してはいけない」理由を
数字で確かめます。

- 演習1（★☆☆）: counter_increase, counter_rate — リセットに対応したカウンタの増分
- 演習2（★★☆）: histogram_quantile, Histogram（observe / cumulative / merge / quantile）,
                  merge_all, average_of_quantiles
（演習3・4 は logstats.py、演習5・6 は tracectx.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.4

簡略化している点: 本物の PromQL の rate() / increase() は、窓の端まで値を外挿しますが、
この演習では外挿しません。histogram_quantile() の細部（小さな非単調性の補正など）も省略しています。
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
# 演習1（★☆☆）: カウンタの増分と rate
# ===========================================================================

def counter_increase(samples: Sequence[tuple[float, float]]) -> float:
    """カウンタのサンプル [(時刻（秒）, 値), ...] から、期間中の増分の合計を返す。

    - カウンタは単調に増える値だが、プロセスの再起動で 0 に戻る（リセット）。値が前のサンプルより
      減っていたらリセットとみなし、その区間の増分は「0 からの増分 = 今の値」とする。
    - サンプルが 2 つ未満、または時刻が狭義単調増加でなければ ValueError。

    >>> counter_increase([(0, 100), (15, 160), (30, 220), (45, 20), (60, 80)])
    200.0
    """
    raise NotImplementedError("演習1: counter_increase を実装してください")


def counter_rate(samples: Sequence[tuple[float, float]]) -> float:
    """1 秒あたりの平均増加率 = counter_increase(samples) / (最後の時刻 - 最初の時刻)。検証も同じ。"""
    raise NotImplementedError("演習1: counter_rate を実装してください")


# ===========================================================================
# 演習2（★★☆）: 累積バケットのヒストグラムと分位点
# ===========================================================================

def histogram_quantile(q: float, buckets: Iterable[tuple[float, float]]) -> float:
    """累積バケット [(上限 le, その上限以下の観測数の累積), ...] から q 分位点を推定する。

    PromQL の histogram_quantile() と同じ手順:
    1. バケットを上限の昇順に並べる（入力の順序は問わない）。最後は上限 math.inf でなければ ValueError。
       累積の個数が減っているところがあれば ValueError。q が 0〜1 の外なら ValueError。
    2. 総数（+Inf のバケットの累積）が 0 なら math.nan。
    3. rank = q × 総数。+Inf 以外のバケットのうち、累積が初めて rank 以上になるものを探す。
    4. 見つからなければ（rank が +Inf のバケットに入る）、有限の上限の最大値を返す（+Inf の中は補間できない）。
    5. 見つかったバケットの下限（1 つ前のバケットの上限。最初のバケットなら 0）と上限の間で線形補間する:
       下限 + (上限 - 下限) × (rank - 1 つ前の累積) / (このバケットの個数)
       （最初のバケットの上限が 0 以下ならその上限を返す。このバケットの個数が 0 なら下限を返す）

    >>> histogram_quantile(0.9, [(0.1, 50), (0.25, 80), (0.5, 95), (1.0, 100), (math.inf, 100)])
    0.41666666666666663

    つまり推定値は、バケットの中では値が一様に分布していると仮定したもの。精度はバケットの境界の
    選び方で決まる（SLO の閾値をバケットの境界にしておくと、閾値の前後が正確に分かる）。
    """
    raise NotImplementedError("演習2: histogram_quantile を実装してください")


class Histogram:
    """Prometheus のヒストグラム（累積バケット）を模したもの。

    属性: bounds（有限の上限のタプル）、counts（各バケットの「非累積」の個数。最後の要素は +Inf）、
    sum（観測値の合計）、count（観測数）。__init__ は実装済みです。
    """

    def __init__(self, bounds: Sequence[float] = DEFAULT_BUCKETS) -> None:
        bounds = tuple(float(x) for x in bounds)
        if not bounds or any(math.isinf(x) or math.isnan(x) for x in bounds) or any(
            bounds[i] >= bounds[i + 1] for i in range(len(bounds) - 1)
        ):
            raise ValueError("bounds は有限の値の狭義単調増加の列にしてください")
        self.bounds = bounds
        self.counts = [0] * (len(bounds) + 1)
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        """value を「value <= 上限」となる最初のバケットに数える（上限ちょうどはそのバケット）。

        どの上限より大きければ +Inf のバケット。sum と count も更新する。NaN は ValueError。
        ヒント: bisect.bisect_left(self.bounds, value) がバケットの番号になる。
        """
        raise NotImplementedError("演習2: Histogram.observe を実装してください")

    def cumulative(self) -> list[tuple[float, int]]:
        """[(上限, 累積の個数), ...] を上限の昇順で返す。最後は (math.inf, count)。"""
        raise NotImplementedError("演習2: Histogram.cumulative を実装してください")

    def merge(self, other: "Histogram") -> "Histogram":
        """2 つのヒストグラムを足し合わせた新しいヒストグラムを返す（元は変更しない）。

        バケットごとの個数・sum・count をそれぞれ足す（PromQL の sum by (le) に相当）。
        境界が異なれば ValueError。
        """
        raise NotImplementedError("演習2: Histogram.merge を実装してください")

    def quantile(self, q: float) -> float:
        """histogram_quantile(q, self.cumulative())。"""
        raise NotImplementedError("演習2: Histogram.quantile を実装してください")


def merge_all(histograms: Sequence[Histogram]) -> Histogram:
    """複数のインスタンスのヒストグラムをすべて足し合わせる。空なら ValueError。"""
    raise NotImplementedError("演習2: merge_all を実装してください")


def average_of_quantiles(histograms: Sequence[Histogram], q: float) -> float:
    """各ヒストグラムの q 分位点の単純平均を返す（空なら ValueError）。

    これは「やってはいけない集計」の例として実装する。テストで merge_all(...).quantile(q) と比べ、
    トラフィックの偏りがあると何十倍もずれることを確かめよう。
    """
    raise NotImplementedError("演習2: average_of_quantiles を実装してください")
