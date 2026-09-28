"""6.4 ストレージエンジンと障害回復 — 演習1 解答例: Bitcask 方式のキーバリューストア

演習の仕様は exercises/kvstore.py の docstring を参照してください。
"""
from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# 提供済み: レコードの形式（スタブと同じ）
# ---------------------------------------------------------------------------

HEADER = struct.Struct(">III")  # crc32, key_len, value_len（ビッグエンディアンの符号なし 32 ビット × 3）
TOMBSTONE = 0xFFFFFFFF          # value_len がこの値なら削除（墓標）。値のバイト列は続かない
DATA_FILE = "data.log"
COMPACT_FILE = "data.log.compact"


def encode_record(key: bytes, value: bytes | None) -> bytes:
    value_len = TOMBSTONE if value is None else len(value)
    body = struct.pack(">II", len(key), value_len) + key + (value or b"")
    return struct.pack(">I", zlib.crc32(body)) + body


def fsync_directory(path: Path) -> None:
    """ディレクトリのエントリ（ファイル名の変更）を永続化する（POSIX のみ。他の OS では何もしない）。"""
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class BitcaskStore:
    def __init__(self, directory: str | os.PathLike, *, sync: bool = False) -> None:
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.sync = sync
        self.keydir: dict[bytes, tuple[int, int]] = {}  # キー → (値の位置, 値の長さ)
        self.truncated_bytes = 0
        # コンパクションの途中でクラッシュした残骸は信用できないので捨てる
        # （置き換えは os.replace の 1 回で行うので、data.log 自体は常に完全な状態のどちらか）
        stale = self.dir / COMPACT_FILE
        if stale.exists():
            stale.unlink()
        self.path = self.dir / DATA_FILE
        self.path.touch(exist_ok=True)
        self._recover()
        self._file = open(self.path, "r+b")
        self._file.seek(0, os.SEEK_END)

    # --- 演習1-1: 起動時の回復 --------------------------------------------------

    def _recover(self) -> None:
        data = self.path.read_bytes()
        pos = 0
        while pos < len(data):
            end = self._parse_record(data, pos)
            if end is None:
                break  # 途中で途切れた・壊れたレコード。ここから後ろは信用しない
            pos = end
        if pos < len(data):
            # 書き込み途中のクラッシュでできた不完全な末尾（torn write）を切り捨てる
            self.truncated_bytes = len(data) - pos
            with open(self.path, "r+b") as f:
                f.truncate(pos)
                f.flush()
                os.fsync(f.fileno())

    def _parse_record(self, data: bytes, pos: int) -> int | None:
        """pos から 1 レコードを読んで keydir に反映し、次のレコードの位置を返す（壊れていれば None）。"""
        if pos + HEADER.size > len(data):
            return None
        crc, key_len, value_len = HEADER.unpack_from(data, pos)
        start = pos + HEADER.size
        body_len = key_len + (0 if value_len == TOMBSTONE else value_len)
        end = start + body_len
        if end > len(data):
            return None
        if zlib.crc32(data[pos + 4:end]) != crc:
            return None  # チェックサムが合わない: 途中までしか書かれていないか、壊れている
        key = data[start:start + key_len]
        if value_len == TOMBSTONE:
            self.keydir.pop(key, None)
        else:
            self.keydir[key] = (start + key_len, value_len)
        return end

    # --- 演習1-2: 読み書き ------------------------------------------------------

    @staticmethod
    def _check(key: bytes, value: bytes | None = None) -> None:
        if not isinstance(key, bytes) or not key:
            raise TypeError("キーは空でない bytes にしてください")
        if value is not None and not isinstance(value, bytes):
            raise TypeError("値は bytes にしてください")

    def _append(self, record: bytes) -> int:
        offset = self._file.seek(0, os.SEEK_END)
        self._file.write(record)
        self._file.flush()  # Python のバッファから OS へ渡す（プロセスが落ちても残る）
        if self.sync:
            os.fsync(self._file.fileno())  # OS のキャッシュからディスクへ（電源が落ちても残る）
        return offset

    def put(self, key: bytes, value: bytes) -> None:
        self._check(key, value)
        offset = self._append(encode_record(key, value))
        # 値の位置 = レコードの先頭 + ヘッダ + キー
        self.keydir[key] = (offset + HEADER.size + len(key), len(value))

    def get(self, key: bytes) -> bytes | None:
        self._check(key)
        entry = self.keydir.get(key)
        if entry is None:
            return None
        offset, length = entry
        self._file.seek(offset)  # 1 回のシークと読み込みで値が取れる
        return self._file.read(length)

    def delete(self, key: bytes) -> bool:
        self._check(key)
        if key not in self.keydir:
            return False
        self._append(encode_record(key, None))  # 追記専用なので、削除も「墓標」の追記で表す
        del self.keydir[key]
        return True

    def keys(self) -> list[bytes]:
        return sorted(self.keydir)

    def __len__(self) -> int:
        return len(self.keydir)

    def file_size(self) -> int:
        return self.path.stat().st_size

    # --- 演習1-3: コンパクション ------------------------------------------------

    def compact(self) -> None:
        tmp = self.dir / COMPACT_FILE
        new_keydir: dict[bytes, tuple[int, int]] = {}
        with open(tmp, "wb") as out:
            pos = 0
            for key in sorted(self.keydir):  # 生きているキーの最新の値だけを書き出す
                value = self.get(key)
                record = encode_record(key, value)
                out.write(record)
                new_keydir[key] = (pos + HEADER.size + len(key), len(value))
                pos += len(record)
            out.flush()
            os.fsync(out.fileno())  # 置き換える前に、新しいファイルの中身を永続化する
        self._file.close()
        os.replace(tmp, self.path)  # 原子的な置き換え: クラッシュしても古いか新しいかのどちらか
        fsync_directory(self.dir)
        self.keydir = new_keydir
        self._file = open(self.path, "r+b")
        self._file.seek(0, os.SEEK_END)

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()

    def __enter__(self) -> BitcaskStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
