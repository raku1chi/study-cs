"""4.3 ファイルシステムとI/O — evloop のテスト

実行: python3 tools/check.py 4.3   （またはこのディレクトリで python3 -m unittest -v test_evloop）

サーバーを別スレッドで 127.0.0.1 の空いているポート（port=0）に起動し、ソケットで接続して確かめます。
"""
import socket
import threading
import time
import unittest

from evloop import EchoServer

TIMEOUT = 10.0


def recv_exactly(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(65536, n - len(buf)))
        if not chunk:
            break
        buf += chunk
    return bytes(buf)


def recv_until_eof(sock: socket.socket) -> bytes:
    buf = bytearray()
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return bytes(buf)
        buf += chunk


class ServerTestCase(unittest.TestCase):
    server_kwargs: dict = {}

    def setUp(self):
        self.server = EchoServer("127.0.0.1", 0, **self.server_kwargs)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.clients: list[socket.socket] = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.server.shutdown()
        self.thread.join(TIMEOUT)
        self.assertFalse(self.thread.is_alive(), "shutdown() の後、serve_forever() が終わらない")

    def connect(self) -> socket.socket:
        sock = socket.create_connection(self.server.address, timeout=TIMEOUT)
        self.clients.append(sock)
        return sock


class TestExercise5EchoBasics(ServerTestCase):
    def test_address_is_bound(self):
        host, port = self.server.address
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0)

    def test_single_client_echo(self):
        c = self.connect()
        c.sendall(b"hello")
        self.assertEqual(recv_exactly(c, 5), b"hello")
        c.sendall(b", world")
        self.assertEqual(recv_exactly(c, 7), b", world")

    def test_many_clients_at_the_same_time(self):
        # 全員が接続したまま、順番に送受信する。1 接続ずつ最後まで処理するサーバーだと、ここで止まる
        clients = [self.connect() for _ in range(50)]
        for i, c in enumerate(clients):
            c.sendall(f"client-{i}".encode())
        for i, c in enumerate(reversed(clients)):
            expected = f"client-{len(clients) - 1 - i}".encode()
            self.assertEqual(recv_exactly(c, len(expected)), expected)
        self.assertEqual(self.server.connections_accepted, 50)

    def test_half_close_flushes_then_closes(self):
        c = self.connect()
        c.sendall(b"last words")
        c.shutdown(socket.SHUT_WR)  # 送信だけを終える（半分だけ閉じる）
        self.assertEqual(recv_until_eof(c), b"last words", "受け取ったデータを送り切ってから閉じること")

    def test_abrupt_disconnect_does_not_break_the_server(self):
        for _ in range(5):
            bad = socket.create_connection(self.server.address, timeout=TIMEOUT)
            bad.sendall(b"x" * 100000)
            bad.close()  # 受信せずに切断（サーバー側では RST やエラーになりうる）
        c = self.connect()
        c.sendall(b"still alive?")
        self.assertEqual(recv_exactly(c, 12), b"still alive?")


class TestExercise5PartialIoAndBackpressure(ServerTestCase):
    server_kwargs = {"recv_size": 4096, "high_water": 64 * 1024}

    def test_large_transfer_with_partial_reads_and_writes(self):
        c = self.connect()
        payload = bytes(range(256)) * (8 * 1024)  # 2 MiB
        sender_error = []

        def send_all():
            try:
                c.sendall(payload)
            except OSError as e:  # pragma: no cover - 失敗時の診断用
                sender_error.append(e)

        sender = threading.Thread(target=send_all, daemon=True)
        sender.start()  # 送信と受信を同時に行う（そうしないと双方のバッファが満杯になって止まる）
        received = recv_exactly(c, len(payload))
        sender.join(TIMEOUT)
        self.assertEqual(sender_error, [])
        self.assertEqual(len(received), len(payload))
        self.assertEqual(received, payload)

    def test_slow_reader_does_not_make_the_server_buffer_everything(self):
        c = self.connect()
        payload = b"z" * (4 * 1024 * 1024)
        sender = threading.Thread(target=c.sendall, args=(payload,), daemon=True)
        sender.start()
        time.sleep(0.3)  # クライアントはしばらく受信しない
        received = recv_exactly(c, len(payload))
        sender.join(TIMEOUT)
        self.assertEqual(len(received), len(payload))
        self.assertLess(self.server.max_buffered, 64 * 1024 + 4096,
                        "送れていないデータが high_water を超えたら、その接続からの読み込みを止めること")


class TestExercise5Shutdown(unittest.TestCase):
    def test_shutdown_closes_listener_and_connections(self):
        server = EchoServer("127.0.0.1", 0)
        address = server.address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        client = socket.create_connection(address, timeout=TIMEOUT)
        client.sendall(b"ping")
        self.assertEqual(recv_exactly(client, 4), b"ping")
        start = time.monotonic()
        server.shutdown()  # 別スレッドから呼ぶ
        thread.join(TIMEOUT)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic() - start, 2.0, "shutdown() の後すぐに終わること")
        try:
            self.assertEqual(client.recv(1), b"", "既存の接続は閉じられる")
        except ConnectionResetError:
            pass  # 閉じ方によっては RST で届く。それでもよい
        finally:
            client.close()
        with self.assertRaises(OSError):
            socket.create_connection(address, timeout=2).close()  # 待ち受けソケットも閉じている

    def test_shutdown_before_serve_forever(self):
        server = EchoServer("127.0.0.1", 0)
        server.shutdown()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        thread.join(TIMEOUT)
        self.assertFalse(thread.is_alive(), "先に shutdown() されていたら、すぐに戻ること")

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            EchoServer("127.0.0.1", 0, recv_size=0)


if __name__ == "__main__":
    unittest.main()
