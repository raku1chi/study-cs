"""14.7 技術デューデリジェンスとM&A — 解答例: DDスコアカード

演習の仕様は exercises/dd_scorecard.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

SEVERITY_POINTS: dict[str, int] = {"critical": 40, "high": 20, "medium": 8, "low": 2}
GREEN_MIN = 75.0
AMBER_MIN = 50.0
RAG_ORDER = ("GREEN", "AMBER", "RED")


@dataclass(frozen=True)
class Finding:
    id: str
    area: str
    title: str
    severity: str
    confidence: float = 1.0
    red_flag: bool = False
    effort_days: float = 0.0


@dataclass(frozen=True)
class Rating:
    score: float
    rag: str
    coverage: float
    reasons: tuple[str, ...]


def _validate(findings: Iterable[Finding], areas: Iterable[str]) -> list[Finding]:
    known = set(areas)
    items = list(findings)
    for f in items:
        if f.area not in known:
            raise ValueError(f"{f.id}: 未知の領域です: {f.area}")
        if f.severity not in SEVERITY_POINTS:
            raise ValueError(f"{f.id}: 未知の深刻度です: {f.severity}")
        if not 0.0 <= f.confidence <= 1.0:
            raise ValueError(f"{f.id}: confidence は 0〜1: {f.confidence}")
        if f.effort_days < 0:
            raise ValueError(f"{f.id}: effort_days は 0 以上: {f.effort_days}")
    return items


def _penalty(f: Finding) -> float:
    # 確信度で割り引く: 「たぶん問題」は「確実に問題」ほどスコアを下げない
    return SEVERITY_POINTS[f.severity] * f.confidence


# ---------------------------------------------------------------------------
# 演習1: 領域ごとのスコア
# ---------------------------------------------------------------------------

def area_scores(findings: Iterable[Finding], areas: Iterable[str]) -> dict[str, float]:
    area_list = list(dict.fromkeys(areas))  # 順序を保ったまま重複を除く
    items = _validate(findings, area_list)
    scores = {a: 100.0 for a in area_list}
    for f in items:
        scores[f.area] -= _penalty(f)
    return {a: max(0.0, s) for a, s in scores.items()}


# ---------------------------------------------------------------------------
# 演習2: 総合評価
# ---------------------------------------------------------------------------

def _downgrade_green(rag: str) -> str:
    # 確証がないまま「GREEN（問題なし）」とは言わない
    return "AMBER" if rag == "GREEN" else rag


def overall_rating(
    findings: Iterable[Finding],
    weights: Mapping[str, float],
    reviewed: Iterable[str] | None = None,
    red_flag_min_confidence: float = 0.5,
    min_coverage: float = 0.8,
) -> Rating:
    if not weights:
        raise ValueError("weights が空です")
    for area, w in weights.items():
        if w <= 0:
            raise ValueError(f"重みは正の数: {area}={w}")
    reviewed_set = set(weights) if reviewed is None else set(reviewed)
    if not reviewed_set:
        raise ValueError("レビュー済みの領域がありません")
    unknown = reviewed_set - set(weights)
    if unknown:
        raise ValueError(f"weights にない領域です: {sorted(unknown)}")

    items = _validate(findings, weights)
    for f in items:
        if f.area not in reviewed_set:
            # 所見があるのに「未レビュー」は矛盾。入力の誤りを黙って通さない
            raise ValueError(f"{f.id}: 未レビューの領域 {f.area} に所見があります")

    scores = area_scores(items, weights)
    reviewed_weight = sum(weights[a] for a in reviewed_set)
    score = sum(weights[a] * scores[a] for a in reviewed_set) / reviewed_weight
    coverage = reviewed_weight / sum(weights.values())

    rag = "GREEN" if score >= GREEN_MIN else "AMBER" if score >= AMBER_MIN else "RED"
    reasons: list[str] = []
    # 1. 確度の高いレッドフラグは、スコアに関係なく RED（平均で隠れてはいけない）
    for f in items:
        if f.red_flag and f.confidence >= red_flag_min_confidence:
            reasons.append(f"red_flag:{f.id}")
            rag = "RED"
    # 2. 確度の低いレッドフラグ候補は、確認が済むまで GREEN にしない
    for f in items:
        if f.red_flag and f.confidence < red_flag_min_confidence:
            reasons.append(f"unconfirmed_red_flag:{f.id}")
            rag = _downgrade_green(rag)
    # 3. 見ていない領域が多いなら、「問題が見つからなかった」は「問題がない」ではない
    if coverage < min_coverage:
        reasons.append("low_coverage")
        rag = _downgrade_green(rag)
    return Rating(score=score, rag=rag, coverage=coverage, reasons=tuple(reasons))


# ---------------------------------------------------------------------------
# 演習3: 是正の優先順位
# ---------------------------------------------------------------------------

def remediation_plan(findings: Iterable[Finding], weights: Mapping[str, float]) -> list[Finding]:
    items = _validate(findings, weights)

    def key(f: Finding) -> tuple:
        priority = _penalty(f) * weights[f.area]
        # False < True なので「not red_flag」でレッドフラグが先頭に来る。
        # 優先度は降順にしたいので符号を反転。工数は小さい順（早く片付くものから）。
        return (not f.red_flag, -priority, f.effort_days, f.id)

    return sorted(items, key=key)
