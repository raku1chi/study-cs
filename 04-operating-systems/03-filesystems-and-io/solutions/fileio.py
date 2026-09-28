"""4.3 ファイルシステムとI/O — 解答例: 原子的な書き込み・tail・ストリーム処理・レコードログ

演習の仕様は exercises/fileio.py の docstring を参照してください。
"""
from __future__ import annotations

import os
import stat
import struct
import uuid
import zlib
from typing import BinaryIO, NamedTuple


# ---------------------------------------------------------------------------
# 演習1: 原子的なファイルの置き換え
# ---------------------------------------------------------------------------

def atomic_write(path: str | os.PathLike, data: bytes) -> None:
    path = os.fspath(path)
    directory = os.path.dirname(os.path.abspath(path))
    # 一時ファイルは必ず「同じディレクトリ」に作る。rename が原子的なのは同じファイルシステム内だけ
    tmp = os.path.join(directory, f".{os.path.basename(path)}.{uuid.uuid4().hex}.tmp")
    # O_EXCL で既存ファイルを誤って上書きしない。モード 0o666 には umask が適用される（普通の open と同じ）
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        try:
            if hasattr(os, "fchmod"):
                # 既存ファイルのパーミッションを引き継ぐ（忘れると、置き換えるたびに権限が変わってしまう）
                try:
                    os.fchmod(fd, stat.S_IMODE(os.stat(path).st_mode))
                except FileNotFoundError:
                    pass
            view = memoryview(data)  # bytes 以外（str など）はここで TypeError になる
            while view:
                n = os.write(fd, view)  # 一度に全部は書けないことがある
                view = view[n:]
            os.fsync(fd)  # (1) 中身をディスクに届ける。これを rename の前に行うのが要点
        finally:
            os.close(fd)
        os.replace(tmp, path)  # (2) 名前を原子的に付け替える。読み手は旧版か新版のどちらかしか見ない
    except BaseException:
        try:
            os.unlink(tmp)  # 失敗したら一時ファイルを残さない
        except FileNotFoundError:
            pass
        raise
    _fsync_directory(directory)  # (3) 名前の変更（ディレクトリの内容）も永続化する


def _fsync_directory(directory: str) -> None:
    if os.name != "posix":
        return  # Windows ではディレクトリを開いて fsync できない
    dfd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


# ---------------------------------------------------------------------------
# 演習2: tail（後ろから読む）
# ---------------------------------------------------------------------------

def tail(f: BinaryIO, n: int, *, block_size: int = 4096) -> list[bytes]:
    if n < 0:
        raise ValueError(f"n は 0 以上: {n}")
    if block_size < 1:
        raise ValueError(f"block_size は 1 以上: {block_size}")
    f.seek(0, os.SEEK_END)
    size = f.tell()
    if n == 0 or size == 0:
        return []
    pos = size
    chunks: list[bytes] = []
    newlines = 0
    # 末尾の改行を含めて n+1 個の改行が見つかれば、最後の n 行は確実に手元にそろう
    while pos > 0 and newlines <= n:
        step = min(block_size, pos)
        pos -= step
        f.seek(pos)
        chunk = f.read(step)
        chunks.append(chunk)
        newlines += chunk.count(b"\n")
    data = b"".join(reversed(chunks))
    if data.endswith(b"\n"):
        data = data[:-1]  # 最後の改行は「最後の行の終わり」であって、空の行の始まりではない
    lines = data.split(b"\n")
    # pos > 0 で打ち切ったときの lines[0] は途中から始まる行だが、改行が十分あるので捨てられる
    return lines[-n:]


# ---------------------------------------------------------------------------
# 演習3: 大きなファイルを一定のメモリで数える
# ---------------------------------------------------------------------------

class Counts(NamedTuple):
    lines: int
    words: int
    bytes: int


_WHITESPACE = frozenset(b" \t\n\r\x0b\x0c")  # bytes.split() が区切りに使う ASCII の空白


def count_file(path: str | os.PathLike, *, chunk_size: int = 64 * 1024) -> Counts:
    if chunk_size < 1:
        raise ValueError(f"chunk_size は 1 以上: {chunk_size}")
    lines = words = total = 0
    in_word = False  # 直前のチャンクが単語の途中で終わったか（境界をまたぐ単語を二重に数えないため）
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            lines += chunk.count(b"\n")
            words += len(chunk.split())
            if in_word and chunk[0] not in _WHITESPACE:
                words -= 1  # 前のチャンクの最後の単語の続きなので、新しい単語ではない
            in_word = chunk[-1] not in _WHITESPACE
    return Counts(lines, words, total)


# ---------------------------------------------------------------------------
# 演習4: 長さ＋CRC32 で区切ったレコードログと、途中で切れた末尾の回復
# ---------------------------------------------------------------------------

HEADER = struct.Struct(">II")  # (ペイロードの長さ, ペイロードの CRC32)。ビッグエンディアンの 32 ビット符号なし整数 × 2
MAX_RECORD_SIZE = 16 * 1024 * 1024


def encode_record(payload: bytes) -> bytes:
    if not isinstance(payload, (bytes, bytearray, memoryview)):
        raise TypeError(f"payload は bytes: {type(payload).__name__}")
    payload = bytes(payload)
    if len(payload) > MAX_RECORD_SIZE:
        raise ValueError(f"レコードが大きすぎます: {len(payload)} バイト")
    return HEADER.pack(len(payload), zlib.crc32(payload)) + payload


def decode_records(data: bytes) -> tuple[list[bytes], int]:
    records: list[bytes] = []
    offset = 0
    while True:
        if len(data) - offset < HEADER.size:
            break  # ヘッダが途中で切れている（または終端）
        length, crc = HEADER.unpack_from(data, offset)
        if length > MAX_RECORD_SIZE:
            break  # 壊れた長さ。信じて読み進めると、とんでもない量を読むことになる
        start = offset + HEADER.size
        end = start + length
        if end > len(data):
            break  # ペイロードが途中で切れている（書き込み中のクラッシュ）
        payload = data[start:end]
        if zlib.crc32(payload) != crc:
            break  # 中身が壊れている。これ以降の区切りも信用できないので、ここで打ち切る
        records.append(payload)
        offset = end
    return records, offset


class RecordLog:
    def __init__(self, path: str | os.PathLike, *, sync: bool = True) -> None:
        self.path = os.fspath(path)
        self.sync = sync
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        self._f = os.fdopen(fd, "r+b")
        # 回復: 先頭から正しいレコードだけを読み、壊れた末尾（途中で切れた書き込み）を切り詰める
        data = self._f.read()
        _, valid_end = decode_records(data)
        self.truncated_bytes = len(data) - valid_end
        if self.truncated_bytes:
            self._f.truncate(valid_end)
            self._f.flush()
            os.fsync(self._f.fileno())  # 切り詰めた結果も永続化してから書き込みを受け付ける
        self._f.seek(0, os.SEEK_END)

    def append(self, payload: bytes) -> int:
        record = encode_record(payload)
        offset = self._f.seek(0, os.SEEK_END)
        self._f.write(record)  # ヘッダとペイロードを 1 回の write でまとめて書く
        self._f.flush()  # Python のバッファからカーネル（ページキャッシュ）へ
        if self.sync:
            os.fsync(self._f.fileno())  # ページキャッシュからディスクへ。ここまでして初めて「書けた」と言える
        return offset

    def records(self) -> list[bytes]:
        self._f.seek(0)
        data = self._f.read()
        self._f.seek(0, os.SEEK_END)
        return decode_records(data)[0]

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "RecordLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
