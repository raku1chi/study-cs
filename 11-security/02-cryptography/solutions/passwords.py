"""11.2 暗号技術の基礎 — 解答例（passwords）

演習の仕様は exercises/passwords.py の docstring を参照してください。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass

SALT_SIZE = 16
DKLEN = 32
MAX_PASSWORD_LENGTH = 1024


@dataclass(frozen=True)
class ScryptParams:
    log2_n: int = 17
    r: int = 8
    p: int = 1


@dataclass(frozen=True)
class Pbkdf2Params:
    iterations: int = 600_000


Params = ScryptParams | Pbkdf2Params  # Python 3.10 以降は X | Y で型の和が書ける

DEFAULT_SCRYPT = ScryptParams()
DEFAULT_PBKDF2 = Pbkdf2Params()

_SCRYPT_RE = re.compile(r"\$scrypt\$ln=(\d+),r=(\d+),p=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)")
_PBKDF2_RE = re.compile(r"\$pbkdf2-sha256\$i=(\d+)\$([A-Za-z0-9+/]+)\$([A-Za-z0-9+/]+)")


# ---------------------------------------------------------------------------
# 補助: エンコードとパラメータの検証
# ---------------------------------------------------------------------------

def _b64encode(data: bytes) -> str:
    # PHC 文字列形式に倣い、標準の Base64 から末尾の '=' を取り除く
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _b64decode(text: str) -> bytes:
    try:
        return base64.b64decode(text + "=" * (-len(text) % 4), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Base64 として不正です: {text!r}") from exc


def _validate_params(params: Params) -> None:
    if isinstance(params, ScryptParams):
        if not (1 <= params.log2_n <= 30 and params.r >= 1 and params.p >= 1):
            raise ValueError(f"scrypt のパラメータが不正です: {params}")
    elif isinstance(params, Pbkdf2Params):
        if params.iterations < 1:
            raise ValueError(f"PBKDF2 の反復回数が不正です: {params}")
    else:
        raise TypeError(f"未知のパラメータ型です: {type(params).__name__}")


def _prepare(password: str, pepper: bytes | None) -> bytes:
    # 見た目が同じ文字列（全角・半角、合成・分解）を同じパスワードとして扱う
    data = unicodedata.normalize("NFKC", password).encode("utf-8")
    if pepper is not None:
        # ペッパー: DB とは別の場所（KMS・HSM・環境変数など）に置く秘密鍵で HMAC を取る
        data = hmac.new(pepper, data, hashlib.sha256).digest()
    return data


def _derive(data: bytes, salt: bytes, params: Params) -> bytes:
    if isinstance(params, ScryptParams):
        if not scrypt_available():
            raise RuntimeError("この環境の hashlib は scrypt に対応していません")
        n = 1 << params.log2_n
        # OpenSSL の既定の上限（32 MiB）を超えるパラメータでも動くように、必要量＋余裕を渡す
        maxmem = 128 * params.r * (n + params.p + 2) + (1 << 20)
        return hashlib.scrypt(data, salt=salt, n=n, r=params.r, p=params.p, maxmem=maxmem, dklen=DKLEN)
    return hashlib.pbkdf2_hmac("sha256", data, salt, params.iterations, dklen=DKLEN)


def _encode(params: Params, salt: bytes, digest: bytes) -> str:
    if isinstance(params, ScryptParams):
        head = f"$scrypt$ln={params.log2_n},r={params.r},p={params.p}"
    else:
        head = f"$pbkdf2-sha256$i={params.iterations}"
    return f"{head}${_b64encode(salt)}${_b64encode(digest)}"


# ---------------------------------------------------------------------------
# 演習1: 環境の確認と既定のパラメータ
# ---------------------------------------------------------------------------

def scrypt_available() -> bool:
    if not hasattr(hashlib, "scrypt"):
        return False
    try:
        hashlib.scrypt(b"probe", salt=b"s" * 16, n=2, r=1, p=1, dklen=16)
    except (ValueError, OSError):
        return False
    return True


def default_params() -> Params:
    return DEFAULT_SCRYPT if scrypt_available() else DEFAULT_PBKDF2


# ---------------------------------------------------------------------------
# 演習2: ハッシュ化とエンコード
# ---------------------------------------------------------------------------

def hash_password(
    password: str,
    params: Params | None = None,
    *,
    salt: bytes | None = None,
    pepper: bytes | None = None,
) -> str:
    if not isinstance(password, str):
        raise TypeError("password は str で渡してください")
    if not password:
        raise ValueError("空のパスワードはハッシュ化しません")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError("パスワードが長すぎます")
    params = default_params() if params is None else params
    _validate_params(params)
    if salt is None:
        salt = secrets.token_bytes(SALT_SIZE)  # ユーザーごとに異なるランダムなソルト
    elif len(salt) < 8:
        raise ValueError("ソルトは 8 バイト以上にしてください")
    return _encode(params, salt, _derive(_prepare(password, pepper), salt, params))


def parse_hash(encoded: str) -> tuple[Params, bytes, bytes]:
    m = _SCRYPT_RE.fullmatch(encoded)
    if m:
        params: Params = ScryptParams(int(m[1]), int(m[2]), int(m[3]))
        salt, digest = _b64decode(m[4]), _b64decode(m[5])
    else:
        m = _PBKDF2_RE.fullmatch(encoded)
        if not m:
            raise ValueError("未知または不正なハッシュ形式です")
        params = Pbkdf2Params(int(m[1]))
        salt, digest = _b64decode(m[2]), _b64decode(m[3])
    _validate_params(params)
    if len(digest) != DKLEN:
        raise ValueError("ハッシュ値の長さが不正です")
    return params, salt, digest


# ---------------------------------------------------------------------------
# 演習3: 検証と再ハッシュの判定
# ---------------------------------------------------------------------------

def verify_password(password: str, encoded: str, *, pepper: bytes | None = None) -> bool:
    if not isinstance(password, str):
        raise TypeError("password は str で渡してください")
    params, salt, expected = parse_hash(encoded)  # 形式が不正なら ValueError（サーバー側の不具合）
    if not password or len(password) > MAX_PASSWORD_LENGTH:
        # 高コストな計算をする前に弾く（巨大な入力による DoS を防ぐ）
        return False
    actual = _derive(_prepare(password, pepper), salt, params)
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str, params: Params | None = None) -> bool:
    current, _, _ = parse_hash(encoded)
    wanted = default_params() if params is None else params
    # 型（アルゴリズム）もパラメータも完全に一致しなければ作り直す
    return current != wanted
