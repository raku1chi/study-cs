"""5.4 Webの仕組みとネットワーク構成 — テスト（url_tools）

実行: python3 tools/check.py 5.4   （またはこのディレクトリで python3 -m unittest -v）

参照の解決のテストは、RFC 3986 の 5.4 節に載っている例をそのまま使っています。
"""
import random
import unittest

from url_tools import URL, normalize_url, parse_url, remove_dot_segments, resolve_reference

BASE = "http://a/b/c/d;p?q"

# RFC 3986 5.4.1 通常の例
NORMAL_EXAMPLES = {
    "g:h": "g:h", "g": "http://a/b/c/g", "./g": "http://a/b/c/g", "g/": "http://a/b/c/g/",
    "/g": "http://a/g", "//g": "http://g", "?y": "http://a/b/c/d;p?y", "g?y": "http://a/b/c/g?y",
    "#s": "http://a/b/c/d;p?q#s", "g#s": "http://a/b/c/g#s", "g?y#s": "http://a/b/c/g?y#s",
    ";x": "http://a/b/c/;x", "g;x": "http://a/b/c/g;x", "g;x?y#s": "http://a/b/c/g;x?y#s",
    "": "http://a/b/c/d;p?q", ".": "http://a/b/c/", "./": "http://a/b/c/", "..": "http://a/b/",
    "../": "http://a/b/", "../g": "http://a/b/g", "../..": "http://a/", "../../": "http://a/",
    "../../g": "http://a/g",
}

# RFC 3986 5.4.2 異常な例（ルートより上に戻ろうとする、ドットを含む名前など）
ABNORMAL_EXAMPLES = {
    "../../../g": "http://a/g", "../../../../g": "http://a/g", "/./g": "http://a/g", "/../g": "http://a/g",
    "g.": "http://a/b/c/g.", ".g": "http://a/b/c/.g", "g..": "http://a/b/c/g..", "..g": "http://a/b/c/..g",
    "./../g": "http://a/b/g", "./g/.": "http://a/b/c/g/", "g/./h": "http://a/b/c/g/h", "g/../h": "http://a/b/c/h",
    "g;x=1/./y": "http://a/b/c/g;x=1/y", "g;x=1/../y": "http://a/b/c/y", "g?y/./x": "http://a/b/c/g?y/./x",
    "g?y/../x": "http://a/b/c/g?y/../x", "g#s/./x": "http://a/b/c/g#s/./x", "g#s/../x": "http://a/b/c/g#s/../x",
    "http:g": "http:g",  # 厳格な解釈（互換性のための解釈では http://a/b/c/g）
}


class TestParseUrl(unittest.TestCase):
    def test_full_url(self):
        u = parse_url("https://user:pw@Example.COM:8443/a/b?x=1&y=2#frag")
        self.assertEqual(u, URL(scheme="https", userinfo="user:pw", host="Example.COM", port=8443,
                                path="/a/b", query="x=1&y=2", fragment="frag"))
        self.assertEqual(u.authority, "user:pw@Example.COM:8443")

    def test_components_may_be_absent_or_empty(self):
        self.assertEqual(parse_url("http://example.com"), URL("http", None, "example.com", None, "", None, None))
        self.assertEqual(parse_url("http://example.com/?#"), URL("http", None, "example.com", None, "/", "", ""),
                         "空のクエリ（?）と、クエリがないこと（None）は区別する")
        self.assertEqual(parse_url("http://example.com:/").port, None, "空のポートは指定なしと同じ")

    def test_ipv6_literal(self):
        u = parse_url("http://[2001:DB8::1]:8080/index.html")
        self.assertEqual((u.host, u.port, u.path), ("[2001:DB8::1]", 8080, "/index.html"))

    def test_without_authority(self):
        self.assertEqual(parse_url("mailto:someone@example.com"), URL("mailto", None, None, None, "someone@example.com"))
        self.assertEqual(parse_url("urn:isbn:0451450523").path, "isbn:0451450523")
        u = parse_url("file:///etc/hosts")
        self.assertEqual((u.host, u.path), ("", "/etc/hosts"), "オーソリティが空（//）とない（None）は区別する")

    def test_relative_references(self):
        self.assertEqual(parse_url("//g"), URL(None, None, "g", None, ""))
        self.assertEqual(parse_url("?y"), URL(path="", query="y"))
        self.assertEqual(parse_url("g;x?y#s"), URL(path="g;x", query="y", fragment="s"))
        self.assertEqual(parse_url(""), URL())

    def test_round_trip(self):
        for text in ["https://user:pw@Example.COM:8443/a/b?x=1#frag", "http://example.com", "http://example.com/?#",
                     "mailto:someone@example.com", "file:///etc/hosts", "//g", "?y", "g;x?y#s", "",
                     "http://[2001:db8::1]:8080/", "https://example.com/a%2Fb?q=%E6%97%A5"]:
            self.assertEqual(str(parse_url(text)), text)

    def test_invalid(self):
        for bad in ["http://exa mple.com/", "http://example.com:99999/", "http://example.com:8a/",
                    "ht^tp://x/", "1http://x/", "http://例え.jp/", "http://x/%zz", "http://x/%4", "http://x/a#b#c",
                    "http://x/<script>", "http://[::1/", "http://[::1]x/", "http://x/[a]", 'http://x/"q"']:
            with self.assertRaises(ValueError, msg=bad):
                parse_url(bad)


