"""3.2 型システム — 演習1・2（Money / Quantity）のテスト

実行: python3 tools/check.py 3.2   （またはこのディレクトリで python3 -m unittest -v test_units）
"""
import math
import random
import unittest

from units import (
    HOUR,
    JOULE,
    KILOGRAM,
    KILOMETER,
    METER,
    NEWTON,
    POUND_FORCE,
    SECOND,
    CurrencyMismatchError,
    DimensionError,
    Money,
    Quantity,
)


class TestExercise1Money(unittest.TestCase):
    def test_construction_validates(self):
        self.assertEqual(Money(100, "JPY").amount, 100)
        for bad_amount in (1.5, 100.0, True, "100", None):
            with self.assertRaises(TypeError, msg=repr(bad_amount)):
                Money(bad_amount, "JPY")
        for bad_currency in ("XYZ", "jpy", "", "JP"):
            with self.assertRaises(ValueError, msg=repr(bad_currency)):
                Money(100, bad_currency)

    def test_add_and_subtract_same_currency(self):
        self.assertEqual(Money(1000, "JPY") + Money(500, "JPY"), Money(1500, "JPY"))
        self.assertEqual(Money(1000, "JPY") - Money(1500, "JPY"), Money(-500, "JPY"))
        self.assertEqual(-Money(250, "USD"), Money(-250, "USD"))
        self.assertEqual(sum([Money(1, "EUR"), Money(2, "EUR")], Money(0, "EUR")), Money(3, "EUR"))

    def test_currency_mismatch(self):
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "JPY") + Money(100, "USD")
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "JPY") - Money(100, "USD")
        with self.assertRaises(TypeError):  # CurrencyMismatchError は TypeError の一種
            Money(100, "JPY") + Money(100, "USD")

    def test_no_mixing_with_plain_numbers(self):
        with self.assertRaises(TypeError):
            Money(100, "JPY") + 100
        with self.assertRaises(TypeError):
            100 + Money(100, "JPY")
        with self.assertRaises(TypeError):
            Money(100, "JPY") - 1

    def test_multiply_by_int_only(self):
        self.assertEqual(Money(300, "JPY") * 3, Money(900, "JPY"))
        self.assertEqual(3 * Money(300, "JPY"), Money(900, "JPY"))
        for bad in (1.1, Money(2, "JPY"), True):
            with self.assertRaises(TypeError, msg=repr(bad)):
                Money(300, "JPY") * bad

    def test_comparison(self):
        self.assertTrue(Money(100, "JPY") < Money(200, "JPY"))
        self.assertTrue(Money(200, "JPY") >= Money(200, "JPY"))
        self.assertFalse(Money(200, "JPY") > Money(200, "JPY"))
        self.assertTrue(Money(100, "JPY") <= Money(100, "JPY"))
        self.assertEqual(max(Money(3, "USD"), Money(7, "USD")), Money(7, "USD"))
        with self.assertRaises(CurrencyMismatchError):
            Money(100, "JPY") < Money(200, "USD")
        with self.assertRaises(TypeError):
            Money(100, "JPY") < 200

    def test_equality_and_hash(self):
        self.assertEqual(Money(100, "JPY"), Money(100, "JPY"))
        self.assertNotEqual(Money(100, "JPY"), Money(100, "USD"))
        self.assertNotEqual(Money(100, "JPY"), 100)
        self.assertEqual(len({Money(1, "JPY"), Money(1, "JPY"), Money(1, "USD")}), 2)

    def test_str(self):
        self.assertEqual(str(Money(1234567, "JPY")), "JPY 1,234,567")
        self.assertEqual(str(Money(123456, "USD")), "USD 1,234.56")
        self.assertEqual(str(Money(-5, "USD")), "USD -0.05")
        self.assertEqual(str(Money(1234, "KWD")), "KWD 1.234")
        self.assertEqual(str(Money(0, "EUR")), "EUR 0.00")
        self.assertEqual(str(Money(-1234, "JPY")), "JPY -1,234")

    def test_parse(self):
        self.assertEqual(Money.parse("12.34", "USD"), Money(1234, "USD"))
        self.assertEqual(Money.parse("12.3", "USD"), Money(1230, "USD"))
        self.assertEqual(Money.parse("12", "USD"), Money(1200, "USD"))
        self.assertEqual(Money.parse(" 0.1 ", "USD"), Money(10, "USD"))
        self.assertEqual(Money.parse("-0.05", "USD"), Money(-5, "USD"))
        self.assertEqual(Money.parse("100", "JPY"), Money(100, "JPY"))
        self.assertEqual(Money.parse("1.005", "KWD"), Money(1005, "KWD"))

    def test_parse_is_exact_for_many_values(self):
        # float を経由すると 0.29 * 100 = 28.999999999999996 のような誤差が出る
        for cents in range(0, 100_000, 7):
            text = f"{cents // 100}.{cents % 100:02d}"
            self.assertEqual(Money.parse(text, "USD").amount, cents, text)

    def test_parse_rejects(self):
        for text, currency in [("12.345", "USD"), ("100.5", "JPY"), ("abc", "USD"), ("", "USD"),
                               ("1,000", "JPY"), ("1e3", "USD"), ("12.", "USD"), (".5", "USD"),
                               ("１２", "JPY"), ("1.0", "XYZ")]:
            with self.assertRaises(ValueError, msg=f"{text!r} {currency}"):
                Money.parse(text, currency)

    def test_allocate(self):
        self.assertEqual([m.amount for m in Money(100, "JPY").allocate([1, 1, 1])], [34, 33, 33])
        self.assertEqual([m.amount for m in Money(5, "USD").allocate([70, 30])], [4, 1])
        self.assertEqual([m.amount for m in Money(11, "JPY").allocate([0, 1, 1])], [0, 6, 5])
        self.assertEqual([m.amount for m in Money(10, "JPY").allocate([1])], [10])
        shares = Money(100, "USD").allocate([1, 2])
        self.assertTrue(all(s.currency == "USD" for s in shares))

    def test_allocate_preserves_total(self):
        rng = random.Random(32)
        for _ in range(300):
            amount = rng.randrange(-10_000, 10_000)
            ratios = [rng.randrange(0, 10) for _ in range(rng.randrange(1, 6))]
            if sum(ratios) == 0:
                ratios[0] = 1
            shares = [m.amount for m in Money(amount, "JPY").allocate(ratios)]
            self.assertEqual(sum(shares), amount, (amount, ratios))
            for share, r in zip(shares, ratios):
                exact = amount * r / sum(ratios)
                self.assertLessEqual(abs(share - exact), 1, (amount, ratios, shares))
                if r == 0:
                    self.assertEqual(share, 0, "比率 0 の項目には配らない")

    def test_allocate_rejects(self):
        for ratios in ([], [0, 0], [1, -1], [1.5, 1]):
            with self.assertRaises(ValueError, msg=repr(ratios)):
                Money(100, "JPY").allocate(ratios)

    def test_immutable(self):
        m = Money(100, "JPY")
        with self.assertRaises(AttributeError):
            m.amount = 200


