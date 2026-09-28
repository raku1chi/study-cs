"""1.3 メモリ階層とキャッシュ — 演習: キャッシュシミュレータ

CPU のキャッシュの動きを Python で再現し、アクセスパターンによってヒット率がどう変わるかを確かめます。

    演習1（★☆☆）: アドレスをタグ・インデックス・オフセットに分解する      cache_geometry, split_address
    演習2（★★☆）: セットアソシアティブ・キャッシュ（LRU）のシミュレータ    Cache.access, Cache.contains
    演習3（★★★）: 行列のたどり方・転置のアクセスパターン（トレース）を作る  row_major_trace ほか
    演習4（★★☆）: ライトバックとライトスルーのメモリ通信量を数える        Cache.access, Cache.flush

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.3
    python3 tools/check.py -v 1.3       # 詳しい出力
このディレクトリで直接実行することもできます:
    python3 -m unittest -v

用語:
    - ライン（line, ブロック）: キャッシュとメモリの間でやり取りする単位（例: 64 バイト）。
    - セット（set）: アドレスから決まる「置き場所の候補」のグループ。1 セットに ways 本のラインが入る。
    - ways = 1 ならダイレクトマップ、セットが 1 つだけ（ways = 全ライン数）ならフルアソシアティブ。
    - アドレスは「タグ | インデックス | オフセット」に分かれる。
          オフセット: ライン内の位置（log2(line_size) ビット）
          インデックス: どのセットか（log2(セット数) ビット）
          タグ: 同じセットに入るラインどうしを見分ける残りの上位ビット

注意: このシミュレータはアドレスを「そのバイトを含むライン」への 1 回のアクセスとして扱います
（1 回のアクセスが 2 つのラインにまたがる場合は考えません）。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Iterable, Optional, Union

Access = Union[int, tuple[int, bool]]  # 番地だけなら読み込み、(番地, 書き込みか) の組も使える

WRITE_POLICIES = ("write-back", "write-through")


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: アドレスの分解
# ---------------------------------------------------------------------------

def cache_geometry(cache_size: int, line_size: int, ways: int) -> tuple[int, int, int]:
    """キャッシュの形から (セット数, オフセットのビット数, インデックスのビット数) を求める。

    - セット数 = cache_size ÷ (line_size × ways)
    - line_size とセット数は 2 のべき乗でなければならない（cache_size は 2 のべき乗でなくてもよい。
      例: 48 KiB・12 ウェイの L1 キャッシュ → 64 セット）。
    - 値が 0 以下、line_size やセット数が 2 のべき乗でない、cache_size が line_size × ways で
      割り切れない場合は ValueError。

    >>> cache_geometry(32 * 1024, 64, 8)     # 32 KiB、64 バイトのライン、8 ウェイ
    (64, 6, 6)
    >>> cache_geometry(48 * 1024, 64, 12)    # 48 KiB、12 ウェイ（最近の x86 の L1 データキャッシュの一例）
    (64, 6, 6)
    """
    raise NotImplementedError("演習1: cache_geometry を実装してください")


def split_address(addr: int, cache_size: int, line_size: int, ways: int) -> tuple[int, int, int]:
    """アドレス addr を (タグ, インデックス, オフセット) に分解する。

    - addr が負なら ValueError。キャッシュの形が不正なら（cache_geometry と同じく）ValueError。

    >>> split_address(0x12345, 32 * 1024, 64, 8)   # 0x12345 = 0b 010010 001101 000101
    (18, 13, 5)

    ヒント: シフトとマスク（& (2^k − 1)）で取り出す。1.1 章のビット演算の復習です。
    """
    raise NotImplementedError("演習1: split_address を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）・演習4（★★☆）: キャッシュ本体
# ---------------------------------------------------------------------------

class Cache:
    """セットアソシアティブ・キャッシュ。置き換えは LRU（最も長く使われていないラインを追い出す）。

    __init__ は用意済みです（演習1 の cache_geometry を使っています）。

    統計（すべて 0 から始まる整数）:
        hits, misses      : ヒット・ミスの回数
        evictions         : ラインを追い出した回数
        mem_reads         : メモリから読み込んだバイト数（ラインを読み込むたびに line_size）
        mem_writes        : メモリへ書き込んだバイト数（演習4 の規則に従う）
    """

    def __init__(
        self,
        cache_size: int,
        line_size: int,
        ways: int,
        write_policy: str = "write-back",
        write_allocate: bool = True,
        word_size: int = 8,
    ) -> None:
        self.num_sets, self.offset_bits, self.index_bits = cache_geometry(cache_size, line_size, ways)
        if write_policy not in WRITE_POLICIES:
            raise ValueError(f"write_policy は {WRITE_POLICIES} のいずれかです: {write_policy!r}")
        if word_size <= 0:
            raise ValueError("word_size は正の整数です")
        self.cache_size = cache_size
        self.line_size = line_size
        self.ways = ways
        self.write_policy = write_policy
        self.write_allocate = write_allocate
        self.word_size = word_size  # 1 回の書き込みの大きさ（ライトスルーで毎回メモリへ書くバイト数）
        # セットごとに「タグ → dirty フラグ」の OrderedDict を用意しておく（使い方は自由に変えてよい）。
        # OrderedDict は move_to_end(key) と popitem(last=False) で、LRU の順序を簡単に管理できる。
        self.sets: list[OrderedDict[int, bool]] = [OrderedDict() for _ in range(self.num_sets)]
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.mem_reads = 0
        self.mem_writes = 0

    @property
    def accesses(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        """ヒット率（アクセスがまだなければ 0.0）。"""
        return self.hits / self.accesses if self.accesses else 0.0

    def contains(self, addr: int) -> bool:
        """addr を含むラインが今キャッシュに入っているかを返す（統計や LRU の順序は変えない）。"""
        raise NotImplementedError("演習2: Cache.contains を実装してください")

    def access(self, addr: int, write: bool = False) -> bool:
        """addr へのアクセスを 1 回処理し、ヒットなら True、ミスなら False を返す。

        演習2（読み込みと、既定の設定での書き込み）:
            - ヒット: hits を 1 増やし、そのラインを「最も最近使った」ことにする。
            - ミス: misses を 1 増やし、ラインを読み込む（mem_reads += line_size）。
              セットが満杯（ways 本）なら、最も長く使われていないライン（LRU）を追い出し、evictions を 1 増やす。
            - addr が負なら ValueError。

        演習4（書き込み方式。既定は write_policy="write-back", write_allocate=True）:
            - ライトバック（write-back）: 書き込みはキャッシュ内のラインだけを更新し、ラインを dirty にする。
              dirty なラインを追い出すときに、ライン全体を書き戻す（mem_writes += line_size）。
            - ライトスルー（write-through）: 書き込みのたびにメモリにも書く（mem_writes += word_size）。
              ラインが dirty になることはない。
            - ライトアロケート（write_allocate=True）: 書き込みミスでもラインを読み込んで確保し、そこに書く。
            - ノーライトアロケート（write_allocate=False）: 書き込みミスではラインを確保せず、
              メモリに直接書く（mem_writes += word_size）。ミスとして数える。

        ヒント: 読み込みミスとライトアロケートの書き込みミスは、どちらも「ラインを確保する」処理を共有できる。
        """
        raise NotImplementedError("演習2: Cache.access を実装してください")

    def flush(self) -> None:
        """dirty なラインをすべてメモリへ書き戻し（1 本ごとに mem_writes += line_size）、dirty を解除する。

        ラインはキャッシュに残る（無効化はしない）。ヒット・ミスの統計は変えない。
        プログラムの終了時やデバイスへの転送の前に、キャッシュの内容をメモリへ反映させる操作にあたる。
        """
        raise NotImplementedError("演習4: Cache.flush を実装してください")


def replay(cache: Cache, trace: Iterable[Access]) -> float:
    """トレースを順にキャッシュへ流し、ヒット率を返す（用意済み）。

    トレースの要素は、番地（int。読み込み）か、(番地, 書き込みなら True) の組。
    """
    for item in trace:
        if isinstance(item, tuple):
            addr, is_write = item
            cache.access(addr, write=is_write)
        else:
            cache.access(item)
    return cache.hit_rate


# ---------------------------------------------------------------------------
# 演習3（★★★）: アクセスパターン（トレース）の生成
# ---------------------------------------------------------------------------
# 行列 a（rows 行 × cols 列、1 要素 elem_size バイト）は、C や NumPy の既定と同じく「行優先」で
# メモリに置かれているとする。a[i][j] の番地 = base + (i * cols + j) * elem_size。

def row_major_trace(rows: int, cols: int, elem_size: int = 8, base: int = 0) -> list[int]:
    """a[i][j] を「i を外側、j を内側」のループでたどったときの番地の列（メモリ上の順番どおり）。

    >>> row_major_trace(2, 3, elem_size=8)
    [0, 8, 16, 24, 32, 40]
    """
    raise NotImplementedError("演習3: row_major_trace を実装してください")


def column_major_trace(rows: int, cols: int, elem_size: int = 8, base: int = 0) -> list[int]:
    """同じ行列を「j を外側、i を内側」のループでたどったときの番地の列（cols × elem_size バイトおきに飛ぶ）。

    >>> column_major_trace(2, 3, elem_size=8)
    [0, 24, 8, 32, 16, 40]
    """
    raise NotImplementedError("演習3: column_major_trace を実装してください")


def transpose_naive_trace(
    n: int, elem_size: int = 8, src: int = 0, dst: Optional[int] = None
) -> list[tuple[int, bool]]:
    """n × n 行列の素朴な転置 dst[j][i] = src[i][j] のアクセスの列を返す。

    ループは「for i in range(n): for j in range(n):」で、各 (i, j) について
    (src[i][j] の番地, False)（読み込み）、(dst[j][i] の番地, True)（書き込み）の順に 2 つ追加する。
    dst を省略したときは、src の直後（src + n * n * elem_size）に置かれているとする。

    >>> transpose_naive_trace(2, elem_size=1)       # src は 0〜3 番地、dst は 4〜7 番地
    [(0, False), (4, True), (1, False), (6, True), (2, False), (5, True), (3, False), (7, True)]
    """
    raise NotImplementedError("演習3: transpose_naive_trace を実装してください")


def transpose_blocked_trace(
    n: int, block: int, elem_size: int = 8, src: int = 0, dst: Optional[int] = None
) -> list[tuple[int, bool]]:
    """block × block のタイルごとに転置する（ブロック化、タイリング）ときのアクセスの列を返す。

    ループの順番（n が block で割り切れなくてもよい。はみ出す部分は min で切る）:

        for ii in range(0, n, block):
            for jj in range(0, n, block):
                for i in range(ii, min(ii + block, n)):
                    for j in range(jj, min(jj + block, n)):
                        src[i][j] を読み、dst[j][i] に書く（素朴な版と同じく 2 つ追加）

    - block <= 0 なら ValueError。
    - 素朴な版とアクセスの「集合」は同じで、順番だけが違う。

    ヒント: キャッシュの大きさに合ったタイルなら、タイルの読み書きに使うラインがキャッシュに収まり、
    読み込んだラインを追い出される前に使い切れる。テストでヒット率が上がることを確かめる。
    """
    raise NotImplementedError("演習3: transpose_blocked_trace を実装してください")
