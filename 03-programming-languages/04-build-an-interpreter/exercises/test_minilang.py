"""3.4 言語処理系を作る — MiniLang のテスト（段階ごとのテストクラス）

実行: python3 tools/check.py 3.4
段階ごと: python3 -m unittest -v test_minilang.TestStage1Tokenizer
"""
import unittest

from minilang import (
    Assign,
    Binary,
    Block,
    Boolean,
    Call,
    Environment,
    ExprStmt,
    FnDecl,
    FunctionExpr,
    If,
    Interpreter,
    Let,
    LexError,
    Logical,
    MiniLangError,
    MiniRuntimeError,
    Nil,
    Number,
    ParseError,
    Print,
    Return,
    String,
    Unary,
    Var,
    While,
    apply_binary,
    apply_unary,
    fold_constants,
    is_truthy,
    parse,
    parse_expr,
    run,
    tokenize,
    values_equal,
)


def types(source):
    return [t.type for t in tokenize(source)]


N = Number
x, y = Var("x"), Var("y")


# ===========================================================================
# 段階1: 字句解析
# ===========================================================================


class TestStage1Tokenizer(unittest.TestCase):
    def test_simple_statement(self):
        tokens = tokenize("let x = 10;")
        self.assertEqual([t.type for t in tokens], ["let", "IDENT", "=", "INT", ";", "EOF"])
        self.assertEqual(tokens[1].lexeme, "x")
        self.assertEqual(tokens[3].value, 10)
        self.assertIsNone(tokens[0].value)

    def test_operators_use_longest_match(self):
        self.assertEqual(
            types("a<=b==c!=d>=e<f>g=h"),
            ["IDENT", "<=", "IDENT", "==", "IDENT", "!=", "IDENT", ">=", "IDENT", "<", "IDENT", ">",
             "IDENT", "=", "IDENT", "EOF"],
        )
        self.assertEqual(types("+-*/%(){},;"), list("+-*/%(){},;") + ["EOF"])
        self.assertEqual(types("x = = y"), ["IDENT", "=", "=", "IDENT", "EOF"])

    def test_keywords_and_identifiers(self):
        self.assertEqual(
            types("let fn if else while return print true false nil and or not"),
            ["let", "fn", "if", "else", "while", "return", "print", "true", "false", "nil",
             "and", "or", "not", "EOF"],
        )
        self.assertEqual(types("letter lets nil_value _tmp x1 fnord"), ["IDENT"] * 6 + ["EOF"])

    def test_integers(self):
        tokens = tokenize("0 42 007 123abc")
        self.assertEqual([(t.type, t.value) for t in tokens[:3]], [("INT", 0), ("INT", 42), ("INT", 7)])
        self.assertEqual([(t.type, t.lexeme) for t in tokens[3:5]], [("INT", "123"), ("IDENT", "abc")])

    def test_strings_and_escapes(self):
        tokens = tokenize(r'"hello" "a\nb" "tab\there" "q\"uote" "back\\slash" ""')
        self.assertEqual([t.value for t in tokens[:-1]],
                         ["hello", "a\nb", "tab\there", 'q"uote', "back\\slash", ""])
        self.assertEqual(tokens[1].lexeme, r'"a\nb"', "lexeme はソース上の文字列そのもの")
        self.assertTrue(all(t.type == "STRING" for t in tokens[:-1]))

    def test_comments_and_whitespace(self):
        source = "// 先頭のコメント\nlet a = 1; // 行末のコメント\n\t print(a);\n"
        self.assertEqual(types(source), ["let", "IDENT", "=", "INT", ";", "print", "(", "IDENT", ")", ";", "EOF"])
        self.assertEqual(types("8 / 2 // 割り算とコメント"), ["INT", "/", "INT", "EOF"])

    def test_positions(self):
        tokens = tokenize('let a = 1;\n  print("x", a);\n')
        pr = tokens[5]
        self.assertEqual((pr.type, pr.line, pr.col), ("print", 2, 3))
        s = tokens[7]
        self.assertEqual((s.type, s.line, s.col), ("STRING", 2, 9))
        comma = tokens[8]
        self.assertEqual((comma.type, comma.line, comma.col), (",", 2, 12))
        eof = tokens[-1]
        self.assertEqual((eof.type, eof.line), ("EOF", 3))

    def test_unicode_inside_strings_and_comments(self):
        tokens = tokenize('print("こんにちは"); // コメント')
        self.assertEqual(tokens[2].value, "こんにちは")
        self.assertEqual((tokens[3].type, tokens[3].col), (")", 14), "col は文字（コードポイント）単位で数える")

    def test_errors(self):
        cases = {
            '"abc': 1,  # 閉じていない文字列
            'let s = "abc\nprint(s);': 1,  # 文字列の途中で改行（開始した行を報告）
            "let a = 1;\nlet b = @;": 2,  # 知らない文字
            "if (!x) {}": 1,  # ! は使えない（not を使う）
            r'"bad \q escape"': 1,  # 不明なエスケープ
            "x = 1;\n\n  # comment": 3,
            "let 名前 = 1;": 1,  # 識別子は ASCII のみ
        }
        for source, line in cases.items():
            with self.assertRaises(LexError, msg=repr(source)) as cm:
                tokenize(source)
            self.assertEqual(cm.exception.line, line, repr(source))
            self.assertIsInstance(cm.exception, MiniLangError)

    def test_empty_source(self):
        tokens = tokenize("")
        self.assertEqual([(t.type, t.line, t.col) for t in tokens], [("EOF", 1, 1)])


