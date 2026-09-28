"""3.3 メモリ管理とランタイム — 演習2: フリーリスト方式のメモリアロケータ

bytearray を「ヒープ領域」に見立てて、C の malloc / free に相当するものを実装します。
各ブロックの先頭には 8 バイトのヘッダを置き、そこにブロックの大きさと状態を書き込みます
（実際の malloc の実装も、同じようにヒープの中に管理情報を置いています）。

    ブロック = [ヘッダ 8 バイト][ペイロード（利用者が使う領域）]
                ^                ^
                addr             malloc が返すアドレス = addr + HEADER_SIZE

    ヘッダ: struct "<II" = (ブロックの大きさ（ヘッダ込み・バイト）, マジックナンバー)
            マジックナンバーは使用中なら MAGIC_USED、空きなら MAGIC_FREE

ヒープは先頭から隙間なくブロックが並んでいる。ヘッダの大きさを足していけば次のブロックに
たどり着ける（暗黙のフリーリスト, implicit free list）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_allocator
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 8  # ヘッダの大きさ（バイト）
ALIGN = 8  # ブロックの大きさは 8 の倍数（アラインメント）
MIN_BLOCK = 16  # ブロックの最小サイズ（ヘッダ 8 ＋ ペイロード 8）
MAGIC_USED = 0xA110C8ED
MAGIC_FREE = 0xF7EEB10C
_HEADER = struct.Struct("<II")  # (ブロックの大きさ, 状態を表すマジックナンバー)


class AllocatorError(Exception):
    """アロケータの使い方の誤り、またはヒープの破損（与えられたもの）。"""


class DoubleFreeError(AllocatorError):
    """解放済みのブロックをもう一度 free した（与えられたもの）。"""


class InvalidPointerError(AllocatorError):
    """malloc が返していないアドレスを free した（与えられたもの）。"""


class HeapCorruptionError(AllocatorError):
    """ブロックのヘッダが壊れている（バッファオーバーフローなどで上書きされた）（与えられたもの）。"""


@dataclass(frozen=True)
class Block:
    """ヒープ上の 1 つのブロック（与えられたもの）。addr はヘッダの位置、size はヘッダ込みの大きさ。"""

    addr: int
    size: int
    used: bool


@dataclass(frozen=True)
class HeapStats:
    """ヒープの統計（与えられたもの）。大きさはすべてヘッダ込みのバイト数。"""

    total: int  # ヒープ全体の大きさ
    used: int  # 使用中ブロックの合計
    free: int  # 空きブロックの合計
    free_blocks: int  # 空きブロックの数
    largest_free: int  # 最大の空きブロックの大きさ（空きがなければ 0）

    @property
    def fragmentation(self) -> float:
        """外部断片化の指標: 1 - 最大の空きブロック / 空きの合計（空きがなければ 0.0）。

        0 なら空きが 1 か所にまとまっている。1 に近いほど、空きが細かく散らばっていて、
        合計は十分でも大きな要求に応えられない状態。
        """
        return 0.0 if self.free == 0 else 1 - self.largest_free / self.free


def align_up(n: int, align: int = ALIGN) -> int:
    """n 以上で最小の align の倍数（与えられたもの）。align_up(17) == 24"""
    return (n + align - 1) // align * align


class FreeListAllocator:
    """フリーリスト方式のアロケータ。strategy は "first_fit" か "best_fit"。

    >>> a = FreeListAllocator(256)
    >>> p = a.malloc(10)            # ヘッダ 8 ＋ 10 → 8 の倍数に切り上げて 24 バイトのブロック
    >>> p
    8
    >>> a.blocks()
    [Block(addr=0, size=24, used=True), Block(addr=24, size=232, used=False)]
    >>> a.free(p)
    >>> a.blocks()
    [Block(addr=0, size=256, used=False)]
    """

    def __init__(self, size: int, strategy: str = "first_fit") -> None:
        """ヒープ全体を 1 つの空きブロックとして初期化する（与えられたもの）。"""
        if size < MIN_BLOCK or size % ALIGN != 0:
            raise ValueError(f"size は {ALIGN} の倍数で {MIN_BLOCK} 以上: {size}")
        if strategy not in ("first_fit", "best_fit"):
            raise ValueError(f"strategy は first_fit か best_fit: {strategy!r}")
        self.size = size
        self.strategy = strategy
        self.memory = bytearray(size)
        self._write_header(0, size, MAGIC_FREE)

    # ---- 与えられたもの ----
    def _write_header(self, addr: int, size: int, magic: int) -> None:
        """addr にヘッダ (size, magic) を書き込む。"""
        _HEADER.pack_into(self.memory, addr, size, magic)

    def _read_header(self, addr: int) -> tuple[int, int]:
        """addr のヘッダを (size, magic) として読む。"""
        return _HEADER.unpack_from(self.memory, addr)

    # ---- 演習 ----
    def blocks(self) -> list[Block]:
        """アドレス 0 から、ヘッダの大きさをたどってヒープ全体を歩き、ブロックのリストを返す。

        次のいずれかに当てはまるヘッダを見つけたら HeapCorruptionError（ヒープが壊れている）:
        - マジックナンバーが MAGIC_USED でも MAGIC_FREE でもない
        - 大きさが MIN_BLOCK 未満、または ALIGN の倍数でない
        - ブロックがヒープの末尾を越える
        """
        raise NotImplementedError("演習2: FreeListAllocator.blocks を実装してください")

    def malloc(self, n: int) -> int:
        """n バイトのペイロードを持つブロックを確保し、ペイロードの先頭アドレスを返す。

        1. 必要なブロックの大きさ need = max(align_up(n + HEADER_SIZE), MIN_BLOCK)。
        2. need 以上の大きさの空きブロックを選ぶ。
           - first_fit: アドレスの小さい順に見て、最初に見つかったもの
           - best_fit: 大きさが最小のもの（同じ大きさならアドレスの小さいもの）
        3. 選んだブロックの残り（size - need）が MIN_BLOCK 以上なら分割し、前半を使用中、
           後半を新しい空きブロックにする。MIN_BLOCK 未満なら分割せず、ブロック全体を使用中にする。
        4. ブロックの先頭アドレス + HEADER_SIZE を返す。

        - n が 1 以上の int でなければ ValueError。
        - 条件を満たす空きブロックがなければ MemoryError（空きの合計が足りていても、連続して
          いなければ確保できない。これが外部断片化）。
        """
        raise NotImplementedError("演習2: FreeListAllocator.malloc を実装してください")

    def free(self, ptr: int) -> None:
        """malloc が返したアドレス ptr のブロックを解放し、隣接する空きブロックと結合する。

        - ptr - HEADER_SIZE がブロックの先頭（blocks() に現れる addr）でなければ InvalidPointerError。
        - そのブロックがすでに空きなら DoubleFreeError。
        - 解放後、隣り合う空きブロックはすべて 1 つにまとめること（blocks() に空きブロックが
          2 つ続けて現れてはいけない）。
        - ヘッダが壊れていれば HeapCorruptionError（blocks() が検出する）。
        """
        raise NotImplementedError("演習2: FreeListAllocator.free を実装してください")

    def stats(self) -> HeapStats:
        """現在のヒープの統計を返す。"""
        raise NotImplementedError("演習2: FreeListAllocator.stats を実装してください")
