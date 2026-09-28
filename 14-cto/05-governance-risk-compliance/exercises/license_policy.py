"""14.5 ガバナンス・リスク・コンプライアンスと法務 — 演習（license_policy.py）

依存パッケージの SPDX ライセンス式（AND / OR / WITH / 括弧 / +）を構文解析し、
提供形態（社内利用 / SaaS / 配布）ごとのポリシーで「許可 / 要レビュー / 禁止」を判定する
OSS コンプライアンスのツールを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
構文木・ポリシーのデータ構造・DEFAULT_POLICY・canonical_id は完成しています。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.5
    python3 -m unittest -v test_license_policy   # このディレクトリで直接

SPDX ライセンス式の文法（SPDX 仕様 Annex D を簡略化）:
    license-id    : 英数字・"-"・"." からなる ID（例: MIT, Apache-2.0, GPL-2.0-only）。
                    "LicenseRef-…" や "DocumentRef-…:LicenseRef-…" のような独自 ID もある（":" を含みうる）
    simple        : license-id または license-id の直後に "+"（「そのバージョン以降」）
    演算子        : WITH（例外の付加）、AND（両方に従う）、OR（どちらかを選べる）、括弧
    優先順位      : + > WITH > AND > OR（"A OR B AND C" は "A OR (B AND C)"）
    大文字小文字  : ライセンス ID と例外 ID は区別しない（"mit" は MIT）。
                    演算子は区別する（AND / OR / WITH は大文字だけが演算子）
    WITH の制約   : WITH は単一のライセンスにだけ付けられる（"(A OR B) WITH X" は不正）

注意: 教育用に簡略化したポリシーです。実際のライセンスの解釈と社内ポリシーの策定は、
法務部門・弁護士と行ってください。
"""
from __future__ import annotations

import re  # noqa: F401  演習1の字句解析で使えます
from dataclasses import dataclass
from typing import Mapping, Union

DECISIONS = ("allowed", "review", "prohibited")   # 軽い → 重い の順
MODELS = ("internal", "saas", "distributed")      # 社内利用 / SaaS として提供 / バイナリ等を配布

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


# ---------------------------------------------------------------------------
# 構文木（完成しています）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class License:
    """単一のライセンス。例: GPL-2.0-only WITH Classpath-exception-2.0"""

    id: str                        # ライセンス ID（既知の ID なら正式な表記に揃える）
    or_later: bool = False         # 末尾の "+"（そのバージョン以降）
    exception: str | None = None   # WITH で付いた例外の ID


@dataclass(frozen=True)
class And:
    """すべてに従う必要がある。items は 2 つ以上。"""

    items: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    """どれか 1 つを選べる。items は 2 つ以上。"""

    items: tuple[Node, ...]


Node = Union[License, And, Or]


# ---------------------------------------------------------------------------
# ポリシー（完成しています）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Policy:
    categories: Mapping[str, str]              # ライセンス ID → カテゴリ
    exceptions: Mapping[str, str]              # 例外 ID → 例外を適用した後のカテゴリ
    rules: Mapping[str, Mapping[str, str]]     # カテゴリ → {提供形態: 判定}
    unknown_decision: str = "review"           # rules にないカテゴリ（unknown など）の判定


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
    """大文字小文字を区別せずに known のキーと照合し、見つかれば正式な表記を返す（完成しています）。

    >>> canonical_id("apache-2.0", DEFAULT_POLICY.categories)
    'Apache-2.0'
    >>> canonical_id("LicenseRef-Foo", DEFAULT_POLICY.categories)
    'LicenseRef-Foo'
    """
    lowered = {k.lower(): k for k in known}
    return lowered.get(identifier.lower(), identifier)


# ---------------------------------------------------------------------------
# 演習1（★★★）: 字句解析と構文解析
# ---------------------------------------------------------------------------

