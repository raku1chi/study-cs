"""5.3 DNS・HTTP・TLS — 演習（mini_http_server）: ソケットから作る HTTP/1.1 サーバー

http11.py の parse_request と serialize_response を使って、スレッドで動く小さな HTTP/1.1
サーバーを作ります。ルーティング、持続接続（keep-alive）、404・405、HEAD、アイドル
タイムアウト、エラー処理を実装します。演習1（http11.py）を先に終わらせてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.3
    python3 tools/check.py -v 5.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_mini_http_server

制約:
    - http.server・socketserver は使わず、socket と threading で実装してください。
    - テストは 127.0.0.1 の空いているポート（port=0）で起動し、http.client でアクセスします。

動かしてみる（演習を解いた後で。Ctrl+C で止める）:
    python3 -c "
    from mini_http_server import *
    r = Router(); r.add('GET', '/', lambda req: text_response(200, 'hello\\n'))
    s = MiniHTTPServer(r, port=8080); s.start(); input('Enter で終了')"
    curl -v http://127.0.0.1:8080/        # 別の端末から
"""
from __future__ import annotations

import email.utils  # noqa: F401  Date ヘッダの生成に使えます（email.utils.formatdate(usegmt=True)）
import socket
import threading  # noqa: F401
from dataclasses import dataclass, field
from typing import Callable

from http11 import DEFAULT_MAX_BODY_BYTES, HTTPParseError, Request, parse_request, serialize_response  # noqa: F401

RECV_SIZE = 65536


@dataclass
class Response:
    """ハンドラが返すレスポンス（実装済み）。"""

    status: int = 200
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""


Handler = Callable[[Request], Response]


def text_response(status: int, text: str, headers: list[tuple[str, str]] | None = None) -> Response:
    """text/plain のレスポンスを作る（実装済み）。"""
    return Response(status, [("Content-Type", "text/plain; charset=utf-8"), *(headers or [])], text.encode("utf-8"))


def send_all(sock: socket.socket, data: bytes) -> None:
    """data をすべて送る（実装済み。5.2 の演習で作ったものと同じ）。"""
    view = memoryview(data)
    while view:
        sent = sock.send(view)
        if sent == 0:
            raise ConnectionError("送信できません")
        view = view[sent:]


# ---------------------------------------------------------------------------
# 演習2（★★★）: ルーティング
# ---------------------------------------------------------------------------

class Router:
    """(メソッド, パス) からハンドラを選ぶ。パスは完全一致（クエリ文字列は含まない）。

    >>> router = Router()
    >>> router.add("GET", "/", lambda req: text_response(200, "hi"))
    >>> router.resolve("GET", "/")[1:]
    (200, ['GET', 'HEAD'])
    >>> router.resolve("POST", "/")[1:]
    (405, ['GET', 'HEAD'])
    >>> router.resolve("GET", "/nope")[1:]
    (404, [])
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習2: Router.__init__ を実装してください")

    def add(self, method: str, path: str, handler: Handler) -> None:
        """ルートを登録する。method は大文字にそろえる。path が "/" で始まらなければ ValueError。"""
        raise NotImplementedError("演習2: Router.add を実装してください")

    def route(self, method: str, path: str) -> Callable[[Handler], Handler]:
        """デコレータとして使える add（実装済み）。

        @router.route("GET", "/hello")
        def hello(req): ...
        """

        def decorator(handler: Handler) -> Handler:
            self.add(method, path, handler)
            return handler

        return decorator

    def resolve(self, method: str, path: str) -> tuple[Handler | None, int, list[str]]:
        """(ハンドラ, ステータス, 許可されたメソッドの一覧) を返す。

        - パスが登録されていなければ (None, 404, [])。
        - 許可されたメソッドの一覧は、そのパスに登録されたメソッドに、GET があれば HEAD を加え、
          アルファベット順に並べたもの。
        - method が登録されていれば (そのハンドラ, 200, 一覧)。
        - method が "HEAD" で GET が登録されていれば (GET のハンドラ, 200, 一覧)。
        - それ以外は (None, 405, 一覧)。
        """
        raise NotImplementedError("演習2: Router.resolve を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★★）: HTTP/1.1 サーバー
# ---------------------------------------------------------------------------

class MiniHTTPServer:
    """接続ごとにスレッドを 1 つ使う HTTP/1.1 サーバー。

    使い方:
        with MiniHTTPServer(router) as server:      # port=0 なら空いているポート
            host, port = server.address

    要件:
        start() / stop() / with 文: 5.2 の EchoServer と同じ（待ち受けソケットは SO_REUSEADDR 付き、
            accept はスレッドで繰り返す、stop() は数秒以内に戻る）。
        accepted_connections: 受け付けた接続の数。handled_requests: 応答したリクエストの数
            （ハンドラ・404・405・500 を含む。パースに失敗したものは含まない）。

        接続ごとの処理:
            1. 受信したバイト列をバッファに溜め、parse_request(バッファ, max_body_bytes=...) を呼ぶ。
               None ならさらに recv() する。recv() が b"" なら接続を閉じる。
            2. リクエストが完成したら、消費したバイト数だけバッファから取り除く
               （残りはパイプライン化された次のリクエスト）。
            3. Router で振り分けて応答を作る:
               - 404: text_response(404, "Not Found\\n")
               - 405: text_response(405, "Method Not Allowed\\n") に Allow ヘッダ（一覧をカンマ＋空白で連結）
               - ハンドラが例外を送出したら text_response(500, "Internal Server Error\\n")
                 （サーバー全体は止めない）
            4. 応答のヘッダに Date（email.utils.formatdate(usegmt=True)）を付ける。
               request.keep_alive が False なら "Connection: close" を付け、送った後に接続を閉じる。
               HTTP/1.0 で持続接続を続ける場合は "Connection: keep-alive" を付ける。
            5. HEAD なら serialize_response(..., head_request=True) で本文を送らない。
            6. HTTPParseError なら、そのステータスのエラー応答（"Connection: close" 付き）を送って
               接続を閉じる（不正なリクエストの後ろのバイト列は信用できないため）。
            7. keepalive_timeout 秒のあいだ何も届かなければ接続を閉じる（conn.settimeout を使う。
               タイムアウトは socket.timeout（OSError の一種）として送出される）。

    ヒント: 接続の処理は「parse → 足りなければ recv → 完成したら応答 → keep-alive なら繰り返す」
    というループになる。例外の経路でも必ず conn.close() するよう try/finally を使う。
    """

    def __init__(
        self,
        router: Router,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        keepalive_timeout: float = 5.0,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    ) -> None:
        """設定を保存する（実装済み）。必要に応じて属性を追加してください。"""
        self.router = router
        self.host = host
        self.port = port
        self.keepalive_timeout = keepalive_timeout
        self.max_body_bytes = max_body_bytes
        self.accepted_connections = 0
        self.handled_requests = 0
        self._listener: socket.socket | None = None

    @property
    def address(self) -> tuple[str, int]:
        """待ち受けている (ホスト, ポート)（実装済み）。"""
        if self._listener is None:
            raise RuntimeError("start() の前です")
        host, port = self._listener.getsockname()[:2]
        return host, port

    def start(self) -> tuple[str, int]:
        raise NotImplementedError("演習2: MiniHTTPServer.start を実装してください")

    def stop(self) -> None:
        raise NotImplementedError("演習2: MiniHTTPServer.stop を実装してください")

    def __enter__(self) -> MiniHTTPServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()
