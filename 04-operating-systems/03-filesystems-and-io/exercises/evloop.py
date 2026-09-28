"""4.3 ファイルシステムとI/O — 演習5: selectors によるイベントループのエコーサーバー

1 つのスレッドで多数の接続を同時に扱う「イベントループ」を、標準ライブラリの selectors
（Linux では epoll、macOS では kqueue を使う）で実装します。受け取ったバイトをそのまま送り返す
エコーサーバーですが、本物のサーバーと同じ難しさ（部分的な読み書き、背圧、切断、停止）を含みます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.3
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_evloop

手で試す（実装後）:
    python3 evloop.py 8888          # 別の端末で: nc 127.0.0.1 8888

制約: asyncio・socketserver・スレッドによる接続ごとの並行処理は使わないでください。
      使ってよいのは socket・selectors・threading.Event（停止の合図）です。
"""
from __future__ import annotations

import selectors  # noqa: F401
import socket  # noqa: F401
import sys
import threading  # noqa: F401


# ---------------------------------------------------------------------------
# 演習5（★★★）: イベントループのエコーサーバー
# ---------------------------------------------------------------------------

class EchoServer:
    """エコーサーバー。

    EchoServer(host="127.0.0.1", port=0, *, recv_size=4096, high_water=64 * 1024)
        - コンストラクタの中で、待ち受けソケットを作って bind・listen まで済ませる
          （port=0 なら OS が空いているポートを選ぶ。テストは address でそれを知る）。
        - recv_size: 1 回の recv で読む最大バイト数。high_water: 背圧の閾値（下記）。
          どちらかが 1 未満なら ValueError（ソケットを作る前に検査する）。

    属性:
        address: (host, port) — 実際に待ち受けているアドレス（property）
        connections_accepted: 受け付けた接続の総数
        max_buffered: これまでに 1 つの接続の「未送信データ」が最大で何バイト溜まったか

    serve_forever() の要件:
        - すべてのソケット（待ち受け・各接続）をノンブロッキングにし、selector で
          「読める」「書ける」ようになったものだけを処理する。1 つの遅い接続で全体を止めない。
        - 読んだデータは接続ごとの送信バッファに追加し、送れるだけ送る。
          send() は一部しか送れないことがあるので、残りは EVENT_WRITE を待って送る（部分書き込み）。
        - 背圧: ある接続の送信バッファが high_water バイト以上溜まったら、その接続からの読み込み
          （EVENT_READ）を止め、送り切って減ったら再開する。相手が受信しないまま送り続けても、
          サーバーのメモリが際限なく増えないようにするため。
        - recv() が b"" を返したら、相手は送信を終えた（半分閉じた）。送信バッファに残っている
          データを送り切ってから、その接続を閉じる。
        - 接続ごとのエラー（ConnectionResetError など）では、その接続だけを閉じてループを続ける。
        - shutdown() が呼ばれたら速やかに（遅くとも 1 秒以内に）ループを抜け、すべての接続と
          待ち受けソケットを閉じてから戻る。

    shutdown() の要件:
        - 別のスレッドから呼べること。serve_forever() より前に呼ばれていたら、serve_forever() は
          すぐに戻る。

    ヒント:
        - selector.register(sock, events, data=...) の data に接続ごとの状態（送信バッファなど）を
          入れておくと、select() の結果から取り出せる。関心のあるイベントは selector.modify() で変える。
        - select() で眠っているループを別スレッドから起こすには、socket.socketpair() で作った
          ソケットの片方を selector に登録しておき、shutdown() でもう片方に 1 バイト書く
          （self-pipe の技法）。select(timeout=0.1) で定期的にフラグを確かめる方法でもよい。
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0, *,
                 recv_size: int = 4096, high_water: int = 64 * 1024) -> None:
        raise NotImplementedError("演習5: EchoServer.__init__ を実装してください")

    @property
    def address(self) -> tuple[str, int]:
        raise NotImplementedError("演習5: EchoServer.address を実装してください")

    def serve_forever(self) -> None:
        raise NotImplementedError("演習5: EchoServer.serve_forever を実装してください")

    def shutdown(self) -> None:
        raise NotImplementedError("演習5: EchoServer.shutdown を実装してください")


if __name__ == "__main__":
    server = EchoServer(port=int(sys.argv[1]) if len(sys.argv) > 1 else 8888)
    print("listening on", server.address)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
