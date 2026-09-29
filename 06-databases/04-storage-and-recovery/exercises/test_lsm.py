"""6.4 演習2（LSM 木）のテスト

実行: python3 tools/check.py 6.4   （またはこのディレクトリで python3 -m unittest -v test_lsm）
"""
import random
import tempfile
import unittest
from pathlib import Path

from lsm import WAL_FILE, LSMTree


class LSMTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.opened = []

    def tearDown(self):
        for db in self.opened:
            db.close()
        self.tmp.cleanup()

    def open(self, **kwargs):
        db = LSMTree(self.dir, **kwargs)
        self.opened.append(db)
        return db

    def reopen(self, db, **kwargs):
        db.close()
        return self.open(**kwargs)

    def sst_files(self):
        return sorted(p.name for p in self.dir.glob("*.sst"))

    def tiers(self, db):
        return [s.tier for s in db.sstables]


class TestWritesAndReads(LSMTestCase):
    def test_memtable_only(self):
        db = self.open(memtable_limit=100)
        db.put("apple", "red")
        db.put("banana", "yellow")
        db.put("apple", "green")
        db.delete("banana")
        self.assertEqual((db.get("apple"), db.get("banana"), db.get("cherry")), ("green", None, None))
        self.assertEqual(db.scan(), [("apple", "green")])
        self.assertEqual(self.sst_files(), [], "memtable が一杯になるまでは SSTable を作らない")

    def test_flush_on_limit_creates_sorted_sstable_and_empties_wal(self):
        db = self.open(memtable_limit=3)
        db.put("c", "3")
        db.put("a", "1")
        self.assertGreater((self.dir / WAL_FILE).stat().st_size, 0, "書き込みはまず WAL に入る")
        db.put("b", "2")
        self.assertEqual(self.sst_files(), ["00000001-t0.sst"])
        self.assertEqual(list(db.sstables[0].items()), [("a", "1"), ("b", "2"), ("c", "3")], "キーの昇順")
        self.assertEqual(db.memtable, {})
        self.assertEqual((self.dir / WAL_FILE).stat().st_size, 0, "フラッシュした分の WAL は不要になる")

    def test_newest_value_wins_across_sstables(self):
        db = self.open(memtable_limit=1)
        db.put("a", "old")
        db.put("a", "new")
        self.assertEqual(len(db.sstables), 2)
        self.assertEqual(db.get("a"), "new")
        self.assertEqual(db.scan(), [("a", "new")])

    def test_tombstone_hides_older_value(self):
        db = self.open(memtable_limit=1, tier_size=10)
        db.put("a", "1")
        db.delete("a")
        self.assertIsNone(db.get("a"))
        self.assertEqual(db.scan(), [])
        self.assertEqual(list(db.sstables[0].items()), [("a", None)], "削除は墓標として SSTable に残る")

    def test_get_stops_at_first_match(self):
        db = self.open(memtable_limit=2, tier_size=10)
        db.put("a", "old")
        db.put("b", "only-old")
        db.put("a", "new")
        db.put("c", "x")
        newer, older = db.sstables
        older.reads = newer.reads = 0
        self.assertEqual(db.get("a"), "new")
        self.assertEqual(older.reads, 0, "新しい SSTable で見つかったら、古い SSTable は読まない")
        self.assertEqual(db.get("b"), "only-old")
        self.assertEqual(older.reads, 1)

    def test_scan_is_half_open_range(self):
        db = self.open(memtable_limit=2, tier_size=10)
        for k in "edcba":
            db.put(k, k.upper())
        self.assertEqual(db.scan("b", "d"), [("b", "B"), ("c", "C")])
        self.assertEqual(db.scan(None, "b"), [("a", "A")])
        self.assertEqual(db.scan("d"), [("d", "D"), ("e", "E")])
        self.assertEqual(db.scan("x"), [])

    def test_scan_merges_memtable_and_all_sstables(self):
        db = self.open(memtable_limit=2, tier_size=10)
        db.put("a", "1")
        db.put("b", "1")      # SSTable 1: a=1, b=1
        db.put("b", "2")
        db.delete("a")        # SSTable 2: a=墓標, b=2
        db.put("c", "3")      # memtable: c=3
        self.assertEqual(db.scan(), [("b", "2"), ("c", "3")])

    def test_validation(self):
        db = self.open()
        with self.assertRaises(TypeError):
            db.put(b"bytes", "v")
        with self.assertRaises(TypeError):
            db.put("k", 1)
        with self.assertRaises(TypeError):
            db.delete(None)
        with self.assertRaises(ValueError):
            LSMTree(self.dir / "x", memtable_limit=0)
        with self.assertRaises(ValueError):
            LSMTree(self.dir / "y", tier_size=1)


