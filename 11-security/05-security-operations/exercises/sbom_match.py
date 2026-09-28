"""11.5 セキュリティ運用とサプライチェーン — 演習（sbom_match）

SBOM（Software Bill of Materials, ソフトウェア部品表）と脆弱性情報を突き合わせ、
「どの依存関係に、どの既知の脆弱性があり、どのバージョンで直るか」を出す小さな SCA
（Software Composition Analysis）ツールを作ります。
中心は「バージョンの大小を正しく比較する」ことです（"1.10.0" > "1.9.0" を文字列順で
間違えると、脆弱なバージョンを見逃したり、逆に誤検知したりします）。

作るもの:
  - 演習1: セマンティックバージョニング風のバージョン比較と、範囲制約（">=1.0.0,<1.4.2"）の判定
  - 演習2: CycloneDX（簡略版）の JSON の読み取りと、脆弱性フィードとの突き合わせ

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.5
    python3 tools/check.py -v 11.5

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_sbom_match

CycloneDX（簡略版）の JSON:
    {"bomFormat": "CycloneDX", "specVersion": "1.5",
     "components": [{"type": "library", "name": "log4j-core", "version": "2.14.1", "purl": "..."}]}
"""
from __future__ import annotations

import json  # noqa: F401
import re  # noqa: F401
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# 演習1（★★☆相当）: バージョンの比較
# ---------------------------------------------------------------------------

def parse_version(text: str) -> tuple[int, int, int, tuple[int, int, int]]:
    """"1.2.3" や "v2" を、比較できるタプルに変換する。解釈できなければ ValueError。

    - major.minor.patch を数値として取り出す（省略された部分は 0）。先頭の "v" は無視する。
    - "1.0.0-rc1" や "1.0.0-alpha.2" のようなプレリリースは、同じ番号の正式版より **小さく** なる
      ようにする。段階の順序は alpha/dev/pre < beta < rc < 正式版。
    - 戻り値の 4 番目は、正式版なら他のどのプレリリースより大きくなる値にする。
      （ヒント: 正式版を (1, 0, 0)、プレリリースを (0, 段階, 番号) のように表すと大小が付く）

    >>> parse_version("1.2.3")[:3]
    (1, 2, 3)
    """
    raise NotImplementedError("演習1: parse_version を実装してください")


def compare_versions(a: str, b: str) -> int:
    """a < b なら -1、a == b なら 0、a > b なら 1 を返す。"""
    raise NotImplementedError("演習1: compare_versions を実装してください")


def satisfies(version: str, constraint: str) -> bool:
    """version が constraint を満たすか。

    constraint はカンマ区切りの制約の AND（すべて満たす必要がある）。
    各制約は演算子（>=, <=, >, <, ==, !=）とバージョン（例 ">=1.0.0"）。
    空文字列の制約はすべてのバージョンに一致する（True）。
    制約の構文が不正なら ValueError。

    >>> satisfies("2.14.1", ">=2.0.0,<2.16.0")
    True
    """
    raise NotImplementedError("演習1: satisfies を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆相当）: CycloneDX SBOM と脆弱性の突き合わせ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Component:
    name: str
    version: str
    purl: str = ""


@dataclass(frozen=True)
class Advisory:
    id: str
    package: str
    affected: str  # 影響を受けるバージョンの制約（satisfies に渡す）
    fixed: str  # 修正されたバージョン（なければ ""）
    severity: str


@dataclass(frozen=True)
class Finding:
    component: str
    version: str
    advisory_id: str
    severity: str
    fixed: str


def parse_cyclonedx(data: str | dict) -> list[Component]:
    """CycloneDX（簡略版）の JSON 文字列または dict から Component の一覧を取り出す。

    - "bomFormat" が "CycloneDX" でなければ ValueError。
    - components の各要素は name と version を必ず持つ（欠けていれば ValueError）。purl は任意。
    """
    raise NotImplementedError("演習2: parse_cyclonedx を実装してください")


def load_advisories(rows: list[dict]) -> list[Advisory]:
    """辞書のリストから Advisory のリストを作る（affected/fixed/severity は無ければ既定値）。"""
    raise NotImplementedError("演習2: load_advisories を実装してください")


def match(components: list[Component], advisories: list[Advisory]) -> list[Finding]:
    """各コンポーネントに該当する脆弱性を Finding として返す。

    コンポーネント名が advisory.package と一致し、かつ version が advisory.affected を
    満たすものを検出する。結果は (advisory_id, component) の昇順で安定にソートして返す。
    """
    raise NotImplementedError("演習2: match を実装してください")


def scan_sbom_file(path: str | Path, advisories: list[Advisory]) -> list[Finding]:
    """SBOM ファイルを読み込み、parse_cyclonedx → match の結果を返す。"""
    raise NotImplementedError("演習2: scan_sbom_file を実装してください")
