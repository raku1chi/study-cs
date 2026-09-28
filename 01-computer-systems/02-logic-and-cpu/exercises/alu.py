"""1.2 論理回路と CPU の仕組み — 演習2: 加算器と ALU（★★☆）

1 ビットの加算器を組み合わせて多ビットの加算器を作り、それを使って ALU（算術論理演算装置）を作ります。
ALU は演算結果と一緒に 4 つのフラグ（Z/N/C/V）を出力します。1.1 章の 2 の補数とオーバーフローの復習でもあります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.2
このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_alu

ビット列の表し方（重要）:
    ビット列は「下位ビットが先頭」のリスト（LSB first）で表します。bits[i] が 2^i の桁です。
        6 = 0b0110 を 4 ビットで表すと [0, 1, 1, 0]
    int_to_bits / bits_to_int は用意済みです。

制約（学びのための縛り）:
    - half_adder / full_adder では、+ や - を使わず、ビット演算（& | ^）だけで計算してください
      （演習1 の gates.py を import して使ってもかまいません）。
    - ripple_carry_add では full_adder を下位ビットから順につなげて計算し、整数の + は使わないでください。
    - alu の ADD / SUB は ripple_carry_add を使って計算してください（SUB は「ビット反転して 1 を足す」）。
"""
from __future__ import annotations

from typing import NamedTuple

Bits = list[int]


def int_to_bits(x: int, width: int) -> Bits:
    """0 <= x < 2**width の整数を、下位ビットが先頭のビット列にする（用意済み）。

    >>> int_to_bits(6, 4)
    [0, 1, 1, 0]
    """
    if width <= 0:
        raise ValueError(f"width は 1 以上: {width}")
    if not 0 <= x < (1 << width):
        raise ValueError(f"{x} は {width} ビットの符号なし整数の範囲外です")
    return [(x >> i) & 1 for i in range(width)]


def bits_to_int(bits: Bits) -> int:
    """下位ビットが先頭のビット列を、符号なし整数に戻す（用意済み）。

    >>> bits_to_int([0, 1, 1, 0])
    6
    """
    return sum(bit << i for i, bit in enumerate(bits))


# ---------------------------------------------------------------------------
# 演習2a: 1 ビットの加算器
# ---------------------------------------------------------------------------

def half_adder(a: int, b: int) -> tuple[int, int]:
    """半加算器。1 ビットの a と b を足し、(和, 桁上がり) を返す。

    | a | b | 和 | 桁上がり |
    |---|---|----|----------|
    | 0 | 0 | 0  | 0        |
    | 0 | 1 | 1  | 0        |
    | 1 | 0 | 1  | 0        |
    | 1 | 1 | 0  | 1        |
    """
    raise NotImplementedError("演習2: half_adder を実装してください")


def full_adder(a: int, b: int, carry_in: int) -> tuple[int, int]:
    """全加算器。a + b + carry_in（それぞれ 0 か 1）を計算し、(和, 桁上がり) を返す。

    >>> full_adder(1, 1, 1)
    (1, 1)

    ヒント: 半加算器 2 個と OR 1 個で作れる。和は 3 つの XOR、桁上がりは「2 つ以上が 1」。
    """
    raise NotImplementedError("演習2: full_adder を実装してください")


# ---------------------------------------------------------------------------
# 演習2b: リップルキャリー加算器
# ---------------------------------------------------------------------------

def ripple_carry_add(a: Bits, b: Bits, carry_in: int = 0) -> tuple[Bits, int]:
    """同じ長さのビット列 a と b（下位ビットが先頭）を足し、(和のビット列, 最上位からの桁上がり) を返す。

    - 和のビット列の長さは入力と同じ（あふれた桁は桁上がりとして返す）。
    - 長さが違う、長さが 0、または 0/1 以外の値を含む場合は ValueError。

    >>> ripple_carry_add([1, 1, 0, 0], [1, 0, 0, 0])     # 3 + 1 = 4
    ([0, 0, 1, 0], 0)
    >>> ripple_carry_add([1, 1, 1, 1], [1, 0, 0, 0])     # 15 + 1 = 16 → 4 ビットでは 0、桁上がり 1
    ([0, 0, 0, 0], 1)
    """
    raise NotImplementedError("演習2: ripple_carry_add を実装してください")


# ---------------------------------------------------------------------------
# 演習2c: フラグ付きの ALU
# ---------------------------------------------------------------------------

class AluResult(NamedTuple):
    value: int  # 結果のビットパターン（0 〜 2**bits - 1）
    z: int      # Zero: 結果が 0 なら 1
    n: int      # Negative: 結果の最上位ビット（符号付きとして見たとき負なら 1）
    c: int      # Carry: 加算器の最上位ビットからの桁上がり
    v: int      # oVerflow: 符号付きとして見たときにオーバーフローしたら 1


def alu(op: str, a: int, b: int, bits: int = 8) -> AluResult:
    """bits ビットの ALU。a と b はビットパターン（0 〜 2**bits - 1 の符号なし整数）で渡す。

    op は "ADD", "SUB", "AND", "OR", "XOR" のいずれか。

    - value: 演算結果の下位 bits ビット。
    - z: value == 0 なら 1。  n: value の最上位ビット。
    - ADD: c は a + b の最上位からの桁上がり（符号なしとして見たときの桁あふれ）。
           v は符号付きとして見たときのオーバーフロー。
    - SUB: a + (b のビット反転) + 1 として計算する。c はその加算の桁上がりで、
           「符号なしとして a >= b（借りが発生しなかった）」なら 1 になる。
           （これは ARM と同じ規約。x86 はこれを反転した「借りがあったら 1」を CF に入れる）
           v は a - b が符号付きの範囲に収まらなければ 1。
    - AND / OR / XOR: ビットごとの演算。c と v は 0。
    - a, b が範囲外、bits <= 0、未知の op のときは ValueError。

    >>> alu("ADD", 0x7F, 0x01)       # 127 + 1: 符号付きではオーバーフロー
    AluResult(value=128, z=0, n=1, c=0, v=1)
    >>> alu("ADD", 0xFF, 0x01)       # 255 + 1: 符号なしでは桁あふれ（-1 + 1 = 0 なので v=0）
    AluResult(value=0, z=1, n=0, c=1, v=0)
    >>> alu("SUB", 3, 5)             # 3 - 5 = -2 = 0xFE。借りが発生したので c=0
    AluResult(value=254, z=0, n=1, c=0, v=0)

    ヒント（V フラグ）: 加算器に入る 2 つの数（SUB なら反転後の b）の符号ビットが等しいのに、
    結果の符号ビットがそれと異なれば、符号付きオーバーフロー。
    """
    raise NotImplementedError("演習2: alu を実装してください")
