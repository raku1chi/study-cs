"""11.2 HMAC の実装（hmac_impl）— テスト

実行: python3 tools/check.py 11.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import hashlib
import hmac
import random
import unittest

from hmac_impl import constant_time_equal, hmac_sha256, sha256_padding, verify_hmac

# RFC 4231「Identifiers and Test Vectors for HMAC-SHA-224, HMAC-SHA-256, HMAC-SHA-384,
# and HMAC-SHA-512」の HMAC-SHA-256 のテストケース 1〜7。
# （執筆時に標準ライブラリの hmac モジュールでも一致することを確認済み）
RFC4231_CASES = [
    (b"\x0b" * 20, b"Hi There",
     "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"),
    (b"Jefe", b"what do ya want for nothing?",
     "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"),
    (b"\xaa" * 20, b"\xdd" * 50,
     "773ea91e36800e46854db8ebd09181a72959098b3ef8c122d9635514ced565fe"),
    (bytes(range(1, 26)), b"\xcd" * 50,
     "82558a389a443c0ea4cc819899f2083a85f0faa3e578f8077a2e3ff46729665b"),
    # ケース 5 は出力を 128 ビットに切り詰めたもの
    (b"\x0c" * 20, b"Test With Truncation", "a3b6167473100ee06e0c796c2955552b"),
    # ケース 6・7 はブロック長（64 バイト）より長い 131 バイトの鍵
    (b"\xaa" * 131, b"Test Using Larger Than Block-Size Key - Hash Key First",
     "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"),
    (b"\xaa" * 131,
     b"This is a test using a larger than block-size key and a larger than block-size data. "
     b"The key needs to be hashed before being used by the HMAC algorithm.",
     "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"),
]


class TestExercise1Hmac(unittest.TestCase):
    def test_rfc4231_vectors(self):
        for i, (key, msg, expected) in enumerate(RFC4231_CASES, 1):
            tag = hmac_sha256(key, msg)
            self.assertEqual(len(tag), 32)
            self.assertEqual(tag.hex()[: len(expected)], expected, f"RFC 4231 テストケース {i}")

    def test_matches_stdlib_for_many_key_lengths(self):
        rng = random.Random(4231)
        # 鍵長 0・63・64・65 は境界（ブロック長 64 バイト前後）
        for key_len in [0, 1, 16, 32, 63, 64, 65, 100, 131, 200]:
            for _ in range(10):
                key = rng.randbytes(key_len)
                msg = rng.randbytes(rng.randrange(0, 300))
                self.assertEqual(hmac_sha256(key, msg), hmac.new(key, msg, hashlib.sha256).digest(),
                                 f"key_len={key_len}")

    def test_different_keys_give_different_tags(self):
        self.assertNotEqual(hmac_sha256(b"key-1", b"msg"), hmac_sha256(b"key-2", b"msg"))

    def test_rejects_str(self):
        with self.assertRaises(TypeError):
            hmac_sha256("key", b"msg")  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            hmac_sha256(b"key", "msg")  # type: ignore[arg-type]


class TestExercise2ConstantTime(unittest.TestCase):
    def test_equal_and_not_equal(self):
        self.assertIs(constant_time_equal(b"abc", b"abc"), True)
        self.assertIs(constant_time_equal(b"abc", b"abd"), False)
        self.assertIs(constant_time_equal(b"abc", b"xbc"), False)
        self.assertIs(constant_time_equal(b"", b""), True)
        self.assertIs(constant_time_equal(b"abc", b"abcd"), False)
        self.assertIs(constant_time_equal(b"\x00" * 32, b"\x00" * 31 + b"\x01"), False)

    def test_agrees_with_compare_digest(self):
        rng = random.Random(5)
        for _ in range(500):
            a = bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 8)))
            b = a if rng.random() < 0.5 else bytes(rng.getrandbits(8) for _ in range(rng.randrange(0, 8)))
            self.assertEqual(constant_time_equal(a, b), hmac.compare_digest(a, b), (a, b))

    def test_verify_hmac(self):
        key, msg = b"k" * 32, b"amount=10000&to=alice"
        tag = hmac.new(key, msg, hashlib.sha256).digest()
        self.assertTrue(verify_hmac(key, msg, tag))
        self.assertFalse(verify_hmac(key, b"amount=90000&to=alice", tag), "改ざんされたメッセージ")
        self.assertFalse(verify_hmac(b"x" * 32, msg, tag), "別の鍵")
        self.assertFalse(verify_hmac(key, msg, tag[:16]), "切り詰めたタグは完全なタグと一致しない")
        self.assertFalse(verify_hmac(key, msg, b""), "空のタグ")


class TestExercise3Sha256Padding(unittest.TestCase):
    def test_known_lengths(self):
        self.assertEqual(sha256_padding(0), b"\x80" + b"\x00" * 55 + b"\x00" * 8)
        self.assertEqual(sha256_padding(3), b"\x80" + b"\x00" * 52 + (24).to_bytes(8, "big"))
        self.assertEqual(sha256_padding(55), b"\x80" + (440).to_bytes(8, "big"), "ちょうど 1 ブロックに収まる最大長")
        self.assertEqual(len(sha256_padding(56)), 72, "56 バイトだと長さ欄が入らず 2 ブロックになる")

    def test_structure_for_many_lengths(self):
        for n in range(0, 300):
            pad = sha256_padding(n)
            self.assertEqual((n + len(pad)) % 64, 0, n)
            self.assertTrue(9 <= len(pad) <= 72, n)
            self.assertEqual(pad[0], 0x80, n)
            self.assertEqual(pad[1:-8], b"\x00" * (len(pad) - 9), n)
            self.assertEqual(int.from_bytes(pad[-8:], "big"), n * 8, n)

    def test_negative(self):
        with self.assertRaises(ValueError):
            sha256_padding(-1)


if __name__ == "__main__":
    unittest.main()
