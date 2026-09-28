"""8.4 CI/CDとリリースエンジニアリング — 演習4: セマンティックバージョニング（SemVer 2.0.0）

依存関係の管理では「^1.2.3 なら 1.x の最新まで自動で上げてよい」のような範囲指定を使います。
その意味を正確に理解するために、SemVer 2.0.0 の解析・優先順位の比較と、npm 風の範囲指定の
判定を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.4

SemVer 2.0.0 の要点（https://semver.org/ の仕様に従う）:
    MAJOR.MINOR.PATCH[-プレリリース][+ビルドメタデータ]
    - MAJOR・MINOR・PATCH は 0 以上の整数。先頭に 0 を付けてはいけない（"01" は不正、"0" はよい）。
    - プレリリース: "-" の後ろに、"." で区切った識別子を 1 つ以上。識別子は [0-9A-Za-z-] の
      1 文字以上で、数字だけの識別子は先頭に 0 を付けてはいけない。
    - ビルドメタデータ: "+" の後ろに、"." で区切った [0-9A-Za-z-] の 1 文字以上の識別子。
      （先頭の 0 は許される）
    - "v1.2.3" のような接頭辞、空白、"1.2" のような省略形は SemVer ではない。

優先順位（precedence）の規則:
    1. MAJOR・MINOR・PATCH を数値として順に比べる。
    2. 同じなら、プレリリースのある版は、ない版より低い（1.0.0-alpha < 1.0.0）。
    3. プレリリースどうしは、識別子を左から順に比べる:
       数字だけの識別子は数値で比べ、英字を含む識別子は ASCII の辞書順で比べ、
       数字だけの識別子は英字を含む識別子より低い。すべて等しければ、識別子の多い方が高い。
       例: 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2
           < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
    4. ビルドメタデータは優先順位に影響しない（1.0.0+a と 1.0.0+b は同じ優先順位）。

範囲指定（npm の node-semver に準拠した部分集合）:
    範囲     := 集合 ( "||" 集合 )*          … いずれかの集合を満たせばよい（OR）
    集合     := 比較子 ( 空白 比較子 )*     … すべての比較子を満たす（AND）。または "*"（任意の版）
    比較子   := 演算子? バージョン          … 演算子は "^" "~" ">=" "<=" ">" "<" "="（省略時は "="）
    - "^1.2.3" := ">=1.2.3 <2.0.0-0"    （先頭の 0 でない部分を固定する）
      "^0.2.3" := ">=0.2.3 <0.3.0-0"
      "^0.0.3" := ">=0.0.3 <0.0.4-0"
    - "~1.2.3" := ">=1.2.3 <1.3.0-0"    （MINOR まで固定する）
    - 上限の "-0" は、次のメジャーなどのプレリリース（2.0.0-alpha など）を除外するための技法。
      "0" はプレリリースの識別子として最も低いので、2.0.0-0 より前は 2.0.0 のどのプレリリースより前になる。
    - プレリリースの規則: プレリリースを持つ版は、集合の中のどれかの比較子が **同じ
      MAJOR.MINOR.PATCH のプレリリース** を持つときだけ、その集合を満たしうる。
      例: "1.3.0-beta" は "^1.2.0" を満たさない（安定版の範囲に、不安定な版が勝手に入らない）。
          "1.2.3-beta.2" は ">=1.2.3-beta.1 <2.0.0" を満たす。
    - バージョンの省略形（"^1.2"、"1.x"）は扱わない（ValueError）。
"""
from __future__ import annotations

import re  # noqa: F401  実装で使えます
from dataclasses import dataclass
from typing import Iterable, Optional, Union


@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[Union[int, str], ...] = ()  # 数字だけの識別子は int、それ以外は str
    build: tuple[str, ...] = ()

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(str(p) for p in self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text


def parse(text: str) -> Version:
    """SemVer 2.0.0 の文字列を Version にする。不正なら ValueError。

    >>> parse("1.2.3-beta.11+build.5")
    Version(major=1, minor=2, patch=3, prerelease=('beta', 11), build=('build', '5'))

    注意: 正規表現の \\d は全角数字などの Unicode の数字にも一致します。[0-9] を使うこと。
          また、$ は末尾の改行の直前にも一致するので、re.fullmatch を使うこと。
    """
    raise NotImplementedError("演習4: parse を実装してください")


def compare(a: Union[str, Version], b: Union[str, Version]) -> int:
    """優先順位を比べ、a < b なら -1、等しければ 0、a > b なら 1 を返す（文字列なら parse してから）。"""
    raise NotImplementedError("演習4: compare を実装してください")


def satisfies(version: Union[str, Version], range_expr: str) -> bool:
    """version が範囲指定 range_expr を満たすか。範囲指定が不正なら ValueError。

    >>> satisfies("1.9.0", "^1.2.3"), satisfies("2.0.0", "^1.2.3")
    (True, False)
    """
    raise NotImplementedError("演習4: satisfies を実装してください")


def max_satisfying(versions: Iterable[str], range_expr: str) -> Optional[str]:
    """versions のうち range_expr を満たす、優先順位が最も高いものを（元の文字列のまま）返す。なければ None。

    依存関係の解決（「^1.2.0 を満たす最新版をインストールする」）の中核になる処理です。
    """
    raise NotImplementedError("演習4: max_satisfying を実装してください")
