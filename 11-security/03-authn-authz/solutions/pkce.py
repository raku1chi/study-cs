"""11.3 認証と認可 — 解答例（pkce）

演習の仕様は exercises/pkce.py の docstring を参照してください。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from typing import Callable

_VERIFIER_RE = re.compile(r"[A-Za-z0-9\-._~]{43,128}")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def is_valid_verifier(verifier: str) -> bool:
    # RFC 7636: unreserved 文字（英数字と - . _ ~）だけからなる 43〜128 文字
    return isinstance(verifier, str) and _VERIFIER_RE.fullmatch(verifier) is not None


def generate_code_verifier(nbytes: int = 32, *, token_bytes: Callable[[int], bytes] = secrets.token_bytes) -> str:
    if not 32 <= nbytes <= 96:
        raise ValueError("nbytes は 32〜96 です（base64url で 43〜128 文字になる範囲）")
    # CSPRNG の 32 バイト（256 ビット）を base64url にすると 43 文字
    return _b64url(token_bytes(nbytes))


def code_challenge(verifier: str, method: str = "S256") -> str:
    if not is_valid_verifier(verifier):
        raise ValueError("code_verifier の形式が不正です")
    if method == "S256":
        return _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    if method == "plain":
        return verifier
    raise ValueError(f"未知の method です: {method}")


def verify_code_verifier(verifier: str, challenge: str, method: str = "S256", *, allow_plain: bool = False) -> bool:
    if method == "plain" and not allow_plain:
        # plain は認可リクエストを盗み見られると意味がない。S256 が使えるなら必ず S256
        return False
    if method not in ("S256", "plain") or not is_valid_verifier(verifier) or not isinstance(challenge, str):
        return False
    return hmac.compare_digest(code_challenge(verifier, method), challenge)
