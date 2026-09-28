"""4.3 ファイルシステムとI/O — fileio のテスト

実行: python3 tools/check.py 4.3   （またはこのディレクトリで python3 -m unittest -v test_fileio）
"""
import io
import os
import random
import stat
import tempfile
import tracemalloc
import unittest
import zlib
from pathlib import Path
from unittest import mock

import fileio
from fileio import (
    HEADER,
    MAX_RECORD_SIZE,
    Counts,
    RecordLog,
    atomic_write,
    count_file,
    decode_records,
    encode_record,
    tail,
)

POSIX = os.name == "posix"


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="study-cs-4.3-")
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def entries(self):
        return sorted(p.name for p in self.dir.iterdir())


class TestExercise1AtomicWrite(TempDirTestCase):
    def test_creates_and_replaces(self):
        path = self.dir / "config.json"
        atomic_write(path, b'{"v": 1}')
        self.assertEqual(path.read_bytes(), b'{"v": 1}')
        atomic_write(str(path), b'{"v": 2}')  # str のパスも受け付ける
        self.assertEqual(path.read_bytes(), b'{"v": 2}')
        self.assertEqual(self.entries(), ["config.json"], "一時ファイルが残っていてはいけない")

    def test_large_and_empty_data(self):
        path = self.dir / "blob"
        data = os.urandom(3 * 1024 * 1024 + 7)
        atomic_write(path, data)
        self.assertEqual(path.read_bytes(), data)
        atomic_write(path, b"")
        self.assertEqual(path.read_bytes(), b"")

    def test_fsync_file_then_replace_then_fsync_directory(self):
        path = self.dir / "state"
        path.write_bytes(b"old")
        events = []
        real_fsync, real_replace = os.fsync, os.replace

        def fsync(fd):
            events.append(("fsync", "dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file"))
            return real_fsync(fd)

        def replace(src, dst, *args, **kwargs):
            events.append(("replace",))
            return real_replace(src, dst, *args, **kwargs)

        with mock.patch.object(fileio.os, "fsync", side_effect=fsync), \
                mock.patch.object(fileio.os, "replace", side_effect=replace):
            atomic_write(path, b"new")
        expected = [("fsync", "file"), ("replace",)]
        if POSIX:
            expected.append(("fsync", "dir"))
        self.assertEqual(events, expected, "中身の fsync → rename → ディレクトリの fsync の順であること")
        self.assertEqual(path.read_bytes(), b"new")

    def test_failure_keeps_old_content_and_removes_temp_file(self):
        path = self.dir / "state"
        path.write_bytes(b"old")
        with mock.patch.object(fileio.os, "fsync", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                atomic_write(path, b"new content")
        self.assertEqual(path.read_bytes(), b"old", "失敗しても元の内容はそのまま")
        self.assertEqual(self.entries(), ["state"], "失敗しても一時ファイルを残さない")

    def test_non_bytes_data_is_rejected_without_leftovers(self):
        path = self.dir / "x"
        with self.assertRaises(TypeError):
            atomic_write(path, "text is not bytes")
        self.assertEqual(self.entries(), [])

    def test_missing_directory(self):
        with self.assertRaises(FileNotFoundError):
            atomic_write(self.dir / "no-such-dir" / "file", b"x")

    @unittest.skipUnless(POSIX, "パーミッションの検査は POSIX のみ")
    def test_permissions_are_preserved(self):
        path = self.dir / "secret.conf"
        path.write_bytes(b"old")
        os.chmod(path, 0o640)
        atomic_write(path, b"new")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o640)

    @unittest.skipUnless(POSIX, "パーミッションの検査は POSIX のみ")
    def test_new_file_gets_default_permissions(self):
        umask = os.umask(0)
        os.umask(umask)
        path = self.dir / "new"
        atomic_write(path, b"x")
        self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o666 & ~umask,
                         "新しいファイルは、普通に open したときと同じ権限（0o666 から umask を除いたもの）")


