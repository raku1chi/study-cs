"""2.7 計算理論 — テスト（正規表現エンジン: 演習5）

実行: python3 tools/check.py 2.7   （またはこのディレクトリで python3 -m unittest -v）
"""
import functools
import random
import re
import threading
import time
import unittest

from thompson_regex import (
    Alt,
    AnyChar,
    Char,
    Concat,
    Empty,
    Plus,
    Regex,
    RegexSyntaxError,
    Star,
    StepLimitExceeded,
    backtrack_fullmatch,
    compile_nfa,
    parse,
)

def with_timeout(seconds: float):
    """クラスの各テストを別スレッドで実行し、seconds 秒で終わらなければ失敗にする。

    無限ループや指数時間の実装でも、テスト全体が止まらずに失敗として報告されるようにするため。
    """

    def wrap(fn):
        @functools.wraps(fn)
        def wrapper(self):
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    fn(self)
                except BaseException as exc:  # noqa: BLE001 — テストのスレッドへ例外を運ぶ
                    errors.append(exc)

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(seconds)
            if t.is_alive():
                self.fail(f"{seconds} 秒以内に終わりません（無限ループや指数時間になっていませんか）")
            if errors:
                raise errors[0]

        return wrapper

    def decorate(cls):
        for name, value in list(vars(cls).items()):
            if name.startswith("test") and callable(value):
                setattr(cls, name, wrap(value))
        return cls

    return decorate


PATHOLOGICAL = ["(a+)+b", "(a|aa)*c", "(a*)*b", "(a|a)*b", "(.*)*x", "(a?)*(a?)*(a?)*b"]


def random_pattern(rng: random.Random, depth: int) -> str:
    """{a, b} 上のランダムな正規表現（この演習の部分集合で、Python の re でも同じ意味になるもの）。"""
    if depth == 0 or rng.random() < 0.25:
        return rng.choice(["a", "b", "a", "b", "."])
    kind = rng.choice(["cat", "cat", "alt", "star", "plus", "quest", "group", "empty"])
    if kind == "cat":
        return random_pattern(rng, depth - 1) + random_pattern(rng, depth - 1)
    if kind == "alt":
        return random_pattern(rng, depth - 1) + "|" + random_pattern(rng, depth - 1)
    if kind == "group":
        return "(" + random_pattern(rng, depth - 1) + ")"
    if kind == "empty":
        return rng.choice(["()", "(|a)", "(b|)"])
    # 量指定子は必ずグループか 1 文字に付ける（a** のような連続した量指定子を作らない）
    inner = random_pattern(rng, depth - 1)
    if len(inner) > 1:
        inner = "(" + inner + ")"
    return inner + {"star": "*", "plus": "+", "quest": "?"}[kind]


def random_text(rng: random.Random, max_len: int) -> str:
    return "".join(rng.choice("ab") for _ in range(rng.randrange(0, max_len + 1)))


class TestGivenParser(unittest.TestCase):
    """parse は実装済み（読んで理解してください）。構文木の形を確かめておく。"""

    def test_ast_shapes(self):
        self.assertEqual(parse("ab"), Concat((Char("a"), Char("b"))))
        self.assertEqual(parse("a|b|c"), Alt((Char("a"), Char("b"), Char("c"))))
        self.assertEqual(parse("(ab)*"), Star(Concat((Char("a"), Char("b")))))
        self.assertEqual(parse("a+."), Concat((Plus(Char("a")), AnyChar())))
        self.assertEqual(parse(""), Empty())
        self.assertEqual(parse("a|"), Alt((Char("a"), Empty())))
        self.assertEqual(parse(r"\.\*"), Concat((Char("."), Char("*"))))

    def test_syntax_errors(self):
        for bad in ["(", "(a", "a)", "*a", "a**", "a+?", "(*)", "|*", "a\\", r"\d", "[ab]", "a{2}", "^a"]:
            with self.assertRaises(RegexSyntaxError, msg=bad):
                parse(bad)
        self.assertTrue(issubclass(RegexSyntaxError, ValueError))


