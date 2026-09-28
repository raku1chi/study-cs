"""5.3 DNS・HTTP・TLS — テスト（http11）

実行: python3 tools/check.py 5.3   （またはこのディレクトリで python3 -m unittest -v）

答え合わせのために、標準ライブラリの http.client が作るリクエストと、http.client による
レスポンスの解釈を使っています（通信はしません）。
"""
import http.client
import io
import unittest

from http11 import HTTPParseError, Headers, parse_request, serialize_response


def crlf(text: str) -> bytes:
    """読みやすさのため、テストでは \\n で書いて \\r\\n に変換する。"""
    return text.replace("\n", "\r\n").encode("latin-1")


class CaptureSock:
    def __init__(self):
        self.buf = bytearray()

    def sendall(self, data):
        self.buf += data

    def close(self):
        pass


def capture_request(method, url, **kwargs) -> bytes:
    """http.client が送るはずのバイト列を、実際には通信せずに取り出す。"""
    conn = http.client.HTTPConnection("example.com", 8080)
    conn.sock = CaptureSock()
    conn.request(method, url, **kwargs)
    return bytes(conn.sock.buf)


class FakeReadSock:
    def __init__(self, data):
        self.data = data

    def makefile(self, *args, **kwargs):
        return io.BytesIO(self.data)


def interpret_response(raw: bytes, method: str = "GET") -> http.client.HTTPResponse:
    resp = http.client.HTTPResponse(FakeReadSock(raw), method=method)
    resp.begin()
    return resp


class TestHeaders(unittest.TestCase):
    def test_case_insensitive_multi_values(self):
        h = Headers([("Accept", "text/html"), ("X-Tag", "a")])
        h.add("accept", "application/json")
        self.assertEqual(h.get("ACCEPT"), "text/html", "get は最初の値")
        self.assertEqual(h.get_all("Accept"), ["text/html", "application/json"])
        self.assertIn("x-tag", h)
        self.assertNotIn("X-Missing", h)
        self.assertIsNone(h.get("X-Missing"))
        self.assertEqual(h.get("X-Missing", "default"), "default")
        self.assertEqual(h.items(), [("Accept", "text/html"), ("X-Tag", "a"), ("accept", "application/json")],
                         "元の大文字小文字と順序を保つ")
        self.assertEqual(len(h), 3)


