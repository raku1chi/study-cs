"""1.2 演習1 のテスト: NAND だけで論理ゲートを作る

実行: python3 tools/check.py 1.2   （またはこのディレクトリで python3 -m unittest -v test_gates）
"""
import itertools
import random
import unittest
from unittest import mock

import gates

ORIGINAL_NAND = gates.nand


class CountingNand:
    """nand の呼び出し回数を数える差し替え用の部品。"""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, a: int, b: int) -> int:
        self.calls += 1
        return ORIGINAL_NAND(a, b)


def count_nands(func, *args):
    """func(*args) を実行し、(結果, nand の呼び出し回数) を返す。"""
    counter = CountingNand()
    with mock.patch.object(gates, "nand", counter):
        result = func(*args)
    return result, counter.calls


class TestExercise1Gates(unittest.TestCase):
    def test_nand_is_unchanged(self):
        self.assertEqual([gates.nand(a, b) for a in (0, 1) for b in (0, 1)], [1, 1, 1, 0])

    def test_not_truth_table(self):
        self.assertEqual(gates.not_(0), 1)
        self.assertEqual(gates.not_(1), 0)

    def test_and_or_xor_truth_tables(self):
        for a, b in itertools.product((0, 1), repeat=2):
            self.assertEqual(gates.and_(a, b), a & b, f"AND({a}, {b})")
            self.assertEqual(gates.or_(a, b), a | b, f"OR({a}, {b})")
            self.assertEqual(gates.xor(a, b), a ^ b, f"XOR({a}, {b})")

    def test_mux_truth_table(self):
        for sel, a, b in itertools.product((0, 1), repeat=3):
            self.assertEqual(gates.mux(sel, a, b), b if sel else a, f"mux(sel={sel}, a={a}, b={b})")

    def test_results_are_ints_not_bools(self):
        self.assertIs(type(gates.and_(1, 1)), int)
        self.assertIs(type(gates.xor(1, 0)), int)

    def test_gates_are_built_from_nand(self):
        # nand を 1 回も呼ばずに正しい値を返している場合（Python の演算子を使った場合）を検出する
        arity = {"not_": 1, "and_": 2, "or_": 2, "xor": 2, "mux": 3}
        for name, n_args in arity.items():
            func = getattr(gates, name)
            for args in itertools.product((0, 1), repeat=n_args):
                _, calls = count_nands(func, *args)
                self.assertGreater(calls, 0, f"{name}{args} は nand() を使って組み立ててください")

    def test_gate_counts_are_minimal(self):
        limits = {"not_": 1, "and_": 2, "or_": 3, "xor": 4, "mux": 4}
        for name, limit in limits.items():
            func = getattr(gates, name)
            n_args = 3 if name == "mux" else (1 if name == "not_" else 2)
            worst = max(count_nands(func, *args)[1] for args in itertools.product((0, 1), repeat=n_args))
            self.assertLessEqual(
                worst, limit,
                f"{name} は NAND {limit} 個で作れます（現在 {worst} 個）。docstring のヒントを参照",
            )

    def test_invalid_inputs_are_rejected_by_nand(self):
        for func, args in [(gates.not_, (2,)), (gates.and_, (1, 2)), (gates.or_, (-1, 0)),
                           (gates.xor, (0, 5)), (gates.mux, (2, 0, 1))]:
            with self.assertRaises(ValueError, msg=f"{func.__name__}{args}"):
                func(*args)


class TestExercise1Synthesize(unittest.TestCase):
    def check_table(self, table):
        n = len(table).bit_length() - 1
        f = gates.synthesize(table)
        for row, inputs in enumerate(itertools.product((0, 1), repeat=n)):
            self.assertEqual(f(*inputs), table[row], f"table={table} inputs={inputs}")

    def test_xor_and_majority(self):
        self.check_table([0, 1, 1, 0])
        self.check_table([0, 0, 0, 1, 0, 1, 1, 1])

    def test_all_two_input_functions(self):
        # 2 入力の論理関数は 2^4 = 16 種類しかない。すべて作れることを確かめる
        for bits in itertools.product((0, 1), repeat=4):
            self.check_table(list(bits))

    def test_random_tables(self):
        rng = random.Random(12)
        for n in range(1, 5):
            for _ in range(20):
                self.check_table([rng.randrange(2) for _ in range(2**n)])

    def test_synthesized_circuit_uses_nand(self):
        f = gates.synthesize([0, 1, 1, 0])
        counter = CountingNand()
        with mock.patch.object(gates, "nand", counter):
            self.assertEqual(f(1, 0), 1)
        self.assertGreater(counter.calls, 0, "返す関数は、ゲート（nand）を通して出力を計算してください")

    def test_invalid_tables(self):
        for table in ([], [1], [0, 1, 1], [0, 2], [0, 1, 1, 0, 1]):
            with self.assertRaises(ValueError, msg=f"table={table}"):
                gates.synthesize(table)

    def test_invalid_call(self):
        f = gates.synthesize([0, 1, 1, 0])
        with self.assertRaises(ValueError):
            f(1)
        with self.assertRaises(ValueError):
            f(1, 0, 1)
        with self.assertRaises(ValueError):
            f(1, 2)


if __name__ == "__main__":
    unittest.main()
