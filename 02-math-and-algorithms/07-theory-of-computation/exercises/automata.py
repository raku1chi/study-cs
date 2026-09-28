"""2.7 計算理論 — 演習（有限オートマトンとスタック: 演習1〜4）

各クラス・関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
正規表現エンジンの演習（演習5）は thompson_regex.py にあります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.7          # 合格数を表示（automata と thompson_regex の両方）
    python3 tools/check.py -v 2.7       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_automata

オートマトンの表し方（この演習の約束）:
    - 状態はハッシュ可能な任意の値（整数・文字列・frozenset など）。
    - 記号は 1 文字の文字列。入力は記号を並べた文字列。
    - DFA の遷移は dict: (状態, 記号) -> 次の状態。定義されていない組は「行き止まり」
      （以後どんな入力が来ても受理しない状態）へ行くものとみなす。
    - NFA の遷移は dict: (状態, 記号) -> 次の状態の集合。記号 EPSILON（空文字列 ""）は ε 遷移
      （入力を読まずに移れる遷移）を表す。
"""
from __future__ import annotations

from collections import deque  # noqa: F401  演習3で使えます
from dataclasses import dataclass, field
from typing import Hashable, Iterable, Mapping

State = Hashable
EPSILON = ""  # ε 遷移を表す記号（空文字列）


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: DFA（決定性有限オートマトン）
# ---------------------------------------------------------------------------

@dataclass
class DFA:
    """決定性有限オートマトン (Q, Σ, δ, q0, F)。フィールドの定義は実装済みです。

    - states: 状態の集合 Q
    - alphabet: 入力記号の集合 Σ
    - transitions: 遷移関数 δ。{(状態, 記号): 次の状態}（一部が欠けていてもよい）
    - start: 開始状態 q0
    - accepting: 受理状態の集合 F
    """

    states: set
    alphabet: set[str]
    transitions: dict[tuple[State, str], State]
    start: State
    accepting: set = field(default_factory=set)

    def accepts(self, s: str) -> bool:
        """入力 s を先頭から 1 文字ずつ読み、最後に受理状態にいれば True。

        - s にアルファベットにない記号が含まれていれば ValueError。
        - 遷移が定義されていない (状態, 記号) に出会ったら、その時点で False（行き止まり）。
        - 入力の長さ n に対して O(n) 時間・O(1) メモリ（状態を 1 つ覚えるだけ）。

        >>> dfa = DFA({0, 1}, {"a"}, {(0, "a"): 1, (1, "a"): 0}, start=0, accepting={0})
        >>> dfa.accepts("aa"), dfa.accepts("aaa")
        (True, False)
        """
        raise NotImplementedError("演習1: DFA.accepts を実装してください")


