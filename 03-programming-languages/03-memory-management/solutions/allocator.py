"""3.3 メモリ管理とランタイム — フリーリスト方式のメモリアロケータ（解答例）

演習の仕様は exercises/allocator.py の docstring を参照してください。
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

HEADER_SIZE = 8
ALIGN = 8
MIN_BLOCK = 16
MAGIC_USED = 0xA110C8ED
MAGIC_FREE = 0xF7EEB10C
_HEADER = struct.Struct("<II")  # (ブロックの大きさ, 状態を表すマジックナンバー)


class AllocatorError(Exception):
    """アロケータの使い方の誤り、またはヒープの破損。"""


class DoubleFreeError(AllocatorError):
    """解放済みのブロックをもう一度 free した。"""


class InvalidPointerError(AllocatorError):
    """malloc が返していないアドレスを free した。"""


class HeapCorruptionError(AllocatorError):
    """ブロックのヘッダが壊れている（バッファオーバーフローなどで上書きされた）。"""


@dataclass(frozen=True)
class Block:
    addr: int
    size: int
    used: bool


@dataclass(frozen=True)
class HeapStats:
    total: int
    used: int
    free: int
    free_blocks: int
    largest_free: int

    @property
    def fragmentation(self) -> float:
        return 0.0 if self.free == 0 else 1 - self.largest_free / self.free


def align_up(n: int, align: int = ALIGN) -> int:
    return (n + align - 1) // align * align


class FreeListAllocator:
    def __init__(self, size: int, strategy: str = "first_fit") -> None:
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
        _HEADER.pack_into(self.memory, addr, size, magic)

    def _read_header(self, addr: int) -> tuple[int, int]:
        return _HEADER.unpack_from(self.memory, addr)

    # ---- 演習 ----
    def blocks(self) -> list[Block]:
        result: list[Block] = []
        addr = 0
        # ヘッダに書かれた大きさで次のブロックへ飛びながら、ヒープ全体を歩く（暗黙のフリーリスト）
        while addr < self.size:
            size, magic = self._read_header(addr)
            if (
                magic not in (MAGIC_USED, MAGIC_FREE)
                or size < MIN_BLOCK
                or size % ALIGN != 0
                or addr + size > self.size
            ):
                raise HeapCorruptionError(
                    f"アドレス {addr} のヘッダが壊れています（size={size}, magic={magic:#010x}）"
                )
            result.append(Block(addr, size, magic == MAGIC_USED))
            addr += size
        return result

    def malloc(self, n: int) -> int:
        if type(n) is not int or n < 1:
            raise ValueError(f"n は 1 以上の整数: {n!r}")
        need = max(align_up(n + HEADER_SIZE), MIN_BLOCK)
        candidates = [b for b in self.blocks() if not b.used and b.size >= need]
        if not candidates:
            raise MemoryError(f"{n} バイトを確保できる連続した空きブロックがありません")
        if self.strategy == "first_fit":
            block = candidates[0]  # アドレス順で最初に見つかったもの
        else:
            block = min(candidates, key=lambda b: (b.size, b.addr))  # 最も小さく収まるもの
        if block.size - need >= MIN_BLOCK:
            # 分割: 前半を使用中に、残りを新しい空きブロックにする
            self._write_header(block.addr, need, MAGIC_USED)
            self._write_header(block.addr + need, block.size - need, MAGIC_FREE)
        else:
            # 残りが小さすぎてブロックにできないので、丸ごと渡す（内部断片化）
            self._write_header(block.addr, block.size, MAGIC_USED)
        return block.addr + HEADER_SIZE

    def free(self, ptr: int) -> None:
        addr = ptr - HEADER_SIZE if type(ptr) is int else -1
        target = next((b for b in self.blocks() if b.addr == addr), None)
        if target is None:
            raise InvalidPointerError(f"malloc が返したアドレスではありません: {ptr!r}")
        if not target.used:
            raise DoubleFreeError(f"すでに解放されています: {ptr}")
        self._write_header(target.addr, target.size, MAGIC_FREE)
        self._coalesce()

    def _coalesce(self) -> None:
        # 隣り合う空きブロックを 1 つにまとめる（結合しないと、小さな空きばかりが増える）
        merged: list[Block] = []
        for b in self.blocks():
            if merged and not merged[-1].used and not b.used:
                prev = merged.pop()
                merged.append(Block(prev.addr, prev.size + b.size, False))
            else:
                merged.append(b)
        for b in merged:
            if not b.used:
                self._write_header(b.addr, b.size, MAGIC_FREE)

    def stats(self) -> HeapStats:
        blocks = self.blocks()
        free_sizes = [b.size for b in blocks if not b.used]
        return HeapStats(
            total=self.size,
            used=sum(b.size for b in blocks if b.used),
            free=sum(free_sizes),
            free_blocks=len(free_sizes),
            largest_free=max(free_sizes, default=0),
        )
