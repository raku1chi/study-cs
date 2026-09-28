"""4.2 仮想メモリ — テスト

実行: python3 tools/check.py 4.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from vmsim import (
    MMU,
    TLB,
    CowMemory,
    PageFault,
    ProtectionFault,
    TwoLevelPageTable,
    simulate_clock,
    simulate_fifo,
    simulate_lru,
    simulate_opt,
    working_set_sizes,
)

BELADY = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
SILBERSCHATZ = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]


class TestExercise1PageTable(unittest.TestCase):
    def test_split_classic_32bit(self):
        pt = TwoLevelPageTable()  # 4 KiB ページ、10 + 10 + 12 ビット（32 ビットの x86 と同じ）
        self.assertEqual(pt.split(0x12345678), (0x48, 0x345, 0x678))
        self.assertEqual(pt.split(0), (0, 0, 0))
        self.assertEqual(pt.split(0xFFFFFFFF), (1023, 1023, 4095))

    def test_split_other_geometry(self):
        pt = TwoLevelPageTable(page_size=256, l1_bits=4, l2_bits=4)  # 16 ビットのアドレス空間
        self.assertEqual(pt.split(0xABCD), (0xA, 0xB, 0xCD))
        with self.assertRaises(ValueError):
            pt.split(0x10000)

    def test_translate(self):
        pt = TwoLevelPageTable()
        pt.map(0x12345, 0x777)
        self.assertEqual(pt.translate(0x12345678), 0x777678)
        self.assertEqual(pt.translate(0x12345000), 0x777000)
        self.assertEqual(pt.translate(0x12345FFF), 0x777FFF)

    def test_unmapped_address_is_page_fault(self):
        pt = TwoLevelPageTable()
        pt.map(1, 10)
        with self.assertRaises(PageFault) as ctx:
            pt.translate(0x5000)
        self.assertEqual(ctx.exception.vaddr, 0x5000)
        with self.assertRaises(PageFault, msg="同じ 2 段目の表の、別のエントリ"):
            pt.translate(0x2000)

    def test_not_present_is_page_fault(self):
        pt = TwoLevelPageTable()
        pt.map(3, 30)
        pt.lookup(3).present = False  # スワップアウトされた状態
        with self.assertRaises(PageFault):
            pt.translate(0x3000)

    def test_unmap(self):
        pt = TwoLevelPageTable()
        pt.map(3, 30)
        pt.unmap(3)
        with self.assertRaises(PageFault):
            pt.translate(0x3000)

    def test_permissions(self):
        pt = TwoLevelPageTable()
        pt.map(1, 11, writable=False)
        pt.map(2, 22, user=False)
        self.assertEqual(pt.translate(0x1004), 11 * 4096 + 4)  # 読むのは可
        with self.assertRaises(ProtectionFault):
            pt.translate(0x1004, write=True)
        with self.assertRaises(ProtectionFault):
            pt.translate(0x2000)  # ユーザーモードからカーネル専用ページ
        self.assertEqual(pt.translate(0x2000, user=False), 22 * 4096)  # カーネルモードなら可

    def test_accessed_and_dirty_bits(self):
        pt = TwoLevelPageTable()
        pt.map(5, 50)
        pte = pt.lookup(5)
        self.assertFalse(pte.accessed or pte.dirty)
        pt.translate(0x5000)
        self.assertTrue(pte.accessed)
        self.assertFalse(pte.dirty)
        pt.translate(0x5000, write=True)
        self.assertTrue(pte.dirty)

    def test_second_level_tables_are_allocated_on_demand(self):
        pt = TwoLevelPageTable()
        self.assertEqual(pt.table_count(), 1)
        pt.map(0, 1)
        pt.map(1, 2)  # 同じ 2 段目の表に入る
        self.assertEqual(pt.table_count(), 2)
        pt.map((1 << 20) - 1, 3)  # アドレス空間の最後のページ
        self.assertEqual(pt.table_count(), 3)
        # 3 つの表 × 1024 エントリ × 4 バイト = 12 KiB（1 段の表なら 2^20 × 4 = 4 MiB 必要）
        self.assertEqual(pt.table_bytes(), 12 * 1024)

    def test_invalid_arguments(self):
        for kwargs in ({"page_size": 1000}, {"page_size": 0}, {"l1_bits": 0}, {"l2_bits": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                TwoLevelPageTable(**kwargs)
        pt = TwoLevelPageTable()
        with self.assertRaises(ValueError):
            pt.map(1 << 20, 0)
        with self.assertRaises(ValueError):
            pt.map(0, -1)
        with self.assertRaises(ValueError):
            pt.translate(1 << 32)


class TestExercise2Tlb(unittest.TestCase):
    def test_lru_eviction_and_stats(self):
        tlb = TLB(2)
        self.assertIsNone(tlb.lookup(1))
        self.assertIsNone(tlb.insert(1, "a"))
        self.assertIsNone(tlb.insert(2, "b"))
        self.assertEqual(tlb.lookup(1), "a")  # 1 が最近使われた
        self.assertEqual(tlb.insert(3, "c"), 2, "最も長く使われていない 2 が追い出される")
        self.assertNotIn(2, tlb)
        self.assertIn(1, tlb)
        self.assertEqual((tlb.hits, tlb.misses), (1, 1))
        self.assertAlmostEqual(tlb.hit_rate, 0.5)
        self.assertEqual(len(tlb), 2)

    def test_insert_existing_updates_without_eviction(self):
        tlb = TLB(2)
        tlb.insert(1, "a")
        tlb.insert(2, "b")
        self.assertIsNone(tlb.insert(1, "A"))
        self.assertEqual(tlb.insert(3, "c"), 2)
        self.assertEqual(tlb.lookup(1), "A")

    def test_invalidate(self):
        tlb = TLB(4)
        for v in range(3):
            tlb.insert(v, v)
        tlb.invalidate(1)
        self.assertNotIn(1, tlb)
        self.assertEqual(len(tlb), 2)
        tlb.invalidate()
        self.assertEqual(len(tlb), 0)
        self.assertEqual(TLB(1).hit_rate, 0.0)
        with self.assertRaises(ValueError):
            TLB(0)

    def test_sequential_scan_hits_within_each_page(self):
        pt = TwoLevelPageTable()
        for vpn in range(64):
            pt.map(vpn, 1000 + vpn)
        mmu = MMU(pt, TLB(16))
        for vaddr in range(0, 64 * 4096, 64):  # 64 バイトごとに全ページを順に読む
            self.assertEqual(mmu.translate(vaddr), (1000 + vaddr // 4096) * 4096 + vaddr % 4096)
        self.assertEqual(mmu.walks, 64, "ページテーブルを引くのは各ページの最初の 1 回だけ")
        self.assertEqual(mmu.tlb.misses, 64)
        self.assertAlmostEqual(mmu.tlb.hit_rate, 63 / 64)

    def test_loop_slightly_larger_than_tlb_always_misses_with_lru(self):
        pt = TwoLevelPageTable()
        for vpn in range(17):
            pt.map(vpn, vpn)
        mmu = MMU(pt, TLB(16))
        for _ in range(10):
            for vpn in range(17):  # 17 ページを繰り返し巡回する
                mmu.translate(vpn * 4096)
        self.assertEqual(mmu.tlb.hits, 0, "LRU は「容量より 1 つ多いループ」で毎回ミスする")

    def test_faults_propagate_and_are_not_cached(self):
        pt = TwoLevelPageTable()
        pt.map(1, 5, writable=False)
        mmu = MMU(pt, TLB(4))
        with self.assertRaises(PageFault):
            mmu.translate(0x9000)
        self.assertNotIn(9, mmu.tlb)
        with self.assertRaises(ProtectionFault):
            mmu.translate(0x1000, write=True)  # TLB ミス → ページテーブルで検出
        mmu.translate(0x1000)  # 読みは成功し、TLB に入る
        self.assertIn(1, mmu.tlb)
        with self.assertRaises(ProtectionFault):
            mmu.translate(0x1000, write=True)  # TLB ヒットでも権限は検査される

    def test_stale_translation_until_invalidated(self):
        pt = TwoLevelPageTable()
        pt.map(2, 100)
        mmu = MMU(pt, TLB(4))
        self.assertEqual(mmu.translate(0x2010), 100 * 4096 + 0x10)
        pt.map(2, 200)  # OS がページテーブルを書き換えた（例: ページの移動）
        self.assertEqual(mmu.translate(0x2010), 100 * 4096 + 0x10, "TLB は古い変換を覚えている")
        mmu.tlb.invalidate(2)  # TLB シュートダウン
        self.assertEqual(mmu.translate(0x2010), 200 * 4096 + 0x10)


class TestExercise3Replacement(unittest.TestCase):
    ALL = (simulate_fifo, simulate_lru, simulate_opt, simulate_clock)

    def test_belady_anomaly_with_fifo(self):
        self.assertEqual(simulate_fifo(BELADY, 3), 9)
        self.assertEqual(simulate_fifo(BELADY, 4), 10, "フレームを増やしたのにフォールトが増える")

    def test_textbook_reference_string(self):
        self.assertEqual(simulate_fifo(SILBERSCHATZ, 3), 15)
        self.assertEqual(simulate_lru(SILBERSCHATZ, 3), 12)
        self.assertEqual(simulate_opt(SILBERSCHATZ, 3), 9)

    def test_clock(self):
        self.assertEqual(simulate_clock(SILBERSCHATZ, 3), 14)
        self.assertEqual(simulate_clock(BELADY, 3), 9)
        self.assertEqual(simulate_clock([1, 2, 3, 1, 4, 5], 3), 5)

    def test_lru_and_opt_on_belady_string(self):
        self.assertEqual([simulate_lru(BELADY, k) for k in (3, 4)], [10, 8])
        self.assertEqual([simulate_opt(BELADY, k) for k in (3, 4)], [7, 6])

    def test_edge_cases(self):
        for f in self.ALL:
            self.assertEqual(f([], 3), 0, f.__name__)
            self.assertEqual(f([1, 1, 1], 1), 1, f.__name__)
            self.assertEqual(f([1, 2, 1, 2], 1), 4, f.__name__)
            self.assertEqual(f([1, 2, 3, 1, 2, 3], 3), 3, f.__name__)  # 強制ミスのみ
            self.assertEqual(f(["a", "b", "a"], 2), 2, f.__name__)  # ページは任意のハッシュ可能な値
            with self.assertRaises(ValueError, msg=f.__name__):
                f([1], 0)

    def test_random_properties(self):
        rng = random.Random(21)
        for _ in range(200):
            refs = [rng.randrange(8) for _ in range(rng.randrange(1, 60))]
            distinct = len(set(refs))
            prev_lru = prev_opt = None
            for k in range(1, 10):
                fifo, lru, opt, clock = (f(refs, k) for f in self.ALL)
                self.assertLessEqual(opt, min(fifo, lru, clock), (refs, k))  # OPT は最適
                self.assertGreaterEqual(opt, distinct, (refs, k))  # 初回参照（強制ミス）は避けられない
                if k >= distinct:
                    self.assertEqual({fifo, lru, opt, clock}, {distinct}, (refs, k))
                # LRU と OPT はスタックアルゴリズムなので、Belady の異常を起こさない
                if prev_lru is not None:
                    self.assertLessEqual(lru, prev_lru, (refs, k))
                    self.assertLessEqual(opt, prev_opt, (refs, k))
                prev_lru, prev_opt = lru, opt


class TestExercise4CopyOnWrite(unittest.TestCase):
    def setUp(self):
        self.mem = CowMemory()
        self.parent = self.mem.spawn()
        for vpn in range(4):
            self.mem.alloc(self.parent, vpn, f"data{vpn}")

    def test_fork_copies_nothing(self):
        child = self.mem.fork(self.parent)
        self.assertEqual(self.mem.frames_in_use(), 4)
        self.assertEqual(self.mem.copies, 0)
        for vpn in range(4):
            self.assertEqual(self.mem.read(child, vpn), f"data{vpn}")

    def test_first_write_copies_the_page(self):
        child = self.mem.fork(self.parent)
        self.mem.write(child, 2, "child!")
        self.assertEqual(self.mem.read(child, 2), "child!")
        self.assertEqual(self.mem.read(self.parent, 2), "data2", "親からは元の内容が見える")
        self.assertEqual((self.mem.copies, self.mem.cow_faults, self.mem.frames_in_use()), (1, 1, 5))
        self.mem.write(child, 2, "again")  # 2 回目以降は普通の書き込み
        self.assertEqual((self.mem.copies, self.mem.cow_faults), (1, 1))

    def test_last_sharer_reuses_the_frame_without_copying(self):
        child = self.mem.fork(self.parent)
        self.mem.write(child, 0, "c")
        self.mem.write(self.parent, 0, "p")  # 元のフレームを参照しているのは親だけになっている
        self.assertEqual(self.mem.copies, 1)
        self.assertEqual(self.mem.cow_faults, 2)
        self.assertEqual(self.mem.frames_in_use(), 5)
        self.assertEqual((self.mem.read(self.parent, 0), self.mem.read(child, 0)), ("p", "c"))

    def test_exit_releases_frames(self):
        child = self.mem.fork(self.parent)
        self.mem.write(child, 1, "x")
        self.mem.write(child, 3, "y")
        self.assertEqual(self.mem.frames_in_use(), 6)
        self.mem.exit(child)
        self.assertEqual(self.mem.frames_in_use(), 4)
        self.mem.write(self.parent, 1, "z")  # 共有されていないので、コピーは起きない
        self.assertEqual(self.mem.copies, 2)
        with self.assertRaises(ValueError):
            self.mem.read(child, 0)

    def test_fork_of_fork(self):
        child = self.mem.fork(self.parent)
        grandchild = self.mem.fork(child)
        for pid in (self.parent, child, grandchild):
            self.mem.write(pid, 0, f"by{pid}")
        self.assertEqual(self.mem.copies, 2, "3 者で共有していたページは、最後の 1 者がそのまま使う")
        self.assertEqual({self.mem.read(p, 0) for p in (self.parent, child, grandchild)},
                         {f"by{p}" for p in (self.parent, child, grandchild)})

    def test_read_only_pages_are_shared_and_never_copied(self):
        self.mem.alloc(self.parent, 10, "code", writable=False)
        child = self.mem.fork(self.parent)
        with self.assertRaises(ProtectionFault):
            self.mem.write(child, 10, "patched")
        self.assertEqual(self.mem.copies, 0)
        self.assertEqual(self.mem.read(child, 10), "code")

    def test_errors(self):
        with self.assertRaises(PageFault):
            self.mem.read(self.parent, 99)
        with self.assertRaises(PageFault):
            self.mem.write(self.parent, 99, "x")
        with self.assertRaises(ValueError):
            self.mem.alloc(self.parent, 0, "dup")
        with self.assertRaises(ValueError):
            self.mem.fork(12345)

    def test_snapshot_memory_growth(self):
        # Redis の fork によるバックグラウンド保存のような状況: 子がスナップショットを書き出す間に親が更新を続ける
        mem = CowMemory()
        server = mem.spawn()
        for vpn in range(1000):
            mem.alloc(server, vpn, 0)
        snapshot = mem.fork(server)
        rng = random.Random(4)
        for vpn in rng.sample(range(1000), 300):  # 親がページの 30% を更新
            mem.write(server, vpn, 1)
        self.assertEqual(mem.copies, 300)
        self.assertEqual(mem.frames_in_use(), 1300, "メモリ使用量は 1.3 倍に増える")
        self.assertTrue(all(mem.read(snapshot, v) == 0 for v in range(1000)), "子は fork 時点の内容を見る")
        mem.exit(snapshot)
        self.assertEqual(mem.frames_in_use(), 1000)


class TestExercise5WorkingSet(unittest.TestCase):
    def test_example(self):
        self.assertEqual(working_set_sizes([1, 2, 1, 3, 4, 4, 4, 1], 3), [1, 2, 2, 3, 3, 2, 1, 2])

    def test_window_one_and_empty(self):
        self.assertEqual(working_set_sizes([5, 6, 5], 1), [1, 1, 1])
        self.assertEqual(working_set_sizes([], 4), [])
        with self.assertRaises(ValueError):
            working_set_sizes([1], 0)

    def test_matches_brute_force(self):
        rng = random.Random(22)
        for _ in range(200):
            refs = [rng.randrange(10) for _ in range(rng.randrange(0, 80))]
            window = rng.randrange(1, 20)
            expected = [len(set(refs[max(0, t - window + 1): t + 1])) for t in range(len(refs))]
            self.assertEqual(working_set_sizes(refs, window), expected, (refs, window))

    def test_phase_change(self):
        # 前半はページ 0〜4 を、後半はページ 100〜109 を使うプログラム（局所性の変化）
        refs = [i % 5 for i in range(100)] + [100 + i % 10 for i in range(100)]
        sizes = working_set_sizes(refs, 20)
        self.assertEqual(sizes[99], 5)
        self.assertEqual(max(sizes[100:119]), 15, "切り替わりの直後は新旧のページが混ざって一時的に大きくなる")
        self.assertEqual(sizes[-1], 10)


if __name__ == "__main__":
    unittest.main()
