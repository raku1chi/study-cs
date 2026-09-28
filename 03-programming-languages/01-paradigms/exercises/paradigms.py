"""3.1 プログラミングパラダイムと抽象化 — 演習

各関数・メソッドの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.1          # 合格数を表示
    python3 tools/check.py -v 3.1       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます（演習ごとに絞り込めます）:
    python3 -m unittest -v test_paradigms
    python3 -m unittest -v test_paradigms.TestExercise2Streams

演習の一覧:
    演習1（★☆☆）: compose / pipe / curry / memoize — 関数を値として扱う
    演習2（★★☆）: iterate / take / take_while / chunked / sliding_window — 遅延ストリーム
    演習3（★★☆）: PList — 構造共有する永続（不変）リスト
    演習4（★★☆）: Ok / Err / sequence / validate_signup — 例外を使わないエラー処理
    演習5（★★★）: evaluate / to_str / derive と Pow — 表現問題（Expression Problem）

制約（学びのための縛り）:
    - 演習1 では functools.lru_cache / functools.cache / functools.partial を使わないでください
      （functools.wraps は使って構いません）。
    - 演習2 では itertools（islice・takewhile・pairwise など）を使わないでください。
      ジェネレータ（yield）で自分で書くことが目的です。
    - 演習5 は Python 3.10 の match 文で書くことを想定しています（if/isinstance でも動きます）。
"""
from __future__ import annotations

import functools  # noqa: F401  演習1で使えます（functools.wraps）
import inspect  # noqa: F401  演習1で使えます（inspect.signature）
from collections import deque  # noqa: F401  演習2で使えます
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Generic,
    Iterable,
    Iterator,
    Mapping,
    NamedTuple,
    TypeVar,
    Union,
)

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 関数の合成・カリー化・メモ化
# ---------------------------------------------------------------------------

def compose(*fns: Callable[..., Any]) -> Callable[..., Any]:
    """関数を右から左へ合成した関数を返す。compose(f, g, h)(x) == f(g(h(x)))。

    - 右端の関数は任意の引数（位置引数・キーワード引数）を受け取れる。
      それ以外の関数は 1 引数関数として、直前の結果を受け取る。
    - 関数を 1 つも渡さなければ恒等関数（x をそのまま返す 1 引数関数）を返す。

    >>> inc = lambda x: x + 1
    >>> double = lambda x: x * 2
    >>> compose(inc, double)(5)      # inc(double(5))
    11
    >>> compose(str, max)(3, 9, 4)   # 右端の max は複数の引数を受け取れる
    '9'
    >>> compose()(42)
    42
    """
    raise NotImplementedError("演習1: compose を実装してください")


def pipe(value: Any, *fns: Callable[[Any], Any]) -> Any:
    """value に関数を左から右へ順に適用した結果を返す。pipe(x, f, g) == g(f(x))。

    >>> pipe(5, lambda x: x * 2, lambda x: x + 1)
    11
    >>> pipe("hello")
    'hello'
    """
    raise NotImplementedError("演習1: pipe を実装してください")


def curry(fn: Callable[..., T], arity: int | None = None) -> Callable[..., Any]:
    """fn をカリー化した関数を返す。

    - arity（引数の個数）を省略したら、inspect.signature で「デフォルト値を持たない
      位置引数」の数を数えて使う。*args / **kwargs を持つ関数で arity を省略したら TypeError。
    - arity が負なら ValueError。
    - 1 回の呼び出しで 1 個以上の引数を渡せる。合計が arity に達したら fn を呼んで結果を返し、
      まだ足りなければ「残りの引数を待つ関数」を返す。
    - 残りの個数より多くの引数を渡したら TypeError。
      残りが 1 個以上あるのに引数なしで呼んだら TypeError。
    - arity が 0 のときは curry(fn)() で fn() を呼ぶ。
    - 部分適用した関数は何度でも再利用できること（互いの引数が混ざってはいけない）。

    >>> add3 = curry(lambda a, b, c: a + b + c)
    >>> add3(1)(2)(3)
    6
    >>> add3(1, 2)(3)
    6
    >>> inc = add3(1)
    >>> inc(2)(3), inc(10)(20)       # inc を再利用しても結果が混ざらない
    (6, 31)

    ヒント: 「これまでに受け取った引数（タプル）」を閉じ込めたクロージャを返す。
    """
    raise NotImplementedError("演習1: curry を実装してください")


