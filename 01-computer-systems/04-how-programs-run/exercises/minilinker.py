"""1.4 プログラムが動く仕組み — 演習5（★★★）: 小さなリンカ

別々に作られた「オブジェクトモジュール」（stackvm の命令列と、シンボル表・再配置情報の組）を
1 つの実行可能なプログラムにまとめるリンカを作ります。本物のリンカ（ld）が .o ファイルに対して
行っている「シンボル解決」と「再配置」の核心部分です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.4
このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_minilinker

======================================================================
オブジェクトモジュールの形式
======================================================================

各モジュールは、自分がどこに配置されるかを知らない状態で作られています（コンパイル・アセンブルは
モジュールごとに別々に行われるため）。そこで、番地が入るべき命令の引数は仮の値（0 など）にしておき、
「ここには、このシンボルの番地を入れてほしい」という再配置情報を添えておきます。

    ObjectModule(
        name="mathlib",
        code=[("LOAD", 0), ("LOAD", 0), ("MUL",), ("RET",)],     # square(x) = x * x
        symbols={"square": 0},             # 公開する（グローバル）シンボル → code 内の位置
        local_symbols={},                  # このモジュールの中だけで使うシンボル → code 内の位置
        relocations=[],                    # (code 内の位置, シンボル名) のリスト
    )

    再配置 (i, "name") の意味: code[i] の最初の引数を、シンボル name の「最終的な番地」で置き換える。
    例: code[3] が ("CALL", 0, 1) で、再配置 (3, "square") があれば、("CALL", <square の番地>, 1) にする。

======================================================================
リンクの手順（link が行うこと）
======================================================================

1. 配置: 出力の先頭に、スタートアップコード [("CALL", <entry の番地>, 0), ("HALT",)] の 2 命令を置く。
   その後ろに、モジュールを渡された順に並べる。各モジュールの先頭番地（ベース）が決まる。
   （本物の実行ファイルでも、main の前に _start などのスタートアップコードが実行されます）
2. シンボル解決: 全モジュールのグローバルシンボルについて「最終的な番地 = ベース + モジュール内の位置」の表を作る。
3. 再配置: 各モジュールの命令をコピーし、再配置情報に従って引数を書き換える。
   シンボル名は、まずそのモジュールの local_symbols から探し（ベース + 位置）、なければグローバルの表から探す。
   ローカルシンボルは他のモジュールからは見えないので、別のモジュールに同じ名前のローカルシンボルがあってもよい。

エラー（すべて LinkError。本物のリンカの「undefined reference」「multiple definition」にあたる）:
    - 同じグローバルシンボルが 2 つ以上のモジュールで定義されている
    - 再配置が参照するシンボルが、どこにも定義されていない
    - エントリポイント（entry）のシンボルが定義されていない
    - シンボルの位置や再配置の位置が、そのモジュールの code の範囲外
    - 再配置の位置の命令に、書き換える引数がない（("RET",) など）
"""
from __future__ import annotations

from dataclasses import dataclass, field

Instr = tuple


@dataclass
class ObjectModule:
    name: str
    code: list[Instr]
    symbols: dict[str, int] = field(default_factory=dict)
    local_symbols: dict[str, int] = field(default_factory=dict)
    relocations: list[tuple[int, str]] = field(default_factory=list)


class LinkError(Exception):
    """リンクの失敗（未定義のシンボル、重複定義、不正な再配置など）。"""


START_CODE_SIZE = 2  # 先頭に置くスタートアップコード: CALL entry, 0 / HALT


def link(modules: list[ObjectModule], entry: str = "main") -> tuple[list[Instr], dict[str, int]]:
    """モジュールをリンクし、(実行可能な命令列, グローバルシンボル → 最終的な番地 の辞書) を返す。

    - 返す命令列は stackvm.VM でそのまま実行できる。
    - 引数のモジュール（の code）は書き換えないこと（コピーしてから書き換える）。

    例（詳しくはテストを参照）:
        main = ObjectModule("main", [("PUSH", 7), ("CALL", 0, 1), ("RET",)],
                            symbols={"main": 0}, relocations=[(1, "square")])
        lib  = ObjectModule("mathlib", [("LOAD", 0), ("LOAD", 0), ("MUL",), ("RET",)],
                            symbols={"square": 0})
        code, table = link([main, lib])
        # table == {"main": 2, "square": 5}
        # code  == [("CALL", 2, 0), ("HALT",),
        #           ("PUSH", 7), ("CALL", 5, 1), ("RET",),
        #           ("LOAD", 0), ("LOAD", 0), ("MUL",), ("RET",)]
        # VM(code).run() == 49

    ヒント: 「全モジュールの配置を決める → シンボル表を作る → 書き換える」の順に、ループを分けて書く。
    書き換えの段階では、すべてのシンボルの番地が分かっている必要がある（前方参照があるため）。
    """
    raise NotImplementedError("演習5: link を実装してください")
