"""5.2 TCPとUDP — テスト（echo_tcp）

実行: python3 tools/check.py 5.2   （またはこのディレクトリで python3 -m unittest -v）

127.0.0.1 の空いているポート（port=0）だけを使います。外部との通信はしません。
"""
import random
import socket
import struct
import threading
import time
import unittest

from echo_tcp import EchoClient, EchoServer, recv_exact, recv_frame, send_all
from framing import encode_frame


class ChunkySocket:
    """1 回の send / recv で少しずつしか処理しない、テスト用の偽のソケット。"""

    def __init__(self, incoming: bytes = b"", max_chunk: int = 3, refuse_after: int | None = None):
        self.incoming = bytearray(incoming)
        self.sent = bytearray()
        self.max_chunk = max_chunk
        self.refuse_after = refuse_after
        self.send_calls = 0

    def send(self, data, flags=0):
        self.send_calls += 1
        if self.refuse_after is not None and len(self.sent) >= self.refuse_after:
            return 0
        n = min(len(data), self.max_chunk)
        self.sent += bytes(data[:n])
        return n

    def recv(self, bufsize, flags=0):
        n = min(bufsize, self.max_chunk, len(self.incoming))
        chunk = bytes(self.incoming[:n])
        del self.incoming[:n]
        return chunk

    def sendall(self, data, flags=0):
        raise AssertionError("sendall を使わず、send の戻り値を見るループで実装してください")


class TestPartialIO(unittest.TestCase):
    def test_send_all_handles_partial_sends(self):
        s = ChunkySocket(max_chunk=3)
        data = bytes(range(100))
        send_all(s, data)
        self.assertEqual(bytes(s.sent), data)
        self.assertEqual(s.send_calls, 34, "3 バイトずつしか送れないので 34 回呼ぶ")

    def test_send_all_detects_closed_connection(self):
        with self.assertRaises(ConnectionError):
            send_all(ChunkySocket(max_chunk=3, refuse_after=9), bytes(20))

    def test_recv_exact_handles_partial_reads(self):
        s = ChunkySocket(incoming=b"hello, world", max_chunk=2)
        self.assertEqual(recv_exact(s, 5), b"hello")
        self.assertEqual(recv_exact(s, 0), b"")
        self.assertEqual(recv_exact(s, 7), b", world")

    def test_recv_exact_raises_on_eof(self):
        with self.assertRaises(ConnectionError):
            recv_exact(ChunkySocket(incoming=b"abc"), 5)

    def test_recv_frame(self):
        s = ChunkySocket(incoming=encode_frame(b"framed!") + encode_frame(b""), max_chunk=1)
        self.assertEqual(recv_frame(s), b"framed!")
        self.assertEqual(recv_frame(s), b"")


class TestEchoServer(unittest.TestCase):
    def setUp(self):
        self.server = EchoServer(max_frame_size=4 * 1024 * 1024)
        self.addr = self.server.start()
        self.addCleanup(self.server.stop)

    def client(self, **kw):
        c = EchoClient(self.addr, timeout=5, **kw)
        self.addCleanup(c.close)
        return c

    def test_listens_on_ephemeral_port(self):
        host, port = self.addr
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0, "port=0 なら OS が選んだ実際のポート番号を返す")

    def test_various_sizes(self):
        c = self.client()
        rng = random.Random(524)
        for size in [0, 1, 100, 1460, 65535, 65536, 65537, 300_000, 2 * 1024 * 1024 + 3]:
            payload = rng.randbytes(size)
            self.assertEqual(c.request(payload), payload, f"{size} バイト")

    def test_many_requests_on_one_connection(self):
        c = self.client()
        for i in range(200):
            msg = f"message {i}".encode()
            self.assertEqual(c.request(msg), msg)

    def test_pipelined_frames(self):
        # 100 個のフレームを 1 回でまとめて送り、あとで 100 個の応答を順に読む
        with socket.create_connection(self.addr, timeout=5) as sock:
            frames = [f"pipelined-{i}".encode() * (i % 7) for i in range(100)]
            send_all(sock, b"".join(encode_frame(f) for f in frames))
            self.assertEqual([recv_frame(sock) for _ in frames], frames)

    def test_frame_split_across_segments(self):
        # ヘッダの途中で区切られても正しく扱えること（Nagle を切って 1 バイトずつ送る）
        with socket.create_connection(self.addr, timeout=5) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            for b in encode_frame(b"slowly"):
                sock.send(bytes([b]))
                time.sleep(0.002)
            self.assertEqual(recv_frame(sock), b"slowly")

    def test_concurrent_clients(self):
        errors = []

        def worker(seed):
            rng = random.Random(seed)
            try:
                with EchoClient(self.addr, timeout=5) as c:
                    for _ in range(20):
                        payload = rng.randbytes(rng.choice([0, 10, 1000, 70_000]))
                        if c.request(payload) != payload:
                            errors.append(f"worker {seed}: 応答が一致しない")
            except Exception as exc:  # noqa: BLE001  スレッド内の例外をテスト本体に伝える
                errors.append(f"worker {seed}: {exc!r}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)
            self.assertFalse(t.is_alive(), "クライアントのスレッドが終わらない")
        self.assertEqual(errors, [])

    def test_stop_is_prompt_with_idle_connection(self):
        c = self.client()
        self.assertEqual(c.request(b"ping"), b"ping")
        start = time.monotonic()
        self.server.stop()
        self.assertLess(time.monotonic() - start, 3, "アイドルな接続が残っていても stop() はすぐ戻る")
        with self.assertRaises(OSError, msg="停止後は接続できない"):
            socket.create_connection(self.addr, timeout=2).close()


class TestEchoServerOptions(unittest.TestCase):
    def test_custom_handler(self):
        with EchoServer(handler=bytes.upper) as server, EchoClient(server.address, timeout=5) as c:
            self.assertEqual(c.request(b"hello"), b"HELLO")

    def test_too_large_frame_closes_connection(self):
        with EchoServer(max_frame_size=1024) as server:
            with EchoClient(server.address, timeout=5) as c:
                self.assertEqual(c.request(b"x" * 1024), b"x" * 1024)
                with self.assertRaises(ConnectionError):
                    c.request(b"x" * 1025)

    def test_client_rejects_too_large_response(self):
        with EchoServer() as server, EchoClient(server.address, timeout=5, max_frame_size=10) as c:
            with self.assertRaises(ValueError):
                c.request(b"0123456789A")

    def test_server_side_header_only_attack(self):
        # 長さだけ巨大なヘッダを送られても、データを待たずに接続を閉じる
        with EchoServer(max_frame_size=1024) as server:
            with socket.create_connection(server.address, timeout=5) as sock:
                sock.sendall(struct.pack("!I", 2**31))
                self.assertEqual(sock.recv(10), b"", "サーバーが接続を閉じる")


if __name__ == "__main__":
    unittest.main()
