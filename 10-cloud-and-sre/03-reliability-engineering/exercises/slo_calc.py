"""10.3 信頼性設計とSLO — 演習: SLO 計算機

可用性の合成、エラーバジェット、バーンレート、そして Google の SRE ワークブックが推奨する
「多窓・多バーンレート」のアラート評価を実装します。数字で考える習慣が、SLO に基づく
運用判断の土台になります。

- 演習1（★☆☆）: serial, parallel, quorum, composite — 依存構造からの可用性の計算
- 演習2（★☆☆）: allowed_downtime, nines, error_budget, burn_rate, window_sli
- 演習3（★★★）: threshold_for, multiwindow_rules, evaluate_alerts — 分単位の時系列でアラートを評価
（演習4・5 は dr_planner.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.3

前提と簡略化:
    - 部品の故障は互いに独立と仮定する（現実には同じ AZ・同じ変更・同じバグによる相関があり、
      計算値は楽観的になる。本文を参照）。
    - 時系列は 1 分ごとの (成功数, 総数) のリスト。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

MINUTES_PER_30_DAYS = 30 * 24 * 60  # 43,200 分


@dataclass(frozen=True)
class BudgetStatus:
    total: int            # 期間中のリクエスト数
    bad: int              # 失敗（SLO を満たさなかった）リクエスト数
    allowed_bad: float    # エラーバジェット（許される失敗の数）
    consumed: float       # 予算の消費割合（1.0 で使い切り。超えることもある）
    remaining: float      # 1 - consumed


@dataclass(frozen=True)
class AlertRule:
    name: str
    long_window: int      # 分
    short_window: int     # 分
    threshold: float      # バーンレートの閾値（これを「超えたら」発火）
    severity: str = "page"


# ===========================================================================
# 演習1（★☆☆）: 可用性の合成
# ===========================================================================

def serial(*availabilities: float) -> float:
    """直列（すべてが動いていないと全体が止まる）の可用性 = 各可用性の積。

    - 引数がない、または 0〜1 の数値（bool は不可）でないものがあれば ValueError。

    >>> round(serial(0.999, 0.999), 6)
    0.998001
    """
    raise NotImplementedError("演習1: serial を実装してください")


def parallel(*availabilities: float) -> float:
    """並列（どれか 1 つが動いていれば全体が動く）の可用性 = 1 - Π(1 - aᵢ)。

    - 検証は serial と同じ。

    >>> round(parallel(0.99, 0.99), 6)
    0.9999
    """
    raise NotImplementedError("演習1: parallel を実装してください")


def quorum(k: int, availabilities: Sequence[float]) -> float:
    """n 個の部品のうち k 個以上が動いていれば全体が動く（多数決・クォーラム）ときの可用性。

    部品ごとに可用性が違ってよい。k は 1〜n の整数（そうでなければ ValueError）。
    1-of-n は並列、n-of-n は直列と一致する。

    >>> round(quorum(2, [0.99, 0.99, 0.99]), 6)   # 3 台の Raft クラスタ（過半数 = 2）
    0.999702

    ヒント: 「ここまでの部品のうち、ちょうど j 個が動いている確率」の表 dist[j] を、
    部品を 1 つずつ加えながら更新する（動的計画法）。最後に dist[k] 以降を足す。
    """
    raise NotImplementedError("演習1: quorum を実装してください")


def composite(structure: Any) -> float:
    """入れ子の構造から可用性を計算する。構造は次のいずれか:

    - 数値（0〜1）: 1 つの部品の可用性
    - ("serial", [構造, ...])
    - ("parallel", [構造, ...])
    - ("quorum", k, [構造, ...])
    それ以外（未知の種類、要素数の誤り、リストや文字列そのもの）は ValueError。

    >>> round(composite(("serial", [0.9999, ("parallel", [0.999, 0.999])])), 6)
    0.999899
    """
    raise NotImplementedError("演習1: composite を実装してください")


# ===========================================================================
# 演習2（★☆☆）: ダウンタイム・エラーバジェット・バーンレート
# ===========================================================================

def allowed_downtime(slo: float, period: timedelta = timedelta(days=30)) -> timedelta:
    """期間 period の中で、可用性 slo を守りながら許される停止時間 = period × (1 - slo)。

    slo は 0〜1（1.0 なら 0 秒）。範囲外は ValueError。

    >>> allowed_downtime(0.999)
    datetime.timedelta(seconds=2592)
    """
    raise NotImplementedError("演習2: allowed_downtime を実装してください")


def nines(availability: float) -> float:
    """「ナインの数」= -log10(1 - availability)。0.999 → 3.0、1.0 → math.inf。範囲外は ValueError。"""
    raise NotImplementedError("演習2: nines を実装してください")


def error_budget(slo: float, good: int, total: int) -> BudgetStatus:
    """リクエストベースの SLI でのエラーバジェットの状況を返す。

    - bad = total - good、allowed_bad = (1 - slo) × total、consumed = bad / allowed_bad、remaining = 1 - consumed
    - total が 0 なら consumed = 0.0、remaining = 1.0
    - slo は 0 < slo < 1（100% は予算がゼロなので不可）。0 <= good <= total でなければ ValueError。

    >>> error_budget(0.999, good=999_400, total=1_000_000).consumed   # doctest: +ELLIPSIS
    0.59999...
    """
    raise NotImplementedError("演習2: error_budget を実装してください")


def burn_rate(bad: int, total: int, slo: float) -> float:
    """バーンレート = (bad / total) / (1 - slo)。total が 0 なら 0.0。

    1.0 は「SLO の期間のちょうど終わりに予算を使い切る速さ」。14.4 なら 30 日の予算を 50 時間で使い切る。
    slo・bad・total の検証は error_budget と同じ（0 <= bad <= total）。
    """
    raise NotImplementedError("演習2: burn_rate を実装してください")


def window_sli(series: Sequence[tuple[int, int]], max_error_ratio: float) -> float:
    """ウィンドウベースの SLI: 「良い分」の割合を返す。

    series[i] = i 分目の (成功数, 総数)。その分のエラー率 (総数 - 成功数) / 総数 が max_error_ratio 以下なら
    良い分。総数が 0 の分も良い分として数える。series が空、または (成功数, 総数) が不正なら ValueError。
    """
    raise NotImplementedError("演習2: window_sli を実装してください")


# ===========================================================================
# 演習3（★★★）: 多窓・多バーンレートのアラート
# ===========================================================================

def threshold_for(budget_fraction: float, long_window: int, period: int = MINUTES_PER_30_DAYS) -> float:
    """「期間 period（分）のエラーバジェットの budget_fraction を、long_window 分で消費する」バーンレート。

    = budget_fraction × period / long_window
    例: 30 日の予算の 2% を 1 時間で → 0.02 × 43200 / 60 = 14.4
    """
    raise NotImplementedError("演習3: threshold_for を実装してください")


def multiwindow_rules(period: int = MINUTES_PER_30_DAYS) -> list[AlertRule]:
    """SRE ワークブックが推奨する 3 つのルールを、この順で返す（閾値は threshold_for で計算する）。

    | name | long_window | short_window | 予算の消費 | severity |
    |---|---|---|---|---|
    | "page-1h" | 60 | 5 | 2% | "page" |
    | "page-6h" | 360 | 30 | 5% | "page" |
    | "ticket-3d" | 4320 | 360 | 10% | "ticket" |
    """
    raise NotImplementedError("演習3: multiwindow_rules を実装してください")


def evaluate_alerts(
    series: Sequence[tuple[int, int]],
    slo: float,
    rules: Sequence[AlertRule],
) -> dict[str, list[tuple[int, int]]]:
    """1 分ごとの時系列に対して各ルールを評価し、{ルール名: 発火していた区間のリスト} を返す。

    - 時刻 t（0 始まりの分）での窓 w のバーンレート = 分 [t - w + 1, t] の合計の失敗数 / 合計の総数 / (1 - slo)。
      系列の先頭で窓がはみ出す部分は、ある分だけで計算する。総数が 0 ならバーンレート 0。
    - ルールが t で発火している ⇔ 長い窓のバーンレート > threshold かつ 短い窓のバーンレート > threshold
      （どちらも「超えたら」。等しいだけでは発火しない）
    - 発火している連続した分を、半開区間 (開始, 終了) にまとめる（終了の分は発火していない）。
      系列の最後まで発火していれば、終了は len(series)。
    - slo・(成功数, 総数) の検証は error_budget と同じ。窓の長さが 1 未満なら ValueError。

    短い窓の役割: 障害が終わった後、長い窓（1 時間）にはまだ失敗が残っているが、短い窓（5 分）は
    すぐに平常に戻るので、アラートが素早く止まる。テストで確かめてみよう。

    性能のヒント: 毎分・毎窓で合計を数え直すと O(系列の長さ × 窓の長さ) になり、3 日の窓では遅い。
    失敗数と総数の累積和（prefix sum）を先に作れば、どの窓の合計も引き算 1 回で求まる。
    """
    raise NotImplementedError("演習3: evaluate_alerts を実装してください")
