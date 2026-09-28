"""6.4 ストレージエンジンと障害回復 — 演習1: Bitcask 方式のキーバリューストア

Riak で使われた Bitcask（Basho, 2010）の設計にならった、追記専用のログと、メモリ上のハッシュ索引
（keydir）からなるキーバリューストアを実装します。ログ構造のストレージの基本と、
「書き込みの途中でクラッシュしたらどうなるか」を体験するのが目的です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.4
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_kvstore

ファイルの形式（data.log に、レコードを次々に追記する）:

    +----------+-----------+-------------+-----------+-------------+
    | crc32    | key_len   | value_len   | key       | value       |
    | 4 バイト | 4 バイト  | 4 バイト    | key_len   | value_len   |
    +----------+-----------+-------------+-----------+-------------+
      ↑ crc32 は key_len から value の末尾までの zlib.crc32。整数はビッグエンディアンの符号なし
      value_len が 0xFFFFFFFF（TOMBSTONE）のレコードは削除（墓標）で、value は続かない

    encode_record(key, value) が 1 レコード分のバイト列を作る（提供済み）。

約束:
    - キーは空でない bytes、値は bytes（そうでなければ TypeError）。
    - keydir: {キー: (値の先頭のファイル内の位置, 値の長さ)}。値そのものはメモリに持たず、
      get のたびにファイルから読む（1 回のシークで読める、が Bitcask の売り）。
    - 書き込みのたびに flush() する。sync=True なら os.fsync() もする。
    - 使ってはいけないもの: dbm、shelve、sqlite3 など既存のストレージエンジン。
"""
from __future__ import annotations

import os
import struct
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# 提供済み: レコードの形式（変更しなくてよい）
# ---------------------------------------------------------------------------

HEADER = struct.Struct(">III")  # crc32, key_len, value_len（ビッグエンディアンの符号なし 32 ビット × 3）
TOMBSTONE = 0xFFFFFFFF          # value_len がこの値なら削除（墓標）。値のバイト列は続かない
DATA_FILE = "data.log"
COMPACT_FILE = "data.log.compact"


def encode_record(key: bytes, value: bytes | None) -> bytes:
    """1 レコード分のバイト列を作る。value が None なら墓標。

    >>> encode_record(b"k", b"v").hex(" ")      # crc32 | key_len=1 | value_len=1 | 'k' | 'v'
    '7b 50 6f 90 00 00 00 01 00 00 00 01 6b 76'
    >>> encode_record(b"k", None).hex(" ")      # 墓標: value_len = 0xFFFFFFFF
    'ce e8 77 39 00 00 00 01 ff ff ff ff 6b'
    """
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
    """追記専用ログ＋メモリ上の索引のキーバリューストア。

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     with BitcaskStore(d) as db:
    ...         db.put(b"apple", b"red")
    ...         db.put(b"apple", b"green")      # 上書きも「追記」
    ...         db.get(b"apple"), len(db)
    (b'green', 1)
    """

    # -----------------------------------------------------------------------
    # 演習1-1（★★☆）: 起動と、クラッシュからの回復
    # -----------------------------------------------------------------------

    def __init__(self, directory: str | os.PathLike, *, sync: bool = False) -> None:
        """directory（なければ作る）の data.log を開き、keydir を組み立てる。

        手順:
          1. directory/data.log.compact が残っていたら削除する（コンパクションの途中でクラッシュした残骸）。
          2. data.log を先頭から 1 レコードずつ読み、keydir を組み立てる（同じキーは後のレコードが勝つ。
             墓標ならキーを keydir から消す）。
          3. 途中で「ヘッダが途中で切れている」「キーや値が途中で切れている」「crc32 が合わない」
             レコードに出会ったら、そこから後ろは書き込みの途中でクラッシュした不完全な末尾とみなし、
             ファイルをその位置で切り詰める（truncate）。切り捨てたバイト数を self.truncated_bytes に
             入れる（切り捨てがなければ 0）。
          4. 追記用にファイルを開いたままにする（例: open(path, "r+b")）。

        属性（テストが参照する）: self.keydir, self.truncated_bytes, self.path（data.log の Path）

        簡略化: 本物のシステムは、ファイルの途中の破損（ハードウェアの故障など）と、末尾の書きかけを
        区別して扱う。ここでは最初に見つかった不正なレコード以降をすべて捨てる。
        """
        raise NotImplementedError("演習1-1: __init__（回復）を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-2（★☆☆）: 読み書き
    # -----------------------------------------------------------------------

    def put(self, key: bytes, value: bytes) -> None:
        """レコードをファイルの末尾に追記し、keydir を更新する。"""
        raise NotImplementedError("演習1-2: put を実装してください")

    def get(self, key: bytes) -> bytes | None:
        """keydir で位置を調べ、ファイルから値を読む。なければ None。"""
        raise NotImplementedError("演習1-2: get を実装してください")

    def delete(self, key: bytes) -> bool:
        """キーがあれば墓標を追記して keydir から消し True。なければ何もせず False。"""
        raise NotImplementedError("演習1-2: delete を実装してください")

    def keys(self) -> list[bytes]:
        """生きているキーを昇順で返す。"""
        raise NotImplementedError("演習1-2: keys を実装してください")

    def __len__(self) -> int:
        """生きているキーの数。"""
        raise NotImplementedError("演習1-2: __len__ を実装してください")

    def file_size(self) -> int:
        """data.log の現在のバイト数。"""
        raise NotImplementedError("演習1-2: file_size を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-3（★★☆）: コンパクション
    # -----------------------------------------------------------------------

    def compact(self) -> None:
        """生きているキーの最新の値だけを新しいファイルに書き直し、古いファイルと置き換える。

        手順（クラッシュしても data.log が壊れないように）:
          1. data.log.compact に、生きているキーのレコードを（キーの昇順で）書く。墓標は書かない。
          2. flush と os.fsync で、新しいファイルの中身を永続化する。
          3. os.replace(data.log.compact, data.log) で置き換える（原子的な名前の変更）。
             fsync_directory(ディレクトリ) で名前の変更も永続化する。
          4. keydir を新しいファイルの位置で作り直し、追記用のファイルを開き直す。

        上書きや削除を繰り返すとファイルには古いレコードが溜まる（空間の増幅）。
        コンパクションはそれを回収する。
        """
        raise NotImplementedError("演習1-3: compact を実装してください")

    # --- 提供済み ---------------------------------------------------------------

    def close(self) -> None:
        """ファイルを閉じる（__init__ で self._file に開いたファイルを入れた前提）。"""
        f = getattr(self, "_file", None)
        if f is not None and not f.closed:
            f.close()

    def __enter__(self) -> BitcaskStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