def tokenize(expression: str) -> list[str]:
    """ライセンス式をトークンの列に分ける。

    トークンは次の 3 種類。空白は区切りとして読み飛ばす（括弧の前後に空白がなくてもよい）。
    - "(" と ")"
    - ID（英数字・"-"・"."・":" の 1 文字以上。直後に "+" が 1 つ付いてもよい）
      演算子 AND / OR / WITH も、この段階では ID と同じ形のトークンとして取り出す。
    それ以外の文字（"/"、","、単独の "+"、全角文字など）があれば ValueError。

    >>> tokenize("(MIT OR Apache-2.0) AND GPL-2.0+")
    ['(', 'MIT', 'OR', 'Apache-2.0', ')', 'AND', 'GPL-2.0+']
    >>> tokenize("(MIT)")
    ['(', 'MIT', ')']

    ヒント: re.findall で「括弧 | ID | その他の空白以外の 1 文字」を取り出し、
    「その他」が出てきたらエラーにする。
    """
    raise NotImplementedError("演習1: tokenize を実装してください")


def parse(expression: str, policy: Policy = DEFAULT_POLICY) -> Node:
    """ライセンス式を構文木（License / And / Or）に変換する。

    - 優先順位は + > WITH > AND > OR。括弧で優先順位を変えられる。
    - 同じ演算子の連なりは 1 つのノードにまとめる（平坦化）:
        "A AND B AND C"   → And((A, B, C))
        "(A AND B) AND C" → And((A, B, C))   ← 括弧があっても同じ演算子なら平坦化する
        "A OR B AND C"    → Or((A, And((B, C))))
    - ライセンス ID は canonical_id(id, policy.categories)、例外 ID は
      canonical_id(id, policy.exceptions) で正式な表記に揃える（未知の ID は書かれたまま）。
    - "GPL-2.0+" は License("GPL-2.0", or_later=True)。
    - "GPL-2.0-only WITH Classpath-exception-2.0" は
      License("GPL-2.0-only", exception="Classpath-exception-2.0")。

    次の場合は ValueError:
    - 空の式、閉じていない括弧、余分な閉じ括弧、空の括弧 "()"
    - 演算子が連続する・式が演算子で終わる（"MIT AND", "MIT OR OR BSD-3-Clause"）
    - ID が演算子なしに並ぶ（"MIT Apache-2.0"、小文字の "mit and bsd-3-clause" もこれに当たる）
    - WITH のあとに例外 ID がない、例外 ID に "+" が付いている、括弧のあとに WITH がある
    - tokenize がエラーにする文字を含む

    ヒント（再帰下降構文解析）: 優先順位の低い順に関数を分ける。
        or_expr   := and_expr ("OR" and_expr)*
        and_expr  := with_expr ("AND" with_expr)*
        with_expr := "(" or_expr ")" | simple ["WITH" 例外ID]
        simple    := ライセンスID["+"]
    トークンの位置を持つ小さなクラスを作ると書きやすい。
    """
    raise NotImplementedError("演習1: parse を実装してください")


