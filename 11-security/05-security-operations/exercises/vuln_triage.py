"""11.5 セキュリティ運用とサプライチェーン — 演習（vuln_triage）

脆弱性スキャンの結果を「どれから直すか」で並べ替えるトリアージツールを作ります。
CVSS（深刻度）だけで並べると数が多すぎて回りません。実際に悪用されているか（KEV）、
悪用されやすいか（EPSS）、インターネットに露出しているか、資産の重要度、を組み合わせて
優先度と対応期限（SLA）を決めます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.5
    python3 tools/check.py -v 11.5

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_vuln_triage

用語:
    CVSS 基本値  脆弱性そのものの深刻度（0.0〜10.0）。「どれだけ危ないか」
    EPSS         今後 30 日以内に悪用される確率（0.0〜1.0）。「悪用されそうか」
    KEV          CISA の「悪用が確認された脆弱性」カタログに載っているか。「もう悪用されているか」
    これらは 2026 年時点で広く使われている指標です。数値の意味と最新版は一次情報で確認してください。
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

# 優先度 → 対応期限（日数）。組織のポリシーとして決める例
SLA_DAYS = {"P1": 7, "P2": 30, "P3": 90, "P4": 180}


@dataclass(frozen=True)
class Finding:
    id: str  # CVE 番号など
    cvss: float  # CVSS 基本値（0.0〜10.0）
    epss: float  # 悪用される確率（0.0〜1.0）
    kev: bool  # CISA KEV に載っているか
    internet_facing: bool  # インターネットに露出した資産か
    asset_criticality: int  # 資産の重要度（1〜5）


@dataclass(frozen=True)
class Triage:
    id: str
    severity: str
    priority: str  # "P1"〜"P4"
    due_days: int
    score: float  # 同じ優先度の中で並べるための連続スコア
    rationale: tuple[str, ...]  # 優先度の理由（表示用）


# ---------------------------------------------------------------------------
# 演習1（★☆☆相当）: CVSS の深刻度バンド
# ---------------------------------------------------------------------------

def severity_band(cvss: float) -> str:
    """CVSS 基本値を深刻度に分類する（CVSS v3.1 の区分）。

    0.0="none", 0.1〜3.9="low", 4.0〜6.9="medium", 7.0〜8.9="high", 9.0〜10.0="critical"。
    0.0〜10.0 の範囲外は ValueError。
    """
    raise NotImplementedError("演習1: severity_band を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆相当）: 優先順位付け
# ---------------------------------------------------------------------------

def prioritize(finding: Finding) -> Triage:
    """1 件の検出結果を評価して Triage を返す。

    まず値を検証する（cvss は 0〜10、epss は 0〜1、asset_criticality は 1〜5 の int。
    どれか外れていれば ValueError）。

    優先度（この順に判定し、当てはまったら以降は見ない）:
      P1: kev が True、または（cvss >= 9.0 かつ internet_facing）
      P2: epss >= 0.5、または（cvss >= 7.0 かつ internet_facing）
      P3: cvss >= 7.0、または epss >= 0.1
      P4: それ以外
    その後、asset_criticality == 5 なら、P4 を P3 に、P3 を P2 に引き上げる（P1・P2 はそのまま）。

    due_days は SLA_DAYS[priority]。severity は severity_band(cvss)。
    score は「同じ優先度の中で順位を付ける」ための連続値で、次のように決める（丸めは小数第 4 位）:
        cvss + 10*epss + (kev なら 5) + (internet_facing なら 2) + asset_criticality*0.5
    rationale には、当てはまった理由（KEV・露出・EPSS が高い・重要資産で引き上げ など）を入れる
    （表示用。テストは KEV と引き上げの文言だけを確認します）。
    """
    raise NotImplementedError("演習2: prioritize を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆相当）: 一覧の作成
# ---------------------------------------------------------------------------

def triage_all(findings: list[Finding]) -> list[Triage]:
    """すべて評価し、優先度（P1 が先）→ score の降順 → id の昇順で並べて返す。"""
    raise NotImplementedError("演習3: triage_all を実装してください")


def summarize(findings: list[Finding]) -> dict[str, int]:
    """優先度ごとの件数を返す。0 件でも P1〜P4 のキーを必ず持つ。"""
    raise NotImplementedError("演習3: summarize を実装してください")
