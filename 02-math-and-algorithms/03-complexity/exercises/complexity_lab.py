"""2.3 計算量とアルゴリズム解析 — 演習

各関数・クラスの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.3          # 合格数を表示
    python3 tools/check.py -v 2.3       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

演習の一覧:
    演習1（★☆☆）うっかり二乗（accidentally quadratic）な関数を O(n) に書き直す
    演習2（★★☆）二分探索の変種 lower_bound / upper_bound / first_true
    演習3（★★☆）動的配列を実装し、ならし解析の主張（コピー回数の上限）を確かめる
    演習4（★★☆）実測の時間から計算量を推定する（両対数の最小二乗法とモデル比較）
    演習5（★★★）分割統治の掛け算の回数を数え、マスター定理の予測と照合する

テストの特徴:
    計算量のテストは、実行時間ではなく「基本操作の回数」を数えて行います
    （比較・ハッシュ計算の回数を数える要素、要素アクセスの回数を数える列など）。
    時間はマシンや負荷で変わりますが、操作の回数は変わらないので、テストが安定します。

制約（学びのための縛り）:
    - 演習2 では bisect モジュールを使わないでください（テストでは答え合わせに使っています）。
    - 演習3 では、内部の記憶領域を「固定長のリスト」（[None] * capacity）として扱い、
      容量を変えるときは新しいリストを作って要素を 1 つずつコピーしてください
      （list.append や list.extend でデータを伸ばすと、Python の list のならし解析を借りることになります）。
"""
from __future__ import annotations

import math  # noqa: F401  演習4・5で使えます
import time
from collections import Counter  # noqa: F401  演習1で使えます
from typing import Any, Callable, Hashable, Iterable, Sequence

# ---------------------------------------------------------------------------
# 演習1（★☆☆）: うっかり二乗を直す
# ---------------------------------------------------------------------------
# 各関数の docstring にある「遅い参照実装」は O(n^2) です。同じ結果を返す O(n)（平均）の
# 実装に書き直してください。テストは、要素の比較・ハッシュ計算・足し算の回数を数え、
# 回数が n^2 に比例して増える実装を不合格にします。


def has_duplicates(items: Sequence[Hashable]) -> bool:
    """items に同じ値（==）が 2 回以上現れるなら True。

    遅い参照実装（O(n^2)）:
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i] == items[j]:
                    return True
        return False

    >>> has_duplicates([3, 1, 4, 1, 5])
    True
    >>> has_duplicates([])
    False
    """
    raise NotImplementedError("演習1: has_duplicates を実装してください")


def dedupe_preserving_order(items: Iterable[Hashable]) -> list:
    """重複を取り除いたリストを返す。各値は最初に現れた位置の順に並べる。

    遅い参照実装（O(n^2)）:
        out = []
        for x in items:
            if x not in out:      # list に対する in は O(len(out))
                out.append(x)
        return out

    >>> dedupe_preserving_order(["b", "a", "b", "c", "a"])
    ['b', 'a', 'c']
    """
    raise NotImplementedError("演習1: dedupe_preserving_order を実装してください")


def two_sum(nums: Sequence[int], target: int) -> tuple[int, int] | None:
    """nums[i] + nums[j] == target となる添字の組 (i, j)（i < j）を返す。なければ None。

    複数あるときは、j が最小の組を、その中で i が最小のものを返す（下の参照実装と同じ結果）。

    遅い参照実装（O(n^2)）:
        for j in range(len(nums)):
            for i in range(j):
                if nums[i] + nums[j] == target:
                    return (i, j)
        return None

    >>> two_sum([2, 7, 11, 15], 9)
    (0, 1)
    >>> two_sum([3, 3, 4, 3], 6)
    (0, 1)
    >>> two_sum([1, 2, 3], 100) is None
    True

    ヒント: j を左から見ながら、「これまでに見た値 → 最初に現れた添字」の dict を育てる。
    """
    raise NotImplementedError("演習1: two_sum を実装してください")