class TestCompaction(LSMTestCase):
    def test_tiered_compaction_shape(self):
        db = self.open(memtable_limit=1, tier_size=3)
        for i in range(9):
            db.put(f"k{i:02d}", str(i))
        self.assertEqual(self.tiers(db), [2], "段 0 が 3 つで段 1 に、段 1 が 3 つで段 2 にまとまる")
        for i in range(9, 13):
            db.put(f"k{i:02d}", str(i))
        self.assertEqual(self.tiers(db), [0, 1, 2], "13 回のフラッシュ = 3 進数で 111")
        self.assertEqual(len(self.sst_files()), 3, "まとめた元のファイルは削除する")
        self.assertEqual([db.get(f"k{i:02d}") for i in range(13)], [str(i) for i in range(13)])

    def test_number_of_sstables_stays_small(self):
        db = self.open(memtable_limit=1, tier_size=3)
        for i in range(80):
            db.put(f"k{i:03d}", "v")
        self.assertLessEqual(len(db.sstables), 8, "80 = 3 進数で 2222。各桁の和 8 個以下")
        self.assertEqual(len(db.scan()), 80)

    def test_partial_merge_keeps_tombstones(self):
        db = self.open(memtable_limit=1, tier_size=3)
        for k in ("a", "b", "c"):
            db.put(k, "old")              # → 段 1 の SSTable に a, b, c
        db.delete("a")
        db.put("d", "x")
        db.put("e", "x")                  # → 墓標を含む段 0 が 3 つ → 段 1 にまとまる
        self.assertEqual(self.tiers(db), [1, 1])
        self.assertIsNone(db.get("a"), "一部だけのマージで墓標を捨てると、古い値が生き返ってしまう")
        self.assertIn(("a", None), list(db.sstables[0].items()))
        for k in ("f", "g", "h"):
            db.put(k, "x")                # → 段 1 が 3 つ → 全部をまとめて段 2 へ
        self.assertEqual(self.tiers(db), [2])
        self.assertNotIn("a", [k for k, _ in db.sstables[0].items()], "全部をまとめるなら墓標は捨ててよい")
        self.assertIsNone(db.get("a"))

    def test_compact_all(self):
        db = self.open(memtable_limit=2, tier_size=10)
        for i in range(10):
            db.put(f"k{i}", str(i))
        for i in range(0, 10, 3):
            db.delete(f"k{i}")
        db.flush()
        before = db.scan()
        db.compact_all()
        self.assertEqual(len(db.sstables), 1)
        self.assertEqual(len(self.sst_files()), 1)
        self.assertTrue(all(v is not None for _, v in db.sstables[0].items()), "墓標は残らない")
        self.assertEqual(db.scan(), before)

    def test_flush_and_compact_on_empty(self):
        db = self.open()
        db.flush()
        db.compact_all()
        self.assertEqual(self.sst_files(), [])


class TestRecovery(LSMTestCase):
    def test_memtable_is_rebuilt_from_wal(self):
        db = self.open(memtable_limit=100)
        db.put("a", "1")
        db.put("b", "2")
        db.delete("a")
        db = self.reopen(db, memtable_limit=100)   # クラッシュしたことにして開き直す
        self.assertEqual((db.get("a"), db.get("b")), (None, "2"))
        self.assertEqual(db.wal_truncated_bytes, 0)

    def test_torn_wal_tail_is_discarded(self):
        db = self.open(memtable_limit=100)
        db.put("a", "1")
        db.put("b", "2")
        db.close()
        torn = b'["put", "c", "tr'  # 改行まで書かれる前にクラッシュした
        with open(self.dir / WAL_FILE, "ab") as f:
            f.write(torn)
        db = self.open(memtable_limit=100)
        self.assertEqual(db.wal_truncated_bytes, len(torn))
        self.assertEqual((db.get("a"), db.get("b"), db.get("c")), ("1", "2", None))
        db.put("d", "4")
        db = self.reopen(db, memtable_limit=100)
        self.assertEqual(db.wal_truncated_bytes, 0, "切り詰めた後の追記は正しく読める")
        self.assertEqual(db.get("d"), "4")

    def test_corrupt_wal_line_stops_replay(self):
        db = self.open(memtable_limit=100)
        db.put("a", "1")
        db.close()
        with open(self.dir / WAL_FILE, "ab") as f:
            f.write(b"garbage\n")
            f.write(b'["put", "z", "after garbage"]\n')
        db = self.open(memtable_limit=100)
        self.assertEqual(db.get("a"), "1")
        self.assertIsNone(db.get("z"), "壊れた行より後ろは信用しない")

    def test_recovery_with_sstables_and_wal(self):
        db = self.open(memtable_limit=2)
        db.put("a", "1")
        db.put("b", "2")          # フラッシュ済み
        db.put("c", "3")          # WAL にだけある
        db = self.reopen(db, memtable_limit=2)
        self.assertEqual([db.get(k) for k in "abc"], ["1", "2", "3"])
        self.assertEqual(len(db.sstables), 1)
        db.put("d", "4")          # c と d でフラッシュ。連番は続きから
        self.assertEqual(self.sst_files(), ["00000001-t0.sst", "00000002-t0.sst"])

    def test_leftover_temporary_files_are_removed(self):
        db = self.open(memtable_limit=1)
        db.put("a", "1")
        db.close()
        (self.dir / "00000009-t0.sst.tmp").write_text('["half", "written"', encoding="utf-8")
        db = self.open(memtable_limit=1)
        self.assertEqual(list(self.dir.glob("*.tmp")), [])
        self.assertEqual(db.get("a"), "1")

    def test_random_operations_against_model(self):
        rng = random.Random(64)
        for tier_size in (2, 3):
            directory = self.dir / f"t{tier_size}"
            db = LSMTree(directory, memtable_limit=3, tier_size=tier_size)
            model = {}
            for step in range(400):
                key = f"k{rng.randrange(25):02d}"
                r = rng.random()
                if r < 0.55:
                    value = f"v{step}"
                    db.put(key, value)
                    model[key] = value
                elif r < 0.75:
                    db.delete(key)
                    model.pop(key, None)
                elif r < 0.8:
                    db.flush()
                elif r < 0.84:
                    db.close()
                    db = LSMTree(directory, memtable_limit=3, tier_size=tier_size)
                elif r < 0.86:
                    db.compact_all()
                else:
                    self.assertEqual(db.get(key), model.get(key), f"tier_size={tier_size} step={step} key={key}")
                if step % 50 == 0:
                    self.assertEqual(db.scan(), sorted(model.items()), f"tier_size={tier_size} step={step}")
            self.assertEqual(db.scan(), sorted(model.items()))
            db.close()


if __name__ == "__main__":
    unittest.main()
