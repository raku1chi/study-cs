"""4.3 ファイルシステムとI/O — 演習: 原子的な書き込み・tail・ストリーム処理・レコードログ

「データを失わない」「メモリを使いすぎない」ファイル操作の定番の技法を実装します。
各関数・メソッドの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.3          # 合格数を表示（evloop.py の演習5も含む）
    python3 tools/check.py -v 4.3       # 各テストの結果を詳しく表示
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_fileio

演習の一覧:
    演習1（★☆☆）: atomic_write — 途中でクラッシュしても壊れないファイルの置き換え
    演習2（★★☆）: tail — ファイルの末尾から読んで最後の n 行を返す
    演習3（★☆☆）: count_file — 大きなファイルを一定のメモリで数える（wc コマンド）
    演習4（★★★）: encode_record / decode_records / RecordLog — 長さ＋CRC32 のレコードログと障害回復

注意: テストは os.fsync・os.replace の呼び出しを置き換えて順序を確認します。
これらは `os.fsync(...)` のように os モジュール経由で呼んでください（`from os import fsync` は不可）。
"""
from __future__ import annotations

import os  # noqa: F401
import stat  # noqa: F401  演習1 でパーミッションを扱うのに使えます
import struct
import uuid  # noqa: F401  演習1 で一時ファイルの名前を作るのに使えます
import zlib  # noqa: F401  演習4 で zlib.crc32 を使います
from typing import BinaryIO, NamedTuple


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 原子的なファイルの置き換え
# ---------------------------------------------------------------------------

