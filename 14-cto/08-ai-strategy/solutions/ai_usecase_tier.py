"""14.8 AI戦略とAIガバナンス — 解答例: AIユースケースのリスク区分（教育用）

演習の仕様は exercises/ai_usecase_tier.py の docstring を参照してください。
これは法令上の分類ではありません（教育用に大幅に簡略化した社内トリアージのモデルです）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

PROHIBITED_KEYS = (
    "manipulative_or_exploitative",
    "social_scoring",
    "workplace_emotion_recognition",
    "untargeted_face_scraping",
)
HIGH_RISK_KEYS = (
    "employment_decision",
    "credit_or_insurance_decision",
    "education_decision",
    "essential_service_eligibility",
    "biometric_identification",
    "safety_critical_control",
)
TRANSPARENCY_KEYS = ("interacts_with_people", "generates_synthetic_media")
POLICY_KEYS = ("fully_automated_significant_decision", "uses_sensitive_personal_data")

QUESTIONS: dict[str, str] = {
    "manipulative_or_exploitative": "年齢・障害・経済状況などの弱みにつけこむ、または本人が気づかない操作的な手法で行動を歪め、重大な害を与えるおそれがあるか",
    "social_scoring": "人の社会的な行動や性格の評価をもとに、無関係な場面で不利益な扱いをするか",
    "workplace_emotion_recognition": "職場や教育の場で、人の感情を推定するか（医療・安全目的を除く）",
    "untargeted_face_scraping": "インターネットや監視カメラの映像から顔画像を無差別に集めて、顔認識のデータベースを作るか",
    "employment_decision": "採用・評価・昇進・解雇・業務の割り当ての判断に使うか",
    "credit_or_insurance_decision": "個人の与信（信用スコア）や、生命保険・医療保険の引受・保険料の判断に使うか",
    "education_decision": "入学・成績評価・試験の監督など、教育の機会や評価に関わる判断に使うか",
    "essential_service_eligibility": "公的給付・医療・住まいなど、生活に不可欠なサービスを受けられるかの判断に使うか",
    "biometric_identification": "顔・声・指紋などの生体情報で個人を識別するか",
    "safety_critical_control": "重要インフラ・機械・医療機器など、人の安全に関わる制御に使うか",
    "interacts_with_people": "利用者が AI と直接やりとりするか（チャットボット・音声応答など）",
    "generates_synthetic_media": "画像・音声・動画・文章を生成し、社外の人の目に触れるか",
    "fully_automated_significant_decision": "人の確認なしに、個人に重大な影響（契約の拒否・価格・アカウント停止など）を与える判断をするか",
    "uses_sensitive_personal_data": "要配慮個人情報（病歴・信条など）や子どもの個人データを扱うか",
}

TIERS = ("minimal", "limited", "high", "prohibited")  # リスクの低い順

BASE_CONTROLS = ("AI台帳に登録し、責任者を決める", "社内のAI利用規程に従う")
TRANSPARENCY_CONTROLS = {
    "interacts_with_people": "AI とやりとりしていることを利用者に明示する",
    "generates_synthetic_media": "AI による生成物であることを表示する",
}
HIGH_CONTROLS = (
    "影響評価（リスク評価）を実施して記録する",
    "人による監督を設計する（最終判断を人が行う、または覆せる）",
    "精度と公平性を導入前と定期的に評価する",
    "判断の根拠をたどれるようにログを保存する",
    "影響を受ける人への説明と異議申し立ての窓口を用意する",
)
PROHIBITED_CONTROLS = ("利用を中止し、法務と経営に相談する",)


@dataclass(frozen=True)
class TierResult:
    tier: str
    reasons: tuple[str, ...]
    escalated_by_policy: bool
    controls: tuple[str, ...]


def _check_answers(answers: Mapping[str, bool]) -> None:
    unknown = sorted(set(answers) - set(QUESTIONS))
    if unknown:
        raise ValueError(f"未知の質問です: {unknown}")
    # 未回答を「いいえ」と扱うと、確認漏れがそのまま「低リスク」になってしまう
    missing = [k for k in QUESTIONS if k not in answers]
    if missing:
        raise ValueError(f"未回答の質問があります: {missing}")
    for key, value in answers.items():
        if not isinstance(value, bool):
            raise TypeError(f"{key} の回答は True / False で指定してください: {value!r}")


def classify_use_case(answers: Mapping[str, bool]) -> TierResult:
    _check_answers(answers)
    reasons = tuple(k for k in QUESTIONS if answers[k])

    if any(answers[k] for k in PROHIBITED_KEYS):
        return TierResult("prohibited", reasons, False, PROHIBITED_CONTROLS)

    escalated = False
    if any(answers[k] for k in HIGH_RISK_KEYS):
        tier = "high"
    elif any(answers[k] for k in POLICY_KEYS):
        # 規制の類型には当たらなくても、社内基準でリスクを引き上げる
        tier, escalated = "high", True
    elif any(answers[k] for k in TRANSPARENCY_KEYS):
        tier = "limited"
    else:
        tier = "minimal"

    controls = list(BASE_CONTROLS)
    # 透明性の対策は、該当する回答があれば区分にかかわらず必要
    controls += [TRANSPARENCY_CONTROLS[k] for k in TRANSPARENCY_KEYS if answers[k]]
    if tier == "high":
        controls += HIGH_CONTROLS
    return TierResult(tier, reasons, escalated, tuple(controls))


def summarize_inventory(use_cases: Mapping[str, Mapping[str, bool]]) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {tier: [] for tier in reversed(TIERS)}
    for name, answers in use_cases.items():
        summary[classify_use_case(answers).tier].append(name)
    return {tier: sorted(names) for tier, names in summary.items()}
