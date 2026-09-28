"""1.2 論理回路と CPU の仕組み — 演習1 解答例: NAND だけで論理ゲートを作る

仕様は exercises/gates.py の docstring を参照してください。
各ゲートの右に、使っている NAND の個数を書いています。
"""
from __future__ import annotations

from typing import Callable


def nand(a: int, b: int) -> int:
    """唯一の部品。a と b がともに 1 のときだけ 0 を返す（演習でも変更しない）。"""
    if a not in (0, 1) or b not in (0, 1):
        raise ValueError(f"入力は 0 か 1 です: a={a!r}, b={b!r}")
    return 0 if (a == 1 and b == 1) else 1


def not_(a: int) -> int:
    # NAND の 2 つの入力に同じ信号をつなぐ: NAND(a, a) = NOT(a AND a) = NOT a   … 1 個
    return nand(a, a)


def and_(a: int, b: int) -> int:
    # AND = NOT(NAND)                                                        … 2 個
    return not_(nand(a, b))


def or_(a: int, b: int) -> int:
    # ド・モルガン: a OR b = NOT(NOT a AND NOT b) = NAND(NOT a, NOT b)        … 3 個
    return nand(not_(a), not_(b))


def xor(a: int, b: int) -> int:
    # 定番の 4 NAND 構成。t = NAND(a, b) を共有するのがポイント              … 4 個
    #   a=1,b=0 のとき t=1 → NAND(a,t)=0, NAND(b,t)=1 → 出力 1
    #   a=b=1   のとき t=0 → NAND(a,t)=1, NAND(b,t)=1 → 出力 0
    t = nand(a, b)
    return nand(nand(a, t), nand(b, t))


def mux(sel: int, a: int, b: int) -> int:
    # (a AND NOT sel) OR (b AND sel) を、ド・モルガンで NAND 2 段に直したもの  … 4 個
    #   = NAND(NAND(a, NOT sel), NAND(b, sel))
    return nand(nand(a, not_(sel)), nand(b, sel))


def synthesize(table: list[int]) -> Callable[..., int]:
    """真理値表から、ゲートだけで計算する関数を作る（積和形 = 最小項の OR）。"""
    size = len(table)
    if size < 2 or size & (size - 1):
        raise ValueError(f"真理値表の長さは 2 以上の 2 のべき乗です: {size}")
    if any(v not in (0, 1) for v in table):
        raise ValueError("真理値表の値は 0 か 1 です")
    n_inputs = size.bit_length() - 1

    # 出力が 1 になる行（最小項）の番号だけを覚えておく。ここは「回路の設計」なので Python の if を使ってよい
    minterms = [row for row, out in enumerate(table) if out == 1]

    def circuit(*inputs: int) -> int:
        # 入力の検査（回路の外側の約束ごと）。論理の計算そのものはゲートだけで行う
        if len(inputs) != n_inputs:
            raise ValueError(f"入力は {n_inputs} 個です: {len(inputs)} 個が渡されました")
        if any(x not in (0, 1) for x in inputs):
            raise ValueError(f"入力は 0 か 1 です: {inputs!r}")
        result = 0  # 1 になる行が 1 つもなければ常に 0（ハードウェアなら GND につなぐだけ）
        for i, row in enumerate(minterms):
            # 行番号のビットを見て、各入力をそのまま使うか反転して使うかを決める（配線を決めるだけ）
            term = 0
            for k, x in enumerate(inputs):
                bit = (row >> (n_inputs - 1 - k)) & 1  # 最初の引数が最上位ビット
                literal = x if bit == 1 else not_(x)
                term = literal if k == 0 else and_(term, literal)
            result = term if i == 0 else or_(result, term)
        return result

    return circuit
