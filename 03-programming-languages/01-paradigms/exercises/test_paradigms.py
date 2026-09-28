"""3.1 プログラミングパラダイムと抽象化 — テスト

実行: python3 tools/check.py 3.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import itertools
import math
import unittest

from paradigms import (
    Add,
    CacheInfo,
    Err,
    EvalError,
    Mul,
    Neg,
    Num,
    Ok,
    PList,
    Pow,
    Signup,
    UnwrapError,
    Var,
    chunked,
    compose,
    curry,
    derive,
    evaluate,
    iterate,
    memoize,
    parse_age,
    parse_email,
    parse_int,
    pipe,
    sequence,
    sliding_window,
    take,
    take_while,
    to_str,
    validate_signup,
)


class CountingSource:
    """取り出された要素数を数えるイテラブル（遅延評価の検証用）。"""

    def __init__(self, iterable):
        self._it = iter(iterable)
        self.pulled = 0

    def __iter__(self):
        return self

    def __next__(self):
        value = next(self._it)
        self.pulled += 1
        return value


# ---------------------------------------------------------------------------
# 演習1
# ---------------------------------------------------------------------------

class TestExercise1Compose(unittest.TestCase):
    def test_compose_applies_right_to_left(self):
        inc = lambda x: x + 1  # noqa: E731
        double = lambda x: x * 2  # noqa: E731
        self.assertEqual(compose(inc, double)(5), 11)
        self.assertEqual(compose(double, inc)(5), 12)
        self.assertEqual(compose(str, inc, double)(5), "11")

    def test_compose_rightmost_takes_any_arguments(self):
        self.assertEqual(compose(str, max)(3, 9, 4), "9")
        self.assertEqual(compose(len, sorted)([3, 1, 2], reverse=True), 3)

    def test_compose_empty_is_identity(self):
        identity = compose()
        self.assertEqual(identity(42), 42)
        obj = object()
        self.assertIs(identity(obj), obj)

    def test_compose_single_function(self):
        self.assertEqual(compose(abs)(-3), 3)

    def test_pipe(self):
        self.assertEqual(pipe(5, lambda x: x * 2, lambda x: x + 1), 11)
        self.assertEqual(pipe("hello"), "hello")
        self.assertEqual(pipe([3, 1, 2], sorted, tuple), (1, 2, 3))

    def test_pipe_and_compose_agree(self):
        fs = [lambda x: x + 3, lambda x: x * 5, lambda x: x - 1]
        for x in range(-5, 6):
            self.assertEqual(pipe(x, *fs), compose(*reversed(fs))(x))


class TestExercise1Curry(unittest.TestCase):
    def test_one_argument_at_a_time(self):
        add3 = curry(lambda a, b, c: a + b + c)
        self.assertEqual(add3(1)(2)(3), 6)

    def test_several_arguments_at_once(self):
        add3 = curry(lambda a, b, c: a + b + c)
        self.assertEqual(add3(1, 2)(3), 6)
        self.assertEqual(add3(1)(2, 3), 6)
        self.assertEqual(add3(1, 2, 3), 6)

    def test_partial_applications_are_reusable(self):
        # 部分適用した関数を何度使っても、互いの引数が混ざらないこと
        add3 = curry(lambda a, b, c: a * 100 + b * 10 + c)
        f = add3(1)
        g = f(2)
        self.assertEqual(g(3), 123)
        self.assertEqual(g(4), 124)
        self.assertEqual(f(5)(6), 156)
        self.assertEqual(f(7, 8), 178)

    def test_arity_from_signature_ignores_defaults(self):
        def greet(greeting, name, punctuation="!"):
            return f"{greeting}, {name}{punctuation}"

        self.assertEqual(curry(greet)("Hello")("World"), "Hello, World!")

    def test_explicit_arity(self):
        total = curry(lambda *xs: sum(xs), arity=3)
        self.assertEqual(total(1)(2)(3), 6)

    def test_zero_arity(self):
        self.assertEqual(curry(lambda: "done")(), "done")

    def test_errors(self):
        add2 = curry(lambda a, b: a + b)
        with self.assertRaises(TypeError):
            add2(1, 2, 3)
        with self.assertRaises(TypeError):
            add2(1)(2, 3)
        with self.assertRaises(TypeError):
            add2()
        with self.assertRaises(TypeError):
            curry(lambda *xs: xs)  # 可変長引数は arity の指定が必要
        with self.assertRaises(ValueError):
            curry(lambda a: a, arity=-1)


class TestExercise1Memoize(unittest.TestCase):
    def test_caches_results(self):
        calls = []

        @memoize
        def square(x):
            calls.append(x)
            return x * x

        self.assertEqual(square(4), 16)
        self.assertEqual(square(4), 16)
        self.assertEqual(square(5), 25)
        self.assertEqual(calls, [4, 5])
        self.assertEqual(square.cache_info(), CacheInfo(hits=1, misses=2, uncacheable=0, size=2))

    def test_recursive_fibonacci_is_fast(self):
        body_runs = []

        @memoize
        def fib(n):
            body_runs.append(n)
            return n if n < 2 else fib(n - 1) + fib(n - 2)

        self.assertEqual(fib(80), 23416728348467685)
        self.assertEqual(sorted(body_runs), list(range(81)), "各 n について本体は 1 回だけ実行される")
        self.assertEqual(fib.cache_info().misses, 81)

    def test_keyword_arguments(self):
        calls = []

        @memoize
        def f(a, b=0):
            calls.append((a, b))
            return a - b

        self.assertEqual(f(a=5, b=2), 3)
        self.assertEqual(f(b=2, a=5), 3)  # 名前順に並べるので同じキー
        self.assertEqual(len(calls), 1)
        self.assertEqual(f(5, 2), 3)  # 位置引数とキーワード引数は別のキー
        self.assertEqual(len(calls), 2)

    def test_unhashable_arguments_are_not_cached(self):
        calls = []

        @memoize
        def total(xs):
            calls.append(list(xs))
            return sum(xs)

        self.assertEqual(total([1, 2, 3]), 6)
        self.assertEqual(total([1, 2, 3]), 6)
        self.assertEqual(len(calls), 2, "リストはハッシュできないので毎回実行される")
        self.assertEqual(total((1, 2, 3)), 6)
        self.assertEqual(total((1, 2, 3)), 6)
        self.assertEqual(len(calls), 3, "タプルならキャッシュされる")
        info = total.cache_info()
        self.assertEqual((info.uncacheable, info.misses, info.hits, info.size), (2, 1, 1, 1))

    def test_unhashable_nested_and_keyword(self):
        @memoize
        def f(x, opts=None):
            return x

        self.assertEqual(f((1, [2])), (1, [2]))  # タプルの中のリストもハッシュできない
        self.assertEqual(f(1, opts={"a": 1}), 1)
        self.assertEqual(f.cache_info().uncacheable, 2)

    def test_exceptions_are_not_cached(self):
        calls = []

        @memoize
        def flaky(x):
            calls.append(x)
            if len(calls) == 1:
                raise ValueError("一時的な失敗")
            return x

        with self.assertRaises(ValueError):
            flaky(1)
        self.assertEqual(flaky(1), 1)
        self.assertEqual(len(calls), 2)

    def test_cache_clear_and_metadata(self):
        @memoize
        def ident(x):
            """恒等関数"""
            return x

        ident(1)
        ident(1)
        ident.cache_clear()
        self.assertEqual(ident.cache_info(), CacheInfo(0, 0, 0, 0))
        self.assertEqual(ident.__name__, "ident")
        self.assertEqual(ident.__doc__, "恒等関数")


# ---------------------------------------------------------------------------
# 演習2
# ---------------------------------------------------------------------------

class TestExercise2Streams(unittest.TestCase):
    def test_iterate(self):
        it = iterate(lambda n: n * 2, 1)
        self.assertEqual([next(it) for _ in range(6)], [1, 2, 4, 8, 16, 32])

    def test_iterate_is_lazy(self):
        calls = []

        def f(x):
            calls.append(x)
            return x + 1

        it = iterate(f, 0)
        self.assertEqual(calls, [], "作っただけでは f は呼ばれない")
        next(it)
        next(it)
        self.assertEqual(calls, [0])

    def test_take(self):
        self.assertEqual(list(take(3, iterate(lambda n: n + 1, 0))), [0, 1, 2])
        self.assertEqual(list(take(5, [1, 2])), [1, 2])
        self.assertEqual(list(take(0, [1, 2])), [])

    def test_take_pulls_exactly_n_items(self):
        src = CountingSource(itertools.count())
        self.assertEqual(list(take(3, src)), [0, 1, 2])
        self.assertEqual(src.pulled, 3, "n 個目を返した後に、n+1 個目を取り出してはいけない")
        src2 = CountingSource(itertools.count())
        self.assertEqual(list(take(0, src2)), [])
        self.assertEqual(src2.pulled, 0)

    def test_take_validates_eagerly(self):
        with self.assertRaises(ValueError):
            take(-1, [1, 2])  # list() で回す前に送出されること

    def test_take_while(self):
        powers = iterate(lambda n: n * 3, 1)
        self.assertEqual(list(take_while(lambda n: n < 20, powers)), [1, 3, 9])
        self.assertEqual(list(take_while(lambda n: n < 0, [1, 2])), [])
        self.assertEqual(list(take_while(lambda n: True, [1, 2])), [1, 2])

    def test_take_while_stops_right_after_first_failure(self):
        src = CountingSource(itertools.count())
        self.assertEqual(list(take_while(lambda n: n < 3, src)), [0, 1, 2])
        self.assertEqual(src.pulled, 4, "偽になった要素（3）までしか取り出さない")

    def test_chunked(self):
        self.assertEqual(list(chunked(range(7), 3)), [(0, 1, 2), (3, 4, 5), (6,)])
        self.assertEqual(list(chunked(range(6), 3)), [(0, 1, 2), (3, 4, 5)])
        self.assertEqual(list(chunked([], 3)), [])
        self.assertEqual(list(chunked("abc", 1)), [("a",), ("b",), ("c",)])

    def test_chunked_is_lazy_on_infinite_input(self):
        src = CountingSource(itertools.count())
        self.assertEqual(list(take(2, chunked(src, 3))), [(0, 1, 2), (3, 4, 5)])
        self.assertEqual(src.pulled, 6)

    def test_sliding_window(self):
        self.assertEqual(list(sliding_window([1, 2, 3, 4], 2)), [(1, 2), (2, 3), (3, 4)])
        self.assertEqual(list(sliding_window([1, 2, 3], 3)), [(1, 2, 3)])
        self.assertEqual(list(sliding_window([1, 2], 3)), [])
        self.assertEqual(list(sliding_window("abc", 1)), [("a",), ("b",), ("c",)])

    def test_sliding_window_is_lazy_on_infinite_input(self):
        src = CountingSource(itertools.count())
        self.assertEqual(list(take(3, sliding_window(src, 2))), [(0, 1), (1, 2), (2, 3)])
        self.assertEqual(src.pulled, 4)

    def test_invalid_sizes_are_rejected_eagerly(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                chunked([1, 2, 3], bad)
            with self.assertRaises(ValueError):
                sliding_window([1, 2, 3], bad)

    def test_pipeline_moving_average(self):
        # 遅延ストリームの組み合わせ: 無限の数列から移動平均を必要な分だけ計算する
        squares = (n * n for n in itertools.count(1))
        averages = (sum(w) / len(w) for w in sliding_window(squares, 3))
        self.assertEqual(list(take(3, averages)), [14 / 3, 29 / 3, 50 / 3])


# ---------------------------------------------------------------------------
# 演習3
# ---------------------------------------------------------------------------

class TestExercise3PersistentList(unittest.TestCase):
    def test_construction_and_iteration(self):
        self.assertEqual(list(PList.of(1, 2, 3)), [1, 2, 3])
        self.assertEqual(list(PList.from_iterable("abc")), ["a", "b", "c"])
        self.assertEqual(list(PList()), [])
        self.assertEqual(len(PList.of(1, 2, 3)), 3)
        self.assertEqual(len(PList()), 0)

    def test_stack_operations(self):
        s = PList().push(1).push(2)
        self.assertEqual(s.peek(), 2)
        self.assertEqual(s.pop().peek(), 1)
        self.assertTrue(s.pop().pop().is_empty())
        self.assertFalse(s.is_empty())

    def test_empty_errors(self):
        with self.assertRaises(IndexError):
            PList().peek()
        with self.assertRaises(IndexError):
            PList().pop()

    def test_old_versions_are_unchanged(self):
        versions = [PList()]
        for i in range(5):
            versions.append(versions[-1].push(i))
        for i, v in enumerate(versions):
            self.assertEqual(list(v), list(reversed(range(i))), f"バージョン {i} が変わっている")

    def test_immutable(self):
        xs = PList.of(1, 2)
        with self.assertRaises(AttributeError):
            xs._head = 99
        with self.assertRaises(AttributeError):
            xs.extra = 1
        self.assertEqual(list(xs), [1, 2])

    def test_push_and_pop_share_structure(self):
        a = PList.of(2, 3)
        b = a.push(1)
        self.assertIs(b.pop(), a, "pop は共有している尾部そのものを返す")

    def test_drop(self):
        a = PList.of(3, 4)
        b = a.push(2).push(1)
        self.assertIs(b.drop(2), a)
        self.assertIs(b.drop(0), b)
        self.assertTrue(b.drop(4).is_empty())
        with self.assertRaises(IndexError):
            b.drop(5)
        with self.assertRaises(ValueError):
            b.drop(-1)

    def test_set_uses_path_copying(self):
        xs = PList.of(0, 1, 2, 3, 4, 5)
        ys = xs.set(2, "two")
        self.assertEqual(list(ys), [0, 1, "two", 3, 4, 5])
        self.assertEqual(list(xs), [0, 1, 2, 3, 4, 5], "元のリストは変わらない")
        self.assertIs(ys.drop(3), xs.drop(3), "変更点より後ろは共有する")
        self.assertEqual(list(xs.set(0, "zero")), ["zero", 1, 2, 3, 4, 5])
        self.assertIs(xs.set(5, "five").drop(6), xs.drop(6))
        for bad in (6, -1):
            with self.assertRaises(IndexError):
                xs.set(bad, "x")

    def test_concat_shares_the_right_operand(self):
        xs = PList.of(1, 2)
        ys = PList.of(3, 4)
        zs = xs.concat(ys)
        self.assertEqual(list(zs), [1, 2, 3, 4])
        self.assertIs(zs.drop(2), ys)
        self.assertEqual(list(xs), [1, 2])
        self.assertIs(PList().concat(ys), ys)
        self.assertEqual(list(xs.concat(PList())), [1, 2])

    def test_reverse(self):
        self.assertEqual(list(PList.of(1, 2, 3).reverse()), [3, 2, 1])
        self.assertEqual(list(PList().reverse()), [])

    def test_equality_and_hash(self):
        self.assertEqual(PList.of(1, 2), PList.of(1, 2))
        self.assertNotEqual(PList.of(1, 2), PList.of(2, 1))
        self.assertNotEqual(PList.of(1, 2), PList.of(1, 2, 3))
        self.assertEqual(PList(), PList())
        self.assertNotEqual(PList.of(1, 2), [1, 2])
        self.assertEqual(hash(PList.of(1, 2)), hash(PList.of(1, 2)))
        self.assertEqual(len({PList.of(1, 2), PList.of(1, 2), PList.of(2, 1)}), 2)

    def test_repr(self):
        self.assertEqual(repr(PList.of(1, "a")), "PList(1, 'a')")
        self.assertEqual(repr(PList()), "PList()")

    def test_long_lists_do_not_recurse(self):
        n = 50_000
        xs = PList.from_iterable(range(n))
        ys = PList.from_iterable(range(n))
        self.assertEqual(len(xs), n)
        self.assertEqual(xs, ys)  # 再帰で比較すると RecursionError になる
        self.assertEqual(hash(xs), hash(ys))
        self.assertEqual(xs.reverse().peek(), n - 1)
        self.assertEqual(xs.set(n - 1, -1).drop(n - 1).peek(), -1)

    def test_equality_uses_sharing(self):
        # 共有している尾部に比較できない要素があっても、共有を検出すれば比較せずに済む
        class NoCompare:
            def __eq__(self, other):
                raise AssertionError("共有している部分は比較しなくてよい")

            __hash__ = object.__hash__

        tail = PList.of(NoCompare())
        self.assertEqual(tail.push(1), tail.push(1))


# ---------------------------------------------------------------------------
# 演習4
# ---------------------------------------------------------------------------

class TestExercise4Result(unittest.TestCase):
    def test_predicates(self):
        self.assertTrue(Ok(1).is_ok())
        self.assertFalse(Ok(1).is_err())
        self.assertTrue(Err("e").is_err())
        self.assertFalse(Err("e").is_ok())

    def test_map(self):
        self.assertEqual(Ok(2).map(lambda x: x * 10), Ok(20))
        self.assertEqual(Err("e").map(lambda x: x * 10), Err("e"))

    def test_map_does_not_call_function_on_err(self):
        def boom(_):
            raise AssertionError("Err では呼ばれない")

        Err("e").map(boom)
        Err("e").and_then(boom)
        Ok(1).map_err(boom)

    def test_map_err(self):
        self.assertEqual(Err("bad").map_err(str.upper), Err("BAD"))
        self.assertEqual(Ok(1).map_err(str.upper), Ok(1))

    def test_and_then_chains_and_short_circuits(self):
        def half(n):
            return Ok(n // 2) if n % 2 == 0 else Err(f"{n} は奇数")

        self.assertEqual(Ok(8).and_then(half).and_then(half), Ok(2))
        self.assertEqual(Ok(6).and_then(half).and_then(half), Err("3 は奇数"))
        self.assertEqual(Err("最初から失敗").and_then(half), Err("最初から失敗"))

    def test_and_then_requires_result(self):
        with self.assertRaises(TypeError):
            Ok(1).and_then(lambda x: x + 1)  # map と取り違えている

    def test_unwrap(self):
        self.assertEqual(Ok(5).unwrap(), 5)
        self.assertEqual(Ok(5).unwrap_or(0), 5)
        self.assertEqual(Err("e").unwrap_or(0), 0)
        with self.assertRaises(UnwrapError):
            Err("e").unwrap()

    def test_sequence(self):
        self.assertEqual(sequence([Ok(1), Ok(2), Ok(3)]), Ok([1, 2, 3]))
        self.assertEqual(sequence([]), Ok([]))
        self.assertEqual(sequence([Ok(1), Err("x"), Err("y")]), Err("x"))

    def test_sequence_stops_at_first_error(self):
        def results():
            yield Ok(1)
            yield Err("stop")
            raise AssertionError("最初の Err の後は取り出さない")

        self.assertEqual(sequence(results()), Err("stop"))


class TestExercise4Validation(unittest.TestCase):
    def test_parse_int(self):
        self.assertEqual(parse_int("42"), Ok(42))
        self.assertEqual(parse_int(" 42 "), Ok(42))
        self.assertEqual(parse_int("-7"), Ok(-7))
        self.assertEqual(parse_int("+7"), Ok(7))
        self.assertEqual(parse_int("007"), Ok(7))

    def test_parse_int_rejects(self):
        for text in ["", "   ", "abc", "4.2", "1_000", "１２３", "--1", "+", "1 2", "0x10"]:
            result = parse_int(text)
            self.assertIsInstance(result, Err, repr(text))
            self.assertIsInstance(result.error, str)

    def test_parse_age(self):
        self.assertEqual(parse_age("0"), Ok(0))
        self.assertEqual(parse_age("150"), Ok(150))
        for text in ["-1", "151", "abc"]:
            self.assertIsInstance(parse_age(text), Err, text)

    def test_parse_email(self):
        self.assertEqual(parse_email(" Alice@Example.COM "), Ok("Alice@example.com"))
        self.assertEqual(parse_email("a.b@sub.example.jp"), Ok("a.b@sub.example.jp"))
        for text in ["", "alice", "alice@", "@example.com", "a@@example.com", "a@b@c.com",
                     "alice@localhost", "alice@.com", "alice@example.", "al ice@example.com"]:
            self.assertIsInstance(parse_email(text), Err, repr(text))

    def test_valid_signup(self):
        form = {"name": " Taro ", "age": "30", "email": "Taro@Example.JP"}
        self.assertEqual(validate_signup(form), Ok(Signup("Taro", 30, "Taro@example.jp")))

    def test_collects_all_errors(self):
        result = validate_signup({"name": "", "age": "abc", "email": "ok@example.com"})
        self.assertIsInstance(result, Err)
        self.assertEqual(set(result.error), {"name", "age"})
        result = validate_signup({"name": "x" * 51, "age": "200", "email": "bad"})
        self.assertEqual(set(result.error), {"name", "age", "email"})
        for message in result.error.values():
            self.assertIsInstance(message, str)

    def test_missing_fields(self):
        result = validate_signup({"name": "Hanako"})
        self.assertIsInstance(result, Err)
        self.assertEqual(set(result.error), {"age", "email"})

    def test_name_length_boundary(self):
        form = {"name": "あ" * 50, "age": "20", "email": "a@b.cd"}
        self.assertIsInstance(validate_signup(form), Ok)


# ---------------------------------------------------------------------------
# 演習5
# ---------------------------------------------------------------------------

x, y = Var("x"), Var("y")


class TestExercise5aEvalAndPrint(unittest.TestCase):
    def test_evaluate(self):
        self.assertEqual(evaluate(Num(3), {}), 3)
        self.assertEqual(evaluate(Add(Num(1), Mul(x, Num(3))), {"x": 2}), 7)
        self.assertEqual(evaluate(Neg(Add(x, y)), {"x": 2, "y": 5}), -7)
        self.assertEqual(evaluate(Mul(Num(0.5), x), {"x": 3}), 1.5)

    def test_unbound_variable(self):
        with self.assertRaises(EvalError):
            evaluate(Add(x, Num(1)), {})

    def test_unknown_node(self):
        with self.assertRaises(TypeError):
            evaluate("x + 1", {})
        with self.assertRaises(TypeError):
            to_str(42)

    def test_to_str_basic(self):
        self.assertEqual(to_str(Num(3)), "3")
        self.assertEqual(to_str(Num(2.5)), "2.5")
        self.assertEqual(to_str(x), "x")
        self.assertEqual(to_str(Add(x, Num(1))), "x + 1")
        self.assertEqual(to_str(Mul(x, y)), "x * y")

    def test_to_str_precedence(self):
        self.assertEqual(to_str(Mul(Add(x, Num(1)), y)), "(x + 1) * y")
        self.assertEqual(to_str(Add(Mul(x, Num(2)), y)), "x * 2 + y")
        self.assertEqual(to_str(Add(x, Mul(y, Num(2)))), "x + y * 2")
        self.assertEqual(to_str(Mul(x, Add(y, Num(1)))), "x * (y + 1)")

    def test_to_str_associativity(self):
        self.assertEqual(to_str(Add(Add(x, y), Num(1))), "x + y + 1")
        self.assertEqual(to_str(Add(x, Add(y, Num(1)))), "x + (y + 1)")
        self.assertEqual(to_str(Mul(Mul(x, y), x)), "x * y * x")
        self.assertEqual(to_str(Mul(x, Mul(y, x))), "x * (y * x)")

    def test_to_str_negation(self):
        self.assertEqual(to_str(Neg(x)), "-x")
        self.assertEqual(to_str(Neg(Num(3))), "-3")
        self.assertEqual(to_str(Neg(Add(x, Num(1)))), "-(x + 1)")
        self.assertEqual(to_str(Neg(Mul(x, y))), "-(x * y)")
        self.assertEqual(to_str(Neg(Neg(x))), "-(-x)")
        self.assertEqual(to_str(Neg(Num(-3))), "-(-3)")
        self.assertEqual(to_str(Mul(Neg(x), y)), "-x * y")
        self.assertEqual(to_str(Add(x, Num(-3))), "x + -3")


class TestExercise5bNewOperation(unittest.TestCase):
    def check(self, expr, derivative, points=(-3, -1, 0, 2, 5)):
        """derive(expr) を評価した値が、手で求めた導関数 derivative(x) と一致するか。"""
        d = derive(expr, "x")
        for p in points:
            self.assertEqual(evaluate(d, {"x": p, "y": 7}), derivative(p), f"x={p}: {expr}")

    def test_constants_and_variables(self):
        self.check(Num(5), lambda p: 0)
        self.check(x, lambda p: 1)
        self.check(y, lambda p: 0)

    def test_sum_product_negation(self):
        self.check(Add(x, Num(3)), lambda p: 1)
        self.check(Mul(Num(3), x), lambda p: 3)
        self.check(Mul(x, x), lambda p: 2 * p)
        self.check(Mul(x, Mul(x, x)), lambda p: 3 * p * p)
        self.check(Neg(Mul(x, y)), lambda p: -7)
        self.check(Add(Mul(x, x), Neg(Mul(Num(4), x))), lambda p: 2 * p - 4)

    def test_derive_returns_expression(self):
        d = derive(Mul(x, x), "x")
        self.assertIsInstance(d, (Num, Var, Add, Mul, Neg, Pow))
        self.assertEqual(evaluate(d, {"x": 10}), 20)


class TestExercise5cNewType(unittest.TestCase):
    def test_evaluate_pow(self):
        self.assertEqual(evaluate(Pow(x, 3), {"x": 2}), 8)
        self.assertEqual(evaluate(Pow(Add(x, Num(1)), 2), {"x": 2}), 9)
        self.assertEqual(evaluate(Pow(x, 0), {"x": 5}), 1)

    def test_to_str_pow(self):
        self.assertEqual(to_str(Pow(x, 2)), "x^2")
        self.assertEqual(to_str(Pow(Add(x, Num(1)), 2)), "(x + 1)^2")
        self.assertEqual(to_str(Pow(Neg(x), 2)), "(-x)^2")
        self.assertEqual(to_str(Neg(Pow(x, 2))), "-x^2")
        self.assertEqual(to_str(Pow(Pow(x, 2), 3)), "(x^2)^3")
        self.assertEqual(to_str(Pow(Num(-2), 2)), "(-2)^2")
        self.assertEqual(to_str(Mul(Num(3), Pow(x, 2))), "3 * x^2")
        self.assertEqual(to_str(Pow(Mul(x, y), 2)), "(x * y)^2")

    def test_derive_pow(self):
        d = derive(Pow(x, 3), "x")
        for p in (-2, 0, 1, 3):
            self.assertEqual(evaluate(d, {"x": p}), 3 * p ** 2)
        d = derive(Pow(Add(Mul(Num(2), x), Num(1)), 2), "x")  # ((2x+1)^2)' = 4(2x+1)
        for p in (-2, 0, 1, 3):
            self.assertEqual(evaluate(d, {"x": p}), 4 * (2 * p + 1))
        self.assertEqual(evaluate(derive(Pow(x, 0), "x"), {"x": 4}), 0)
        self.assertEqual(evaluate(derive(Pow(x, 1), "x"), {"x": 4}), 1)

    def test_polynomial(self):
        # f(x) = x^3 - 2x^2 + 5 → f'(x) = 3x^2 - 4x
        f = Add(Add(Pow(x, 3), Neg(Mul(Num(2), Pow(x, 2)))), Num(5))
        self.assertEqual(to_str(f), "x^3 + -(2 * x^2) + 5")
        for p in range(-3, 4):
            self.assertEqual(evaluate(f, {"x": p}), p ** 3 - 2 * p ** 2 + 5)
            self.assertEqual(evaluate(derive(f, "x"), {"x": p}), 3 * p ** 2 - 4 * p)

    def test_float_values(self):
        f = Pow(Add(x, Num(0.5)), 2)
        self.assertTrue(math.isclose(evaluate(derive(f, "x"), {"x": 1.25}), 2 * 1.75))


if __name__ == "__main__":
    unittest.main()
