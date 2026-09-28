"""2.7 計算理論 — テスト（有限オートマトンとスタック: 演習1〜4）

実行: python3 tools/check.py 2.7   （またはこのディレクトリで python3 -m unittest -v）
"""
import functools
import itertools
import re
import threading
import unittest

from automata import DFA, EPSILON, NFA, divisible_by_dfa, first_error_index, is_balanced, nfa_to_dfa



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


def all_strings(alphabet: str, max_len: int):
    for n in range(max_len + 1):
        for t in itertools.product(alphabet, repeat=n):
            yield "".join(t)


def dragon_book_nfa() -> NFA:
    """(a|b)*abb を Thompson の構成法で作った ε-NFA（教科書『コンパイラ』（通称ドラゴンブック）の有名な例）。"""
    t = {
        (0, EPSILON): {1, 7},
        (1, EPSILON): {2, 4},
        (2, "a"): {3},
        (4, "b"): {5},
        (3, EPSILON): {6},
        (5, EPSILON): {6},
        (6, EPSILON): {1, 7},
        (7, "a"): {8},
        (8, "b"): {9},
        (9, "b"): {10},
    }
    return NFA(states=set(range(11)), alphabet={"a", "b"}, transitions=t, start=0, accepting={10})


def nth_from_last_nfa(n: int) -> NFA:
    """「後ろから n 番目の文字が 1」である 0/1 の列を受理する NFA（状態数 n + 1）。"""
    t = {(0, "0"): {0}, (0, "1"): {0, 1}}
    for i in range(1, n):
        t[(i, "0")] = {i + 1}
        t[(i, "1")] = {i + 1}
    return NFA(states=set(range(n + 1)), alphabet={"0", "1"}, transitions=t, start=0, accepting={n})


class TestExercise1DFA(unittest.TestCase):
    def test_simple_dfa(self):
        # 「a が偶数個」の列を受理する DFA
        even_a = DFA(
            states={"even", "odd"},
            alphabet={"a", "b"},
            transitions={("even", "a"): "odd", ("odd", "a"): "even", ("even", "b"): "even", ("odd", "b"): "odd"},
            start="even",
            accepting={"even"},
        )
        self.assertTrue(even_a.accepts(""))
        self.assertTrue(even_a.accepts("abba"))
        self.assertFalse(even_a.accepts("ab"))

    def test_missing_transition_rejects(self):
        only_ab = DFA(states={0, 1, 2}, alphabet={"a", "b"}, transitions={(0, "a"): 1, (1, "b"): 2}, start=0, accepting={2})
        self.assertTrue(only_ab.accepts("ab"))
        self.assertFalse(only_ab.accepts("abb"), "遷移が定義されていなければ、その時点で受理しない")
        self.assertFalse(only_ab.accepts("b"))

    def test_symbol_not_in_alphabet(self):
        with self.assertRaises(ValueError):
            divisible_by_dfa(3).accepts("102")

    def test_divisible_by_3(self):
        dfa = divisible_by_dfa(3)
        self.assertEqual(dfa.states, {0, 1, 2})
        self.assertEqual(dfa.alphabet, {"0", "1"})
        for s in all_strings("01", 10):
            self.assertEqual(dfa.accepts(s), (int(s, 2) if s else 0) % 3 == 0, s)

    def test_divisible_by_k(self):
        for k in range(1, 13):
            dfa = divisible_by_dfa(k)
            self.assertEqual(len(dfa.states), k)
            for s in all_strings("01", 8):
                self.assertEqual(dfa.accepts(s), (int(s, 2) if s else 0) % k == 0, (k, s))
        with self.assertRaises(ValueError):
            divisible_by_dfa(0)

    def test_long_input(self):
        n = 3 ** 200
        self.assertTrue(divisible_by_dfa(3).accepts(bin(n)[2:]))
        self.assertFalse(divisible_by_dfa(3).accepts(bin(n + 1)[2:]))


@with_timeout(5)
class TestExercise2NFA(unittest.TestCase):
    def test_epsilon_closure(self):
        nfa = dragon_book_nfa()
        self.assertEqual(nfa.epsilon_closure([0]), frozenset({0, 1, 2, 4, 7}))
        self.assertEqual(nfa.epsilon_closure([3]), frozenset({1, 2, 3, 4, 6, 7}))
        self.assertEqual(nfa.epsilon_closure([]), frozenset())
        self.assertIsInstance(nfa.epsilon_closure([8]), frozenset)

    def test_epsilon_cycle_terminates(self):
        nfa = NFA(
            states={"p", "q", "r"},
            alphabet={"x"},
            transitions={("p", EPSILON): {"q"}, ("q", EPSILON): {"p", "r"}},
            start="p",
            accepting={"r"},
        )
        self.assertEqual(nfa.epsilon_closure(["p"]), frozenset({"p", "q", "r"}))
        self.assertTrue(nfa.accepts(""))

    def test_step(self):
        nfa = dragon_book_nfa()
        a = nfa.epsilon_closure([0])
        self.assertEqual(nfa.step(a, "a"), frozenset({1, 2, 3, 4, 6, 7, 8}))
        self.assertEqual(nfa.step(a, "b"), frozenset({1, 2, 4, 5, 6, 7}))
        with self.assertRaises(ValueError):
            nfa.step(a, "c")

    def test_accepts_matches_regex(self):
        nfa = dragon_book_nfa()
        for s in all_strings("ab", 8):
            self.assertEqual(nfa.accepts(s), re.fullmatch("(a|b)*abb", s) is not None, s)
        with self.assertRaises(ValueError):
            nfa.accepts("abc")

    def test_nth_from_last(self):
        nfa = nth_from_last_nfa(3)
        for s in all_strings("01", 8):
            self.assertEqual(nfa.accepts(s), len(s) >= 3 and s[-3] == "1", s)


