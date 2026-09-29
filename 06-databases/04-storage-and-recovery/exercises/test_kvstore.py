"""6.4 演習1（Bitcask 方式のキーバリューストア）のテスト

実行: python3 tools/check.py 6.4   （またはこのディレクトリで python3 -m unittest -v test_kvstore）

クラッシュは「ファイルの末尾を切り詰める・壊れたバイトを足す」ことで再現します。
"""
import random
import tempfile
import unittest
from pathlib import Path

from kvstore import COMPACT_FILE, DATA_FILE, HEADER, BitcaskStore, encode_record


class KVTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.stores = []

    def tearDown(self):
        for s in self.stores:
            s.close()
        self.tmp.cleanup()

    def open(self, **kwargs):
        store = BitcaskStore(self.dir, **kwargs)
        self.stores.append(store)
        return store

    @property
    def data_path(self):
        return self.dir / DATA_FILE


class TestBasics(KVTestCase):
    def test_put_get_overwrite_delete(self):
        db = self.open()
        db.put(b"apple", b"red")
        db.put(b"banana", b"yellow")
        db.put(b"apple", b"green")
        self.assertEqual(db.get(b"apple"), b"green")
        self.assertEqual(db.get(b"banana"), b"yellow")
        self.assertIsNone(db.get(b"cherry"))
        self.assertEqual(len(db), 2)
        self.assertTrue(db.delete(b"banana"))
        self.assertFalse(db.delete(b"banana"))
        self.assertIsNone(db.get(b"banana"))
        self.assertEqual(db.keys(), [b"apple"])

    def test_file_is_append_only_log(self):
        db = self.open()
        db.put(b"k", b"v1")
        db.put(b"k", b"v2")
        db.delete(b"k")
        expected = encode_record(b"k", b"v1") + encode_record(b"k", b"v2") + encode_record(b"k", None)
        self.assertEqual(self.data_path.read_bytes(), expected, "上書きも削除も、末尾への追記で表す")
        self.assertEqual(db.file_size(), len(expected))

    def test_keydir_points_into_file(self):
        db = self.open()
        db.put(b"ab", b"xyz")
        offset, length = db.keydir[b"ab"]
        self.assertEqual((offset, length), (HEADER.size + 2, 3))
        with open(self.data_path, "rb") as f:
            f.seek(offset)
            self.assertEqual(f.read(length), b"xyz")

    def test_empty_values_and_binary_data(self):
        db = self.open()
        db.put(b"empty", b"")
        db.put(b"\x00\xff", bytes(range(256)))
        self.assertEqual(db.get(b"empty"), b"")
        self.assertEqual(db.get(b"\x00\xff"), bytes(range(256)))

    def test_type_checks(self):
        db = self.open()
        for bad in ("str", b"", 1):
            with self.assertRaises(TypeError, msg=repr(bad)):
                db.put(bad, b"v")
        with self.assertRaises(TypeError):
            db.put(b"k", "not bytes")

    def test_data_survives_reopen(self):
        for sync in (False, True):
            d = self.dir / f"sync-{sync}"
            db = BitcaskStore(d, sync=sync)
            db.put(b"a", b"1")
            db.put(b"b", b"2")
            db.delete(b"a")
            db.close()
            db = BitcaskStore(d, sync=sync)
            self.assertEqual((db.get(b"a"), db.get(b"b")), (None, b"2"), f"sync={sync}")
            self.assertEqual(db.truncated_bytes, 0)
            db.close()


