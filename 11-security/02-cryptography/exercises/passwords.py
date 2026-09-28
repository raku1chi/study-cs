"""11.2 暗号技術の基礎 — 演習（passwords）

パスワードを安全に保存するための小さなライブラリを作ります。
  - ソルト付きの「わざと遅い」鍵導出関数（scrypt、使えなければ PBKDF2-HMAC-SHA256）でハッシュ化する
  - アルゴリズム・パラメータ・ソルトを 1 つの文字列にまとめて保存する（あとから強化できるように）
  - 定数時間で検証し、パラメータが古くなったハッシュを検出して作り直す（needs_rehash）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.2
    python3 tools/check.py -v 11.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_passwords

保存形式（PHC 文字列形式に倣った、この教材の形式）:
    scrypt:  $scrypt$ln=17,r=8,p=1$<ソルト>$<ハッシュ値>       （ln は log2(N)）
    PBKDF2:  $pbkdf2-sha256$i=600000$<ソルト>$<ハッシュ値>
    <ソルト>・<ハッシュ値> は標準の Base64 から末尾の '=' を取り除いたもの。
    ソルトは 16 バイト、ハッシュ値（導出する鍵の長さ）は 32 バイト。

使ってよいもの: hashlib.scrypt, hashlib.pbkdf2_hmac, hmac.compare_digest, hmac.new,
    secrets.token_bytes, base64, unicodedata。
    （目的は「正しい部品を正しく組み合わせる」ことです。KDF そのものは自作しません）

注意（scrypt と maxmem）:
    hashlib.scrypt は OpenSSL の既定のメモリ上限（32 MiB）を超えるパラメータで ValueError に
    なります。N=2^17, r=8 は約 128 MiB 必要なので、maxmem 引数に
        128 * r * (N + p + 2) + 余裕（例: 1 MiB）
    を渡してください。
"""
from __future__ import annotations

import base64  # noqa: F401
import binascii  # noqa: F401
import hashlib  # noqa: F401
import hmac  # noqa: F401
import re  # noqa: F401
import secrets  # noqa: F401
import unicodedata  # noqa: F401
from dataclasses import dataclass

SALT_SIZE = 16
DKLEN = 32
MAX_PASSWORD_LENGTH = 1024


@dataclass(frozen=True)
class ScryptParams:
    """scrypt のパラメータ。N = 2 ** log2_n。既定値は 2026 年時点の OWASP の最小推奨値。"""

    log2_n: int = 17
    r: int = 8
    p: int = 1


@dataclass(frozen=True)
class Pbkdf2Params:
    """PBKDF2-HMAC-SHA256 のパラメータ。既定値は 2026 年時点の OWASP の推奨値。"""

    iterations: int = 600_000


Params = ScryptParams | Pbkdf2Params

DEFAULT_SCRYPT = ScryptParams()
DEFAULT_PBKDF2 = Pbkdf2Params()


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 環境の確認と既定のパラメータ
# ---------------------------------------------------------------------------

def scrypt_available() -> bool:
    """この環境の hashlib で scrypt が使えれば True。

    hashlib.scrypt は OpenSSL 1.1 以降でビルドされた Python にしかない。属性があっても
    呼び出しに失敗する環境に備えて、小さなパラメータ（n=2, r=1, p=1）で実際に 1 回呼び、
    ValueError / OSError が出たら False を返す。
    """
    raise NotImplementedError("演習1: scrypt_available を実装してください")


def default_params() -> Params:
    """scrypt が使えれば DEFAULT_SCRYPT、使えなければ DEFAULT_PBKDF2 を返す。

    テストは scrypt_available をモック（差し替え）するので、この関数の中で
    scrypt_available() を呼んで判定すること。
    """
    raise NotImplementedError("演習1: default_params を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ハッシュ化とエンコード
# ---------------------------------------------------------------------------

def hash_password(
    password: str,
    params: Params | None = None,
    *,
    salt: bytes | None = None,
    pepper: bytes | None = None,
) -> str:
    """パスワードをハッシュ化し、保存形式の文字列を返す。

    手順:
      1. 検査: password が str でなければ TypeError。空、または MAX_PASSWORD_LENGTH 文字を
         超えるなら ValueError（巨大な入力は高コストな計算を狙った DoS に使われる）。
      2. params が None なら default_params()。パラメータが不正（log2_n が 1〜30 の外、
         r < 1、p < 1、iterations < 1）なら ValueError。
      3. salt が None なら secrets.token_bytes(SALT_SIZE) で作る。指定されたソルトが
         8 バイト未満なら ValueError（テストでは再現性のためにソルトを渡します）。
      4. パスワードを Unicode 正規化（NFKC）して UTF-8 のバイト列にする。
      5. pepper が指定されたら、そのバイト列を hmac.new(pepper, data, "sha256").digest() に置き換える。
      6. scrypt なら hashlib.scrypt(data, salt=salt, n=2**log2_n, r=r, p=p, maxmem=…, dklen=32)、
         PBKDF2 なら hashlib.pbkdf2_hmac("sha256", data, salt, iterations, dklen=32)。
      7. モジュール docstring の形式で文字列にする。

    >>> hash_password("pw", Pbkdf2Params(1000), salt=b"s" * 16)  # doctest: +ELLIPSIS
    '$pbkdf2-sha256$i=1000$c3Nzc3Nzc3Nzc3Nzc3Nzcw$...'
    """
    raise NotImplementedError("演習2: hash_password を実装してください")


def parse_hash(encoded: str) -> tuple[Params, bytes, bytes]:
    """保存形式の文字列を (パラメータ, ソルト, ハッシュ値) に分解する。

    次の場合は ValueError:
    - 形式がどちらにも **完全一致** しない（前後の余計な文字、未知のアルゴリズム、数値でないパラメータ）
    - Base64 として不正
    - パラメータが範囲外（hash_password と同じ基準）
    - ハッシュ値が DKLEN（32）バイトでない

    ヒント: re.fullmatch と、base64.b64decode(text + "=" * (-len(text) % 4), validate=True)。
    """
    raise NotImplementedError("演習2: parse_hash を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 検証と再ハッシュの判定
# ---------------------------------------------------------------------------

def verify_password(password: str, encoded: str, *, pepper: bytes | None = None) -> bool:
    """password が encoded と一致すれば True を返す。

    - password が str でなければ TypeError。
    - encoded が不正な形式なら ValueError（parse_hash の例外をそのまま伝える。DB の破損や
      実装の不具合なので、「パスワードが違う」と同じ扱いにして隠してはいけない）。
    - password が空、または MAX_PASSWORD_LENGTH 文字を超えるなら、**計算せずに** False。
    - 保存されたパラメータとソルトで同じ計算をやり直し、hmac.compare_digest で比較する。
    - scrypt のハッシュなのにこの環境で scrypt が使えなければ RuntimeError。
    """
    raise NotImplementedError("演習3: verify_password を実装してください")


def needs_rehash(encoded: str, params: Params | None = None) -> bool:
    """保存されたハッシュを、現在の方針 params（None なら default_params()）で作り直すべきなら True。

    アルゴリズムが違う、またはパラメータが 1 つでも違えば True。形式が不正なら ValueError。
    ログインに成功した瞬間（平文のパスワードが手元にある唯一の機会）に呼び出し、
    True なら新しいパラメータでハッシュし直して保存する、という使い方をします。
    """
    raise NotImplementedError("演習3: needs_rehash を実装してください")
