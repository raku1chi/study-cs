"""10.6 クラウドコスト管理（FinOps）— 演習（クラウド費用の計算）の解答例

演習の仕様は exercises/cloudcost.py の docstring を参照してください。
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
# 演習1: 段階的な料金
# ===========================================================================

def tiered_cost(quantity: float, tiers: Sequence[tuple[float, float]]) -> float:
    if quantity < 0:
        raise ValueError("quantity は 0 以上")
    if not tiers or not math.isinf(tiers[-1][0]):
        raise ValueError("最後の段の上限は math.inf にしてください")
    bounds = [upper for upper, _ in tiers]
    if any(b <= a for a, b in zip(bounds, bounds[1:])) or bounds[0] <= 0:
        raise ValueError("段の上限は正の狭義単調増加にしてください")
    cost, lower = 0.0, 0.0
    for upper, price in tiers:
        if quantity <= lower:
            break
        # この段に入る量だけに、この段の単価を掛ける（全体に最後の段の単価を掛けるのではない）
        cost += (min(quantity, upper) - lower) * price
        lower = upper
    return cost


# ===========================================================================
# 演習2: 確約利用割引の損益分岐
# ===========================================================================

def breakeven_utilization(on_demand_hourly: float, committed_hourly: float) -> float:
    if on_demand_hourly <= 0 or committed_hourly < 0:
        raise ValueError("単価が不正です")
    # 確約は使っても使わなくても毎時間払う。オンデマンドは使った時間だけ払う。
    # 稼働率 u で u × オンデマンド = 確約 となる u が損益分岐点
    return committed_hourly / on_demand_hourly


def commitment_savings(on_demand_hourly: float, committed_hourly: float, utilization: float,
                       hours: float = HOURS_PER_MONTH) -> float:
    if not 0 <= utilization <= 1:
        raise ValueError("utilization は 0〜1")
    breakeven_utilization(on_demand_hourly, committed_hourly)  # 単価の検証
    return (utilization * on_demand_hourly - committed_hourly) * hours


# ===========================================================================
# 演習3: スポットの中断を考慮した費用
# ===========================================================================

def expected_runtime(job_hours: float, interruptions_per_hour: float, restart_overhead_hours: float = 0.0,
                     checkpoint_hours: float | None = None) -> float:
    if job_hours < 0 or interruptions_per_hour < 0 or restart_overhead_hours < 0:
        raise ValueError("負の値は指定できません")
    if checkpoint_hours is not None and checkpoint_hours <= 0:
        raise ValueError("checkpoint_hours は正の数")
    lam = interruptions_per_hour
    if lam == 0:
        return job_hours

    def segment(work: float) -> float:
        # 中断が平均 λ 回/時間のポアソン過程で起き、中断されたら区間の最初からやり直すとき、
        # 長さ w の仕事を終えるまでの期待時間は (e^{λw} − 1)(1/λ + R)（R は再開のたびのオーバーヘッド）
        return math.expm1(lam * work) * (1 / lam + restart_overhead_hours)

    if checkpoint_hours is None:
        return segment(job_hours)
    full, rest = divmod(job_hours, checkpoint_hours)
    total = int(full) * segment(checkpoint_hours)
    if rest > 1e-12:
        total += segment(rest)
    return total


def spot_vs_on_demand(job_hours: float, on_demand_hourly: float, spot_hourly: float,
                      interruptions_per_hour: float, restart_overhead_hours: float = 0.0,
                      checkpoint_hours: float | None = None) -> tuple[float, float]:
    if on_demand_hourly < 0 or spot_hourly < 0:
        raise ValueError("単価が不正です")
    runtime = expected_runtime(job_hours, interruptions_per_hour, restart_overhead_hours, checkpoint_hours)
    # スポットでは、やり直した時間や再開の準備の時間にも料金がかかる
    return runtime * spot_hourly, job_hours * on_demand_hourly


# ===========================================================================
# 演習4: 共有費用の配賦と単位あたりの費用
# ===========================================================================

def allocate(total_yen: int, usage: Mapping[str, float], method: str = "proportional",
             weights: Mapping[str, float] | None = None) -> dict[str, int]:
    if total_yen < 0 or not usage:
        raise ValueError("total_yen は 0 以上、usage は空でないこと")
    names = sorted(usage)
    if method == "proportional":
        basis = {n: float(usage[n]) for n in names}
    elif method == "even":
        basis = {n: 1.0 for n in names}
    elif method == "weighted":
        if weights is None or set(weights) != set(names):
            raise ValueError("weighted には、すべてのテナントの重みが必要です")
        basis = {n: float(weights[n]) for n in names}
    else:
        raise ValueError(f"未知の配賦方法です: {method!r}")
    if any(v < 0 for v in basis.values()):
        raise ValueError("使用量・重みは 0 以上")
    denom = sum(basis.values())
    if denom == 0:
        raise ValueError("使用量（重み）の合計が 0 では比例配分できません")
    # 最大剰余法: まず切り捨てで配り、端数の大きい順に 1 円ずつ配る。合計が必ず total_yen に一致する
    exact = {n: total_yen * basis[n] / denom for n in names}
    result = {n: math.floor(exact[n]) for n in names}
    leftover = total_yen - sum(result.values())
    by_remainder = sorted(names, key=lambda n: (-(exact[n] - result[n]), n))
    for n in by_remainder[:leftover]:
        result[n] += 1
    return result


def unit_cost(total_cost: float, units: float) -> float:
    if units <= 0:
        raise ValueError("units は正の数")
    return total_cost / units


# ===========================================================================
# 演習5: 適正化（ライトサイジング）
# ===========================================================================

def rightsize(cpu_used: Sequence[float], memory_used_gib: Sequence[float], catalog: Sequence[InstanceType],
              headroom: float = 0.2, percentile: float = 95) -> InstanceType | None:
    if headroom < 0:
        raise ValueError("headroom は 0 以上")
    if not cpu_used or not memory_used_gib:
        raise ValueError("使用量の系列が空です")
    # CPU は一時的に足りなくても遅くなるだけなので分位点で見る。メモリは足りなければプロセスが
    # 強制終了されるので、最大値で見る
    need_cpu = nearest_rank(cpu_used, percentile) * (1 + headroom)
    need_mem = max(memory_used_gib) * (1 + headroom)
    fits = [t for t in catalog if t.vcpu >= need_cpu and t.memory_gib >= need_mem]
    if not fits:
        return None
    return min(fits, key=lambda t: (t.hourly, t.vcpu, t.memory_gib, t.name))


def monthly_savings(current: InstanceType, recommended: InstanceType, count: int = 1,
                    hours: float = HOURS_PER_MONTH) -> float:
    return (current.hourly - recommended.hourly) * count * hours


# ===========================================================================
# 演習6: 確約の量を決める
# ===========================================================================

def commitment_cost(hourly_usage: Sequence[float], level: float, on_demand_rate: float, commit_rate: float) -> float:
    if level < 0 or on_demand_rate < 0 or commit_rate < 0:
        raise ValueError("負の値は指定できません")
    # 確約した量は使わなくても毎時間払う。超えた分はオンデマンドの単価で払う
    return sum(level * commit_rate + max(0.0, u - level) * on_demand_rate for u in hourly_usage)


def coverage_and_utilization(hourly_usage: Sequence[float], level: float) -> tuple[float, float]:
    if not hourly_usage:
        raise ValueError("hourly_usage が空です")
    covered = sum(min(u, level) for u in hourly_usage)
    total = sum(hourly_usage)
    coverage = covered / total if total else 0.0
    utilization = covered / (level * len(hourly_usage)) if level > 0 else 0.0
    return coverage, utilization


def optimal_commitment(hourly_usage: Sequence[float], on_demand_rate: float, commit_rate: float,
                       step: float = 1.0) -> tuple[float, float]:
    if not hourly_usage:
        raise ValueError("hourly_usage が空です")
    if step <= 0:
        raise ValueError("step は正の数")
    baseline = commitment_cost(hourly_usage, 0.0, on_demand_rate, commit_rate)
    best_level, best_cost = 0.0, baseline
    k = 1
    while k * step <= max(hourly_usage) + 1e-9:
        level = k * step
        cost = commitment_cost(hourly_usage, level, on_demand_rate, commit_rate)
        if cost < best_cost - 1e-9:  # 同じ費用なら小さい確約（縛りが少ない）を選ぶ
            best_level, best_cost = level, cost
        k += 1
    return best_level, baseline - best_cost
