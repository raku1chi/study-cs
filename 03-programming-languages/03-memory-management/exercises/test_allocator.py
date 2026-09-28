"""3.3 メモリ管理とランタイム — 演習2（フリーリスト方式のアロケータ）のテスト

実行: python3 tools/check.py 3.3   （またはこのディレクトリで python3 -m unittest -v test_allocator）
"""
import random
import unittest

from allocator import (
    ALIGN,
    HEADER_SIZE,
    MIN_BLOCK,
    Block,
    DoubleFreeError,
    FreeListAllocator,
    HeapCorruptionError,
    InvalidPointerError,
)


class TestExercise2Allocator(unittest.TestCase):
    def assertHeapInvariants(self, a):
        blocks = a.blocks()
        addr = 0
        for blk in blocks:
            self.assertEqual(blk.addr, addr, "ブロックは隙間なく並ぶ")
            self.assertEqual(blk.size % ALIGN, 0)
            self.assertGreaterEqual(blk.size, MIN_BLOCK)
            addr += blk.size
        self.assertEqual(addr, a.size, "ブロックの合計はヒープ全体の大きさ")
        for x, y in zip(blocks, blocks[1:]):
            self.assertFalse(not x.used and not y.used, "隣り合う空きブロックは結合されている")

    def test_initial_state(self):
        a = FreeListAllocator(256)
        self.assertEqual(a.blocks(), [Block(0, 256, False)])
        st = a.stats()
        self.assertEqual((st.total, st.used, st.free, st.free_blocks, st.largest_free), (256, 0, 256, 1, 256))
        self.assertEqual(st.fragmentation, 0.0)

    def test_malloc_splits_block(self):
        a = FreeListAllocator(256)
        p = a.malloc(10)
        self.assertEqual(p, HEADER_SIZE)
        self.assertEqual(a.blocks(), [Block(0, 24, True), Block(24, 232, False)])
        q = a.malloc(10)
        self.assertEqual(q, 24 + HEADER_SIZE)
        self.assertEqual(a.stats().used, 48)

    def test_block_sizes_are_aligned_with_minimum(self):
        cases = {1: 16, 8: 16, 9: 24, 16: 24, 17: 32, 56: 64}
        for n, expected in cases.items():
            a = FreeListAllocator(256)
            a.malloc(n)
            self.assertEqual(a.blocks()[0].size, expected, f"malloc({n})")

    def test_payloads_do_not_overlap(self):
        a = FreeListAllocator(512)
        allocations = []
        for i, n in enumerate([5, 17, 32, 1, 64, 23]):
            p = a.malloc(n)
            self.assertEqual(p % ALIGN, 0, "返すアドレスは 8 の倍数")
            a.memory[p:p + n] = bytes([i + 1]) * n
            allocations.append((p, n, i + 1))
        for p, n, v in allocations:
            self.assertEqual(bytes(a.memory[p:p + n]), bytes([v]) * n)
        self.assertHeapInvariants(a)

    def test_free_and_coalesce(self):
        a = FreeListAllocator(256)
        p1, p2, p3 = a.malloc(8), a.malloc(8), a.malloc(8)
        a.free(p2)
        self.assertEqual(a.blocks(), [Block(0, 16, True), Block(16, 16, False), Block(32, 16, True), Block(48, 208, False)])
        a.free(p1)  # 後ろの空きブロックと結合
        self.assertEqual(a.blocks()[:2], [Block(0, 32, False), Block(32, 16, True)])
        a.free(p3)  # 前後両方と結合
        self.assertEqual(a.blocks(), [Block(0, 256, False)])

    def _fragmented_heap(self, strategy):
        # A(64) B(16) C(32) D(16) 残り(128) を確保し、A と C を解放して穴を 2 つ作る
        a = FreeListAllocator(256, strategy)
        pa, pb, pc, pd = a.malloc(56), a.malloc(8), a.malloc(24), a.malloc(8)
        a.free(pa)
        a.free(pc)
        self.assertEqual(
            a.blocks(),
            [Block(0, 64, False), Block(64, 16, True), Block(80, 32, False), Block(112, 16, True), Block(128, 128, False)],
        )
        return a

    def test_first_fit(self):
        a = self._fragmented_heap("first_fit")
        p = a.malloc(20)  # 32 バイトのブロックが必要
        self.assertEqual(p, 0 + HEADER_SIZE, "アドレス順で最初に収まる穴（64 バイト）を使う")
        self.assertEqual(a.blocks()[:2], [Block(0, 32, True), Block(32, 32, False)])

    def test_best_fit(self):
        a = self._fragmented_heap("best_fit")
        p = a.malloc(20)
        self.assertEqual(p, 80 + HEADER_SIZE, "最も小さく収まる穴（32 バイト）を使う")
        self.assertEqual(a.blocks()[2], Block(80, 32, True))

    def test_no_split_when_remainder_too_small(self):
        a = FreeListAllocator(256)
        p1, p2, p3 = a.malloc(24), a.malloc(8), a.malloc(8)
        a.free(p1)  # 32 バイトの穴
        p = a.malloc(16)  # 24 バイト必要。残り 8 バイトではブロックを作れない
        self.assertEqual(p, p1)
        self.assertEqual(a.blocks()[0], Block(0, 32, True), "ブロック全体を渡す（内部断片化）")

    def test_external_fragmentation(self):
        a = FreeListAllocator(1024)
        ptrs = [a.malloc(56) for _ in range(16)]  # 64 バイト × 16 で満杯
        with self.assertRaises(MemoryError):
            a.malloc(1)
        for p in ptrs[::2]:
            a.free(p)
        st = a.stats()
        self.assertEqual((st.free, st.free_blocks, st.largest_free), (512, 8, 64))
        self.assertAlmostEqual(st.fragmentation, 1 - 64 / 512)
        with self.assertRaises(MemoryError):
            a.malloc(100)  # 空きの合計は 512 バイトあるのに、連続した 112 バイトがない
        for p in ptrs[1::2]:
            a.free(p)
        self.assertEqual(a.stats().fragmentation, 0.0)
        self.assertIsInstance(a.malloc(1000), int)

    def test_double_free(self):
        a = FreeListAllocator(256)
        p = a.malloc(16)
        a.malloc(16)
        a.free(p)
        with self.assertRaises(DoubleFreeError):
            a.free(p)

    def test_invalid_pointers(self):
        a = FreeListAllocator(256)
        p = a.malloc(32)
        for bad in (p + 8, p - 1, 0, 3, 10_000, -8):
            with self.assertRaises(InvalidPointerError, msg=str(bad)):
                a.free(bad)
        a.free(p)  # 正しいポインタは解放できる

    def test_buffer_overflow_corrupts_heap(self):
        a = FreeListAllocator(256)
        p = a.malloc(16)  # ブロック [0, 24)。ペイロードは [8, 24)
        q = a.malloc(16)  # ブロック [24, 48)。ヘッダは [24, 32)
        a.memory[p:p + 24] = b"A" * 24  # 16 バイトの領域に 24 バイト書く（オーバーフロー）
        with self.assertRaises(HeapCorruptionError):
            a.free(q)
        with self.assertRaises(HeapCorruptionError):
            a.blocks()
        with self.assertRaises(HeapCorruptionError):
            a.malloc(8)

    def test_bad_sizes_in_header_are_detected(self):
        a = FreeListAllocator(64)
        a._write_header(0, 1000, 0xF7EEB10C)  # ヒープの末尾を越える大きさ
        with self.assertRaises(HeapCorruptionError):
            a.blocks()
        a._write_header(0, 12, 0xF7EEB10C)  # 8 の倍数でない
        with self.assertRaises(HeapCorruptionError):
            a.blocks()

    def test_invalid_requests(self):
        a = FreeListAllocator(64)
        for bad in (0, -1, 1.5, "8"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                a.malloc(bad)
        with self.assertRaises(MemoryError):
            a.malloc(64)  # ヘッダの分だけ足りない
        self.assertEqual(a.malloc(56), HEADER_SIZE)

    def test_constructor_validation(self):
        for size in (8, 100, 0):
            with self.assertRaises(ValueError):
                FreeListAllocator(size)
        with self.assertRaises(ValueError):
            FreeListAllocator(64, "worst_fit")

    def test_random_stress(self):
        for strategy in ("first_fit", "best_fit"):
            rng = random.Random(35)
            a = FreeListAllocator(4096, strategy)
            live = {}  # ptr -> (n, 埋めたバイト値)
            for step in range(1500):
                if live and (rng.random() < 0.45 or len(live) > 40):
                    p = rng.choice(list(live))
                    n, v = live.pop(p)
                    self.assertEqual(bytes(a.memory[p:p + n]), bytes([v]) * n, "他の確保で上書きされていない")
                    a.free(p)
                else:
                    n = rng.randrange(1, 200)
                    try:
                        p = a.malloc(n)
                    except MemoryError:
                        continue
                    v = step % 251 + 1
                    a.memory[p:p + n] = bytes([v]) * n
                    live[p] = (n, v)
                if step % 50 == 0:
                    self.assertHeapInvariants(a)
                    st = a.stats()
                    self.assertEqual(st.used + st.free, st.total)
            for p in list(live):
                a.free(p)
            self.assertEqual(a.blocks(), [Block(0, 4096, False)])


if __name__ == "__main__":
    unittest.main()
