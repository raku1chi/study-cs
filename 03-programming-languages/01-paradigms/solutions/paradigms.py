"""3.1 プログラミングパラダイムと抽象化 — 解答例

演習の仕様は exercises/paradigms.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import functools
import inspect
from collections import deque
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
# 演習1: 関数の合成・カリー化・メモ化
# ---------------------------------------------------------------------------

def compose(*fns: Callable[..., Any]) -> Callable[..., Any]:
    if not fns:
        return lambda x: x  # 何も合成しなければ恒等関数
    *outer, innermost = fns

    def composed(*args: Any, **kwargs: Any) -> Any:
        # 右端の関数だけは任意の引数を受け取れる。以降は 1 引数関数を右から左へ適用する
        result = innermost(*args, **kwargs)
        for f in reversed(outer):
            result = f(result)
        return result

    return composed


def pipe(value: Any, *fns: Callable[[Any], Any]) -> Any:
    # compose と逆向き（左から右）。データの流れる順に読めるのが利点
    for f in fns:
        value = f(value)
    return value


def _required_positional_count(fn: Callable[..., Any]) -> int:
    params = inspect.signature(fn).parameters.values()
    if any(p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD) for p in params):
        raise TypeError("可変長引数を持つ関数は arity を明示してください")
    return sum(
        1
        for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) and p.default is p.empty
    )


def curry(fn: Callable[..., T], arity: int | None = None) -> Callable[..., Any]:
    n = _required_positional_count(fn) if arity is None else arity
    if n < 0:
        raise ValueError(f"arity は 0 以上: {n}")

    # collected はタプル（不変）。部分適用した関数を何度再利用しても、
    # 互いの引数が混ざらない。リストを共有するとここで壊れる。
    def accumulate(collected: tuple[Any, ...]) -> Callable[..., Any]:
        def curried(*args: Any) -> Any:
            remaining = n - len(collected)
            if not args and remaining > 0:
                raise TypeError("少なくとも 1 つの引数を渡してください")
            if len(args) > remaining:
                raise TypeError(f"引数が多すぎます（残り {remaining} 個に対して {len(args)} 個）")
            new = collected + args
            if len(new) == n:
                return fn(*new)
            return accumulate(new)

        return curried

    return accumulate(())


class CacheInfo(NamedTuple):
    hits: int
    misses: int
    uncacheable: int
    size: int


def memoize(fn: Callable[..., T]) -> Callable[..., T]:
    cache: dict[Any, Any] = {}
    hits = misses = uncacheable = 0

    @functools.wraps(fn)  # __name__ や __doc__ を元の関数から引き継ぐ
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        nonlocal hits, misses, uncacheable
        # キーワード引数は名前順に並べる（f(a=1, b=2) と f(b=2, a=1) を同一視する）
        key = (args, tuple(sorted(kwargs.items())))
        try:
            cached = key in cache  # ここで hash(key) が計算される
        except TypeError:
            # リストや辞書などハッシュできない引数はキャッシュせず、そのまま呼ぶ
            uncacheable += 1
            return fn(*args, **kwargs)
        if cached:
            hits += 1
            return cache[key]
        misses += 1
        result = fn(*args, **kwargs)  # 例外が出たら何もキャッシュされない
        cache[key] = result
        return result

    def cache_info() -> CacheInfo:
        return CacheInfo(hits, misses, uncacheable, len(cache))

    def cache_clear() -> None:
        nonlocal hits, misses, uncacheable
        cache.clear()
        hits = misses = uncacheable = 0

    wrapper.cache_info = cache_info  # type: ignore[attr-defined]
    wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
    return wrapper


# ---------------------------------------------------------------------------
# 演習2: ジェネレータによる遅延ストリーム
# ---------------------------------------------------------------------------

def iterate(f: Callable[[T], T], x: T) -> Iterator[T]:
    while True:  # 無限ストリーム。必要な分だけ取り出される
        yield x
        x = f(x)


def take(n: int, iterable: Iterable[T]) -> Iterator[T]:
    # 引数チェックは「呼び出した時点」で行う。ジェネレータ関数の本体は
    # 最初の next() まで実行されないので、内側の関数に分けている。
    if n < 0:
        raise ValueError(f"n は 0 以上: {n}")

    def gen() -> Iterator[T]:
        if n == 0:
            return
        for i, x in enumerate(iterable, 1):
            yield x
            if i == n:
                return  # n 個目を渡したら、元のイテラブルから次を取り出さずに終わる

    return gen()


def take_while(pred: Callable[[T], bool], iterable: Iterable[T]) -> Iterator[T]:
    for x in iterable:
        if not pred(x):
            return  # 条件を満たさない最初の要素は（判定のために）消費される
        yield x


def chunked(iterable: Iterable[T], size: int) -> Iterator[tuple[T, ...]]:
    if size < 1:
        raise ValueError(f"size は 1 以上: {size}")

    def gen() -> Iterator[tuple[T, ...]]:
        chunk: list[T] = []
        for x in iterable:
            chunk.append(x)
            if len(chunk) == size:
                yield tuple(chunk)
                chunk = []
        if chunk:
            yield tuple(chunk)

    return gen()


def sliding_window(iterable: Iterable[T], size: int) -> Iterator[tuple[T, ...]]:
    if size < 1:
        raise ValueError(f"size は 1 以上: {size}")

    def gen() -> Iterator[tuple[T, ...]]:
        window: deque[T] = deque(maxlen=size)  # 古い要素は自動的に押し出される
        for x in iterable:
            window.append(x)
            if len(window) == size:
                yield tuple(window)

    return gen()


# ---------------------------------------------------------------------------
# 演習3: 永続リスト（構造共有）
# ---------------------------------------------------------------------------

class PList:
    __slots__ = ("_head", "_tail", "_size")

    def __init__(self) -> None:
        object.__setattr__(self, "_head", None)
        object.__setattr__(self, "_tail", None)
        object.__setattr__(self, "_size", 0)

    @classmethod
    def _cons(cls, head: Any, tail: PList) -> PList:
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
        return cls.from_iterable(items)

    @classmethod
    def from_iterable(cls, iterable: Iterable[Any]) -> PList:
        result = cls()
        # 連結リストは先頭にしか効率よく追加できないので、後ろから積む
        for x in reversed(list(iterable)):
            result = cls._cons(x, result)
        return result

    def push(self, x: Any) -> PList:
        return type(self)._cons(x, self)  # self はまるごと共有される（O(1)）

    def peek(self) -> Any:
        if self._size == 0:
            raise IndexError("空のリストです")
        return self._head

    def pop(self) -> PList:
        if self._size == 0:
            raise IndexError("空のリストです")
        return self._tail  # 新しいオブジェクトは作らない。尾部をそのまま返す

    def is_empty(self) -> bool:
        return self._size == 0

    def __len__(self) -> int:
        return self._size  # 各ノードが長さを持っているので O(1)

    def __iter__(self) -> Iterator[Any]:
        node = self
        while node._size:  # 再帰ではなくループで辿る（長いリストでも安全）
            yield node._head
            node = node._tail

    def drop(self, n: int) -> PList:
        if n < 0:
            raise ValueError(f"n は 0 以上: {n}")
        if n > self._size:
            raise IndexError(f"長さ {self._size} のリストから {n} 個は取り除けません")
        node = self
        for _ in range(n):
            node = node._tail
        return node

    def set(self, index: int, value: Any) -> PList:
        if not 0 <= index < self._size:
            raise IndexError(f"添字が範囲外です: {index}")
        # 経路コピー（path copying）: 変更点より前のノードだけを作り直し、後ろは共有する
        prefix: list[Any] = []
        node = self
        for _ in range(index):
            prefix.append(node._head)
            node = node._tail
        result = type(self)._cons(value, node._tail)
        for x in reversed(prefix):
            result = type(self)._cons(x, result)
        return result

    def concat(self, other: PList) -> PList:
        # self のノードはコピーが必要（末尾の「次」を書き換えられないため）。other は共有できる
        result = other
        for x in reversed(list(self)):
            result = type(self)._cons(x, result)
        return result

    def reverse(self) -> PList:
        result = type(self)()
        for x in self:
            result = type(self)._cons(x, result)
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PList):
            return NotImplemented
        if self._size != other._size:
            return False
        a, b = self, other
        while a._size:
            if a is b:
                return True  # 同じ尾部を共有していれば、残りは比べるまでもなく等しい
            if a._head != b._head:
                return False
            a, b = a._tail, b._tail
        return True

    def __hash__(self) -> int:
        return hash(("PList", tuple(self)))

    def __repr__(self) -> str:
        return f"PList({', '.join(repr(x) for x in self)})"


# ---------------------------------------------------------------------------
# 演習4: Result 型（例外を使わないエラー処理）
# ---------------------------------------------------------------------------

class UnwrapError(Exception):
    """Err に対して unwrap() を呼んだときに送出される。"""


def _check_result(value: object) -> None:
    if not isinstance(value, (Ok, Err)):
        raise TypeError(f"and_then に渡す関数は Ok か Err を返してください: {value!r}")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    def map(self, f: Callable[[T], U]) -> Ok[U]:
        return Ok(f(self.value))

    def map_err(self, f: Callable[[Any], Any]) -> Ok[T]:
        return self

    def and_then(self, f: Callable[[T], Result[U, Any]]) -> Result[U, Any]:
        result = f(self.value)
        _check_result(result)
        return result

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: Any) -> T:
        return self.value


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    def map(self, f: Callable[[Any], Any]) -> Err[E]:
        return self  # エラーはそのまま素通りする（これが「短絡」の正体）

    def map_err(self, f: Callable[[E], F]) -> Err[F]:
        return Err(f(self.error))

    def and_then(self, f: Callable[[Any], Any]) -> Err[E]:
        return self

    def unwrap(self) -> Any:
        raise UnwrapError(f"Err に対して unwrap() が呼ばれました: {self.error!r}")

    def unwrap_or(self, default: U) -> U:
        return default


Result = Union[Ok[T], Err[E]]


def sequence(results: Iterable[Result[T, E]]) -> Result[list[T], E]:
    values: list[T] = []
    for r in results:
        if isinstance(r, Err):
            return r  # 最初のエラーで打ち切る。残りは取り出さない
        values.append(r.value)
    return Ok(values)


_ASCII_DIGITS = frozenset("0123456789")


def parse_int(text: str) -> Result[int, str]:
    s = text.strip()
    body = s[1:] if s.startswith(("+", "-")) else s
    # int() は「１２３」（全角）や「1_000」も受け付けてしまうので、自分で検査する
    if not body or not set(body) <= _ASCII_DIGITS:
        return Err(f"整数ではありません: {text!r}")
    return Ok(int(s))


def parse_age(text: str) -> Result[int, str]:
    def check_range(n: int) -> Result[int, str]:
        return Ok(n) if 0 <= n <= 150 else Err(f"年齢は 0〜150 の範囲で入力してください: {n}")

    return parse_int(text).and_then(check_range)


def parse_email(text: str) -> Result[str, str]:
    s = text.strip()
    if any(c.isspace() for c in s) or s.count("@") != 1:
        return Err(f"メールアドレスの形式が不正です: {text!r}")
    local, domain = s.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        return Err(f"メールアドレスの形式が不正です: {text!r}")
    return Ok(f"{local}@{domain.lower()}")


@dataclass(frozen=True)
class Signup:
    name: str
    age: int
    email: str


def _parse_name(text: str) -> Result[str, str]:
    s = text.strip()
    if not s:
        return Err("名前を入力してください")
    if len(s) > 50:
        return Err(f"名前は 50 文字以内で入力してください（{len(s)} 文字）")
    return Ok(s)


def validate_signup(form: Mapping[str, str]) -> Result[Signup, dict[str, str]]:
    parsers: dict[str, Callable[[str], Result[Any, str]]] = {
        "name": _parse_name,
        "age": parse_age,
        "email": parse_email,
    }
    values: dict[str, Any] = {}
    errors: dict[str, str] = {}
    # and_then で繋ぐと最初のエラーで止まってしまう。フォームでは全項目のエラーを
    # まとめて返したいので、各項目を独立に検証してから結果を集める。
    for field, parse in parsers.items():
        if field not in form:
            errors[field] = "必須項目です"
            continue
        result = parse(form[field])
        if isinstance(result, Ok):
            values[field] = result.value
        else:
            errors[field] = result.error
    if errors:
        return Err(errors)
    return Ok(Signup(**values))


# ---------------------------------------------------------------------------
# 演習5: 表現問題（Expression Problem）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Num:
    value: int | float


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class Add:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Mul:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Neg:
    operand: Expr


@dataclass(frozen=True)
class Pow:
    base: Expr
    exponent: int


Expr = Union[Num, Var, Add, Mul, Neg, Pow]


class EvalError(Exception):
    """式を評価できないとき（未定義の変数など）に送出される。"""


def evaluate(expr: Expr, env: Mapping[str, int | float]) -> int | float:
    match expr:
        case Num(value):
            return value
        case Var(name):
            if name not in env:
                raise EvalError(f"未定義の変数です: {name}")
            return env[name]
        case Add(left, right):
            return evaluate(left, env) + evaluate(right, env)
        case Mul(left, right):
            return evaluate(left, env) * evaluate(right, env)
        case Neg(operand):
            return -evaluate(operand, env)
        case Pow(base, exponent):  # 演習5c で追加した分岐
            return evaluate(base, env) ** exponent
        case _:
            raise TypeError(f"未知の式です: {expr!r}")


# 結合の強さ。大きいほど強く結び付く
_PREC_ADD, _PREC_MUL, _PREC_NEG, _PREC_POW, _PREC_ATOM = 1, 2, 3, 4, 5


def _prec(expr: Expr) -> int:
    match expr:
        case Add():
            return _PREC_ADD
        case Mul():
            return _PREC_MUL
        case Neg():
            return _PREC_NEG
        case Num(value) if value < 0:
            return _PREC_NEG  # 負の数のリテラルは「-3」と書かれるので Neg と同じ扱い
        case Pow():
            return _PREC_POW
        case _:
            return _PREC_ATOM


def _num_str(value: int | float) -> str:
    return repr(value)


def _paren(expr: Expr, needed: bool) -> str:
    s = to_str(expr)
    return f"({s})" if needed else s


def to_str(expr: Expr) -> str:
    match expr:
        case Num(value):
            return _num_str(value)
        case Var(name):
            return name
        case Add(left, right):
            # 左結合: 左の子は「より弱い」ときだけ、右の子は「同じか弱い」ときに括弧
            return f"{_paren(left, _prec(left) < _PREC_ADD)} + {_paren(right, _prec(right) <= _PREC_ADD)}"
        case Mul(left, right):
            return f"{_paren(left, _prec(left) < _PREC_MUL)} * {_paren(right, _prec(right) <= _PREC_MUL)}"
        case Neg(operand):
            # 「--x」や「-(-3)」の曖昧さを避けるため、Neg 以下の強さなら括弧
            return "-" + _paren(operand, _prec(operand) <= _PREC_NEG)
        case Pow(base, exponent):
            return f"{_paren(base, _prec(base) <= _PREC_POW)}^{exponent}"
        case _:
            raise TypeError(f"未知の式です: {expr!r}")


def derive(expr: Expr, var: str) -> Expr:
    match expr:
        case Num():
            return Num(0)
        case Var(name):
            return Num(1 if name == var else 0)
        case Add(left, right):
            return Add(derive(left, var), derive(right, var))
        case Mul(left, right):  # 積の微分: (fg)' = f'g + fg'
            return Add(Mul(derive(left, var), right), Mul(left, derive(right, var)))
        case Neg(operand):
            return Neg(derive(operand, var))
        case Pow(base, exponent):  # 演習5c: (u^n)' = n * u^(n-1) * u'
            if exponent == 0:
                return Num(0)
            return Mul(Mul(Num(exponent), Pow(base, exponent - 1)), derive(base, var))
        case _:
            raise TypeError(f"未知の式です: {expr!r}")
