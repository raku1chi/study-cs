"""5.3 DNS・HTTP・TLS — 解答例（mini_http_server）

演習の仕様は exercises/mini_http_server.py の docstring を参照してください。
"""
from __future__ import annotations

import email.utils
import socket
import threading
from dataclasses import dataclass, field
from typing import Callable

from http11 import DEFAULT_MAX_BODY_BYTES, HTTPParseError, Request, parse_request, serialize_response

RECV_SIZE = 65536


@dataclass
class Response:
    status: int = 200
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""


Handler = Callable[[Request], Response]


def text_response(status: int, text: str, headers: list[tuple[str, str]] | None = None) -> Response:
    return Response(status, [("Content-Type", "text/plain; charset=utf-8"), *(headers or [])], text.encode("utf-8"))


class Router:
    def __init__(self) -> None:
        self._routes: dict[str, dict[str, Handler]] = {}

    def add(self, method: str, path: str, handler: Handler) -> None:
        if not path.startswith("/"):
            raise ValueError(f"パスは / で始めてください: {path!r}")
        self._routes.setdefault(path, {})[method.upper()] = handler

    def route(self, method: str, path: str) -> Callable[[Handler], Handler]:
        def decorator(handler: Handler) -> Handler:
            self.add(method, path, handler)
            return handler

        return decorator

    def resolve(self, method: str, path: str) -> tuple[Handler | None, int, list[str]]:
        methods = self._routes.get(path)
        if not methods:
            return None, 404, []
        allowed = set(methods)
        if "GET" in allowed:
            allowed.add("HEAD")  # GET を受け付けるパスは HEAD も受け付ける
        allowed_list = sorted(allowed)
        if method in methods:
            return methods[method], 200, allowed_list
        if method == "HEAD" and "GET" in methods:
            return methods["GET"], 200, allowed_list
        return None, 405, allowed_list


def send_all(sock: socket.socket, data: bytes) -> None:
    view = memoryview(data)
    while view:
        sent = sock.send(view)
        if sent == 0:
            raise ConnectionError("送信できません")
        view = view[sent:]


class MiniHTTPServer:
    def __init__(
        self,
        router: Router,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        keepalive_timeout: float = 5.0,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        self.router = router
        self.host = host
        self.port = port
        self.keepalive_timeout = keepalive_timeout
        self.max_body_bytes = max_body_bytes
        self.accepted_connections = 0
        self.handled_requests = 0
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
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.host, self.port))
        listener.listen(128)
        listener.settimeout(0.1)
        self._listener = listener
        self._accept_thread = threading.Thread(target=self._accept_loop, name="http-accept", daemon=True)
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
                break
            with self._lock:
                if self._stopping.is_set():
                    conn.close()
                    break
                self.accepted_connections += 1
                self._conns.add(conn)
                worker = threading.Thread(target=self._serve, args=(conn,), name="http-conn", daemon=True)
                self._workers.append(worker)
            worker.start()

    def _serve(self, conn: socket.socket) -> None:
        # アイドルな持続接続は keepalive_timeout 秒で閉じる（遅いクライアントに接続を占有させない）
        conn.settimeout(self.keepalive_timeout)
        buf = bytearray()
        try:
            while not self._stopping.is_set():
                try:
                    parsed = parse_request(bytes(buf), max_body_bytes=self.max_body_bytes)
                except HTTPParseError as exc:
                    # 不正なリクエストの後ろのバイト列は信用できないので、応答して接続を閉じる
                    resp = text_response(exc.status, exc.message + "\n", [("Connection", "close")])
                    send_all(conn, self._serialize(resp, head_request=False))
                    break
                if parsed is None:
                    data = conn.recv(RECV_SIZE)
                    if not data:
                        break  # クライアントが閉じた
                    buf += data
                    continue
                request, consumed = parsed
                del buf[:consumed]  # 残りはパイプライン化された次のリクエスト
                keep_alive = request.keep_alive and not self._stopping.is_set()
                send_all(conn, self._respond(request, keep_alive))
                if not keep_alive:
                    break
        except OSError:
            pass  # タイムアウト（socket.timeout は OSError の一種）や、相手による切断
        finally:
            with self._lock:
                self._conns.discard(conn)
            conn.close()

    def _respond(self, request: Request, keep_alive: bool) -> bytes:
        handler, status, allowed = self.router.resolve(request.method, request.path)
        if status == 404:
            resp = text_response(404, "Not Found\n")
        elif status == 405:
            # 405 には、そのパスで使えるメソッドの一覧（Allow）を付けなければならない
            resp = text_response(405, "Method Not Allowed\n", [("Allow", ", ".join(allowed))])
        else:
            assert handler is not None
            try:
                resp = handler(request)
            except Exception:  # noqa: BLE001  ハンドラのバグでサーバー全体を止めない
                resp = text_response(500, "Internal Server Error\n")
        with self._lock:
            self.handled_requests += 1
        conn_headers: list[tuple[str, str]] = []
        if not keep_alive:
            conn_headers.append(("Connection", "close"))
        elif request.version == "HTTP/1.0":
            conn_headers.append(("Connection", "keep-alive"))  # HTTP/1.0 では持続接続を明示する
        head = request.method == "HEAD"
        try:
            return self._serialize(Response(resp.status, [*resp.headers, *conn_headers], resp.body), head_request=head)
        except ValueError:  # ハンドラが不正なレスポンス（改行入りのヘッダなど）を返した
            return self._serialize(text_response(500, "Internal Server Error\n", conn_headers), head_request=head)

    @staticmethod
    def _serialize(resp: Response, *, head_request: bool) -> bytes:
        headers = [("Date", email.utils.formatdate(usegmt=True)), ("Server", "mini-http"), *resp.headers]
        return serialize_response(resp.status, headers, resp.body, head_request=head_request)

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
                conn.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for worker in workers:
            worker.join(timeout=5)

    def __enter__(self) -> MiniHTTPServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