# ===========================================================================
# 段階2: 式の構文解析
# ===========================================================================


class TestStage2ExpressionParser(unittest.TestCase):
    def test_literals_and_variables(self):
        self.assertEqual(parse_expr("42"), N(42))
        self.assertEqual(parse_expr('"hi"'), String("hi"))
        self.assertEqual(parse_expr("true"), Boolean(True))
        self.assertEqual(parse_expr("false"), Boolean(False))
        self.assertEqual(parse_expr("nil"), Nil())
        self.assertEqual(parse_expr("x"), x)
        self.assertNotEqual(parse_expr("true"), N(1), "true と 1 は別の種類のノード")

    def test_precedence(self):
        self.assertEqual(parse_expr("1 + 2 * 3"), Binary("+", N(1), Binary("*", N(2), N(3))))
        self.assertEqual(parse_expr("1 * 2 + 3"), Binary("+", Binary("*", N(1), N(2)), N(3)))
        self.assertEqual(parse_expr("(1 + 2) * 3"), Binary("*", Binary("+", N(1), N(2)), N(3)))
        self.assertEqual(parse_expr("10 - 7 % 4"), Binary("-", N(10), Binary("%", N(7), N(4))))

    def test_left_associativity(self):
        self.assertEqual(parse_expr("1 - 2 - 3"), Binary("-", Binary("-", N(1), N(2)), N(3)))
        self.assertEqual(parse_expr("8 / 4 / 2"), Binary("/", Binary("/", N(8), N(4)), N(2)))
        self.assertEqual(parse_expr("a or b or c"), Logical("or", Logical("or", Var("a"), Var("b")), Var("c")))

    def test_unary(self):
        self.assertEqual(parse_expr("-x"), Unary("-", x))
        self.assertEqual(parse_expr("--x"), Unary("-", Unary("-", x)))
        self.assertEqual(parse_expr("not true"), Unary("not", Boolean(True)))
        self.assertEqual(parse_expr("-2 * 3"), Binary("*", Unary("-", N(2)), N(3)))
        self.assertEqual(parse_expr("not a == b"), Binary("==", Unary("not", Var("a")), Var("b")))

    def test_comparison_equality_logic(self):
        a, b, c, d = Var("a"), Var("b"), Var("c"), Var("d")
        self.assertEqual(parse_expr("a < b == c < d"), Binary("==", Binary("<", a, b), Binary("<", c, d)))
        self.assertEqual(parse_expr("a or b and c"), Logical("or", a, Logical("and", b, c)))
        self.assertEqual(parse_expr("a and b or c"), Logical("or", Logical("and", a, b), c))
        self.assertEqual(
            parse_expr("x + 1 >= y and not x != 2"),
            Logical("and", Binary(">=", Binary("+", x, N(1)), y), Binary("!=", Unary("not", x), N(2))),
        )

    def test_assignment_is_right_associative(self):
        self.assertEqual(parse_expr("a = 1"), Assign("a", N(1)))
        self.assertEqual(parse_expr("a = b = 1 + 2"), Assign("a", Assign("b", Binary("+", N(1), N(2)))))
        self.assertEqual(parse_expr("a = b or c"), Assign("a", Logical("or", Var("b"), Var("c"))))

    def test_invalid_assignment_target(self):
        for source in ("1 = 2", "a + b = c", "(a) + 1 = 2", "-a = 1"):
            with self.assertRaises(ParseError, msg=source):
                parse_expr(source)

    def test_syntax_errors(self):
        for source in ("1 +", "(1 + 2", "1 2", ")", "* 3", "", "1 + * 2", "(1 + 2))"):
            with self.assertRaises(ParseError, msg=repr(source)):
                parse_expr(source)

    def test_error_line_numbers(self):
        with self.assertRaises(ParseError) as cm:
            parse_expr("1 +\n\n* 2")
        self.assertEqual(cm.exception.line, 3)
        with self.assertRaises(ParseError) as cm:
            parse_expr("(1 +\n 2")  # ")" がないままファイルが終わる
        self.assertEqual(cm.exception.line, 2)

    def test_nodes_record_line_numbers(self):
        expr = parse_expr("1\n+\n2")
        self.assertEqual(expr.line, 2, "Binary の line は演算子の行")
        self.assertEqual((expr.left.line, expr.right.line), (1, 3))
        self.assertEqual(parse_expr("\n\n-x").line, 3)
        self.assertEqual(parse_expr("\nname = 1").line, 2)


