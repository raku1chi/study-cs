"""4.3 ファイルシステムとI/O — 解答例: selectors によるイベントループのエコーサーバー

演習の仕様は exercises/evloop.py の docstring を参照してください。

コマンドラインから試す:
    python3 evloop.py 8888          # 別の端末で: nc 127.0.0.1 8888
"""
from __future__ import annotations

import selectors
import socket
import sys
import threading


class _Conn:
    """1 つの接続の状態。イベントループでは、この状態を自分で持ち回る（スレッドのスタックの代わり）。"""

    __slots__ = ("sock", "outbuf", "read_closed")

    def __init__(self, sock: socket.socket) -> None:
        self.sock = sock
        self.outbuf = bytearray()  # まだ送れていないデータ
        self.read_closed = False  # 相手が送信を終えた（EOF を受け取った）か


class EchoServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 0, *,
                 recv_size: int = 4096, high_water: int = 64 * 1024) -> None:
        if recv_size < 1 or high_water < 1:
            raise ValueError("recv_size と high_water は 1 以上")
        self.recv_size = recv_size
        self.high_water = high_water
        self.connections_accepted = 0
        self.max_buffered = 0
        self._sel = selectors.DefaultSelector()  # Linux なら epoll、macOS なら kqueue
        self._listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind((host, port))
        self._listener.listen(128)
        self._listener.setblocking(False)
        self._sel.register(self._listener, selectors.EVENT_READ, data="listener")
        # 自己パイプ（self-pipe）の技法: 別スレッドから select() を起こすための通り道
        self._wake_r, self._wake_w = socket.socketpair()
        self._wake_r.setblocking(False)
        self._wake_w.setblocking(False)
        self._sel.register(self._wake_r, selectors.EVENT_READ, data="wakeup")
        self._stop = threading.Event()
        self._closed = False

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._listener.getsockname()[:2]
        return host, port

    def shutdown(self) -> None:
        self._stop.set()
        try:
            self._wake_w.send(b"x")  # select() で眠っているループを起こす
        except OSError:
            pass  # すでに閉じている、またはバッファが満杯（どちらにしても起きる）

    def serve_forever(self) -> None:
        try:
            while not self._stop.is_set():
                for key, mask in self._sel.select():
                    if key.data == "listener":
                        self._accept()
                    elif key.data == "wakeup":
                        self._drain_wakeup()
                    else:
                        self._service(key.data, mask)
        finally:
            self._close_all()

    # --- 内部処理 -----------------------------------------------------------

    def _accept(self) -> None:
        while True:  # 溜まっている接続をまとめて受け付ける
            try:
                sock, _ = self._listener.accept()
            except (BlockingIOError, InterruptedError):
                return
            sock.setblocking(False)  # これを忘れると、1 つの遅いクライアントでループ全体が止まる
            self.connections_accepted += 1
            self._sel.register(sock, selectors.EVENT_READ, data=_Conn(sock))

    def _drain_wakeup(self) -> None:
        try:
            while self._wake_r.recv(1024):
                pass
        except (BlockingIOError, InterruptedError):
            pass

    def _service(self, conn: _Conn, mask: int) -> None:
        try:
            if mask & selectors.EVENT_READ:
                self._on_readable(conn)
            if mask & selectors.EVENT_WRITE and conn.outbuf:
                self._on_writable(conn)
        except (ConnectionError, OSError):
            self._close(conn)  # 相手の強制切断（RST）など。この接続だけを片付ける
            return
        self._update_interest(conn)

    def _on_readable(self, conn: _Conn) -> None:
        try:
            data = conn.sock.recv(self.recv_size)
        except (BlockingIOError, InterruptedError):
            return
        if not data:
            conn.read_closed = True  # 相手は送信を終えた。残りを送り切ったら閉じる
            return
        conn.outbuf += data
        self.max_buffered = max(self.max_buffered, len(conn.outbuf))
        self._on_writable(conn)  # すぐ送れる分は送ってしまう（送れなければ EVENT_WRITE を待つ）

    def _on_writable(self, conn: _Conn) -> None:
        try:
            sent = conn.sock.send(conn.outbuf)  # 一部しか送れないことがある（部分書き込み）
        except (BlockingIOError, InterruptedError):
            return
        del conn.outbuf[:sent]

    def _update_interest(self, conn: _Conn) -> None:
        events = 0
        # 背圧（バックプレッシャー）: 送れていないデータが溜まったら、その接続からは読まない
        if not conn.read_closed and len(conn.outbuf) < self.high_water:
            events |= selectors.EVENT_READ
        if conn.outbuf:
            events |= selectors.EVENT_WRITE
        if events == 0:  # 相手は送信を終え、こちらも送り切った
            self._close(conn)
            return
        key = self._sel.get_key(conn.sock)
        if key.events != events:
            self._sel.modify(conn.sock, events, data=conn)

    def _close(self, conn: _Conn) -> None:
        try:
            self._sel.unregister(conn.sock)
        except (KeyError, ValueError):
            pass
        conn.sock.close()

    def _close_all(self) -> None:
        if self._closed:
            return
        self._closed = True
        for key in list(self._sel.get_map().values()):
            if isinstance(key.data, _Conn):
                self._close(key.data)
        for sock in (self._listener, self._wake_r, self._wake_w):
            try:
                self._sel.unregister(sock)
            except (KeyError, ValueError):
                pass
            sock.close()
        self._sel.close()


if __name__ == "__main__":
    server = EchoServer(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8888)
    print("listening on", server.address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