def to_spdx(node: Node) -> str:
    """構文木を SPDX の式の文字列に戻す。parse(to_spdx(x)) == x となること。

    - License: "ID"、or_later なら "ID+"、例外があれば "ID WITH 例外ID"
    - And: 子を " AND " でつなぐ。子が Or なら括弧で囲む
    - Or: 子を " OR " でつなぐ（子の And には括弧を付けない）

    >>> to_spdx(Or((License("MIT"), And((License("Apache-2.0"), License("BSD-3-Clause"))))))
    'MIT OR Apache-2.0 AND BSD-3-Clause'
    >>> to_spdx(And((License("MIT"), Or((License("Apache-2.0"), License("GPL-2.0", or_later=True))))))
    'MIT AND (Apache-2.0 OR GPL-2.0+)'
    """
    raise NotImplementedError("演習1: to_spdx を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ポリシーによる判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Evaluation:
    """判定の結果（この型は完成しています）。"""

    decision: str                # "allowed" / "review" / "prohibited"
    licenses: tuple[str, ...]    # 従う必要のあるライセンス（OR では選んだ側）。to_spdx の表記
    reasons: tuple[str, ...]     # 判定の理由（人が読むための説明）


def license_category(lic: License, policy: Policy = DEFAULT_POLICY) -> tuple[str, list[str]]:
    """単一のライセンスのカテゴリと、補足（注記）のリストを返す。

    - lic.id を大文字小文字を区別せずに policy.categories で引く。なければ "unknown"。
    - or_later（"+"）はカテゴリに影響しない（保守的に、書かれたバージョンで判断する）。
    - 例外（lic.exception）があり、policy.exceptions で引けた場合: 例外を適用した後のカテゴリと
      元のカテゴリのうち、コピーレフトの弱い方を採用する。強さの順は
      permissive < weak-copyleft < strong-copyleft < network-copyleft。
      元のカテゴリがこの 4 つ以外（source-available, unknown）なら、例外で変えない。
    - 例外が policy.exceptions にない場合: カテゴリは変えず、注記に
      「未知の例外 {例外ID} は考慮しない」を加える。

    >>> license_category(License("GPL-2.0-only", exception="Classpath-exception-2.0"))
    ('weak-copyleft', [])
    >>> license_category(License("LicenseRef-Foo"))
    ('unknown', [])
    """
    raise NotImplementedError("演習2: license_category を実装してください")


def evaluate(expression: str | Node, model: str, policy: Policy = DEFAULT_POLICY) -> Evaluation:
    """ライセンス式（文字列または構文木）を、提供形態 model のポリシーで判定する。

    - License: カテゴリを license_category で求め、policy.rules[カテゴリ][model] を判定とする。
      rules にないカテゴリ（unknown など）は policy.unknown_decision。
      licenses は (to_spdx(ノード),)。reasons は 注記 ＋ 次の形式の 1 行:
          "{to_spdx(ノード)}: {CATEGORY_LABEL[カテゴリ]} → {DECISION_LABEL[判定]}（{MODEL_LABEL[model]}）"
    - Or: 子をそれぞれ判定し、判定が最も軽い子を選ぶ（同じなら先に書かれた方）。
      結果の decision と licenses は選んだ子のもの。reasons は選んだ子の reasons の後に
      "OR の選択肢から {選んだ licenses を " AND " でつないだもの} を選択" を加える。
    - And: 子をすべて判定し、最も重い判定を採用する。licenses は子の licenses を順に連結し、
      重複を除く（最初に現れた順を保つ）。reasons は子の reasons を順に連結する。
    - model が MODELS にない場合は ValueError。式の構文エラーは parse の ValueError のまま。

    >>> evaluate("MIT OR GPL-3.0-only", "distributed").decision
    'allowed'
    >>> evaluate("MIT AND GPL-3.0-only", "distributed").licenses
    ('MIT', 'GPL-3.0-only')
    """
    raise NotImplementedError("演習2: evaluate を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: 依存関係の監査
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """1 つの依存パッケージの判定結果（この型は完成しています）。"""

    package: str
    expression: str
    evaluation: Evaluation


def audit(dependencies: Mapping[str, str], model: str, policy: Policy = DEFAULT_POLICY) -> list[Finding]:
    """{パッケージ名: ライセンス式} を判定し、Finding のリストを返す。

    - 並び順: 判定の重い順（prohibited → review → allowed）、同じ判定の中ではパッケージ名の辞書順。
    - ライセンス式が構文エラーのパッケージは、例外を投げずに判定 "review"・licenses は空・
      reasons は ("ライセンス式を解釈できない: {エラーメッセージ}",) とする
      （ツールが出力したライセンス情報が壊れていることは実務でよくある。人が確認する）。
    - model が MODELS にない場合は ValueError。
    """
    raise NotImplementedError("演習3: audit を実装してください")


def overall_decision(findings: list[Finding]) -> str:
    """全体の判定（最も重い判定）を返す。findings が空なら "allowed"。"""
    raise NotImplementedError("演習3: overall_decision を実装してください")
