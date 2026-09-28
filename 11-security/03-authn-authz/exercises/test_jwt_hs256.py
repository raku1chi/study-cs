"""11.3 JWT（jwt_hs256）— テスト

実行: python3 tools/check.py 11.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import base64
import hashlib
import hmac
import json
import unittest

from jwt_hs256 import (
    DecodeError,
    ExpiredTokenError,
    InvalidAlgorithmError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidSignatureError,
    JWTError,
    MissingClaimError,
    NotYetValidError,
    b64url_decode,
    b64url_encode,
    decode,
    encode,
)

KEY = b"0123456789abcdef0123456789abcdef"  # 32 バイト（HS256 の最小の長さ）
NOW = 1_800_000_000

# RFC 7515 Appendix A.1（HS256 の JWS の例）。執筆時に署名を計算して一致を確認済み
RFC7515_KEY = base64.urlsafe_b64decode(
    "AyM1SysPpbyDfgZld3umj1qzKObwVMkoqQ-EstJQLr_T-1qS0gZH75aKtMN3Yj0iPS4hcgUuTwjAzZr1Z9CAow=="
)
RFC7515_TOKEN = (
    "eyJ0eXAiOiJKV1QiLA0KICJhbGciOiJIUzI1NiJ9"
    ".eyJpc3MiOiJqb2UiLA0KICJleHAiOjEzMDA4MTkzODAsDQogImh0dHA6Ly9leGFtcGxlLmNvbS9pc19yb290Ijp0cnVlfQ"
    ".dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
)


def seg(obj) -> str:
    """テスト用: JSON を base64url（パディングなし）にする。"""
    raw = obj if isinstance(obj, bytes) else json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def forge(header, payload, key=KEY) -> str:
    """テスト用: 任意のヘッダー・ペイロードに、正しい HS256 の署名を付けたトークンを作る。"""
    signing_input = f"{seg(header)}.{seg(payload)}"
    sig = hmac.new(key, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{seg(sig)}"


class TestExercise1Base64Url(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(b64url_encode(b""), "")
        self.assertEqual(b64url_encode(b"\xff\xfe"), "__4")
        self.assertEqual(b64url_encode(b"\xfb\xff"), "-_8")
        self.assertNotIn("=", b64url_encode(b"a"))

    def test_round_trip(self):
        for n in range(0, 40):
            data = bytes(range(n))
            self.assertEqual(b64url_decode(b64url_encode(data)), data)

    def test_decode_is_strict(self):
        bad = {
            "パディング付き": "YQ==",
            "標準 Base64 の +": "ab+c",
            "標準 Base64 の /": "ab/c",
            "ありえない長さ": "a",
            "空白": "ab c",
            "改行": "abcd\n",
            "正規形でない（末尾の余りビットが 0 でない）": "__5",
        }
        for label, text in bad.items():
            with self.assertRaises(DecodeError, msg=label):
                b64url_decode(text)


class TestExercise2Encode(unittest.TestCase):
    def test_exact_token(self):
        payload = {"sub": "alice", "exp": 2_000_000_000}
        token = encode(payload, KEY)
        expected = forge({"alg": "HS256", "typ": "JWT"}, payload)
        self.assertEqual(token, expected)
        self.assertEqual(token.count("."), 2)

    def test_extra_headers(self):
        token = encode({"exp": NOW + 60}, KEY, headers={"kid": "2026-key-1"})
        header = json.loads(b64url_decode(token.split(".")[0]))
        self.assertEqual(header, {"alg": "HS256", "typ": "JWT", "kid": "2026-key-1"})

    def test_encode_validation(self):
        with self.assertRaises(ValueError):
            encode({"exp": NOW}, b"short-key")
        with self.assertRaises(ValueError):
            encode({"exp": NOW}, KEY, headers={"alg": "none"})
        with self.assertRaises(TypeError):
            encode(["not", "a", "dict"], KEY)  # type: ignore[arg-type]

    def test_payload_is_not_encrypted(self):
        # JWS は「署名」であって「暗号化」ではない。誰でもペイロードを読める
        token = encode({"sub": "alice", "role": "admin", "exp": NOW + 60}, KEY)
        self.assertIn(b'"role":"admin"', b64url_decode(token.split(".")[1]))


class TestExercise3Decode(unittest.TestCase):
    def test_round_trip(self):
        payload = {"sub": "alice", "exp": NOW + 60, "iat": NOW, "iss": "https://idp.example", "aud": "api"}
        token = encode(payload, KEY)
        self.assertEqual(decode(token, KEY, audience="api", issuer="https://idp.example", now=NOW), payload)

    def test_rfc7515_example(self):
        payload = decode(RFC7515_TOKEN, RFC7515_KEY, issuer="joe", now=1300819379)
        self.assertEqual(payload, {"iss": "joe", "exp": 1300819380, "http://example.com/is_root": True})

    def test_exp_boundary_and_leeway(self):
        with self.assertRaises(ExpiredTokenError):
            decode(RFC7515_TOKEN, RFC7515_KEY, now=1300819380)  # exp ちょうどは期限切れ
        self.assertEqual(decode(RFC7515_TOKEN, RFC7515_KEY, now=1300819385, leeway=10)["iss"], "joe")
        with self.assertRaises(ExpiredTokenError):
            decode(RFC7515_TOKEN, RFC7515_KEY, now=1300819390, leeway=10)

    def test_nbf(self):
        token = encode({"exp": NOW + 600, "nbf": NOW + 60}, KEY)
        with self.assertRaises(NotYetValidError):
            decode(token, KEY, now=NOW)
        self.assertIn("nbf", decode(token, KEY, now=NOW + 60))
        self.assertIn("nbf", decode(token, KEY, now=NOW + 30, leeway=30))

    def test_required_claims(self):
        token = encode({"sub": "alice"}, KEY)
        with self.assertRaises(MissingClaimError):
            decode(token, KEY, now=NOW)  # 既定で exp は必須
        self.assertEqual(decode(token, KEY, now=NOW, require=()), {"sub": "alice"})
        with self.assertRaises(MissingClaimError):
            decode(encode({"exp": NOW + 60}, KEY), KEY, now=NOW, require=("exp", "sub"))

    def test_claim_types(self):
        for bad in ("2000000000", True, None, [1]):
            token = encode({"exp": bad}, KEY)
            with self.assertRaises(DecodeError, msg=repr(bad)):
                decode(token, KEY, now=NOW)
        with self.assertRaises(DecodeError):
            decode(encode({"exp": NOW + 60, "iat": "yesterday"}, KEY), KEY, now=NOW)

    def test_issuer(self):
        token = encode({"exp": NOW + 60, "iss": "https://evil.example"}, KEY)
        with self.assertRaises(InvalidIssuerError):
            decode(token, KEY, issuer="https://idp.example", now=NOW)
        with self.assertRaises(MissingClaimError):
            decode(encode({"exp": NOW + 60}, KEY), KEY, issuer="https://idp.example", now=NOW)

    def test_audience(self):
        single = encode({"exp": NOW + 60, "aud": "billing-api"}, KEY)
        multi = encode({"exp": NOW + 60, "aud": ["billing-api", "report-api"]}, KEY)
        self.assertEqual(decode(single, KEY, audience="billing-api", now=NOW)["aud"], "billing-api")
        self.assertIn("report-api", decode(multi, KEY, audience="report-api", now=NOW)["aud"])
        with self.assertRaises(InvalidAudienceError):
            decode(single, KEY, audience="admin-api", now=NOW)
        with self.assertRaises(MissingClaimError):
            decode(encode({"exp": NOW + 60}, KEY), KEY, audience="billing-api", now=NOW)
        with self.assertRaises(InvalidAudienceError):
            decode(encode({"exp": NOW + 60, "aud": 123}, KEY), KEY, audience="billing-api", now=NOW)

    def test_token_for_other_service_is_rejected_without_audience(self):
        # 検証側が audience を指定し忘れても、aud 付きのトークンは受理しない（安全側に倒す）
        token = encode({"exp": NOW + 60, "aud": "other-service"}, KEY)
        with self.assertRaises(InvalidAudienceError):
            decode(token, KEY, now=NOW)

    def test_short_key_rejected(self):
        with self.assertRaises(ValueError):
            decode(encode({"exp": NOW + 60}, KEY), b"short", now=NOW)


class TestExercise3Attacks(unittest.TestCase):
    """攻撃者が作りそうなトークンを、すべて拒否できるか。"""

    def test_alg_none(self):
        payload = {"sub": "admin", "exp": NOW + 60}
        for alg in ("none", "None", "NONE", "nOnE"):
            token = f"{seg({'alg': alg, 'typ': 'JWT'})}.{seg(payload)}."
            with self.assertRaises(InvalidAlgorithmError, msg=alg):
                decode(token, KEY, now=NOW)
            with self.assertRaises(InvalidAlgorithmError, msg="許可リストに none があっても拒否する"):
                decode(token, KEY, now=NOW, algorithms=("HS256", "none"))

    def test_algorithm_confusion(self):
        # RS256 の公開鍵（公開情報）を HMAC の鍵として使って署名した偽トークン
        public_key_pem = b"-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOC...\n-----END PUBLIC KEY-----\n"
        token = forge({"alg": "RS256", "typ": "JWT"}, {"sub": "admin", "exp": NOW + 60}, key=public_key_pem)
        with self.assertRaises(InvalidAlgorithmError):
            decode(token, KEY, now=NOW)
        for alg in ("HS512", "ES256", None, 256):
            with self.assertRaises(InvalidAlgorithmError, msg=repr(alg)):
                decode(forge({"alg": alg}, {"exp": NOW + 60}), KEY, now=NOW)
        with self.assertRaises(InvalidAlgorithmError, msg="alg がない"):
            decode(forge({"typ": "JWT"}, {"exp": NOW + 60}), KEY, now=NOW)
        with self.assertRaises(InvalidAlgorithmError, msg="許可リストが空"):
            decode(encode({"exp": NOW + 60}, KEY), KEY, now=NOW, algorithms=())

    def test_tampered_payload(self):
        token = encode({"sub": "alice", "role": "member", "exp": NOW + 60}, KEY)
        h, _, s = token.split(".")
        evil = f"{h}.{seg({'sub': 'alice', 'role': 'admin', 'exp': NOW + 60})}.{s}"
        with self.assertRaises(InvalidSignatureError):
            decode(evil, KEY, now=NOW)

    def test_wrong_key_and_bad_signatures(self):
        token = encode({"exp": NOW + 60}, KEY)
        with self.assertRaises(InvalidSignatureError):
            decode(token, b"x" * 32, now=NOW)
        h, p, _ = token.split(".")
        with self.assertRaises(InvalidSignatureError):
            decode(f"{h}.{p}.", KEY, now=NOW)
        with self.assertRaises(JWTError):
            decode(f"{h}.{p}.not*base64", KEY, now=NOW)

    def test_non_canonical_signature(self):
        token = encode({"exp": NOW + 60}, KEY)
        h, p, s = token.split(".")
        alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        # 32 バイトの署名は 43 文字。最後の文字の下位 2 ビットは使われない
        twin = s[:-1] + alphabet[alphabet.index(s[-1]) ^ 1]
        self.assertEqual(base64.urlsafe_b64decode(twin + "="), base64.urlsafe_b64decode(s + "="),
                         "（前提の確認）同じバイト列を表す別の文字列")
        with self.assertRaises(DecodeError):
            decode(f"{h}.{p}.{twin}", KEY, now=NOW)

    def test_structure(self):
        token = encode({"exp": NOW + 60}, KEY)
        for bad in ("", "abc", token + ".extra", token.replace(".", "", 1), 12345):
            with self.assertRaises(DecodeError, msg=repr(bad)):
                decode(bad, KEY, now=NOW)  # type: ignore[arg-type]

    def test_non_object_json(self):
        with self.assertRaises(DecodeError):
            decode(forge({"alg": "HS256"}, [1, 2, 3]), KEY, now=NOW)
        header_array = f"{seg(['HS256'])}.{seg({'exp': NOW + 60})}.{seg(b'x' * 32)}"
        with self.assertRaises(DecodeError):
            decode(header_array, KEY, now=NOW)
        not_json = f"{seg(b'not json')}.{seg({'exp': NOW + 60})}.{seg(b'x' * 32)}"
        with self.assertRaises(DecodeError):
            decode(not_json, KEY, now=NOW)

    def test_crit_header_rejected(self):
        token = encode({"exp": NOW + 60}, KEY, headers={"crit": ["b64"], "b64": False})
        with self.assertRaises(DecodeError):
            decode(token, KEY, now=NOW)

    def test_error_hierarchy(self):
        for cls in (DecodeError, InvalidAlgorithmError, InvalidSignatureError, ExpiredTokenError,
                    NotYetValidError, InvalidAudienceError, InvalidIssuerError, MissingClaimError):
            self.assertTrue(issubclass(cls, JWTError), cls.__name__)


if __name__ == "__main__":
    unittest.main()