# ===========================================================================
# 段階3: 式の評価（構文木を直接組み立てるので、段階1・2 に依存しない）
# ===========================================================================


def ev(expr):
    return Interpreter().evaluate(expr, Environment())


class TestStage3ExpressionEvaluator(unittest.TestCase):
    def test_literals(self):
        self.assertEqual(ev(N(42)), 42)
        self.assertEqual(ev(String("s")), "s")
        self.assertIs(ev(Boolean(True)), True)
        self.assertIsNone(ev(Nil()))

    def test_arithmetic(self):
        self.assertEqual(ev(Binary("+", N(1), Binary("*", N(2), N(3)))), 7)
        self.assertEqual(ev(Binary("-", N(10), N(20))), -10)
        self.assertEqual(ev(Unary("-", Binary("*", N(6), N(7)))), -42)
        self.assertEqual(ev(Binary("*", N(2**40), N(2**40))), 2**80, "整数は任意精度")

    def test_division_truncates_toward_zero(self):
        cases = [(7, 2, 3, 1), (-7, 2, -3, -1), (7, -2, -3, 1), (-7, -2, 3, -1), (6, 3, 2, 0), (0, 5, 0, 0)]
        for a, b, q, r in cases:
            self.assertEqual(apply_binary("/", a, b), q, f"{a} / {b}")
            self.assertEqual(apply_binary("%", a, b), r, f"{a} % {b}")
            self.assertEqual(a, b * q + r, "a == b * (a / b) + a % b が成り立つ")

    def test_division_by_zero_reports_line(self):
        for op in ("/", "%"):
            with self.assertRaises(MiniRuntimeError) as cm:
                ev(Binary(op, N(1), N(0), line=5))
            self.assertEqual(cm.exception.line, 5)

    def test_strings(self):
        self.assertEqual(ev(Binary("+", String("ab"), String("cd"))), "abcd")
        self.assertIs(ev(Binary("<", String("apple"), String("banana"))), True)
        self.assertIs(ev(Binary(">=", String("b"), String("b"))), True)

    def test_no_implicit_conversion(self):
        bad = [("+", "a", 1), ("+", 1, "a"), ("+", True, 1), ("-", "a", "b"), ("*", "ab", 3),
               ("<", 1, "2"), ("<", True, False), ("+", None, 1), ("-", 1, True)]
        for op, a, b in bad:
            with self.assertRaises(MiniRuntimeError, msg=f"{a!r} {op} {b!r}"):
                apply_binary(op, a, b, 1)
        with self.assertRaises(MiniRuntimeError):
            apply_unary("-", "a", 1)
        with self.assertRaises(MiniRuntimeError):
            apply_unary("-", True, 1)

    def test_comparisons(self):
        self.assertIs(apply_binary("<", 1, 2), True)
        self.assertIs(apply_binary("<=", 2, 2), True)
        self.assertIs(apply_binary(">", 1, 2), False)
        self.assertIs(apply_binary(">=", -1, -2), True)

    def test_equality(self):
        self.assertTrue(values_equal(1, 1))
        self.assertTrue(values_equal("a", "a"))
        self.assertTrue(values_equal(None, None))
        self.assertFalse(values_equal(1, "1"))
        self.assertFalse(values_equal(True, 1), "Python では True == 1 だが MiniLang では false")
        self.assertFalse(values_equal(0, False))
        self.assertFalse(values_equal(None, False))
        self.assertIs(apply_binary("==", 1, 1), True)
        self.assertIs(apply_binary("!=", 1, "1"), True)
        self.assertIs(apply_binary("==", True, 1), False)

    def test_truthiness(self):
        for v in (0, "", 1, "false", True):
            self.assertTrue(is_truthy(v), repr(v))
        for v in (None, False):
            self.assertFalse(is_truthy(v), repr(v))
        self.assertIs(apply_unary("not", 0), False, "0 は真なので not 0 は false")
        self.assertIs(apply_unary("not", None), True)

    def test_logical_short_circuit(self):
        boom = Binary("/", N(1), N(0))  # 評価されたらエラーになる式
        self.assertIs(ev(Logical("and", Boolean(False), boom)), False)
        self.assertIs(ev(Logical("or", Boolean(True), boom)), True)
        self.assertIsNone(ev(Logical("and", Nil(), boom)))
        with self.assertRaises(MiniRuntimeError):
            ev(Logical("and", Boolean(True), boom))

    def test_logical_returns_operand_values(self):
        self.assertEqual(ev(Logical("or", Nil(), String("default"))), "default")
        self.assertEqual(ev(Logical("and", N(1), N(2))), 2)
        self.assertEqual(ev(Logical("or", N(0), N(5))), 0, "0 は真なので左辺がそのまま返る")
        self.assertIs(ev(Logical("and", N(1), Boolean(False))), False)

    def test_unknown_node(self):
        with self.assertRaises(TypeError):
            ev("1 + 2")


