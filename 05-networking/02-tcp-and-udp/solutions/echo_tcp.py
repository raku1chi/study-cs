"""5.2 TCPとUDP — 解答例（echo_tcp）

演習の仕様は exercises/echo_tcp.py の docstring を参照してください。
"""
from __future__ import annotations

import socket
import threading
from typing import Callable

from framing import HEADER, HEADER_SIZE, FrameDecoder, FrameTooLarge, encode_frame

DEFAULT_MAX_FRAME_SIZE = 16 * 1024 * 1024
RECV_SIZE = 65536


# ---------------------------------------------------------------------------
# 演習4: 部分的な送受信を扱う
# ---------------------------------------------------------------------------

def send_all(sock: socket.socket, data: bytes) -> None:
    view = memoryview(data)  # スライスのたびにコピーしないように memoryview を使う
    total = 0
    while total < len(view):
        sent = sock.send(view[total:])  # カーネルの送信バッファの空き分しか受け取られないことがある
        if sent == 0:
            raise ConnectionError("接続が閉じられ、送信できません")
        total += sent


def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), RECV_SIZE))  # 要求より少ないバイト数が返ることがある
        if not chunk:  # b"" は相手が送信を終えた（FIN を受け取った）しるし
            raise ConnectionError(f"{n} バイト中 {len(buf)} バイトを受信した時点で接続が閉じられました")
        buf += chunk
    return bytes(buf)


def recv_frame(sock: socket.socket, *, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> bytes:
    (length,) = HEADER.unpack(recv_exact(sock, HEADER_SIZE))
    if length > max_frame_size:
        raise FrameTooLarge(f"フレームが大きすぎます: {length} > {max_frame_size}")
    return recv_exact(sock, length)


# ---------------------------------------------------------------------------
# 演習4: スレッドで複数の接続を扱うエコーサーバー
# ---------------------------------------------------------------------------

class EchoServer:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
        handler: Callable[[bytes], bytes] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.max_frame_size = max_frame_size
        self.handler = handler or (lambda payload: payload)
        self._listener: socket.socket | None = None
        self._accept_thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._lock = threading.Lock()
        self._conns: set[socket.socket] = set()
        self._workers: list[threading.Thread] = []

    @property
    def address(self) -> tuple[str, int]:
        if self._listener is None:
            raise RuntimeError("start() の前です")
        host, port = self._listener.getsockname()[:2]
        return host, port

    def start(self) -> tuple[str, int]:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 再起動直後に TIME_WAIT の接続が残っていても、同じポートで待ち受けられるようにする
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))  # port=0 なら OS が空いているポートを選ぶ
        listener.listen(128)  # 128 は accept() 待ちの接続を溜めておくキュー（backlog）の長さ
        # accept() が永久にブロックしないよう、短いタイムアウトで停止要求を確認しながら回す
        listener.settimeout(0.1)
        self._listener = listener
        self._accept_thread = threading.Thread(target=self._accept_loop, name="echo-accept", daemon=True)
        self._accept_thread.start()
        return self.address

    def _accept_loop(self) -> None:
        assert self._listener is not None
        while not self._stopping.is_set():
            try:
                conn, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break  # stop() で待ち受けソケットが閉じられた
            with self._lock:
                if self._stopping.is_set():
                    conn.close()
                    break
                self._conns.add(conn)
                worker = threading.Thread(target=self._serve, args=(conn,), name="echo-conn", daemon=True)
                self._workers.append(worker)
            worker.start()

    def _serve(self, conn: socket.socket) -> None:
        decoder = FrameDecoder(self.max_frame_size)
        try:
            while True:
                data = conn.recv(RECV_SIZE)
                if not data:
                    break  # クライアントが接続を閉じた
                # 1 回の recv に複数のフレームや、フレームの一部が入っていてもよい
                for frame in decoder.feed(data):
                    send_all(conn, encode_frame(self.handler(frame)))
        except (FrameTooLarge, OSError):
            pass  # 大きすぎるフレーム・通信エラーでは接続を閉じる
        finally:
            with self._lock:
                self._conns.discard(conn)
            conn.close()

    def stop(self) -> None:
        self._stopping.set()
        if self._listener is not None:
            self._listener.close()
        if self._accept_thread is not None:
            self._accept_thread.join(timeout=5)
        with self._lock:
            conns = list(self._conns)
            workers = list(self._workers)
        for conn in conns:
            try:
                # shutdown は、別のスレッドで recv() や send() に入っているスレッドも起こす
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for worker in workers:
            worker.join(timeout=5)

    def __enter__(self) -> EchoServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


class EchoClient:
    def __init__(
        self,
        address: tuple[str, int],
        *,
        timeout: float = 5.0,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        self.max_frame_size = max_frame_size
        # 接続（3 ウェイハンドシェイク）にも送受信にも timeout 秒の上限を付ける
        self._sock = socket.create_connection(address, timeout=timeout)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def request(self, payload: bytes) -> bytes:
        send_all(self._sock, encode_frame(payload))
        return recv_frame(self._sock, max_frame_size=self.max_frame_size)

    def close(self) -> None:
        self._sock.close()

    def __enter__(self) -> EchoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
