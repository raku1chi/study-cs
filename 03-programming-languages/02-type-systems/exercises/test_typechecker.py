"""3.2 型システム — 演習3・4（型検査器・型推論）のテスト

実行: python3 tools/check.py 3.2   （またはこのディレクトリで python3 -m unittest -v test_typechecker）
"""
import unittest

from typechecker import (
    App,
    BinOp,
    BoolLit,
    Fst,
    If,
    IntLit,
    Lambda,
    Let,
    Pair,
    Snd,
    StrLit,
    TBool,
    TFun,
    TInt,
    TPair,
    TStr,
    TVar,
    TypeCheckError,
    UnaryOp,
    Var,
    check,
    infer,
    show_type,
)

INT, BOOL, STR = TInt(), TBool(), TStr()
a, b, c = TVar("a"), TVar("b"), TVar("c")
x, y, f, g, p = Var("x"), Var("y"), Var("f"), Var("g"), Var("p")


def fn(param, body, t=None):
    """テスト用の略記: fn(x: t) => body"""
    return Lambda(param, t, body)


def add(l, r):
    return BinOp("+", l, r)


class TestShowType(unittest.TestCase):
    """与えられた show_type の動作確認（演習ではありません）。"""

    def test_show(self):
        self.assertEqual(show_type(TFun(INT, TFun(INT, BOOL))), "int -> int -> bool")
        self.assertEqual(show_type(TFun(TFun(INT, INT), BOOL)), "(int -> int) -> bool")
        self.assertEqual(show_type(TPair(INT, TFun(a, b))), "(int, 'a -> 'b)")