# ===========================================================================
# 段階4: 文・変数・スコープ・制御構造
# ===========================================================================


class TestStage4Statements(unittest.TestCase):
    def test_parse_statements(self):
        self.assertEqual(parse("let x = 1; print(x);"), [Let("x", N(1)), Print(x)])
        self.assertEqual(parse("x = x + 1;"), [ExprStmt(Assign("x", Binary("+", x, N(1))))])
        self.assertEqual(parse("{ let a = 1; }"), [Block((Let("a", N(1)),))])
        self.assertEqual(parse(""), [])

    def test_parse_if_while(self):
        self.assertEqual(
            parse("if (x) { print(1); } else { print(2); }"),
            [If(x, Block((Print(N(1)),)), Block((Print(N(2)),)))],
        )
        self.assertEqual(parse("if (x) { }"), [If(x, Block(()), None)])
        self.assertEqual(
            parse("if (x) { } else if (y) { } else { print(3); }"),
            [If(x, Block(()), If(y, Block(()), Block((Print(N(3)),))))],
        )
        self.assertEqual(
            parse("while (x < 3) { x = x + 1; }"),
            [While(Binary("<", x, N(3)), Block((ExprStmt(Assign("x", Binary("+", x, N(1)))),)))],
        )

    def test_statement_line_numbers(self):
        program = parse("let a = 1;\n\nprint(a);\nif (a) {\n}")
        self.assertEqual([s.line for s in program], [1, 3, 4])

    def test_parse_errors(self):
        cases = {
            "let x = 1": 1,  # ; がない
            "let = 5;": 1,
            "print(1;\n": 1,
            "if x { print(1); }": 1,  # 条件に括弧が必要
            "while (true) print(1);": 1,  # 本体はブロックでなければならない
            "let a = 1;\n{\nprint(a);": 3,  # } がないままファイルが終わる
            "let a = 1;\nprint(a)\nprint(a);": 3,
        }
        for source, line in cases.items():
            with self.assertRaises(ParseError, msg=repr(source)) as cm:
                parse(source)
            self.assertEqual(cm.exception.line, line, repr(source))

    def test_print_values(self):
        self.assertEqual(run("print(1 + 2 * 3);"), ["7"])
        self.assertEqual(run('print("hello");'), ["hello"])
        self.assertEqual(run("print(true); print(false); print(nil);"), ["true", "false", "nil"])
        self.assertEqual(run("print(-7 / 2); print(-7 % 2);"), ["-3", "-1"])
        self.assertEqual(run("print(1 == 1); print(true == 1);"), ["true", "false"])

    def test_variables_and_assignment(self):
        self.assertEqual(run("let a = 1; a = a + 41; print(a);"), ["42"])
        self.assertEqual(run("let a = 1; let b = 2; a = b = 5; print(a); print(b);"), ["5", "5"])
        self.assertEqual(run("let a = 1; print(a = 3); print(a);"), ["3", "3"])
        self.assertEqual(run('let s = "a"; s = s + "b"; print(s);'), ["ab"])

    def test_undefined_variables(self):
        with self.assertRaises(MiniRuntimeError) as cm:
            run("let a = 1;\nprint(b);")
        self.assertEqual(cm.exception.line, 2)
        self.assertIn("b", str(cm.exception))
        with self.assertRaises(MiniRuntimeError) as cm:
            run("let a = 1;\n\nundefined_var = 2;")
        self.assertEqual(cm.exception.line, 3)

    def test_block_scope_and_shadowing(self):
        source = """
        let x = "outer";
        {
            let x = "inner";
            print(x);
        }
        print(x);
        """
        self.assertEqual(run(source), ["inner", "outer"])

    def test_assignment_updates_enclosing_scope(self):
        self.assertEqual(run("let x = 1; { x = 2; { x = x + 1; } } print(x);"), ["3"])

    def test_block_variables_are_not_visible_outside(self):
        with self.assertRaises(MiniRuntimeError):
            run("{ let hidden = 1; } print(hidden);")

    def test_if_else(self):
        source = """
        let n = 15;
        if (n % 15 == 0) { print("FizzBuzz"); }
        else if (n % 3 == 0) { print("Fizz"); }
        else if (n % 5 == 0) { print("Buzz"); }
        else { print(n); }
        """
        self.assertEqual(run(source), ["FizzBuzz"])
        self.assertEqual(run("if (false) { print(1); } print(2);"), ["2"])

    def test_truthiness_in_conditions(self):
        self.assertEqual(run('if (0) { print("0 は真"); }'), ["0 は真"])
        self.assertEqual(run('if ("") { print("空文字列も真"); }'), ["空文字列も真"])
        self.assertEqual(run('if (nil) { print("x"); } else { print("nil は偽"); }'), ["nil は偽"])

    def test_while_loop(self):
        source = """
        let i = 1;
        let total = 0;
        while (i <= 10) {
            total = total + i;
            i = i + 1;
        }
        print(total);
        """
        self.assertEqual(run(source), ["55"])

    def test_fizzbuzz(self):
        source = """
        let i = 1;
        while (i <= 15) {
            if (i % 15 == 0) { print("FizzBuzz"); }
            else if (i % 3 == 0) { print("Fizz"); }
            else if (i % 5 == 0) { print("Buzz"); }
            else { print(i); }
            i = i + 1;
        }
        """
        expected = ["1", "2", "Fizz", "4", "Buzz", "Fizz", "7", "8", "Fizz", "Buzz", "11", "Fizz",
                    "13", "14", "FizzBuzz"]
        self.assertEqual(run(source), expected)

    def test_loop_body_gets_fresh_scope_each_iteration(self):
        source = """
        let i = 0;
        while (i < 3) {
            let doubled = i * 2;
            print(doubled);
            i = i + 1;
        }
        """
        self.assertEqual(run(source), ["0", "2", "4"])

    def test_step_limit_stops_long_loops(self):
        source = "let i = 0; while (i < 100000) { i = i + 1; }"
        with self.assertRaises(MiniRuntimeError):
            run(source, max_steps=1000)
        self.assertEqual(run("let i = 0; while (i < 50) { i = i + 1; } print(i);", max_steps=1000), ["50"])

    def test_runtime_error_line_in_program(self):
        source = "let a = 10;\nlet b = 0;\nprint(a / b);\n"
        with self.assertRaises(MiniRuntimeError) as cm:
            run(source)
        self.assertEqual(cm.exception.line, 3)
        self.assertTrue(str(cm.exception).startswith("3行目"))

    def test_environment_directly(self):
        outer = Environment()
        outer.define("a", 1)
        inner = Environment(outer)
        inner.define("b", 2)
        self.assertEqual((inner.get("a"), inner.get("b")), (1, 2))
        inner.assign("a", 10)
        self.assertEqual(outer.get("a"), 10, "見つかったスコープ（外側）を書き換える")
        self.assertNotIn("a", inner.values)
        with self.assertRaises(MiniRuntimeError):
            outer.get("b")
        with self.assertRaises(MiniRuntimeError):
            inner.assign("zzz", 1)