class CacheInfo(NamedTuple):
    """memoize したラッパー関数の cache_info() が返す統計情報（与えられたもの）。"""

    hits: int  # キャッシュから結果を返した回数
    misses: int  # キャッシュになく、元の関数を呼んで結果を保存した回数
    uncacheable: int  # 引数がハッシュできず、キャッシュせずに元の関数を呼んだ回数
    size: int  # キャッシュに保存されている結果の数


def memoize(fn: Callable[..., T]) -> Callable[..., T]:
    """関数の結果を引数ごとにキャッシュするデコレータ。

    - 同じ引数で呼ばれたら、元の関数を呼ばずに保存済みの結果を返す。
      キーは (位置引数のタプル, キーワード引数を名前順に並べたタプル) とする。
      つまり f(a=1, b=2) と f(b=2, a=1) は同じキーだが、f(1) と f(a=1) は別のキー。
    - 引数にリストなどのハッシュできない値が含まれるときは、例外にせず、
      キャッシュを使わずに元の関数を呼ぶ（uncacheable を 1 増やす）。
    - 元の関数が例外を送出したら、何もキャッシュしない（次の呼び出しで再び実行される）。
    - functools.wraps で __name__ や __doc__ を引き継ぐ。
    - 返すラッパー関数には次の 2 つの属性を付ける:
        wrapper.cache_info() -> CacheInfo
        wrapper.cache_clear() -> None   （キャッシュと統計をすべて 0 に戻す）

    >>> @memoize
    ... def fib(n):
    ...     return n if n < 2 else fib(n - 1) + fib(n - 2)
    >>> fib(80)                      # メモ化なしでは終わらない
    23416728348467685
    >>> fib.cache_info().misses      # fib(0)〜fib(80) を 1 回ずつ計算した
    81

    注意: メモ化してよいのは「同じ引数なら必ず同じ結果を返し、副作用のない」純粋関数だけ。
    """
    raise NotImplementedError("演習1: memoize を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ジェネレータによる遅延ストリーム
# ---------------------------------------------------------------------------

def iterate(f: Callable[[T], T], x: T) -> Iterator[T]:
    """x, f(x), f(f(x)), ... を無限に生成するイテレータを返す。

    >>> it = iterate(lambda n: n * 2, 1)
    >>> [next(it) for _ in range(5)]
    [1, 2, 4, 8, 16]
    """
    raise NotImplementedError("演習2: iterate を実装してください")


def take(n: int, iterable: Iterable[T]) -> Iterator[T]:
    """iterable の先頭から最大 n 個の要素を生成するイテレータを返す（遅延評価）。

    - n が負なら、**呼び出した時点で** ValueError を送出する（イテレータを回し始めるまで待たない）。
    - 元の iterable から取り出す要素は、ちょうど n 個（要素が足りなければあるだけ）。
      n 個目を返した後に、確認のために n+1 個目を取り出してはいけない。
    - 無限のイテラブルに対しても動くこと。

    >>> list(take(3, iterate(lambda n: n + 1, 0)))
    [0, 1, 2]
    >>> list(take(5, [1, 2]))
    [1, 2]

    ヒント: 関数の本体に yield があると、その関数は「呼び出しても本体が実行されない」
    ジェネレータ関数になる。引数チェックをすぐに行いたいなら、内側に別のジェネレータ関数を
    定義して、それを呼んだ結果を返すとよい。
    """
    raise NotImplementedError("演習2: take を実装してください")


def take_while(pred: Callable[[T], bool], iterable: Iterable[T]) -> Iterator[T]:
    """pred(x) が真である間だけ要素を生成し、最初に偽になったところで終わる（遅延評価）。

    pred が偽になった要素は（判定のために）取り出されるが、生成はされない。

    >>> list(take_while(lambda n: n < 20, iterate(lambda n: n * 3, 1)))
    [1, 3, 9]
    """
    raise NotImplementedError("演習2: take_while を実装してください")


def chunked(iterable: Iterable[T], size: int) -> Iterator[tuple[T, ...]]:
    """要素を size 個ずつのタプルにまとめて生成する。最後のタプルは size 個未満でもよい。

    - size が 1 未満なら、呼び出した時点で ValueError。
    - 無限のイテラブルに対しても、タプルが 1 つそろうたびに生成すること（遅延評価）。

    >>> list(chunked(range(7), 3))
    [(0, 1, 2), (3, 4, 5), (6,)]
    """
    raise NotImplementedError("演習2: chunked を実装してください")


def sliding_window(iterable: Iterable[T], size: int) -> Iterator[tuple[T, ...]]:
    """連続する size 個の要素のタプルを、1 つずつずらしながら生成する（移動窓）。

    - 要素が size 個未満なら何も生成しない。
    - size が 1 未満なら、呼び出した時点で ValueError。
    - 無限のイテラブルに対しても動くこと（遅延評価）。

    >>> list(sliding_window([1, 2, 3, 4], 2))
    [(1, 2), (2, 3), (3, 4)]

    ヒント: collections.deque(maxlen=size) は、満杯のときに append すると先頭が押し出される。
    """
    raise NotImplementedError("演習2: sliding_window を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 永続リスト（構造共有する不変の連結リスト）
# ---------------------------------------------------------------------------

class PList:
    """永続（persistent）な単方向連結リスト。スタックとしても使える。

    「永続」とは、変更操作が元のリストを書き換えず、新しいリストを返すことを指す。
    古いバージョンはそのまま使い続けられる。新旧のリストは共通部分（尾部）を
    **共有** するので、コピーのコストはかからない（構造共有, structural sharing）。

        a = PList.of(2, 3)        a ──▶ [2] ──▶ [3] ──▶ (空)
        b = a.push(1)             b ──▶ [1] ──┘   （a のノードをそのまま共有）

    内部表現（与えられたもの）:
        各インスタンスは「ノード」であり、_head（先頭の要素）、_tail（残りのリスト = PList）、
        _size（要素数）を持つ。空リストは _size == 0 のインスタンス。
        __init__ は空リストを作り、_cons(head, tail) は先頭に head を持つ新しいノードを作る。
        __setattr__ を禁止しているので、属性の設定には object.__setattr__ を使う（_cons 参照）。

    実装するメソッド: of, from_iterable, push, peek, pop, is_empty, __len__, __iter__,
    drop, set, concat, reverse, __eq__, __hash__, __repr__

    注意: 要素数が 10 万を超えるリストでもテストします。再帰で書くと
    RecursionError になるので、ループで書いてください。
    """

    __slots__ = ("_head", "_tail", "_size")

    def __init__(self) -> None:
        """空のリストを作る（与えられたもの）。"""
        object.__setattr__(self, "_head", None)
        object.__setattr__(self, "_tail", None)
        object.__setattr__(self, "_size", 0)

    @classmethod
    def _cons(cls, head: Any, tail: PList) -> PList:
        """先頭が head、残りが tail のリストを O(1) で作る（与えられたもの）。tail は共有される。"""
        node = object.__new__(cls)
        object.__setattr__(node, "_head", head)
        object.__setattr__(node, "_tail", tail)
        object.__setattr__(node, "_size", tail._size + 1)
        return node

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError(f"PList は不変です（{name} に代入できません）")

    def __delattr__(self, name: str) -> None:
        raise AttributeError(f"PList は不変です（{name} を削除できません）")

    @classmethod
    def of(cls, *items: Any) -> PList:
        """引数を順に並べたリストを作る。PList.of(1, 2, 3) の先頭は 1。"""
        raise NotImplementedError("演習3: PList.of を実装してください")

    @classmethod
    def from_iterable(cls, iterable: Iterable[Any]) -> PList:
        """イテラブルの要素を同じ順に並べたリストを作る。"""
        raise NotImplementedError("演習3: PList.from_iterable を実装してください")

    def push(self, x: Any) -> PList:
        """先頭に x を追加したリストを O(1) で返す（元のリストは変わらない）。"""
        raise NotImplementedError("演習3: PList.push を実装してください")

    def peek(self) -> Any:
        """先頭の要素を返す。空なら IndexError。"""
        raise NotImplementedError("演習3: PList.peek を実装してください")

    def pop(self) -> PList:
        """先頭を取り除いたリストを返す。空なら IndexError。

        新しいオブジェクトを作らず、共有している尾部をそのまま返すこと。
        つまり a.push(x).pop() is a が成り立つ。
        """
        raise NotImplementedError("演習3: PList.pop を実装してください")

    def is_empty(self) -> bool:
        """空リストなら True。"""
        raise NotImplementedError("演習3: PList.is_empty を実装してください")

    def __len__(self) -> int:
        """要素数を O(1) で返す。"""
        raise NotImplementedError("演習3: PList.__len__ を実装してください")

    def __iter__(self) -> Iterator[Any]:
        """先頭から順に要素を生成する。"""
        raise NotImplementedError("演習3: PList.__iter__ を実装してください")

    def drop(self, n: int) -> PList:
        """先頭から n 個を取り除いたリスト（= 共有している尾部そのもの）を返す。

        - n が負なら ValueError、n が長さより大きければ IndexError。
        - 新しいノードを作らないこと: a.push(1).push(2).drop(2) is a
        """
        raise NotImplementedError("演習3: PList.drop を実装してください")

    def set(self, index: int, value: Any) -> PList:
        """index 番目（0 始まり）の要素を value に置き換えたリストを返す。

        - index が範囲外（負を含む）なら IndexError。
        - 経路コピー（path copying）: index 番目までのノードだけを新しく作り、
          それより後ろは元のリストと共有すること。
          つまり xs.set(i, v).drop(i + 1) is xs.drop(i + 1) が成り立つ。
        """
        raise NotImplementedError("演習3: PList.set を実装してください")

    def concat(self, other: PList) -> PList:
        """self の後ろに other をつないだリストを返す。

        other は共有すること: xs.concat(ys).drop(len(xs)) is ys が成り立つ。
        （self のノードは作り直す必要がある。なぜか考えてみよう）
        """
        raise NotImplementedError("演習3: PList.concat を実装してください")

    def reverse(self) -> PList:
        """要素を逆順にしたリストを返す。"""
        raise NotImplementedError("演習3: PList.reverse を実装してください")

    def __eq__(self, other: object) -> bool:
        """要素が同じ順に並んでいれば等しい。PList 以外との比較は NotImplemented を返す。

        - 先頭から 1 要素ずつ比べる途中で、2 つのリストが同じノードを共有していたら
          （is で判定）、残りの要素は比較せずに True を返すこと。共有している尾部は
          比べるまでもなく等しい（構造共有の利点。テストで確認します）。
        """
        raise NotImplementedError("演習3: PList.__eq__ を実装してください")

    def __hash__(self) -> int:
        """等しいリストは同じハッシュ値を返す（辞書のキーや memoize の引数に使えるように）。"""
        raise NotImplementedError("演習3: PList.__hash__ を実装してください")

    def __repr__(self) -> str:
        """PList(1, 2, 3) の形式。空なら PList()。要素は repr() で表示する。"""
        raise NotImplementedError("演習3: PList.__repr__ を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: Result 型 — 例外を使わないエラー処理
# ---------------------------------------------------------------------------

class UnwrapError(Exception):
    """Err に対して unwrap() を呼んだときに送出される（与えられたもの）。"""


@dataclass(frozen=True)
class Ok(Generic[T]):
    """成功を表す値。value に結果を持つ。

    Rust の Result<T, E> を手本にしている。成功（Ok）と失敗（Err）のどちらかを
    「戻り値」として返すことで、エラーの可能性を関数のシグネチャに表す。
    """

    value: T

    def is_ok(self) -> bool:
        """常に True。"""
        raise NotImplementedError("演習4: Ok.is_ok を実装してください")

    def is_err(self) -> bool:
        """常に False。"""
        raise NotImplementedError("演習4: Ok.is_err を実装してください")

    def map(self, f: Callable[[T], U]) -> Ok[U]:
        """Ok(f(value)) を返す。"""
        raise NotImplementedError("演習4: Ok.map を実装してください")

    def map_err(self, f: Callable[[Any], Any]) -> Ok[T]:
        """成功なので何もしない（self を返す）。"""
        raise NotImplementedError("演習4: Ok.map_err を実装してください")

    def and_then(self, f: Callable[[T], Result[U, Any]]) -> Result[U, Any]:
        """f(value) の結果（Ok か Err）をそのまま返す。失敗しうる処理の連結に使う。

        f が Ok / Err 以外を返したら TypeError（map と取り違えたバグを早く見つけるため）。
        """
        raise NotImplementedError("演習4: Ok.and_then を実装してください")

    def unwrap(self) -> T:
        """value を返す。"""
        raise NotImplementedError("演習4: Ok.unwrap を実装してください")

    def unwrap_or(self, default: Any) -> T:
        """value を返す（default は使わない）。"""
        raise NotImplementedError("演習4: Ok.unwrap_or を実装してください")


@dataclass(frozen=True)
class Err(Generic[E]):
    """失敗を表す値。error にエラーの内容を持つ。"""

    error: E

    def is_ok(self) -> bool:
        """常に False。"""
        raise NotImplementedError("演習4: Err.is_ok を実装してください")

    def is_err(self) -> bool:
        """常に True。"""
        raise NotImplementedError("演習4: Err.is_err を実装してください")

    def map(self, f: Callable[[Any], Any]) -> Err[E]:
        """失敗なので f は呼ばない（self を返す）。"""
        raise NotImplementedError("演習4: Err.map を実装してください")

    def map_err(self, f: Callable[[E], F]) -> Err[F]:
        """Err(f(error)) を返す。エラーの型や表現を変換するのに使う。"""
        raise NotImplementedError("演習4: Err.map_err を実装してください")

    def and_then(self, f: Callable[[Any], Any]) -> Err[E]:
        """失敗なので f は呼ばない（self を返す）。"""
        raise NotImplementedError("演習4: Err.and_then を実装してください")

    def unwrap(self) -> Any:
        """UnwrapError を送出する（Rust の panic に相当）。"""
        raise NotImplementedError("演習4: Err.unwrap を実装してください")

    def unwrap_or(self, default: U) -> U:
        """default を返す。"""
        raise NotImplementedError("演習4: Err.unwrap_or を実装してください")


Result = Union[Ok[T], Err[E]]


def sequence(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    """Result の列を「値のリストの Result」にまとめる。

    - すべて Ok なら Ok([value, ...])。空の列なら Ok([])。
    - Err があれば最初の Err をそのまま返す。そこから先の要素は取り出さないこと
      （results がジェネレータなら、残りの計算は実行されない）。

    >>> sequence([Ok(1), Ok(2)])
    Ok(value=[1, 2])
    >>> sequence([Ok(1), Err("x"), Err("y")])
    Err(error='x')
    """
    raise NotImplementedError("演習4: sequence を実装してください")


def parse_int(text: str) -> Result[int, str]:
    """文字列を整数に変換する。例外は送出せず、失敗は Err(メッセージ) で返す。

    - 前後の空白は無視する。先頭に + または - を 1 つ付けてよい。
    - それ以外は ASCII の数字（0〜9）だけからなること。
      「１２３」（全角数字）や「1_000」は、int() は受け付けるがここでは Err にする。

    >>> parse_int(" 42 ")
    Ok(value=42)
    >>> parse_int("-7")
    Ok(value=-7)
    >>> parse_int("abc").is_err()
    True
    """
    raise NotImplementedError("演習4: parse_int を実装してください")


def parse_age(text: str) -> Result[int, str]:
    """年齢を解析する。parse_int に成功し、かつ 0 以上 150 以下なら Ok、それ以外は Err。

    ヒント: parse_int(text).and_then(範囲を検査して Ok か Err を返す関数)
    """
    raise NotImplementedError("演習4: parse_age を実装してください")


def parse_email(text: str) -> Result[str, str]:
    """メールアドレスを（簡略化した規則で）解析し、正規化した文字列を返す。

    規則（実際の RFC 5322 よりずっと単純化している）:
    - 前後の空白は無視する。途中に空白文字があれば Err。
    - "@" がちょうど 1 つあり、その前（ローカル部）が空でない。
    - "@" の後（ドメイン部）に "." を含み、ドメイン部が "." で始まったり終わったりしない。
    - 成功したら、ドメイン部を小文字にした文字列を返す（ローカル部はそのまま）。

    >>> parse_email(" Alice@Example.COM ")
    Ok(value='Alice@example.com')
    >>> parse_email("alice@localhost").is_err()
    True
    """
    raise NotImplementedError("演習4: parse_email を実装してください")


@dataclass(frozen=True)
class Signup:
    """検証済みの会員登録データ（与えられたもの）。このオブジェクトがあれば、中身は検証済み。"""

    name: str
    age: int
    email: str


def validate_signup(form: Mapping[str, str]) -> Result[Signup, dict[str, str]]:
    """会員登録フォーム（文字列の辞書）を検証し、Signup を作る。

    項目:
    - "name": 前後の空白を除いて 1 文字以上 50 文字以下。値は空白を除いたものを使う。
    - "age": parse_age で解析する。
    - "email": parse_email で解析する。

    - すべての項目が正しければ Ok(Signup(...))。
    - 1 つでも誤りがあれば Err({項目名: エラーメッセージ, ...})。
      **誤りのあるすべての項目** を含めること（最初の 1 つで止めない）。
      項目が form に存在しなければ、その項目のエラーとする（メッセージは自由）。
    - 例外は送出しない。

    >>> validate_signup({"name": " Taro ", "age": "30", "email": "taro@example.jp"})
    Ok(value=Signup(name='Taro', age=30, email='taro@example.jp'))
    >>> sorted(validate_signup({"name": "", "age": "x", "email": "a@b.c"}).error)
    ['age', 'name']
    """
    raise NotImplementedError("演習4: validate_signup を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: 表現問題（Expression Problem）
# ---------------------------------------------------------------------------
# 数式の抽象構文木（AST）。各ノードは不変のデータクラス（与えられたもの）。

@dataclass(frozen=True)
class Num:
    """数値リテラル。"""

    value: int | float


@dataclass(frozen=True)
class Var:
    """変数。"""

    name: str


@dataclass(frozen=True)
class Add:
    """left + right"""

    left: Expr
    right: Expr


@dataclass(frozen=True)
class Mul:
    """left * right"""

    left: Expr
    right: Expr


@dataclass(frozen=True)
class Neg:
    """-operand（単項マイナス）"""

    operand: Expr


# ---- 演習5c で「後から追加された」新しいノード型 ----
@dataclass(frozen=True)
class Pow:
    """base ^ exponent（exponent は 0 以上の整数の定数）"""

    base: Expr
    exponent: int


Expr = Union[Num, Var, Add, Mul, Neg, Pow]


class EvalError(Exception):
    """式を評価できないとき（未定義の変数など）に送出される（与えられたもの）。"""


def evaluate(expr: Expr, env: Mapping[str, int | float]) -> int | float:
    """式の値を計算する。変数の値は env から引く。

    - env にない変数を評価したら EvalError。
    - 未知のノードなら TypeError。
    - 演習5a: Num, Var, Add, Mul, Neg に対応する。
    - 演習5c: Pow（べき乗）にも対応する。

    >>> evaluate(Add(Num(1), Mul(Var("x"), Num(3))), {"x": 2})
    7
    """
    raise NotImplementedError("演習5a: evaluate を実装してください")


def to_str(expr: Expr) -> str:
    """式を、必要最小限の括弧を付けた文字列にする。

    演算子の結合の強さ（弱い順）: +  <  *  <  単項 -  <  ^
    - 数値は repr(value) で表す（3 → "3"、2.5 → "2.5"、-3 → "-3"）。
    - 二項演算子は前後に空白を 1 つ入れる: "x + 1"。^ は空白なし: "x^2"。
    - + と * は左結合として扱い、木の形を保つ:
        左の子は、その結合が親より弱いときだけ括弧で囲む。
        右の子は、その結合が親と同じか弱いときに括弧で囲む。
        Add(Add(a, b), c) → "a + b + c"、Add(a, Add(b, c)) → "a + (b + c)"
    - 単項 -: 被演算子が +、*、単項 -、負の数のリテラルなら括弧で囲む。
        Neg(Var("x")) → "-x"、Neg(Add(...)) → "-(x + 1)"、Neg(Neg(x)) → "-(-x)"
        Neg(Pow(x, 2)) → "-x^2"（^ の方が強いので括弧は不要）
    - ^（演習5c）: 底が変数か 0 以上の数値でなければ括弧で囲む。
        Pow(Neg(x), 2) → "(-x)^2"、Pow(Pow(x, 2), 3) → "(x^2)^3"
    - 負の数のリテラルは、単項 - と同じ結合の強さとして扱う:
        Add(x, Num(-3)) → "x + -3"、Pow(Num(-2), 2) → "(-2)^2"

    >>> to_str(Mul(Add(Var("x"), Num(1)), Var("y")))
    '(x + 1) * y'
    """
    raise NotImplementedError("演習5a: to_str を実装してください")


def derive(expr: Expr, var: str) -> Expr:
    """式を変数 var で微分した式を返す（演習5b: 既存の型に「新しい操作」を追加する）。

    規則:
        c' = 0（定数）       x' = 1（var と同じ変数）      y' = 0（それ以外の変数）
        (f + g)' = f' + g'   (f * g)' = f' * g + f * g'    (-f)' = -(f')
        演習5c: (u^n)' = n * u^(n-1) * u'   （n == 0 なら 0）

    結果の式を簡約（0 や 1 を消す）する必要はない。テストは結果を evaluate して値で確かめる。

    >>> e = Mul(Var("x"), Var("x"))          # x * x
    >>> evaluate(derive(e, "x"), {"x": 3})   # 2x → 6
    6
    """
    raise NotImplementedError("演習5b: derive を実装してください")
