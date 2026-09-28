"""1.1 情報の表現 — テスト

実行: python3 tools/check.py 1.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import struct
import unittest

from datarep import (
    add_signed,
    classify_float,
    fields_to_float,
    float_fields,
    from_base,
    from_twos_complement,
    to_base,
    to_twos_complement,
    utf8_decode,
    utf8_encode,
)


class TestExercise1Base(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(to_base(10, 2), "1010")
        self.assertEqual(to_base(255, 16), "ff")
        self.assertEqual(to_base(8, 8), "10")
        self.assertEqual(to_base(0, 2), "0")
        self.assertEqual(to_base(0, 16), "0")

    def test_matches_builtin_formatting(self):
        rng = random.Random(11)
        for _ in range(300):
            n = rng.randrange(0, 2**64)
            self.assertEqual(to_base(n, 2), format(n, "b"), n)
            self.assertEqual(to_base(n, 8), format(n, "o"), n)
            self.assertEqual(to_base(n, 16), format(n, "x"), n)
            base = rng.randrange(2, 17)
            self.assertEqual(int(to_base(n, base), base), n, (n, base))

    def test_from_base_examples(self):
        self.assertEqual(from_base("1010", 2), 10)
        self.assertEqual(from_base("ff", 16), 255)
        self.assertEqual(from_base("FF", 16), 255)
        self.assertEqual(from_base("777", 8), 511)
        self.assertEqual(from_base("0", 10), 0)

    def test_from_base_matches_int(self):
        rng = random.Random(12)
        for _ in range(300):
            n = rng.randrange(0, 2**64)
            base = rng.randrange(2, 17)
            s = to_base_reference(n, base)
            if rng.random() < 0.5:
                s = s.upper()
            self.assertEqual(from_base(s, base), int(s, base), (s, base))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            to_base(-1, 2)
        for bad_base in (0, 1, 17):
            with self.assertRaises(ValueError):
                to_base(10, bad_base)
            with self.assertRaises(ValueError):
                from_base("1", bad_base)
        for s, base in [("2", 2), ("9", 8), ("g", 16), ("", 10), ("1 0", 10), ("-1", 10)]:
            with self.assertRaises(ValueError, msg=f"from_base({s!r}, {base})"):
                from_base(s, base)


def to_base_reference(n: int, base: int) -> str:
    digits = "0123456789abcdef"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, base)
        out.append(digits[r])
    return "".join(reversed(out))


class TestExercise2TwosComplement(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(to_twos_complement(5, 8), "00000101")
        self.assertEqual(to_twos_complement(-1, 8), "11111111")
        self.assertEqual(to_twos_complement(-128, 8), "10000000")
        self.assertEqual(to_twos_complement(127, 8), "01111111")
        self.assertEqual(to_twos_complement(0, 4), "0000")
        self.assertEqual(to_twos_complement(-1, 1), "1")

    def test_from_examples(self):
        self.assertEqual(from_twos_complement("11111111"), -1)
        self.assertEqual(from_twos_complement("10000000"), -128)
        self.assertEqual(from_twos_complement("0111"), 7)
        self.assertEqual(from_twos_complement("1000"), -8)
        self.assertEqual(from_twos_complement("0"), 0)

    def test_round_trip_all_values_up_to_8_bits(self):
        for bits in range(1, 9):
            for n in range(-(2 ** (bits - 1)), 2 ** (bits - 1)):
                s = to_twos_complement(n, bits)
                self.assertEqual(len(s), bits, (n, bits))
                self.assertEqual(s, format(n & (2**bits - 1), f"0{bits}b"), (n, bits))
                self.assertEqual(from_twos_complement(s), n, (n, bits))

    def test_int32_limits(self):
        self.assertEqual(to_twos_complement(2**31 - 1, 32), "0" + "1" * 31)
        self.assertEqual(to_twos_complement(-(2**31), 32), "1" + "0" * 31)

    def test_out_of_range(self):
        with self.assertRaises(OverflowError):
            to_twos_complement(128, 8)
        with self.assertRaises(OverflowError):
            to_twos_complement(-129, 8)
        with self.assertRaises(ValueError):
            to_twos_complement(0, 0)
        for bad in ("", "102", "1a"):
            with self.assertRaises(ValueError):
                from_twos_complement(bad)


class TestExercise3AddSigned(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(add_signed(100, 27, 8), (127, False))
        self.assertEqual(add_signed(127, 1, 8), (-128, True))
        self.assertEqual(add_signed(-128, -1, 8), (127, True))
        self.assertEqual(add_signed(100, -50, 8), (50, False))
        self.assertEqual(add_signed(-100, -28, 8), (-128, False))

    def test_int32_overflow_like_c_and_java(self):
        # Java の int や、多くの環境での C の int32_t（※C の符号付きオーバーフローは未定義動作）
        self.assertEqual(add_signed(2**31 - 1, 1, 32), (-(2**31), True))

    def test_exhaustive_4_bits(self):
        for a in range(-8, 8):
            for b in range(-8, 8):
                exact = a + b
                expected = ((exact + 8) % 16) - 8
                overflow = not -8 <= exact <= 7
                self.assertEqual(add_signed(a, b, 4), (expected, overflow), (a, b))

    def test_opposite_signs_never_overflow(self):
        rng = random.Random(3)
        for _ in range(500):
            a = rng.randrange(0, 2**15)
            b = -rng.randrange(1, 2**15 + 1)
            self.assertFalse(add_signed(a, b, 16)[1], (a, b))

    def test_invalid_operands(self):
        with self.assertRaises(OverflowError):
            add_signed(128, 0, 8)
        with self.assertRaises(ValueError):
            add_signed(0, 0, 0)


class TestExercise4Float(unittest.TestCase):
    def test_fields_examples(self):
        self.assertEqual(float_fields(1.0), (0, 1023, 0))
        self.assertEqual(float_fields(-2.0), (1, 1024, 0))
        self.assertEqual(float_fields(0.5), (0, 1022, 0))
        self.assertEqual(float_fields(0.1), (0, 1019, 0x999999999999A))
        self.assertEqual(float_fields(0.0), (0, 0, 0))
        self.assertEqual(float_fields(-0.0), (1, 0, 0))
        self.assertEqual(float_fields(math.inf), (0, 2047, 0))
        self.assertEqual(float_fields(5e-324), (0, 0, 1))  # 最小の非正規化数

    def test_nan_fields(self):
        sign, exponent, fraction = float_fields(math.nan)
        self.assertEqual(exponent, 2047)
        self.assertNotEqual(fraction, 0)

    def test_fields_match_bit_pattern(self):
        rng = random.Random(4)
        for _ in range(500):
            (bits,) = struct.unpack(">Q", struct.pack(">d", rng.uniform(-1e300, 1e300)))
            x = struct.unpack(">d", struct.pack(">Q", bits))[0]
            self.assertEqual(float_fields(x), (bits >> 63, (bits >> 52) & 0x7FF, bits & (2**52 - 1)))

    def test_classify(self):
        cases = {
            0.0: "zero", -0.0: "zero", 1.0: "normal", -123.456: "normal",
            5e-324: "subnormal", 2.2250738585072014e-308: "normal",
            2.225073858507201e-308: "subnormal", math.inf: "infinity",
            -math.inf: "infinity", math.nan: "nan", 1.7976931348623157e308: "normal",
        }
        for x, expected in cases.items():
            self.assertEqual(classify_float(x), expected, repr(x))

    def test_fields_to_float_examples(self):
        self.assertEqual(fields_to_float(0, 1023, 0), 1.0)
        self.assertEqual(fields_to_float(1, 1024, 0), -2.0)
        self.assertEqual(fields_to_float(0, 1019, 0x999999999999A), 0.1)
        self.assertEqual(fields_to_float(0, 0, 1), 5e-324)
        self.assertEqual(fields_to_float(0, 2047, 0), math.inf)
        self.assertEqual(fields_to_float(1, 2047, 0), -math.inf)
        self.assertTrue(math.isnan(fields_to_float(0, 2047, 1)))

    def test_signed_zero(self):
        z = fields_to_float(1, 0, 0)
        self.assertEqual(z, 0.0)
        self.assertEqual(math.copysign(1.0, z), -1.0, "-0.0 を返すこと")
        self.assertEqual(math.copysign(1.0, fields_to_float(0, 0, 0)), 1.0)

    def test_round_trip_random_bit_patterns(self):
        rng = random.Random(5)
        for _ in range(2000):
            bits = rng.getrandbits(64)
            x = struct.unpack(">d", struct.pack(">Q", bits))[0]
            if math.isnan(x):
                continue
            y = fields_to_float(*float_fields(x))
            self.assertEqual(struct.pack(">d", y), struct.pack(">d", x), hex(bits))

    def test_fields_to_float_validates(self):
        for args in [(2, 0, 0), (0, 2048, 0), (0, -1, 0), (0, 0, 2**52), (0, 0, -1)]:
            with self.assertRaises(ValueError, msg=str(args)):
                fields_to_float(*args)


class TestExercise5Utf8(unittest.TestCase):
    def test_encode_examples(self):
        self.assertEqual(utf8_encode([0x41]), b"A")
        self.assertEqual(utf8_encode([0x3042]), bytes.fromhex("e3 81 82"))  # あ
        self.assertEqual(utf8_encode([0x20BB7]), bytes.fromhex("f0 a0 ae b7"))  # 𠮷
        self.assertEqual(utf8_encode([0x1F600]), bytes.fromhex("f0 9f 98 80"))  # 😀
        self.assertEqual(utf8_encode([]), b"")

    def test_encode_boundaries(self):
        for cp in (0, 0x7F, 0x80, 0x7FF, 0x800, 0xD7FF, 0xE000, 0xFFFF, 0x10000, 0x10FFFF):
            self.assertEqual(utf8_encode([cp]), chr(cp).encode("utf-8"), hex(cp))

    def test_encode_random_text(self):
        rng = random.Random(6)
        for _ in range(300):
            cps = [random_code_point(rng) for _ in range(rng.randrange(0, 20))]
            self.assertEqual(utf8_encode(cps), "".join(map(chr, cps)).encode("utf-8"))

    def test_encode_rejects_invalid(self):
        for cp in (-1, 0xD800, 0xDBFF, 0xDC00, 0xDFFF, 0x110000):
            with self.assertRaises(ValueError, msg=hex(cp)):
                utf8_encode([cp])

    def test_decode_examples(self):
        self.assertEqual(utf8_decode(b"A"), [0x41])
        self.assertEqual(utf8_decode(bytes.fromhex("e3 81 82")), [0x3042])
        text = "Hello, 世界! 𠮷野家 😀"
        self.assertEqual(utf8_decode(text.encode("utf-8")), [ord(c) for c in text])
        self.assertEqual(utf8_decode(b""), [])

    def test_decode_rejects_invalid(self):
        invalid = {
            "単独の継続バイト": "80",
            "C0 は常に不正（'/' の冗長表現）": "c0 af",
            "3バイトの冗長表現": "e0 80 af",
            "4バイトの冗長表現": "f0 80 80 af",
            "サロゲート U+D800": "ed a0 80",
            "U+10FFFF を超える": "f4 90 80 80",
            "先頭バイト F5": "f5 80 80 80",
            "先頭バイト FF": "ff",
            "途中で途切れている": "e3 81",
            "継続バイトの位置に ASCII": "e3 41 82",
        }
        for label, hexbytes in invalid.items():
            with self.assertRaises(ValueError, msg=label):
                utf8_decode(bytes.fromhex(hexbytes))

    def test_decode_agrees_with_strict_builtin(self):
        # ランダムに壊したバイト列で、組み込みの厳格なデコーダと判定が一致するか
        rng = random.Random(7)
        for _ in range(3000):
            cps = [random_code_point(rng) for _ in range(rng.randrange(1, 6))]
            data = bytearray("".join(map(chr, cps)).encode("utf-8"))
            for _ in range(rng.randrange(0, 3)):
                data[rng.randrange(len(data))] = rng.randrange(256)
            if rng.random() < 0.2:
                del data[rng.randrange(len(data)):]
            data = bytes(data)
            try:
                expected = [ord(c) for c in data.decode("utf-8")]
            except UnicodeDecodeError:
                with self.assertRaises(ValueError, msg=data.hex(" ")):
                    utf8_decode(data)
            else:
                self.assertEqual(utf8_decode(data), expected, data.hex(" "))

    def test_round_trip(self):
        rng = random.Random(8)
        for _ in range(300):
            cps = [random_code_point(rng) for _ in range(rng.randrange(0, 30))]
            self.assertEqual(utf8_decode(utf8_encode(cps)), cps)


def random_code_point(rng: random.Random) -> int:
    """1〜4 バイトの UTF-8 になるコードポイントを偏りなく選ぶ（サロゲートは除く）。"""
    lo, hi = rng.choice([(0, 0x7F), (0x80, 0x7FF), (0x800, 0xFFFF), (0x10000, 0x10FFFF)])
    while True:
        cp = rng.randint(lo, hi)
        if not 0xD800 <= cp <= 0xDFFF:
            return cp


if __name__ == "__main__":
    unittest.main()
