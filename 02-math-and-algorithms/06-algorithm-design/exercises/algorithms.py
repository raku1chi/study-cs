"""2.6 アルゴリズム設計技法 — 演習

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.6          # 合格数を表示
    python3 tools/check.py -v 2.6       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

制約（学びのための縛り）:
    - 演習1 では sorted()・list.sort()・heapq を使わないでください。
    - 演習6 の kway_merge では heapq.merge を使わないでください（heapq の heappush などは使ってよい）。
      external_sort では、メモリに載せた 1 チャンクの整列に限り sorted()・list.sort() を使ってかまいません。
    - それ以外の演習では、標準ライブラリを自由に使ってかまいません。
"""
from __future__ import annotations

import heapq  # noqa: F401  演習2・6で使えます
import os  # noqa: F401  演習6で使えます
import random
import tempfile  # noqa: F401  演習6で使えます
from typing import Any, Callable, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: ソート
# ---------------------------------------------------------------------------

def merge_sort(items: Iterable[T], key: Callable[[T], Any] | None = None) -> list[T]:
    """items を key の昇順に並べた新しいリストを返す（安定なマージソート）。

    - 安定（stable）: キーが等しい要素どうしは、元の順序を保つこと。
    - 入力は変更しない。key を省略したら要素そのものを比べる。
    - 比較回数は O(n log n)（テストは 1024 要素で 10240 回以下であることを確かめます）。

    >>> merge_sort([3, 1, 2])
    [1, 2, 3]
    >>> merge_sort([("b", 2), ("a", 1), ("c", 2)], key=lambda t: t[1])
    [('a', 1), ('b', 2), ('c', 2)]

    ヒント:
    - 半分に分けてそれぞれを再帰的にソートし、2 つの整列済みリストを先頭から併合する。
    - 安定にするには、併合で「右の先頭が左の先頭より真に小さいときだけ右を取る」。
    - key() は要素ごとに 1 回だけ計算し、(キー, 要素) の組にしておくとよい。
      比較にはキーだけを使うこと（要素そのものは比較できないかもしれない）。
    """
    raise NotImplementedError("演習1: merge_sort を実装してください")


def quicksort(items: list[T], rng: random.Random | None = None) -> None:
    """items をその場で（in-place）昇順に並べ替える、乱択クイックソート。戻り値は None。

    - ピボットは rng を使ってランダムに選ぶこと（rng が None なら random.Random() を作って使う）。
      乱数を引数で受け取る（注入する）のは、テストで結果を再現できるようにするため。
    - 整列済み・逆順・すべて同じ値、といった入力でも O(n log n) で終わること。
      （テストは 2000 要素で比較回数が 10 n log2 n 未満であることを確かめます）
    - 安定である必要はない。

    ヒント:
    - 「すべて同じ値」の入力で素朴な 2 分割（Lomuto 方式）を使うと、毎回片側に全要素が寄って
      O(n^2) になり、再帰も深くなりすぎる。3-way 分割（ピボット未満・等しい・超える の 3 つに分ける。
      ダイクストラの「オランダ国旗問題」）を使うとよい。
    - 再帰は小さい方の区間だけにし、大きい方はループで処理すると、再帰の深さが O(log n) に収まる。
    """
    raise NotImplementedError("演習1: quicksort を実装してください")


def counting_sort(nums: Sequence[int], max_value: int | None = None) -> list[int]:
    """0 以上の整数の列を、比較を使わずに整列した新しいリストを返す（計数ソート）。O(n + k)。

    - k は値の最大値（max_value が指定されていればそれ、なければ実際の最大値）。
    - 負の数、または max_value を超える値があれば ValueError。整数以外があれば TypeError。

    >>> counting_sort([3, 0, 2, 3, 1])
    [0, 1, 2, 3, 3]
    """
    raise NotImplementedError("演習1: counting_sort を実装してください")


