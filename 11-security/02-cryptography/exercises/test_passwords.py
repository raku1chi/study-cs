"""11.2 パスワードの保存（passwords）— テスト

実行: python3 tools/check.py 11.2   （またはこのディレクトリで python3 -m unittest -v）

テストを速くするため、本番より大幅に弱いパラメータ（scrypt の N=2^10、PBKDF2 の 1,000 回）を
使っています。本番のパラメータは README の表と OWASP の最新版を確認してください。
"""
import base64
import hashlib
import re
import unicodedata
import unittest
from unittest import mock

import passwords
from passwords import (
    DEFAULT_PBKDF2,
    DEFAULT_SCRYPT,
    Pbkdf2Params,
    ScryptParams,
    default_params,
    hash_password,
    needs_rehash,
    parse_hash,
    scrypt_available,
    verify_password,
)

FAST_SCRYPT = ScryptParams(log2_n=10, r=8, p=1)
FAST_PBKDF2 = Pbkdf2Params(iterations=1000)
HAS_SCRYPT = hasattr(hashlib, "scrypt")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode().rstrip("=")


class TestExercise1Environment(unittest.TestCase):
    def test_scrypt_available_matches_hashlib(self):
        self.assertIsInstance(scrypt_available(), bool)
        if not HAS_SCRYPT:
            self.assertFalse(scrypt_available())

    def test_default_params(self):
        expected = DEFAULT_SCRYPT if scrypt_available() else DEFAULT_PBKDF2
        self.assertEqual(default_params(), expected)

    def test_fallback_to_pbkdf2(self):
        with mock.patch.object(passwords, "scrypt_available", return_value=False):
            self.assertEqual(default_params(), DEFAULT_PBKDF2)

    def test_production_defaults_follow_owasp_minimums(self):
        # 2026 年時点の OWASP Password Storage Cheat Sheet の最小推奨値
        self.assertEqual(DEFAULT_SCRYPT, ScryptParams(log2_n=17, r=8, p=1))
        self.assertEqual(DEFAULT_PBKDF2, Pbkdf2Params(iterations=600_000))


class TestExercise2Hash(unittest.TestCase):
    @unittest.skipUnless(HAS_SCRYPT, "この Python の hashlib は scrypt に対応していません")
    def test_scrypt_format_and_value(self):
        salt = b"0123456789abcdef"
        encoded = hash_password("correct horse battery staple", FAST_SCRYPT, salt=salt)
        expected_digest = hashlib.scrypt(
            b"correct horse battery staple", salt=salt, n=1024, r=8, p=1, dklen=32
        )
        self.assertEqual(encoded, f"$scrypt$ln=10,r=8,p=1${b64(salt)}${b64(expected_digest)}")

    def test_pbkdf2_format_and_value(self):
        salt = b"0123456789abcdef"
        encoded = hash_password("correct horse battery staple", FAST_PBKDF2, salt=salt)
        expected_digest = hashlib.pbkdf2_hmac("sha256", b"correct horse battery staple", salt, 1000, dklen=32)
        self.assertEqual(encoded, f"$pbkdf2-sha256$i=1000${b64(salt)}${b64(expected_digest)}")

    def test_random_salt(self):
        a = hash_password("same password", FAST_PBKDF2)
        b = hash_password("same password", FAST_PBKDF2)
        self.assertNotEqual(a, b, "同じパスワードでもソルトが違えば別のハッシュになる")
        self.assertRegex(a, r"^\$pbkdf2-sha256\$i=1000\$[A-Za-z0-9+/]+\$[A-Za-z0-9+/]+$")
        _, salt, _ = parse_hash(a)
        self.assertEqual(len(salt), 16)

    def test_nfkc_normalization(self):
        salt = b"s" * 16
        wide = hash_password("ｐａｓｓｗｏｒｄ１２３", FAST_PBKDF2, salt=salt)
        narrow = hash_password("password123", FAST_PBKDF2, salt=salt)
        self.assertEqual(wide, narrow, "全角と半角は NFKC で同じ文字列になる")
        composed = hash_password("がぎぐ", FAST_PBKDF2, salt=salt)
        decomposed = hash_password(unicodedata.normalize("NFD", "がぎぐ"), FAST_PBKDF2, salt=salt)
        self.assertEqual(composed, decomposed)

    def test_invalid_inputs(self):
        with self.assertRaises(TypeError):
            hash_password(b"bytes", FAST_PBKDF2)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            hash_password("", FAST_PBKDF2)
        with self.assertRaises(ValueError):
            hash_password("x" * 1025, FAST_PBKDF2)
        with self.assertRaises(ValueError):
            hash_password("pw", FAST_PBKDF2, salt=b"short")
        with self.assertRaises(ValueError):
            hash_password("pw", Pbkdf2Params(iterations=0))
        with self.assertRaises(ValueError):
            hash_password("pw", ScryptParams(log2_n=0))

    def test_parse_hash(self):
        encoded = hash_password("pw", FAST_PBKDF2, salt=b"s" * 16)
        params, salt, digest = parse_hash(encoded)
        self.assertEqual(params, FAST_PBKDF2)
        self.assertEqual(salt, b"s" * 16)
        self.assertEqual(len(digest), 32)

    def test_parse_hash_rejects_malformed(self):
        good = hash_password("pw", FAST_PBKDF2, salt=b"s" * 16)
        bad = [
            "",
            "plaintext-password",
            "$md5$abc$def",
            good.replace("i=1000", "i=abc"),
            good.replace("i=1000", "i=0"),
            good + "$extra",
            good[:-5],  # ハッシュ値が短い
            good.replace("$pbkdf2-sha256$", "$pbkdf2-sha1$"),
            "$scrypt$ln=10,r=8$c2FsdA$aGFzaA",
            good.rsplit("$", 1)[0] + "$!!!!",
        ]
        for encoded in bad:
            with self.assertRaises(ValueError, msg=encoded):
                parse_hash(encoded)


