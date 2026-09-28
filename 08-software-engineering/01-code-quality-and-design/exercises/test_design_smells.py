"""8.1 演習3 — 設計の「におい」を測る静的解析器のテスト

実行: python3 tools/check.py 8.1   （またはこのディレクトリで python3 -m unittest -v test_design_smells）
"""
import contextlib
import io
import os
import tempfile
import textwrap
import unittest

from design_smells import SMELL_KINDS, FunctionMetrics, Smell, analyze_source, find_smells, format_report, main


def src(text: str) -> str:
    return textwrap.dedent(text).lstrip("\n")


def metrics_by_name(source: str) -> dict:
    return {m.name: m for m in analyze_source(src(source))}


class TestFunctionDiscovery(unittest.TestCase):
    def test_functions_methods_and_nested_functions_in_source_order(self):
        code = """
        def top():
            def inner():
                return 1
            return inner()

        class Order:
            def total(self):
                return 0

            class Line:
                def amount(self):
                    return 0

        async def fetch():
            return None
        """
        names = [m.name for m in analyze_source(src(code))]
        self.assertEqual(names, ["top", "top.inner", "Order.total", "Order.Line.amount", "fetch"])

    def test_returns_function_metrics(self):
        (m,) = analyze_source("def f():\n    pass\n")
        self.assertIsInstance(m, FunctionMetrics)
        self.assertEqual((m.name, m.lineno), ("f", 1))

    def test_module_level_code_and_lambdas_are_not_functions(self):
        code = """
        x = lambda y: y + 1
        if x:
            print(x)
        """
        self.assertEqual(analyze_source(src(code)), [])

    def test_empty_source(self):
        self.assertEqual(analyze_source(""), [])


class TestLengthAndParams(unittest.TestCase):
    def test_length_counts_from_def_line_excluding_decorators(self):
        code = """
        import functools

        @functools.lru_cache
        def f(x):
            # コメント行も数える
            y = x + 1

            return y
        """
        m = metrics_by_name(code)["f"]
        self.assertEqual(m.lineno, 4, "lineno は def の行（デコレータの行ではない）")
        self.assertEqual(m.length, 5)

    def test_params_all_kinds(self):
        code = """
        def f(a, b, /, c, d=1, *args, e, f=2, **kwargs):
            pass
        """
        self.assertEqual(metrics_by_name(code)["f"].params, 8)

    def test_self_and_cls_are_not_counted_for_methods(self):
        code = """
        class A:
            def m(self, x):
                pass

            @classmethod
            def c(cls, x, y):
                pass

            @staticmethod
            def s(x, y):
                pass

        def g(self, x):
            pass
        """
        m = metrics_by_name(code)
        self.assertEqual(m["A.m"].params, 1)
        self.assertEqual(m["A.c"].params, 2)
        self.assertEqual(m["A.s"].params, 2)
        self.assertEqual(m["g"].params, 2, "クラスの外の関数では self も普通の引数")


class TestNesting(unittest.TestCase):
    def test_no_control_flow_is_zero(self):
        self.assertEqual(metrics_by_name("def f(x):\n    return x\n")["f"].max_nesting, 0)

    def test_nested_blocks(self):
        code = """
        def f(items):
            for item in items:
                if item:
                    while item:
                        with open(item) as fp:
                            item = fp.read()
            return items
        """
        self.assertEqual(metrics_by_name(code)["f"].max_nesting, 4)

    def test_elif_does_not_increase_nesting_but_else_if_does(self):
        flat = """
        def f(x):
            if x == 1:
                return 1
            elif x == 2:
                return 2
            elif x == 3:
                return 3
            else:
                return 0
        """
        nested = """
        def g(x):
            if x == 1:
                return 1
            else:
                if x == 2:
                    return 2
            return 0
        """
        self.assertEqual(metrics_by_name(flat)["f"].max_nesting, 1)
        self.assertEqual(metrics_by_name(nested)["g"].max_nesting, 2)

    def test_try_except_finally_bodies_are_one_level(self):
        code = """
        def f():
            try:
                pass
            except ValueError:
                if True:
                    pass
            finally:
                pass
        """
        self.assertEqual(metrics_by_name(code)["f"].max_nesting, 2)

    def test_nested_function_is_measured_separately(self):
        code = """
        def outer(x):
            if x:
                def inner(y):
                    for i in y:
                        if i:
                            pass
                return inner
        """
        m = metrics_by_name(code)
        self.assertEqual(m["outer"].max_nesting, 1)
        self.assertEqual(m["outer.inner"].max_nesting, 2)

    def test_match_statement(self):
        code = """
        def f(cmd):
            match cmd:
                case "go":
                    if cmd:
                        return 1
                case _:
                    return 0
        """
        self.assertEqual(metrics_by_name(code)["f"].max_nesting, 2)


