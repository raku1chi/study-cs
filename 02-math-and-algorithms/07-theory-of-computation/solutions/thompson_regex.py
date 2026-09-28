"""2.7 計算理論 — 解答例（Thompson の構成法による正規表現エンジン）

演習の仕様は exercises/thompson_regex.py の docstring を参照してください。
構文解析器（parse）は演習ファイルと同じもの（実装済みの部品）です。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

# ---------------------------------------------------------------------------
# 構文木（AST）と構文解析器 — 実装済みの部品（演習ファイルと同じ）
# ---------------------------------------------------------------------------


class RegexSyntaxError(ValueError):
    """正規表現の構文エラー。"""


@dataclass(frozen=True)
class Char:
    c: str  # この 1 文字にマッチ


@dataclass(frozen=True)
class AnyChar:
    pass  # 任意の 1 文字にマッチ（改行も含む）


@dataclass(frozen=True)
class Empty:
    pass  # 空文字列にマッチ（"()" や "a|" の空の側）


@dataclass(frozen=True)
class Concat:
    parts: tuple  # 2 つ以上の部分を順に連結


@dataclass(frozen=True)
class Alt:
    options: tuple  # 2 つ以上の選択肢のどれか


@dataclass(frozen=True)
class Star:
    inner: "Node"  # 0 回以上の繰り返し


@dataclass(frozen=True)
class Plus:
    inner: "Node"  # 1 回以上の繰り返し


@dataclass(frozen=True)
class Quest:
    inner: "Node"  # 0 回または 1 回


Node = Union[Char, AnyChar, Empty, Concat, Alt, Star, Plus, Quest]

_META = set("|*+?().\\")
_UNSUPPORTED = set("^$[]{}")


def parse(pattern: str) -> Node:
    """正規表現の文字列を構文木にする（再帰下降構文解析。文法は演習ファイル参照）。"""
    pos = 0
    n = len(pattern)

    def peek() -> str:
        return pattern[pos] if pos < n else ""

    def alt() -> Node:
        nonlocal pos
        options = [concat()]
        while peek() == "|":
            pos += 1
            options.append(concat())
        return options[0] if len(options) == 1 else Alt(tuple(options))

    def concat() -> Node:
        parts = []
        while pos < n and pattern[pos] not in "|)":
            parts.append(repeat())
        if not parts:
            return Empty()
        return parts[0] if len(parts) == 1 else Concat(tuple(parts))

    def repeat() -> Node:
        nonlocal pos
        node = atom()
        if peek() in ("*", "+", "?"):
            q = pattern[pos]
            pos += 1
            node = {"*": Star, "+": Plus, "?": Quest}[q](node)
            if peek() in ("*", "+", "?"):
                raise RegexSyntaxError(f"量指定子が連続しています（位置 {pos}）")
        return node

    def atom() -> Node:
        nonlocal pos
        c = pattern[pos]
        if c == "(":
            pos += 1
            node = alt()
            if peek() != ")":
                raise RegexSyntaxError(f"')' が足りません（位置 {pos}）")
            pos += 1
            return node
        if c in "*+?":
            raise RegexSyntaxError(f"繰り返す対象がありません: {c!r}（位置 {pos}）")
        if c == ".":
            pos += 1
            return AnyChar()
        if c == "\\":
            if pos + 1 >= n:
                raise RegexSyntaxError("パターンの末尾が \\ で終わっています")
            nxt = pattern[pos + 1]
            if nxt not in _META and nxt not in _UNSUPPORTED:
                raise RegexSyntaxError(f"未対応のエスケープです: \\{nxt}（位置 {pos}）")
            pos += 2
            return Char(nxt)
        if c in _UNSUPPORTED:
            raise RegexSyntaxError(f"未対応の特殊文字です: {c!r}（位置 {pos}）。文字として使うなら \\{c}")
        pos += 1
        return Char(c)

    node = alt()
    if pos < n:
        raise RegexSyntaxError(f"対応する '(' のない ')' があります（位置 {pos}）")
    return node


# ---------------------------------------------------------------------------
# NFA の表現 — 実装済みの部品（演習ファイルと同じ）
# ---------------------------------------------------------------------------


@dataclass
class State:
    kind: str  # "char" | "any" | "split" | "jump" | "match"
    char: str = ""  # kind == "char" のときの文字
    out: int = -1  # 次の状態（char/any は 1 文字読んだ後、split は 1 つ目の分岐、jump は ε 遷移先）
    out2: int = -1  # split の 2 つ目の分岐


@dataclass
class Program:
    states: list  # list[State]。添字が状態番号
    start: int


# ---------------------------------------------------------------------------
# 演習5a: Thompson の構成法
# ---------------------------------------------------------------------------

def compile_nfa(node: Node) -> Program:
    states: list[State] = []

    def new(kind: str, char: str = "", out: int = -1, out2: int = -1) -> int:
        states.append(State(kind, char, out, out2))
        return len(states) - 1

    # 「この部分を読み終えたら nxt へ進む」断片を、後ろから組み立てる（継続を渡す書き方）。
    # 各構文要素が作る状態は高々 1 個なので、状態数はパターンの長さに比例する
    def build(node: Node, nxt: int) -> int:
        if isinstance(node, Char):
            return new("char", node.c, nxt)
        if isinstance(node, AnyChar):
            return new("any", out=nxt)
        if isinstance(node, Empty):
            return nxt  # 何も読まずに次へ（状態を作る必要がない）
        if isinstance(node, Concat):
            for part in reversed(node.parts):
                nxt = build(part, nxt)
            return nxt
        if isinstance(node, Alt):
            starts = [build(opt, nxt) for opt in node.options]
            s = starts[-1]
            for st in reversed(starts[:-1]):
                s = new("split", out=st, out2=s)  # split(1つ目, split(2つ目, ...))
            return s
        if isinstance(node, Star):
            # split ─(1つ目)→ 本体 ─→ split に戻る / split ─(2つ目)→ nxt
            loop = new("split", out2=nxt)
            states[loop].out = build(node.inner, loop)
            return loop
        if isinstance(node, Plus):
            # 本体を 1 回通ってから split に来る。split から本体に戻るか nxt へ抜ける
            loop = new("split", out2=nxt)
            body = build(node.inner, loop)
            states[loop].out = body
            return body
        if isinstance(node, Quest):
            return new("split", out=build(node.inner, nxt), out2=nxt)
        raise TypeError(f"未知の構文木ノード: {node!r}")

    match = new("match")
    return Program(states, build(node, match))


class Regex:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern
        self.program = compile_nfa(parse(pattern))
        self.steps = 0
        # 状態ごとに「最後に追加した世代」を記録し、同じ位置で同じ状態を二度追加しない
        self._mark = [-1] * len(self.program.states)
        self._gen = 0

    @property
    def state_count(self) -> int:
        return len(self.program.states)

    def _add(self, lst: list[int], s: int) -> None:
        """状態 s と、そこから ε（split / jump）だけで行ける状態のうち、
        文字を読む状態（char / any）と match を lst に加える。"""
        states, mark, gen = self.program.states, self._mark, self._gen
        stack = [s]
        while stack:
            i = stack.pop()
            if mark[i] == gen:
                continue  # この位置ではすでに追加済み（ε の循環もここで止まる）
            mark[i] = gen
            self.steps += 1
            st = states[i]
            if st.kind == "split":
                stack.append(st.out2)
                stack.append(st.out)
            elif st.kind == "jump":
                stack.append(st.out)
            else:
                lst.append(i)

    def _step(self, clist: list[int], ch: str) -> list[int]:
        self._gen += 1
        nlist: list[int] = []
        states = self.program.states
        for i in clist:
            st = states[i]
            if st.kind == "any" or (st.kind == "char" and st.char == ch):
                self._add(nlist, st.out)
        return nlist

    def _has_match(self, lst: list[int]) -> bool:
        states = self.program.states
        return any(states[i].kind == "match" for i in lst)

    def fullmatch(self, text: str) -> bool:
        self.steps = 0
        self._gen += 1
        clist: list[int] = []
        self._add(clist, self.program.start)
        # 1 文字ごとに「今いる可能性のある状態の集合」を 1 回更新するだけ。
        # 各位置で各状態を高々 1 回しか処理しないので O(状態数 × 文字数)。バックトラックしない
        for ch in text:
            clist = self._step(clist, ch)
            if not clist:
                return False
        return self._has_match(clist)

    def search(self, text: str) -> bool:
        self.steps = 0
        self._gen += 1
        clist: list[int] = []
        self._add(clist, self.program.start)
        if self._has_match(clist):
            return True
        for ch in text:
            clist = self._step(clist, ch)
            # 次の位置から始まるマッチの試みも、同じ集合に合流させる（先頭に .* を付けたのと同じ）
            self._add(clist, self.program.start)
            if self._has_match(clist):
                return True
        return False


# ---------------------------------------------------------------------------
# 演習5b: 素朴なバックトラッキング型マッチャ（比較用）
# ---------------------------------------------------------------------------


class StepLimitExceeded(Exception):
    """バックトラッキングの試行回数が上限を超えた。"""


def backtrack_fullmatch(pattern: str, text: str, max_steps: int | None = None) -> tuple[bool, int]:
    node = parse(pattern)
    n = len(text)
    steps = 0

    # m(node, i, k): text[i:] の先頭で node にマッチさせ、残りを継続 k に任せる。
    # うまくいかなければ別の選択肢を試す（バックトラック）。選択肢の組み合わせが指数個になりうる
    def m(node: Node, i: int, k: Callable[[int], bool]) -> bool:
        nonlocal steps
        steps += 1
        if max_steps is not None and steps > max_steps:
            raise StepLimitExceeded(f"{max_steps} ステップを超えました")
        if isinstance(node, Char):
            return i < n and text[i] == node.c and k(i + 1)
        if isinstance(node, AnyChar):
            return i < n and k(i + 1)
        if isinstance(node, Empty):
            return k(i)
        if isinstance(node, Concat):
            parts = node.parts

            def seq(idx: int, j: int) -> bool:
                if idx == len(parts):
                    return k(j)
                return m(parts[idx], j, lambda j2: seq(idx + 1, j2))

            return seq(0, i)
        if isinstance(node, Alt):
            return any(m(opt, i, k) for opt in node.options)
        if isinstance(node, Star):
            # 欲張り（greedy）: まず「もう 1 回繰り返す」を試し、だめなら「ここでやめる」。
            # 空文字列にマッチする本体で無限ループしないよう、1 文字も進まない繰り返しは認めない
            return m(node.inner, i, lambda j: j != i and m(node, j, k)) or k(i)
        if isinstance(node, Plus):
            return m(node.inner, i, lambda j: m(Star(node.inner), j, k))
        if isinstance(node, Quest):
            return m(node.inner, i, k) or k(i)
        raise TypeError(f"未知の構文木ノード: {node!r}")

    matched = m(node, 0, lambda j: j == n)
    return matched, steps
