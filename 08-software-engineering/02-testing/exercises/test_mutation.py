"""8.2 演習2 — ミニ・ミューテーションテストのテスト

実行: python3 tools/check.py 8.2   （またはこのディレクトリで python3 -m unittest -v test_mutation）
"""
import ast
import unittest
from collections import Counter

from mutation import Mutant, MutationReport, format_report, generate_mutants, run_mutation_test

LEAP = '''
def is_leap_year(year):
    """西暦 year がうるう年なら True。"""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
'''

ABS = '''
def my_abs(x):
    if x >= 0:
        return x
    return -x
'''

DISCOUNT = '''
MAX_RATE = 15


def helper_not_under_test(x):
    return x + 1


def discount_rate(total, is_member, coupon=None):
    rate = 0
    if is_member:
        rate += 5
    if total >= 10000:
        rate += 5
    if coupon == "SALE" and not is_member:
        rate = rate + 10
    return min(rate, MAX_RATE)
'''


def weak_leap_test(fn):
    assert fn(2024) is True
    assert fn(2023) is False


def strong_leap_test(fn):
    for year, expected in [(2024, True), (2023, False), (1900, False), (2000, True), (2100, False)]:
        assert fn(year) is expected, (year, expected)


def pairs(mutants, kind=None):
    return [(m.original, m.replacement) for m in mutants if kind is None or m.kind == kind]


class TestGenerateMutants(unittest.TestCase):
    def test_single_arithmetic_mutant(self):
        (m,) = generate_mutants("def add(a, b):\n    return a + b\n", "add")
        self.assertIsInstance(m, Mutant)
        self.assertEqual((m.id, m.kind, m.lineno, m.original, m.replacement), (1, "arithmetic", 2, "+", "-"))
        self.assertIn("a - b", m.source)

    def test_arithmetic_table(self):
        table = {"+": "-", "-": "+", "*": "/", "/": "*", "//": "*", "%": "//"}
        for op, expected in table.items():
            mutants = generate_mutants(f"def f(a, b):\n    return a {op} b\n", "f")
            self.assertEqual(pairs(mutants), [(op, expected)], f"演算子 {op}")
        self.assertEqual(generate_mutants("def f(a, b):\n    return a ** b\n", "f"), [], "** は変異させない")

    def test_comparison_table(self):
        table = {
            "<": ["<=", ">="], "<=": ["<", ">"], ">": [">=", "<="], ">=": [">", "<"],
            "==": ["!="], "!=": ["=="], "is": ["is not"], "is not": ["is"], "in": ["not in"], "not in": ["in"],
        }
        for op, expected in table.items():
            mutants = generate_mutants(f"def f(a, b):\n    return a {op} b\n", "f")
            self.assertEqual(pairs(mutants), [(op, r) for r in expected], f"演算子 {op}")
            self.assertTrue(all(m.kind == "comparison" for m in mutants), f"演算子 {op}")

    def test_each_operator_of_a_chained_comparison(self):
        mutants = generate_mutants("def f(a, b, c):\n    return a < b <= c\n", "f")
        self.assertEqual(pairs(mutants), [("<", "<="), ("<", ">="), ("<=", "<"), ("<=", ">")])

    def test_constants(self):
        mutants = generate_mutants("def f():\n    return (3, True, 'x', 2.5, None)\n", "f")
        self.assertEqual(pairs(mutants), [("3", "4"), ("3", "2"), ("True", "False")])
        self.assertTrue(all(m.kind == "constant" for m in mutants))

    def test_boolean_mutations(self):
        src = "def f(a, b):\n    if not a or b:\n        return 1\n    return 0\n"
        mutants = generate_mutants(src, "f")
        self.assertEqual(
            pairs(mutants, "boolean"),
            [("not a or b", "not (not a or b)"), ("or", "and"), ("not", "")],
        )
        self.assertEqual(len(mutants), 7)

    def test_augassign_and_conditional_expression(self):
        src = "def f(x):\n    x += 1\n    return 1 if x else 2\n"
        mutants = generate_mutants(src, "f")
        self.assertEqual(pairs(mutants, "arithmetic"), [("+", "-")])
        self.assertEqual(pairs(mutants, "boolean"), [("x", "not (x)")])
        self.assertEqual(len(mutants), 8)

    def test_leap_year_counts(self):
        mutants = generate_mutants(LEAP, "is_leap_year")
        self.assertEqual(len(mutants), 20)
        self.assertEqual(
            Counter(m.kind for m in mutants),
            Counter({"constant": 12, "arithmetic": 3, "comparison": 3, "boolean": 2}),
        )
        self.assertEqual([m.id for m in mutants], list(range(1, 21)))
        self.assertTrue(all(m.lineno == 4 for m in mutants), "すべて return の行（4 行目）")

    def test_docstring_defaults_and_decorators_are_not_mutated(self):
        src = (
            "import functools\n\n"
            "@functools.lru_cache(maxsize=128)\n"
            "def scale(x, factor=2):\n"
            '    """2 倍にする。"""\n'
            "    return x * factor\n"
        )
        self.assertEqual(pairs(generate_mutants(src, "scale")), [("*", "/")])

    def test_mutant_sources_are_valid_and_differ_from_original(self):
        original = ast.unparse(ast.parse(DISCOUNT).body[2])
        mutants = generate_mutants(DISCOUNT, "discount_rate")
        self.assertEqual(len(mutants), 21)
        for m in mutants:
            tree = ast.parse(m.source)
            self.assertEqual(tree.body[0].name, "discount_rate")
            self.assertNotEqual(m.source, original, f"変異体 #{m.id} が元と同じソースです")
        self.assertEqual(len({m.source for m in mutants}), 21, "変異体はすべて異なるはず")
        self.assertTrue(all(10 <= m.lineno <= 17 for m in mutants), "対象の関数の中だけを変異させる")

    def test_unknown_or_non_top_level_function(self):
        with self.assertRaises(ValueError):
            generate_mutants(LEAP, "no_such_function")
        with self.assertRaises(ValueError):
            generate_mutants("class A:\n    def f(self):\n        return 1\n", "f")