class TestComplexity(unittest.TestCase):
    def cc(self, code: str, name: str = "f") -> int:
        return metrics_by_name(code)[name].complexity

    def test_straight_line_code_is_one(self):
        self.assertEqual(self.cc("def f(x):\n    y = x * 2\n    return y\n"), 1)

    def test_if_elif_else(self):
        code = """
        def f(x):
            if x > 0:
                return 1
            elif x < 0:
                return -1
            else:
                return 0
        """
        self.assertEqual(self.cc(code), 3)

    def test_loops_and_boolean_operators(self):
        code = """
        def f(xs, a, b, c):
            total = 0
            for x in xs:
                while x > 0 and a or b:
                    x -= 1
            return total if a and b and c else 0
        """
        # for +1, while +1, (and, or) +2, IfExp +1, (and, and) +2 → 1 + 7
        self.assertEqual(self.cc(code), 8)

    def test_except_handlers(self):
        code = """
        def f():
            try:
                pass
            except ValueError:
                pass
            except (KeyError, TypeError):
                pass
            else:
                pass
            finally:
                pass
        """
        self.assertEqual(self.cc(code), 3)

    def test_comprehensions(self):
        code = """
        def f(rows):
            return [c for r in rows if r for c in r if c if c > 1]
        """
        # for 節 2 つ（+2）と if 3 つ（+3）→ 1 + 5
        self.assertEqual(self.cc(code), 6)

    def test_lambda_counts_toward_enclosing_function(self):
        code = """
        def f(xs):
            return sorted(xs, key=lambda x: x if x else 0)
        """
        self.assertEqual(self.cc(code), 2)

    def test_nested_function_decisions_are_not_counted_in_outer(self):
        code = """
        def outer(x):
            def inner(y):
                if y:
                    return 1
                return 0
            return inner(x)
        """
        self.assertEqual(self.cc(code, "outer"), 1)
        self.assertEqual(self.cc(code, "outer.inner"), 2)

    def test_match_cases_wildcard_is_not_counted(self):
        code = """
        def f(cmd):
            match cmd:
                case "a":
                    return 1
                case "b" | "c":
                    return 2
                case _ if cmd:
                    return 3
                case _:
                    return 0
        """
        # "a", "b"|"c", ガード付きの _ で +3 → 4
        self.assertEqual(self.cc(code), 4)

    def test_with_and_assert_are_not_decisions(self):
        code = """
        def f(path):
            assert path
            with open(path) as fp:
                return fp.read()
        """
        self.assertEqual(self.cc(code), 1)


SMELLY = """
def process(order, user, coupon, now, logger, flags):
    if order:
        for line in order:
            if line:
                for x in line:
                    if x > 0 and x < 10 or x == 100:
                        logger(x)
    return order
"""


class TestFindSmells(unittest.TestCase):
    def test_reports_values_over_limits(self):
        smells = find_smells(src(SMELLY), max_length=5, max_params=5, max_nesting=3, max_complexity=5)
        kinds = [s.kind for s in smells]
        self.assertEqual(kinds, ["long_function", "too_many_params", "deep_nesting", "high_complexity"])
        by_kind = {s.kind: s for s in smells}
        self.assertEqual(by_kind["long_function"], Smell("process", 1, "long_function", 8, 5))
        self.assertEqual(by_kind["too_many_params"].value, 6)
        self.assertEqual(by_kind["deep_nesting"].value, 5)
        self.assertEqual(by_kind["high_complexity"].value, 8)

    def test_value_equal_to_limit_is_not_a_smell(self):
        smells = find_smells(src(SMELLY), max_length=8, max_params=6, max_nesting=5, max_complexity=8)
        self.assertEqual(smells, [])

    def test_default_limits(self):
        smells = find_smells(src(SMELLY))
        self.assertEqual([s.kind for s in smells], ["too_many_params", "deep_nesting"])
        self.assertEqual({s.limit for s in smells}, {4, 3})

    def test_order_follows_functions_then_kinds(self):
        code = """
        def a(p1, p2, p3):
            return 1

        def b(p1, p2, p3):
            if p1:
                if p2:
                    return 1
        """
        smells = find_smells(src(code), max_params=2, max_nesting=1)
        self.assertEqual(
            [(s.name, s.kind) for s in smells],
            [("a", "too_many_params"), ("b", "too_many_params"), ("b", "deep_nesting")],
        )
        self.assertEqual(SMELL_KINDS[0], "long_function")


class TestReportAndCli(unittest.TestCase):
    def test_format_report_lines(self):
        smells = [Smell("calc", 12, "long_function", 64, 40), Smell("calc", 12, "high_complexity", 21, 10)]
        report = format_report(smells, filename="pricing.py")
        lines = report.split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("pricing.py:12 calc: "), lines[0])
        self.assertIn("64", lines[0])
        self.assertIn("40", lines[0])
        self.assertIn("21", lines[1])
        self.assertFalse(report.endswith("\n"))

    def test_format_report_empty(self):
        report = format_report([], filename="clean.py")
        self.assertIn("問題は見つかりませんでした", report)
        self.assertEqual(len(report.split("\n")), 1)

    def test_main_returns_exit_code_and_prints_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            smelly = os.path.join(tmp, "smelly.py")
            clean = os.path.join(tmp, "clean.py")
            with open(smelly, "w", encoding="utf-8") as fp:
                fp.write(src(SMELLY))
            with open(clean, "w", encoding="utf-8") as fp:
                fp.write("def ok(x):\n    return x\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main([clean]), 0)
                self.assertEqual(main([smelly]), 1)
            printed = out.getvalue()
            self.assertIn("問題は見つかりませんでした", printed)
            self.assertIn(f"{smelly}:1 process: ", printed)


if __name__ == "__main__":
    unittest.main()
