"""11.4 Webアプリケーションセキュリティ — 解答例（csrf_tokens）

演習の仕様は exercises/csrf_tokens.py の docstring を参照してください。
"""
from __future__ import annotations

import base64
import hmac
import secrets
import time
from hashlib import sha256

TOKEN_BYTES = 16


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _sign(secret_key: bytes, session_id: str, issued_at: int, nonce: str) -> str:
    msg = f"{session_id}:{issued_at}:{nonce}".encode("utf-8")
    return _b64url(hmac.new(secret_key, msg, sha256).digest())


def generate_token(secret_key: bytes, session_id: str, *, now: int | None = None) -> str:
    """署名付き CSRF トークン "issued_at.nonce.signature" を作る。"""
    if not isinstance(secret_key, (bytes, bytearray)) or len(secret_key) < 16:
        raise ValueError("secret_key は 16 バイト以上にしてください")
    issued_at = int(time.time()) if now is None else int(now)
    nonce = _b64url(secrets.token_bytes(TOKEN_BYTES))
    signature = _sign(secret_key, session_id, issued_at, nonce)
    return f"{issued_at}.{nonce}.{signature}"


def validate_token(
    secret_key: bytes,
    session_id: str,
    token: str,
    *,
    max_age_seconds: int = 3600,
    now: int | None = None,
) -> bool:
    """token が session_id 宛てに発行され、改ざんされておらず、期限内なら True。"""
    if not isinstance(token, str) or token.count(".") != 2:
        return False
    issued_str, nonce, signature = token.split(".")
    try:
        issued_at = int(issued_str)
    except ValueError:
        return False
    if issued_str != str(issued_at):  # "007" や " 7" などの表記ゆれを弾く
        return False
    # 署名を張り直して定数時間で比較する（セッションに紐づくので、他人のトークンは使えない）
    expected = _sign(secret_key, session_id, issued_at, nonce)
    if not hmac.compare_digest(expected, signature):
        return False
    current = int(time.time()) if now is None else int(now)
    if current < issued_at:
        return False  # 未来に発行されたトークン（時計の巻き戻しや細工）
    return current - issued_at <= max_age_seconds


def constant_time_compare(a: str, b: str) -> bool:
    """double-submit cookie 方式で、Cookie の値とフォームの値を定数時間で比較する。"""
    try:
        return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
    except (AttributeError, UnicodeError):
        return False
