"""14.5 ガバナンス・リスク・コンプライアンスと法務 — 解答例（license_policy.py）

依存パッケージの SPDX ライセンス式（AND / OR / WITH / 括弧 / +）を構文解析し、
提供形態（社内利用 / SaaS / 配布）ごとのポリシーで「許可 / 要レビュー / 禁止」を判定します。
演習の仕様は exercises/license_policy.py の docstring を参照してください。

注意: 教育用に簡略化したポリシーです。実際のライセンスの解釈と社内ポリシーの策定は、
法務部門・弁護士と行ってください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Union

DECISIONS = ("allowed", "review", "prohibited")
_RANK = {d: i for i, d in enumerate(DECISIONS)}
MODELS = ("internal", "saas", "distributed")
_OPERATORS = ("AND", "OR", "WITH")

CATEGORY_LABEL = {
    "permissive": "パーミッシブ",
    "weak-copyleft": "弱いコピーレフト",
    "strong-copyleft": "強いコピーレフト",
    "network-copyleft": "ネットワークコピーレフト",
    "source-available": "ソース公開型（OSS ではない）",
    "unknown": "未知のライセンス",
}
DECISION_LABEL = {"allowed": "許可", "review": "要レビュー", "prohibited": "禁止"}
MODEL_LABEL = {"internal": "社内利用", "saas": "SaaS", "distributed": "配布"}
# コピーレフトの強さの順（例外の適用で「弱める」ときに使う）
_STRENGTH = ["permissive", "weak-copyleft", "strong-copyleft", "network-copyleft"]


# ---------------------------------------------------------------------------
# 構文木
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class License:
    id: str
    or_later: bool = False
    exception: str | None = None


@dataclass(frozen=True)
class And:
    items: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    items: tuple[Node, ...]


Node = Union[License, And, Or]


# ---------------------------------------------------------------------------
# ポリシー
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    categories: Mapping[str, str]
    exceptions: Mapping[str, str]
    rules: Mapping[str, Mapping[str, str]]
    unknown_decision: str = "review"


def _ids(category: str, *ids: str) -> dict[str, str]:
    return {i: category for i in ids}


DEFAULT_POLICY = Policy(
    categories={
        **_ids("permissive", "MIT", "MIT-0", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0",
               "ISC", "Zlib", "0BSD", "Unlicense", "CC0-1.0", "Python-2.0", "PostgreSQL",
               "BSL-1.0"),  # BSL-1.0 は Boost Software License（Business Source License ではない）
        **_ids("weak-copyleft", "LGPL-2.1-only", "LGPL-2.1-or-later", "LGPL-3.0-only",
               "LGPL-3.0-or-later", "LGPL-2.1", "LGPL-3.0", "MPL-2.0", "EPL-2.0", "CDDL-1.0"),
        **_ids("strong-copyleft", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only",
               "GPL-3.0-or-later", "GPL-2.0", "GPL-3.0"),
        **_ids("network-copyleft", "AGPL-3.0-only", "AGPL-3.0-or-later", "AGPL-3.0"),
        **_ids("source-available", "BUSL-1.1", "SSPL-1.0", "Elastic-2.0"),
    },
    exceptions={
        "Classpath-exception-2.0": "weak-copyleft",
        "GCC-exception-3.1": "weak-copyleft",
        "LLVM-exception": "permissive",
    },
    rules={
        "permissive": {"internal": "allowed", "saas": "allowed", "distributed": "allowed"},
        "weak-copyleft": {"internal": "allowed", "saas": "allowed", "distributed": "review"},
        "strong-copyleft": {"internal": "allowed", "saas": "review", "distributed": "prohibited"},
        "network-copyleft": {"internal": "review", "saas": "prohibited", "distributed": "prohibited"},
        "source-available": {"internal": "review", "saas": "review", "distributed": "review"},
    },
)


def canonical_id(identifier: str, known: Mapping[str, str]) -> str:
    """SPDX の ID は大文字小文字を区別せずに照合する。既知の ID なら正式な表記に揃える。"""
    lowered = {k.lower(): k for k in known}
    return lowered.get(identifier.lower(), identifier)


# ---------------------------------------------------------------------------
# 演習1: 字句解析と構文解析
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"\(|\)|[A-Za-z0-9.\-:]+\+?|\S")
_ID_RE = re.compile(r"[A-Za-z0-9.\-:]+\+?")


def tokenize(expression: str) -> list[str]:
    tokens = _TOKEN_RE.findall(expression)
    for tok in tokens:
        if tok not in ("(", ")") and not _ID_RE.fullmatch(tok):
            raise ValueError(f"ライセンス式に使えない文字です: {tok!r}")
    return tokens


class _Parser:
    """再帰下降構文解析。優先順位は + > WITH > AND > OR（SPDX 仕様）。

    or_expr   := and_expr ("OR" and_expr)*
    and_expr  := with_expr ("AND" with_expr)*
    with_expr := "(" or_expr ")" | simple ["WITH" exception-id]
    simple    := license-id ["+"]
    """

    def __init__(self, tokens: list[str], policy: Policy) -> None:
        self.tokens = tokens
        self.pos = 0
        self.policy = policy

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str | None:
        tok = self.peek()
        self.pos += 1
        return tok

    def parse(self) -> Node:
        if not self.tokens:
            raise ValueError("ライセンス式が空です")
        node = self.or_expr()
        if self.peek() is not None:
            raise ValueError(f"余分なトークンがあります: {self.peek()!r}（演算子は大文字の AND / OR / WITH）")
        return node

    def or_expr(self) -> Node:
        items = [self.and_expr()]
        while self.peek() == "OR":
            self.take()
            items.append(self.and_expr())
        return _flatten(Or, items)

    def and_expr(self) -> Node:
        items = [self.with_expr()]
        while self.peek() == "AND":
            self.take()
            items.append(self.with_expr())
        return _flatten(And, items)

    def with_expr(self) -> Node:
        if self.peek() == "(":
            self.take()
            node = self.or_expr()
            if self.take() != ")":
                raise ValueError("閉じ括弧 ')' がありません")
            if self.peek() == "WITH":
                raise ValueError("WITH は括弧のあとには書けません（単一のライセンスにだけ付けられる）")
            return node
        lic = self.simple()
        if self.peek() == "WITH":
            self.take()
            exc = self.take()
            if exc is None or exc in _OPERATORS or exc in ("(", ")") or exc.endswith("+"):
                raise ValueError(f"WITH のあとに例外の ID がありません: {exc!r}")
            return License(lic.id, lic.or_later, canonical_id(exc, self.policy.exceptions))
        return lic

    def simple(self) -> License:
        tok = self.take()
        if tok is None:
            raise ValueError("式が途中で終わっています")
        if tok in _OPERATORS or tok in ("(", ")"):
            raise ValueError(f"ライセンス ID があるべき位置に {tok!r} があります")
        or_later = tok.endswith("+")
        ident = tok[:-1] if or_later else tok
        return License(canonical_id(ident, self.policy.categories), or_later)


def _flatten(cls: type, items: list[Node]) -> Node:
    """A AND (B AND C) のような同じ演算子の入れ子を 1 段にまとめる（AND・OR は結合的）。"""
    if len(items) == 1:
        return items[0]
    flat: list[Node] = []
    for item in items:
        if isinstance(item, cls):
            flat.extend(item.items)
        else:
            flat.append(item)
    return cls(tuple(flat))


def parse(expression: str, policy: Policy = DEFAULT_POLICY) -> Node:
    return _Parser(tokenize(expression), policy).parse()


def to_spdx(node: Node) -> str:
    if isinstance(node, License):
        text = node.id + ("+" if node.or_later else "")
        return f"{text} WITH {node.exception}" if node.exception else text
    if isinstance(node, And):
        # AND の中の OR は括弧が必要（AND の方が強く結合するため）
        return " AND ".join(f"({to_spdx(i)})" if isinstance(i, Or) else to_spdx(i) for i in node.items)
    return " OR ".join(to_spdx(i) for i in node.items)


# ---------------------------------------------------------------------------
# 演習2: ポリシーによる判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Evaluation:
    decision: str
    licenses: tuple[str, ...]
    reasons: tuple[str, ...]


def license_category(lic: License, policy: Policy = DEFAULT_POLICY) -> tuple[str, list[str]]:
    lowered = {k.lower(): v for k, v in policy.categories.items()}
    category = lowered.get(lic.id.lower(), "unknown")
    notes: list[str] = []
    if lic.exception is None:
        return category, notes
    exc_lowered = {k.lower(): v for k, v in policy.exceptions.items()}
    relaxed = exc_lowered.get(lic.exception.lower())
    if relaxed is None:
        notes.append(f"未知の例外 {lic.exception} は考慮しない")
    elif category in _STRENGTH and relaxed in _STRENGTH:
        # 例外は条件を緩めるだけ。元より厳しくはしない
        category = _STRENGTH[min(_STRENGTH.index(category), _STRENGTH.index(relaxed))]
    return category, notes


def evaluate(expression: str | Node, model: str, policy: Policy = DEFAULT_POLICY) -> Evaluation:
    if model not in MODELS:
        raise ValueError(f"提供形態は {MODELS} のいずれかです: {model!r}")
    node = parse(expression, policy) if isinstance(expression, str) else expression
    return _evaluate(node, model, policy)


def _evaluate(node: Node, model: str, policy: Policy) -> Evaluation:
    if isinstance(node, License):
        category, notes = license_category(node, policy)
        decision = policy.rules.get(category, {}).get(model, policy.unknown_decision)
        text = to_spdx(node)
        reason = f"{text}: {CATEGORY_LABEL.get(category, category)} → {DECISION_LABEL[decision]}（{MODEL_LABEL[model]}）"
        return Evaluation(decision, (text,), tuple(notes) + (reason,))
    children = [_evaluate(child, model, policy) for child in node.items]
    if isinstance(node, Or):
        # OR は利用者が選べる: 最も有利な（判定の軽い）選択肢を選ぶ。同点なら先に書かれた方
        best = min(children, key=lambda e: _RANK[e.decision])
        chosen = " AND ".join(best.licenses)
        return Evaluation(best.decision, best.licenses, best.reasons + (f"OR の選択肢から {chosen} を選択",))
    # AND はすべてに従う必要がある: 最も重い判定。従うライセンスは全部（重複は除く）
    worst = max(_RANK[c.decision] for c in children)
    licenses = tuple(dict.fromkeys(lic for c in children for lic in c.licenses))
    reasons = tuple(r for c in children for r in c.reasons)
    return Evaluation(DECISIONS[worst], licenses, reasons)


# ---------------------------------------------------------------------------
# 演習3: 依存関係の監査
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    package: str
    expression: str
    evaluation: Evaluation


def audit(dependencies: Mapping[str, str], model: str, policy: Policy = DEFAULT_POLICY) -> list[Finding]:
    if model not in MODELS:
        raise ValueError(f"提供形態は {MODELS} のいずれかです: {model!r}")
    findings = []
    for package, expression in dependencies.items():
        try:
            evaluation = evaluate(expression, model, policy)
        except ValueError as exc:
            # ツールが出力したライセンス情報が壊れていることもある。人が確認する
            evaluation = Evaluation("review", (), (f"ライセンス式を解釈できない: {exc}",))
        findings.append(Finding(package, expression, evaluation))
    findings.sort(key=lambda f: (-_RANK[f.evaluation.decision], f.package))
    return findings


def overall_decision(findings: list[Finding]) -> str:
    if not findings:
        return "allowed"
    return DECISIONS[max(_RANK[f.evaluation.decision] for f in findings)]


def _pad(text: str, width: int) -> str:
    """全角文字を幅 2 として、表示幅が width になるよう空白で埋める（出力例の整形用）。"""
    import unicodedata

    shown = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)
    return text + " " * max(0, width - shown)


if __name__ == "__main__":
    deps = {
        "web-framework": "MIT",
        "crypto-lib": "Apache-2.0 OR MIT",
        "image-codec": "(MIT AND BSD-3-Clause) OR GPL-2.0-or-later",
        "jdbc-driver": "GPL-2.0-only WITH Classpath-exception-2.0",
        "pdf-engine": "AGPL-3.0-only",
        "search-server": "SSPL-1.0 OR Elastic-2.0 OR AGPL-3.0-only",
        "legacy-widget": "LicenseRef-Proprietary-Vendor",
        "bad-metadata": "MIT/Apache-2.0",
    }
    for model in MODELS:
        findings = audit(deps, model)
        print(f"== 提供形態: {MODEL_LABEL[model]}（全体: {DECISION_LABEL[overall_decision(findings)]}）")
        for f in findings:
            print(f"  {_pad(DECISION_LABEL[f.evaluation.decision], 10)} {f.package:<14} {f.expression}")
    print()
    for reason in evaluate("(MIT AND BSD-3-Clause) OR GPL-2.0-or-later", "distributed").reasons:
        print("  ", reason)
