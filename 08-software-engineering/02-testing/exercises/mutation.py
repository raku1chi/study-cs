"""8.2 テスト戦略 — 演習2: ミニ・ミューテーションテスト

「テストがどれだけバグを見つけられるか」を測る方法の一つが、ミューテーションテストです。
対象のコードにわざと小さなバグ（変異 = mutant）を 1 つずつ入れ、テストがそれを検出できる
（テストが失敗する = 変異体を「殺す」）かを調べます。

    変異スコア = 殺した変異体の数 / 変異体の総数

カバレッジが 100% でも、アサーションが弱ければ変異体は生き残ります。生き残った変異体は、
「このバグが入ってもテストは気づかない」という具体的な証拠です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.2

作るもの:
    2-1 generate_mutants: 関数のソースから、変異体の一覧を作る（ast を使う）
    2-2 run_mutation_test: 各変異体に対してテスト関数を実行し、結果を集計する
    2-3 format_report   : 人が読むためのレポート

変異の規則（この順に、1 か所につき 1 つずつ変異体を作る）:

  kind="arithmetic"（算術演算子。BinOp と AugAssign の演算子）
      +  → -      -  → +      *  → /      /  → *      // → *      %  → //
      （上の表にない演算子（** や @ など）は変異させない）
  kind="comparison"（比較演算子。Compare の各演算子を 1 つずつ）
      <  → <=, >=        <= → <, >         >  → >=, <=        >= → >, <
      == → !=            != → ==           is → is not        is not → is
      in → not in        not in → in
  kind="constant"（定数）
      int（bool 以外）の定数 n → n + 1, n - 1（この順）
      bool の定数 True → False、False → True
      （文字列・浮動小数点数・None などは変異させない。docstring も対象外）
  kind="boolean"（論理）
      and → or、or → and（BoolOp）
      not x → x（not を取り除く）
      if / while / 条件式（x if c else y）の条件 c → not (c)

  - 変異させるのは、指定した関数の **本体（body）** だけ。デコレータ・引数の既定値・型注釈は対象外。
  - 変異箇所を探す順序は、ast.NodeVisitor が本体を訪れる順（深さ優先・前順）。
    1 つのノードに複数の変異があるときは、上の表の順。
    例: Compare `a < b` は、まず `<=` への変異、次に `>=` への変異。

制約: ソースコードの文字列置換ではなく、ast で木を書き換えること（ast.unparse でソースに戻せます）。
ヒント: 「k 番目の変異箇所だけを書き換える ast.NodeTransformer」を作ると、
        列挙と書き換えで同じ順序を使えて間違いにくくなります。copy.deepcopy で元の木を守ること。
"""
from __future__ import annotations

import ast  # noqa: F401  実装で使います
import copy  # noqa: F401  実装で使います
from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Mutant:
    """変異体 1 つ分。"""

    id: int  # 1 から始まる通し番号（変異箇所を探す順）
    kind: str  # "arithmetic" / "comparison" / "constant" / "boolean"
    lineno: int  # 変異させたノードの行番号（元のソース上の行）
    original: str  # 変異前の表現。演算子なら "+"、定数なら "4"、not の除去なら "not"、条件なら元の条件式
    replacement: str  # 変異後の表現。演算子なら "-"、定数なら "5"、not の除去なら ""、条件なら "not (条件式)"
    source: str  # 変異させた関数全体のソース（ast.unparse の結果）


@dataclass
class MutationReport:
    """ミューテーションテストの結果。"""

    total: int
    killed: int
    survived: list[Mutant] = field(default_factory=list)

    @property
    def score(self) -> float:
        """殺した割合（0.0〜1.0）。変異体が 1 つもなければ 1.0。"""
        return self.killed / self.total if self.total else 1.0


def generate_mutants(source: str, function_name: str) -> list[Mutant]:
    """モジュールのソース source の中の、トップレベルの関数 function_name の変異体を作る。

    - function_name という名前のトップレベルの def / async def がなければ ValueError。
    - 戻り値の Mutant は id の昇順（= 変異箇所を探す順）。
    - Mutant.source は ast.unparse で得た、変異後の関数全体のソース。
      （ast.parse(m.source) が成功し、元の関数とは異なるソースになる）

    例: `return a + b` の関数からは、kind="arithmetic", original="+", replacement="-" の
        変異体が 1 つだけ作られる。
    """
    raise NotImplementedError("演習2-1: generate_mutants を実装してください")


def run_mutation_test(
    source: str,
    function_name: str,
    test: Callable[[Callable], None],
) -> MutationReport:
    """各変異体に対してテスト関数 test を実行し、結果を集計する。

    - test は「テスト対象の関数」を引数に受け取り、問題があれば例外（AssertionError など）を
      送出する関数。例: def test(fn): assert fn(2024) is True
    - まず元の関数で test を実行する。失敗したら ValueError（元のコードで通らないテストでは、
      変異体を殺しても意味がないため）。
    - 各変異体について、モジュール全体のソースのうち対象の関数だけを変異体に差し替えたものを
      コンパイルして実行し（新しい名前空間の dict で exec する）、得られた関数で test を実行する。
        test が例外（Exception のサブクラス）を送出 → 殺した（killed）
        test が正常に終了                          → 生き残った（survived）
      変異体の実行自体が例外（ZeroDivisionError など）になった場合も、テストが失敗したので killed。
    - MutationReport(total, killed, survived) を返す。survived は id の昇順。

    発展: while ループの条件を変異させると、無限ループする変異体ができることがあります。
          実用的なツールは、時間切れ（timeout）を「殺した」とみなします。この演習のテストは
          ループのない関数だけを使いますが、sys.settrace で実行行数に上限を設ける方法を考えてみましょう。
    """
    raise NotImplementedError("演習2-2: run_mutation_test を実装してください")


def format_report(report: MutationReport) -> str:
    """人が読むためのレポートを返す。

    - 1 行目は「変異スコア: 85.0%（17/20）」のように、小数点以下 1 桁のパーセントと (killed/total)。
    - 続いて、生き残った変異体ごとに 1 行。行に id・行番号・kind・original・replacement を含める。
      例: 「  生存 #7（2 行目, constant）: 100 → 101」
    """
    raise NotImplementedError("演習2-3: format_report を実装してください")