@with_timeout(5)
class TestExercise3SubsetConstruction(unittest.TestCase):
    def assert_equivalent(self, nfa, dfa, alphabet, max_len):
        for s in all_strings(alphabet, max_len):
            self.assertEqual(dfa.accepts(s), nfa.accepts(s), s)

    def test_dragon_book_example(self):
        nfa = dragon_book_nfa()
        dfa = nfa_to_dfa(nfa)
        self.assertEqual(len(dfa.states), 5, "教科書どおり A〜E の 5 状態になる")
        self.assertEqual(dfa.start, frozenset({0, 1, 2, 4, 7}))
        self.assertEqual(dfa.accepting, {frozenset({1, 2, 4, 5, 6, 7, 10})})
        self.assertEqual(dfa.alphabet, {"a", "b"})
        for (src, sym), dst in dfa.transitions.items():
            self.assertIn(src, dfa.states)
            self.assertIn(dst, dfa.states)
            self.assertIn(sym, dfa.alphabet)
        self.assert_equivalent(nfa, dfa, "ab", 9)

    def test_exponential_blowup(self):
        # NFA なら n + 1 状態で済む言語が、DFA ではちょうど 2^n 状態を必要とする
        for n in range(1, 9):
            nfa = nth_from_last_nfa(n)
            dfa = nfa_to_dfa(nfa)
            self.assertEqual(len(dfa.states), 2 ** n, f"n={n}")
        self.assert_equivalent(nth_from_last_nfa(4), nfa_to_dfa(nth_from_last_nfa(4)), "01", 9)

    def test_only_reachable_nonempty_subsets(self):
        # 状態 9 は開始状態から到達できない。空集合（行き止まり）も状態にしない
        nfa = NFA(
            states={0, 1, 2, 9},
            alphabet={"a", "b"},
            transitions={(0, "a"): {1}, (1, "b"): {2}, (9, "a"): {9}},
            start=0,
            accepting={2},
        )
        dfa = nfa_to_dfa(nfa)
        self.assertEqual(dfa.states, {frozenset({0}), frozenset({1}), frozenset({2})})
        self.assertTrue(dfa.accepts("ab"))
        self.assertFalse(dfa.accepts("aa"))


class TestExercise4Brackets(unittest.TestCase):
    def test_balanced(self):
        for s in ["", "()", "()[]{}", "([{}])", "a(b[c]{d}e)f", "no brackets"]:
            self.assertTrue(is_balanced(s), s)
            self.assertIsNone(first_error_index(s), s)

    def test_unbalanced(self):
        for s in ["(", ")", "(]", "(()", "())", "([)]", "{[}"]:
            self.assertFalse(is_balanced(s), s)

    def test_error_positions(self):
        self.assertEqual(first_error_index("a)"), 1, "開いていないのに閉じた")
        self.assertEqual(first_error_index("([)]"), 2, "直近に開いた [ と ) が対応しない")
        self.assertEqual(first_error_index("{[}"), 2)
        self.assertEqual(first_error_index("(()"), 0, "閉じられていない括弧の位置")
        self.assertEqual(first_error_index("(("), 1, "閉じられていない括弧が複数あれば、最も内側（最後に開いたもの）")
        self.assertEqual(first_error_index("x = f(a, g(b)"), 5)

    def test_custom_pairs(self):
        pairs = {"「": "」", "<": ">"}
        self.assertTrue(is_balanced("「こんにちは「世界」」<a>", pairs))
        self.assertFalse(is_balanced("「<」>", pairs))
        self.assertTrue(is_balanced("(", pairs), "pairs にない文字は無視する")

    def test_deep_nesting(self):
        depth = 100_000  # 入れ子の深さに上限はない。有限状態では数えきれないが、スタックなら扱える
        self.assertTrue(is_balanced("(" * depth + ")" * depth))
        self.assertEqual(first_error_index("(" * depth + ")" * (depth - 1)), 0)


if __name__ == "__main__":
    unittest.main()
