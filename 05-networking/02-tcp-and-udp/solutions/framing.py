"""5.2 TCPとUDP — 解答例（framing）

演習の仕様は exercises/framing.py の docstring を参照してください。
"""
from __future__ import annotations

import struct

HEADER = struct.Struct("!I")  # 4 バイト、ビッグエンディアンの符号なし整数
HEADER_SIZE = HEADER.size
MAX_LENGTH = 2**32 - 1
DEFAULT_MAX_FRAME_SIZE = 16 * 1024 * 1024  # 16 MiB


class FrameTooLarge(ValueError):
    """フレームが上限を超えている。"""


class IncompleteFrame(ValueError):
    """ストリームがフレームの途中で終わった。"""


def encode_frame(payload: bytes) -> bytes:
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError(f"bytes を渡してください: {type(payload).__name__}")
    if len(payload) > MAX_LENGTH:
        raise FrameTooLarge(f"4 バイトの長さで表せません: {len(payload)}")
    # ヘッダとデータを 1 つのバイト列にしておくと、送信が 1 回で済む（Nagle との相互作用も避けられる）
    return HEADER.pack(len(payload)) + bytes(payload)


class FrameDecoder:
    def __init__(self, max_frame_size: int = DEFAULT_MAX_FRAME_SIZE) -> None:
        if max_frame_size < 0:
            raise ValueError(f"max_frame_size は 0 以上です: {max_frame_size}")
        self.max_frame_size = max_frame_size
        self._buf = bytearray()
        self._length: int | None = None  # ヘッダを読み終えたフレームの長さ（未読なら None）

    def feed(self, data: bytes) -> list[bytes]:
        self._buf += data
        frames: list[bytes] = []
        while True:
            if self._length is None:
                if len(self._buf) < HEADER_SIZE:
                    break  # ヘッダがまだそろっていない
                (length,) = HEADER.unpack_from(self._buf)
                # データを溜め込む「前」に上限を確かめる。長さだけ巨大な値を送りつけて
                # メモリを使い果たさせる攻撃（DoS）を、ヘッダの 4 バイトを見た時点で止める
                if length > self.max_frame_size:
                    raise FrameTooLarge(f"フレームが大きすぎます: {length} > {self.max_frame_size}")
                del self._buf[:HEADER_SIZE]  # bytearray の先頭の削除は CPython では償却 O(1)
                self._length = length
            if len(self._buf) < self._length:
                break  # データがまだそろっていない
            frames.append(bytes(self._buf[: self._length]))
            del self._buf[: self._length]
            self._length = None
        return frames

    @property
    def buffered(self) -> int:
        # 受け取ったが、まだフレームとして返していないバイト数（読み終えたヘッダも含む）
        return len(self._buf) + (HEADER_SIZE if self._length is not None else 0)

    def eof(self) -> None:
        if self.buffered:
            raise IncompleteFrame(f"フレームの途中で接続が終わりました（未処理 {self.buffered} バイト）")