@with_timeout(5)
class TestExercise5aThompsonNFA(unittest.TestCase):
    def test_examples(self):
        cases = [
            ("abc", "abc", True), ("abc", "abd", False), ("abc", "ab", False),
            ("a|b", "b", True), ("ab|cd", "cd", True), ("ab|cd", "ad", False),
            ("a*", "", True), ("a*", "aaaa", True), ("a*", "aab", False),
            ("a+", "", False), ("a+", "aaa", True),
            ("colou?r", "color", True), ("colou?r", "colour", True), ("colou?r", "colouur", False),
            ("a.c", "abc", True), ("a.c", "a\nc", True), ("a.c", "ac", False),
            ("(ab)+", "ababab", True), ("(ab)+", "abba", False),
            ("(a|b)*abb", "babaabb", True), ("(a|b)*abb", "abab", False),
            (r"1\.5\*2", "1.5*2", True), (r"1\.5\*2", "1x5*2", False),
            ("", "", True), ("", "a", False), ("()", "", True), ("a|", "", True),
            ("こん(にち|ばん)は", "こんばんは", True),
        ]
        for pattern, text, expected in cases:
            self.assertEqual(Regex(pattern).fullmatch(text), expected, (pattern, text))

    def test_search(self):
        self.assertTrue(Regex("b+").search("aaabbbccc"))
        self.assertFalse(Regex("b+").search("aaaccc"))
        self.assertTrue(Regex("").search(""))
        self.assertTrue(Regex("a*").search("xyz"), "空文字列にマッチするパターンは必ず見つかる")
        self.assertTrue(Regex("error: .*timeout").search("2026-09-28 error: db timeout (3s)"))

    def test_syntax_error_propagates(self):
        with self.assertRaises(RegexSyntaxError):
            Regex("(ab")

    def test_state_count_is_linear_in_pattern_length(self):
        for pattern in ["a" * 100, "(a|b)*" * 30, "((a+)?b*)+" * 10, "(" * 50 + "a" + ")*" * 50]:
            program = compile_nfa(parse(pattern))
            self.assertEqual(Regex(pattern).state_count, len(program.states))
            self.assertLessEqual(len(program.states), 2 * len(pattern) + 2, pattern[:30])
            self.assertTrue(0 <= program.start < len(program.states))

    def test_agrees_with_python_re(self):
        rng = random.Random(90)
        for _ in range(300):
            pattern = random_pattern(rng, 4)
            r = Regex(pattern)
            compiled = re.compile(pattern, re.DOTALL)
            for _ in range(15):
                text = random_text(rng, 8)
                self.assertEqual(r.fullmatch(text), compiled.fullmatch(text) is not None, (pattern, text))
                self.assertEqual(r.search(text), compiled.search(text) is not None, (pattern, text))

    def test_pathological_patterns_run_in_linear_time(self):
        text = "a" * 30
        start = time.perf_counter()
        for pattern in PATHOLOGICAL:
            r = Regex(pattern)
            self.assertFalse(r.fullmatch(text), pattern)
            self.assertLessEqual(r.steps, r.state_count * (len(text) + 1), f"{pattern}: 各位置で各状態を 1 回まで")
            self.assertFalse(r.search(text), pattern)
            self.assertLessEqual(r.steps, r.state_count * (len(text) + 1), f"{pattern}: 各位置で各状態を 1 回まで")
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 1.0, f"{elapsed:.2f} 秒。バックトラックしていませんか")

    def test_steps_grow_linearly(self):
        r = Regex("(a|b)*a(a|b)(a|b)(a|b)")
        rng = random.Random(91)
        text = "".join(rng.choice("ab") for _ in range(4000))
        r.fullmatch(text[:2000])
        s1 = r.steps
        r.fullmatch(text)
        s2 = r.steps
        self.assertGreater(s1, 0, "steps を数えてください")
        self.assertLess(s2 / s1, 2.2, "入力を 2 倍にしたら、ステップ数もおよそ 2 倍のはず")

    def test_cloudflare_like_pattern(self):
        # 2019 年の Cloudflare の障害で問題になった正規表現の一部（.*.*=.*）を簡略化したもの
        r = Regex(".*.*=.*")
        long_line = "x" * 20_000
        start = time.perf_counter()
        self.assertFalse(r.search(long_line))
        self.assertTrue(r.search(long_line + "=1"))
        self.assertLess(time.perf_counter() - start, 3.0)


@with_timeout(5)
class TestExercise5bBacktracking(unittest.TestCase):
    def test_examples(self):
        for pattern, text, expected in [
            ("abc", "abc", True), ("a|b", "c", False), ("(a|b)*abb", "aabb", True),
            ("a+", "", False), ("colou?r", "colour", True), ("a.c", "axc", True), ("", "", True),
        ]:
            matched, steps = backtrack_fullmatch(pattern, text)
            self.assertEqual(matched, expected, (pattern, text))
            self.assertGreater(steps, 0)

    def test_empty_loops_terminate(self):
        self.assertTrue(backtrack_fullmatch("()*", "")[0])
        self.assertTrue(backtrack_fullmatch("()*a", "a")[0])
        self.assertTrue(backtrack_fullmatch("(a*)*", "aaa")[0])
        self.assertFalse(backtrack_fullmatch("(a*)*b", "a" * 10, max_steps=10**6)[0])

    def test_agrees_with_python_re(self):
        rng = random.Random(92)
        for _ in range(200):
            pattern = random_pattern(rng, 3)
            compiled = re.compile(pattern, re.DOTALL)
            for _ in range(8):
                text = random_text(rng, 6)
                matched, _ = backtrack_fullmatch(pattern, text, max_steps=10**6)
                self.assertEqual(matched, compiled.fullmatch(text) is not None, (pattern, text))

    def test_exponential_growth(self):
        steps = [backtrack_fullmatch("(a+)+b", "a" * n)[1] for n in range(8, 14)]
        for n, (s1, s2) in enumerate(zip(steps, steps[1:]), start=8):
            self.assertGreater(s2 / s1, 1.8, f"n={n}→{n + 1} でステップ数がほぼ倍増するはず（素朴なバックトラック）")

    def test_step_limit(self):
        with self.assertRaises(StepLimitExceeded):
            backtrack_fullmatch("(a+)+b", "a" * 30, max_steps=100_000)
        matched, steps = backtrack_fullmatch("(a+)+b", "a" * 5 + "b", max_steps=100_000)
        self.assertTrue(matched)
        self.assertLessEqual(steps, 100_000)

    def test_thompson_vs_backtracking(self):
        n = 14
        text = "a" * n
        r = Regex("(a+)+b")
        t0 = time.perf_counter()
        bt_matched, bt_steps = backtrack_fullmatch("(a+)+b", text)
        t_backtrack = time.perf_counter() - t0
        t0 = time.perf_counter()
        th_matched = r.fullmatch(text)
        t_thompson = time.perf_counter() - t0
        self.assertEqual(bt_matched, th_matched)
        self.assertGreater(bt_steps, 100 * r.steps, f"バックトラック {bt_steps} ステップ / Thompson {r.steps} ステップ")
        self.assertLess(
            t_thompson * 10, t_backtrack,
            f"Thompson {t_thompson * 1000:.2f}ms / バックトラック {t_backtrack * 1000:.2f}ms",
        )


if __name__ == "__main__":
    unittest.main()
