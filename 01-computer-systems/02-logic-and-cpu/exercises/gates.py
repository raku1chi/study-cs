"""1.2 論理回路と CPU の仕組み — 演習1: NAND だけで論理ゲートを作る（★☆☆）

NAND ゲートは「万能（universal）」です。NAND を組み合わせるだけで、どんな論理回路でも作れます。
この演習では、用意された nand() だけを部品にして、基本的なゲートを組み立てます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.2          # 1.2 章のすべての演習
    python3 tools/check.py -v 1.2       # 詳しい出力

このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_gates

制約（学びのための縛り）:
    - not_ / and_ / or_ / xor / mux の中で使ってよいのは、nand() と、この演習で自分が作った関数だけです。
      Python の and / or / not、& | ^ ~、+ - などの演算子、入力の値による if の場合分けは使わないでください。
    - テストは nand() の呼び出し回数を数えて、NAND で組み立てられているか、何個の NAND を使ったかを確かめます。
    - 値はすべて整数の 0 か 1 です。nand() は、それ以外の値が来ると ValueError を送出します。
"""
from __future__ import annotations

from typing import Callable


def nand(a: int, b: int) -> int:
    """唯一の部品。a と b がともに 1 のときだけ 0 を返す（この関数は変更しないでください）。

    | a | b | nand |
    |---|---|------|
    | 0 | 0 |  1   |
    | 0 | 1 |  1   |
    | 1 | 0 |  1   |
    | 1 | 1 |  0   |
    """
    if a not in (0, 1) or b not in (0, 1):
        raise ValueError(f"入力は 0 か 1 です: a={a!r}, b={b!r}")
    return 0 if (a == 1 and b == 1) else 1


def not_(a: int) -> int:
    """NOT。目標: NAND 1 個。

    >>> not_(0), not_(1)
    (1, 0)

    ヒント: NAND の 2 つの入力に、同じ信号をつないだらどうなるか。
    """
    raise NotImplementedError("演習1: not_ を実装してください")


def and_(a: int, b: int) -> int:
    """AND。目標: NAND 2 個。

    ヒント: NAND は「AND の否定」。
    """
    raise NotImplementedError("演習1: and_ を実装してください")


def or_(a: int, b: int) -> int:
    """OR。目標: NAND 3 個。

    ヒント: ド・モルガンの法則 a OR b = NOT(NOT a AND NOT b)。
    """
    raise NotImplementedError("演習1: or_ を実装してください")


def xor(a: int, b: int) -> int:
    """XOR（排他的論理和）。a と b が異なるとき 1。目標: NAND 4 個。

    ヒント: まず t = nand(a, b) を作り、それを 2 か所で使い回す。
    (a AND NOT b) OR (NOT a AND b) をそのまま組むと、NAND が 4 個より多く必要になる。
    """
    raise NotImplementedError("演習1: xor を実装してください")


def mux(sel: int, a: int, b: int) -> int:
    """2 入力マルチプレクサ。sel == 0 なら a を、sel == 1 なら b を出力する。目標: NAND 4 個。

    >>> mux(0, 1, 0), mux(1, 1, 0)
    (1, 0)

    ヒント: 論理式では (a AND NOT sel) OR (b AND sel)。
    OR をド・モルガンの法則で NAND に直すと、AND の後ろの NOT と打ち消し合う。
    """
    raise NotImplementedError("演習1: mux を実装してください")


def synthesize(table: list[int]) -> Callable[..., int]:
    """（発展）真理値表から、ゲートだけで計算する関数を作って返す。

    NAND の万能性を「どんな真理値表でも回路にできる」という形で確かめます。

    - table の長さは 2 のべき乗（2, 4, 8, …）で、入力の個数 n は log2(len(table))。
    - table[i] は、入力 (x0, x1, …, x_{n-1}) を、x0 を最上位ビットとする 2 進数として
      読んだ値が i のときの出力。例: n = 2 なら table = [f(0,0), f(0,1), f(1,0), f(1,1)]。
    - 返す関数は n 個の引数（0 か 1）を受け取り、出力（0 か 1）を返す。
      引数の個数が違う、または 0/1 以外の値のときは ValueError。
    - table の長さが 2 未満か 2 のべき乗でない、または値が 0/1 以外なら、synthesize 自体が ValueError。

    >>> f = synthesize([0, 1, 1, 0])     # XOR
    >>> f(1, 0), f(1, 1)
    (1, 0)
    >>> maj = synthesize([0, 0, 0, 1, 0, 1, 1, 1])   # 3 入力の多数決
    >>> maj(1, 0, 1)
    1

    ヒント（積和形）: 出力が 1 になる各行について「その行のときだけ 1 になる AND 項」を作り、
    それらをすべて OR でつなぐ。例えば 3 入力の行 5（= 101）の項は x0 AND NOT x1 AND x2。
    どの入力を反転するかは行番号から決まる（回路の配線を決めるだけ）ので、そこには Python の if や
    ループを使ってかまいません。ただし、返す関数が出力を計算する部分は、ゲートだけを通してください。
    """
    raise NotImplementedError("演習1（発展）: synthesize を実装してください")
