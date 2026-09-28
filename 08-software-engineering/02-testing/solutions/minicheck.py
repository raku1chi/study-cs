"""8.2 テスト戦略 — 解答例: ミニ・プロパティベーステスト（minicheck）

仕様は exercises/minicheck.py の docstring を参照してください。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, Iterator, Optional, Sequence, TypeVar

T = TypeVar("T")

BOUNDARY_PROBABILITY = 0.1


class Gen(Generic[T]):
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
    ok: bool
    runs: int
    counterexample: Optional[tuple]
    original: Optional[tuple]
    shrinks: int
    error: Optional[str]


# ---------------------------------------------------------------------------
# 演習1-1: 整数
# ---------------------------------------------------------------------------

def integers(lo: int, hi: int) -> Gen[int]:
    if lo > hi:
        raise ValueError(f"lo は hi 以下にしてください: lo={lo}, hi={hi}")
    origin = 0 if lo <= 0 <= hi else (lo if lo > 0 else hi)
    boundaries = sorted({lo, hi, origin})

    def generate(rng: random.Random) -> int:
        # バグは境界に集まるので、一定の割合で境界値を選ぶ
        if rng.random() < BOUNDARY_PROBABILITY:
            return rng.choice(boundaries)
        return rng.randint(lo, hi)

    def shrink(v: int) -> Iterator[int]:
        if v == origin:
            return
        d = abs(v - origin)
        sign = 1 if v > origin else -1
        yield origin
        k = 1
        # 原点から v へ半分ずつ近づく候補。貪欲に採用すると二分探索になる
        while d >> k:
            yield v - sign * (d >> k)
            k += 1

    def contains(v: object) -> bool:
        return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi

    return Gen(generate, shrink, contains, name=f"integers({lo}, {hi})")


# ---------------------------------------------------------------------------
# 演習1-2: リスト・文字列・タプル・選択
# ---------------------------------------------------------------------------

def _check_sizes(min_size: int, max_size: int) -> None:
    if not 0 <= min_size <= max_size:
        raise ValueError(f"0 <= min_size <= max_size にしてください: {min_size}, {max_size}")


def _removal_candidates(xs: Sequence, min_size: int) -> Iterator[Sequence]:
    """連続する k 個を取り除いた候補。大きな塊から試すと、少ない試行で大きく縮む。"""
    n = len(xs)
    removable = n - min_size
    sizes: list[int] = []
    k = removable
    while k > 0:
        if k not in sizes:
            sizes.append(k)
        k //= 2
    for k in sizes:
        for i in range(n - k + 1):
            yield xs[:i] + xs[i + k:]


def lists(elements: Gen[T], min_size: int = 0, max_size: int = 10) -> Gen[list]:
    _check_sizes(min_size, max_size)

    def generate(rng: random.Random) -> list:
        return [elements.generate(rng) for _ in range(rng.randint(min_size, max_size))]

    def shrink(xs: list) -> Iterator[list]:
        yield from _removal_candidates(xs, min_size)
        for i, x in enumerate(xs):
            for c in elements.shrink(x):
                yield xs[:i] + [c] + xs[i + 1:]

    def contains(v: object) -> bool:
        return (
            isinstance(v, list)
            and min_size <= len(v) <= max_size
            and all(elements.contains(x) for x in v)
        )

    return Gen(generate, shrink, contains, name=f"lists({elements!r})")


def text(alphabet: str, min_size: int = 0, max_size: int = 10) -> Gen[str]:
    if not alphabet:
        raise ValueError("alphabet が空です")
    _check_sizes(min_size, max_size)

    def generate(rng: random.Random) -> str:
        return "".join(rng.choice(alphabet) for _ in range(rng.randint(min_size, max_size)))

    def shrink(s: str) -> Iterator[str]:
        yield from _removal_candidates(s, min_size)
        for i, ch in enumerate(s):
            # alphabet の先頭に近い文字ほど「単純」
            for simpler in alphabet[: alphabet.index(ch)]:
                yield s[:i] + simpler + s[i + 1:]

    def contains(v: object) -> bool:
        return isinstance(v, str) and min_size <= len(v) <= max_size and all(c in alphabet for c in v)

    return Gen(generate, shrink, contains, name=f"text({alphabet!r})")


def tuples(*gens: Gen) -> Gen[tuple]:
    def generate(rng: random.Random) -> tuple:
        return tuple(g.generate(rng) for g in gens)

    def shrink(t: tuple) -> Iterator[tuple]:
        for i, g in enumerate(gens):
            for c in g.shrink(t[i]):
                yield t[:i] + (c,) + t[i + 1:]

    def contains(v: object) -> bool:
        return isinstance(v, tuple) and len(v) == len(gens) and all(g.contains(x) for g, x in zip(gens, v))

    return Gen(generate, shrink, contains, name=f"tuples{gens!r}")


def one_of(*gens: Gen) -> Gen:
    if not gens:
        raise ValueError("生成器を 1 つ以上指定してください")

    def generate(rng: random.Random) -> Any:
        return rng.choice(gens).generate(rng)

    def shrink(v: Any) -> Iterator[Any]:
        # 値から生成元を逆算する。最初に「生成しうる」と答えた生成器の縮小に任せる
        for g in gens:
            if g.contains(v):
                yield from g.shrink(v)
                return

    def contains(v: object) -> bool:
        return any(g.contains(v) for g in gens)

    return Gen(generate, shrink, contains, name=f"one_of{gens!r}")


# ---------------------------------------------------------------------------
# 演習1-3: for_all
# ---------------------------------------------------------------------------

def _failure(prop: Callable[..., Any], args: tuple) -> Optional[str]:
    """性質が破れたら失敗内容を、成り立ったら None を返す。"""
    try:
        outcome = prop(*args)
    except Exception as exc:  # 性質の中の例外はすべて「失敗」として扱う
        return f"{type(exc).__name__}: {exc}"
    if outcome is False:
        return "性質が False を返しました"
    return None


def for_all(
    prop: Callable[..., Any],
    *gens: Gen,
    runs: int = 100,
    seed: int = 0,
    max_shrinks: int = 1000,
) -> CheckResult:
    rng = random.Random(seed)
    for run in range(1, runs + 1):
        args = tuple(g.generate(rng) for g in gens)
        error = _failure(prop, args)
        if error is not None:
            shrunk, shrunk_error, steps = _shrink(prop, gens, args, error, max_shrinks)
            return CheckResult(False, run, shrunk, args, steps, shrunk_error)
    return CheckResult(True, runs, None, None, 0, None)


def _shrink(
    prop: Callable[..., Any], gens: Sequence[Gen], args: tuple, error: str, max_shrinks: int
) -> tuple[tuple, str, int]:
    current, current_error, steps = args, error, 0
    while steps < max_shrinks:
        improved = False
        for pos, gen in enumerate(gens):
            for candidate in gen.shrink(current[pos]):
                trial = current[:pos] + (candidate,) + current[pos + 1:]
                trial_error = _failure(prop, trial)
                if trial_error is not None:
                    # 失敗し続ける、より単純な値が見つかった → 採用して最初からやり直す
                    current, current_error, steps = trial, trial_error, steps + 1
                    improved = True
                    break
            if improved:
                break
        if not improved:
            break  # どの候補でも失敗しない → 局所的な最小
    return current, current_error, steps


def check(prop: Callable[..., Any], *gens: Gen, **kwargs: Any) -> None:
    result = for_all(prop, *gens, **kwargs)
    if not result.ok:
        raise AssertionError(
            f"性質が成り立たない反例が見つかりました（{result.runs} 回目、{result.shrinks} 回縮小）\n"
            f"  反例: {result.counterexample!r}\n"
            f"  内容: {result.error}\n"
            f"  縮小前: {result.original!r}"
        )
