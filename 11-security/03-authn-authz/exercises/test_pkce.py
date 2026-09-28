"""11.3 PKCE（pkce）— テスト

実行: python3 tools/check.py 11.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from pkce import code_challenge, generate_code_verifier, is_valid_verifier, verify_code_verifier

# RFC 7636 Appendix B の例。32 オクテットの乱数から作った code_verifier と、その S256 の code_challenge
# （執筆時に hashlib と base64 で計算し、RFC の値と一致することを確認済み）
RFC7636_OCTETS = bytes([116, 24, 223, 180, 151, 153, 224, 37, 79, 250, 96, 125, 216, 173, 187, 186,
                        22, 212, 37, 77, 105, 214, 191, 240, 91, 88, 5, 88, 83, 132, 141, 121])
RFC7636_VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
RFC7636_CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


class TestPkce(unittest.TestCase):
    def test_rfc7636_example(self):
        verifier = generate_code_verifier(token_bytes=lambda n: RFC7636_OCTETS[:n])
        self.assertEqual(verifier, RFC7636_VERIFIER)
        self.assertEqual(code_challenge(verifier), RFC7636_CHALLENGE)
        self.assertTrue(verify_code_verifier(RFC7636_VERIFIER, RFC7636_CHALLENGE))

    def test_generated_verifiers(self):
        v1, v2 = generate_code_verifier(), generate_code_verifier()
        self.assertNotEqual(v1, v2, "毎回ランダム")
        self.assertEqual(len(v1), 43)
        self.assertTrue(is_valid_verifier(v1))
        self.assertEqual(len(generate_code_verifier(96)), 128)
        for bad in (31, 97):
            with self.assertRaises(ValueError):
                generate_code_verifier(bad)

    def test_is_valid_verifier(self):
        self.assertTrue(is_valid_verifier("a" * 43))
        self.assertTrue(is_valid_verifier("A-._~" * 9))
        self.assertTrue(is_valid_verifier("z" * 128))
        for bad in ("a" * 42, "a" * 129, "a" * 42 + "+", "a" * 42 + "/", "a" * 42 + "=", "あ" * 43, "", None):
            self.assertFalse(is_valid_verifier(bad), repr(bad))  # type: ignore[arg-type]

    def test_wrong_verifier_is_rejected(self):
        # 認可コードを盗んだ攻撃者は、正しい code_verifier を知らない
        self.assertFalse(verify_code_verifier("x" * 43, RFC7636_CHALLENGE))
        self.assertFalse(verify_code_verifier(RFC7636_VERIFIER, RFC7636_CHALLENGE[:-1] + "A"))
        self.assertFalse(verify_code_verifier("short", RFC7636_CHALLENGE))

    def test_plain_method_is_disabled_by_default(self):
        v = "b" * 50
        self.assertEqual(code_challenge(v, "plain"), v)
        self.assertFalse(verify_code_verifier(v, v, "plain"), "plain は既定で拒否")
        self.assertTrue(verify_code_verifier(v, v, "plain", allow_plain=True))
        self.assertFalse(verify_code_verifier(v, v, "S512"))
        with self.assertRaises(ValueError):
            code_challenge(v, "S512")
        with self.assertRaises(ValueError):
            code_challenge("bad verifier!")

    def test_random_round_trips(self):
        rng = random.Random(7636)
        for _ in range(100):
            v = generate_code_verifier(rng.randrange(32, 97), token_bytes=rng.randbytes)
            self.assertTrue(verify_code_verifier(v, code_challenge(v)))


if __name__ == "__main__":
    unittest.main()