def count_pairs_with_sum(nums: Sequence[int], k: int) -> int:
    """nums[i] + nums[j] == k となる添字の組 (i, j)（i < j）の個数を返す。

    遅い参照実装（O(n^2)）:
        return sum(1 for i in range(len(nums)) for j in range(i + 1, len(nums))
                   if nums[i] + nums[j] == k)

    >>> count_pairs_with_sum([1, 5, 7, -1, 5], 6)    # (1,5), (1,5), (7,-1)
    3
    >>> count_pairs_with_sum([3, 3, 3], 6)           # C(3, 2) = 3
    3

    ヒント: 値ごとの個数（collections.Counter）を数えれば、組の数は掛け算で求まる。
    同じ値どうしの組（v + v == k）と、二重に数えないことに注意。
    """
    raise NotImplementedError("演習1: count_pairs_with_sum を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 二分探索の変種
# ---------------------------------------------------------------------------
# 要素どうしの比較には「<」だけを使ってください（標準ライブラリの bisect と同じ流儀）。
# テストでは「<」しか定義していない要素でも正しく動くかを確かめます。
# 要素へのアクセス回数は O(log n)（テストは len の bit_length + 1 回以下を要求）です。


def lower_bound(a: Sequence, x: Any, lo: int = 0, hi: int | None = None) -> int:
    """昇順に並んだ a の範囲 [lo, hi) で、a[i] >= x となる最小の i を返す（なければ hi）。

    言い換えると「x を挿入しても順序が保たれる、いちばん左の位置」。bisect.bisect_left と同じ。
    - hi が None なら len(a)。0 <= lo <= hi <= len(a) でなければ ValueError。

    >>> lower_bound([1, 2, 2, 2, 3], 2)
    1
    >>> lower_bound([1, 2, 2, 2, 3], 4)
    5

    ヒント（不変条件）: a[:lo] はすべて x 未満、a[hi:] はすべて x 以上、を保ちながら区間を半分にする。
    """
    raise NotImplementedError("演習2: lower_bound を実装してください")


def upper_bound(a: Sequence, x: Any, lo: int = 0, hi: int | None = None) -> int:
    """昇順に並んだ a の範囲 [lo, hi) で、a[i] > x となる最小の i を返す（なければ hi）。

    bisect.bisect_right と同じ。upper_bound(a, x) - lower_bound(a, x) は a に含まれる x の個数。

    >>> upper_bound([1, 2, 2, 2, 3], 2)
    4
    """
    raise NotImplementedError("演習2: upper_bound を実装してください")


def first_true(lo: int, hi: int, pred: Callable[[int], bool]) -> int:
    """整数の範囲 [lo, hi) で pred(i) が真になる最小の i を返す（なければ hi）。

    pred は単調（ある境界より左はすべて偽、境界から右はすべて真）であると仮定してよい。
    二分探索の「答えそのものを探す」使い方で、配列がなくても使える:
        - 整数平方根: first_true(0, n + 2, lambda r: r * r > n) - 1
        - 容量計画: 「k 台で処理しきれるか」が単調なら、最小の台数を求められる
        - git bisect: 「このコミットでテストが失敗するか」で最初の悪いコミットを探す
    - lo > hi なら ValueError。
    - pred の呼び出しは (hi - lo).bit_length() 回以下であること（テストで数えます）。

    >>> first_true(0, 100, lambda i: i * i >= 50)
    8
    >>> first_true(0, 10, lambda i: False)
    10
    """
    raise NotImplementedError("演習2: first_true を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 動的配列とならし解析
# ---------------------------------------------------------------------------


class DynamicArray:
    """Python の list のように末尾に追加・削除できる配列を、固定長の記憶領域の上に実装する。

    容量（capacity）のルールは次の通りに正確に実装すること（テストは容量の値も確かめます）:
        - 生成時の容量は initial_capacity（1 以上。そうでなければ ValueError）。
        - append で満杯（len == capacity）なら、先に容量を 2 倍にしてから追加する。
        - pop の後で「capacity > initial_capacity かつ len <= capacity // 4」なら、
          容量を max(capacity // 2, initial_capacity) に縮める。
        - 容量を変えるたびに、そのとき入っている要素（len 個）を新しい領域へ 1 つずつコピーし、
          その個数を copies に加算する。

    ならし解析の主張（テストで確かめます）:
        - 空の配列（initial_capacity=1）に n 回 append したとき、copies <= 2n
          （append 自身の書き込み n 回と合わせて、総書き込み回数 <= 3n）。
        - どんな append / pop の列でも、copies は操作回数の定数倍（<= 3 倍）で抑えられる。
        - 容量の境界で append と pop を交互に繰り返しても、コピーが毎回起きる「振動」は起きない。
          （縮小の条件を len <= capacity // 2 にすると振動することを、自分で確かめてみよう）

    >>> arr = DynamicArray()
    >>> for i in range(5):
    ...     arr.append(i)
    >>> len(arr), arr.capacity, arr.copies    # 容量 1→2→4→8、コピーは 1+2+4 = 7 回
    (5, 8, 7)
    >>> arr[0], arr[-1]
    (0, 4)
    """

    def __init__(self, initial_capacity: int = 1) -> None:
        raise NotImplementedError("演習3: DynamicArray.__init__ を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習3: DynamicArray.__len__ を実装してください")

    @property
    def capacity(self) -> int:
        """現在の記憶領域の大きさ（要素をいくつまで入れられるか）。"""
        raise NotImplementedError("演習3: DynamicArray.capacity を実装してください")

    @property
    def copies(self) -> int:
        """容量の変更に伴って要素をコピーした回数の累計。"""
        raise NotImplementedError("演習3: DynamicArray.copies を実装してください")

    def append(self, value: Any) -> None:
        """末尾に value を追加する（ならし O(1)）。"""
        raise NotImplementedError("演習3: DynamicArray.append を実装してください")

    def pop(self) -> Any:
        """末尾の要素を取り除いて返す（ならし O(1)）。空なら IndexError。"""
        raise NotImplementedError("演習3: DynamicArray.pop を実装してください")

    def __getitem__(self, index: int) -> Any:
        """index 番目の要素を返す（O(1)）。負の添字は list と同じく末尾から数える。範囲外なら IndexError。"""
        raise NotImplementedError("演習3: DynamicArray.__getitem__ を実装してください")

    def __setitem__(self, index: int, value: Any) -> None:
        """index 番目の要素を value にする（O(1)）。添字の扱いは __getitem__ と同じ。"""
        raise NotImplementedError("演習3: DynamicArray.__setitem__ を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 実測から計算量を推定する
# ---------------------------------------------------------------------------

#: estimate_order が候補にするモデル。ラベルと、n から「形」を返す関数の組。
ORDER_MODELS: list[tuple[str, Callable[[float], float]]] = [
    ("O(1)", lambda n: 1.0),
    ("O(log n)", lambda n: math.log(n)),
    ("O(n)", lambda n: n),
    ("O(n log n)", lambda n: n * math.log(n)),
    ("O(n^2)", lambda n: n**2),
    ("O(n^3)", lambda n: n**3),
]


def fit_loglog_slope(sizes: Sequence[float], times: Sequence[float]) -> float:
    """(log n, log t) の点に最小二乗法で直線を当てはめ、その傾きを返す。

    t = c·n^k なら log t = log c + k·log n なので、傾きは指数 k の推定値になる。
    傾き = Σ(x - x̄)(y - ȳ) / Σ(x - x̄)^2（x = log n, y = log t）

    - sizes と times の長さが違う、2 点未満、n < 2 や t <= 0 を含む、sizes がすべて同じ値、
      のいずれかなら ValueError。

    >>> round(fit_loglog_slope([1000, 2000, 4000], [3.0, 12.0, 48.0]), 6)
    2.0
    """
    raise NotImplementedError("演習4: fit_loglog_slope を実装してください")


def estimate_order(sizes: Sequence[float], times: Sequence[float]) -> str:
    """実測の (n, 時間) の組から、ORDER_MODELS のうち最もよく当てはまるモデルのラベルを返す。

    手順:
        各モデル g について、t ≈ c·g(n) を対数でとった log t ≈ log c + log g(n) を当てはめる。
        最適な log c は残差 r_i = log t_i - log g(n_i) の平均 r̄ で、
        当てはまりの悪さは残差平方和 Σ(r_i - r̄)^2。これが最小のモデルを選ぶ。
        （差が 1e-12 未満なら、ORDER_MODELS で先にある単純なモデルを選ぶ）
    傾きだけで判断すると、O(n) と O(n log n) の区別が難しい（n log n の傾きは 1.1 前後）ので、
    モデルごとの当てはまりを比べるのがこの方法の要点です。

    - 入力の条件は fit_loglog_slope と同じ（違反すれば ValueError）。

    >>> estimate_order([500, 1000, 2000, 4000], [0.0032, 0.0118, 0.0466, 0.1881])   # 本文 6.2 節の実測
    'O(n^2)'
    """
    raise NotImplementedError("演習4: estimate_order を実装してください")


def measure_times(func: Callable[[Any], Any], make_input: Callable[[int], Any],
                  sizes: Sequence[int], repeat: int = 3,
                  timer: Callable[[], float] = time.perf_counter) -> list[float]:
    """各 n について func(make_input(n)) の実行時間を repeat 回測り、最小値のリストを返す。

    - 入力の生成（make_input(n)）は、n ごとに 1 回だけ行い、計測に含めないこと。
    - 1 回の計測は「start = timer(); func(data); elapsed = timer() - start」とする。
    - 最小値をとるのは、他のプロセスや GC による割り込みの影響を除くため
      （timeit モジュールのドキュメントも、繰り返しの最小値を見ることを勧めている）。
    - repeat < 1 なら ValueError。
    - timer は注入できる（テストでは、決まった値を返す偽の時計を渡して決定的に確かめます）。

    使用例（実際の計測）:
        sizes = [1000, 2000, 4000, 8000]
        times = measure_times(sorted, lambda n: random.sample(range(10**9), n), sizes)
        print(estimate_order(sizes, times))    # 多くの環境で 'O(n log n)' か 'O(n)' になる
    """
    raise NotImplementedError("演習4: measure_times を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: 分割統治の計算量をマスター定理で確かめる
# ---------------------------------------------------------------------------


def master_theorem(a: float, b: float, d: float) -> tuple[int, float, int]:
    """漸化式 T(n) = a·T(n/b) + Θ(n^d) の解を、(場合の番号, p, k) で返す。T(n) = Θ(n^p (log n)^k)。

        場合 1: a > b^d（葉が支配的）  → (1, log_b a, 0)
        場合 2: a = b^d（各段が同じ）  → (2, d, 1)
        場合 3: a < b^d（根が支配的）  → (3, d, 0)

    - a >= 1, b > 1, d >= 0 でなければ ValueError。
    - a と b^d の比較は math.isclose(a, b**d, rel_tol=1e-9) で「等しい」とみなすこと
      （log_b a と d を直接比べると、math.log(1000, 10) = 2.9999999999999996 のような誤差で間違える）。

    >>> master_theorem(2, 2, 1)       # マージソート: Θ(n log n)
    (2, 1.0, 1)
    >>> master_theorem(1, 2, 0)       # 二分探索: Θ(log n)
    (2, 0.0, 1)
    >>> case, p, k = master_theorem(3, 2, 1)   # カラツバ法: Θ(n^1.585)
    >>> case, round(p, 3), k
    (1, 1.585, 0)
    """
    raise NotImplementedError("演習5: master_theorem を実装してください")


def karatsuba_poly(p: Sequence[int], q: Sequence[int]) -> tuple[list[int], int]:
    """多項式の積をカラツバ法で求め、(積の係数, 係数どうしの掛け算の回数) を返す。

    多項式は係数のリストで表す（低次から。[1, 2, 3] は 1 + 2x + 3x^2）。
    - p と q は同じ長さ n で、n は 2 のべき乗（1, 2, 4, 8, ...）。そうでなければ ValueError。
    - 積の係数のリストの長さは 2n - 1。
    - 掛け算の回数は「係数どうしの掛け算（n == 1 の基底での p[0] * q[0]）」だけを数える。
      足し算・引き算は数えない。

    アルゴリズム（h = n // 2）:
        p = p0 + x^h·p1、q = q0 + x^h·q1 と分ける（p0 = p[:h], p1 = p[h:]）
        z0 = p0·q0、z2 = p1·q1、zm = (p0 + p1)·(q0 + q1)       ← 再帰は 3 回
        z1 = zm - z0 - z2                                     （= p0·q1 + p1·q0）
        積 = z0 + x^h·z1 + x^(2h)·z2
    掛け算の回数 M(n) は M(n) = 3·M(n/2)、M(1) = 1 を満たすので、n = 2^k なら M(n) = 3^k = n^(log2 3)。

    >>> karatsuba_poly([1, 2], [3, 4])      # (1 + 2x)(3 + 4x) = 3 + 10x + 8x^2
    ([3, 10, 8], 3)

    CPython の int も、桁数の大きい整数の掛け算にカラツバ法を使っています。
    """
    raise NotImplementedError("演習5: karatsuba_poly を実装してください")


def naive_dc_poly(p: Sequence[int], q: Sequence[int]) -> tuple[list[int], int]:
    """karatsuba_poly と同じ分け方で、4 つの部分積 p0·q0, p0·q1, p1·q0, p1·q1 を
    すべて再帰で計算する「素朴な分割統治」。(積の係数, 掛け算の回数) を返す。入力の条件は同じ。

    M(n) = 4·M(n/2) なので M(n) = n^2。分割統治にしただけでは速くならないことを確かめよう。

    >>> naive_dc_poly([1, 2], [3, 4])
    ([3, 10, 8], 4)
    """
    raise NotImplementedError("演習5: naive_dc_poly を実装してください")
