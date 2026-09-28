"""11.5 秘密情報スキャン（secret_scan）— テスト

実行: python3 tools/check.py 11.5   （またはこのディレクトリで python3 -m unittest -v）

ここで使う鍵やトークンはすべて「明らかに偽物」の例です（AWS の公式ドキュメントの例値など）。
"""
import unittest

from secret_scan import (
    Finding,
    is_allowlisted,
    scan_line,
    scan_text,
    shannon_entropy,
)


class TestExercise1Entropy(unittest.TestCase):
    def test_known_values(self):
        self.assertEqual(shannon_entropy(""), 0.0)
        self.assertEqual(shannon_entropy("aaaaaaaa"), 0.0)
        self.assertEqual(str(shannon_entropy("aaaa")), "0.0", "-0.0 ではなく 0.0")
        self.assertAlmostEqual(shannon_entropy("ab"), 1.0)
        self.assertAlmostEqual(shannon_entropy("0123"), 2.0)
        self.assertAlmostEqual(shannon_entropy("0123456789abcdef" * 2), 4.0)

    def test_random_looking_is_higher_than_words(self):
        self.assertGreater(
            shannon_entropy("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
            shannon_entropy("the quick brown fox jumps over the lazy dog"),
        )


class TestExercise2Patterns(unittest.TestCase):
    def test_aws_access_key_id(self):
        findings = scan_line('aws_key = "AKIAIOSFODNN7EXAMPLE"', 1)
        self.assertEqual([(f.kind, f.secret) for f in findings],
                         [("aws-access-key-id", "AKIAIOSFODNN7EXAMPLE")])

    def test_github_token(self):
        line = 'token = "ghp_1234567890abcdefABCDEF1234567890abcd"'
        kinds = [f.kind for f in scan_line(line, 1)]
        self.assertIn("github-token", kinds)

    def test_private_key_header(self):
        for header in ("-----BEGIN RSA PRIVATE KEY-----",
                       "-----BEGIN OPENSSH PRIVATE KEY-----",
                       "-----BEGIN PRIVATE KEY-----"):
            findings = scan_line(header, 1)
            self.assertTrue(any(f.kind == "private-key" for f in findings), header)

    def test_high_entropy_string(self):
        findings = scan_line('secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"', 1)
        self.assertEqual([f.kind for f in findings], ["high-entropy"])
        self.assertEqual(findings[0].secret, "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY")

    def test_normal_text_is_not_flagged(self):
        for line in [
            "# これはただのコメントです。秘密ではありません。",
            'message = "the quick brown fox jumps over the lazy dog"',
            "total = subtotal + tax_amount * quantity",
            'url = "https://example.com/api/v1/users"',
        ]:
            self.assertEqual(scan_line(line, 1), [], line)

    def test_short_high_entropy_is_ignored(self):
        # 短い 16 進などは誤検知が多いので、長さのしきい値で除外する
        self.assertEqual(scan_line('id = "a1b2c3d4"', 1), [])

    def test_no_double_report(self):
        # 既知の形式で報告したものを、高エントロピーで重ねて報告しない
        findings = scan_line('key="AKIAIOSFODNN7EXAMPLE"', 1)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].kind, "aws-access-key-id")

    def test_redacted(self):
        f = Finding(1, "aws-access-key-id", "AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(f.redacted, "AKIA...LE")
        self.assertNotIn("IOSFODNN7", f.redacted)
        self.assertEqual(Finding(1, "x", "abcd").redacted, "****")


class TestExercise2Allowlist(unittest.TestCase):
    def test_allowlist_marker(self):
        self.assertTrue(is_allowlisted('key = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret'))
        self.assertTrue(is_allowlisted("x = 1  # gitleaks:allow"))
        self.assertFalse(is_allowlisted('key = "AKIAIOSFODNN7EXAMPLE"'))

    def test_allowlisted_line_yields_nothing(self):
        line = 'test_key = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret（テスト用の偽値）'
        self.assertEqual(scan_line(line, 1), [])


class TestExercise2ScanText(unittest.TestCase):
    SOURCE = """\
import os

AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
DB_HOST = "db.internal.example.com"
GITHUB_TOKEN = "ghp_1234567890abcdefABCDEF1234567890abcd"
LEGACY_KEY = "AKIAIOSFODNN7EXAMPLE"  # pragma: allowlist secret
# 通常のコメント行。ここには秘密はありません。
"""

    def test_line_numbers_and_kinds(self):
        findings = scan_text(self.SOURCE)
        self.assertEqual(
            [(f.line, f.kind) for f in findings],
            [(3, "aws-access-key-id"), (4, "high-entropy"), (6, "github-token")],
        )

    def test_allowlisted_line_skipped(self):
        findings = scan_text(self.SOURCE)
        self.assertFalse(any(f.line == 7 for f in findings), "許可コメントのある 7 行目は無視")

    def test_empty(self):
        self.assertEqual(scan_text(""), [])

    def test_threshold_is_configurable(self):
        line = 'x = "abcdefghijklmnopqrst"'  # 20 文字だが全部異なる → エントロピー高め
        self.assertEqual(scan_text(line, min_entropy=5.0), [], "しきい値を上げれば検出されない")
        self.assertTrue(scan_text(line, min_entropy=4.0))


if __name__ == "__main__":
    unittest.main()
