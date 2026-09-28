"""2.7 計算理論 — 解答例（有限オートマトンとスタック）

演習の仕様は exercises/automata.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Hashable, Iterable, Mapping

State = Hashable
EPSILON = ""  # ε 遷移を表す記号（空文字列）


# ---------------------------------------------------------------------------
# 演習1: DFA
# ---------------------------------------------------------------------------

@dataclass
class DFA:
    states: set
    alphabet: set[str]
    transitions: dict[tuple[State, str], State]
    start: State
    accepting: set = field(default_factory=set)

    def accepts(self, s: str) -> bool:
        for ch in s:
            if ch not in self.alphabet:
                raise ValueError(f"アルファベットにない記号です: {ch!r}")
        state = self.start
        for ch in s:
            # 状態は「これまでに読んだ入力について覚えておくべきことの要約」。
            # 1 文字読むたびに表を 1 回引くだけなので、入力の長さに比例する時間で終わる
            nxt = self.transitions.get((state, ch))
            if nxt is None:
                return False  # 遷移が定義されていない = 二度と受理しない「行き止まり状態」
            state = nxt
        return state in self.accepting


def divisible_by_dfa(k: int) -> DFA:
    if k < 1:
        raise ValueError(f"k は 1 以上: {k}")
    # 状態 r = 「ここまでに読んだ 2 進数を k で割った余り」。
    # 次のビット b を読むと、値は 2 × 値 + b になるので、余りは (2r + b) mod k に移る
    transitions = {(r, b): (2 * r + int(b)) % k for r in range(k) for b in "01"}
    return DFA(states=set(range(k)), alphabet={"0", "1"}, transitions=transitions, start=0, accepting={0})


# ---------------------------------------------------------------------------
# 演習2: ε 遷移つき NFA
# ---------------------------------------------------------------------------

@dataclass
class NFA:
    states: set
    alphabet: set[str]
    transitions: dict[tuple[State, str], set]
    start: State
    accepting: set = field(default_factory=set)

    def epsilon_closure(self, states: Iterable[State]) -> frozenset:
        # ε 遷移だけで行ける状態をすべて集める（グラフの到達可能性。ε の循環があっても止まる）
        closure = set(states)
        stack = list(closure)
        while stack:
            q = stack.pop()
            for r in self.transitions.get((q, EPSILON), ()):
                if r not in closure:
                    closure.add(r)
                    stack.append(r)
        return frozenset(closure)

    def step(self, states: Iterable[State], symbol: str) -> frozenset:
        if symbol not in self.alphabet:
            raise ValueError(f"アルファベットにない記号です: {symbol!r}")
        moved: set = set()
        for q in states:
            moved.update(self.transitions.get((q, symbol), ()))
        return self.epsilon_closure(moved)

    def accepts(self, s: str) -> bool:
        # 「今いる可能性のある状態の集合」を 1 つ持って進める。
        # 分岐のたびにやり直す（バックトラック）のではなく、全部の可能性を同時に追う
        current = self.epsilon_closure([self.start])
        for ch in s:
            current = self.step(current, ch)
        return not current.isdisjoint(self.accepting)


# ---------------------------------------------------------------------------
# 演習3: 部分集合構成法（NFA → DFA）
# ---------------------------------------------------------------------------

def nfa_to_dfa(nfa: NFA) -> DFA:
    # NFA のシミュレーションで現れる「状態の集合」そのものを、DFA の 1 つの状態にする
    start = nfa.epsilon_closure([nfa.start])
    states = {start}
    transitions: dict[tuple[frozenset, str], frozenset] = {}
    queue = deque([start])
    symbols = sorted(nfa.alphabet)
    while queue:
        S = queue.popleft()
        for a in symbols:
            T = nfa.step(S, a)
            if not T:
                continue  # 空集合 = 行き止まり。遷移を定義しないことで表す
            transitions[(S, a)] = T
            if T not in states:
                states.add(T)
                queue.append(T)
    accepting = {S for S in states if not S.isdisjoint(nfa.accepting)}
    return DFA(states=states, alphabet=set(nfa.alphabet), transitions=transitions, start=start, accepting=accepting)


# ---------------------------------------------------------------------------
# 演習4: 括弧の対応（スタック = プッシュダウンオートマトン）
# ---------------------------------------------------------------------------

DEFAULT_PAIRS = {"(": ")", "[": "]", "{": "}"}


def first_error_index(s: str, pairs: Mapping[str, str] | None = None) -> int | None:
    pairs = DEFAULT_PAIRS if pairs is None else pairs
    closers = {c: o for o, c in pairs.items()}
    stack: list[tuple[str, int]] = []  # (開き括弧, 位置)
    for i, ch in enumerate(s):
        if ch in pairs:
            stack.append((ch, i))
        elif ch in closers:
            # 閉じ括弧は「直近に開いた、まだ閉じていない括弧」と対応しなければならない。
            # 入れ子の深さに上限がないので、有限個の状態（DFA）では覚えきれず、スタックが要る
            if not stack or stack[-1][0] != closers[ch]:
                return i
            stack.pop()
    if stack:
        return stack[-1][1]  # 閉じられていない括弧のうち、最も内側（最後に開いたもの）
    return None


def is_balanced(s: str, pairs: Mapping[str, str] | None = None) -> bool:
    return first_error_index(s, pairs) is None
