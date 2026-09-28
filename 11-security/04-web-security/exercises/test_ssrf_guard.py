"""11.4 SSRF 対策の URL 検証（ssrf_guard）— テスト

実行: python3 tools/check.py 11.4   （またはこのディレクトリで python3 -m unittest -v）

このテストは外部ネットワークに一切アクセスしません。名前解決は「注入したリゾルバ」で行います。
"""
import unittest

from ssrf_guard import (
    SsrfError,
    classify_address,
    is_safe_address,
    parse_loose_ipv4,
    validate_redirect_chain,
    validate_url,
)


def fake_resolver(table):
    def resolve(host):
        if host not in table:
            raise SsrfError(f"名前解決の失敗（テスト）: {host}")
        return list(table[host])
    return resolve


class TestExercise1Classify(unittest.TestCase):
    def test_loose_ipv4(self):
        self.assertEqual(parse_loose_ipv4("2130706433"), "127.0.0.1")  # 10 進
        self.assertEqual(parse_loose_ipv4("0x7f000001"), "127.0.0.1")  # 16 進
        self.assertEqual(parse_loose_ipv4("0177.0.0.1"), "127.0.0.1")  # 8 進
        self.assertEqual(parse_loose_ipv4("127.1"), "127.0.0.1")  # 省略記法
        self.assertEqual(parse_loose_ipv4("192.168.257"), "192.168.1.1")
        self.assertEqual(parse_loose_ipv4("0xdeadbeef"), "222.173.190.239")
        for bad in ("example.com", "1.2.3.4.5", "256.1.1.1", "10.0.0.256", "", "1..2", "0x", "999999999999"):
            self.assertIsNone(parse_loose_ipv4(bad), bad)

    def test_classify_blocked(self):
        cases = {
            "127.0.0.1": "loopback",
            "0.0.0.0": "unspecified",
            "10.0.0.5": "private",
            "172.16.0.1": "private",
            "192.168.1.1": "private",
            "169.254.169.254": "link-local",  # クラウドのメタデータ
            "100.64.0.1": "shared",  # CGNAT
            "224.0.0.1": "multicast",
            "::1": "loopback",
            "fe80::1": "link-local",
            "fc00::1": "private",
            "::": "unspecified",
            "::ffff:127.0.0.1": "loopback",  # IPv4 射影
            "::ffff:169.254.169.254": "link-local",
            "::ffff:10.0.0.1": "private",
        }
        for ip, reason in cases.items():
            self.assertEqual(classify_address(ip), reason, ip)
            self.assertFalse(is_safe_address(ip), ip)

    def test_classify_global(self):
        for ip in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111", "::ffff:8.8.8.8"):
            self.assertEqual(classify_address(ip), "global", ip)
            self.assertTrue(is_safe_address(ip), ip)


class TestExercise2ValidateUrl(unittest.TestCase):
    def setUp(self):
        self.resolve = fake_resolver({
            "api.example.com": ["93.184.216.34"],
            "internal.example.com": ["10.0.0.5"],
            "rebinding.example.com": ["8.8.8.8", "127.0.0.1"],  # 複数の A レコード
        })

    def test_allows_public_host(self):
        safe = validate_url("https://api.example.com/v1/items?q=1", self.resolve)
        self.assertEqual((safe.scheme, safe.host, safe.port), ("https", "api.example.com", 443))
        self.assertEqual(safe.addresses, ("93.184.216.34",))

    def test_blocks_by_hostname_resolution(self):
        with self.assertRaises(SsrfError):
            validate_url("https://internal.example.com/", self.resolve)

    def test_blocks_ip_literals(self):
        for url in [
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
            "http://10.0.0.5:8080/admin",
            "http://2130706433/",  # 10 進
            "http://0x7f000001/",  # 16 進
            "http://0177.0.0.1/",  # 8 進
            "http://[::ffff:127.0.0.1]/",
        ]:
            with self.assertRaises(SsrfError, msg=url):
                validate_url(url, self.resolve)

    def test_blocks_if_any_resolved_address_is_internal(self):
        with self.assertRaises(SsrfError):
            validate_url("https://rebinding.example.com/", self.resolve)

    def test_scheme_rules(self):
        for url in ["file:///etc/passwd", "gopher://127.0.0.1/", "ftp://example.com/", "javascript:alert(1)"]:
            with self.assertRaises(SsrfError, msg=url):
                validate_url(url, self.resolve)
        # http を許すかどうかは呼び出し側が決められる
        with self.assertRaises(SsrfError):
            validate_url("http://api.example.com/", self.resolve, allowed_schemes=frozenset({"https"}))
        self.assertTrue(validate_url("http://api.example.com/", self.resolve).host, "既定では http も許可")

    def test_rejects_userinfo_and_bad_host(self):
        with self.assertRaises(SsrfError):
            validate_url("https://user:pass@api.example.com/", self.resolve)
        with self.assertRaises(SsrfError):
            validate_url("https://evil.example.com@api.example.com/", self.resolve)
        for url in ["https:///path", "not a url", "http:///", "https://exam ple.com/"]:
            with self.assertRaises(SsrfError, msg=url):
                validate_url(url, self.resolve)

    def test_numeric_hostname_rejected(self):
        # DNS を数値名に引かせるすり抜けを防ぐ
        with self.assertRaises(SsrfError):
            validate_url("http://12345/", fake_resolver({"12345": ["10.0.0.1"]}))

    def test_case_insensitive_scheme_and_host(self):
        safe = validate_url("HTTPS://API.EXAMPLE.COM/", self.resolve)
        self.assertEqual(safe.scheme, "https")
        self.assertEqual(safe.host, "api.example.com")


class TestExercise3Redirects(unittest.TestCase):
    def setUp(self):
        self.resolve = fake_resolver({
            "safe.example.com": ["93.184.216.34"],
            "also-safe.example.com": ["1.1.1.1"],
        })

    def test_allows_safe_chain(self):
        chain = validate_redirect_chain(
            "https://safe.example.com/a",
            ["https://also-safe.example.com/b"],
            self.resolve,
        )
        self.assertEqual(len(chain), 2)
        self.assertEqual(chain[-1].host, "also-safe.example.com")

    def test_blocks_redirect_to_metadata(self):
        # よくあるすり抜け: 入口は安全な公開 URL、リダイレクト先がメタデータ
        with self.assertRaises(SsrfError):
            validate_redirect_chain(
                "https://safe.example.com/redirect",
                ["http://169.254.169.254/latest/meta-data/iam/security-credentials/"],
                self.resolve,
            )

    def test_blocks_redirect_to_loopback_decimal(self):
        with self.assertRaises(SsrfError):
            validate_redirect_chain("https://safe.example.com/", ["http://2130706433/"], self.resolve)

    def test_too_many_redirects(self):
        with self.assertRaises(SsrfError):
            validate_redirect_chain(
                "https://safe.example.com/",
                ["https://safe.example.com/"] * 6,
                self.resolve,
                max_redirects=5,
            )


if __name__ == "__main__":
    unittest.main()