class CountingBytesIO(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.bytes_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.bytes_read += len(chunk)
        return chunk


def reference_tail(data: bytes, n: int) -> list[bytes]:
    if not data or n == 0:
        return []
    body = data[:-1] if data.endswith(b"\n") else data
    return body.split(b"\n")[-n:]


class TestExercise2Tail(unittest.TestCase):
    def test_examples(self):
        f = io.BytesIO(b"one\ntwo\nthree\n")
        self.assertEqual(tail(f, 2), [b"two", b"three"])
        self.assertEqual(tail(f, 10), [b"one", b"two", b"three"])
        self.assertEqual(tail(io.BytesIO(b"a\nb\nc"), 1), [b"c"], "最後の行に改行がなくてもよい")
        self.assertEqual(tail(io.BytesIO(b"x\n\n\ny\n"), 3), [b"", b"", b"y"], "空の行も 1 行")
        self.assertEqual(tail(io.BytesIO(b"\n"), 1), [b""])

    def test_empty_file_and_zero_lines(self):
        self.assertEqual(tail(io.BytesIO(b""), 5), [])
        self.assertEqual(tail(io.BytesIO(b"a\nb\n"), 0), [])

    def test_lines_longer_than_block(self):
        data = b"".join(bytes([97 + i]) * 100 + b"\n" for i in range(5))
        self.assertEqual(tail(io.BytesIO(data), 2, block_size=16), [b"d" * 100, b"e" * 100])

    def test_matches_reference_on_random_files(self):
        rng = random.Random(31)
        for _ in range(400):
            data = bytes(rng.choice(b"ab\n") for _ in range(rng.randrange(0, 200)))
            n = rng.randrange(0, 12)
            block = rng.randrange(1, 40)
            self.assertEqual(tail(io.BytesIO(data), n, block_size=block), reference_tail(data, n),
                             (data, n, block))

    def test_reads_only_the_end_of_a_large_file(self):
        lines = [f"line {i:06d} ".encode() + b"x" * 40 for i in range(20000)]  # 約 1 MB
        f = CountingBytesIO(b"\n".join(lines) + b"\n")
        self.assertEqual(tail(f, 10, block_size=4096), lines[-10:])
        self.assertLessEqual(f.bytes_read, 2 * 4096, "ファイル全体を読まず、末尾のブロックだけを読むこと")

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            tail(io.BytesIO(b"a\n"), -1)
        with self.assertRaises(ValueError):
            tail(io.BytesIO(b"a\n"), 1, block_size=0)


class TestExercise3CountFile(TempDirTestCase):
    def write(self, data: bytes) -> Path:
        path = self.dir / "input.txt"
        path.write_bytes(data)
        return path

    def test_example(self):
        path = self.write(b"hello world\nthis is  a test\n\nlast line without newline")
        self.assertEqual(count_file(path), Counts(lines=3, words=10, bytes=54))

    def test_empty_file(self):
        self.assertEqual(count_file(self.write(b"")), Counts(0, 0, 0))

    def test_words_across_chunk_boundaries(self):
        data = b"alpha beta\tgamma\r\ndelta\x0bepsilon\x0czeta  "
        path = self.write(data)
        expected = Counts(data.count(b"\n"), len(data.split()), len(data))
        for chunk_size in range(1, len(data) + 2):
            self.assertEqual(count_file(path, chunk_size=chunk_size), expected, f"chunk_size={chunk_size}")

    def test_matches_reference_on_random_data(self):
        rng = random.Random(32)
        for _ in range(100):
            data = bytes(rng.choice(b"ab \n\t") for _ in range(rng.randrange(0, 300)))
            path = self.write(data)
            expected = Counts(data.count(b"\n"), len(data.split()), len(data))
            self.assertEqual(count_file(path, chunk_size=rng.randrange(1, 50)), expected, data)

    def test_memory_stays_bounded_for_a_file_with_one_huge_line(self):
        size = 8 * 1024 * 1024
        path = self.write(b"word " * (size // 5) + b"\n")  # 8 MiB の 1 行（行単位で読むと全部がメモリに載る）
        tracemalloc.start()
        try:
            result = count_file(path, chunk_size=64 * 1024)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(result, Counts(1, size // 5, size // 5 * 5 + 1))
        self.assertLess(peak, 3 * 1024 * 1024, f"メモリのピークが大きすぎます: {peak:,} バイト")

    def test_invalid_chunk_size(self):
        with self.assertRaises(ValueError):
            count_file(self.write(b"x"), chunk_size=0)


class TestExercise4RecordLog(TempDirTestCase):
    def test_encode_format(self):
        rec = encode_record(b"hi")
        self.assertEqual(rec, HEADER.pack(2, zlib.crc32(b"hi")) + b"hi")
        self.assertEqual(rec[:4], b"\x00\x00\x00\x02", "長さはビッグエンディアンの 4 バイト")
        self.assertEqual(len(encode_record(b"")), 8)

    def test_encode_errors(self):
        with self.assertRaises(TypeError):
            encode_record("text")
        with self.assertRaises(ValueError):
            encode_record(b"x" * (MAX_RECORD_SIZE + 1))

    def test_decode(self):
        data = encode_record(b"a") + encode_record(b"") + encode_record(b"ccc")
        self.assertEqual(decode_records(data), ([b"a", b"", b"ccc"], len(data)))
        self.assertEqual(decode_records(b""), ([], 0))

    def test_decode_stops_at_torn_or_corrupt_record(self):
        good = encode_record(b"first") + encode_record(b"second")
        tail_rec = encode_record(b"third record")
        for cut in range(1, len(tail_rec)):
            self.assertEqual(decode_records(good + tail_rec[:cut]), ([b"first", b"second"], len(good)), cut)
        broken = bytearray(good + tail_rec)
        broken[-1] ^= 0x01  # ペイロードの 1 ビットを反転
        self.assertEqual(decode_records(bytes(broken)), ([b"first", b"second"], len(good)))
        huge = HEADER.pack(0xFFFFFFFF, 0) + b"junk"
        self.assertEqual(decode_records(good + huge), ([b"first", b"second"], len(good)))

    def test_corruption_in_the_middle_discards_the_rest(self):
        recs = [encode_record(p) for p in (b"a", b"bb", b"ccc")]
        data = bytearray(b"".join(recs))
        data[len(recs[0]) + 8] ^= 0xFF  # 2 番目のレコードのペイロードを壊す
        self.assertEqual(decode_records(bytes(data)), ([b"a"], len(recs[0])))

    def test_append_and_reopen(self):
        path = self.dir / "wal.log"
        with RecordLog(path) as log:
            offsets = [log.append(p) for p in (b"alpha", b"", b"gamma")]
            self.assertEqual(offsets, [0, 13, 21])
            self.assertEqual(log.records(), [b"alpha", b"", b"gamma"])
        with RecordLog(path) as log:
            self.assertEqual(log.truncated_bytes, 0)
            self.assertEqual(log.records(), [b"alpha", b"", b"gamma"])
            log.append(b"delta")
            self.assertEqual(log.records(), [b"alpha", b"", b"gamma", b"delta"])

    def test_recovery_truncates_torn_tail_at_every_cut_point(self):
        path = self.dir / "wal.log"
        good = encode_record(b"committed-1") + encode_record(b"committed-2")
        torn = encode_record(b"in-flight record")
        for cut in range(1, len(torn)):
            path.write_bytes(good + torn[:cut])  # 3 件目を書いている途中でクラッシュした
            with RecordLog(path) as log:
                self.assertEqual(log.truncated_bytes, cut)
                self.assertEqual(log.records(), [b"committed-1", b"committed-2"])
                self.assertEqual(os.path.getsize(path), len(good), "壊れた末尾は切り詰められる")
                log.append(b"after-recovery")
            with RecordLog(path) as log:
                self.assertEqual(log.records(), [b"committed-1", b"committed-2", b"after-recovery"])

    def test_fsync_on_append(self):
        path = self.dir / "wal.log"
        with RecordLog(path) as log, mock.patch.object(fileio.os, "fsync") as fsync:
            log.append(b"x")
            log.append(b"y")
            self.assertEqual(fsync.call_count, 2, "sync=True なら append のたびに fsync する")
        with RecordLog(path, sync=False) as log, mock.patch.object(fileio.os, "fsync") as fsync:
            log.append(b"z")
            self.assertEqual(fsync.call_count, 0)


if __name__ == "__main__":
    unittest.main()
