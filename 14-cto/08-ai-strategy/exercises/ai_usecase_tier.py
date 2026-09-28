"""14.8 AI戦略とAIガバナンス — 演習: AIユースケースのリスク区分（教育用の簡易版）

AI ガバナンスの第一歩は、社内の AI ユースケースを台帳に載せ、リスクに応じて
「どこまでの管理が必要か」を振り分けること（トリアージ）です。この演習では、
EU の AI 法のような「リスクベース」の規制の考え方を参考に、質問票の回答から
ユースケースを 4 区分に振り分け、必要な管理策を返す関数を作ります。

重要: これは法令上の分類ではありません。実在の法令（EU AI 法など）の要件・例外・
定義を大幅に単純化した、教育用・社内トリアージ用のモデルです。実際の適用判断は、
最新の条文とガイダンスを確認し、専門家に相談してください（本文 8 節）。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.8
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

# 禁止相当: 1 つでも「はい」なら "prohibited"
PROHIBITED_KEYS = (
    "manipulative_or_exploitative",
    "social_scoring",
    "workplace_emotion_recognition",
    "untargeted_face_scraping",
)
# 高リスクの分野: 1 つでも「はい」なら "high"
HIGH_RISK_KEYS = (
    "employment_decision",
    "credit_or_insurance_decision",
    "education_decision",
    "essential_service_eligibility",
    "biometric_identification",
    "safety_critical_control",
)
# 透明性（AI であることの明示）が必要になる用途
TRANSPARENCY_KEYS = ("interacts_with_people", "generates_synthetic_media")
# 社内基準でリスクを引き上げる要因（規制の類型に当たらなくても "high" にする）
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
    """区分の判定結果。

    tier:                "minimal" / "limited" / "high" / "prohibited"
    reasons:             「はい」と答えた質問のキー（QUESTIONS の順）
    escalated_by_policy: 高リスク分野には当たらず、社内基準（POLICY_KEYS）だけで "high" になったか
    controls:            必要な管理策
    """

    tier: str
    reasons: tuple[str, ...]
    escalated_by_policy: bool
    controls: tuple[str, ...]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: ユースケースの区分
# ---------------------------------------------------------------------------

def classify_use_case(answers: Mapping[str, bool]) -> TierResult:
    """質問票の回答 {質問のキー: True/False} から、区分と必要な管理策を返す。

    入力の検証:
        - QUESTIONS にないキーがあれば ValueError
        - QUESTIONS のキーが 1 つでも欠けていれば ValueError
          （未回答を「いいえ」とみなすと、確認漏れがそのまま「低リスク」になるため）
        - 値が bool でなければ TypeError

    区分の決め方（上から順に判定）:
        1. PROHIBITED_KEYS のどれかが True → "prohibited"。controls は PROHIBITED_CONTROLS のみ
        2. HIGH_RISK_KEYS のどれかが True → "high"
        3. POLICY_KEYS のどれかが True → "high"（escalated_by_policy=True）
        4. TRANSPARENCY_KEYS のどれかが True → "limited"
        5. それ以外 → "minimal"

    controls（prohibited 以外）:
        BASE_CONTROLS
        ＋ TRANSPARENCY_KEYS のうち True のものに対応する TRANSPARENCY_CONTROLS（TRANSPARENCY_KEYS の順）
        ＋ "high" なら HIGH_CONTROLS

    例: 採用書類のスクリーニングを行うチャットボット
        → tier="high", reasons=("employment_decision", "interacts_with_people")
    """
    raise NotImplementedError("演習1: classify_use_case を実装してください")


def summarize_inventory(use_cases: Mapping[str, Mapping[str, bool]]) -> dict[str, list[str]]:
    """AI 台帳 {ユースケース名: 回答} を区分ごとにまとめる。

    - 戻り値のキーはリスクの高い順 ("prohibited", "high", "limited", "minimal") で、
      該当がなくても空のリストを入れる。
    - 各リストはユースケース名の昇順。
    """
    raise NotImplementedError("演習1: summarize_inventory を実装してください")
