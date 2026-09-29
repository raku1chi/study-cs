"""9.4 API設計 — Webhook の署名と検証のテスト

実行: python3 tools/check.py 9.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import hashlib
import hmac
import unittest
from unittest import mock

import webhook_sig
from webhook_sig import (
    InvalidHeaderError,
    ReplayError,
    ReplayGuard,
    SignatureMismatchError,
    TimestampOutsideToleranceError,
    WebhookVerificationError,
    build_signature_header,
    compute_signature,
    parse_signature_header,
    verify,
)

OLD = b"whsec_old_0123456789"
NEW = b"whsec_new_abcdefghij"
BODY = '{"type":"payment.succeeded","data":{"amount":1000,"currency":"JPY"}}'.encode()
T = 1_767_225_600  # 2026-01-01T00:00:00Z


def reference_signature(secret, msg_id, ts, body):
    return hmac.new(secret, f"{msg_id}.{ts}.".encode() + body, hashlib.sha256).hexdigest()


class TestExercise1Signing(unittest.TestCase):
    def test_compute_signature(self):
        self.assertEqual(compute_signature(NEW, "msg_1", T, BODY), reference_signature(NEW, "msg_1", T, BODY))
        self.assertNotEqual(compute_signature(NEW, "msg_1", T, BODY), compute_signature(NEW, "msg_2", T, BODY))

    def test_header_with_rotation(self):
        header = build_signature_header([OLD, NEW], "msg_1", T, BODY)
        self.assertEqual(header, f"t={T},v1={reference_signature(OLD, 'msg_1', T, BODY)},"
                                 f"v1={reference_signature(NEW, 'msg_1', T, BODY)}")
        with self.assertRaises(ValueError):
            build_signature_header([], "msg_1", T, BODY)

    def test_msg_id_is_restricted(self):
        for bad in ("", "a.b", "has space", "x" * 129, "日本"):
            with self.assertRaises(InvalidHeaderError, msg=repr(bad)):
                compute_signature(NEW, bad, T, BODY)

    def test_parse_header(self):
        self.assertEqual(parse_signature_header("t=10,v1=abc"), (10, ["abc"]))
        self.assertEqual(parse_signature_header(" t=10 , v1=abc , v2=zzz , v1=def "), (10, ["abc", "def"]))
        for bad in ("", "t=10", "v1=abc", "t=ten,v1=abc", "t=10,t=11,v1=abc", "t=10,v1abc",
                    "t=-1,v1=abc", "t=10,v2=only-new-scheme", "garbage"):
            with self.assertRaises(InvalidHeaderError, msg=repr(bad)):
                parse_signature_header(bad)


class TestExercise1Verify(unittest.TestCase):
    def test_valid_signature(self):
        header = build_signature_header([NEW], "msg_1", T, BODY)
        self.assertEqual(verify([NEW], "msg_1", header, BODY, now=T + 10), T)

    def test_key_rotation(self):
        # 送信側がまだ古い鍵だけで署名していても、受信側が新旧両方を持っていれば通る
        old_only = build_signature_header([OLD], "msg_1", T, BODY)
        self.assertEqual(verify([NEW, OLD], "msg_1", old_only, BODY, now=T), T)
        # 送信側が新旧両方で署名していれば、新しい鍵だけに切り替えた受信側でも通る
        both = build_signature_header([OLD, NEW], "msg_1", T, BODY)
        self.assertEqual(verify([NEW], "msg_1", both, BODY, now=T), T)
        with self.assertRaises(SignatureMismatchError):
            verify([NEW], "msg_1", old_only, BODY, now=T)

    def test_tampering_is_detected(self):
        header = build_signature_header([NEW], "msg_1", T, BODY)
        with self.assertRaises(SignatureMismatchError, msg="本文の改ざん"):
            verify([NEW], "msg_1", header, BODY.replace(b"1000", b"9000"), now=T)
        with self.assertRaises(SignatureMismatchError, msg="別の通知の ID"):
            verify([NEW], "msg_2", header, BODY, now=T)
        forged = header.replace(f"t={T}", f"t={T + 60}")
        with self.assertRaises(SignatureMismatchError, msg="タイムスタンプの書き換え"):
            verify([NEW], "msg_1", forged, BODY, now=T + 60)
        with self.assertRaises(SignatureMismatchError, msg="別の鍵"):
            verify([b"attacker-guess"], "msg_1", header, BODY, now=T)

    def test_non_ascii_signature_is_a_mismatch_not_a_crash(self):
        # 攻撃者が作ったヘッダーで TypeError（= 500）にならず、検証の失敗として扱えること
        with self.assertRaises(SignatureMismatchError):
            verify([NEW], "msg_1", f"t={T},v1=署名ではない", BODY, now=T)

    def test_timestamp_tolerance(self):
        header = build_signature_header([NEW], "msg_1", T, BODY)
        self.assertEqual(verify([NEW], "msg_1", header, BODY, now=T + 300), T, "境界ちょうどは許容")
        self.assertEqual(verify([NEW], "msg_1", header, BODY, now=T - 300), T)
        with self.assertRaises(TimestampOutsideToleranceError, msg="古すぎる"):
            verify([NEW], "msg_1", header, BODY, now=T + 301)
        with self.assertRaises(TimestampOutsideToleranceError, msg="未来すぎる"):
            verify([NEW], "msg_1", header, BODY, now=T - 301)
        self.assertEqual(verify([NEW], "msg_1", header, BODY, now=T + 3600, tolerance=3600), T)

    def test_all_errors_share_a_base_class(self):
        for cls in (InvalidHeaderError, TimestampOutsideToleranceError, SignatureMismatchError, ReplayError):
            self.assertTrue(issubclass(cls, WebhookVerificationError))
        with self.assertRaises(WebhookVerificationError):
            verify([NEW], "msg_1", "nonsense", BODY, now=T)

    def test_uses_constant_time_comparison(self):
        header = build_signature_header([NEW], "msg_1", T, BODY)
        real = hmac.compare_digest
        with mock.patch("hmac.compare_digest", side_effect=real) as patched:
            if hasattr(webhook_sig, "compare_digest"):  # from hmac import compare_digest としていても検出する
                with mock.patch.object(webhook_sig, "compare_digest", side_effect=real) as patched2:
                    verify([NEW], "msg_1", header, BODY, now=T)
                    calls = patched.call_count + patched2.call_count
            else:
                verify([NEW], "msg_1", header, BODY, now=T)
                calls = patched.call_count
        self.assertGreater(calls, 0, "署名の比較に hmac.compare_digest を使っていない")


class TestExercise1ReplayGuard(unittest.TestCase):
    def test_duplicate_is_rejected(self):
        guard = ReplayGuard(window=300)
        guard.check("msg_1", T, now=T)
        guard.check("msg_2", T, now=T + 1)
        with self.assertRaises(ReplayError):
            guard.check("msg_1", T, now=T + 2)

    def test_old_ids_are_forgotten(self):
        guard = ReplayGuard(window=300)
        for i in range(100):
            guard.check(f"msg_{i}", T + i, now=T + i)
        self.assertEqual(len(guard), 100)
        guard.check("msg_new", T + 400, now=T + 400)  # T+100 より古い記録は消える
        self.assertEqual(len(guard), 1)


if __name__ == "__main__":
    unittest.main()
