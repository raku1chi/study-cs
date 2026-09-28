"""8.4 CI/CDとリリースエンジニアリング — 演習2: カナリア分析の自動判定

カナリアリリースでは、新しい版（canary）を一部のトラフィックだけに出し、同じ時間帯の
旧版（baseline）と指標を比べて、全体に広げてよいか（PROMOTE）、戻すべきか（ROLLBACK）、
まだ判断できないか（CONTINUE）を決めます。人が目でグラフを見比べる代わりに、
統計的な判定を自動化するのがこの演習です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.4

使う統計（[2.2 確率・統計と定量的思考] の知識で読めます）:
    - エラー率の比較: 2 つの比率の差の検定（z 検定、片側）
    - レイテンシの比較: p95（95 パーセンタイル）の比

制約: statistics モジュールや外部ライブラリの検定関数は使わず、math.erfc などで計算すること
      （テストでは答え合わせに statistics.NormalDist を使っています）。
"""
from __future__ import annotations

import math  # noqa: F401  実装で使います
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class GroupMetrics:
    """一方のグループ（baseline または canary）の観測値。"""

    requests: int  # リクエスト数
    errors: int  # そのうちエラー（5xx など）の数
    latencies_ms: Sequence[float]  # レイテンシの標本（ミリ秒）


@dataclass(frozen=True)
class Verdict:
    decision: str  # "PROMOTE" / "ROLLBACK" / "CONTINUE"
    reasons: tuple[str, ...]  # 判定の理由（人が読む説明。CONTINUE・ROLLBACK では 1 つ以上）
    baseline_error_rate: Optional[float] = None
    canary_error_rate: Optional[float] = None
    p_value: Optional[float] = None
    baseline_p95: Optional[float] = None
    canary_p95: Optional[float] = None


def percentile(values: Sequence[float], p: float) -> float:
    """最近傍順位法（nearest-rank method）による p パーセンタイル（0 < p <= 100）。

    値を昇順に並べ、順位 r = ceil(p / 100 × n) 番目（1 始まり）の値を返す。
    values が空、または p が範囲外なら ValueError。

    >>> percentile(list(range(1, 101)), 95)
    95
    >>> percentile([10, 30, 20], 50)
    20
    """
    raise NotImplementedError("演習2: percentile を実装してください")


def two_proportion_z_test(
    baseline_errors: int, baseline_requests: int, canary_errors: int, canary_requests: int
) -> tuple[float, float]:
    """「canary のエラー率は baseline より高い」かを調べる片側の 2 標本比率の z 検定。

    p_b = baseline_errors / baseline_requests、p_c = canary_errors / canary_requests、
    プールした比率 p = (baseline_errors + canary_errors) / (baseline_requests + canary_requests)、
    標準誤差 se = sqrt(p × (1 - p) × (1 / baseline_requests + 1 / canary_requests)) として、
        z = (p_c - p_b) / se
        p 値 = P(Z >= z) = 0.5 × erfc(z / √2)     （Z は標準正規分布に従う）
    を (z, p 値) で返す。se が 0（両方ともエラーが 0 件、または全件エラー）なら (0.0, 0.5)。
    リクエスト数が 0 以下、エラー数が負またはリクエスト数より多いときは ValueError。
    """
    raise NotImplementedError("演習2: two_proportion_z_test を実装してください")


def analyze(
    baseline: GroupMetrics,
    canary: GroupMetrics,
    *,
    min_requests: int = 1000,
    min_latency_samples: int = 200,
    alpha: float = 0.01,
    min_effect: float = 0.001,
    max_p95_ratio: float = 1.2,
) -> Verdict:
    """baseline と canary を比べて判定する。

    1. 入力の検証: requests・errors が負、errors > requests、負のレイテンシは ValueError。
    2. 標本が足りない → CONTINUE:
         どちらかの requests が min_requests 未満、または
         どちらかの latencies_ms の個数が min_latency_samples 未満。
       （理由に何が足りないかを書く。このときエラー率などの数値は None のままでよい）
    3. 判定のための数値を計算して Verdict に入れる:
         エラー率（errors / requests）、two_proportion_z_test の p 値、それぞれの p95。
    4. 次のどちらかなら ROLLBACK（両方なら理由を 2 つ）:
         - エラー率の悪化: p 値 < alpha かつ（canary のエラー率 − baseline のエラー率）>= min_effect
           （統計的に有意で、かつ実務上意味のある大きさの差。大量のトラフィックでは、ごく小さな
             差でも「有意」になるので、効果量の下限と組み合わせる）
         - レイテンシの悪化: canary の p95 / baseline の p95 > max_p95_ratio
           （baseline の p95 が 0 のときは、canary の p95 も 0 なら比 1.0、そうでなければ無限大とみなす）
    5. それ以外 → PROMOTE（理由は空でよい）
    """
    raise NotImplementedError("演習2: analyze を実装してください")
