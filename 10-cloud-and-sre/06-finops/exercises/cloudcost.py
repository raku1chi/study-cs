"""10.6 クラウドコスト管理（FinOps）— 演習: クラウド費用の計算

クラウドの請求を「なぜこの金額になるのか」から理解し、最適化の判断を数字で下せるように
なるための計算を実装します。金額や単価はすべて説明用の架空の数値です（実際の料金は
事業者・リージョン・時期によって異なるので、必ず公式の料金表で確認してください）。

- 演習1（★☆☆）: tiered_cost — データ転送などの段階的な料金
- 演習2（★★☆）: expected_runtime, spot_vs_on_demand — スポットの中断とやり直しを考慮した費用
- 演習3（★★☆）: allocate, unit_cost — 共有費用の配賦（合計が請求額と一致する丸め）と単位あたりの費用
- 演習4（★★☆）: rightsize, monthly_savings — 使用率の分布に基づく適正化
- 演習5（★★★）: breakeven_utilization, commitment_savings, commitment_cost,
                  coverage_and_utilization, optimal_commitment — 確約利用割引の損益分岐と、確約する量の決定
（演習6 は tag_audit.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.6
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

HOURS_PER_MONTH = 730  # 8,760 時間 ÷ 12。クラウドの月額の見積もりでよく使われる慣習


@dataclass(frozen=True)
class InstanceType:
    name: str
    vcpu: int
    memory_gib: float
    hourly: float          # 1 時間あたりの料金（円。この演習の数値は架空）


def nearest_rank(values: Sequence[float], p: float) -> float:
    """最近順位法のパーセンタイル（昇順で ceil(p/100 × n) 番目）。"""
    if not values:
        raise ValueError("values が空です")
    if not 0 < p <= 100:
        raise ValueError(f"p は 0 < p <= 100: {p}")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


# ===========================================================================
# 演習1（★☆☆）: 段階的な料金
# ===========================================================================

def tiered_cost(quantity: float, tiers: Sequence[tuple[float, float]]) -> float:
    """段階的な料金（使うほど単価が下がる）の合計を返す。

    tiers は [(この段の上限（累計）, 単価), ...] で、最後の段の上限は math.inf。
    例: [(10_000, 15.0), (50_000, 12.0), (math.inf, 10.0)] は
        最初の 10,000 まで 15 円、次の 40,000（50,000 まで）は 12 円、それを超えた分は 10 円。
    - 各段に入る量にだけ、その段の単価を掛ける（全量に最後の段の単価を掛けるのではない）。
    - quantity が負、tiers が空、最後の上限が inf でない、上限が正の狭義単調増加でなければ ValueError。

    >>> tiered_cost(30_000, [(10_000, 15.0), (50_000, 12.0), (math.inf, 10.0)])
    390000.0
    """
    raise NotImplementedError("演習1: tiered_cost を実装してください")


# ===========================================================================
# 演習2（★★☆）: スポットの中断を考慮した費用
# ===========================================================================

def expected_runtime(job_hours: float, interruptions_per_hour: float, restart_overhead_hours: float = 0.0,
                     checkpoint_hours: float | None = None) -> float:
    """中断されうる環境で、job_hours 分の仕事を終えるまでの期待時間（時間）を返す。

    モデル: 中断は平均 λ = interruptions_per_hour 回/時間のポアソン過程で起きる。中断されると、
    直前のチェックポイント（なければ最初）からやり直し、再開のたびに restart_overhead_hours（R）かかる。
    - 長さ w の区間を中断なしで終えるまでの期待時間は (e^{λw} − 1)(1/λ + R)。
    - checkpoint_hours（C）が指定されたら、仕事を長さ C の区間（最後は端数の区間）に分け、
      区間ごとの期待時間を足す（チェックポイントを書く時間は無視する）。
    - λ = 0 なら job_hours。
    - 負の値、または C <= 0 なら ValueError。

    ヒント: e^x − 1 は math.expm1(x) で精度よく計算できる。
    導出の考え方: 1 回の試行が成功する（長さ w の間に中断が起きない）確率は e^{−λw}。失敗の回数は
    幾何分布に従い、期待値は e^{λw} − 1。失敗 1 回あたりに失う時間の期待値と成功した試行の w を合わせると、上の式になる。
    """
    raise NotImplementedError("演習2: expected_runtime を実装してください")


def spot_vs_on_demand(job_hours: float, on_demand_hourly: float, spot_hourly: float,
                      interruptions_per_hour: float, restart_overhead_hours: float = 0.0,
                      checkpoint_hours: float | None = None) -> tuple[float, float]:
    """(スポットでの期待費用, オンデマンドでの費用) を返す。

    スポット = expected_runtime(...) × spot_hourly（やり直しと再開の時間にも料金がかかる）、
    オンデマンド = job_hours × on_demand_hourly（中断されない）。単価が負なら ValueError。
    """
    raise NotImplementedError("演習2: spot_vs_on_demand を実装してください")


# ===========================================================================
# 演習3（★★☆）: 共有費用の配賦と単位あたりの費用
# ===========================================================================

def allocate(total_yen: int, usage: Mapping[str, float], method: str = "proportional",
             weights: Mapping[str, float] | None = None) -> dict[str, int]:
    """共有の費用 total_yen（円、整数）をテナントに配賦する。返り値の合計は必ず total_yen に一致させる。

    method:
    - "proportional": usage（CPU 時間やリクエスト数など）に比例
    - "even": 均等
    - "weighted": weights（契約の比率や人数など）に比例。weights のキーは usage のキーと同じであること
    配分の基準の合計を D、テナント i の基準を bᵢ として、正確な値 total × bᵢ / D を
    **最大剰余法** で整数にする: まず全員に切り捨てた値を配り、残った円を、端数（正確な値 − 切り捨てた値）の
    大きい順に 1 円ずつ配る（端数が同じならテナント名の昇順）。キーは名前の昇順の dict で返す。

    次の場合は ValueError: total_yen が負、usage が空、未知の method、weighted で weights が不足・過剰、
    基準に負の値がある、基準の合計が 0。

    >>> allocate(100, {"a": 1, "b": 2, "c": 4})
    {'a': 14, 'b': 29, 'c': 57}

    なぜ最大剰余法か: それぞれを四捨五入すると、合計が請求額と数円ずれる。数円でも、
    配賦の合計が請求額と一致しないと、経理の突き合わせで説明を求められる。
    """
    raise NotImplementedError("演習3: allocate を実装してください")


def unit_cost(total_cost: float, units: float) -> float:
    """単位あたりの費用（例: 注文 1 件あたり、顧客 1 社あたり）= total_cost / units。units <= 0 は ValueError。"""
    raise NotImplementedError("演習3: unit_cost を実装してください")


# ===========================================================================
# 演習4（★★☆）: 適正化（ライトサイジング）
# ===========================================================================

def rightsize(cpu_used: Sequence[float], memory_used_gib: Sequence[float], catalog: Sequence[InstanceType],
              headroom: float = 0.2, percentile: float = 95) -> InstanceType | None:
    """使用量の時系列から、要件を満たす最も安いインスタンスタイプを返す（なければ None）。

    - 必要な vCPU = nearest_rank(cpu_used, percentile) × (1 + headroom)
      （CPU は一時的に足りなくても遅くなるだけなので、分位点で見る）
    - 必要なメモリ = max(memory_used_gib) × (1 + headroom)
      （メモリは一瞬でも足りなければプロセスが強制終了される（OOM）ので、最大値で見る）
    - vcpu >= 必要な vCPU かつ memory_gib >= 必要なメモリ のタイプのうち、hourly が最小のもの。
      同額なら vcpu の小さいもの、次に memory_gib の小さいもの、次に名前の昇順。
    - 系列が空、または headroom が負なら ValueError。
    """
    raise NotImplementedError("演習4: rightsize を実装してください")


def monthly_savings(current: InstanceType, recommended: InstanceType, count: int = 1,
                    hours: float = HOURS_PER_MONTH) -> float:
    """(current.hourly − recommended.hourly) × count × hours。"""
    raise NotImplementedError("演習4: monthly_savings を実装してください")


# ===========================================================================
# 演習5（★★★）: 確約利用割引（損益分岐と、確約する量の決定）
# ===========================================================================

def breakeven_utilization(on_demand_hourly: float, committed_hourly: float) -> float:
    """確約（リザーブドインスタンスや Savings Plans など）がオンデマンドと同額になる稼働率を返す。

    確約は使っても使わなくても毎時間払い、オンデマンドは使った時間だけ払う。
    稼働率 u で u × on_demand_hourly = committed_hourly となる u = committed_hourly / on_demand_hourly。
    on_demand_hourly <= 0 または committed_hourly < 0 なら ValueError。

    >>> breakeven_utilization(100, 62)   # 38% 割引なら、稼働率 62% を下回ると損
    0.62
    """
    raise NotImplementedError("演習5: breakeven_utilization を実装してください")


def commitment_savings(on_demand_hourly: float, committed_hourly: float, utilization: float,
                       hours: float = HOURS_PER_MONTH) -> float:
    """稼働率 utilization のときの、確約による節約額 = (utilization × on_demand_hourly − committed_hourly) × hours。

    負なら損。utilization が 0〜1 の外なら ValueError（単価の検証は breakeven_utilization と同じ）。
    """
    raise NotImplementedError("演習5: commitment_savings を実装してください")


def commitment_cost(hourly_usage: Sequence[float], level: float, on_demand_rate: float, commit_rate: float) -> float:
    """1 時間ごとの使用量に対して、level 単位を確約したときの費用の合計。

    各時間の費用 = level × commit_rate（使わなくても払う）+ max(0, 使用量 − level) × on_demand_rate
    level・単価が負なら ValueError。
    """
    raise NotImplementedError("演習5: commitment_cost を実装してください")


def coverage_and_utilization(hourly_usage: Sequence[float], level: float) -> tuple[float, float]:
    """FinOps でよく使う 2 つの指標 (カバー率, 利用率) を返す。

    - カバー率 = Σ min(使用量, level) / Σ 使用量（使用量のうち確約でまかなえた割合。合計 0 なら 0.0）
    - 利用率 = Σ min(使用量, level) / (level × 時間数)（確約のうち実際に使われた割合。level が 0 なら 0.0）
    hourly_usage が空なら ValueError。
    """
    raise NotImplementedError("演習5: coverage_and_utilization を実装してください")


def optimal_commitment(hourly_usage: Sequence[float], on_demand_rate: float, commit_rate: float,
                       step: float = 1.0) -> tuple[float, float]:
    """費用が最小になる確約の量と、確約しない場合からの節約額を (level, 節約額) で返す。

    候補は 0, step, 2×step, … で max(hourly_usage) 以下のもの。commitment_cost が最小のものを選び、
    同じ費用なら小さい方（縛りが少ない方）を選ぶ（比較には 1e-9 程度の許容誤差を使ってよい）。
    hourly_usage が空、または step <= 0 なら ValueError。

    考えてみよう: 最適な水準では「使用量がその水準を超える時間の割合」が commit_rate / on_demand_rate を
    またぐ。なぜか（確約を 1 単位増やしたときの損得を考える）。利用率 100% を目指すのが正しくない理由も分かる。
    """
    raise NotImplementedError("演習5: optimal_commitment を実装してください")
