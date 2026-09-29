"""5.4 Webの仕組みとネットワーク構成 — テスト（cors）

実行: python3 tools/check.py 5.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from cors import (
    CorsPolicy,
    actual_response_headers,
    browser_cors_check,
    browser_preflight_check,
    origin_allowed,
    preflight_response_headers,
)

APP = "https://app.example.com"


def preflight(policy, origin, method, headers=()):
    req = {"Origin": origin, "Access-Control-Request-Method": method}
    if headers:
        req["Access-Control-Request-Headers"] = ",".join(headers)
    return preflight_response_headers(policy, req)


class TestPolicyValidation(unittest.TestCase):
    def test_wildcard_with_credentials_is_rejected(self):
        with self.assertRaises(ValueError, msg="Cookie 付きで「どこからでも読める」は禁止"):
            CorsPolicy(["*"], allow_credentials=True)

    def test_wildcard_headers_with_credentials_is_rejected(self):
        with self.assertRaises(ValueError):
            CorsPolicy([APP], allowed_headers=["*"], allow_credentials=True)

    def test_invalid_origin_entries(self):
        for bad in ("null", "app.example.com", "https://app.example.com/", "https://*", "ftp://a.example.com"):
            with self.assertRaises(ValueError, msg=bad):
                CorsPolicy([bad])


class TestOriginMatching(unittest.TestCase):
    def test_exact(self):
        p = CorsPolicy([APP, "http://localhost:3000"])
        self.assertTrue(origin_allowed(p, APP))
        self.assertTrue(origin_allowed(p, "http://localhost:3000"))
        self.assertFalse(origin_allowed(p, "http://app.example.com"), "スキームが違えば別のオリジン")
        self.assertFalse(origin_allowed(p, "https://app.example.com:8443"), "ポートが違えば別のオリジン")
        self.assertFalse(origin_allowed(p, "http://localhost:3001"))
        self.assertFalse(origin_allowed(p, None))
        self.assertFalse(origin_allowed(p, "null"))

    def test_default_port_is_same_origin(self):
        p = CorsPolicy(["https://app.example.com:443"])
        self.assertTrue(origin_allowed(p, APP))

    def test_subdomain_pattern(self):
        p = CorsPolicy(["https://*.example.com"])
        self.assertTrue(origin_allowed(p, "https://app.example.com"))
        self.assertTrue(origin_allowed(p, "https://a.b.example.com"))
        self.assertFalse(origin_allowed(p, "https://example.com"), "サブドメインだけ")
        self.assertFalse(origin_allowed(p, "https://evil-example.com"), "単純な endswith の罠")
        self.assertFalse(origin_allowed(p, "https://example.com.evil.net"))
        self.assertFalse(origin_allowed(p, "http://app.example.com"))

    def test_wildcard(self):
        p = CorsPolicy(["*"])
        self.assertTrue(origin_allowed(p, "https://anything.example.net"))
        self.assertTrue(origin_allowed(p, "null"))


class TestServerSide(unittest.TestCase):
    def test_preflight_allowed(self):
        p = CorsPolicy([APP], allowed_methods=["GET", "POST", "PUT"], allowed_headers=["Content-Type", "X-Request-Id"],
                       max_age=600)
        h = preflight(p, APP, "PUT", ["content-type", "x-request-id"])
        self.assertEqual(h, {
            "Access-Control-Allow-Origin": APP,
            "Access-Control-Allow-Methods": "GET, POST, PUT",
            "Access-Control-Allow-Headers": "content-type, x-request-id",
            "Access-Control-Max-Age": "600",
            "Vary": "Origin",
        })

    def test_preflight_rejections(self):
        p = CorsPolicy([APP], allowed_methods=["GET", "POST"], allowed_headers=["content-type"])
        self.assertEqual(preflight(p, "https://evil.example.net", "POST"), {"Vary": "Origin"}, "許可しないオリジン")
        self.assertEqual(preflight(p, APP, "DELETE"), {"Vary": "Origin"}, "許可しないメソッド")
        self.assertEqual(preflight(p, APP, "POST", ["x-secret"]), {"Vary": "Origin"}, "許可しないヘッダ")
        self.assertEqual(preflight_response_headers(p, {"Origin": APP}), {"Vary": "Origin"},
                         "Access-Control-Request-Method のないものはプリフライトではない")

    def test_preflight_with_credentials(self):
        p = CorsPolicy([APP], allowed_methods=["GET", "PATCH"], allowed_headers=["authorization"], allow_credentials=True)
        h = preflight(p, APP, "PATCH", ["Authorization"])
        self.assertEqual(h["Access-Control-Allow-Origin"], APP, "資格情報付きでは * ではなくオリジンを返す")
        self.assertEqual(h["Access-Control-Allow-Credentials"], "true")
        self.assertEqual(h["Access-Control-Allow-Headers"], "authorization")

    def test_wildcard_headers_do_not_cover_authorization(self):
        p = CorsPolicy(["*"], allowed_methods=["GET"], allowed_headers=["*"])
        self.assertEqual(preflight(p, APP, "GET", ["x-anything"])["Access-Control-Allow-Origin"], "*")
        self.assertEqual(preflight(p, APP, "GET", ["authorization"]), {}, "Authorization は明示が必要")

    def test_wildcard_policy_has_no_vary(self):
        p = CorsPolicy(["*"])
        self.assertEqual(actual_response_headers(p, {"Origin": APP}), {"Access-Control-Allow-Origin": "*"})

    def test_actual_response(self):
        p = CorsPolicy([APP], exposed_headers=["X-Total-Count", "ETag"], allow_credentials=True)
        self.assertEqual(actual_response_headers(p, {"origin": APP}), {
            "Access-Control-Allow-Origin": APP,
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Expose-Headers": "X-Total-Count, ETag",
            "Vary": "Origin",
        })
        self.assertEqual(actual_response_headers(p, {"Origin": "https://evil.example.net"}), {"Vary": "Origin"})
        self.assertEqual(actual_response_headers(p, {}), {"Vary": "Origin"}, "Origin のない（同一オリジンの）リクエスト")


class TestBrowserSide(unittest.TestCase):
    def test_cors_check(self):
        self.assertTrue(browser_cors_check({"Access-Control-Allow-Origin": "*"}, origin=APP, credentials=False))
        self.assertFalse(browser_cors_check({"Access-Control-Allow-Origin": "*"}, origin=APP, credentials=True),
                         "資格情報付きのリクエストに * は通用しない")
        self.assertTrue(browser_cors_check({"access-control-allow-origin": APP}, origin=APP, credentials=False))
        self.assertFalse(browser_cors_check({"Access-Control-Allow-Origin": APP}, origin=APP, credentials=True),
                         "Allow-Credentials: true がない")
        self.assertTrue(browser_cors_check({"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Credentials": "true"},
                                           origin=APP, credentials=True))
        self.assertFalse(browser_cors_check({"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Credentials": "True"},
                                            origin=APP, credentials=True), "値は小文字の true だけ")
        self.assertFalse(browser_cors_check({"Access-Control-Allow-Origin": "https://other.example.com"},
                                            origin=APP, credentials=False))
        self.assertFalse(browser_cors_check({}, origin=APP, credentials=False))

    def test_preflight_check(self):
        ok = {"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Methods": "PUT, DELETE",
              "Access-Control-Allow-Headers": "Content-Type, X-Request-Id"}
        self.assertTrue(browser_preflight_check(ok, origin=APP, method="PUT", request_headers=["content-type"],
                                                credentials=False))
        self.assertFalse(browser_preflight_check(ok, origin=APP, method="PATCH", request_headers=[], credentials=False))
        self.assertTrue(browser_preflight_check(ok, origin=APP, method="POST", request_headers=["x-request-id"],
                                                credentials=False), "GET・HEAD・POST はメソッドの許可が不要")
        self.assertFalse(browser_preflight_check(ok, origin=APP, method="PUT", request_headers=["x-other"],
                                                 credentials=False))

    def test_preflight_wildcards(self):
        star = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Methods": "*", "Access-Control-Allow-Headers": "*"}
        self.assertTrue(browser_preflight_check(star, origin=APP, method="DELETE", request_headers=["x-any"],
                                                credentials=False))
        self.assertFalse(browser_preflight_check(star, origin=APP, method="DELETE", request_headers=["authorization"],
                                                 credentials=False), "ワイルドカードは Authorization を含まない")
        cred = {"Access-Control-Allow-Origin": APP, "Access-Control-Allow-Credentials": "true",
                "Access-Control-Allow-Methods": "*", "Access-Control-Allow-Headers": "*"}
        self.assertFalse(browser_preflight_check(cred, origin=APP, method="DELETE", request_headers=[], credentials=True),
                         "資格情報付きでは * は文字どおりのメソッド名としてしか扱われない")
        self.assertFalse(browser_preflight_check(cred, origin=APP, method="GET", request_headers=["x-any"],
                                                 credentials=True))

    def test_end_to_end(self):
        # サーバー側の設定と、ブラウザ側の判定を組み合わせる
        p = CorsPolicy(["https://*.example.com"], allowed_methods=["GET", "POST", "DELETE"],
                       allowed_headers=["content-type", "authorization"], allow_credentials=True, max_age=300)
        for origin, method, headers, expected in [
            ("https://app.example.com", "DELETE", ["authorization"], True),
            ("https://app.example.com", "PUT", [], False),
            ("https://evil.example.net", "DELETE", [], False),
            ("https://admin.example.com", "POST", ["content-type", "x-debug"], False),
        ]:
            resp = preflight(p, origin, method, headers)
            self.assertEqual(browser_preflight_check(resp, origin=origin, method=method, request_headers=headers,
                                                     credentials=True), expected, (origin, method, headers))


if __name__ == "__main__":
    unittest.main()
