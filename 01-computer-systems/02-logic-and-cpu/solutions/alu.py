"""1.2 論理回路と CPU の仕組み — 演習2 解答例: 加算器と ALU

仕様は exercises/alu.py の docstring を参照してください。
ハードウェアと同じく「ビットごとの論理演算」と「桁上がりの受け渡し」だけで加算・減算を組み立てます。
"""
from __future__ import annotations

from typing import NamedTuple

Bits = list[int]


def int_to_bits(x: int, width: int) -> Bits:
    """0 <= x < 2**width の整数を、下位ビットが先頭のビット列にする（用意済み）。"""
    if width <= 0:
        raise ValueError(f"width は 1 以上: {width}")
    if not 0 <= x < (1 << width):
        raise ValueError(f"{x} は {width} ビットの符号なし整数の範囲外です")
    return [(x >> i) & 1 for i in range(width)]


def bits_to_int(bits: Bits) -> int:
    """下位ビットが先頭のビット列を、符号なし整数に戻す（用意済み）。"""
    return sum(bit << i for i, bit in enumerate(bits))


def half_adder(a: int, b: int) -> tuple[int, int]:
    # 和は「どちらか一方だけが 1」= XOR、桁上がりは「両方 1」= AND
    return a ^ b, a & b


def full_adder(a: int, b: int, carry_in: int) -> tuple[int, int]:
    # 半加算器 2 個と OR 1 個で作る（教科書どおりの構成）
    s1, c1 = half_adder(a, b)
    s2, c2 = half_adder(s1, carry_in)
    return s2, c1 | c2


def ripple_carry_add(a: Bits, b: Bits, carry_in: int = 0) -> tuple[Bits, int]:
    if len(a) != len(b) or not a:
        raise ValueError(f"同じ長さ（1 以上）のビット列を渡してください: {len(a)} と {len(b)}")
    for bit in (*a, *b, carry_in):
        if bit not in (0, 1):
            raise ValueError(f"ビットは 0 か 1 です: {bit!r}")
    result: Bits = []
    carry = carry_in
    # 下位ビットから順に、桁上がりをバケツリレーのように次の全加算器へ渡す。
    # ハードウェアでは、最上位ビットの和が確定するまでに n 段ぶんの遅延がかかる（リップルキャリー）
    for x, y in zip(a, b):
        s, carry = full_adder(x, y, carry)
        result.append(s)
    return result, carry


class AluResult(NamedTuple):
    value: int  # 結果のビットパターン（0 〜 2**bits - 1）
    z: int      # Zero: 結果が 0
    n: int      # Negative: 結果の最上位ビット（符号付きとして見たとき負）
    c: int      # Carry: 加算器の最上位からの桁上がり
    v: int      # oVerflow: 符号付きとして見たときのオーバーフロー


OPS = ("ADD", "SUB", "AND", "OR", "XOR")


def alu(op: str, a: int, b: int, bits: int = 8) -> AluResult:
    if bits <= 0:
        raise ValueError(f"bits は 1 以上: {bits}")
    if op not in OPS:
        raise ValueError(f"未知の演算です: {op!r}（{', '.join(OPS)} のいずれか）")
    a_bits = int_to_bits(a, bits)  # 範囲外なら ValueError
    b_bits = int_to_bits(b, bits)

    c = v = 0
    if op in ("ADD", "SUB"):
        if op == "SUB":
            # a - b = a + (b のビット反転) + 1。2 の補数のおかげで加算器をそのまま使える
            b_bits = [1 - bit for bit in b_bits]
            carry_in = 1
        else:
            carry_in = 0
        out_bits, c = ripple_carry_add(a_bits, b_bits, carry_in)
        # 同じ符号の数を足したのに結果の符号が変わったら符号付きオーバーフロー
        # （「最上位ビットへの桁上がり」と「最上位ビットからの桁上がり」が異なる、と同値）
        sign_a, sign_b, sign_r = a_bits[-1], b_bits[-1], out_bits[-1]
        v = int(sign_a == sign_b and sign_r != sign_a)
    elif op == "AND":
        out_bits = [x & y for x, y in zip(a_bits, b_bits)]
    elif op == "OR":
        out_bits = [x | y for x, y in zip(a_bits, b_bits)]
    else:  # XOR
        out_bits = [x ^ y for x, y in zip(a_bits, b_bits)]

    value = bits_to_int(out_bits)
    z = int(value == 0)
    n = out_bits[-1]
    return AluResult(value, z, n, c, v)