# ===========================================================================
# 段階5: 関数・クロージャ・再帰
# ===========================================================================

EXAMPLE = """
let x = 10;
fn fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); }
print(fact(x));
let make_counter = fn() { let c = 0; return fn() { c = c + 1; return c; }; };
let counter = make_counter();
counter();
counter();
print(counter());
"""


class TestStage5Functions(unittest.TestCase):
    def test_parse_function_declaration(self):
        a, b = Var("a"), Var("b")
        self.assertEqual(
            parse("fn add(a, b) { return a + b; }"),
            [FnDecl("add", ("a", "b"), (Return(Binary("+", a, b)),))],
        )
        self.assertEqual(parse("fn nothing() { return; }"), [FnDecl("nothing", (), (Return(None),))])

    def test_parse_calls_and_function_expressions(self):
        f = Var("f")
        self.assertEqual(parse_expr("f()"), Call(f, ()))
        self.assertEqual(parse_expr("f(1, x + 2)"), Call(f, (N(1), Binary("+", x, N(2)))))
        self.assertEqual(parse_expr("f(1)(2)"), Call(Call(f, (N(1),)), (N(2),)))
        self.assertEqual(parse_expr("-f(1)"), Unary("-", Call(f, (N(1),))))
        self.assertEqual(parse_expr("fn(x) { return x; }"), FunctionExpr(("x",), (Return(x),)))
        self.assertEqual(
            parse("let id = fn(x) { return x; };"),
            [Let("id", FunctionExpr(("x",), (Return(x),)))],
        )

    def test_function_parse_errors(self):
        for source in ("return 1;", "fn f(a, a) { }", "fn f(a,) { }", "fn f(1) { }", "f(1, 2;",
                       "fn f() { return 1 }", "{ return; }"):
            with self.assertRaises(ParseError, msg=source):
                parse(source)
        self.assertIsInstance(parse("fn f() { fn g() { return 1; } return g(); }")[0], FnDecl)

    def test_chapter_example(self):
        self.assertEqual(run(EXAMPLE), ["3628800", "3"])

    def test_recursion(self):
        source = """
        fn fib(n) { if (n < 2) { return n; } return fib(n - 1) + fib(n - 2); }
        print(fib(15));
        """
        self.assertEqual(run(source), ["610"])

    def test_counters_are_independent(self):
        source = """
        fn make_counter() { let c = 0; fn inc() { c = c + 1; return c; } return inc; }
        let a = make_counter();
        let b = make_counter();
        a(); a();
        print(a());
        print(b());
        """
        self.assertEqual(run(source), ["3", "1"])

    def test_closures_capture_variables_not_values(self):
        source = """
        let n = 1;
        let get = fn() { return n; };
        n = 2;
        print(get());
        """
        self.assertEqual(run(source), ["2"])

    def test_lexical_not_dynamic_scope(self):
        source = """
        let x = "global";
        fn show() { print(x); }
        fn caller() { let x = "local"; show(); }
        caller();
        """
        self.assertEqual(run(source), ["global"], "呼び出し元ではなく定義された場所の x を見る")

    def test_higher_order_functions(self):
        source = """
        fn twice(f, v) { return f(f(v)); }
        fn compose(f, g) { return fn(v) { return f(g(v)); }; }
        let triple = fn(n) { return n * 3; };
        let inc = fn(n) { return n + 1; };
        print(twice(triple, 2));
        print(compose(inc, triple)(5));
        """
        self.assertEqual(run(source), ["18", "16"])

    def test_return_from_nested_loops_and_blocks(self):
        source = """
        fn find_first_multiple(k) {
            let i = 1;
            while (true) {
                if (i % k == 0) { { return i; } }
                i = i + 1;
            }
        }
        print(find_first_multiple(7));
        """
        self.assertEqual(run(source), ["7"])

    def test_implicit_nil_return(self):
        self.assertEqual(run("fn f() { } print(f());"), ["nil"])
        self.assertEqual(run("fn g() { return; } print(g());"), ["nil"])

    def test_function_values(self):
        source = """
        fn fact(n) { return n; }
        print(fact);
        print(fn() { return 1; });
        print(len);
        print(fact == fact);
        print(fn() {} == fn() {});
        """
        self.assertEqual(run(source), ["<fn fact>", "<fn>", "<builtin len>", "true", "false"])

    def test_builtins(self):
        self.assertEqual(run('print("n=" + str(42));'), ["n=42"])
        self.assertEqual(run('print(len("hello"));'), ["5"])
        self.assertEqual(run('print(str(nil) + str(true));'), ["niltrue"])
        with self.assertRaises(MiniRuntimeError):
            run("print(len(42));")
        with self.assertRaises(MiniRuntimeError):
            run('print(len("a", "b"));')

    def test_call_errors(self):
        with self.assertRaises(MiniRuntimeError) as cm:
            run("fn f(a, b) { return a; }\nprint(f(1));")
        self.assertEqual(cm.exception.line, 2)
        for source in ("let x = 1; x();", "nil();", '"text"(1);'):
            with self.assertRaises(MiniRuntimeError, msg=source):
                run(source)

    def test_parameters_are_local(self):
        source = """
        let a = "outer";
        fn f(a) { a = "changed"; return a; }
        print(f("arg"));
        print(a);
        """
        self.assertEqual(run(source), ["changed", "outer"])

    def test_infinite_recursion_is_stopped(self):
        with self.assertRaises(MiniRuntimeError):
            run("fn f(n) { return f(n + 1); } f(0);")
        self.assertEqual(run("fn depth(n) { if (n == 0) { return 0; } return 1 + depth(n - 1); } print(depth(150));"),
                         ["150"])

    def test_step_limit_counts_calls(self):
        source = "fn f(n) { if (n == 0) { return 0; } return f(n - 1); } let i = 0; while (i < 100) { f(50); i = i + 1; }"
        with self.assertRaises(MiniRuntimeError):
            run(source, max_steps=500)