class TestExercise3Check(unittest.TestCase):
    def assertTypeError(self, expr, *must_contain, env=None):
        with self.assertRaises(TypeCheckError) as cm:
            check(expr, env)
        for text in must_contain:
            self.assertIn(text, str(cm.exception), f"エラーメッセージに {text!r} を含めてください")

    def test_literals(self):
        self.assertEqual(check(IntLit(42)), INT)
        self.assertEqual(check(BoolLit(True)), BOOL)
        self.assertEqual(check(StrLit("hi")), STR)

    def test_arithmetic_and_comparison(self):
        self.assertEqual(check(add(IntLit(1), BinOp("*", IntLit(2), IntLit(3)))), INT)
        for op in ("-", "/", "%"):
            self.assertEqual(check(BinOp(op, IntLit(7), IntLit(2))), INT, op)
        for op in ("<", "<=", ">", ">="):
            self.assertEqual(check(BinOp(op, IntLit(1), IntLit(2))), BOOL, op)

    def test_logic_and_strings(self):
        self.assertEqual(check(BinOp("and", BoolLit(True), BoolLit(False))), BOOL)
        self.assertEqual(check(BinOp("or", BoolLit(True), BinOp("<", IntLit(1), IntLit(2)))), BOOL)
        self.assertEqual(check(BinOp("++", StrLit("a"), StrLit("b"))), STR)
        self.assertEqual(check(UnaryOp("-", IntLit(5))), INT)
        self.assertEqual(check(UnaryOp("not", BoolLit(False))), BOOL)

    def test_operand_type_errors(self):
        self.assertTypeError(add(IntLit(1), BoolLit(True)), "int", "bool")
        self.assertTypeError(add(StrLit("a"), IntLit(1)), "int", "str")  # 文字列の連結は ++
        self.assertTypeError(BinOp("++", StrLit("a"), IntLit(1)), "str", "int")
        self.assertTypeError(BinOp("and", IntLit(1), BoolLit(True)), "bool", "int")
        self.assertTypeError(BinOp("<", StrLit("a"), StrLit("b")), "int", "str")
        self.assertTypeError(UnaryOp("not", IntLit(1)), "bool", "int")
        self.assertTypeError(UnaryOp("-", BoolLit(True)), "int", "bool")

    def test_equality(self):
        for lit in (IntLit(1), BoolLit(True), StrLit("s")):
            self.assertEqual(check(BinOp("==", lit, lit)), BOOL)
            self.assertEqual(check(BinOp("!=", lit, lit)), BOOL)
        self.assertEqual(check(BinOp("==", Pair(IntLit(1), StrLit("a")), Pair(IntLit(2), StrLit("b")))), BOOL)
        self.assertTypeError(BinOp("==", IntLit(1), StrLit("1")), "int", "str")
        inc = fn("x", add(x, IntLit(1)), INT)
        self.assertTypeError(BinOp("==", inc, inc), "int -> int")

    def test_unknown_operator_and_node(self):
        self.assertTypeError(BinOp("**", IntLit(2), IntLit(3)), "**")
        self.assertTypeError(UnaryOp("~", IntLit(2)), "~")
        with self.assertRaises(TypeError):
            check("1 + 2")

    def test_variables(self):
        self.assertEqual(check(x, {"x": INT}), INT)
        self.assertEqual(check(add(x, y), {"x": INT, "y": INT}), INT)
        self.assertTypeError(x, "x")
        self.assertTypeError(add(IntLit(1), Var("counter")), "counter")

    def test_env_is_not_modified(self):
        env = {"x": INT}
        check(Let("y", IntLit(1), add(x, y)), env)
        check(fn("z", Var("z"), STR), env)
        self.assertEqual(env, {"x": INT})

    def test_if(self):
        self.assertEqual(check(If(BoolLit(True), IntLit(1), IntLit(2))), INT)
        self.assertEqual(check(If(BinOp("<", x, IntLit(0)), StrLit("neg"), StrLit("pos")), {"x": INT}), STR)
        self.assertTypeError(If(IntLit(1), IntLit(1), IntLit(2)), "bool", "int")
        self.assertTypeError(If(BoolLit(True), IntLit(1), StrLit("a")), "int", "str")

    def test_let(self):
        self.assertEqual(check(Let("x", IntLit(5), add(x, x))), INT)
        # 内側の let は外側の同名の変数を隠す（シャドーイング）
        self.assertEqual(check(Let("x", IntLit(5), Let("x", StrLit("s"), x))), STR)
        # let で束縛した名前は body の外では見えない
        self.assertTypeError(add(Let("t", IntLit(1), Var("t")), Var("t")), "t")

    def test_lambda_and_application(self):
        inc = fn("x", add(x, IntLit(1)), INT)
        self.assertEqual(check(inc), TFun(INT, INT))
        self.assertEqual(check(App(inc, IntLit(41))), INT)
        is_small = fn("x", BinOp("<", x, IntLit(10)), INT)
        self.assertEqual(check(is_small), TFun(INT, BOOL))

    def test_curried_functions(self):
        add2 = fn("x", fn("y", add(x, y), INT), INT)
        self.assertEqual(check(add2), TFun(INT, TFun(INT, INT)))
        self.assertEqual(check(App(add2, IntLit(1))), TFun(INT, INT))  # 部分適用
        self.assertEqual(check(App(App(add2, IntLit(1)), IntLit(2))), INT)

    def test_higher_order_functions(self):
        twice = fn("f", fn("x", App(f, App(f, x)), INT), TFun(INT, INT))
        self.assertEqual(check(twice), TFun(TFun(INT, INT), TFun(INT, INT)))
        inc = fn("n", add(Var("n"), IntLit(1)), INT)
        self.assertEqual(check(App(App(twice, inc), IntLit(0))), INT)
        # 関数を返す関数を let で束縛して使う
        prog = Let("twice", twice, App(App(Var("twice"), inc), IntLit(5)))
        self.assertEqual(check(prog), INT)

    def test_application_errors(self):
        self.assertTypeError(App(IntLit(1), IntLit(2)), "int")  # 関数でないものを呼ぶ
        inc = fn("x", add(x, IntLit(1)), INT)
        self.assertTypeError(App(inc, BoolLit(True)), "int", "bool")
        twice = fn("f", App(f, IntLit(1)), TFun(INT, INT))
        not_fn = fn("b", UnaryOp("not", Var("b")), BOOL)
        self.assertTypeError(App(twice, not_fn), "int -> int", "bool -> bool")

    def test_unannotated_lambda_is_rejected(self):
        with self.assertRaises(TypeCheckError):
            check(fn("x", x))

    def test_pairs(self):
        pr = Pair(IntLit(1), StrLit("a"))
        self.assertEqual(check(pr), TPair(INT, STR))
        self.assertEqual(check(Fst(pr)), INT)
        self.assertEqual(check(Snd(pr)), STR)
        swap = fn("p", Pair(Snd(p), Fst(p)), TPair(INT, BOOL))
        self.assertEqual(check(swap), TFun(TPair(INT, BOOL), TPair(BOOL, INT)))
        self.assertTypeError(Fst(IntLit(1)), "int")
        self.assertTypeError(Snd(BoolLit(True)), "bool")

    def test_bigger_program(self):
        # let abs = fn (n: int) => if n < 0 then -n else n in (abs (-3), abs 3 == 3)
        n = Var("n")
        abs_fn = fn("n", If(BinOp("<", n, IntLit(0)), UnaryOp("-", n), n), INT)
        body = Pair(App(Var("abs"), UnaryOp("-", IntLit(3))), BinOp("==", App(Var("abs"), IntLit(3)), IntLit(3)))
        self.assertEqual(check(Let("abs", abs_fn, body)), TPair(INT, BOOL))


