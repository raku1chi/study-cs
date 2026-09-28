"""HTTP サーバー（標準ライブラリの wsgiref ＋ スレッド）。

wsgiref は WSGI の参照実装で、本番用のサーバーではありません（HTTP/1.0 で接続を使い回さない、
TLS なし、性能と堅牢性は最低限）。この教材では、HTTP サーバーとアプリケーションの境界を
見えるようにするために使います。本番相当の構成では言語ごとの本番用アプリケーションサーバーを使い、
TLS はロードバランサーやリバースプロキシで終端するのが一般的です（5.4 章）。
"""
from __future__ import annotations

import logging
import socketserver
from typing import Any, Callable
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer
from wsgiref.simple_server import make_server as _wsgiref_make_server

logger = logging.getLogger("taskapi")
access_logger = logging.getLogger("taskapi.access")


class ThreadingWSGIServer(socketserver.ThreadingMixIn, WSGIServer):
    """1 リクエストを 1 スレッドで処理する WSGI サーバー。"""

    # TODO(M5): グレースフルシャットダウンでは、処理中のリクエストが終わるのを待ってから終了したい。
    #   daemon_threads = True のままだと、プロセスの終了時に処理中のスレッドが途中で打ち切られる。
    daemon_threads = True


class RequestHandler(WSGIRequestHandler):
    """wsgiref の標準のハンドラ。アクセスログの出力先だけを logging に変えている。"""

    def log_message(self, format: str, *args: Any) -> None:  # 引数名は基底クラスに合わせている
        # wsgiref は既定でアクセスログを標準エラー出力に直接書く。logging に流して扱いを統一する。
        # TODO(M4): リクエストID・ルート・ステータス・所要時間を含む構造化ログ（JSON Lines）にする
        access_logger.info("%s %s", self.address_string(), format % args)


def make_server(app: Callable[..., Any], host: str = "127.0.0.1", port: int = 8000) -> ThreadingWSGIServer:
    """サーバーを作る（待ち受けループはまだ始めない）。port=0 なら OS が空きポートを選ぶ。"""
    return _wsgiref_make_server(host, port, app, server_class=ThreadingWSGIServer, handler_class=RequestHandler)


def serve(app: Callable[..., Any], host: str, port: int) -> None:
    server = make_server(app, host, port)
    logger.info("listening on http://%s:%d", host, server.server_port)
    # TODO(M5): SIGTERM を受けたら、(1) readiness を 503 にする (2) 新規の受け付けを止める
    #   (3) 処理中のリクエストを期限付きで待つ (4) 終了する — というグレースフルシャットダウンを実装する。
    #   server.shutdown() は serve_forever() とは別のスレッドから呼ぶ必要がある点に注意。
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("interrupted")
    finally:
        server.server_close()