class TestRemoveDotSegments(unittest.TestCase):
    def test_rfc_examples(self):
        self.assertEqual(remove_dot_segments("/a/b/c/./../../g"), "/a/g")
        self.assertEqual(remove_dot_segments("mid/content=5/../6"), "mid/6")

    def test_edge_cases(self):
        cases = {"": "", ".": "", "..": "", "/.": "/", "/..": "/", "/../a": "/a", "a/b/..": "a/",
                 "/a/b/../../..": "/", "/a/./b/./": "/a/b/", "/a//b/../c": "/a//c", "../a/./b": "a/b",
                 "/a/..b/.c/c.": "/a/..b/.c/c.", "/a/b/c": "/a/b/c"}
        for path, expected in cases.items():
            self.assertEqual(remove_dot_segments(path), expected, repr(path))


class TestResolveReference(unittest.TestCase):
    def test_normal_examples(self):
        for ref, expected in NORMAL_EXAMPLES.items():
            self.assertEqual(resolve_reference(BASE, ref), expected, repr(ref))

    def test_abnormal_examples(self):
        for ref, expected in ABNORMAL_EXAMPLES.items():
            self.assertEqual(resolve_reference(BASE, ref), expected, repr(ref))

    def test_base_with_empty_path(self):
        self.assertEqual(resolve_reference("http://example.com", "page.html"), "http://example.com/page.html")
        self.assertEqual(resolve_reference("http://example.com?x=1", "?y=2"), "http://example.com?y=2")

    def test_base_must_be_absolute(self):
        with self.assertRaises(ValueError):
            resolve_reference("/relative/base", "g")


class TestNormalizeUrl(unittest.TestCase):
    def test_rfc_example(self):
        # RFC 3986 6.2.2 の例: 2 つは同じ URI を表す
        self.assertEqual(normalize_url("eXAMPLE://a/./b/../b/%63/%7bfoo%7d"), "example://a/b/c/%7Bfoo%7D")
        self.assertEqual(normalize_url("example://a/b/c/%7Bfoo%7D"), "example://a/b/c/%7Bfoo%7D")

    def test_case_normalization(self):
        self.assertEqual(normalize_url("HTTP://www.Example.COM/Path"), "http://www.example.com/Path",
                         "スキームとホストは小文字、パスは大文字小文字を区別するのでそのまま")
        self.assertEqual(normalize_url("http://User:PW@Example.com/"), "http://User:PW@example.com/")

    def test_default_port_and_empty_path(self):
        self.assertEqual(normalize_url("http://example.com:80"), "http://example.com/")
        self.assertEqual(normalize_url("https://example.com:443/a"), "https://example.com/a")
        self.assertEqual(normalize_url("http://example.com:443/"), "http://example.com:443/", "http の既定は 80")
        self.assertEqual(normalize_url("https://example.com:8443"), "https://example.com:8443/")
        self.assertEqual(normalize_url("http://example.com:/"), "http://example.com/")
        self.assertEqual(normalize_url("wss://chat.example.com:443/ws"), "wss://chat.example.com/ws")

    def test_percent_encoding(self):
        self.assertEqual(normalize_url("http://example.com/%7Euser/%41%62c"), "http://example.com/~user/Abc",
                         "非予約文字のエンコードは元に戻す")
        self.assertEqual(normalize_url("http://example.com/a%2fb?q=a%2bb"), "http://example.com/a%2Fb?q=a%2Bb",
                         "予約文字（/ や +）は意味が変わるので戻さず、16 進数を大文字にそろえる")
        self.assertEqual(normalize_url("http://example.com/%e6%97%a5"), "http://example.com/%E6%97%A5")
        self.assertEqual(normalize_url("http://Ex%41mple.com/"), "http://example.com/")

    def test_dot_segments_query_and_fragment(self):
        self.assertEqual(normalize_url("http://example.com/a/b/../c/./d.html?b=2&a=1#Sec%5f1"),
                         "http://example.com/a/c/d.html?b=2&a=1#Sec_1", "クエリの順序は変えない")

    def test_ipv6(self):
        self.assertEqual(normalize_url("http://[2001:DB8::1]:80/"), "http://[2001:db8::1]/")

    def test_requires_absolute_uri(self):
        for bad in ("/path/only", "//example.com/", "example.com/path"):
            with self.assertRaises(ValueError, msg=bad):
                normalize_url(bad)

    def test_idempotent(self):
        rng = random.Random(54)
        pieces = ["a", "b", ".", "..", "%7e", "%2F", "%41", "x%2fy", ""]
        for _ in range(300):
            path = "/" + "/".join(rng.choice(pieces) for _ in range(rng.randrange(0, 6)))
            url = f"{rng.choice(['HTTP', 'https', 'Ftp'])}://{rng.choice(['Example.com', 'a.B.c'])}" \
                  f"{rng.choice(['', ':80', ':443', ':21', ':8080'])}{path}{rng.choice(['', '?q=%7E1', '#%61'])}"
            once = normalize_url(url)
            self.assertEqual(normalize_url(once), once, url)


if __name__ == "__main__":
    unittest.main()
