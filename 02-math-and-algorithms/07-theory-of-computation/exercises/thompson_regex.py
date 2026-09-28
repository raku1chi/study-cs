"""2.7 計算理論 — 演習（Thompson の構成法による正規表現エンジン: 演習5）

構文木（AST）・構文解析器 parse()・NFA の表現（State, Program）は実装済みです。まず読んで理解してください。
`raise NotImplementedError(...)` の部分（compile_nfa・Regex・backtrack_fullmatch）を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.7          # 合格数を表示（automata と thompson_regex の両方）
    python3 tools/check.py -v 2.7       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_thompson_regex

対応する正規表現（Python の re と同じ意味になる部分集合）:
    a       その文字 1 文字（通常の文字）
    .       任意の 1 文字（改行も含む。re.DOTALL を付けた Python の re と同じ）
    xy      連結
    x|y     選択（どちらか）。空の選択肢も書ける（"a|" は "a" または空文字列）
    x*      0 回以上の繰り返し
    x+      1 回以上の繰り返し
    x?      0 回または 1 回
    (x)     グループ化。"()" は空文字列
    \\c     特殊文字 c をただの文字として使う（\\. \\* \\( \\\\ など）
    未対応の特殊文字 ^ $ [ ] { } や、\\d のようなエスケープ、a** のような量指定子の連続は
    RegexSyntaxError にする（黙って違う意味で解釈しないため）。

制約: 演習5 では re モジュールを使わないでください（テストでは答え合わせに使っています）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union  # noqa: F401  Callable は演習5b で使えます

# ---------------------------------------------------------------------------
# 構文木（AST）と構文解析器 — 実装済み（構文解析は 3.4 章で詳しく扱います）
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
    """正規表現の文字列を構文木にする（実装済み）。

    再帰下降構文解析（recursive descent parsing）で、次の文法を優先順位の低い順に解析する:
        alt    := concat ("|" concat)*          選択（優先順位が最も低い）
        concat := repeat*                       連結（0 個なら空文字列 Empty）
        repeat := atom ("*" | "+" | "?")?       繰り返し（量指定子は 1 つまで）
        atom   := 文字 | "." | "(" alt ")" | "\\" 特殊文字

    >>> parse("ab|c*")
    Alt(options=(Concat(parts=(Char(c='a'), Char(c='b'))), Star(inner=Char(c='c'))))
    """
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
# NFA の表現 — 実装済み
# ---------------------------------------------------------------------------


@dataclass
class State:
    """NFA の状態 1 つ。Program.states の添字が状態番号になる。

    kind の種類:
        "char"  : 文字 char を 1 つ読んで out へ進む
        "any"   : 任意の 1 文字を読んで out へ進む
        "split" : 文字を読まずに out と out2 の両方へ進む（ε 遷移による分岐）
        "jump"  : 文字を読まずに out へ進む（ε 遷移。使わなくても実装できる）
        "match" : ここに到達したらマッチ成功（受理状態）
    """

    kind: str
    char: str = ""
    out: int = -1
    out2: int = -1


@dataclass
class Program:
    states: list  # list[State]
    start: int  # 開始状態の番号


# ---------------------------------------------------------------------------
# 演習5a（★★★）: Thompson の構成法と、状態集合のシミュレーション
# ---------------------------------------------------------------------------

def compile_nfa(node: Node) -> Program:
    """構文木を Thompson の構成法で NFA（Program）に変換する。

    - 状態数はパターンの長さに比例すること（テストは 2 × len(pattern) + 2 以下を確かめます）。
    - "match" 状態がちょうど 1 つあり、パターン全体にマッチし終えたらそこへ到達する。

    ヒント（「続き」を渡して後ろから組み立てる方法）:
      build(node, nxt) を「node にマッチしたら状態 nxt へ進む断片を作り、その入口の番号を返す」関数にする。
      最初に match 状態を作り、start = build(全体, match) とする。
        Char(c)     : new("char", c, out=nxt) を返す
        AnyChar     : new("any", out=nxt) を返す
        Empty       : nxt をそのまま返す（何も作らない）
        Concat      : parts を後ろから順に build し、入口を次の nxt にしていく
        Alt         : 各選択肢を build(opt, nxt) し、split で束ねる
        Star(x)     : s = new("split", out2=nxt) を作り、s.out = build(x, s)（本体の後で s に戻る）。s を返す
        Plus(x)     : Star と同じ split を作るが、入口は本体（最低 1 回は通る）
        Quest(x)    : new("split", out=build(x, nxt), out2=nxt) を返す
    （Russ Cox の記事のように「出口が未接続の断片」をつなぎ合わせる方法でもかまいません）
    """
    raise NotImplementedError("演習5a: compile_nfa を実装してください")


class Regex:
    """Thompson の NFA を「状態の集合」で同時にシミュレーションする、線形時間の正規表現エンジン。

    - Regex(pattern): parse して compile_nfa する。構文エラーは RegexSyntaxError（parse が送出する）。
    - fullmatch(text): text 全体がパターンにマッチすれば True（Python の re.fullmatch 相当）。
    - search(text): text のどこか（空の部分文字列を含む）がマッチすれば True（re.search 相当）。
    - state_count（プロパティ）: NFA の状態数。
    - steps（属性）: 直前の fullmatch / search で、状態を「訪れた」回数。
      ε 閉包を計算するとき、同じ位置では同じ状態を 1 回しか訪れない（重複を除く）ので、
      steps <= state_count × (len(text) + 1) が常に成り立つ。これが線形時間の保証そのもの。
      （テストは (a+)+b のような「病的な」パターンでこの不等式を確かめます）

    >>> r = Regex("(a|b)*abb")
    >>> r.fullmatch("babaabb"), r.fullmatch("abab"), r.search("xxabbxx")
    (True, False, True)

    ヒント:
    - add(リスト, s): 状態 s を加える。s が split / jump なら、その先を（再帰ではなくスタックで）たどる。
      char / any / match の状態だけをリストに入れる。「この位置で訪問済み」の印を状態ごとに付けて
      重複を防ぐ（世代番号 generation を 1 文字ごとに増やし、mark[状態] == generation で判定すると速い）。
    - 1 文字 ch を読む: 今のリストの各状態について、ch を読めるなら add(次のリスト, その状態の out)。
    - search は「各位置で開始状態も新たに add する」だけで作れる（先頭に .* を付けたのと同じ効果）。
    """

    def __init__(self, pattern: str) -> None:
        raise NotImplementedError("演習5a: Regex.__init__ を実装してください")

    @property
    def state_count(self) -> int:
        raise NotImplementedError("演習5a: Regex.state_count を実装してください")

    def fullmatch(self, text: str) -> bool:
        raise NotImplementedError("演習5a: Regex.fullmatch を実装してください")

    def search(self, text: str) -> bool:
        raise NotImplementedError("演習5a: Regex.search を実装してください")


# ---------------------------------------------------------------------------
# 演習5b（★★☆）: 素朴なバックトラッキング型マッチャ（比較のため）
# ---------------------------------------------------------------------------


class StepLimitExceeded(Exception):
    """バックトラッキングの試行回数が上限を超えた（実装済み）。"""


def backtrack_fullmatch(pattern: str, text: str, max_steps: int | None = None) -> tuple[bool, int]:
    """構文木を再帰的にたどり、失敗したら別の選択肢を試す（バックトラックする）素朴なマッチャ。

    Perl・PCRE・Java・Python の re などの多くのエンジンが採用している方式を、最小限の形で再現する。
    - 戻り値は (text 全体がマッチしたか, ステップ数)。
    - ステップ数 = 「構文木のあるノードを、テキストのある位置で照合しようとした」回数（照合関数の呼び出し回数）。
    - max_steps が指定されていて、ステップ数がそれを超えたら StepLimitExceeded を送出する。
      （実運用のエンジンにある「バックトラックの上限」や「照合のタイムアウト」に相当する安全装置）
    - メモ化などの高速化はしないこと（指数時間になる様子を観察するのが目的）。
    - 空文字列にマッチしうる繰り返し（"()*" や "(a*)*"）で無限ループしないこと。

    >>> backtrack_fullmatch("(a|b)*abb", "aabb")[0]
    True

    ヒント（継続渡し: continuation-passing）:
      m(node, i, k) を「text[i:] の先頭で node にマッチさせ、マッチし終えた位置 j について
      k(j) が True になる選び方があれば True」とする。全体は m(root, 0, lambda j: j == len(text))。
        Char(c)   : i < n かつ text[i] == c かつ k(i + 1)
        Alt       : いずれかの選択肢 opt で m(opt, i, k)
        Concat    : 先頭の部分にマッチさせ、その続き（残りの部分 → k）を継続として渡す
        Star(x)   : m(x, i, lambda j: j != i and m(Star(x), j, k)) or k(i)
                    （まず「もう 1 回」を試し、だめなら「ここでやめる」。j != i で空回りを防ぐ）
        Plus(x)   : m(x, i, lambda j: m(Star(x), j, k))
        Quest(x)  : m(x, i, k) or k(i)
    """
    raise NotImplementedError("演習5b: backtrack_fullmatch を実装してください")