# ===========================================================================
# 段階6: 定数畳み込み
# ===========================================================================

SEMANTIC_PROGRAMS = [
    "print(1 + 2 * 3 - 4 / 2);",
    'print("a" + "b" + "c");',
    "print(-7 / 2); print(-7 % 2); print(7 % -2);",
    "print(1 < 2 and 3 >= 3); print(nil or \"x\"); print(0 or 5); print(false and 1);",
    "print(not 0); print(not nil); print(1 == true); print(\"1\" != 1);",
    "if (1 + 1 == 2) { print(\"yes\"); } else { print(\"no\"); }",
    "if (2 < 1) { print(\"no\"); }",
    "let x = 2 * 3; fn f(a) { return a + 10 * 10; } print(f(x));",
    "let i = 0; while (i < 2 + 1) { print(i * (4 - 2)); i = i + 1; }",
    "fn f() { if (true) { return 1; } return 2; } print(f());",
]


class TestStage6ConstantFolding(unittest.TestCase):
    def test_fold_arithmetic(self):
        self.assertEqual(fold_constants(parse_expr("1 + 2 * 3")), N(7))
        self.assertEqual(fold_constants(parse_expr("(1 + 2) * (3 + 4)")), N(21))
        self.assertEqual(fold_constants(parse_expr("-(2 + 3)")), N(-5))
        self.assertEqual(fold_constants(parse_expr("-7 / 2")), N(-3))

    def test_fold_other_types(self):
        self.assertEqual(fold_constants(parse_expr('"a" + "b"')), String("ab"))
        self.assertEqual(fold_constants(parse_expr("1 < 2")), Boolean(True))
        self.assertEqual(fold_constants(parse_expr("not true")), Boolean(False))
        self.assertEqual(fold_constants(parse_expr("nil == nil")), Boolean(True))
        self.assertEqual(fold_constants(parse_expr("1 == true")), Boolean(False))

    def test_partial_folding(self):
        self.assertEqual(fold_constants(parse_expr("x + 2 * 3")), Binary("+", x, N(6)))
        self.assertEqual(fold_constants(parse_expr("f(1 + 1, x)")), Call(Var("f"), (N(2), x)))
        self.assertEqual(fold_constants(parse_expr("x = 2 * 21")), Assign("x", N(42)))

    def test_no_reassociation(self):
        expr = parse_expr("x + 1 + 2")
        self.assertEqual(fold_constants(expr), Binary("+", Binary("+", x, N(1)), N(2)))

    def test_errors_are_not_folded(self):
        self.assertEqual(fold_constants(parse_expr("1 / 0")), Binary("/", N(1), N(0)))
        self.assertEqual(fold_constants(parse_expr('"a" + 1')), Binary("+", String("a"), N(1)))
        self.assertEqual(fold_constants(parse_expr("-true")), Unary("-", Boolean(True)))
        self.assertEqual(fold_constants(parse("if (x) { print(1 / 0); }")),
                         [If(x, Block((Print(Binary("/", N(1), N(0))),)), None)])
        with self.assertRaises(MiniRuntimeError) as cm:
            run("let a = 1;\nprint(10 / (5 - 5));", optimize=True)
        self.assertEqual(cm.exception.line, 2)

    def test_fold_logical(self):
        self.assertEqual(fold_constants(parse_expr("true and x")), x)
        self.assertEqual(fold_constants(parse_expr("false and x")), Boolean(False))
        self.assertEqual(fold_constants(parse_expr("nil or x")), x)
        self.assertEqual(fold_constants(parse_expr("1 or x")), N(1))
        self.assertEqual(fold_constants(parse_expr("x and 1 + 1")), Logical("and", x, N(2)))

    def test_fold_if_with_constant_condition(self):
        self.assertEqual(fold_constants(parse("if (1 < 2) { print(1); } else { print(2); }")),
                         [Block((Print(N(1)),))])
        self.assertEqual(fold_constants(parse("if (1 > 2) { print(1); } else { print(2); }")),
                         [Block((Print(N(2)),))])
        self.assertEqual(fold_constants(parse("if (false) { print(1); }")), [Block(())])
        self.assertEqual(fold_constants(parse("if (false) { } else if (x) { print(3); }")),
                         [If(x, Block((Print(N(3)),)), None)])

    def test_folds_inside_statements_and_functions(self):
        program = parse("fn f(a) { let k = 60 * 60; while (a < 2 + 3) { a = a + k; } return a; }")
        folded = fold_constants(program)
        self.assertEqual(
            folded,
            [FnDecl("f", ("a",), (
                Let("k", N(3600)),
                While(Binary("<", Var("a"), N(5)), Block((ExprStmt(Assign("a", Binary("+", Var("a"), Var("k")))),))),
                Return(Var("a")),
            ))],
        )
        self.assertEqual(fold_constants(parse_expr("fn() { return 2 + 2; }")), FunctionExpr((), (Return(N(4)),)))

    def test_line_numbers_are_preserved(self):
        folded = fold_constants(parse_expr("\n1\n+\n2"))
        self.assertEqual(folded, N(3))
        self.assertEqual(folded.line, 3, "置き換えた元のノード（演算子）の行")

    def test_input_is_not_modified(self):
        program = parse("print(1 + 2);")
        before = repr(program)
        fold_constants(program)
        self.assertEqual(repr(program), before)

    def test_semantics_are_preserved(self):
        for source in SEMANTIC_PROGRAMS:
            self.assertEqual(run(source, optimize=True), run(source), source)


if __name__ == "__main__":
    unittest.main()
