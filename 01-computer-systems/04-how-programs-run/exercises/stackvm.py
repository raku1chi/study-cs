"""1.4 プログラムが動く仕組み — 演習1〜4: スタックマシン型の仮想マシン（VM）

CPython や JVM、WebAssembly のような「バイトコードを実行する仮想マシン」の核を作ります。
1.2 章の TinyCPU はレジスタを持つハードウェアの CPU でしたが、ここで作るのは値をスタックに積んで
計算する「スタックマシン」で、関数呼び出しのためのフレーム（ローカル変数と戻り番地）を持ちます。

    演習1（★★☆）: VM 本体（フェッチ・デコード・実行、フレームによる関数呼び出し）   VM.step, VM.run
    演習2（★☆☆）: 呼び出しの深さの上限と StackOverflowError                        VM.step の CALL
    演習3（★★☆）: ラベル付きのアセンブリを命令列に変換するアセンブラ               assemble
    演習4（★★☆）: VM のプログラムを書く（階乗の反復版・再帰版、フィボナッチ数）   factorial_iterative ほか

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.4
このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_stackvm

======================================================================
VM の仕様
======================================================================

命令（Instr）は「命令名, 引数…」のタプルです。プログラムは命令のリストで、番地は 0 始まりの添字です。
    例: [("PUSH", 2), ("PUSH", 3), ("ADD",), ("HALT",)]   → 実行すると 5 が残る

フレーム（Frame）: 関数の呼び出しごとに 1 つ作る。
    - locals: ローカル変数（NUM_LOCALS = 16 個、0 で初期化）。引数もここに入る。
    - stack : オペランドスタック（計算の途中の値を積む）。フレームごとに別々。
    - return_address: RET で戻る番地。
  VM を作った時点で、最初のフレーム（戻り先のない「メイン」のフレーム）が 1 つある。
  以下の説明の「スタック」は、今実行中のフレーム（frames の末尾）のスタックのこと。

| 命令           | 動作                                                                          |
|----------------|-------------------------------------------------------------------------------|
| PUSH n         | n を積む                                                                      |
| POP            | 1 つ取り除く                                                                  |
| ADD/SUB/MUL    | b を取り出し、a を取り出し、a + b / a - b / a * b を積む（b が先に取り出される） |
| DIV/MOD        | 同じく a // b、a % b を積む（Python の // と % と同じ切り捨て）。b == 0 はエラー |
| EQ/LT          | 同じく a == b、a < b なら 1、そうでなければ 0 を積む                          |
| DUP            | 一番上の値を複製して積む                                                      |
| SWAP           | 上の 2 つを入れ替える                                                         |
| JMP addr       | addr へ飛ぶ                                                                   |
| JZ addr        | 1 つ取り出し、それが 0 なら addr へ飛ぶ                                       |
| LOAD i         | locals[i] を積む                                                              |
| STORE i        | 1 つ取り出して locals[i] に入れる                                             |
| CALL addr, k   | 新しいフレームを作り、呼び出し側のスタックの上から k 個の値を取り出して、       |
|                | 積んだ順に locals[0], …, locals[k-1] へ入れる（最後に積んだ値が locals[k-1]）。|
|                | 戻り番地は CALL の次の番地。そして addr へ飛ぶ                                 |
| RET            | 今のスタックから戻り値を 1 つ取り出し、フレームを捨て、呼び出し側のスタックに   |
|                | 戻り値を積んで、戻り番地へ飛ぶ                                               |
| HALT           | 停止する                                                                      |

エラー（すべて VMError）: スタックが空なのに取り出そうとした、未知の命令・引数の個数の誤り・整数でない引数、
PC が範囲外、0 除算、ローカル変数の番号が範囲外、CALL の引数の個数が 0〜16 の範囲外またはスタックに足りない、
最初のフレームで RET した、ステップ数の上限を超えた。
"""
from __future__ import annotations

import re  # noqa: F401  演習3 で使えます
from dataclasses import dataclass, field
from typing import Optional

Instr = tuple  # ("PUSH", 5) のような「命令名, 引数…」のタプル

NUM_LOCALS = 16

# 命令名 → 引数の個数
ARITY = {
    "PUSH": 1, "POP": 0, "ADD": 0, "SUB": 0, "MUL": 0, "DIV": 0, "MOD": 0,
    "DUP": 0, "SWAP": 0, "JMP": 1, "JZ": 1, "EQ": 0, "LT": 0,
    "LOAD": 1, "STORE": 1, "CALL": 2, "RET": 0, "HALT": 0,
}


class VMError(Exception):
    """実行時のエラー（スタックの空読み、不正な命令、0 除算、ステップ数の超過など）。"""


class StackOverflowError(VMError):
    """呼び出しの深さが上限を超えた（演習2）。"""


class AssemblerError(ValueError):
    """アセンブリのソースの誤り。メッセージは「行 N: 」で始める（演習3）。"""


@dataclass
class Frame:
    return_address: int                                      # RET で戻る番地（最初のフレームは -1）
    locals: list[int] = field(default_factory=lambda: [0] * NUM_LOCALS)
    stack: list[int] = field(default_factory=list)          # このフレームのオペランドスタック


