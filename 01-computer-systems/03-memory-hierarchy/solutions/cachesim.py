"""1.3 メモリ階層とキャッシュ — 解答例: キャッシュシミュレータ

仕様は exercises/cachesim.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Iterable, Optional, Union

Access = Union[int, tuple[int, bool]]

WRITE_POLICIES = ("write-back", "write-through")


def _is_power_of_two(x: int) -> bool:
    return x > 0 and x & (x - 1) == 0


# ---------------------------------------------------------------------------
# 演習1: アドレスの分解
# ---------------------------------------------------------------------------

def cache_geometry(cache_size: int, line_size: int, ways: int) -> tuple[int, int, int]:
    if min(cache_size, line_size, ways) <= 0:
        raise ValueError("cache_size, line_size, ways は正の整数です")
    if not _is_power_of_two(line_size):
        raise ValueError(f"line_size は 2 のべき乗です: {line_size}")
    if cache_size % (line_size * ways) != 0:
        raise ValueError("cache_size は line_size × ways で割り切れる必要があります")
    num_sets = cache_size // (line_size * ways)
    if not _is_power_of_two(num_sets):
        raise ValueError(f"セット数は 2 のべき乗です: {num_sets}")
    # 2 のべき乗 x に対して x.bit_length() - 1 = log2(x)
    return num_sets, line_size.bit_length() - 1, num_sets.bit_length() - 1


def split_address(addr: int, cache_size: int, line_size: int, ways: int) -> tuple[int, int, int]:
    num_sets, offset_bits, index_bits = cache_geometry(cache_size, line_size, ways)
    if addr < 0:
        raise ValueError(f"アドレスは 0 以上です: {addr}")
    offset = addr & (line_size - 1)                 # 下位 offset_bits ビット: ライン内の位置
    index = (addr >> offset_bits) & (num_sets - 1)  # 次の index_bits ビット: どのセットか
    tag = addr >> (offset_bits + index_bits)        # 残りの上位ビット: セット内でラインを見分ける
    return tag, index, offset


# ---------------------------------------------------------------------------
# 演習2・4: セットアソシアティブ・キャッシュ（LRU）と書き込み方式
# ---------------------------------------------------------------------------

class Cache:
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
        self.word_size = word_size
        # セットごとに「タグ → dirty フラグ」の OrderedDict。先頭が最も古く使われた（LRU）ライン
        self.sets: list[OrderedDict[int, bool]] = [OrderedDict() for _ in range(self.num_sets)]
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.mem_reads = 0   # メモリから読んだバイト数
        self.mem_writes = 0  # メモリへ書いたバイト数

    @property
    def accesses(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        return self.hits / self.accesses if self.accesses else 0.0

    def _locate(self, addr: int) -> tuple[int, int]:
        if addr < 0:
            raise ValueError(f"アドレスは 0 以上です: {addr}")
        index = (addr >> self.offset_bits) & (self.num_sets - 1)
        tag = addr >> (self.offset_bits + self.index_bits)
        return tag, index

    def contains(self, addr: int) -> bool:
        tag, index = self._locate(addr)
        return tag in self.sets[index]

    def access(self, addr: int, write: bool = False) -> bool:
        tag, index = self._locate(addr)
        lines = self.sets[index]
        write_back = self.write_policy == "write-back"

        if tag in lines:  # ヒット
            self.hits += 1
            lines.move_to_end(tag)  # 最も最近使ったライン（MRU）にする
            if write:
                if write_back:
                    lines[tag] = True  # dirty にしておき、追い出すときにまとめて書き戻す
                else:
                    self.mem_writes += self.word_size  # ライトスルー: 毎回メモリにも書く
            return True

        self.misses += 1
        if write and not self.write_allocate:
            # 書き込みミスでラインを確保しない方式: メモリに直接書くだけ
            self.mem_writes += self.word_size
            return False

        if len(lines) >= self.ways:  # セットが満杯なら LRU のラインを追い出す
            _, dirty = lines.popitem(last=False)
            self.evictions += 1
            if dirty:
                self.mem_writes += self.line_size  # 変更済みのラインだけ書き戻す
        self.mem_reads += self.line_size  # ライン全体をメモリから読み込む
        lines[tag] = write and write_back
        if write and not write_back:
            self.mem_writes += self.word_size
        return False

    def flush(self) -> None:
        for lines in self.sets:
            for tag, dirty in lines.items():
                if dirty:
                    self.mem_writes += self.line_size
                    lines[tag] = False


def replay(cache: Cache, trace: Iterable[Access]) -> float:
    """トレースを順にキャッシュへ流し、ヒット率を返す（用意済み）。"""
    for item in trace:
        if isinstance(item, tuple):
            addr, is_write = item
            cache.access(addr, write=is_write)
        else:
            cache.access(item)
    return cache.hit_rate


# ---------------------------------------------------------------------------
# 演習3: アクセスパターン（トレース）の生成
# ---------------------------------------------------------------------------

def row_major_trace(rows: int, cols: int, elem_size: int = 8, base: int = 0) -> list[int]:
    # 行優先で格納された a[i][j] の番地は base + (i * cols + j) * elem_size
    return [base + (i * cols + j) * elem_size for i in range(rows) for j in range(cols)]


def column_major_trace(rows: int, cols: int, elem_size: int = 8, base: int = 0) -> list[int]:
    # 格納は行優先のまま、j（列）を外側のループにしてたどる
    return [base + (i * cols + j) * elem_size for j in range(cols) for i in range(rows)]


def _dst_base(n: int, elem_size: int, src: int, dst: Optional[int]) -> int:
    return src + n * n * elem_size if dst is None else dst


def transpose_naive_trace(
    n: int, elem_size: int = 8, src: int = 0, dst: Optional[int] = None
) -> list[tuple[int, bool]]:
    dst = _dst_base(n, elem_size, src, dst)
    trace: list[tuple[int, bool]] = []
    for i in range(n):
        for j in range(n):
            trace.append((src + (i * n + j) * elem_size, False))  # src[i][j] を読む（連続）
            trace.append((dst + (j * n + i) * elem_size, True))   # dst[j][i] に書く（n 要素おき）
    return trace


def transpose_blocked_trace(
    n: int, block: int, elem_size: int = 8, src: int = 0, dst: Optional[int] = None
) -> list[tuple[int, bool]]:
    if block <= 0:
        raise ValueError(f"block は正の整数です: {block}")
    dst = _dst_base(n, elem_size, src, dst)
    trace: list[tuple[int, bool]] = []
    # block × block のタイルごとに転置する。タイルの読み書きに使うラインがキャッシュに収まれば、
    # 一度読み込んだラインを追い出される前に使い切れる
    for ii in range(0, n, block):
        for jj in range(0, n, block):
            for i in range(ii, min(ii + block, n)):
                for j in range(jj, min(jj + block, n)):
                    trace.append((src + (i * n + j) * elem_size, False))
                    trace.append((dst + (j * n + i) * elem_size, True))
    return trace
