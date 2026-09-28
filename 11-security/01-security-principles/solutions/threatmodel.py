"""11.1 セキュリティの基本原則と脅威モデリング — 解答例（threatmodel）

演習の仕様は exercises/threatmodel.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("external_entity", "process", "data_store")
STRIDE = "STRIDE"
FLOW_CATEGORIES = "TID"

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

CONTROL_EFFECTS = {
    "authn": "S",
    "mfa": "S",
    "tls": "TI",
    "signing": "TR",
    "audit_log": "R",
    "encryption": "I",
    "authz": "IE",
    "input_validation": "TE",
    "rate_limit": "D",
    "redundancy": "D",
    "least_privilege": "E",
    "sandbox": "E",
}


@dataclass(frozen=True)
class Element:
    id: str
    name: str
    kind: str
    zone: str
    sensitivity: int = 3
    controls: frozenset[str] = field(default_factory=frozenset)
    is_log: bool = False


@dataclass(frozen=True)
class Flow:
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
    id: str
    target_id: str
    target_name: str
    category: str
    likelihood: int
    impact: int
    existing_controls: tuple[str, ...] = ()

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
# 演習1: モデルの検証と STRIDE-per-element
# ---------------------------------------------------------------------------

def _check_common(obj_id: str, sensitivity: int, controls: frozenset[str]) -> None:
    # bool は int のサブクラスなので、True を 1 と誤認しないよう明示的に除外する
    if isinstance(sensitivity, bool) or not isinstance(sensitivity, int) or not 1 <= sensitivity <= 5:
        raise ValueError(f"{obj_id}: sensitivity は 1〜5 の整数です: {sensitivity!r}")
    unknown = set(controls) - set(CONTROL_EFFECTS)
    if unknown:
        raise ValueError(f"{obj_id}: 未知の対策です: {sorted(unknown)}")


def validate_model(model: ThreatModel) -> None:
    for zone, trust in model.zones.items():
        if isinstance(trust, bool) or not isinstance(trust, int) or trust < 0:
            raise ValueError(f"ゾーン {zone!r} の trust は 0 以上の整数です: {trust!r}")

    seen: set[str] = set()
    elements: dict[str, Element] = {}
    for e in model.elements:
        if e.id in seen:
            raise ValueError(f"ID が重複しています: {e.id}")
        seen.add(e.id)
        if e.kind not in KINDS:
            raise ValueError(f"{e.id}: 未知の要素の種類です: {e.kind!r}")
        if e.zone not in model.zones:
            raise ValueError(f"{e.id}: 未定義のゾーンです: {e.zone!r}")
        if e.is_log and e.kind != "data_store":
            raise ValueError(f"{e.id}: is_log はデータストアにだけ指定できます")
        _check_common(e.id, e.sensitivity, e.controls)
        elements[e.id] = e

    for f in model.flows:
        if f.id in seen:
            raise ValueError(f"ID が重複しています: {f.id}")
        seen.add(f.id)
        for end in (f.source, f.target):
            if end not in elements:
                raise ValueError(f"{f.id}: 未定義の要素を参照しています: {end!r}")
        if f.source == f.target:
            raise ValueError(f"{f.id}: 始点と終点が同じです")
        # DFD の規則: データは必ずプロセスを通って動く。
        # 外部エンティティ→データストアのような「プロセスを経ない流れ」は描けない。
        kinds = {elements[f.source].kind, elements[f.target].kind}
        if "process" not in kinds:
            raise ValueError(f"{f.id}: データフローの少なくとも一端はプロセスでなければなりません")
        _check_common(f.id, f.sensitivity, f.controls)


def stride_for_element(element: Element) -> str:
    # Microsoft SDL / Shostack の STRIDE-per-element 表
    if element.kind == "external_entity":
        return "SR"
    if element.kind == "process":
        return "STRIDE"
    if element.kind == "data_store":
        # 監査ログを保存するストアは「記録の改ざん・消去による否認」の対象にもなる
        return "TRID" if element.is_log else "TID"
    raise ValueError(f"未知の要素の種類です: {element.kind!r}")


def crosses_trust_boundary(model: ThreatModel, flow: Flow) -> bool:
    by_id = {e.id: e for e in model.elements}
    return by_id[flow.source].zone != by_id[flow.target].zone


# ---------------------------------------------------------------------------
# 演習2: 脅威の生成とリスクスコア
# ---------------------------------------------------------------------------

def exposure(model: ThreatModel, target_id: str) -> int:
    by_id = {e.id: e for e in model.elements}
    zones = model.zones
    if target_id in by_id:
        element = by_id[target_id]
        if zones[element.zone] == 0:
            return 2  # 要素そのものが信頼できないゾーンにある
        level = 0
        for f in model.flows:
            if target_id not in (f.source, f.target):
                continue
            other = by_id[f.target if f.source == target_id else f.source]
            if other.zone == element.zone:
                continue  # 同じゾーン内の流れは信頼境界をまたがない
            if zones[other.zone] == 0:
                return 2  # 信頼できないゾーンと直接やり取りしている
            level = 1
        return level
    for f in model.flows:
        if f.id == target_id:
            if not crosses_trust_boundary(model, f):
                return 0
            ends = (by_id[f.source], by_id[f.target])
            return 2 if any(zones[e.zone] == 0 for e in ends) else 1
    raise KeyError(target_id)


def _likelihood(base_exposure: int, controls: frozenset[str], category: str) -> tuple[int, tuple[str, ...]]:
    relevant = tuple(sorted(c for c in controls if category in CONTROL_EFFECTS[c]))
    value = 3 + base_exposure - len(relevant)
    return max(1, min(5, value)), relevant


def generate_threats(model: ThreatModel) -> list[Threat]:
    validate_model(model)
    threats: list[Threat] = []

    def add(target_id: str, name: str, category: str, impact: int, controls: frozenset[str]) -> None:
        likelihood, relevant = _likelihood(exposure(model, target_id), controls, category)
        threats.append(
            Threat(
                id=f"T{len(threats) + 1:03d}",
                target_id=target_id,
                target_name=name,
                category=category,
                likelihood=likelihood,
                impact=impact,
                existing_controls=relevant,
            )
        )

    for e in model.elements:
        for category in stride_for_element(e):
            add(e.id, e.name, category, e.sensitivity, e.controls)
    # データフローは信頼境界をまたぐものだけを分析する（境界の内側は要素の脅威で扱う）
    for f in model.flows:
        if crosses_trust_boundary(model, f):
            for category in FLOW_CATEGORIES:
                add(f.id, f.name, category, f.sensitivity, f.controls)
    return threats


# ---------------------------------------------------------------------------
# 演習3: 優先順位付けとチェックリスト
# ---------------------------------------------------------------------------

def prioritize(threats: list[Threat], top: int | None = None) -> list[Threat]:
    # 同点なら影響度が大きい方を先に（発生可能性の見積もりは影響度より外れやすい）
    ordered = sorted(threats, key=lambda t: (-t.score, -t.impact, t.id))
    return ordered if top is None else ordered[:top]


def render_checklist(threats: list[Threat]) -> str:
    lines = [f"# 対策チェックリスト（{len(threats)} 件）"]
    for t in prioritize(threats):
        line = (
            f"- [ ] [{t.priority}/{t.score}] {t.id} {t.category_name} — "
            f"{t.target_name}: {t.mitigation}"
        )
        if t.existing_controls:
            line += f"（既存の対策: {', '.join(t.existing_controls)}）"
        lines.append(line)
    return "\n".join(lines) + "\n"