class TestRecovery(KVTestCase):
    def fill(self):
        db = self.open()
        db.put(b"a", b"apple")
        db.put(b"b", b"banana")
        db.put(b"a", b"avocado")
        db.close()
        return self.data_path.stat().st_size

    def test_garbage_tail_is_truncated(self):
        size = self.fill()
        with open(self.data_path, "ab") as f:
            f.write(b"\x00\x01\x02\x03\x04")  # ヘッダの途中でクラッシュした書き込み
        db = self.open()
        self.assertEqual(db.truncated_bytes, 5)
        self.assertEqual(self.data_path.stat().st_size, size, "壊れた末尾を切り詰める")
        self.assertEqual((db.get(b"a"), db.get(b"b")), (b"avocado", b"banana"))

    def test_torn_last_record_is_discarded(self):
        self.fill()
        db = self.open()
        db.put(b"b", b"blueberry")  # この書き込みの途中でクラッシュしたことにする
        db.close()
        full = self.data_path.stat().st_size
        with open(self.data_path, "r+b") as f:
            f.truncate(full - 4)
        db = self.open()
        self.assertEqual(db.get(b"b"), b"banana", "書きかけの更新は無かったことになり、前の値が残る")
        self.assertEqual(db.truncated_bytes, len(encode_record(b"b", b"blueberry")) - 4)

    def test_corrupted_record_fails_crc_check(self):
        self.fill()
        db = self.open()
        db.put(b"c", b"cherry")
        db.close()
        data = bytearray(self.data_path.read_bytes())
        data[-1] ^= 0xFF  # 最後のレコードの値の 1 バイトが化けた
        self.data_path.write_bytes(bytes(data))
        db = self.open()
        self.assertIsNone(db.get(b"c"), "crc32 が合わないレコードは信用しない")
        self.assertEqual(db.get(b"a"), b"avocado")

    def test_writes_after_recovery_are_readable_after_another_reopen(self):
        self.fill()
        with open(self.data_path, "ab") as f:
            f.write(b"\xde\xad")
        db = self.open()
        db.put(b"d", b"date")
        db.close()
        db = self.open()
        self.assertEqual(db.truncated_bytes, 0, "回復後の追記は、正しい位置から始まっている")
        self.assertEqual((db.get(b"a"), db.get(b"d")), (b"avocado", b"date"))

    def test_torn_tombstone(self):
        self.fill()
        db = self.open()
        db.delete(b"a")
        db.close()
        with open(self.data_path, "r+b") as f:
            f.truncate(self.data_path.stat().st_size - 1)
        db = self.open()
        self.assertEqual(db.get(b"a"), b"avocado", "書きかけの削除も無かったことになる")

    def test_random_truncation_never_loses_complete_records(self):
        rng = random.Random(64)
        db = self.open()
        boundaries = [0]
        model_at = [{}]
        model = {}
        for i in range(60):
            key = f"k{rng.randrange(10)}".encode()
            if rng.random() < 0.2 and key in model:
                db.delete(key)
                del model[key]
            else:
                value = rng.randbytes(rng.randrange(0, 20))
                db.put(key, value)
                model[key] = value
            boundaries.append(self.data_path.stat().st_size)
            model_at.append(dict(model))
        db.close()
        original = self.data_path.read_bytes()
        for _ in range(40):
            cut = rng.randrange(len(original) + 1)
            self.data_path.write_bytes(original[:cut])
            db = BitcaskStore(self.dir)
            complete = max(i for i, b in enumerate(boundaries) if b <= cut)
            self.assertEqual({k: db.get(k) for k in db.keys()}, model_at[complete], f"cut={cut}")
            self.assertEqual(db.truncated_bytes, cut - boundaries[complete])
            db.close()


class TestCompaction(KVTestCase):
    def test_compaction_reclaims_space(self):
        db = self.open()
        for i in range(50):
            db.put(b"counter", str(i).encode())
        for i in range(10):
            db.put(f"tmp{i}".encode(), b"x" * 10)
            db.delete(f"tmp{i}".encode())
        db.put(b"keep", b"me")
        before = db.file_size()
        db.compact()
        after = db.file_size()
        expected = len(encode_record(b"counter", b"49")) + len(encode_record(b"keep", b"me"))
        self.assertEqual(after, expected, "生きているキーの最新の値だけが残る")
        self.assertLess(after, before / 10)
        self.assertEqual((db.get(b"counter"), db.get(b"keep"), db.get(b"tmp3")), (b"49", b"me", None))
        self.assertEqual(db.keys(), [b"counter", b"keep"])

    def test_store_works_after_compaction_and_reopen(self):
        db = self.open()
        db.put(b"a", b"1")
        db.put(b"b", b"2")
        db.put(b"a", b"3")
        db.compact()
        db.put(b"c", b"4")
        db.delete(b"b")
        db.close()
        db = self.open()
        self.assertEqual({k: db.get(k) for k in db.keys()}, {b"a": b"3", b"c": b"4"})
        self.assertFalse((self.dir / COMPACT_FILE).exists())

    def test_leftover_compaction_file_is_ignored(self):
        db = self.open()
        db.put(b"a", b"1")
        db.close()
        (self.dir / COMPACT_FILE).write_bytes(b"half-written garbage")  # コンパクション中にクラッシュ
        db = self.open()
        self.assertEqual(db.get(b"a"), b"1")
        self.assertFalse((self.dir / COMPACT_FILE).exists(), "残骸は削除する")


if __name__ == "__main__":
    unittest.main()
