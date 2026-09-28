"""13.4 採用 — 解答例: 採用ファネルの計算

演習の仕様は exercises/hiring_funnel.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

EPS = 1e-9  # 浮動小数点の誤差の許容幅


@dataclass(frozen=True)
class Stage:
    name: str
    pass_rate: float
    duration_days: float = 0.0
    interview_hours: float = 0.0


@dataclass(frozen=True)
class Channel:
    name: str
    share: float
    fee_rate: float = 0.0
    fee_per_hire: float = 0.0
    fixed_cost: float = 0.0


def _check_stages(stages: list[Stage]) -> None:
    if not stages:
        raise ValueError("段階が 1 つもありません")
    names = [s.name for s in stages]
    if len(set(names)) != len(names):
        raise ValueError("段階の名前が重複しています")
    for s in stages:
        if not 0 < s.pass_rate <= 1:
            raise ValueError(f"{s.name}: 通過率は 0 より大きく 1 以下: {s.pass_rate}")
        if s.duration_days < 0 or s.interview_hours < 0:
            raise ValueError(f"{s.name}: 日数と時間は 0 以上")


# ---------------------------------------------------------------------------
# 演習1: 必要な母集団
# ---------------------------------------------------------------------------

def required_pipeline(target_hires: int, stages: list[Stage]) -> list[int]:
    if target_hires < 1:
        raise ValueError("採用目標は 1 人以上")
    _check_stages(stages)
    counts = [0] * len(stages)
    needed = target_hires  # 最後の段階を通過して「採用」になる必要がある人数
    # 後ろの段階から逆算する: その段階に入る人数 × 通過率 ≥ 次に必要な人数
    for i in range(len(stages) - 1, -1, -1):
        # 3 / 0.3 = 10.000000000000002 が 11 にならないよう、誤差を引いてから切り上げる
        needed = math.ceil(needed / stages[i].pass_rate - EPS)
        counts[i] = needed
    return counts


# ---------------------------------------------------------------------------
# 演習2: 充足までの期間
# ---------------------------------------------------------------------------

def expected_time_to_fill(target_hires: int, stages: list[Stage], weekly_applicants: float) -> float:
    if weekly_applicants <= 0:
        raise ValueError("週あたりの応募者数は正の値")
    top = required_pipeline(target_hires, stages)[0]
    # 必要な応募者がそろうまでの日数 + 最後の応募者が全段階を通過するまでの日数
    sourcing_days = top / weekly_applicants * 7
    return sourcing_days + sum(s.duration_days for s in stages)


# ---------------------------------------------------------------------------
# 演習3: 面接官の負荷
# ---------------------------------------------------------------------------

def interviewer_load(
    target_hires: int, stages: list[Stage], weeks: float, interviewers: dict[str, int]
) -> dict[str, float]:
    if weeks <= 0:
        raise ValueError("期間（週）は正の値")
    pipeline = required_pipeline(target_hires, stages)
    load: dict[str, float] = {}
    for stage, entrants in zip(stages, pipeline):
        if stage.interview_hours == 0:
            continue
        pool = interviewers.get(stage.name, 0)
        if pool < 1:
            raise ValueError(f"{stage.name}: 面接官の人数が指定されていません")
        # その段階の総時間を、期間と面接官の人数で割る（均等に分担できると仮定）
        load[stage.name] = entrants * stage.interview_hours / weeks / pool
    return load


# ---------------------------------------------------------------------------
# 演習4: 採用単価
# ---------------------------------------------------------------------------

def cost_per_hire(
    channels: list[Channel], hires: int, annual_salary: float, internal_cost: float = 0.0
) -> dict[str, float]:
    if hires < 1:
        raise ValueError("採用数は 1 人以上")
    if annual_salary < 0 or internal_cost < 0:
        raise ValueError("年収と社内コストは 0 以上")
    if not channels:
        raise ValueError("チャネルが 1 つもありません")
    for c in channels:
        if c.share < 0 or c.fee_rate < 0 or c.fee_per_hire < 0 or c.fixed_cost < 0:
            raise ValueError(f"{c.name}: 負の値は使えません")
    if abs(sum(c.share for c in channels) - 1.0) > EPS:
        raise ValueError("チャネルの割合の合計は 1 にしてください")
    if "合計" in {c.name for c in channels}:
        raise ValueError("チャネル名に '合計' は使えません")

    result: dict[str, float] = {}
    total = internal_cost
    for c in channels:
        channel_hires = hires * c.share
        variable = c.fee_rate * annual_salary + c.fee_per_hire  # 1 人ごとにかかる費用
        total += variable * channel_hires + c.fixed_cost
        if channel_hires > 0:
            result[c.name] = variable + c.fixed_cost / channel_hires
        else:
            # 固定費を払っているのに 1 人も採れていないチャネルは、単価が無限大
            result[c.name] = math.inf if c.fixed_cost > 0 else variable
    result["合計"] = total / hires
    return result
