"""11.5 セキュリティ運用とサプライチェーン — 解答例（vuln_triage）

演習の仕様は exercises/vuln_triage.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass

SEVERITY_BANDS = (
    (9.0, "critical"),
    (7.0, "high"),
    (4.0, "medium"),
    (0.1, "low"),
    (0.0, "none"),
)

# 優先度 → 対応期限（日数）。CISA の運用指令などを参考にした例（組織のポリシーとして決める）
SLA_DAYS = {"P1": 7, "P2": 30, "P3": 90, "P4": 180}


@dataclass(frozen=True)
class Finding:
    id: str  # CVE 番号など
    cvss: float  # CVSS 基本値（0.0〜10.0）
    epss: float  # 悪用される確率（0.0〜1.0）
    kev: bool  # CISA KEV（既知の悪用済み脆弱性）に載っているか
    internet_facing: bool  # インターネットに露出した資産か
    asset_criticality: int  # 資産の重要度（1〜5）


@dataclass(frozen=True)
class Triage:
    id: str
    severity: str
    priority: str
    due_days: int
    score: float
    rationale: tuple[str, ...]


# ---------------------------------------------------------------------------
# 演習1: CVSS の深刻度バンド
# ---------------------------------------------------------------------------

def severity_band(cvss: float) -> str:
    if not 0.0 <= cvss <= 10.0:
        raise ValueError(f"CVSS 基本値は 0.0〜10.0 です: {cvss}")
    for threshold, name in SEVERITY_BANDS:
        if cvss >= threshold:
            return name
    return "none"


# ---------------------------------------------------------------------------
# 演習2: 優先順位付け
# ---------------------------------------------------------------------------

def _validate(finding: Finding) -> None:
    if not 0.0 <= finding.cvss <= 10.0:
        raise ValueError(f"{finding.id}: CVSS は 0.0〜10.0 です")
    if not 0.0 <= finding.epss <= 1.0:
        raise ValueError(f"{finding.id}: EPSS は 0.0〜1.0 です")
    if isinstance(finding.asset_criticality, bool) or not 1 <= finding.asset_criticality <= 5:
        raise ValueError(f"{finding.id}: asset_criticality は 1〜5 です")


def prioritize(finding: Finding) -> Triage:
    """1 件の検出結果を評価して Triage を返す。

    優先度の決め方（この順で判定。上に当てはまれば下は見ない）:
      P1: KEV に載っている、または（CVSS >= 9.0 かつ インターネット露出）
          → 実際に悪用されている / されやすく、被害が大きい。最優先で直す
      P2: EPSS >= 0.5、または（CVSS >= 7.0 かつ インターネット露出）
      P3: CVSS >= 7.0、または EPSS >= 0.1
      P4: それ以外
    ただし資産重要度が 5 の場合、P4 は P3 に、P3 は P2 に引き上げる（1 段階厳しく）。
    """
    _validate(finding)
    reasons: list[str] = []
    if finding.kev:
        reasons.append("KEV（悪用が確認済み）")
    if finding.internet_facing:
        reasons.append("インターネットに露出")
    if finding.epss >= 0.5:
        reasons.append(f"EPSS が高い（{finding.epss:.2f}）")

    if finding.kev or (finding.cvss >= 9.0 and finding.internet_facing):
        priority = "P1"
    elif finding.epss >= 0.5 or (finding.cvss >= 7.0 and finding.internet_facing):
        priority = "P2"
    elif finding.cvss >= 7.0 or finding.epss >= 0.1:
        priority = "P3"
    else:
        priority = "P4"

    if finding.asset_criticality == 5 and priority in ("P3", "P4"):
        priority = {"P4": "P3", "P3": "P2"}[priority]
        reasons.append("重要資産のため 1 段階引き上げ")

    # 並べ替え用の連続スコア（優先度が同じものの中で順位を付ける）
    score = round(
        finding.cvss
        + 10.0 * finding.epss
        + (5.0 if finding.kev else 0.0)
        + (2.0 if finding.internet_facing else 0.0)
        + finding.asset_criticality * 0.5,
        4,
    )
    return Triage(
        id=finding.id,
        severity=severity_band(finding.cvss),
        priority=priority,
        due_days=SLA_DAYS[priority],
        score=score,
        rationale=tuple(reasons),
    )


# ---------------------------------------------------------------------------
# 演習3: 一覧の作成
# ---------------------------------------------------------------------------

def triage_all(findings: list[Finding]) -> list[Triage]:
    """すべての検出結果を評価し、優先度（P1 が先）→ スコアの降順 → ID 昇順で並べて返す。"""
    order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    triaged = [prioritize(f) for f in findings]
    triaged.sort(key=lambda t: (order[t.priority], -t.score, t.id))
    return triaged


def summarize(findings: list[Finding]) -> dict[str, int]:
    """優先度ごとの件数を返す（0 件の優先度も含めて P1〜P4 のキーを必ず持つ）。"""
    counts = {p: 0 for p in ("P1", "P2", "P3", "P4")}
    for t in triage_all(findings):
        counts[t.priority] += 1
    return counts
