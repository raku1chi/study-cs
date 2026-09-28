"""11.1 セキュリティの基本原則と脅威モデリング — 演習（threatmodel）

データフロー図（DFD）から STRIDE-per-element で脅威を洗い出し、リスクスコアで
優先順位を付けて、対策チェックリストを出力する小さなツールを作ります。
実務の脅威モデリングは人間の議論が主役ですが、「DFD の要素の種類ごとに考えるべき
脅威の型が決まっている」「信頼境界をまたぐところが危ない」という考え方を、
コードに落とすことで確実に身につけるのが狙いです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.1          # 合格数を表示
    python3 tools/check.py -v 11.1       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_threatmodel

モデルの表現:
    - ゾーン（信頼ゾーン）: {"internet": 0, "app": 2, ...} のように名前 → 信頼度（0 以上の整数）。
      信頼度 0 は「信頼できないゾーン」（インターネットなど）を表す。
      **ゾーン名が異なる要素の間には信頼境界がある** とみなす（信頼度が同じでも別ゾーンなら境界）。
    - 要素 Element: 外部エンティティ（external_entity）・プロセス（process）・データストア（data_store）。
    - データフロー Flow: 要素から要素へのデータの流れ。
    - sensitivity（1〜5）: その要素・フローが扱うデータや機能の重要度。影響度（impact）として使う。
    - controls: すでにある対策の名前の集合。CONTROL_EFFECTS に載っているものだけを使える。

スコアリングの規則（演習2）:
    発生可能性 likelihood = 3 + 露出度 exposure − 効く対策の数 （1〜5 に切り詰める）
    影響度     impact     = 対象の sensitivity
    スコア     score      = likelihood × impact（1〜25）
    優先度     priority   = score >= 15 なら "高"、>= 8 なら "中"、それ以外は "低"

    「効く対策」とは、対象の controls のうち CONTROL_EFFECTS[対策] にその脅威の分類
    （S/T/R/I/D/E の 1 文字）を含むもの。

注意: この採点規則は教材用に単純化したものです。実務では数値を機械的に信じるのではなく、
チームで議論して調整します（README の「リスクで考える」を参照）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("external_entity", "process", "data_store")
STRIDE = "STRIDE"
FLOW_CATEGORIES = "TID"  # データフローに対する脅威（STRIDE-per-element）

CATEGORY_NAMES = {
    "S": "なりすまし（Spoofing）",
    "T": "改ざん（Tampering）",
    "R": "否認（Repudiation）",
    "I": "情報漏えい（Information disclosure）",
    "D": "サービス拒否（Denial of service）",
    "E": "権限昇格（Elevation of privilege）",
}

MITIGATIONS = {
    "S": "強い認証（MFA・パスキー・mTLS・署名付きトークン）で相手を確かめる",
    "T": "完全性を守る（TLS・MAC/署名・入力検証・変更権限の限定）",
    "R": "改ざんできない監査ログに「誰が・いつ・何を」を記録する",
    "I": "暗号化・アクセス制御・データ最小化で「見せない・持たない」",
    "D": "レート制限・クォータ・タイムアウト・冗長化で可用性を守る",
    "E": "最小権限・すべての要求での認可チェック・サンドボックス化",
}

# 対策の名前 → その対策が発生可能性を下げる脅威の分類
CONTROL_EFFECTS = {
    "authn": "S",  # 認証
    "mfa": "S",  # 多要素認証
    "tls": "TI",  # 通信の暗号化と完全性保護
    "signing": "TR",  # 署名（改ざん検知と否認防止）
    "audit_log": "R",  # 監査ログ
    "encryption": "I",  # 保存時の暗号化
    "authz": "IE",  # 認可（アクセス制御）
    "input_validation": "TE",  # 入力検証
    "rate_limit": "D",  # レート制限
    "redundancy": "D",  # 冗長化
    "least_privilege": "E",  # 最小権限
    "sandbox": "E",  # サンドボックス
}


@dataclass(frozen=True)
class Element:
    """DFD の要素（データフロー以外）。"""

    id: str
    name: str
    kind: str  # "external_entity" | "process" | "data_store"
    zone: str
    sensitivity: int = 3
    controls: frozenset[str] = field(default_factory=frozenset)
    is_log: bool = False  # 監査ログを保存するデータストアなら True


@dataclass(frozen=True)
class Flow:
    """DFD のデータフロー（source から target へ）。"""

    id: str
    source: str
    target: str
    name: str
    sensitivity: int = 3
    controls: frozenset[str] = field(default_factory=frozenset)


@dataclass
class ThreatModel:
    zones: dict[str, int]
    elements: list[Element]
    flows: list[Flow]


@dataclass(frozen=True)
class Threat:
    """1 件の脅威。スコアや優先度は likelihood と impact から計算される。"""

    id: str  # "T001", "T002", ...（生成順の連番）
    target_id: str  # 要素またはフローの id
    target_name: str
    category: str  # "S" / "T" / "R" / "I" / "D" / "E"
    likelihood: int
    impact: int
    existing_controls: tuple[str, ...] = ()  # この脅威に効いている既存の対策（名前順）

    @property
    def score(self) -> int:
        return self.likelihood * self.impact

    @property
    def priority(self) -> str:
        if self.score >= 15:
            return "高"
        if self.score >= 8:
            return "中"
        return "低"

    @property
    def category_name(self) -> str:
        return CATEGORY_NAMES[self.category]

    @property
    def mitigation(self) -> str:
        return MITIGATIONS[self.category]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: モデルの検証と STRIDE-per-element
# ---------------------------------------------------------------------------

def validate_model(model: ThreatModel) -> None:
    """モデルが DFD として正しいかを検査し、問題があれば ValueError を送出する。

    検査すること:
    - ゾーンの信頼度が 0 以上の int であること（bool は不可）
    - 要素・フローの id がすべて一意であること（要素とフローの間の重複も不可）
    - 要素の kind が KINDS のいずれかであること
    - 要素の zone が model.zones に定義されていること
    - is_log=True はデータストアにだけ指定されていること
    - sensitivity が 1〜5 の int であること（bool は不可）
    - controls に CONTROL_EFFECTS にない名前が含まれていないこと
    - フローの source と target が既存の要素を指し、互いに異なること
    - フローの少なくとも一端がプロセスであること
      （DFD の規則: データは必ずプロセスを通って動く。外部エンティティ → データストアの
       直接の流れは描けない。現実には「その間にある処理」を描き忘れている）
    """
    raise NotImplementedError("演習1: validate_model を実装してください")


def stride_for_element(element: Element) -> str:
    """要素の種類に応じて、検討すべき STRIDE の分類を "STRIDE" の順で返す。

    | 種類              | 分類                                   |
    |-------------------|----------------------------------------|
    | external_entity   | "SR"                                   |
    | process           | "STRIDE"                               |
    | data_store        | "TID"（is_log=True なら "TRID"）        |

    未知の種類は ValueError。

    >>> stride_for_element(Element("u", "利用者", "external_entity", "internet"))
    'SR'
    """
    raise NotImplementedError("演習1: stride_for_element を実装してください")


def crosses_trust_boundary(model: ThreatModel, flow: Flow) -> bool:
    """フローの両端の要素が異なるゾーンにあれば True（信頼境界をまたぐ）。"""
    raise NotImplementedError("演習1: crosses_trust_boundary を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 脅威の生成とリスクスコア
# ---------------------------------------------------------------------------

def exposure(model: ThreatModel, target_id: str) -> int:
    """要素またはフローの露出度（0〜2）を返す。存在しない id は KeyError。

    要素の場合:
    - 要素自身が信頼度 0 のゾーンにある → 2
    - その要素につながる（source または target が自分の）フローのうち、相手が
      別ゾーンにあるものについて、相手のゾーンの信頼度が 0 のものが 1 本でもある → 2
    - 相手が別ゾーンにあるフローがある（ただし上に当てはまらない）→ 1
    - それ以外（同じゾーンの中だけで完結）→ 0

    フローの場合:
    - 信頼境界をまたがない → 0
    - またぎ、どちらかの端が信頼度 0 のゾーンにある → 2
    - またぐが、どちらの端も信頼度 0 ではない → 1
    """
    raise NotImplementedError("演習2: exposure を実装してください")


def generate_threats(model: ThreatModel) -> list[Threat]:
    """モデルから脅威の一覧を生成して返す。

    手順:
    1. validate_model(model) で検証する（不正なら ValueError がそのまま伝わる）。
    2. 要素を model.elements の順に、stride_for_element の分類ごとに Threat を作る。
    3. 続いてフローを model.flows の順に見て、**信頼境界をまたぐフローだけ** について
       "TID" の分類ごとに Threat を作る（境界の内側のやり取りは要素の脅威で扱う）。
    4. id は生成順に "T001", "T002", ... と振る。

    各 Threat の値（モジュール docstring の規則）:
    - likelihood = max(1, min(5, 3 + exposure(対象) − 効く対策の数))
    - impact = 対象の sensitivity
    - existing_controls = 効く対策の名前を昇順に並べたタプル
    - target_name = 対象の name

    ヒント: 「効く対策」は controls のうち、CONTROL_EFFECTS[対策] に分類の文字を含むもの。
    """
    raise NotImplementedError("演習2: generate_threats を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: 優先順位付けとチェックリスト
# ---------------------------------------------------------------------------

def prioritize(threats: list[Threat], top: int | None = None) -> list[Threat]:
    """脅威を優先順に並べた **新しいリスト** を返す（引数のリストは変更しない）。

    並び順: スコアの降順 → 影響度（impact）の降順 → id の昇順。
    top が指定されたら先頭の top 件だけを返す。

    同点のとき影響度を優先するのは、発生可能性の見積もりの方が外れやすく、
    「起きたら致命的」なものを先に検討したいからです。
    """
    raise NotImplementedError("演習3: prioritize を実装してください")


def render_checklist(threats: list[Threat]) -> str:
    """優先順（prioritize の順）に並べた Markdown のチェックリストを返す。

    1 行目: "# 対策チェックリスト（{件数} 件）"
    続く各行（1 脅威 1 行）:
        "- [ ] [{priority}/{score}] {id} {category_name} — {target_name}: {mitigation}"
    既存の対策がある場合は、行末に "（既存の対策: authz, input_validation）" のように
    existing_controls を ", " でつないで付け加える。
    全体は改行でつなぎ、最後にも改行を 1 つ付ける。

    例:
        # 対策チェックリスト（2 件）
        - [ ] [高/20] T003 なりすまし（Spoofing） — 経費精算API: 強い認証（…）で相手を確かめる
        - [ ] [中/12] T001 なりすまし（Spoofing） — 利用者のブラウザ: 強い認証（…）（既存の対策: authn）
    """
    raise NotImplementedError("演習3: render_checklist を実装してください")