class TestParseRequest(unittest.TestCase):
    def test_simple_get(self):
        data = crlf("GET /index.html?q=1&x=2 HTTP/1.1\nHost: example.com\nUser-Agent: test\n\n")
        req, consumed = parse_request(data)
        self.assertEqual((req.method, req.target, req.version), ("GET", "/index.html?q=1&x=2", "HTTP/1.1"))
        self.assertEqual((req.path, req.query), ("/index.html", "q=1&x=2"))
        self.assertEqual(req.headers.get("host"), "example.com")
        self.assertEqual(req.body, b"")
        self.assertEqual(consumed, len(data))

    def test_field_values_are_trimmed(self):
        req, _ = parse_request(crlf("GET / HTTP/1.1\nHost: a\nX-Value: \t spaced  value \t\nX-Empty:\n\n"))
        self.assertEqual(req.headers.get("X-Value"), "spaced  value", "前後の空白・タブだけを取り除く")
        self.assertEqual(req.headers.get("X-Empty"), "")

    def test_multiple_values(self):
        req, _ = parse_request(crlf("GET / HTTP/1.1\nHost: a\nAccept: text/html\nACCEPT: image/png\n\n"))
        self.assertEqual(req.headers.get_all("accept"), ["text/html", "image/png"])

    def test_content_length_body(self):
        data = crlf("POST /submit HTTP/1.1\nHost: a\nContent-Length: 11\n\n") + b"hello world"
        req, consumed = parse_request(data)
        self.assertEqual(req.body, b"hello world")
        self.assertEqual(consumed, len(data))

    def test_pipelined_requests(self):
        first = crlf("POST /a HTTP/1.1\nHost: a\nContent-Length: 3\n\n") + b"abc"
        second = crlf("GET /b HTTP/1.1\nHost: a\n\n")
        req1, n1 = parse_request(first + second)
        self.assertEqual((req1.path, req1.body, n1), ("/a", b"abc", len(first)))
        req2, n2 = parse_request((first + second)[n1:])
        self.assertEqual((req2.path, n2), ("/b", len(second)))

    def test_incomplete_input_returns_none(self):
        data = crlf("POST /x HTTP/1.1\nHost: a\nContent-Length: 5\n\n") + b"hello"
        for cut in range(len(data)):
            self.assertIsNone(parse_request(data[:cut]), f"{cut} バイトではまだ完成していない")
        self.assertIsNotNone(parse_request(data))

    def test_chunked_body_and_trailers(self):
        data = crlf("POST /up HTTP/1.1\nHost: a\nTransfer-Encoding: chunked\n\n"
                    "4\nWiki\n5;name=value\npedia\nA\n in chunks\n0\nX-Checksum: 42\n\n")
        req, consumed = parse_request(data)
        self.assertEqual(req.body, b"Wikipedia in chunks")
        self.assertEqual(req.trailers.get("x-checksum"), "42")
        self.assertEqual(consumed, len(data))

    def test_chunked_incomplete_returns_none(self):
        data = crlf("POST /up HTTP/1.1\nHost: a\nTransfer-Encoding: chunked\n\n3\nabc\n0\n\n")
        for cut in range(len(data)):
            self.assertIsNone(parse_request(data[:cut]), f"{cut} バイトではまだ完成していない")

    def test_requests_made_by_http_client(self):
        raw = capture_request("POST", "/upload?x=1", body=iter([b"ab", b"cde", b"fghij"]), headers={"X-A": "1"})
        req, consumed = parse_request(raw)  # http.client は反復可能な本文を chunked で送る
        self.assertEqual((req.method, req.target, req.body, consumed), ("POST", "/upload?x=1", b"abcdefghij", len(raw)))
        self.assertEqual(req.headers.get("x-a"), "1")
        raw = capture_request("PUT", "/items/7", body=b'{"name": "x"}', headers={"Content-Type": "application/json"})
        req, _ = parse_request(raw)
        self.assertEqual((req.method, req.body, req.headers.get("content-length")), ("PUT", b'{"name": "x"}', "13"))

    def test_leading_empty_lines_are_ignored(self):
        data = crlf("\n\nGET / HTTP/1.1\nHost: a\n\n")
        req, consumed = parse_request(data)
        self.assertEqual((req.method, consumed), ("GET", len(data)))

    def test_keep_alive(self):
        def ka(text):
            return parse_request(crlf(text))[0].keep_alive

        self.assertTrue(ka("GET / HTTP/1.1\nHost: a\n\n"), "HTTP/1.1 は既定で持続接続")
        self.assertFalse(ka("GET / HTTP/1.1\nHost: a\nConnection: close\n\n"))
        self.assertFalse(ka("GET / HTTP/1.1\nHost: a\nConnection: Upgrade, CLOSE\n\n"), "トークンは大文字小文字を区別しない")
        self.assertFalse(ka("GET / HTTP/1.0\n\n"), "HTTP/1.0 は既定で閉じる（Host もなくてよい）")
        self.assertTrue(ka("GET / HTTP/1.0\nConnection: keep-alive\n\n"))

    def assertStatus(self, data: bytes, status: int, **kwargs):
        with self.assertRaises(HTTPParseError, msg=repr(data)) as ctx:
            parse_request(data, **kwargs)
        self.assertEqual(ctx.exception.status, status, repr(data))

    def test_malformed_request_line(self):
        self.assertStatus(crlf("GET /\n\n"), 400)
        self.assertStatus(crlf("GET  / HTTP/1.1\nHost: a\n\n"), 400)
        self.assertStatus(crlf("G@T / HTTP/1.1\nHost: a\n\n"), 400)
        self.assertStatus(crlf("GET / HTTX/1.1\nHost: a\n\n"), 400)
        self.assertStatus(crlf("GET / HTTP/2.0\nHost: a\n\n"), 505)

    def test_host_header_rules(self):
        self.assertStatus(crlf("GET / HTTP/1.1\n\n"), 400)
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nHost: b\n\n"), 400)

    def test_malformed_fields(self):
        self.assertStatus(crlf("GET / HTTP/1.1\nHost : a\n\n"), 400)  # 名前と「:」の間の空白
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nX-Folded: 1\n  2\n\n"), 400)  # obs-fold
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nNoColon\n\n"), 400)
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nX-Bad: a\x00b\n\n"), 400)
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nX (y): 1\n\n"), 400)

    def test_bare_line_endings(self):
        self.assertStatus(b"GET / HTTP/1.1\nHost: a\n\n", 400)  # 途中でも、完成していても 400（None ではない）
        self.assertStatus(b"GET / HTTP/1.1\r\nHost: a\rX: b\r\n\r\n", 400)

    def test_content_length_rules(self):
        for value in ("abc", "-1", "+5", "5_0", "0x10", " ", "5 5"):
            self.assertStatus(crlf(f"POST / HTTP/1.1\nHost: a\nContent-Length: {value}\n\n") + b"12345", 400)
        self.assertStatus(crlf("POST / HTTP/1.1\nHost: a\nContent-Length: 5\nContent-Length: 6\n\n12345"), 400)
        req, _ = parse_request(crlf("POST / HTTP/1.1\nHost: a\nContent-Length: 5\nContent-Length: 5, 5\n\n12345"))
        self.assertEqual(req.body, b"12345", "同じ値の重複は受け入れてよい")

    def test_transfer_encoding_rules(self):
        base = "POST / HTTP/1.1\nHost: a\n{}\n\n0\n\n"
        self.assertStatus(crlf(base.format("Transfer-Encoding: chunked\nContent-Length: 5")), 400)
        self.assertStatus(crlf(base.format("Transfer-Encoding: gzip, chunked")), 501)
        self.assertStatus(crlf(base.format("Transfer-Encoding: chunked, gzip")), 400)
        self.assertStatus(crlf(base.format("Transfer-Encoding: gzip")), 400)
        self.assertStatus(crlf("POST / HTTP/1.0\nTransfer-Encoding: chunked\n\n0\n\n"), 400)
        req, _ = parse_request(crlf(base.format("Transfer-Encoding: Chunked")))
        self.assertEqual(req.body, b"", "コーディング名は大文字小文字を区別しない")

    def test_malformed_chunks(self):
        head = "POST / HTTP/1.1\nHost: a\nTransfer-Encoding: chunked\n\n"
        self.assertStatus(crlf(head + "zz\nabc\n0\n\n"), 400)
        self.assertStatus(crlf(head + "0x3\nabc\n0\n\n"), 400)
        self.assertStatus(crlf(head + "3\nabcX\n0\n\n"), 400)  # データの後ろに CRLF がない
        self.assertStatus(crlf(head + " 3\nabc\n0\n\n"), 400)

    def test_limits(self):
        self.assertStatus(crlf("POST / HTTP/1.1\nHost: a\nContent-Length: 11\n\n"), 413, max_body_bytes=10)
        head = "POST / HTTP/1.1\nHost: a\nTransfer-Encoding: chunked\n\n"
        self.assertStatus(crlf(head + "8\n12345678\n8\n12345678\n0\n\n"), 413, max_body_bytes=10)
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nX-Long: " + "x" * 200 + "\n\n"), 431, max_header_bytes=128)
        self.assertStatus(b"GET / HTTP/1.1\r\nHost: a\r\nX-Long: " + b"x" * 200, 431, max_header_bytes=128)
        self.assertStatus(crlf("GET / HTTP/1.1\nHost: a\nA: 1\nB: 2\nC: 3\n\n"), 431, max_headers=3)

    def test_parse_error_is_value_error(self):
        self.assertTrue(issubclass(HTTPParseError, ValueError))


