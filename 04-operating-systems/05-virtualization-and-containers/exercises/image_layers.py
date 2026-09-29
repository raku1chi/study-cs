"""4.5 仮想化とコンテナ — 演習4・5: コンテンツアドレスのレイヤとビルドキャッシュ

コンテナイメージは、ファイルシステムの差分である「レイヤ」を積み重ねたもので、各レイヤは中身の
ハッシュ（ダイジェスト）で識別されます。同じダイジェストのレイヤは、複数のイメージで共有され、
一度ダウンロードすれば再利用できます。また、ビルドツールは各命令について「キャッシュのキー」を
計算し、キーが同じなら前回の結果を再利用します。この 2 つの仕組みを小さなモデルで実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.5
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_image_layers

簡略化している点: 実際の BuildKit のキャッシュキーや OCI のレイヤのダイジェストは、ここでの
定義とは計算方法が違います（例えば、レイヤのダイジェストは tar アーカイブのハッシュ）。
「親のキー・命令・取り込むファイルの中身がすべて同じなら再利用する」という考え方は同じです。
"""
from __future__ import annotations

import hashlib
from typing import Mapping, NamedTuple, Sequence


def sha256_hex(data: bytes) -> str:
    """data の SHA-256 を 16 進文字列で返す（実装済み）。"""
    return hashlib.sha256(data).hexdigest()


class Step(NamedTuple):
    instruction: str  # 例: "RUN pip install -r requirements.txt"
    sources: tuple[str, ...] = ()  # COPY/ADD がビルドコンテキストから取り込むパス（それ以外は空）


class Layer(NamedTuple):
    digest: str  # 中身のハッシュ。同じダイジェストなら同じ中身
    size: int  # バイト数


class Usage(NamedTuple):
    logical: int  # 各イメージの大きさの合計（イメージ間の共有を考えない場合）
    physical: int  # 異なるレイヤの大きさの合計（実際に必要な保存容量）
    shared: int  # 2 つ以上のイメージが使うレイヤの大きさの合計（各レイヤ 1 回）
    unique: dict[str, int]  # イメージ名 -> そのイメージだけが使うレイヤの大きさの合計


# ---------------------------------------------------------------------------
# 演習4（★★☆）: ビルドキャッシュのキー
# ---------------------------------------------------------------------------
# ビルドコンテキスト context は {パス: 中身} の辞書（パスの区切りは "/"）。

def select_files(context: Mapping[str, bytes], source: str) -> list[str]:
    """取り込み元の指定 source に当てはまるパスを、名前順のリストで返す。

    - "." または "./" : コンテキストのすべてのファイル
    - context にちょうど同じパスがある : そのファイルだけ
    - それ以外 : source をディレクトリとみなし、"source/" で始まるすべてのファイル
      （末尾の "/" はあってもなくてもよい）
    - 1 つも当てはまらなければ FileNotFoundError

    >>> select_files({"a.txt": b"", "src/x.py": b"", "src/y.py": b""}, "src")
    ['src/x.py', 'src/y.py']
    """
    raise NotImplementedError("演習4: select_files を実装してください")


def content_digest(context: Mapping[str, bytes], sources: Sequence[str]) -> str:
    """sources のすべてに当てはまるファイル（重複は 1 回）の、パスと中身を要約したハッシュを返す。

    定義: 当てはまるパスを名前順に並べ、各パスについて
        パス（UTF-8）+ b"\\0" + sha256_hex(中身)（ASCII）+ b"\\n"
    をつなげたバイト列の SHA-256 の 16 進文字列。
    ファイルの中身・名前が 1 つでも変われば値が変わり、辞書の順序には依存しない。
    """
    raise NotImplementedError("演習4: content_digest を実装してください")


def cache_keys(base: str, steps: Sequence[Step], context: Mapping[str, bytes]) -> list[str]:
    """各ステップのキャッシュキー（SHA-256 の 16 進文字列）のリストを返す。

    定義（テストはこの定義で答え合わせをします）:
        parent_0 = sha256_hex(base の UTF-8)
        material = parent + "\\n" + step.instruction
        step.sources が空でなければ material += "\\n" + content_digest(context, step.sources)
        key = sha256_hex(material の UTF-8)、そして次のステップの parent = key

    つまり、あるステップのキーは「ベース・それまでの全命令・取り込んだファイルの中身」で決まる。
    RUN のキーはコマンドの文字列だけで決まり、外の世界（パッケージのリポジトリなど）の変化は反映されない。
    """
    raise NotImplementedError("演習4: cache_keys を実装してください")


def build(base: str, steps: Sequence[Step], context: Mapping[str, bytes], cache: set[str]) -> list[bool]:
    """ビルドをシミュレーションする。各ステップについて、作り直しが必要（キーが cache にない）なら True。

    計算したすべてのキーを cache に追加する（次回のビルドで再利用できるように）。
    """
    raise NotImplementedError("演習4: build を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: レイヤの共有と保存容量
# ---------------------------------------------------------------------------

def storage_usage(images: Mapping[str, Sequence[Layer]]) -> Usage:
    """イメージの集まり {イメージ名: レイヤのリスト} の保存容量を集計する。

    - 1 つのイメージの中に同じダイジェストが 2 回現れても、そのイメージでは 1 回と数える。
    - 同じダイジェストなのに大きさが違うレイヤがあれば ValueError（中身が同じはずなので矛盾）。
      大きさが負でも ValueError。

    >>> base, app = Layer("sha256:base", 100), Layer("sha256:app", 5)
    >>> storage_usage({"a": [base, app], "b": [base]})
    Usage(logical=205, physical=105, shared=100, unique={'a': 5, 'b': 0})
    """
    raise NotImplementedError("演習5: storage_usage を実装してください")


def pull_bytes(layers: Sequence[Layer], present: set[str]) -> int:
    """イメージ（レイヤのリスト）を取得するときに、新たにダウンロードが必要なバイト数を返す。

    present は、そのノードに既にあるレイヤのダイジェストの集合。同じダイジェストは 1 回だけ数える。
    同じダイジェストで大きさが違えば ValueError。
    """
    raise NotImplementedError("演習5: pull_bytes を実装してください")
