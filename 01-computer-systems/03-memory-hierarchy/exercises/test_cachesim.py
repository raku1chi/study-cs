"""1.3 メモリ階層とキャッシュ — テスト

実行: python3 tools/check.py 1.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from cachesim import (
    Cache,
    cache_geometry,
    column_major_trace,
    replay,
    row_major_trace,
    split_address,
    transpose_blocked_trace,
    transpose_naive_trace,
)

KiB = 1024


class TestExercise1Address(unittest.TestCase):
    def test_geometry_examples(self):
        self.assertEqual(cache_geometry(32 * KiB, 64, 8), (64, 6, 6))
        self.assertEqual(cache_geometry(48 * KiB, 64, 12), (64, 6, 6))
        self.assertEqual(cache_geometry(2 * KiB * KiB, 64, 16), (2048, 6, 11))
        self.assertEqual(cache_geometry(1 * KiB, 16, 1), (64, 4, 6))       # ダイレクトマップ
        self.assertEqual(cache_geometry(1 * KiB, 16, 64), (1, 4, 0))       # フルアソシアティブ

    def test_geometry_invalid(self):
        for args in [(0, 64, 8), (32 * KiB, 48, 8), (32 * KiB, 64, 0), (1000, 64, 1), (48 * KiB, 64, 8)]:
            with self.assertRaises(ValueError, msg=str(args)):
                cache_geometry(*args)

    def test_split_examples(self):
        self.assertEqual(split_address(0x12345, 32 * KiB, 64, 8), (18, 13, 5))
        self.assertEqual(split_address(0, 32 * KiB, 64, 8), (0, 0, 0))
        self.assertEqual(split_address(63, 32 * KiB, 64, 8), (0, 0, 63))
        self.assertEqual(split_address(64, 32 * KiB, 64, 8), (0, 1, 0))
        self.assertEqual(split_address(4096, 32 * KiB, 64, 8), (1, 0, 0), "4 KiB 離れると同じセットに戻る")

    def test_fully_associative_has_no_index(self):
        self.assertEqual(split_address(0x12345, 1 * KiB, 16, 64), (0x1234, 0, 5))

    def test_split_recombines(self):
        rng = random.Random(1)
        for _ in range(300):
            addr = rng.getrandbits(48)
            tag, index, offset = split_address(addr, 48 * KiB, 64, 12)
            self.assertEqual((tag << 12) | (index << 6) | offset, addr)
            self.assertLess(index, 64)
            self.assertLess(offset, 64)

    def test_negative_address(self):
        with self.assertRaises(ValueError):
            split_address(-1, 32 * KiB, 64, 8)


class TestExercise2Cache(unittest.TestCase):
    def test_first_access_misses_then_hits_within_line(self):
        c = Cache(1 * KiB, 64, 2)
        self.assertFalse(c.access(100))
        self.assertTrue(c.access(64), "同じライン（64〜127 番地）はヒット")
        self.assertTrue(c.access(127))
        self.assertFalse(c.access(128), "次のラインはミス")
        self.assertEqual((c.hits, c.misses, c.accesses), (2, 2, 4))
        self.assertAlmostEqual(c.hit_rate, 0.5)
        self.assertEqual(c.mem_reads, 2 * 64)

    def test_hit_rate_before_any_access(self):
        self.assertEqual(Cache(1 * KiB, 64, 1).hit_rate, 0.0)

    def test_direct_mapped_conflict(self):
        # 256 バイト、16 バイトのライン、ダイレクトマップ → 16 セット。256 バイト離れた番地は同じセット
        c = Cache(256, 16, 1)
        pattern = [0, 256, 0, 256, 0, 256]
        self.assertEqual([c.access(a) for a in pattern], [False] * 6, "交互に追い出し合う（競合ミス）")
        self.assertEqual(c.evictions, 5)

    def test_two_way_absorbs_the_same_conflict(self):
        c = Cache(256, 16, 2)
        pattern = [0, 256, 0, 256, 0, 256]
        self.assertEqual([c.access(a) for a in pattern], [False, False, True, True, True, True])
        self.assertEqual(c.evictions, 0)

    def test_lru_evicts_least_recently_used(self):
        c = Cache(256, 16, 2)       # 8 セット × 2 ウェイ。0, 128, 256 は同じセット
        c.access(0)
        c.access(128)
        c.access(0)                 # 0 を使ったので、LRU は 128
        c.access(256)               # 128 が追い出される
        self.assertTrue(c.contains(0))
        self.assertFalse(c.contains(128))
        self.assertTrue(c.contains(256))
        self.assertEqual(c.evictions, 1)

    def test_contains_does_not_change_state(self):
        c = Cache(256, 16, 2)
        c.access(0)
        c.access(128)
        self.assertTrue(c.contains(0))   # contains は LRU の順序を変えない
        c.access(256)                    # LRU の 0 が追い出されるはず
        self.assertFalse(c.contains(0))
        self.assertEqual(c.accesses, 3)

    def test_fully_associative_lru(self):
        c = Cache(64, 16, 4)        # 1 セット × 4 ウェイ
        for a in (0, 16, 32, 48):
            c.access(a)
        c.access(0)                 # 0 を最近使ったことにする
        c.access(1000)              # LRU の 16 が追い出される
        self.assertEqual([c.contains(a) for a in (0, 16, 32, 48, 1000)], [True, False, True, True, True])

    def test_matches_reference_lru_on_random_traces(self):
        rng = random.Random(2)
        for cache_size, line, ways in [(1 * KiB, 32, 1), (1 * KiB, 32, 4), (2 * KiB, 64, 8), (512, 16, 32)]:
            c = Cache(cache_size, line, ways)
            ref = ReferenceLRU(cache_size, line, ways)
            for _ in range(3000):
                addr = rng.randrange(8 * cache_size)
                self.assertEqual(c.access(addr), ref.access(addr), (cache_size, line, ways, addr))
            self.assertEqual((c.hits, c.misses, c.evictions), (ref.hits, ref.misses, ref.evictions))

    def test_negative_address(self):
        with self.assertRaises(ValueError):
            Cache(1 * KiB, 64, 1).access(-8)


class ReferenceLRU:
    """答え合わせ用: リストで素直に書いた LRU キャッシュ（読み込みのみ）。"""

    def __init__(self, cache_size, line, ways):
        self.line, self.ways = line, ways
        self.num_sets = cache_size // (line * ways)
        self.sets = [[] for _ in range(self.num_sets)]  # 末尾が最近使ったライン
        self.hits = self.misses = self.evictions = 0

    def access(self, addr):
        block = addr // self.line
        s = self.sets[block % self.num_sets]
        if block in s:
            s.remove(block)
            s.append(block)
            self.hits += 1
            return True
        self.misses += 1
        if len(s) == self.ways:
            s.pop(0)
            self.evictions += 1
        s.append(block)
        return False


class TestExercise3Traces(unittest.TestCase):
    def test_row_and_column_examples(self):
        self.assertEqual(row_major_trace(2, 3, elem_size=8), [0, 8, 16, 24, 32, 40])
        self.assertEqual(column_major_trace(2, 3, elem_size=8), [0, 24, 8, 32, 16, 40])
        self.assertEqual(row_major_trace(1, 2, elem_size=4, base=1000), [1000, 1004])
        self.assertEqual(column_major_trace(3, 1, elem_size=4, base=100), [100, 104, 108])

    def test_same_addresses_different_order(self):
        r, c = row_major_trace(7, 5, 8, 64), column_major_trace(7, 5, 8, 64)
        self.assertEqual(len(r), 35)
        self.assertEqual(sorted(r), sorted(c))
        self.assertNotEqual(r, c)

    def test_row_major_is_cache_friendly(self):
        # 256 × 256 の double（8 バイト）を、32 KiB・8 ウェイ・64 バイトのライン（典型的な L1）で
        row = replay(Cache(32 * KiB, 64, 8), row_major_trace(256, 256))
        col = replay(Cache(32 * KiB, 64, 8), column_major_trace(256, 256))
        self.assertAlmostEqual(row, 7 / 8, msg="1 ラインに 8 要素: 1 回ミスして 7 回ヒット")
        self.assertLess(col, 0.05, "列ごとにたどると、ラインを使い切る前に追い出される")

    def test_transpose_naive_example(self):
        self.assertEqual(
            transpose_naive_trace(2, elem_size=1),
            [(0, False), (4, True), (1, False), (6, True), (2, False), (5, True), (3, False), (7, True)],
        )
        self.assertEqual(transpose_naive_trace(1, elem_size=8, src=100, dst=500), [(100, False), (500, True)])

    def test_transpose_blocked_example(self):
        # 4 × 4、block=2: 左上のタイル (0..1, 0..1) から順に処理する
        trace = transpose_blocked_trace(4, 2, elem_size=1)
        reads = [addr for addr, is_write in trace if not is_write]
        self.assertEqual(reads, [0, 1, 4, 5, 2, 3, 6, 7, 8, 9, 12, 13, 10, 11, 14, 15])
        writes = [addr for addr, is_write in trace if is_write]
        self.assertEqual(writes[:4], [16, 20, 17, 21])

    def test_blocked_is_a_permutation_of_naive(self):
        for n, block in [(5, 2), (8, 3), (6, 6), (4, 10)]:
            naive = transpose_naive_trace(n)
            blocked = transpose_blocked_trace(n, block)
            self.assertEqual(sorted(blocked), sorted(naive), (n, block))
            self.assertEqual(len(blocked), 2 * n * n)

    def test_block_equal_to_n_is_naive(self):
        self.assertEqual(transpose_blocked_trace(6, 6), transpose_naive_trace(6))

    def test_blocking_improves_hit_rate(self):
        n = 128
        naive = replay(Cache(32 * KiB, 64, 8), transpose_naive_trace(n))
        blocked = replay(Cache(32 * KiB, 64, 8), transpose_blocked_trace(n, 8))
        self.assertLess(naive, 0.5, "素朴な転置では書き込みが毎回ミスする")
        self.assertGreater(blocked, 0.85, "8 × 8 のタイルなら読み書きともにラインを使い切れる")

    def test_invalid_block(self):
        with self.assertRaises(ValueError):
            transpose_blocked_trace(4, 0)


class TestExercise4WritePolicies(unittest.TestCase):
    def test_write_back_defers_writes(self):
        c = Cache(1 * KiB, 64, 2)                      # 既定: ライトバック + ライトアロケート
        for _ in range(100):
            c.access(0, write=True)                    # 同じ語に 100 回書く
        self.assertEqual(c.mem_writes, 0, "dirty なラインはキャッシュの中にあるだけ")
        self.assertEqual(c.mem_reads, 64, "最初の書き込みミスでラインを読み込む（ライトアロケート）")
        c.flush()
        self.assertEqual(c.mem_writes, 64, "flush でライン 1 本を書き戻す")
        c.flush()
        self.assertEqual(c.mem_writes, 64, "書き戻した後は dirty ではない")
        self.assertTrue(c.contains(0), "flush してもラインは残る")
        self.assertEqual((c.hits, c.misses), (99, 1))

    def test_write_through_writes_every_time(self):
        c = Cache(1 * KiB, 64, 2, write_policy="write-through")
        for _ in range(100):
            c.access(0, write=True)
        self.assertEqual(c.mem_writes, 100 * 8)
        c.flush()
        self.assertEqual(c.mem_writes, 100 * 8, "ライトスルーのラインは dirty にならない")

    def test_dirty_eviction_writes_back_line(self):
        c = Cache(128, 64, 1)                          # 2 セットのダイレクトマップ
        c.access(0, write=True)                        # ライン 0 を dirty に
        c.access(128)                                  # 同じセット → dirty なラインを追い出す
        self.assertEqual(c.mem_writes, 64)
        c.access(256)                                  # 追い出されるのは clean なライン → 書き戻しなし
        self.assertEqual(c.mem_writes, 64)
        self.assertEqual(c.mem_reads, 3 * 64)
        self.assertEqual(c.evictions, 2)

    def test_no_write_allocate(self):
        c = Cache(1 * KiB, 64, 2, write_policy="write-through", write_allocate=False)
        self.assertFalse(c.access(0, write=True))
        self.assertFalse(c.contains(0), "書き込みミスではラインを確保しない")
        self.assertEqual((c.mem_reads, c.mem_writes), (0, 8))
        self.assertFalse(c.access(0), "読み込みではラインを確保する")
        self.assertTrue(c.access(0, write=True), "確保済みなら書き込みはヒット")
        self.assertEqual((c.mem_reads, c.mem_writes), (64, 16))

    def test_write_back_no_write_allocate(self):
        c = Cache(1 * KiB, 64, 2, write_allocate=False)
        c.access(0, write=True)                         # ミス → メモリへ直接
        self.assertEqual((c.mem_reads, c.mem_writes), (0, 8))
        c.access(0)                                     # 読み込みで確保
        c.access(0, write=True)                         # ヒット → dirty に
        c.flush()
        self.assertEqual((c.mem_reads, c.mem_writes), (64, 8 + 64))

    def test_write_back_saves_traffic_on_repeated_updates(self):
        # 同じ小さな配列を何度も更新するループ（カウンタの配列など）
        trace = [(i * 8 % 512, True) for i in range(10_000)]
        wb = Cache(4 * KiB, 64, 4)
        wt = Cache(4 * KiB, 64, 4, write_policy="write-through")
        replay(wb, trace)
        replay(wt, trace)
        wb.flush()
        self.assertEqual(wb.mem_writes, 512, "最後に 8 ライン分を書き戻すだけ")
        self.assertEqual(wt.mem_writes, 10_000 * 8)

    def test_invalid_policy(self):
        with self.assertRaises(ValueError):
            Cache(1 * KiB, 64, 2, write_policy="write-around")


if __name__ == "__main__":
    unittest.main()
