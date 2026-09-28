"""11.4 Webアプリケーションセキュリティ — 解答例（safe_files）

演習の仕様は exercises/safe_files.py の docstring を参照してください。
"""
from __future__ import annotations

import os
from pathlib import Path


class UnsafePathError(ValueError):
    """要求されたパスがベースディレクトリの外を指している（または不正）ことを表す。"""


def safe_join(base_dir: str | os.PathLike[str], user_path: str) -> Path:
    """base_dir を基準に user_path を解決し、base_dir 内に収まる実体パスを返す。

    危険なら UnsafePathError を送出する。
    """
    if not isinstance(user_path, str):
        raise UnsafePathError("パスは文字列で指定してください")
    if "\x00" in user_path:
        # NUL バイトは C の文字列を途中で終わらせ、拡張子チェックなどをすり抜ける古典的な手口
        raise UnsafePathError("パスに NUL バイトを含めることはできません")
    # base 自身はシンボリックリンクを解決した正規の絶対パスにしておく
    base = Path(base_dir).resolve(strict=False)
    candidate = Path(user_path)
    if candidate.is_absolute() or candidate.drive or candidate.root:
        # "/etc/passwd" や "C:\\..." のような絶対パスは、join しても base を無視してしまう
        raise UnsafePathError(f"絶対パスは許可されません: {user_path!r}")
    # resolve() が ".." とシンボリックリンクの両方をたどって実体の絶対パスにする。
    # これでリンクを経由した脱出（symlink escape）も含めて 1 か所で判定できる
    resolved = (base / candidate).resolve(strict=False)
    if resolved != base and base not in resolved.parents:
        raise UnsafePathError(f"ベースディレクトリの外を指しています: {user_path!r}")
    return resolved


def serve_file(base_dir: str | os.PathLike[str], user_path: str) -> bytes:
    """安全なら base_dir 内のファイルの内容を返す。

    - パスが安全でなければ UnsafePathError。
    - 対象が存在しない、または通常ファイルでない（ディレクトリなど）なら FileNotFoundError。
    """
    resolved = safe_join(base_dir, user_path)
    if not resolved.is_file():
        raise FileNotFoundError(f"ファイルがありません: {user_path!r}")
    return resolved.read_bytes()
