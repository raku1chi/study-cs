"""14.7 技術デューデリジェンスとM&A — 演習: DDスコアカード

技術デューデリジェンス（DD）では、数週間で数十件の所見（finding）が集まります。
最後に必要なのは「総合評価は RED / AMBER / GREEN のどれか」「何から直すべきか」を、
投資委員会や買収チームに一貫した基準で説明することです。この演習では、所見を
領域の重み・深刻度・確信度で集計し、レッドフラグの扱いとレビュー範囲（カバレッジ）を
考慮した総合評価と、是正の優先順位リストを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.7          # 合格数を表示
    python3 tools/check.py -v 14.7       # 各テストの結果を詳しく表示

このスコアカードの考え方（本文 3.3 節）:
    - 平均点は便利だが、致命的な問題を「薄める」。確度の高いレッドフラグは平均に関係なく RED。
    - 「問題が見つからなかった」と「問題がない」は違う。レビューしていない領域が多ければ
      GREEN とは言わない。
    - 所見の確信度（confidence）で減点を割り引く。ただし確度の低いレッドフラグ候補も、
      確認が済むまでは GREEN を出さない理由になる。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

# 深刻度ごとの減点（1 件・確信度 1.0 のとき）
SEVERITY_POINTS: dict[str, int] = {"critical": 40, "high": 20, "medium": 8, "low": 2}
# 総合スコアのしきい値: 75 以上 GREEN、50 以上 AMBER、それ未満 RED
GREEN_MIN = 75.0
AMBER_MIN = 50.0


@dataclass(frozen=True)
class Finding:
    """DD の所見 1 件。

    area:        領域（"security", "ip_oss" など。weights のキーのどれか）
    severity:    "critical" / "high" / "medium" / "low"
    confidence:  0.0〜1.0。所見が事実である（影響の見積もりが正しい）確からしさ
    red_flag:    取引の前提を揺るがしうる問題か（権利の欠落、未公表の侵害事故など）
    effort_days: 是正に必要な工数の見積もり（人日）
    """

    id: str
    area: str
    title: str
    severity: str
    confidence: float = 1.0
    red_flag: bool = False
    effort_days: float = 0.0


@dataclass(frozen=True)
class Rating:
    """総合評価。

    score:    レビュー済み領域のスコアの加重平均（0〜100）
    rag:      "GREEN" / "AMBER" / "RED"
    coverage: レビュー済み領域の重みの合計 ÷ 全領域の重みの合計（0〜1）
    reasons:  スコア以外の判定理由のコード（下記 overall_rating を参照）
    """

    score: float
    rag: str
    coverage: float
    reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 領域ごとのスコア
# ---------------------------------------------------------------------------

def area_scores(findings: Iterable[Finding], areas: Iterable[str]) -> dict[str, float]:
    """領域ごとのスコア（0〜100）を返す。

    - 各領域は 100 点から始まり、所見 1 件ごとに
      SEVERITY_POINTS[severity] × confidence を引く。0 未満にはしない。
    - 戻り値のキーは areas のすべて（所見のない領域は 100.0）。
    - 次の場合は ValueError:
        所見の area が areas に含まれない / severity が未知 /
        confidence が 0〜1 の範囲外 / effort_days が負

    例: security に high（確信度 1.0）と medium（確信度 0.5）の所見
        → 100 − 20 − 4 = 76.0
    """
    raise NotImplementedError("演習1: area_scores を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 総合評価
# ---------------------------------------------------------------------------

def overall_rating(
    findings: Iterable[Finding],
    weights: Mapping[str, float],
    reviewed: Iterable[str] | None = None,
    red_flag_min_confidence: float = 0.5,
    min_coverage: float = 0.8,
) -> Rating:
    """所見を総合評価にまとめる。

    入力:
        weights:  {領域: 重み}。これが領域の一覧。重みは正の数。
        reviewed: レビューを実施した領域。None ならすべての領域をレビュー済みとみなす。

    手順:
        1. score = レビュー済み領域の area_scores の加重平均（重みは weights）。
        2. coverage = レビュー済み領域の重みの合計 ÷ 全領域の重みの合計。
        3. score が GREEN_MIN 以上なら "GREEN"、AMBER_MIN 以上なら "AMBER"、それ未満は "RED"。
        4. red_flag=True かつ confidence >= red_flag_min_confidence の所見があれば、
           score に関係なく "RED"。reasons に "red_flag:<id>" を追加（所見の入力順）。
        5. red_flag=True だが confidence が red_flag_min_confidence 未満の所見は
           "unconfirmed_red_flag:<id>" を reasons に追加し、"GREEN" なら "AMBER" に下げる。
        6. coverage < min_coverage なら "low_coverage" を reasons に追加し、
           "GREEN" なら "AMBER" に下げる。
        reasons の並びは「4 のすべて → 5 のすべて → 6」の順。該当がなければ空のタプル。

    ValueError になる場合:
        weights が空 / 重みが 0 以下 / reviewed に weights にない領域がある /
        reviewed が空 / 未レビューの領域に所見がある / area_scores と同じ検証エラー
    """
    raise NotImplementedError("演習2: overall_rating を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: 是正の優先順位
# ---------------------------------------------------------------------------

def remediation_plan(findings: Iterable[Finding], weights: Mapping[str, float]) -> list[Finding]:
    """是正の優先順位の順に並べた所見のリストを返す（入力は変更しない）。

    並べ方:
        1. red_flag=True の所見を先頭に（確信度にかかわらず。まず事実確認が要る）
        2. 次に 優先度 = SEVERITY_POINTS[severity] × confidence × weights[area] の降順
        3. 優先度が同じなら effort_days の昇順（早く片付くものを先に）
        4. それでも同じなら id の昇順（結果を決定的にするため）
    検証は area_scores と同じ（weights にない領域は ValueError）。

    ヒント: sorted() の key にタプルを返す関数を渡すと、複数の基準で並べられる。
    降順にしたい数値は符号を反転させる。
    """
    raise NotImplementedError("演習3: remediation_plan を実装してください")
