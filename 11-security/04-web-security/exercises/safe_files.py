"""11.4 Webアプリケーションセキュリティ — 演習（safe_files）

ユーザーが指定したパスのファイルを配信する機能で、パストラバーサル
（../../etc/passwd のように、公開ディレクトリの外のファイルを読み出す攻撃）を防ぎます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.4
    python3 tools/check.py -v 11.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_safe_files

ヒント: pathlib.Path の resolve() は、".." とシンボリックリンクの両方をたどって
実体の絶対パスにします。ベースディレクトリも resolve() しておき、
「解決後のパスがベースの中にあるか」を 1 か所で判定するのが確実です。
文字列を自分で分解して ".." を数える方法は、記法のバリエーション（URL エンコード、
シンボリックリンク、絶対パスなど）を取りこぼしがちなので避けましょう。
"""
from __future__ import annotations

import os
from pathlib import Path


class UnsafePathError(ValueError):
    """要求されたパスがベースディレクトリの外を指している（または不正）ことを表す。"""


def safe_join(base_dir: str | os.PathLike[str], user_path: str) -> Path:
    """base_dir を基準に user_path を解決し、base_dir 内に収まる実体パス（解決済み）を返す。

    次のいずれかなら UnsafePathError を送出する:
    - user_path が文字列でない
    - NUL バイト（"\\x00"）を含む
    - 絶対パス（"/etc/passwd" や "C:\\..." など。join しても base を無視してしまう）
    - 解決後のパスが base_dir の外を指す（".." やシンボリックリンクでの脱出を含む）

    base_dir の中で ".." を使って base_dir 内に戻ってくるだけなら許してよい。

    >>> safe_join("/srv/public", "css/site.css")   # doctest: +SKIP
    PosixPath('/srv/public/css/site.css')
    """
    raise NotImplementedError("演習: safe_join を実装してください")


def serve_file(base_dir: str | os.PathLike[str], user_path: str) -> bytes:
    """安全なら base_dir 内のファイルの内容（bytes）を返す。

    - パスが安全でなければ UnsafePathError（safe_join の例外をそのまま伝える）。
    - 対象が存在しない、または通常ファイルでない（ディレクトリなど）なら FileNotFoundError。
    """
    raise NotImplementedError("演習: serve_file を実装してください")