def radix_sort(nums: Sequence[int], base: int = 256) -> list[int]:
    """0 以上の整数の列を、下の桁から順に分配して整列した新しいリストを返す（LSD 基数ソート）。

    - base 進数の 1 桁ずつ、安定な分配（バケットに追加順に入れて、順に連結する）を繰り返す。
      桁の数を d とすると O(d × (n + base))。
    - base < 2 なら ValueError。負の数があれば ValueError。整数以外があれば TypeError。
    - 入力は変更しない。

    >>> radix_sort([170, 45, 75, 90, 802, 24, 2, 66], base=10)
    [2, 24, 45, 66, 75, 90, 170, 802]
    """
    raise NotImplementedError("演習1: radix_sort を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 貪欲法（区間スケジューリング）
# ---------------------------------------------------------------------------
# 区間は (開始, 終了) のタプルで、半開区間 [開始, 終了) を表す。
# したがって (9, 10) と (10, 11) は重ならない（10 時に終わる会議の直後に 10 時の会議を入れられる）。
# 開始 < 終了 でない区間があれば ValueError。

def max_non_overlapping(intervals: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    """互いに重ならない区間をできるだけ多く選び、終了時刻の昇順（同じなら開始時刻の昇順）で返す。

    1 つの会議室にできるだけ多くの会議を入れる問題（区間スケジューリング）。

    >>> max_non_overlapping([(9, 12), (10, 11), (11, 13), (12, 14), (13, 15), (9, 10)])
    [(9, 10), (10, 11), (11, 13), (13, 15)]

    ヒント: 「終わるのが最も早い区間」を選び、それと重ならない区間の中から同じことを繰り返す。
    なぜこれで最適になるのか（交換論法）は README を参照。
    """
    raise NotImplementedError("演習2: max_non_overlapping を実装してください")


def min_meeting_rooms(intervals: Iterable[tuple[float, float]]) -> int:
    """すべての会議を開くのに必要な会議室の最小数を返す（区間がなければ 0）。

    >>> min_meeting_rooms([(9, 10), (9, 12), (10, 11), (11, 12)])
    2

    ヒント: 開始時刻の早い順に見ていき、「使用中の部屋の終了時刻」を最小ヒープで持つ。
    最も早く空く部屋が、次の会議の開始時刻までに空いていれば再利用する。
    """
    raise NotImplementedError("演習2: min_meeting_rooms を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 動的計画法（編集距離・最長共通部分列・行単位の差分）
# ---------------------------------------------------------------------------

def edit_distance(a: Sequence[T], b: Sequence[T]) -> tuple[int, list[tuple]]:
    """a を b に変えるのに必要な最小の操作回数（レーベンシュタイン距離）と、その操作列を返す。

    操作は 1 文字（1 要素）の挿入・削除・置換で、それぞれコスト 1。
    戻り値の操作列は、a の先頭から順に次のタプルを並べたもの（要素に None は含まれないものとする）:
        ("=", x, x)     x はそのまま（コスト 0）
        ("~", x, y)     x を y に置換
        ("-", x, None)  x を削除
        ("+", None, y)  y を挿入
    操作列から "+" 以外の x を並べると a に、"-" 以外の y を並べると b になること。
    "=" 以外の操作の数は距離と一致すること。最小の操作列が複数あればどれでもよい。

    >>> edit_distance("kitten", "sitting")[0]
    3
    >>> edit_distance("ab", "b")
    (1, [('-', 'a', None), ('=', 'b', 'b')])

    ヒント:
    - dp[i][j] = 「a の先頭 i 文字」を「b の先頭 j 文字」に変える最小コスト。
      dp[i][0] = i、dp[0][j] = j。
      dp[i][j] = min(dp[i-1][j-1] + (a[i-1] != b[j-1]), dp[i-1][j] + 1, dp[i][j-1] + 1)
    - 操作列は、表を dp[n][m] から逆にたどり、「どの候補で最小値になったか」を調べて復元する。
    """
    raise NotImplementedError("演習3: edit_distance を実装してください")


def lcs(a: Sequence[T], b: Sequence[T]) -> list[T]:
    """a と b の最長共通部分列（longest common subsequence）の 1 つをリストで返す。

    部分列とは、元の順序を保ったまま、いくつかの要素を取り除いたもの（連続している必要はない）。

    >>> "".join(lcs("ABCBDAB", "BDCABA")) in {"BCBA", "BDAB", "BCAB"}
    True
    """
    raise NotImplementedError("演習3: lcs を実装してください")


def line_diff(old: Sequence[str], new: Sequence[str]) -> list[str]:
    """2 つの行のリストの差分を、unified diff に似た形式の行のリストで返す。

    - 共通の行は " " + 行、old にだけある行は "-" + 行、new にだけある行は "+" + 行。
    - " " の行の数が最大（= old と new の最長共通部分列の長さ）になること（最小の差分）。
    - " " と "-" の行を並べると old に、" " と "+" の行を並べると new になること。
    - 変更箇所では削除行を先に出すこと: "+" の行の直後に "-" の行が来てはいけない。

    >>> line_diff(["a", "b", "c", "d"], ["a", "B", "c", "d", "e"])
    [' a', '-b', '+B', ' c', ' d', '+e']

    ヒント:
    - L[i][j] = 「old[i:] と new[j:] の LCS の長さ」を後ろから埋めた表を作ると、
      前から順に「一致なら共通行、そうでなければ L の値が大きい方へ進む」と歩ける。
    - L[i+1][j] >= L[i][j+1] のとき（同点を含む）は削除を選ぶ。こうすると
      「+ の直後に -」が起こらないことが証明できる（README 参照）。
    """
    raise NotImplementedError("演習3: line_diff を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 0/1 ナップサック問題
# ---------------------------------------------------------------------------

def knapsack(items: Sequence[tuple[int, int]], capacity: int) -> tuple[int, list[int]]:
    """重さの合計が capacity 以下になるように品物を選び、価値の合計を最大にする（各品物は 0 個か 1 個）。

    - items[i] = (重さ, 価値)。どちらも 0 以上の整数。capacity も 0 以上の整数。負なら ValueError。
    - 戻り値は (価値の合計の最大値, 選んだ品物の添字の昇順リスト)。最適な選び方が複数あればどれでもよい。
    - O(n × capacity) の動的計画法で解くこと（2^n 通りの全探索はしない）。

    >>> knapsack([(1, 1), (3, 4), (4, 5), (5, 7)], 7)
    (9, [1, 2])

    ヒント:
    - dp[i][c] = 先頭 i 個の品物だけを使い、容量 c で得られる最大の価値。
      dp[i][c] = max(dp[i-1][c], dp[i-1][c - w_i] + v_i)（w_i <= c のとき）
    - 選んだ品物は、i = n から逆にたどり「dp[i][c] != dp[i-1][c] なら品物 i-1 を入れた」で復元できる。
    """
    raise NotImplementedError("演習4: knapsack を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: バックトラッキング
# ---------------------------------------------------------------------------

def n_queens(n: int) -> int:
    """n × n の盤面に、互いに取り合わない（同じ行・列・斜めにない）n 個のクイーンを置く方法の数を返す。

    - n == 0 のときは 1（何も置かない 1 通り）。n < 0 なら ValueError。
    - n = 10 程度まで、すぐに（1 秒以内に）答えが出ること。

    >>> [n_queens(n) for n in range(1, 9)]
    [1, 0, 0, 2, 10, 4, 40, 92]

    ヒント: 1 行に 1 個ずつ置いていき、置けない列（同じ列・2 方向の斜め）を記録しておく。
    使用中の列と斜めを整数のビットで持つと速い（1.1 章のビット演算。x & -x で一番下の 1 のビット）。
    """
    raise NotImplementedError("演習5: n_queens を実装してください")


def subset_sum(nums: Sequence[int], target: int) -> list[int] | None:
    """nums からいくつかを選んで合計をちょうど target にする。選んだ要素の添字の昇順リストを返す。

    - nums の要素は正の整数（1 以上）。0 以下があれば ValueError。target < 0 も ValueError。
    - 見つからなければ None。target == 0 なら []（何も選ばない）。解が複数あればどれでもよい。
    - バックトラッキングで探索し、次の枝刈りを入れること（テストは 22 要素で 1 秒以内を確かめます）:
        - 足すと target を超える要素は試さない
        - 残りの要素を全部足しても target に届かないなら、その枝をあきらめる

    >>> nums = [8, 6, 7, 5, 3]
    >>> sum(nums[i] for i in subset_sum(nums, 16))
    16
    >>> subset_sum([4, 6, 10], 7) is None
    True

    ヒント: 大きい順に並べ替えて（元の添字を覚えておく）、「残りの合計」を後ろから累積しておくと、
    2 つ目の枝刈りが O(1) で判定できる。
    """
    raise NotImplementedError("演習5: subset_sum を実装してください")


# ---------------------------------------------------------------------------
# 演習6（★★☆）: 乱択アルゴリズムと、メモリに載らないデータの整列
# ---------------------------------------------------------------------------

def reservoir_sample(stream: Iterable[T], k: int, rng: random.Random) -> list[T]:
    """長さの分からないストリームから、k 個を一様ランダムに（どの要素も同じ確率で）選ぶ。

    リザーバサンプリング（アルゴリズム R）を、次の手順どおりに実装すること
    （テストは rng の呼び出し方まで確かめます）:
      - 先頭の k 個はそのままリザーバ（長さ k のリスト）に入れる。
      - i 番目（0 始まり、i >= k）の要素では j = rng.randrange(i + 1) を 1 回だけ呼び、
        j < k ならリザーバの j 番目をその要素で置き換える。
    - ストリームは 1 回しか走査できないものとして扱う（len() を使わない）。O(k) メモリ。
    - 要素が k 個未満なら、全要素を到着順に返す。k < 0 なら ValueError。

    >>> reservoir_sample([1, 2, 3], 5, random.Random(0))
    [1, 2, 3]
    """
    raise NotImplementedError("演習6: reservoir_sample を実装してください")


def kway_merge(iterables: Iterable[Iterable[T]], key: Callable[[T], Any] | None = None) -> Iterator[T]:
    """それぞれ key の昇順に整列済みの複数の入力を、1 本の昇順の列に併合して、順に返す（ジェネレータ）。

    - 遅延評価: 各入力から必要な分だけ読むこと（先に全部を list にしない）。
      無限に続く入力や、メモリに載らない巨大なファイルでも使えるようにするため。
    - キーが等しい要素は、入力の順番（iterables の中での位置）が前のものを先に出す（安定）。
      要素そのものは比較しないこと（比較できないかもしれない）。
    - 入力が k 本、全要素数が n なら O(n log k) 時間・O(k) メモリ。

    >>> list(kway_merge([[1, 4, 7], [2, 5, 8], [3, 6, 9]]))
    [1, 2, 3, 4, 5, 6, 7, 8, 9]

    ヒント: 各入力の「次の要素」を 1 つずつ、(キー, 入力の番号, 要素) としてヒープに入れる。
    最小のものを出したら、同じ入力から次の要素を読んでヒープに入れる（heapq.heapreplace が便利）。
    """
    raise NotImplementedError("演習6: kway_merge を実装してください")


def external_sort(
    lines: Iterable[str], max_lines_in_memory: int, tmp_dir: str | os.PathLike[str]
) -> Iterator[str]:
    """メモリに一度に max_lines_in_memory 行までしか置かずに、行を昇順に並べて返す（ジェネレータ）。

    外部ソート（external sort）:
      1. 入力を max_lines_in_memory 行ずつ読み、メモリ上で整列して、tmp_dir の一時ファイル
         （ラン, run）に書き出す。
      2. すべてのランを kway_merge で併合しながら、1 行ずつ返す。
    - 各行は改行文字を含まない str。"\\n" や "\\r" を含む行があれば ValueError。
    - max_lines_in_memory < 1 なら ValueError。
    - 最後まで読み終えたら（途中で例外が起きた場合も）一時ファイルをすべて削除すること。
    - エラーは、返されたイテレータを読み進めた時点で送出されてよい。

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     list(external_sort(["b", "c", "a"], 2, d))
    ['a', 'b', 'c']

    ヒント:
    - 一時ファイルは tempfile.mkstemp(dir=tmp_dir) で作れる。書き込み・読み込みとも encoding="utf-8" を明示する。
    - ファイルを行ごとに読むと末尾に "\\n" が付いているので取り除く。
    - try: ... finally: で片付けると、途中で例外が起きても一時ファイルが残らない。
    """
    raise NotImplementedError("演習6: external_sort を実装してください")