class TestRunMutationTest(unittest.TestCase):
    def test_weak_tests_leave_survivors(self):
        report = run_mutation_test(LEAP, "is_leap_year", weak_leap_test)
        self.assertIsInstance(report, MutationReport)
        self.assertEqual((report.total, report.killed, len(report.survived)), (20, 9, 11))
        self.assertAlmostEqual(report.score, 0.45)
        self.assertIn(("100", "101"), pairs(report.survived), "1900 年を試さないので 100 → 101 に気づけない")
        self.assertEqual([m.id for m in report.survived], sorted(m.id for m in report.survived))

    def test_strong_tests_kill_everything(self):
        report = run_mutation_test(LEAP, "is_leap_year", strong_leap_test)
        self.assertEqual((report.total, report.killed, report.survived), (20, 20, []))
        self.assertEqual(report.score, 1.0)

    def test_missing_boundary_case_is_revealed(self):
        def test(fn):
            assert fn(5000, False) == 0
            assert fn(20000, False) == 5
            assert fn(5000, True) == 5
            assert fn(1000, False, "SALE") == 10

        report = run_mutation_test(DISCOUNT, "discount_rate", test)
        self.assertEqual(
            sorted(pairs(report.survived)),
            sorted([(">=", ">"), ("10000", "10001"), ("10000", "9999")]),
            "境界値 10000 ちょうどを試していないことが、生き残った変異体から分かる",
        )

    def test_equivalent_mutants_cannot_be_killed(self):
        def gap(fn):
            for x in (-3, 0, 5):
                assert fn(x) == abs(x)

        def thorough(fn):
            for x in (-3, -1, 0, 5):
                assert fn(x) == abs(x)

        self.assertIn(("0", "-1"), pairs(run_mutation_test(ABS, "my_abs", gap).survived), "fn(-1) を試していない")
        survivors = pairs(run_mutation_test(ABS, "my_abs", thorough).survived)
        # x > 0 や x >= 1 に変えても、x == 0 のとき -x も 0 なので結果は同じ（等価な変異体）
        self.assertEqual(sorted(survivors), sorted([(">=", ">"), ("0", "1")]))

    def test_exceptions_in_mutants_count_as_killed(self):
        src = "def ratio(a, b):\n    return a / (b + 1)\n"

        def test(fn):
            assert fn(4, 1) == 2.0

        report = run_mutation_test(src, "ratio", test)
        # b + 1 → b - 1 は ZeroDivisionError になる。これも「テストが気づいた」ので killed
        self.assertEqual((report.total, report.killed), (4, 4))

    def test_failing_test_on_original_code_is_rejected(self):
        def wrong(fn):
            assert fn(2023) is True

        with self.assertRaises(ValueError):
            run_mutation_test(LEAP, "is_leap_year", wrong)

    def test_function_without_mutation_points(self):
        report = run_mutation_test("def ident(x):\n    return x\n", "ident", lambda fn: None)
        self.assertEqual((report.total, report.killed, report.survived, report.score), (0, 0, [], 1.0))


class TestFormatReport(unittest.TestCase):
    def test_report_lines(self):
        report = run_mutation_test(LEAP, "is_leap_year", weak_leap_test)
        lines = format_report(report).split("\n")
        self.assertIn("45.0%", lines[0])
        self.assertIn("9/20", lines[0])
        self.assertEqual(len(lines), 1 + 11)
        for m, line in zip(report.survived, lines[1:]):
            self.assertIn(f"#{m.id}", line)
            self.assertIn(m.original, line)
            self.assertIn(m.replacement, line)
            self.assertIn(m.kind, line)

    def test_all_killed_is_a_single_line(self):
        report = run_mutation_test(LEAP, "is_leap_year", strong_leap_test)
        text = format_report(report)
        self.assertEqual(len(text.split("\n")), 1)
        self.assertIn("100.0%", text)


if __name__ == "__main__":
    unittest.main()