def atomic_write(path: str | os.PathLike, data: bytes) -> None:
    """path の内容を data に「原子的に」置き換える。

    途中で電源が落ちたりプロセスが殺されたりしても、path は「古い内容」か「新しい内容」の
    どちらか一方であり、空や書きかけの内容には決してならないようにする。手順:

      1. path と **同じディレクトリ** に、他と重ならない名前の一時ファイルを作る
         （os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666) を使うと、
         パーミッションには普通の open と同じく umask が適用される）
      2. path が既に存在すれば、そのパーミッション（stat.S_IMODE(os.stat(path).st_mode)）を
         一時ファイルに引き継ぐ（os.fchmod。os.fchmod がない環境では省略してよい）
      3. data をすべて書き込む（os.write は一部しか書かないことがあるので、書き切るまで繰り返す）
      4. os.fsync で一時ファイルの中身をディスクに届けてから閉じる
      5. os.replace(tmp, path) で名前を付け替える（同じファイルシステム内なら原子的）
      6. POSIX（os.name == "posix"）なら、ディレクトリを os.open(dir, os.O_RDONLY) で開いて
         os.fsync し、名前の変更も永続化する

    - 5 より前で失敗したら、一時ファイルを削除してから例外をそのまま送出する（元のファイルは無傷）。
    - data が bytes（bytes-like）でなければ TypeError（このときも一時ファイルを残さない）。
    - ディレクトリが存在しなければ FileNotFoundError。
    """
    raise NotImplementedError("演習1: atomic_write を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: tail（後ろから読む）
# ---------------------------------------------------------------------------

def tail(f: BinaryIO, n: int, *, block_size: int = 4096) -> list[bytes]:
    """シーク可能なバイナリファイル f の、最後の n 行を返す（`tail -n` と同じ）。

    - 行は b"\\n" で区切る。返す各行に改行は含めない（b"\\r" は区切りとして扱わず、行の一部とする）。
    - ファイルが改行で終わっていれば、それは最後の行の終わりであって、空の行が続くわけではない。
      改行で終わっていなければ、最後の不完全な行も 1 行として数える。
    - 行数が n より少なければ全行を返す。空のファイル、n == 0 なら []。
    - n < 0、block_size < 1 なら ValueError。
    - **ファイル全体を読まないこと**。末尾から block_size バイトずつ前に戻りながら読み、
      必要な行がそろったらやめる（テストは読んだバイト数を数えます）。

    >>> import io
    >>> tail(io.BytesIO(b"one\\ntwo\\nthree\\n"), 2)
    [b'two', b'three']
    >>> tail(io.BytesIO(b"a\\nb\\nc"), 1)
    [b'c']

    ヒント: f.seek(0, os.SEEK_END) と f.tell() でファイルの大きさが分かる。改行の数を数えながら
    後ろのブロックから読んでいき、「末尾の改行を含めて n+1 個」見つかれば最後の n 行は確実にそろう。
    """
    raise NotImplementedError("演習2: tail を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: 大きなファイルを一定のメモリで数える
# ---------------------------------------------------------------------------

class Counts(NamedTuple):
    lines: int  # b"\n" の数
    words: int  # ASCII の空白（b" \t\n\r\x0b\x0c"）で区切られた、空でない並びの数
    bytes: int  # バイト数


def count_file(path: str | os.PathLike, *, chunk_size: int = 64 * 1024) -> Counts:
    """ファイルの行数・単語数・バイト数を数える（`wc` コマンドと同じ定義）。

    - ファイル全体を一度に読まず、chunk_size バイトずつ読んで処理すること。
      1 行が巨大なファイルもあるので、行単位で読むのも不可（テストはメモリのピークを測ります）。
    - 単語がチャンクの境界をまたぐときに、2 語と数えないこと。
    - chunk_size < 1 なら ValueError。

    答え合わせ: ファイル全体を data とすると、
    Counts(data.count(b"\\n"), len(data.split()), len(data)) と一致すること。

    ヒント: 「直前のチャンクが単語の途中で終わったか」を覚えておき、次のチャンクが空白以外で
    始まるなら、そのチャンクの最初の単語は前の単語の続きである。
    """
    raise NotImplementedError("演習3: count_file を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★★）: 長さ＋CRC32 で区切ったレコードログと、途中で切れた末尾の回復
# ---------------------------------------------------------------------------
#
# ログファイルは、次の形式のレコードを先頭から隙間なく並べたもの:
#
#   +----------------------+----------------------+---------------------+
#   | 長さ（4 バイト）       | CRC32（4 バイト）      | ペイロード（長さ分）    |
#   +----------------------+----------------------+---------------------+
#   長さ・CRC32 はビッグエンディアンの 32 ビット符号なし整数（HEADER = struct.Struct(">II")）
#   CRC32 はペイロードに対する zlib.crc32(payload)
#
# 書き込みの途中でクラッシュすると、ファイルの末尾に「途中で切れたレコード」が残る。
# 開き直したときにそれを検出して切り詰めるのが「回復（recovery）」。

HEADER = struct.Struct(">II")
MAX_RECORD_SIZE = 16 * 1024 * 1024  # これより長い「長さ」は壊れているとみなす


def encode_record(payload: bytes) -> bytes:
    """payload を 1 つのレコード（ヘッダ＋ペイロード）のバイト列にする。

    payload が bytes-like でなければ TypeError、MAX_RECORD_SIZE より長ければ ValueError。

    >>> encode_record(b"hi").hex(" ")
    '00 00 00 02 d8 93 2a ac 68 69'
    """
    raise NotImplementedError("演習4: encode_record を実装してください")


def decode_records(data: bytes) -> tuple[list[bytes], int]:
    """data を先頭からレコードとして読み、(正しいレコードのペイロードのリスト, 正しい部分の終わりの位置) を返す。

    次のいずれかに当たったら、そこで読むのをやめる（それ以降は信用しない）:
      - 残りがヘッダ（8 バイト）より短い
      - 長さが MAX_RECORD_SIZE を超える
      - ペイロードが途中で切れている
      - CRC32 が一致しない

    >>> decode_records(encode_record(b"a") + encode_record(b"bc") + b"\\x00\\x00")
    ([b'a', b'bc'], 19)
    """
    raise NotImplementedError("演習4: decode_records を実装してください")


class RecordLog:
    """追記専用のレコードログ。

    RecordLog(path, sync=True):
        ファイルを開く（なければ作る）。先頭から decode_records で読み、正しい部分より後ろに
        残っているバイト（途中で切れたレコードなど）があれば、ファイルをそこで切り詰めて
        os.fsync する。切り詰めたバイト数を属性 truncated_bytes に入れる（なければ 0）。

    ヒント: os.open(path, os.O_RDWR | os.O_CREAT, 0o666) で開き、os.fdopen(fd, "r+b") で
    ファイルオブジェクトにすると、read・write・seek・truncate が使える。
    """

    def __init__(self, path: str | os.PathLike, *, sync: bool = True) -> None:
        raise NotImplementedError("演習4: RecordLog.__init__ を実装してください")

    def append(self, payload: bytes) -> int:
        """レコードをファイルの末尾に追記し、そのレコードの先頭の位置（バイトオフセット）を返す。

        ヘッダとペイロードは 1 回の write でまとめて書き、flush する。sync=True なら
        さらに os.fsync してから戻る（ここまでして初めて「書けた」と言える）。
        """
        raise NotImplementedError("演習4: RecordLog.append を実装してください")

    def records(self) -> list[bytes]:
        """ファイルの先頭から、すべてのレコードのペイロードを順に返す。"""
        raise NotImplementedError("演習4: RecordLog.records を実装してください")

    def close(self) -> None:
        raise NotImplementedError("演習4: RecordLog.close を実装してください")

    def __enter__(self) -> "RecordLog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
