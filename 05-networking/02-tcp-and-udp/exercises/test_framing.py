"""5.2 TCPとUDP — テスト（framing）

実行: python3 tools/check.py 5.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import struct
import unittest

from framing import FrameDecoder, FrameTooLarge, IncompleteFrame, encode_frame


def stream_of(frames):
    return b"".join(struct.pack("!I", len(f)) + f for f in frames)


class TestEncode(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(encode_frame(b"abc"), b"\x00\x00\x00\x03abc")
        self.assertEqual(encode_frame(b""), b"\x00\x00\x00\x00")
        self.assertEqual(encode_frame(b"x" * 300)[:4], b"\x00\x00\x01\x2c", "長さはビッグエンディアン")
        self.assertEqual(encode_frame(bytearray(b"hi")), b"\x00\x00\x00\x02hi")

    def test_rejects_non_bytes(self):
        with self.assertRaises(TypeError):
            encode_frame("文字列はエンコードしてから渡す")


class TestFrameDecoder(unittest.TestCase):
    FRAMES = [b"hello", b"", b"x" * 1000, bytes(range(256)), "日本語".encode("utf-8"), b"\x00\x00\x00\x05"]

    def test_whole_stream_at_once(self):
        d = FrameDecoder()
        self.assertEqual(d.feed(stream_of(self.FRAMES)), self.FRAMES)
        self.assertEqual(d.buffered, 0)

    def test_frames_are_bytes(self):
        frames = FrameDecoder().feed(encode_frame(b"abc"))
        self.assertIsInstance(frames[0], bytes, "bytearray や memoryview ではなく bytes を返す")

    def test_every_split_point(self):
        data = stream_of(self.FRAMES[:4])
        for cut in range(len(data) + 1):
            d = FrameDecoder()
            got = d.feed(data[:cut]) + d.feed(data[cut:])
            self.assertEqual(got, self.FRAMES[:4], f"{cut} バイト目で分割")

    def test_one_byte_at_a_time(self):
        data = stream_of(self.FRAMES)
        d = FrameDecoder()
        got = []
        for i in range(len(data)):
            got.extend(d.feed(data[i:i + 1]))
        self.assertEqual(got, self.FRAMES)

    def test_random_chunking(self):
        rng = random.Random(521)
        for _ in range(200):
            frames = [bytes(rng.getrandbits(8) for _ in range(rng.choice([0, 1, 3, 4, 5, 50, 700])))
                      for _ in range(rng.randrange(0, 8))]
            data = stream_of(frames)
            d = FrameDecoder()
            got, pos = [], 0
            while pos < len(data):
                step = rng.randrange(1, 40)
                got.extend(d.feed(data[pos:pos + step]))
                pos += step
            self.assertEqual(got, frames)
            self.assertEqual(d.buffered, 0)

    def test_partial_data_is_buffered(self):
        d = FrameDecoder()
        self.assertEqual(d.feed(b"\x00\x00"), [])
        self.assertEqual(d.buffered, 2)
        self.assertEqual(d.feed(b"\x00\x05he"), [])
        self.assertEqual(d.buffered, 6, "読み終えたヘッダ 4 バイト＋データ 2 バイト")
        self.assertEqual(d.feed(b"llo\x00\x00"), [b"hello"])
        self.assertEqual(d.buffered, 2)

    def test_large_frame_fed_in_small_chunks(self):
        payload = bytes(random.Random(522).getrandbits(8) for _ in range(20000))
        data = encode_frame(payload)
        d = FrameDecoder()
        got = []
        for i in range(0, len(data), 7):
            got.extend(d.feed(data[i:i + 7]))
        self.assertEqual(got, [payload])

    def test_max_frame_size_is_checked_on_header(self):
        d = FrameDecoder(max_frame_size=10)
        self.assertEqual(d.feed(encode_frame(b"0123456789")), [b"0123456789"], "ちょうど上限は OK")
        with self.assertRaises(FrameTooLarge, msg="ヘッダを受け取った時点で拒否する（データを待たない）"):
            d.feed(struct.pack("!I", 11))
        with self.assertRaises(FrameTooLarge):
            FrameDecoder(max_frame_size=1024).feed(b"\xff\xff\xff\xff")

    def test_frame_too_large_is_a_value_error(self):
        self.assertTrue(issubclass(FrameTooLarge, ValueError))

    def test_eof(self):
        d = FrameDecoder()
        d.feed(encode_frame(b"ok"))
        d.eof()  # 途中のデータがなければ何も起きない
        d.feed(b"\x00\x00\x00\x09partial")
        with self.assertRaises(IncompleteFrame):
            d.eof()

    def test_invalid_max_frame_size(self):
        with self.assertRaises(ValueError):
            FrameDecoder(max_frame_size=-1)


if __name__ == "__main__":
    unittest.main()
