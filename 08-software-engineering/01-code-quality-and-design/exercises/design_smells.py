"""8.1 良いコードと設計原則 — 演習3: 設計の「におい」を測る静的解析器

Python の標準ライブラリ ast（抽象構文木）を使って、関数ごとに次の指標を測り、
しきい値を超えたものを「におい（smell）」として報告するツールを作ります。

  - 関数の長さ（行数）
  - 引数の数
  - 制御構造の入れ子の深さ
  - 循環的複雑度（cyclomatic complexity, McCabe 1976）

これらの数値は「悪いコードの証明」ではなく「人間が見るべき場所の目印」です。
本文の「複雑さの正体」と合わせて、数値が捉えられるもの・捉えられないものを考えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.1

完成したら、コマンドラインから使えます（exercises/ ディレクトリで）:
    python3 design_smells.py pricing.py

制約: 解析には ast モジュールを使ってください（正規表現や行の字下げで数えない）。
"""
from __future__ import annotations

import ast  # noqa: F401  実装で使います
import sys
from dataclasses import dataclass

# 報告の順序（同じ行の関数では、この順に並べる）
SMELL_KINDS = ("long_function", "too_many_params", "deep_nesting", "high_complexity")


@dataclass(frozen=True)
class FunctionMetrics:
    """1 つの関数の測定結果。"""

    name: str  # 修飾名。メソッドは "Class.method"、入れ子の関数は "outer.inner"
    lineno: int  # def の行（デコレータの行ではない）
    length: int  # def の行から本体の最終行までの行数（end_lineno - lineno + 1）
    params: int  # 引数の数（下記の規則）
    max_nesting: int  # 制御構造の入れ子の最大の深さ（下記の規則）
    complexity: int  # 循環的複雑度（下記の規則）


@dataclass(frozen=True)
class Smell:
    """しきい値を超えた指標 1 つ分。"""

    name: str  # 関数の修飾名
    lineno: int
    kind: str  # SMELL_KINDS のいずれか
    value: int  # 測定値
    limit: int  # しきい値（value > limit のとき報告する）


def analyze_source(source: str) -> list[FunctionMetrics]:
    """ソースコード中のすべての関数（def と async def）を測定し、出現順（行・列の順）に返す。

    対象: モジュール直下の関数、クラスのメソッド、入れ子の関数（すべて別々に測る）。
    lambda は独立した関数として扱わず、それを含む関数の一部として数える。
    モジュール直下の（関数に含まれない）コードは測定しない。

    修飾名（name）: 外側のクラス名・関数名を "." でつなぐ。
        class Order:            → Order.total
            def total(self): ...
        def outer():            → outer.inner
            def inner(): ...

    引数の数（params）:
        位置専用引数 + 通常の引数 + キーワード専用引数 の個数に、
        *args があれば +1、**kwargs があれば +1。
        ただし、クラスの本体に直接書かれたメソッドの第 1 引数が self または cls なら数えない。

    入れ子の深さ（max_nesting）:
        関数本体の直下を深さ 0 とし、次の文の本体に入るたびに 1 深くなる。
            if / for / async for / while / with / async with / try / match
        - elif は深くしない（if と同じ深さの分岐として扱う）。
          ヒント: elif は AST では orelse に入った If になる。`else:` の中に書いた if と
          区別するには、orelse の唯一の要素が If で、その col_offset が外側の if と同じか
          を見ればよい（elif の If ノードは elif キーワードの位置から始まる）。
        - else / except / finally の本体は、対応する if・for・try の本体と同じ深さ。
        - 入れ子の関数・クラスの中には入らない（それらは別に測る）。
        例: 本体に if があり、その中に for がある → max_nesting == 2。制御構造がなければ 0。

    循環的複雑度（complexity）: 1 ＋ 次の「分岐点」の数。
        - if・elif（AST ではどちらも If）: 各 +1
        - 条件式 `a if c else b`（IfExp）: +1
        - for / async for / while: 各 +1
        - except 節: 1 つにつき +1
        - and / or: `a and b and c` は +2（BoolOp の値の個数 − 1）
        - 内包表記・ジェネレータ式: for 節 1 つにつき +1、その中の if 1 つにつき +1
        - match 文の case: 1 つにつき +1（ただしガードのない `case _:` は else に相当するので数えない）
        - else・finally・with・assert は数えない
        - 入れ子の関数・クラスの中の分岐は数えない（lambda の中の分岐は数える）

    >>> [m.name for m in analyze_source("class A:\\n    def f(self, x):\\n        return x\\n")]
    ['A.f']
    >>> analyze_source("def f(a, b):\\n    if a and b:\\n        return 1\\n    return 0\\n")[0].complexity
    3
    """
    raise NotImplementedError("演習3: analyze_source を実装してください")


def find_smells(
    source: str,
    *,
    max_length: int = 40,
    max_params: int = 4,
    max_nesting: int = 3,
    max_complexity: int = 10,
) -> list[Smell]:
    """analyze_source の結果のうち、しきい値を「超えた」（value > limit）指標を Smell として返す。

    kind と対応する指標:
        "long_function" → length / "too_many_params" → params /
        "deep_nesting" → max_nesting / "high_complexity" → complexity
    並び順: 関数の出現順。同じ関数の中では SMELL_KINDS の順。

    既定のしきい値は一例です。循環的複雑度 10 は McCabe が論文で示した上限の目安に由来します。
    """
    raise NotImplementedError("演習3: find_smells を実装してください")


def format_report(smells: list[Smell], filename: str = "<source>") -> str:
    """人が読むためのレポートを作る。

    - 1 つの Smell につき 1 行。各行は "{filename}:{lineno} {name}: " で始まり、
      その後に日本語の説明と「value > limit」の形の数値を含める。例:
        pricing.py:81 calculate_total: 関数が長すぎます（64 行 > 40）
    - smells が空なら「問題は見つかりませんでした」を含む 1 行を返す。
    - 末尾に改行を付けない。
    """
    raise NotImplementedError("演習3: format_report を実装してください")


def main(argv: list[str]) -> int:
    """コマンドライン: 引数の各ファイルを解析してレポートを標準出力に書く。

    におい が 1 つでもあれば 1、なければ 0 を返す（CI で使えるように）。
    ファイルは UTF-8 として読む。
    """
    raise NotImplementedError("演習3: main を実装してください")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
