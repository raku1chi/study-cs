"""8.2 テスト戦略 — 演習1: ミニ・プロパティベーステスト（minicheck）

Hypothesis や QuickCheck のような「プロパティベーステスト」の核となる仕組みを、
標準ライブラリだけで作ります。

  - 生成器（Gen）: ランダムな入力値を作り、失敗した値を「より単純な値」に縮める方法を知っている
  - for_all: 性質（property）を多数のランダムな入力で試し、反例が見つかったら最小化（shrink）して返す

完成すると、次のように使えます。

    >>> result = for_all(lambda xs: sorted(xs) == xs, lists(integers(0, 100)), seed=1)
    >>> result.ok, result.counterexample
    (False, ([1, 0],))

「並んでいない最小のリスト」が [1, 0] に縮められて報告されるのがポイントです。
ランダムに見つかった反例（例えば長さ 9 の雑多なリスト）より、はるかに原因を考えやすくなります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.2

進め方（演習1 はこの順に 3 段階あります）:
    1-1 integers の生成と縮小          （★☆☆）
    1-2 lists / text / tuples / one_of  （★★☆）
    1-3 for_all（反例の探索と縮小）      （★★★）

制約: random.Random のインスタンス（引数 rng）だけを使って値を作ること。
      モジュールの random.randint などのグローバルな乱数を使うと、seed による再現性が失われます。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, Iterator, Optional, TypeVar

T = TypeVar("T")


class Gen(Generic[T]):
    """値の生成器。次の 3 つの関数の組です（このクラスは完成しています）。

    - generate(rng): 乱数生成器 rng を使って値を 1 つ作る
    - shrink(value): value より「単純な」候補を、試すべき順に列挙する（単純な候補ほど先）
    - contains(value): value がこの生成器の生成しうる値かどうか（one_of の縮小で使う）
    """

    def __init__(
        self,
        generate: Callable[[random.Random], T],
        shrink: Callable[[T], Iterable[T]],
        contains: Callable[[object], bool],
        name: str = "Gen",
    ):
        self._generate = generate
        self._shrink = shrink
        self._contains = contains
        self.name = name

    def generate(self, rng: random.Random) -> T:
        return self._generate(rng)

    def shrink(self, value: T) -> Iterator[T]:
        return iter(self._shrink(value))

    def contains(self, value: object) -> bool:
        return self._contains(value)

    def __repr__(self) -> str:
        return self.name


@dataclass(frozen=True)
class CheckResult:
    """for_all の結果。"""

    ok: bool  # すべての試行で性質が成り立ったか
    runs: int  # 実行した試行の数（失敗したら、失敗した試行を含めた数）
    counterexample: Optional[tuple]  # 縮小後の反例（引数のタプル）。ok なら None
    original: Optional[tuple]  # 最初に見つかった、縮小前の反例。ok なら None
    shrinks: int  # 縮小で採用したステップの数
    error: Optional[str]  # 縮小後の反例での失敗内容。例外なら "型名: メッセージ"


# ---------------------------------------------------------------------------
# 演習1-1（★☆☆）: 整数
# ---------------------------------------------------------------------------

def integers(lo: int, hi: int) -> Gen[int]:
    """lo 以上 hi 以下の整数の生成器を返す。lo > hi なら ValueError。

    generate:
        - 値のおよそ 1 割は「境界値」から選ぶ: lo、hi、（範囲に含まれるなら）0。
          バグは境界に集まるので、実用的なライブラリはこうした値を優先的に試します。
        - 残りは lo〜hi から一様に選ぶ（rng.randint）。
    contains(v):
        - v が int（bool は除く）で、lo <= v <= hi なら True。
    shrink(v):
        「原点」o に近づく候補を返す。o は範囲に 0 が含まれれば 0、lo > 0 なら lo、hi < 0 なら hi。
        - v == o なら候補はない。
        - それ以外は、d = |v - o|、s = v - o の符号（+1 か -1）として、
          まず o を返し、続いて k = 1, 2, 3, … について v - s * (d >> k) を、d >> k が 0 になるまで返す。
          （o から v へ半分ずつ近づく列。貪欲に採用していくと二分探索になる）

    >>> list(integers(-100, 100).shrink(10))
    [0, 5, 8, 9]
    >>> list(integers(5, 100).shrink(37))
    [5, 21, 29, 33, 35, 36]
    """
    raise NotImplementedError("演習1-1: integers を実装してください")


# ---------------------------------------------------------------------------
# 演習1-2（★★☆）: リスト・文字列・タプル・選択
# ---------------------------------------------------------------------------

def lists(elements: Gen[T], min_size: int = 0, max_size: int = 10) -> Gen[list]:
    """要素を elements で作るリストの生成器。0 <= min_size <= max_size でなければ ValueError。

    generate: 長さを rng.randint(min_size, max_size) で決め、要素を elements.generate(rng) で作る。
    contains(v): v が list で、長さが範囲内で、すべての要素を elements が contains する。
    shrink(xs): n = len(xs) として、次の順に候補を返す。
        1. 要素の削除: r = n - min_size（削除してよい最大数）とし、k = r, r // 2, r // 4, …, 1
           （0 は除き、重複する k は 1 回だけ）の各 k について、i = 0, 1, …, n - k の順に
           xs[:i] + xs[i + k:]（i 番目から連続する k 個を取り除いたもの）を返す。
        2. 要素の縮小: i = 0, 1, …, n - 1 の順に、elements.shrink(xs[i]) の各候補 c について
           xs[:i] + [c] + xs[i + 1:] を返す。

    >>> [c for c in lists(integers(0, 10)).shrink([3, 1])]
    [[], [1], [3], [0, 1], [2, 1], [3, 0]]
    """
    raise NotImplementedError("演習1-2: lists を実装してください")


def text(alphabet: str, min_size: int = 0, max_size: int = 10) -> Gen[str]:
    """alphabet の文字だけからなる文字列の生成器。alphabet が空、または長さの範囲が不正なら ValueError。

    generate: 長さを rng.randint(min_size, max_size) で決め、各文字を rng.choice(alphabet) で選ぶ。
    contains(v): v が str で、長さが範囲内で、すべての文字が alphabet に含まれる。
    shrink(s): lists と同じ規則で、文字の削除 → 文字の縮小 の順に候補を返す。
        文字の縮小: alphabet の中で位置 j にある文字は、alphabet[0], alphabet[1], …, alphabet[j - 1]
        の順に置き換えた候補になる（alphabet の先頭に近い文字ほど「単純」とみなす）。

    >>> list(text("abc").shrink("ba"))
    ['', 'a', 'b', 'aa']
    """
    raise NotImplementedError("演習1-2: text を実装してください")


def tuples(*gens: Gen) -> Gen[tuple]:
    """各位置を gens の対応する生成器で作るタプルの生成器。

    contains(v): v が tuple で、長さが len(gens) に等しく、各要素を対応する生成器が contains する。
    shrink(t): 位置 i = 0, 1, … の順に、gens[i].shrink(t[i]) の各候補で i 番目だけを置き換えたタプル。

    >>> list(tuples(integers(0, 10), integers(0, 10)).shrink((3, 0)))
    [(0, 0), (2, 0)]
    """
    raise NotImplementedError("演習1-2: tuples を実装してください")


def one_of(*gens: Gen) -> Gen:
    """gens のどれか 1 つ（一様に選ぶ）で値を作る生成器。gens が空なら ValueError。

    contains(v): どれかの生成器が contains すれば True。
    shrink(v): v を contains する **最初の** 生成器の shrink(v) の候補を返す（なければ候補なし）。

    メモ: この「値から逆算して縮める」方式は単純ですが、値を見ても生成元が分からない場合
    （map で変換した値など）には使えません。Hypothesis は値ではなく「乱数の選択の列」を
    縮めることでこの問題を解決しています（本文参照）。
    """
    raise NotImplementedError("演習1-2: one_of を実装してください")


# ---------------------------------------------------------------------------
# 演習1-3（★★★）: for_all
# ---------------------------------------------------------------------------

def for_all(
    prop: Callable[..., Any],
    *gens: Gen,
    runs: int = 100,
    seed: int = 0,
    max_shrinks: int = 1000,
) -> CheckResult:
    """性質 prop が、gens で生成したランダムな引数で成り立つかを runs 回試す。

    - rng = random.Random(seed) を 1 つ作り、各試行で args = (g.generate(rng) for g in gens) を作る。
    - prop(*args) が **False を返す** か **例外（Exception のサブクラス）を送出** したら「失敗」。
      それ以外の戻り値（True や None）は成功とみなす（assert を使う性質も書けるように）。
    - 最初の失敗が見つかったら、それ以上の試行はせずに縮小する:
        現在の反例 current から始め、位置 pos = 0, 1, … の順に gens[pos].shrink(current[pos]) の
        候補を試し、失敗し続ける候補が見つかったら **即座に採用して** 先頭（pos = 0）からやり直す。
        どの候補でも失敗しなくなったら（局所的な最小）、または採用したステップ数が
        max_shrinks に達したら終了する（max_shrinks=0 なら縮小せず、候補も試さない）。
    - 結果は CheckResult で返す（error は縮小後の反例での失敗内容。例外なら "型名: メッセージ"、
      False を返したなら任意の説明文）。

    >>> for_all(lambda x: x < 1000, integers(0, 10**6)).counterexample
    (1000,)
    """
    raise NotImplementedError("演習1-3: for_all を実装してください")


def check(prop: Callable[..., Any], *gens: Gen, **kwargs: Any) -> None:
    """for_all を実行し、失敗したら AssertionError を送出する（unittest の中で使う補助関数）。

    メッセージには縮小後の反例と error を含める。kwargs は for_all にそのまま渡す。
    """
    raise NotImplementedError("演習1-3: check を実装してください")
