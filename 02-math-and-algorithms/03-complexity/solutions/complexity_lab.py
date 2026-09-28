"""2.3 計算量とアルゴリズム解析 — 解答例

演習の仕様は exercises/complexity_lab.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import math
import time
from collections import Counter
from typing import Any, Callable, Hashable, Iterable, Sequence

# ---------------------------------------------------------------------------
# 演習1: うっかり二乗を直す
# ---------------------------------------------------------------------------


def has_duplicates(items: Sequence[Hashable]) -> bool:
    seen = set()
    for x in items:
        if x in seen:          # set の in は平均 O(1)（list なら O(n)）
            return True
        seen.add(x)
    return False


def dedupe_preserving_order(items: Iterable[Hashable]) -> list:
    seen = set()
    out = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def two_sum(nums: Sequence[int], target: int) -> tuple[int, int] | None:
    first_index: dict[int, int] = {}   # 値 → その値が最初に現れた添字
    for j, x in enumerate(nums):
        i = first_index.get(target - x)
        if i is not None:
            return i, j                    # j を左から順に見るので、j が最小の組が最初に見つかる
        first_index.setdefault(x, j)       # 上書きしない = 同じ値なら最小の i を覚えておく
    return None


def count_pairs_with_sum(nums: Sequence[int], k: int) -> int:
    counts = Counter(nums)
    total = 0
    for v, c in counts.items():
        w = k - v
        if v < w:
            total += c * counts.get(w, 0)   # 異なる値の組: 個数の積（v < w で二重計上を防ぐ）
        elif v == w:
            total += c * (c - 1) // 2       # 同じ値どうし: C(c, 2)
    return total


# ---------------------------------------------------------------------------
# 演習2: 二分探索の変種
# ---------------------------------------------------------------------------


def _check_range(a: Sequence, lo: int, hi: int | None) -> int:
    if hi is None:
        hi = len(a)
    if not 0 <= lo <= hi <= len(a):
        raise ValueError(f"0 <= lo <= hi <= len(a) を満たしません: lo={lo}, hi={hi}, len={len(a)}")
    return hi


def lower_bound(a: Sequence, x: Any, lo: int = 0, hi: int | None = None) -> int:
    hi = _check_range(a, lo, hi)
    # 不変条件: a[:lo] の要素はすべて x 未満、a[hi:] の要素はすべて x 以上（元の範囲の中で）
    while lo < hi:
        mid = (lo + hi) // 2   # Python の int はあふれないが、C や Java では lo + (hi - lo) // 2 と書く
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo


def upper_bound(a: Sequence, x: Any, lo: int = 0, hi: int | None = None) -> int:
    hi = _check_range(a, lo, hi)
    # 不変条件: a[:lo] の要素はすべて x 以下、a[hi:] の要素はすべて x より大きい
    while lo < hi:
        mid = (lo + hi) // 2
        if x < a[mid]:         # 「<」だけを使う（a[mid] <= x は not (x < a[mid])）
            hi = mid
        else:
            lo = mid + 1
    return lo


def first_true(lo: int, hi: int, pred: Callable[[int], bool]) -> int:
    if lo > hi:
        raise ValueError(f"lo <= hi が必要です: lo={lo}, hi={hi}")
    # 不変条件: [元の lo, lo) の pred はすべて偽、[hi, 元の hi) の pred はすべて真
    while lo < hi:
        mid = (lo + hi) // 2
        if pred(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo


# ---------------------------------------------------------------------------
# 演習3: 動的配列とならし解析
# ---------------------------------------------------------------------------


class DynamicArray:
    def __init__(self, initial_capacity: int = 1) -> None:
        if initial_capacity < 1:
            raise ValueError(f"initial_capacity は 1 以上: {initial_capacity}")
        self._min_capacity = initial_capacity
        self._data: list = [None] * initial_capacity   # 固定長の「生のメモリ」の代わり
        self._size = 0
        self._copies = 0

    def __len__(self) -> int:
        return self._size

    @property
    def capacity(self) -> int:
        return len(self._data)

    @property
    def copies(self) -> int:
        return self._copies

    def _resize(self, new_capacity: int) -> None:
        new_data: list = [None] * new_capacity
        for i in range(self._size):     # 要素を 1 つずつ新しい領域へコピーする: O(size)
            new_data[i] = self._data[i]
        self._copies += self._size
        self._data = new_data

    def append(self, value: Any) -> None:
        if self._size == self.capacity:
            self._resize(2 * self.capacity)   # 倍々に広げる。定数倍なら何倍でもならし O(1)
        self._data[self._size] = value
        self._size += 1

    def pop(self) -> Any:
        if self._size == 0:
            raise IndexError("pop from empty DynamicArray")
        self._size -= 1
        value = self._data[self._size]
        self._data[self._size] = None       # 参照を消して GC できるようにする
        # 1/4 まで減ったら半分に縮める。1/2 で縮めると、境界で push/pop を繰り返したときに
        # 拡張と縮小が交互に起きて、毎回 O(n) のコピーが発生する（振動）
        if self.capacity > self._min_capacity and self._size <= self.capacity // 4:
            self._resize(max(self.capacity // 2, self._min_capacity))
        return value

    def _normalize(self, index: int) -> int:
        if index < 0:
            index += self._size
        if not 0 <= index < self._size:
            raise IndexError("DynamicArray index out of range")
        return index

    def __getitem__(self, index: int) -> Any:
        return self._data[self._normalize(index)]

    def __setitem__(self, index: int, value: Any) -> None:
        self._data[self._normalize(index)] = value


# ---------------------------------------------------------------------------
# 演習4: 実測から計算量を推定する
# ---------------------------------------------------------------------------

ORDER_MODELS: list[tuple[str, Callable[[float], float]]] = [
    ("O(1)", lambda n: 1.0),
    ("O(log n)", lambda n: math.log(n)),
    ("O(n)", lambda n: n),
    ("O(n log n)", lambda n: n * math.log(n)),
    ("O(n^2)", lambda n: n**2),
    ("O(n^3)", lambda n: n**3),
]


def _check_samples(sizes: Sequence[float], times: Sequence[float]) -> None:
    if len(sizes) != len(times):
        raise ValueError("sizes と times の長さが違います")
    if len(sizes) < 2:
        raise ValueError("2 点以上のデータが必要です")
    if any(n < 2 for n in sizes) or any(t <= 0 for t in times):
        raise ValueError("sizes は 2 以上、times は正の数にしてください")
    if len(set(sizes)) < 2:
        raise ValueError("sizes には異なる値が 2 つ以上必要です")


def fit_loglog_slope(sizes: Sequence[float], times: Sequence[float]) -> float:
    _check_samples(sizes, times)
    # t = c·n^k なら log t = log c + k·log n。(log n, log t) に直線を当てはめた傾きが k
    xs = [math.log(n) for n in sizes]
    ys = [math.log(t) for t in times]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    return sxy / sxx


def estimate_order(sizes: Sequence[float], times: Sequence[float]) -> str:
    _check_samples(sizes, times)
    ys = [math.log(t) for t in times]
    best_label, best_rss = "", math.inf
    for label, g in ORDER_MODELS:
        # モデル t ≈ c·g(n) を対数でとると log t ≈ log c + log g(n)。
        # 最小二乗の log c は残差 log t - log g(n) の平均で、その残差平方和でモデルを比べる
        resid = [y - math.log(g(n)) for y, n in zip(ys, sizes)]
        m = sum(resid) / len(resid)
        rss = sum((r - m) ** 2 for r in resid)
        if rss < best_rss - 1e-12:   # 同程度なら先（単純なモデル）を優先する
            best_label, best_rss = label, rss
    return best_label


def measure_times(func: Callable[[Any], Any], make_input: Callable[[int], Any],
                  sizes: Sequence[int], repeat: int = 3,
                  timer: Callable[[], float] = time.perf_counter) -> list[float]:
    if repeat < 1:
        raise ValueError(f"repeat は 1 以上: {repeat}")
    results = []
    for n in sizes:
        data = make_input(n)             # 入力の生成は計測に含めない
        best = math.inf
        for _ in range(repeat):
            start = timer()
            func(data)
            best = min(best, timer() - start)   # 他の処理の割り込みを除くため最小値をとる
        results.append(best)
    return results


# ---------------------------------------------------------------------------
# 演習5: 分割統治の計算量をマスター定理で確かめる
# ---------------------------------------------------------------------------


def master_theorem(a: float, b: float, d: float) -> tuple[int, float, int]:
    if a < 1 or b <= 1 or d < 0:
        raise ValueError(f"a >= 1, b > 1, d >= 0 が必要です: a={a}, b={b}, d={d}")
    # 葉の方の仕事量 n^(log_b a) と、根の仕事量 n^d のどちらが勝つか。
    # log_b a と d を直接比べると浮動小数点の誤差が出やすいので、a と b^d を比べる
    bd = b**d
    if math.isclose(a, bd, rel_tol=1e-9):
        return 2, float(d), 1                 # 各段の仕事量が等しい: n^d × 段数 log n
    if a > bd:
        return 1, math.log(a) / math.log(b), 0  # 葉が支配的
    return 3, float(d), 0                     # 根が支配的


def _check_poly_pair(p: Sequence[int], q: Sequence[int]) -> int:
    n = len(p)
    if n != len(q) or n < 1 or n & (n - 1):
        raise ValueError(f"p と q は同じ長さで、長さは 2 のべき乗にしてください: {len(p)}, {len(q)}")
    return n


def _add(u: Sequence[int], v: Sequence[int]) -> list[int]:
    return [x + y for x, y in zip(u, v)]


def karatsuba_poly(p: Sequence[int], q: Sequence[int]) -> tuple[list[int], int]:
    n = _check_poly_pair(p, q)
    if n == 1:
        return [p[0] * q[0]], 1
    h = n // 2
    p0, p1 = p[:h], p[h:]   # p(x) = p0(x) + x^h · p1(x)
    q0, q1 = q[:h], q[h:]
    z0, m0 = karatsuba_poly(p0, q0)
    z2, m2 = karatsuba_poly(p1, q1)
    # (p0 + p1)(q0 + q1) = p0q0 + (p0q1 + p1q0) + p1q1 なので、
    # 中央の項は 1 回の掛け算と引き算で求まる（4 回ではなく 3 回で済む）
    zm, m1 = karatsuba_poly(_add(p0, p1), _add(q0, q1))
    z1 = [m - a - b for m, a, b in zip(zm, z0, z2)]
    result = [0] * (2 * n - 1)
    for i, c in enumerate(z0):
        result[i] += c
    for i, c in enumerate(z1):
        result[i + h] += c
    for i, c in enumerate(z2):
        result[i + 2 * h] += c
    return result, m0 + m1 + m2


def naive_dc_poly(p: Sequence[int], q: Sequence[int]) -> tuple[list[int], int]:
    n = _check_poly_pair(p, q)
    if n == 1:
        return [p[0] * q[0]], 1
    h = n // 2
    p0, p1, q0, q1 = p[:h], p[h:], q[:h], q[h:]
    parts = [
        (naive_dc_poly(p0, q0), 0),
        (naive_dc_poly(p0, q1), h),
        (naive_dc_poly(p1, q0), h),
        (naive_dc_poly(p1, q1), 2 * h),
    ]
    result = [0] * (2 * n - 1)
    mults = 0
    for (coeffs, m), shift in parts:
        mults += m
        for i, c in enumerate(coeffs):
            result[i + shift] += c
    return result, mults
