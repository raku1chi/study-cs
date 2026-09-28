"""2.6 アルゴリズム設計技法 — 解答例

演習の仕様は exercises/algorithms.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import heapq
import os
import random
import tempfile
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1: ソート
# ---------------------------------------------------------------------------

def merge_sort(items: Iterable[T], key: Callable[[T], Any] | None = None) -> list[T]:
    # キーは要素ごとに 1 回だけ計算しておく（decorate）。比較のたびに key() を呼ぶと遅い
    keyf = key if key is not None else (lambda x: x)
    decorated = [(keyf(x), x) for x in items]

    def sort(a: list[tuple[Any, T]]) -> list[tuple[Any, T]]:
        if len(a) <= 1:
            return a
        mid = len(a) // 2
        left, right = sort(a[:mid]), sort(a[mid:])  # 分割統治: 半分ずつ解いて
        merged: list[tuple[Any, T]] = []           # 2 つの整列済み列を併合する
        i = j = 0
        while i < len(left) and j < len(right):
            # 右が「真に小さい」ときだけ右を取る。等しければ左（元の順で前にあった方）を取るので安定
            if right[j][0] < left[i][0]:
                merged.append(right[j])
                j += 1
            else:
                merged.append(left[i])
                i += 1
        merged.extend(left[i:])
        merged.extend(right[j:])
        return merged

    return [x for _, x in sort(decorated)]


def quicksort(items: list[T], rng: random.Random | None = None) -> None:
    rng = rng if rng is not None else random.Random()

    def sort(lo: int, hi: int) -> None:  # items[lo..hi]（両端を含む）を整列する
        while lo < hi:
            # ランダムにピボットを選ぶので、どんな入力でも期待計算量は O(n log n)
            pivot = items[rng.randint(lo, hi)]
            # 3-way 分割（オランダ国旗問題）: [< pivot | == pivot | 未処理 | > pivot]
            lt, i, gt = lo, lo, hi
            while i <= gt:
                if items[i] < pivot:
                    items[lt], items[i] = items[i], items[lt]
                    lt += 1
                    i += 1
                elif pivot < items[i]:
                    items[i], items[gt] = items[gt], items[i]
                    gt -= 1
                else:
                    i += 1  # ピボットと等しい要素は真ん中に集まり、以後は触らない
            # 小さい方の区間だけ再帰し、大きい方はループで処理する → 再帰の深さは O(log n) で済む
            if lt - lo < hi - gt:
                sort(lo, lt - 1)
                lo = gt + 1
            else:
                sort(gt + 1, hi)
                hi = lt - 1

    sort(0, len(items) - 1)


def counting_sort(nums: Sequence[int], max_value: int | None = None) -> list[int]:
    for x in nums:
        if not isinstance(x, int):
            raise TypeError(f"整数ではありません: {x!r}")
        if x < 0:
            raise ValueError(f"負の数は扱えません: {x}")
    if not nums:
        return []
    top = max(nums)
    if max_value is not None:
        if top > max_value:
            raise ValueError(f"max_value={max_value} を超える値があります: {top}")
        top = max_value
    # 値ごとの出現回数を数えるだけ。要素どうしを一度も比較しないので Ω(n log n) の壁の外にいる
    counts = [0] * (top + 1)
    for x in nums:
        counts[x] += 1
    out: list[int] = []
    for value, c in enumerate(counts):
        out.extend([value] * c)
    return out


def radix_sort(nums: Sequence[int], base: int = 256) -> list[int]:
    if base < 2:
        raise ValueError(f"base は 2 以上: {base}")
    for x in nums:
        if not isinstance(x, int):
            raise TypeError(f"整数ではありません: {x!r}")
        if x < 0:
            raise ValueError(f"負の数は扱えません: {x}")
    a = list(nums)
    if not a:
        return a
    top = max(a)
    place = 1
    # LSD（最下位桁から）基数ソート: 各桁で「安定な」分配を繰り返す。
    # 下の桁で並べた順序が、上の桁が等しい要素どうしの間で保たれるので、最後に全体が整列する
    while place <= top:
        buckets: list[list[int]] = [[] for _ in range(base)]
        for x in a:
            buckets[(x // place) % base].append(x)  # 追加順を保つ = 安定
        a = [x for b in buckets for x in b]
        place *= base
    return a


# ---------------------------------------------------------------------------
# 演習2: 貪欲法（区間スケジューリング）
# ---------------------------------------------------------------------------

def _validate_intervals(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    out = []
    for s, e in intervals:
        if not s < e:
            raise ValueError(f"開始 < 終了 でない区間です: {(s, e)}")
        out.append((s, e))
    return out


def max_non_overlapping(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    chosen: list[tuple[float, float]] = []
    last_end = None
    # 「最も早く終わる区間」を選び続ける。交換論法: 最適解の最初の区間を、最も早く終わる区間に
    # 取り替えても他と重ならない（むしろ後ろに余裕ができる）ので、この選択で損をすることはない
    for s, e in sorted(_validate_intervals(intervals), key=lambda iv: (iv[1], iv[0])):
        if last_end is None or s >= last_end:  # 半開区間 [s, e) なので、終了 == 開始 は重ならない
            chosen.append((s, e))
            last_end = e
    return chosen


def min_meeting_rooms(intervals: Iterable[tuple[float, float]]) -> int:
    ends: list[float] = []  # 使用中の会議室の終了時刻（最小ヒープ）
    rooms = 0
    for s, e in sorted(_validate_intervals(intervals)):
        # 開始時刻の早い順に見る。最も早く空く部屋が空いていれば再利用する
        if ends and ends[0] <= s:
            heapq.heapreplace(ends, e)
        else:
            heapq.heappush(ends, e)
        rooms = max(rooms, len(ends))
    return rooms


# ---------------------------------------------------------------------------
# 演習3: 動的計画法（編集距離・LCS・差分）
# ---------------------------------------------------------------------------

EditOp = tuple  # ("=", x, x) / ("~", x, y) / ("-", x, None) / ("+", None, y)


def edit_distance(a: Sequence[T], b: Sequence[T]) -> tuple[int, list[EditOp]]:
    n, m = len(a), len(b)
    # dp[i][j] = a[:i] を b[:j] に変える最小の操作回数
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i  # すべて削除
    for j in range(m + 1):
        dp[0][j] = j  # すべて挿入
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j - 1] + cost,  # 一致（コスト 0）または置換
                dp[i - 1][j] + 1,         # a[i-1] を削除
                dp[i][j - 1] + 1,         # b[j-1] を挿入
            )
    # 表を右下から逆にたどり、どの選択で最小値になったかを復元する
    ops: list[EditOp] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and dp[i][j] == dp[i - 1][j - 1] + (0 if a[i - 1] == b[j - 1] else 1):
            ops.append(("=" if a[i - 1] == b[j - 1] else "~", a[i - 1], b[j - 1]))
            i, j = i - 1, j - 1
        elif i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            ops.append(("-", a[i - 1], None))
            i -= 1
        else:
            ops.append(("+", None, b[j - 1]))
            j -= 1
    ops.reverse()
    return dp[n][m], ops


def _lcs_suffix_table(a: Sequence[T], b: Sequence[T]) -> list[list[int]]:
    # L[i][j] = a[i:] と b[j:] の最長共通部分列の長さ（後ろから埋める）
    n, m = len(a), len(b)
    L = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                L[i][j] = L[i + 1][j + 1] + 1
            else:
                L[i][j] = max(L[i + 1][j], L[i][j + 1])
    return L


def lcs(a: Sequence[T], b: Sequence[T]) -> list[T]:
    L = _lcs_suffix_table(a, b)
    out: list[T] = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] == b[j]:
            out.append(a[i])  # 等しい要素は必ず一致させてよい（そうしても最適性を失わない）
            i, j = i + 1, j + 1
        elif L[i + 1][j] >= L[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


def line_diff(old: Sequence[str], new: Sequence[str]) -> list[str]:
    L = _lcs_suffix_table(old, new)
    out: list[str] = []
    i = j = 0
    # 前から順に、LCS に沿って進む。共通行は " "、old だけの行は "-"、new だけの行は "+"。
    # 同点のときは削除を先に選ぶ。「+ の直後に -」は起こらない（起こるなら削除を先に選べたはず）ので、
    # 変更箇所では必ず「- の行 → + の行」の順になる
    while i < len(old) and j < len(new):
        if old[i] == new[j]:
            out.append(" " + old[i])
            i, j = i + 1, j + 1
        elif L[i + 1][j] >= L[i][j + 1]:
            out.append("-" + old[i])
            i += 1
        else:
            out.append("+" + new[j])
            j += 1
    out.extend("-" + line for line in old[i:])
    out.extend("+" + line for line in new[j:])
    return out


# ---------------------------------------------------------------------------
# 演習4: 0/1 ナップサック
# ---------------------------------------------------------------------------

def knapsack(items: Sequence[tuple[int, int]], capacity: int) -> tuple[int, list[int]]:
    if capacity < 0:
        raise ValueError(f"capacity は 0 以上: {capacity}")
    for w, v in items:
        if w < 0 or v < 0:
            raise ValueError(f"重さと価値は 0 以上: {(w, v)}")
    n = len(items)
    # dp[i][c] = 先頭 i 個の品物だけを使い、容量 c で得られる最大の価値
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    for i, (w, v) in enumerate(items, start=1):
        prev, cur = dp[i - 1], dp[i]
        for c in range(capacity + 1):
            best = prev[c]  # 品物 i を入れない
            if w <= c and prev[c - w] + v > best:
                best = prev[c - w] + v  # 品物 i を入れる（各品物は 1 回だけなので prev を見る）
            cur[c] = best
    # どの品物を入れたかを、表を下から逆にたどって復元する
    chosen: list[int] = []
    c = capacity
    for i in range(n, 0, -1):
        if dp[i][c] != dp[i - 1][c]:  # 値が変わった = 品物 i を入れた
            chosen.append(i - 1)
            c -= items[i - 1][0]
    chosen.reverse()
    return dp[n][capacity], chosen


# ---------------------------------------------------------------------------
# 演習5: バックトラッキング
# ---------------------------------------------------------------------------

def n_queens(n: int) -> int:
    if n < 0:
        raise ValueError(f"n は 0 以上: {n}")
    full = (1 << n) - 1

    def place(cols: int, diag1: int, diag2: int) -> int:
        # cols: 使用中の列、diag1/diag2: 次の行で利きのある列（斜め方向）をビットで持つ
        if cols == full:
            return 1  # n 行すべてに置けた
        count = 0
        free = full & ~(cols | diag1 | diag2)  # この行で置ける列
        while free:
            bit = free & -free  # 一番下の 1 のビット（1.1 章のビット演算）
            free ^= bit
            # 次の行では、斜めの利きが 1 列ずつずれる
            count += place(cols | bit, ((diag1 | bit) << 1) & full, (diag2 | bit) >> 1)
        return count

    return place(0, 0, 0)


def subset_sum(nums: Sequence[int], target: int) -> list[int] | None:
    for x in nums:
        if x <= 0:
            raise ValueError(f"正の整数だけを扱います: {x}")
    if target < 0:
        raise ValueError(f"target は 0 以上: {target}")
    # 大きい順に試すと、目標を超える枝を早く刈り込める
    order = sorted(range(len(nums)), key=lambda i: -nums[i])
    values = [nums[i] for i in order]
    # suffix[k] = values[k:] の合計（残りを全部足しても届かない枝を刈るため）
    suffix = [0] * (len(values) + 1)
    for k in range(len(values) - 1, -1, -1):
        suffix[k] = suffix[k + 1] + values[k]
    chosen: list[int] = []

    def search(k: int, remaining: int) -> bool:
        if remaining == 0:
            return True
        if k == len(values) or suffix[k] < remaining:
            return False  # 残りを全部使っても届かない
        if values[k] <= remaining:  # 超える枝は試さない（正の数なので、足すほど増える一方）
            chosen.append(order[k])
            if search(k + 1, remaining - values[k]):
                return True
            chosen.pop()
        return search(k + 1, remaining)  # values[k] を使わない枝

    return sorted(chosen) if search(0, target) else None


# ---------------------------------------------------------------------------
# 演習6: 乱択アルゴリズムと外部ソート
# ---------------------------------------------------------------------------

def reservoir_sample(stream: Iterable[T], k: int, rng: random.Random) -> list[T]:
    if k < 0:
        raise ValueError(f"k は 0 以上: {k}")
    reservoir: list[T] = []
    for i, x in enumerate(stream):
        if i < k:
            reservoir.append(x)
        else:
            # i 番目（0 始まり）の要素を確率 k/(i+1) で採用し、採用するなら既存の 1 つと入れ替える。
            # 帰納法で、どの時点でも「これまでの各要素が等確率 k/(i+1) で残っている」ことが示せる
            j = rng.randrange(i + 1)
            if j < k:
                reservoir[j] = x
    return reservoir


def kway_merge(iterables: Iterable[Iterable[T]], key: Callable[[T], Any] | None = None) -> Iterator[T]:
    keyf = key if key is not None else (lambda x: x)
    iterators = [iter(it) for it in iterables]
    heap: list[tuple[Any, int, T]] = []
    # 各入力の先頭 1 つずつだけをヒープに入れる。メモリは O(k)、1 要素あたり O(log k)
    for idx, it in enumerate(iterators):
        for x in it:
            heap.append((keyf(x), idx, x))
            break
    heapq.heapify(heap)
    while heap:
        # キーが等しいときは入力の番号 idx で順序が決まる（=安定。要素そのものは比べない）
        k, idx, x = heap[0]
        yield x
        for nxt in iterators[idx]:
            heapq.heapreplace(heap, (keyf(nxt), idx, nxt))
            break
        else:
            heapq.heappop(heap)  # この入力は尽きた


def external_sort(
    lines: Iterable[str], max_lines_in_memory: int, tmp_dir: str | os.PathLike[str]
) -> Iterator[str]:
    if max_lines_in_memory < 1:
        raise ValueError(f"max_lines_in_memory は 1 以上: {max_lines_in_memory}")
    run_paths: list[str] = []

    def spill(chunk: list[str]) -> None:
        # メモリに収まる分だけを整列して、一時ファイル（ラン）に書き出す
        chunk.sort()
        fd, path = tempfile.mkstemp(prefix="run-", suffix=".txt", dir=tmp_dir)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.writelines(line + "\n" for line in chunk)
        run_paths.append(path)

    files = []
    try:
        chunk: list[str] = []
        for line in lines:
            if "\n" in line or "\r" in line:
                raise ValueError(f"改行文字を含む行は扱えません: {line!r}")
            chunk.append(line)
            if len(chunk) == max_lines_in_memory:
                spill(chunk)
                chunk = []
        if chunk:
            spill(chunk)
        # 各ランの先頭から少しずつ読みながら k-way マージする（全体をメモリに載せない）
        files = [open(p, encoding="utf-8") for p in run_paths]
        streams = [(line[:-1] for line in f) for f in files]
        yield from kway_merge(streams)
    finally:
        # 途中で例外が起きても、呼び出し側が最後まで読まずに捨てても、一時ファイルを片付ける
        for f in files:
            f.close()
        for p in run_paths:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
