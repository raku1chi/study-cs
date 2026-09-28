"""11.1 セキュリティの基本原則と脅威モデリング — 解答例（risk_register）

演習の仕様は exercises/risk_register.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Control:
    name: str
    effectiveness: float


@dataclass(frozen=True)
class Risk:
    id: str
    title: str
    owner: str
    likelihood: int
    impact: int
    controls: tuple[Control, ...] = ()


@dataclass(frozen=True)
class Assessment:
    risk_id: str
    title: str
    owner: str
    inherent_score: int
    residual_likelihood: int
    residual_score: int
    level: str
    needs_treatment: bool


# ---------------------------------------------------------------------------
# 演習1: 定量的リスク評価（ALE）
# ---------------------------------------------------------------------------

def single_loss_expectancy(asset_value: float, exposure_factor: float) -> float:
    if asset_value < 0:
        raise ValueError(f"資産価値は 0 以上です: {asset_value}")
    if not 0.0 <= exposure_factor <= 1.0:
        raise ValueError(f"exposure_factor は 0〜1 です: {exposure_factor}")
    return asset_value * exposure_factor


def annualized_loss_expectancy(sle: float, aro: float) -> float:
    if sle < 0 or aro < 0:
        raise ValueError("SLE と ARO は 0 以上です")
    return sle * aro


def control_net_benefit(ale_before: float, ale_after: float, annual_cost: float) -> float:
    # 対策の価値 = 減らせた年間予想損失 − 対策の年間コスト
    return (ale_before - ale_after) - annual_cost


# ---------------------------------------------------------------------------
# 演習2: 固有リスクと残存リスク
# ---------------------------------------------------------------------------

def _check_scale(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{name} は 1〜5 の整数です: {value!r}")


def combined_effectiveness(controls: tuple[Control, ...] | list[Control]) -> float:
    remaining = 1.0
    for c in controls:
        if not 0.0 <= c.effectiveness <= 1.0:
            raise ValueError(f"{c.name}: effectiveness は 0〜1 です: {c.effectiveness}")
        # 独立した対策を重ねると「すり抜ける確率」が掛け算で小さくなる
        remaining *= 1.0 - c.effectiveness
    return 1.0 - remaining


def inherent_score(risk: Risk) -> int:
    _check_scale("likelihood", risk.likelihood)
    _check_scale("impact", risk.impact)
    return risk.likelihood * risk.impact


def residual_likelihood(risk: Risk) -> int:
    _check_scale("likelihood", risk.likelihood)
    reduced = risk.likelihood * (1.0 - combined_effectiveness(risk.controls))
    # 効果 0.2 と 0.25 の対策を重ねると、5 × (1 − 0.4) は浮動小数点では
    # 3.0000000000000004 になり、そのまま切り上げると 4 になってしまう。
    # 先に丸めてから保守的に切り上げる（1 未満にはしない）
    return max(1, math.ceil(round(reduced, 9)))


def risk_level(score: int) -> str:
    if isinstance(score, bool) or not isinstance(score, int) or not 1 <= score <= 25:
        raise ValueError(f"スコアは 1〜25 の整数です: {score!r}")
    if score >= 17:
        return "重大"
    if score >= 10:
        return "高"
    if score >= 5:
        return "中"
    return "低"


def assess(risk: Risk, appetite: int = 9) -> Assessment:
    inherent = inherent_score(risk)
    r_likelihood = residual_likelihood(risk)
    residual = r_likelihood * risk.impact
    return Assessment(
        risk_id=risk.id,
        title=risk.title,
        owner=risk.owner,
        inherent_score=inherent,
        residual_likelihood=r_likelihood,
        residual_score=residual,
        level=risk_level(residual),
        needs_treatment=residual > appetite,
    )


# ---------------------------------------------------------------------------
# 演習3: ヒートマップとトップリスク報告
# ---------------------------------------------------------------------------

def heat_map(risks: list[Risk], residual: bool = True) -> dict[tuple[int, int], list[str]]:
    cells: dict[tuple[int, int], list[str]] = {}
    for r in risks:
        likelihood = residual_likelihood(r) if residual else r.likelihood
        _check_scale("impact", r.impact)
        cells.setdefault((likelihood, r.impact), []).append(r.id)
    return {key: sorted(ids) for key, ids in cells.items()}


def top_risks(risks: list[Risk], n: int = 5, appetite: int = 9) -> list[Assessment]:
    assessed = [assess(r, appetite) for r in risks]
    assessed.sort(key=lambda a: (-a.residual_score, -a.inherent_score, a.risk_id))
    return assessed[:n]


def render_report(risks: list[Risk], n: int = 5, appetite: int = 9) -> str:
    lines = [
        "| ID | リスク | オーナー | 固有 | 残存 | レベル | 対応 |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in top_risks(risks, n, appetite):
        action = "要対応" if a.needs_treatment else "受容可"
        lines.append(
            f"| {a.risk_id} | {a.title} | {a.owner} | {a.inherent_score} | "
            f"{a.residual_score} | {a.level} | {action} |"
        )
    return "\n".join(lines) + "\n"
