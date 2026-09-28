"""5.2 TCPとUDP — 演習（framing）: 長さプレフィックスによるメッセージの区切り

TCP は「バイトの流れ（バイトストリーム）」を運ぶだけで、送信側の send() 1 回分の区切りは
受信側に伝わりません。1 回の recv() に 2 つのメッセージがくっついて届くことも、1 つの
メッセージが 3 回に分かれて届くこともあります。そこで、アプリケーションの側で
メッセージの区切り方（フレーミング）を決める必要があります。

この演習では、最も基本的な「長さプレフィックス」方式を実装します。

    フレーム = [データの長さ: 4 バイト、ビッグエンディアンの符号なし整数][データ]

    例: b"abc" → b"\\x00\\x00\\x00\\x03abc"

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.2
    python3 tools/check.py -v 5.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_framing
"""
from __future__ import annotations

import struct

HEADER = struct.Struct("!I")  # 4 バイト、ビッグエンディアンの符号なし整数（実装済み）
HEADER_SIZE = HEADER.size  # 4
MAX_LENGTH = 2**32 - 1
DEFAULT_MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MiB


class FrameTooLarge(ValueError):
    """フレームが上限を超えている（実装済み）。"""


class IncompleteFrame(ValueError):
    """ストリームがフレームの途中で終わった（実装済み）。"""


# ---------------------------------------------------------------------------
# 演習1（★★☆）: フレームのエンコードとデコード
# ---------------------------------------------------------------------------

def encode_frame(payload: bytes) -> bytes:
    """payload の前に 4 バイトの長さを付けたフレームを返す。

    - payload が bytes・bytearray・memoryview 以外なら TypeError（str はエンコードしてから渡す）。
    - 長さが 4 バイトで表せない（2**32 - 1 を超える）なら FrameTooLarge。

    >>> encode_frame(b"abc")
    b'\\x00\\x00\\x00\\x03abc'
    >>> encode_frame(b"")
    b'\\x00\\x00\\x00\\x00'

    ヒント: HEADER.pack(len(payload)) で 4 バイトのヘッダが作れる。
    ヘッダとデータを別々に send() するより、1 つのバイト列にまとめて送る方がよい
    （理由は本文の「Nagle アルゴリズムと遅延 ACK」を参照）。
    """
    raise NotImplementedError("演習1: encode_frame を実装してください")


class FrameDecoder:
    """受信したバイト列を少しずつ与えると、完成したフレームを取り出して返すデコーダ。

    >>> d = FrameDecoder()
    >>> d.feed(b"\\x00\\x00\\x00\\x05hel")    # まだ途中
    []
    >>> d.feed(b"lo\\x00\\x00\\x00\\x01!\\x00")  # 1 つ目の残り・2 つ目・3 つ目の途中
    [b'hello', b'!']
    >>> d.buffered
    1

    要件:
        - feed(data) は、data を内部のバッファに追加し、完成したフレームのデータ部分
          （ヘッダを除いたもの）を bytes のリストにして、届いた順に返す。1 つもなければ []。
        - data はどこで区切られていてもよい（ヘッダの途中、データの途中、複数のフレームを含む…）。
        - 長さが max_frame_size を超えるフレームのヘッダを受け取ったら、**データを待たずに
          その時点で** FrameTooLarge を送出する。長さだけ巨大な値のヘッダを送りつけて、受信側に
          メモリを確保させ続ける攻撃を防ぐため。送出した後、そのデコーダは使わない（接続を閉じる）。
        - buffered は「受け取ったが、まだフレームとして返していないバイト数」（読み終えたヘッダを含む）。
        - eof() は、接続が閉じられたときに呼ぶ。フレームの途中のデータが残っていれば IncompleteFrame。
        - max_frame_size < 0 なら ValueError。

    ヒント:
        - バッファには bytearray を使い、「ヘッダを読む → データがそろうのを待つ → 切り出す」を
          while ループで繰り返す（1 回の feed で複数のフレームが完成しうる）。
        - 「今読んでいるフレームの長さ」（ヘッダを読み終えたかどうか）を状態として持つとよい。
        - bytes 同士の + を繰り返すと、そのたびに全体をコピーするので遅くなる。
    """

    def __init__(self, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> None:
        raise NotImplementedError("演習1: FrameDecoder.__init__ を実装してください")

    def feed(self, data: bytes) -> list[bytes]:
        raise NotImplementedError("演習1: FrameDecoder.feed を実装してください")

    @property
    def buffered(self) -> int:
        raise NotImplementedError("演習1: FrameDecoder.buffered を実装してください")

    def eof(self) -> None:
        raise NotImplementedError("演習1: FrameDecoder.eof を実装してください")
