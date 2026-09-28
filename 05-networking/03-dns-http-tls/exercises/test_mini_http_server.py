"""5.3 DNS・HTTP・TLS — テスト（mini_http_server）

実行: python3 tools/check.py 5.3   （またはこのディレクトリで python3 -m unittest -v）

127.0.0.1 の空いているポート（port=0）で起動したサーバーに、標準ライブラリの http.client で
アクセスして確かめます。外部との通信はしません。
"""
import http.client
import socket
import threading
import time
import unittest

from mini_http_server import MiniHTTPServer, Response, Router

BIG = bytes(i % 251 for i in range(300_000))


def make_router() -> Router:
    router = Router()
    router.add("GET", "/", lambda req: Response(200, [("Content-Type", "text/plain")], b"hello"))
    router.add("GET", "/big", lambda req: Response(200, [("Content-Type", "application/octet-stream")], BIG))
    router.add("POST", "/echo", lambda req: Response(200, [("X-Body-Length", str(len(req.body)))], req.body))
    router.add("PUT", "/items", lambda req: Response(201, [("Location", "/items/1")], b""))
    router.add("GET", "/items", lambda req: Response(200, [], b"[]"))
    router.add("GET", "/query", lambda req: Response(200, [], req.query.encode()))
    router.add("GET", "/multi", lambda req: Response(200, [], ",".join(req.headers.get_all("X-Tag")).encode()))

    def boom(req):
        raise RuntimeError("ハンドラのバグ")

    router.add("GET", "/boom", boom)
    return router


def raw_exchange(address, data: bytes, timeout: float = 5.0) -> bytes:
    """生のバイト列を送り、サーバーが接続を閉じるまでに返したものをすべて読む。"""
    with socket.create_connection(address, timeout=timeout) as sock:
        sock.sendall(data)
        chunks = []
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


class TestRouter(unittest.TestCase):
    def test_resolve(self):
        router = make_router()
        handler, status, allowed = router.resolve("GET", "/")
        self.assertEqual(status, 200)
        self.assertIsNotNone(handler)
        self.assertEqual(router.resolve("GET", "/nope")[1], 404)
        handler, status, allowed = router.resolve("DELETE", "/items")
        self.assertIsNone(handler)
        self.assertEqual(status, 405)
        self.assertEqual(allowed, ["GET", "HEAD", "PUT"], "GET を受け付けるなら HEAD も。アルファベット順")
        self.assertEqual(router.resolve("HEAD", "/")[1], 200)

    def test_route_decorator(self):
        router = Router()

        @router.route("POST", "/login")
        def login(req):
            return Response(204)

        self.assertIs(router.resolve("POST", "/login")[0], login)