def divisible_by_dfa(k: int) -> DFA:
    """2 進数の文字列（"0" と "1" の列）のうち、値が k で割り切れるものを受理する DFA を返す。

    - 状態は 0, 1, ..., k-1 の整数（= それまでに読んだ 2 進数を k で割った余り）。
      states = {0, ..., k-1}、alphabet = {"0", "1"}、start = 0、accepting = {0}。
    - 先頭の 0 は許す（"0011" は 3）。空文字列は値 0 とみなして受理する。
    - k < 1 なら ValueError。

    >>> dfa = divisible_by_dfa(3)
    >>> [dfa.accepts(bin(n)[2:]) for n in range(7)]
    [True, False, False, True, False, False, True]

    ヒント: 値 v の 2 進数の後ろにビット b を付けると、値は 2v + b になる。
    余り r の状態で b を読んだら、次の余りは (2r + b) mod k。
    """
    raise NotImplementedError("演習1: divisible_by_dfa を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ε 遷移つき NFA（非決定性有限オートマトン）
# ---------------------------------------------------------------------------

@dataclass
class NFA:
    """ε 遷移つきの非決定性有限オートマトン。フィールドの定義は実装済みです。

    - transitions: {(状態, 記号): 次の状態の集合}。記号が EPSILON（""）なら ε 遷移。
    - そのほかは DFA と同じ。
    """

    states: set
    alphabet: set[str]
    transitions: dict[tuple[State, str], set]
    start: State
    accepting: set = field(default_factory=set)

    def epsilon_closure(self, states: Iterable[State]) -> frozenset:
        """states と、そこから ε 遷移だけを 0 回以上たどって行ける状態をすべて集めた frozenset を返す。

        ε 遷移が循環していても止まること（訪問済みの状態を記録する）。

        >>> nfa = NFA({0, 1, 2}, {"a"}, {(0, EPSILON): {1}, (1, EPSILON): {2}}, start=0, accepting={2})
        >>> sorted(nfa.epsilon_closure([0]))
        [0, 1, 2]
        """
        raise NotImplementedError("演習2: NFA.epsilon_closure を実装してください")

    def step(self, states: Iterable[State], symbol: str) -> frozenset:
        """状態の集合 states から記号 symbol を 1 つ読んだ後の状態の集合（ε 閉包を取ったもの）を返す。

        states はすでに ε 閉包になっているものとしてよい。
        symbol がアルファベットにない記号なら ValueError。
        """
        raise NotImplementedError("演習2: NFA.step を実装してください")

    def accepts(self, s: str) -> bool:
        """「今いる可能性のある状態の集合」を 1 つ持って入力を読み進め、
        最後にその集合が受理状態を 1 つでも含めば True。

        開始時の集合は epsilon_closure([start])。記号がアルファベットになければ ValueError。

        ヒント: 分岐ごとにやり直す（バックトラックする）のではなく、すべての可能性を同時に追う。
        これが演習5の正規表現エンジンの核心でもある。
        """
        raise NotImplementedError("演習2: NFA.accepts を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 部分集合構成法（NFA → DFA）
# ---------------------------------------------------------------------------

def nfa_to_dfa(nfa: NFA) -> DFA:
    """NFA と同じ言語を受理する DFA を、部分集合構成法（subset construction）で作る。

    - DFA の各状態は、NFA の状態の frozenset。
    - 開始状態は nfa.epsilon_closure([nfa.start])。
    - 開始状態から到達できる集合だけを作る（すべての部分集合 2^|Q| 個を作ってはいけない）。
    - 集合 S と記号 a について T = nfa.step(S, a)。T が空集合なら遷移を作らない（行き止まり）。
      したがって空集合は DFA の状態に含めない。
    - 受理状態は、NFA の受理状態を 1 つでも含む集合すべて。
    - alphabet は NFA と同じ。

    >>> nfa = NFA({0, 1}, {"a", "b"}, {(0, "a"): {0, 1}, (0, "b"): {0}}, start=0, accepting={1})
    >>> dfa = nfa_to_dfa(nfa)          # 「a で終わる列」を受理する
    >>> len(dfa.states), dfa.accepts("ba"), dfa.accepts("ab")
    (2, True, False)

    ヒント: キューに「未処理の集合」を入れて幅優先で広げる。すでに作った集合は set で覚えておく。
    """
    raise NotImplementedError("演習3: nfa_to_dfa を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★☆☆）: 括弧の対応（スタック = プッシュダウンオートマトン）
# ---------------------------------------------------------------------------

DEFAULT_PAIRS = {"(": ")", "[": "]", "{": "}"}


def first_error_index(s: str, pairs: Mapping[str, str] | None = None) -> int | None:
    """括弧の対応が正しければ None、正しくなければ最初に見つかった誤りの位置（添字）を返す。

    - pairs は {開き括弧: 閉じ括弧}。None なら DEFAULT_PAIRS。それ以外の文字は無視する。
    - 誤りの位置:
        - 閉じ括弧が、直近に開いたまだ閉じていない括弧と対応しない（または開いた括弧がない）
          → その閉じ括弧の位置
        - 最後まで読んで閉じられていない括弧が残った → そのうち最も内側（最後に開いたもの）の位置
          （Python 自身の構文エラーの報告と同じ方針）

    >>> first_error_index("f(a[0])")
    >>> first_error_index("([)]")
    2
    >>> first_error_index("x = f(a, g(b)")
    5

    ヒント: 開き括弧を (文字, 位置) としてスタックに積み、閉じ括弧で取り出して照合する。
    入れ子の深さに上限がないので、有限個の状態（DFA）では判定できない。スタックが必要になる。
    """
    raise NotImplementedError("演習4: first_error_index を実装してください")


def is_balanced(s: str, pairs: Mapping[str, str] | None = None) -> bool:
    """括弧の対応が正しければ True（first_error_index(s, pairs) is None と同じ）。

    >>> is_balanced("([{}])"), is_balanced("(]")
    (True, False)
    """
    raise NotImplementedError("演習4: is_balanced を実装してください")