class TestExercise3Verify(unittest.TestCase):
    def check_verify(self, params):
        encoded = hash_password("Tr0ub4dor&3 は短すぎる", params)
        self.assertTrue(verify_password("Tr0ub4dor&3 は短すぎる", encoded))
        self.assertFalse(verify_password("tr0ub4dor&3 は短すぎる", encoded), "大文字小文字は区別する")
        self.assertFalse(verify_password("Tr0ub4dor&3", encoded))
        self.assertFalse(verify_password("", encoded))
        self.assertFalse(verify_password("x" * 100_000, encoded), "巨大な入力は計算せずに False")

    def test_verify_pbkdf2(self):
        self.check_verify(FAST_PBKDF2)

    @unittest.skipUnless(HAS_SCRYPT, "この Python の hashlib は scrypt に対応していません")
    def test_verify_scrypt(self):
        self.check_verify(FAST_SCRYPT)

    def test_tampered_hash_fails(self):
        encoded = hash_password("pw", FAST_PBKDF2, salt=b"s" * 16)
        head, digest = encoded.rsplit("$", 1)
        flipped = ("A" if digest[0] != "A" else "B") + digest[1:]
        self.assertFalse(verify_password("pw", f"{head}${flipped}"))
        with self.assertRaises(ValueError):
            verify_password("pw", "not-a-hash")

    def test_pepper(self):
        pepper = b"pepper-kept-in-kms-not-in-db"
        encoded = hash_password("pw123456", FAST_PBKDF2, pepper=pepper)
        self.assertTrue(verify_password("pw123456", encoded, pepper=pepper))
        self.assertFalse(verify_password("pw123456", encoded), "ペッパーがなければ一致しない")
        self.assertFalse(verify_password("pw123456", encoded, pepper=b"other-pepper"))

    def test_needs_rehash(self):
        old = hash_password("pw", Pbkdf2Params(iterations=1000))
        self.assertFalse(needs_rehash(old, Pbkdf2Params(iterations=1000)))
        self.assertTrue(needs_rehash(old, Pbkdf2Params(iterations=2000)), "反復回数を増やしたら作り直す")
        self.assertTrue(needs_rehash(old, FAST_SCRYPT), "アルゴリズムを変えたら作り直す")
        with mock.patch.object(passwords, "scrypt_available", return_value=False):
            self.assertTrue(needs_rehash(old), "既定値（PBKDF2 60 万回）と違えば作り直す")
        with self.assertRaises(ValueError):
            needs_rehash("garbage", FAST_PBKDF2)

    @unittest.skipUnless(HAS_SCRYPT, "この Python の hashlib は scrypt に対応していません")
    def test_needs_rehash_scrypt(self):
        encoded = hash_password("pw", FAST_SCRYPT)
        self.assertFalse(needs_rehash(encoded, ScryptParams(10, 8, 1)))
        self.assertTrue(needs_rehash(encoded, ScryptParams(11, 8, 1)))
        self.assertTrue(needs_rehash(encoded, ScryptParams(10, 8, 2)))
        self.assertTrue(needs_rehash(encoded), "既定値（N=2^17）より弱いので作り直す")

    def test_login_flow_upgrades_hash(self):
        # ログイン成功時にだけ平文が手に入るので、そのときに新しいパラメータで作り直す
        stored = hash_password("s3cret-passphrase", Pbkdf2Params(iterations=1000))
        target = Pbkdf2Params(iterations=1500)
        if verify_password("s3cret-passphrase", stored) and needs_rehash(stored, target):
            stored = hash_password("s3cret-passphrase", target)
        self.assertTrue(re.match(r"^\$pbkdf2-sha256\$i=1500\$", stored))
        self.assertTrue(verify_password("s3cret-passphrase", stored))


if __name__ == "__main__":
    unittest.main()