class TestMiniHTTPServer(unittest.TestCase):
    def setUp(self):
        self.server = MiniHTTPServer(make_router(), keepalive_timeout=5.0, max_body_bytes=512 * 1024)
        self.address = self.server.start()
        self.addCleanup(self.server.stop)

    def connection(self):
        conn = http.client.HTTPConnection(*self.address, timeout=5)
        self.addCleanup(conn.close)
        return conn

    def get(self, method, path, body=None, headers=None):
        conn = self.connection()
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        return resp, resp.read()

    def test_get(self):
        resp, body = self.get("GET", "/")
        self.assertEqual((resp.status, body), (200, b"hello"))
        self.assertEqual(resp.getheader("Content-Type"), "text/plain")
        self.assertEqual(resp.getheader("Content-Length"), "5")
        self.assertIsNotNone(resp.getheader("Date"), "オリジンサーバーは Date ヘッダを付ける")

    def test_query_and_multiple_headers(self):
        self.assertEqual(self.get("GET", "/query?a=1&b=2")[1], b"a=1&b=2")
        conn = self.connection()
        conn.putrequest("GET", "/multi")
        conn.putheader("X-Tag", "one")
        conn.putheader("X-Tag", "two")
        conn.endheaders()
        self.assertEqual(conn.getresponse().read(), b"one,two")

    def test_not_found(self):
        resp, _ = self.get("GET", "/missing")
        self.assertEqual(resp.status, 404)

    def test_method_not_allowed_has_allow_header(self):
        resp, _ = self.get("POST", "/")
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.getheader("Allow"), "GET, HEAD")

    def test_head(self):
        resp, body = self.get("HEAD", "/big")
        self.assertEqual(resp.status, 200)
        self.assertEqual(body, b"", "HEAD の応答に本文はない")
        self.assertEqual(resp.getheader("Content-Length"), str(len(BIG)), "GET と同じ Content-Length")

    def test_large_response(self):
        resp, body = self.get("GET", "/big")
        self.assertEqual((resp.status, len(body)), (200, len(BIG)))
        self.assertEqual(body, BIG)

    def test_post_content_length_and_chunked(self):
        payload = bytes(range(256)) * 400
        resp, body = self.get("POST", "/echo", body=payload)
        self.assertEqual((resp.status, body), (200, payload))
        resp, body = self.get("POST", "/echo", body=iter([b"abc", b"", b"defgh"]))  # chunked で送られる
        self.assertEqual((resp.status, body, resp.getheader("X-Body-Length")), (200, b"abcdefgh", "8"))

    def test_status_without_body(self):
        resp, body = self.get("PUT", "/items", body=b"{}")
        self.assertEqual((resp.status, body, resp.getheader("Location")), (201, b"", "/items/1"))

    def test_keep_alive_reuses_connection(self):
        conn = self.connection()
        for _ in range(3):
            conn.request("GET", "/")
            self.assertEqual(conn.getresponse().read(), b"hello")
        self.assertEqual(self.server.accepted_connections, 1, "HTTP/1.1 では接続を使い回す")
        self.assertEqual(self.server.handled_requests, 3)

    def test_connection_close(self):
        conn = self.connection()
        conn.request("GET", "/", headers={"Connection": "close"})
        resp = conn.getresponse()
        self.assertEqual(resp.getheader("Connection"), "close")
        resp.read()
        conn.request("GET", "/")  # http.client は閉じられた接続を張り直す
        conn.getresponse().read()
        self.assertEqual(self.server.accepted_connections, 2)

    def test_http10_closes_by_default(self):
        raw = raw_exchange(self.address, b"GET / HTTP/1.0\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1.1 200 "), raw[:40])
        self.assertTrue(raw.endswith(b"hello"), "応答の後、サーバーが接続を閉じる")

    def test_pipelining(self):
        requests = (b"GET /query?first HTTP/1.1\r\nHost: t\r\n\r\n"
                    b"GET /query?second HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")
        raw = raw_exchange(self.address, requests)
        self.assertEqual(raw.count(b"HTTP/1.1 200 OK"), 2)
        self.assertLess(raw.index(b"first"), raw.index(b"second"), "応答はリクエストの順")

    def test_bad_request_closes_connection(self):
        raw = raw_exchange(self.address, b"THIS IS NOT HTTP\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1.1 400 "), raw[:40])
        raw = raw_exchange(self.address, b"GET / HTTP/1.1\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1.1 400 "), "Host のない HTTP/1.1 リクエスト")
        raw = raw_exchange(self.address, b"GET / HTTP/3.0\r\nHost: t\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1.1 505 "), raw[:40])

    def test_body_too_large(self):
        raw = raw_exchange(self.address, b"POST /echo HTTP/1.1\r\nHost: t\r\nContent-Length: 999999999\r\n\r\n")
        self.assertTrue(raw.startswith(b"HTTP/1.1 413 "), raw[:40])

    def test_handler_exception_becomes_500(self):
        resp, _ = self.get("GET", "/boom")
        self.assertEqual(resp.status, 500)
        self.assertEqual(self.get("GET", "/")[1], b"hello", "サーバーは動き続ける")

    def test_concurrent_clients(self):
        errors = []

        def worker(n):
            try:
                conn = http.client.HTTPConnection(*self.address, timeout=5)
                for i in range(10):
                    conn.request("POST", "/echo", body=f"{n}-{i}".encode() * 100)
                    body = conn.getresponse().read()
                    if body != f"{n}-{i}".encode() * 100:
                        errors.append(f"worker {n}: 応答が一致しない")
                conn.close()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"worker {n}: {exc!r}")

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
            self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])

    def test_stop_is_prompt(self):
        conn = self.connection()
        conn.request("GET", "/")
        conn.getresponse().read()  # アイドルな持続接続を残したまま止める
        start = time.monotonic()
        self.server.stop()
        self.assertLess(time.monotonic() - start, 3)


class TestIdleTimeout(unittest.TestCase):
    def test_idle_connection_is_closed(self):
        with MiniHTTPServer(make_router(), keepalive_timeout=0.2) as server:
            with socket.create_connection(server.address, timeout=5) as sock:
                start = time.monotonic()
                self.assertEqual(sock.recv(10), b"", "何も送らない接続はタイムアウトで閉じられる")
                self.assertLess(time.monotonic() - start, 3)


if __name__ == "__main__":
    unittest.main()