class TestExercise2Quantity(unittest.TestCase):
    def assertQuantity(self, q, value, dims):
        self.assertIsInstance(q, Quantity)
        self.assertTrue(math.isclose(q.value, value, rel_tol=1e-12, abs_tol=1e-12), f"{q.value} != {value}")
        self.assertEqual(q.dims, Quantity(1.0, dims).dims)

    def test_add_same_dimension(self):
        self.assertQuantity(3 * METER + 2 * METER, 5.0, {"m": 1})
        self.assertQuantity(METER + KILOMETER, 1001.0, {"m": 1})
        self.assertQuantity(5 * SECOND - 2 * SECOND, 3.0, {"s": 1})
        self.assertQuantity(-(2 * METER), -2.0, {"m": 1})

    def test_add_different_dimension_raises(self):
        with self.assertRaises(DimensionError):
            METER + SECOND
        with self.assertRaises(DimensionError):
            NEWTON - JOULE
        with self.assertRaises(TypeError):  # DimensionError は TypeError の一種
            METER + SECOND

    def test_plain_numbers_are_dimensionless(self):
        ratio = (6 * METER) / (2 * METER)
        self.assertEqual(ratio.dims, ())
        self.assertQuantity(ratio + 1, 4.0, {})
        self.assertQuantity(1 + ratio, 4.0, {})
        self.assertQuantity(10 - ratio, 7.0, {})
        with self.assertRaises(DimensionError):
            METER + 1  # 裸の数値を長さに足すのは誤り
        with self.assertRaises(DimensionError):
            1 - METER

    def test_multiply_and_divide_combine_dimensions(self):
        self.assertQuantity((10 * METER) / (2 * SECOND), 5.0, {"m": 1, "s": -1})
        self.assertQuantity(METER * METER, 1.0, {"m": 2})
        self.assertQuantity(KILOGRAM * METER / SECOND / SECOND, 1.0, {"kg": 1, "m": 1, "s": -2})
        self.assertEqual(KILOGRAM * METER / SECOND ** 2, NEWTON)
        self.assertEqual(NEWTON * METER, JOULE)
        self.assertQuantity(1 / SECOND, 1.0, {"s": -1})
        self.assertQuantity(SECOND / 4, 0.25, {"s": 1})
        self.assertQuantity((METER / SECOND) * SECOND, 1.0, {"m": 1})

    def test_power(self):
        self.assertQuantity((2 * METER) ** 3, 8.0, {"m": 3})
        self.assertQuantity((2 * SECOND) ** -1, 0.5, {"s": -1})
        self.assertQuantity(METER ** 0, 1.0, {})
        with self.assertRaises(TypeError):
            METER ** 0.5

    def test_conversion(self):
        self.assertAlmostEqual((90 * KILOMETER / HOUR).to(METER / SECOND), 25.0)
        self.assertAlmostEqual((3 * KILOMETER).to(METER), 3000.0)
        with self.assertRaises(DimensionError):
            (3 * METER).to(SECOND)

    def test_mars_climate_orbiter(self):
        # 一方のチームはポンド重・秒で、もう一方はニュートン・秒で力積を扱っていた。
        # 単位を値と一緒に持っていれば、換算は自動で正しく行われる。
        impulse_lbf_s = 100 * POUND_FORCE * SECOND
        impulse_n_s = impulse_lbf_s.to(NEWTON * SECOND)
        self.assertAlmostEqual(impulse_n_s, 444.82216152605)
        total = impulse_lbf_s + 50 * NEWTON * SECOND  # 同じ次元（力積）なので足せる
        self.assertAlmostEqual(total.to(NEWTON * SECOND), 494.82216152605)
        with self.assertRaises(DimensionError):
            impulse_lbf_s + 100  # 単位のない「ただの数値」は混ぜられない

    def test_comparison(self):
        self.assertTrue(2 * METER < 3 * METER)
        self.assertTrue(KILOMETER > 999 * METER)
        self.assertTrue(METER <= METER)
        self.assertTrue(METER >= METER)
        with self.assertRaises(DimensionError):
            METER < SECOND
        with self.assertRaises(TypeError):
            METER < "1 m"

    def test_str(self):
        self.assertEqual(str(3.0 * METER / SECOND), "3.0 m/s")
        self.assertEqual(str(NEWTON), "1.0 kg·m/s^2")
        self.assertEqual(str(JOULE), "1.0 kg·m^2/s^2")
        self.assertEqual(str(1 / SECOND), "1.0 1/s")
        self.assertEqual(str(METER ** 2), "1.0 m^2")
        self.assertEqual(str(METER / METER), "1.0")
        self.assertEqual((NEWTON * METER).unit_str(), "kg·m^2/s^2")

    def test_unsupported_operands(self):
        with self.assertRaises(TypeError):
            METER + "1"
        with self.assertRaises(TypeError):
            METER * "2"

    def test_constructor_validation(self):
        with self.assertRaises(ValueError):
            Quantity(1.0, {"inch": 1})
        with self.assertRaises(TypeError):
            Quantity(1.0, {"m": 0.5})
        self.assertEqual(Quantity(1, {"m": 1, "s": 0}).dims, (("m", 1),))


if __name__ == "__main__":
    unittest.main()
