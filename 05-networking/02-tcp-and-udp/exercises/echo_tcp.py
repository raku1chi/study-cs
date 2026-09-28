"""5.2 TCPとUDP — 演習（echo_tcp）: ソケット API で作る TCP サーバーとクライアント

framing.py の長さプレフィックス方式を使って、本物の TCP の上でメッセージをやりとりする
エコーサーバー（受け取ったメッセージをそのまま、または handler で変換して返す）と
クライアントを実装します。framing.py の演習1を先に終わらせてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.2
    python3 tools/check.py -v 5.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_echo_tcp

制約:
    - send_all では sock.sendall()、recv_exact では socket.makefile() などを使わず、
      send() / recv() の戻り値を見るループで実装してください（部分的な送受信を体験するため）。
    - テストは 127.0.0.1 の空いているポート（port=0）だけを使います。

使うソケット API（詳しくは本文の「ソケット API」の節）:
    サーバー: socket() → setsockopt(SO_REUSEADDR) → bind() → listen() → accept() → recv()/send() → close()
    クライアント: socket.create_connection((host, port), timeout=...) → send()/recv() → close()
"""
from __future__ import annotations

import socket
import threading  # noqa: F401  EchoServer で使います
from typing import Callable

from framing import HEADER, HEADER_SIZE, FrameDecoder, FrameTooLarge, encode_frame  # noqa: F401

DEFAULT_MAX_FRAME_SIZE = 16 * 1024 * 1024
RECV_SIZE = 65536


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 部分的な送受信を扱う
# ---------------------------------------------------------------------------

def send_all(sock: socket.socket, data: bytes) -> None:
    """data をすべて送り終えるまで sock.send() を繰り返す。

    - sock.send(buf) は、カーネルの送信バッファに空きがある分しか受け取らず、実際に受け取った
      バイト数を返す（len(buf) より小さいことがある）。残りを送り直すこと。
    - send() が 0 を返したら、接続が使えなくなったとみなして ConnectionError を送出する。

    ヒント: memoryview(data)[total:] を使うと、スライスのたびにデータをコピーせずに済む。
    """
    raise NotImplementedError("演習4: send_all を実装してください")


def recv_exact(sock: socket.socket, n: int) -> bytes:
    """ちょうど n バイトを受信するまで sock.recv() を繰り返し、n バイトの bytes を返す。

    - sock.recv(k) は「最大」k バイトを返す。届いている分だけ返るので、足りなければ繰り返す。
    - recv() が b"" を返したら、相手が送信を終えた（FIN を受け取った）ということ。
      n バイトそろう前にそうなったら ConnectionError を送出する。
    - n == 0 なら b"" を返す。
    """
    raise NotImplementedError("演習4: recv_exact を実装してください")


def recv_frame(sock: socket.socket, *, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> bytes:
    """フレームを 1 つ受信してデータ部分を返す（クライアント用）。

    4 バイトのヘッダを recv_exact で読み、長さが max_frame_size を超えていれば FrameTooLarge、
    そうでなければその長さのデータを recv_exact で読んで返す。
    """
    raise NotImplementedError("演習4: recv_frame を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: スレッドで複数の接続を扱うエコーサーバー
# ---------------------------------------------------------------------------

class EchoServer:
    """接続ごとにスレッドを 1 つ使う（thread-per-connection）エコーサーバー。

    使い方:
        server = EchoServer()              # port=0 なら OS が空いているポートを選ぶ
        host, port = server.start()        # 待ち受けを始め、実際のアドレスを返す
        ...
        server.stop()

        with EchoServer() as server:       # with 文でも使える（__enter__ で start、__exit__ で stop）
            client = EchoClient(server.address)

    要件:
        - start(): 待ち受け用のソケットを作って bind・listen し、accept を繰り返すスレッドを
          起動して、(ホスト, 実際のポート番号) を返す。SO_REUSEADDR を設定すること。
        - 接続を受け付けるたびに、その接続を処理するスレッドを起動する。処理の内容:
            recv() で受け取ったバイト列を FrameDecoder（max_frame_size 付き）に与え、完成した
            フレームごとに handler(フレーム) の結果を encode_frame して send_all で返す。
            1 回の recv() に複数のフレームやフレームの一部が入っていても正しく扱うこと。
          recv() が b"" を返したら（クライアントが閉じたら）接続を閉じる。
          FrameTooLarge や OSError が起きたら接続を閉じる（サーバー全体は止めない）。
        - stop(): 新しい接続の受け付けをやめ、処理中の接続をすべて閉じ、スレッドの終了を待つ。
          アイドルな接続が残っていても、数秒以内に戻ること。

    ヒント:
        - 待ち受けソケットに settimeout(0.1) を設定すると、accept() が 0.1 秒ごとに
          socket.timeout で戻るので、そのたびに「停止要求（threading.Event）」を確認できる。
        - 別のスレッドで recv() を待っている接続は、conn.shutdown(socket.SHUT_RDWR) で起こせる
          （recv() が b"" を返すか、OSError になる）。
        - 処理中の接続の集合を複数のスレッドから触るので、threading.Lock で守る。
        - スレッドは daemon=True にしておくと、万一止め損ねてもテストのプロセスが終われる。
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        *,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
        handler: Callable[[bytes], bytes] | None = None,
    ) -> None:
        """設定を保存する（実装済み）。ソケットはまだ作らない。"""
        self.host = host
        self.port = port
        self.max_frame_size = max_frame_size
        self.handler = handler or (lambda payload: payload)
        self._listener: socket.socket | None = None
        # 必要に応じて、停止要求の Event・接続の集合・Lock・スレッドのリストなどを追加してください

    @property
    def address(self) -> tuple[str, int]:
        """待ち受けている (ホスト, ポート)（実装済み）。start() で self._listener を設定しておくこと。"""
        if self._listener is None:
            raise RuntimeError("start() の前です")
        host, port = self._listener.getsockname()[:2]
        return host, port

    def start(self) -> tuple[str, int]:
        raise NotImplementedError("演習4: EchoServer.start を実装してください")

    def stop(self) -> None:
        raise NotImplementedError("演習4: EchoServer.stop を実装してください")

    def __enter__(self) -> EchoServer:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()


class EchoClient:
    """EchoServer に接続し、フレーム単位でリクエストとレスポンスをやりとりするクライアント。

    - __init__: socket.create_connection(address, timeout=timeout) で接続する（接続にも送受信にも
      timeout 秒の上限が付く）。TCP_NODELAY を設定するとよい（本文の Nagle の節を参照）。
    - request(payload): encode_frame(payload) を send_all で送り、recv_frame で応答を 1 つ読んで返す。
      応答が max_frame_size を超えるなら FrameTooLarge（ValueError の一種）。
      サーバーが接続を閉じていたら ConnectionError（send / recv が送出する OSError の一種も含む）。
    - close(): 接続を閉じる。with 文でも使える。

    >>> with EchoServer() as server, EchoClient(server.address) as client:   # doctest: +SKIP
    ...     client.request(b"hello")
    b'hello'
    """

    def __init__(
        self,
        address: tuple[str, int],
        *,
        timeout: float = 5.0,
        max_frame_size: int = DEFAULT_MAX_FRAME_SIZE,
    ) -> None:
        raise NotImplementedError("演習4: EchoClient.__init__ を実装してください")

    def request(self, payload: bytes) -> bytes:
        raise NotImplementedError("演習4: EchoClient.request を実装してください")

    def close(self) -> None:
        raise NotImplementedError("演習4: EchoClient.close を実装してください")

    def __enter__(self) -> EchoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