class TestExercise4Infer(unittest.TestCase):
    def assertInfers(self, expr, expected, env=None):
        actual = infer(expr, env)
        self.assertEqual(actual, expected, f"{show_type(actual)} != {show_type(expected)}")

    def test_monomorphic_functions(self):
        self.assertInfers(fn("x", add(x, IntLit(1))), TFun(INT, INT))
        self.assertInfers(fn("x", If(x, IntLit(1), IntLit(0))), TFun(BOOL, INT))
        self.assertInfers(fn("s", BinOp("++", Var("s"), StrLit("!"))), TFun(STR, STR))
        self.assertInfers(fn("b", UnaryOp("not", Var("b"))), TFun(BOOL, BOOL))
        self.assertInfers(fn("x", UnaryOp("-", x)), TFun(INT, INT))

    def test_polymorphic_functions(self):
        self.assertInfers(fn("x", x), TFun(a, a))
        self.assertInfers(fn("x", fn("y", x)), TFun(a, TFun(b, a)))
        self.assertInfers(fn("x", Pair(x, x)), TFun(a, TPair(a, a)))
        self.assertInfers(fn("x", fn("y", BinOp("==", x, y))), TFun(a, TFun(a, BOOL)))

    def test_higher_order(self):
        twice = fn("f", fn("x", App(f, App(f, x))))
        self.assertInfers(twice, TFun(TFun(a, a), TFun(a, a)))
        compose = fn("f", fn("g", fn("x", App(f, App(g, x)))))
        self.assertInfers(compose, TFun(TFun(a, b), TFun(TFun(c, a), TFun(c, b))))
        uses_f_twice = fn("f", add(App(f, IntLit(1)), App(f, IntLit(2))))
        self.assertInfers(uses_f_twice, TFun(TFun(INT, INT), INT))

    def test_pairs(self):
        swap = fn("p", Pair(Snd(p), Fst(p)))
        self.assertInfers(swap, TFun(TPair(a, b), TPair(b, a)))
        self.assertInfers(fn("p", add(Fst(p), IntLit(1))), TFun(TPair(INT, a), INT))

    def test_application_and_let(self):
        inc = fn("x", add(x, IntLit(1)))
        self.assertInfers(App(inc, IntLit(2)), INT)
        self.assertInfers(Let("f", inc, App(f, IntLit(2))), INT)
        self.assertInfers(App(fn("x", x), BoolLit(True)), BOOL)
        self.assertInfers(add(x, IntLit(1)), INT, env={"x": INT})

    def test_mixed_with_annotations(self):
        self.assertInfers(fn("x", fn("y", Pair(x, y)), INT), TFun(INT, TFun(a, TPair(INT, a))))
        annotated = fn("x", add(x, IntLit(1)), INT)
        self.assertInfers(annotated, TFun(INT, INT))

    def test_agrees_with_check_on_annotated_programs(self):
        n = Var("n")
        programs = [
            fn("f", fn("x", App(f, App(f, x)), INT), TFun(INT, INT)),
            Let("abs", fn("n", If(BinOp("<", n, IntLit(0)), UnaryOp("-", n), n), INT), App(Var("abs"), IntLit(-3))),
            fn("p", Pair(Snd(p), Fst(p)), TPair(INT, BOOL)),
        ]
        for prog in programs:
            self.assertEqual(infer(prog), check(prog))

    def test_type_errors(self):
        errors = [
            App(fn("x", add(x, IntLit(1))), BoolLit(True)),  # int と bool
            fn("x", If(x, add(x, IntLit(1)), IntLit(0))),  # x が bool かつ int
            App(fn("f", App(f, BoolLit(True))), fn("x", add(x, IntLit(1)))),
            App(IntLit(3), IntLit(4)),
            If(BoolLit(True), IntLit(1), StrLit("one")),
            Var("undefined"),
        ]
        for expr in errors:
            with self.assertRaises(TypeCheckError, msg=repr(expr)):
                infer(expr)

    def test_occurs_check(self):
        with self.assertRaises(TypeCheckError):
            infer(fn("x", App(x, x)))  # x の型 'a = 'a -> 'b となり無限の型になる

    def test_cannot_compare_functions(self):
        inc = fn("x", add(x, IntLit(1)))
        with self.assertRaises(TypeCheckError):
            infer(BinOp("==", inc, inc))


if __name__ == "__main__":
    unittest.main()