class TestSerializeResponse(unittest.TestCase):
    def test_basic(self):
        raw = serialize_response(200, [("Content-Type", "text/plain")], b"hi")
        self.assertEqual(raw, b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nhi")

    def test_http_client_can_read_it(self):
        raw = serialize_response(404, [("X-Reason", "missing")], "見つかりません".encode("utf-8"))
        resp = interpret_response(raw)
        self.assertEqual((resp.status, resp.reason), (404, "Not Found"))
        self.assertEqual(resp.getheader("x-reason"), "missing")
        self.assertEqual(resp.read().decode("utf-8"), "見つかりません")

    def test_reason_phrases(self):
        self.assertTrue(serialize_response(201).startswith(b"HTTP/1.1 201 Created\r\n"))
        self.assertTrue(serialize_response(200, reason="Fine").startswith(b"HTTP/1.1 200 Fine\r\n"))
        self.assertTrue(serialize_response(299).startswith(b"HTTP/1.1 299 \r\n"), "未知のコードは理由句が空")

    def test_statuses_without_body(self):
        for status in (204, 304):
            raw = serialize_response(status)
            self.assertNotIn(b"Content-Length", raw, f"{status} には Content-Length を付けない")
            self.assertTrue(raw.endswith(b"\r\n\r\n"))
            with self.assertRaises(ValueError):
                serialize_response(status, body=b"x")

    def test_head_request_omits_body(self):
        raw = serialize_response(200, [("Content-Type", "text/plain")], b"hello", head_request=True)
        self.assertIn(b"Content-Length: 5\r\n", raw, "GET のときと同じ Content-Length を返す")
        self.assertTrue(raw.endswith(b"\r\n\r\n"))
        resp = interpret_response(raw, method="HEAD")
        self.assertEqual((resp.status, resp.read()), (200, b""))

    def test_does_not_duplicate_length_headers(self):
        raw = serialize_response(200, [("Content-Length", "2")], b"hi")
        self.assertEqual(raw.count(b"Content-Length"), 1)
        raw = serialize_response(200, [("Transfer-Encoding", "chunked")], b"2\r\nhi\r\n0\r\n\r\n")
        self.assertNotIn(b"Content-Length", raw)

    def test_rejects_header_injection(self):
        with self.assertRaises(ValueError, msg="値の CRLF を許すとレスポンスを分割される"):
            serialize_response(302, [("Location", "/next\r\nSet-Cookie: session=evil")])
        with self.assertRaises(ValueError):
            serialize_response(200, [("Bad Name", "x")])
        with self.assertRaises(ValueError):
            serialize_response(200, reason="OK\r\nX: y")

    def test_invalid_status(self):
        for status in (99, 600):
            with self.assertRaises(ValueError):
                serialize_response(status)


if __name__ == "__main__":
    unittest.main()
