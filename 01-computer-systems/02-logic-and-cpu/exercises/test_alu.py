"""1.2 演習2 のテスト: 加算器と ALU

実行: python3 tools/check.py 1.2   （またはこのディレクトリで python3 -m unittest -v test_alu）
"""
import itertools
import random
import unittest

from alu import AluResult, alu, bits_to_int, full_adder, half_adder, int_to_bits, ripple_carry_add


def reference_alu(op: str, a: int, b: int, bits: int) -> AluResult:
    """答え合わせ用: 整数演算で ALU の結果とフラグを計算する。"""
    mask = (1 << bits) - 1

    def signed(x: int) -> int:
        return x - (1 << bits) if x >> (bits - 1) else x

    lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if op == "ADD":
        value = (a + b) & mask
        c = int(a + b > mask)
        v = int(not lo <= signed(a) + signed(b) <= hi)
    elif op == "SUB":
        value = (a - b) & mask
        c = int(a >= b)  # 借りが発生しなければ 1（ARM 方式）
        v = int(not lo <= signed(a) - signed(b) <= hi)
    else:
        value = {"AND": a & b, "OR": a | b, "XOR": a ^ b}[op]
        c = v = 0
    return AluResult(value, int(value == 0), value >> (bits - 1), c, v)


class TestExercise2Adders(unittest.TestCase):
    def test_half_adder(self):
        expected = {(0, 0): (0, 0), (0, 1): (1, 0), (1, 0): (1, 0), (1, 1): (0, 1)}
        for (a, b), out in expected.items():
            self.assertEqual(half_adder(a, b), out, f"half_adder({a}, {b})")

    def test_full_adder_all_8_cases(self):
        for a, b, cin in itertools.product((0, 1), repeat=3):
            total = a + b + cin
            self.assertEqual(full_adder(a, b, cin), (total & 1, total >> 1), f"full_adder({a}, {b}, {cin})")

    def test_ripple_carry_examples(self):
        self.assertEqual(ripple_carry_add([1, 1, 0, 0], [1, 0, 0, 0]), ([0, 0, 1, 0], 0))  # 3 + 1
        self.assertEqual(ripple_carry_add([1, 1, 1, 1], [1, 0, 0, 0]), ([0, 0, 0, 0], 1))  # 15 + 1
        self.assertEqual(ripple_carry_add([1], [1]), ([0], 1))
        self.assertEqual(ripple_carry_add([0, 0], [0, 0], carry_in=1), ([1, 0], 0))

    def test_ripple_carry_exhaustive_4_bits(self):
        for x in range(16):
            for y in range(16):
                for cin in (0, 1):
                    total = x + y + cin
                    out, carry = ripple_carry_add(int_to_bits(x, 4), int_to_bits(y, 4), cin)
                    self.assertEqual((bits_to_int(out), carry), (total & 15, total >> 4), (x, y, cin))
                    self.assertEqual(len(out), 4)

    def test_ripple_carry_64_bits_random(self):
        rng = random.Random(21)
        for _ in range(200):
            x, y = rng.getrandbits(64), rng.getrandbits(64)
            out, carry = ripple_carry_add(int_to_bits(x, 64), int_to_bits(y, 64))
            self.assertEqual(bits_to_int(out) + (carry << 64), x + y, (x, y))

    def test_ripple_carry_invalid(self):
        for a, b in [([1, 0], [1]), ([], []), ([2], [0]), ([0, 1], [1, -1])]:
            with self.assertRaises(ValueError, msg=f"{a} + {b}"):
                ripple_carry_add(a, b)


class TestExercise2Alu(unittest.TestCase):
    def test_docstring_examples(self):
        self.assertEqual(alu("ADD", 0x7F, 0x01), AluResult(128, 0, 1, 0, 1))
        self.assertEqual(alu("ADD", 0xFF, 0x01), AluResult(0, 1, 0, 1, 0))
        self.assertEqual(alu("SUB", 3, 5), AluResult(254, 0, 1, 0, 0))

    def test_signed_overflow_on_subtraction(self):
        # -128 - 1 = -129 は 8 ビットに収まらない → 127 に回り込み、V=1
        self.assertEqual(alu("SUB", 0x80, 0x01), AluResult(0x7F, 0, 0, 1, 1))
        # 127 - (-1) = 128 も収まらない
        self.assertEqual(alu("SUB", 0x7F, 0xFF), AluResult(0x80, 0, 1, 0, 1))

    def test_compare_equal_sets_z(self):
        # CMP 命令は SUB の結果を捨ててフラグだけを残す。等しければ Z=1、借りなし C=1
        self.assertEqual(alu("SUB", 42, 42), AluResult(0, 1, 0, 1, 0))

    def test_logic_ops_clear_c_and_v(self):
        self.assertEqual(alu("AND", 0b1100, 0b1010, bits=4), AluResult(0b1000, 0, 1, 0, 0))
        self.assertEqual(alu("OR", 0b1100, 0b1010, bits=4), AluResult(0b1110, 0, 1, 0, 0))
        self.assertEqual(alu("XOR", 0b1010, 0b1010, bits=4), AluResult(0, 1, 0, 0, 0))

    def test_exhaustive_4_bits(self):
        for op in ("ADD", "SUB", "AND", "OR", "XOR"):
            for a in range(16):
                for b in range(16):
                    self.assertEqual(alu(op, a, b, bits=4), reference_alu(op, a, b, 4), f"{op} {a}, {b}")

    def test_random_wider_widths(self):
        rng = random.Random(22)
        for bits in (1, 8, 16, 32, 64):
            for _ in range(60):
                op = rng.choice(["ADD", "SUB", "AND", "OR", "XOR"])
                a, b = rng.getrandbits(bits), rng.getrandbits(bits)
                self.assertEqual(alu(op, a, b, bits=bits), reference_alu(op, a, b, bits), f"{op} {a}, {b} ({bits} bits)")

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            alu("MUL", 1, 2)
        with self.assertRaises(ValueError):
            alu("ADD", 256, 0)       # 8 ビットに収まらない
        with self.assertRaises(ValueError):
            alu("ADD", -1, 0)        # 負の数ではなくビットパターン（0xFF）で渡す
        with self.assertRaises(ValueError):
            alu("ADD", 0, 0, bits=0)


if __name__ == "__main__":
    unittest.main()
