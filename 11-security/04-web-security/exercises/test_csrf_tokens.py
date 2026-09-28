"""11.4 CSRF トークン（csrf_tokens）— テスト

実行: python3 tools/check.py 11.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from csrf_tokens import constant_time_compare, generate_token, validate_token

KEY = b"server-side-csrf-signing-key-0001"
SID = "session-abc123"


class TestSynchronizerToken(unittest.TestCase):
    def test_generate_and_validate(self):
        token = generate_token(KEY, SID, now=1000)
        self.assertEqual(token.count("."), 2)
        self.assertTrue(validate_token(KEY, SID, token, now=1000))
        self.assertTrue(validate_token(KEY, SID, token, now=1000 + 3599))

    def test_tokens_are_unique(self):
        # nonce により、同じセッション・同じ時刻でも毎回違うトークンになる
        tokens = {generate_token(KEY, SID, now=1000) for _ in range(50)}
        self.assertEqual(len(tokens), 50)

    def test_expiry(self):
        token = generate_token(KEY, SID, now=1000)
        self.assertFalse(validate_token(KEY, SID, token, now=1000 + 3601), "期限切れ")
        self.assertTrue(validate_token(KEY, SID, token, max_age_seconds=7200, now=1000 + 7200))
        self.assertFalse(validate_token(KEY, SID, token, now=999), "発行時刻より前は無効")

    def test_bound_to_session(self):
        token = generate_token(KEY, SID, now=1000)
        self.assertFalse(validate_token(KEY, "other-session", token, now=1000),
                         "別セッションのトークンは使えない")

    def test_tampering_is_detected(self):
        token = generate_token(KEY, SID, now=1000)
        issued, nonce, sig = token.split(".")
        forgeries = [
            f"{issued}.{nonce}.{sig[:-1]}" + ("A" if sig[-1] != "A" else "B"),  # 署名の改ざん
            f"999999.{nonce}.{sig}",  # 発行時刻の改ざん（期限を延ばそうとする）
            f"{issued}.{nonce}x.{sig}",  # nonce の改ざん
            f"{issued}.{nonce}",  # 部分が足りない
            "not-a-token",
            "",
            f"00{issued}.{nonce}.{sig}",  # 発行時刻の表記ゆれ
        ]
        for bad in forgeries:
            self.assertFalse(validate_token(KEY, SID, bad, now=1000), repr(bad))

    def test_wrong_key_rejected(self):
        token = generate_token(KEY, SID, now=1000)
        self.assertFalse(validate_token(b"another-key-that-is-long-enough!", SID, token, now=1000))

    def test_key_length_enforced(self):
        with self.assertRaises(ValueError):
            generate_token(b"short", SID)
        with self.assertRaises(ValueError):
            generate_token("not-bytes", SID)  # type: ignore[arg-type]

    def test_uses_real_clock_by_default(self):
        # now を渡さなければ実時刻。生成直後は有効なはず
        token = generate_token(KEY, SID)
        self.assertTrue(validate_token(KEY, SID, token))


class TestDoubleSubmit(unittest.TestCase):
    def test_constant_time_compare(self):
        self.assertTrue(constant_time_compare("abc123", "abc123"))
        self.assertFalse(constant_time_compare("abc123", "abc124"))
        self.assertFalse(constant_time_compare("abc", "abcd"))
        self.assertFalse(constant_time_compare("", "x"))
        self.assertTrue(constant_time_compare("", ""))

    def test_non_string_is_false(self):
        self.assertFalse(constant_time_compare(None, "x"))  # type: ignore[arg-type]
        self.assertFalse(constant_time_compare("x", None))  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