# ---------------------------------------------------------------------------
# 演習1（★★☆）・演習2（★☆☆）: VM 本体
# ---------------------------------------------------------------------------

class VM:
    """スタックマシン。__init__ は用意済みです（状態の定義そのものが仕様）。"""

    def __init__(self, code: list[Instr], max_depth: int = 1000, max_steps: int = 1_000_000) -> None:
        self.code = list(code)
        self.max_depth = max_depth      # フレームの数（呼び出しの深さ）の上限。最初のフレームも 1 と数える
        self.max_steps = max_steps      # 実行する命令数の上限（無限ループ対策）
        self.frames: list[Frame] = [Frame(return_address=-1)]
        self.pc = 0
        self.steps = 0                  # これまでに実行した命令数
        self.halted = False

    @property
    def frame(self) -> Frame:
        """今実行中のフレーム。"""
        return self.frames[-1]

    def step(self) -> None:
        """命令を 1 つ実行する。

        1. フェッチ: code[pc] を読む（pc が範囲外なら VMError）。形式を確かめる（ARITY を使う）。
        2. pc を 1 進める。
        3. モジュールの docstring の表に従って実行する（ジャンプ・CALL・RET は pc を書き換える）。
        4. steps を 1 増やす。
        すでに停止しているのに呼ばれたら VMError。

        演習2: CALL で新しいフレームを積むと、フレームの数が max_depth を超える場合は、
        積む前に StackOverflowError を送出する。例えば max_depth=3 なら、最初のフレームから
        2 段までは呼べて、3 段目の CALL がエラーになる。

        ヒント: 関数呼び出しを Python の再帰（step の中で別の run を呼ぶなど）で実装しないこと。
        フレームは self.frames というリストに積み、ループ 1 つで実行し続ける。そうしないと、
        深い再帰のプログラムで Python 自身のスタック（再帰の上限）が先に尽きてしまう。
        """
        raise NotImplementedError("演習1: VM.step を実装してください")

    def run(self) -> Optional[int]:
        """HALT するまで step() を繰り返し、そのときのスタックの一番上の値を返す（空なら None）。

        - 実行した命令の総数（steps）が max_steps に達しても停止していなければ VMError。

        >>> VM([("PUSH", 2), ("PUSH", 3), ("ADD",), ("HALT",)]).run()
        5
        >>> VM([("PUSH", 7), ("PUSH", 2), ("SUB",), ("HALT",)]).run()     # 7 - 2（b が先に取り出される）
        5
        """
        raise NotImplementedError("演習1: VM.run を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: アセンブラ
# ---------------------------------------------------------------------------

def assemble(source: str) -> list[Instr]:
    """VM のアセンブリ言語を、命令のタプルのリストに変換する。

    文法:
        - 1 行に 1 命令。空行は無視。「;」から行末まではコメント。
        - 行頭の「名前:」はラベルの定義（値はその次の命令の番地）。ラベルだけの行も、
          同じ行に命令が続く行も書ける。名前は英字か _ で始まり、英数字と _ が続く（大文字小文字を区別）。
        - 命令名は大文字小文字を区別しない（出力のタプルでは大文字にする）。
        - 引数はカンマで区切る。引数は整数（負も可）か、ラベル名（その番地に置き換える）。
            例: "CALL fact, 1" → ("CALL", <fact の番地>, 1)

    - 誤りは AssemblerError（メッセージは「行 N: 」で始める）: 未知の命令、引数の個数の誤り、
      未定義のラベル、ラベルの重複、整数でもラベル名でもない引数。

    >>> assemble("PUSH 1\\nloop: PUSH 2\\nJMP loop")
    [('PUSH', 1), ('PUSH', 2), ('JMP', 1)]

    ヒント: 1.2 章の演習4（TinyCPU のアセンブラ）と同じく、2 パスで作る。
    """
    raise NotImplementedError("演習3: assemble を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: VM のプログラムを書く
# ---------------------------------------------------------------------------
# 各関数は、n を埋め込んだプログラム（命令のリスト）を返す。VM(code).run() の戻り値が答えになること。
# assemble を使って、f 文字列でアセンブリを組み立ててもよいし、タプルのリストを直接書いてもよい。

def factorial_iterative(n: int) -> list[Instr]:
    """n!（n >= 0、0! = 1）をループで計算するプログラム。CALL を使わないこと。"""
    raise NotImplementedError("演習4: factorial_iterative を実装してください")


def factorial_recursive(n: int) -> list[Instr]:
    """n! を、fact(n) = n * fact(n - 1)（n < 2 なら 1）という再帰関数で計算するプログラム。

    メインの部分は n を積んで CALL し、戻り値を残したまま HALT する。
    関数 fact は引数を locals[0] で受け取り、RET で結果を返す。
    """
    raise NotImplementedError("演習4: factorial_recursive を実装してください")


def fibonacci(n: int) -> list[Instr]:
    """フィボナッチ数 F(n)（F(0) = 0、F(1) = 1、F(n) = F(n-1) + F(n-2)）を計算するプログラム。

    反復でも再帰でもよいが、n = 30 程度まで max_steps（100 万）以内に終わること。
    """
    raise NotImplementedError("演習4: fibonacci を実装してください")
