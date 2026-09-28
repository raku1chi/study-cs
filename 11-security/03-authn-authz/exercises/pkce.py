"""11.3 認証と認可 — 演習（pkce）

OAuth 2.0 の認可コードフローで、認可コードの横取り（interception）を防ぐ
PKCE（Proof Key for Code Exchange, RFC 7636）のクライアント側とサーバー側の部品を作ります。

    1. クライアントが秘密の code_verifier（ランダムな文字列）を作る
    2. 認可リクエストには code_challenge = BASE64URL(SHA256(code_verifier)) だけを付けて送る
    3. トークンリクエストで code_verifier そのものを送る
    4. 認可サーバーは SHA256 を計算し直して、2 の値と一致するか確かめる
    → 途中で認可コードを盗んだ攻撃者は code_verifier を知らないので、トークンに交換できない

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.3
    python3 tools/check.py -v 11.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_pkce
"""
from __future__ import annotations

import base64  # noqa: F401
import hashlib  # noqa: F401
import hmac  # noqa: F401
import re  # noqa: F401
import secrets
from typing import Callable


def is_valid_verifier(verifier: str) -> bool:
    """RFC 7636 の code_verifier の形式なら True。

    条件: str であり、unreserved 文字（A-Z a-z 0-9 と - . _ ~）だけからなる 43〜128 文字。
    """
    raise NotImplementedError("演習（PKCE）: is_valid_verifier を実装してください")


def generate_code_verifier(nbytes: int = 32, *, token_bytes: Callable[[int], bytes] = secrets.token_bytes) -> str:
    """token_bytes(nbytes) で得た乱数を base64url（パディングなし）にした code_verifier を返す。

    - nbytes が 32〜96 でなければ ValueError（base64url にすると 43〜128 文字になる範囲）。
    - token_bytes はテストで差し替えられるようにした引数。既定は OS の CSPRNG（secrets）。
      random モジュールは予測可能なので、秘密の値の生成に使ってはいけない。
    """
    raise NotImplementedError("演習（PKCE）: generate_code_verifier を実装してください")


def code_challenge(verifier: str, method: str = "S256") -> str:
    """code_verifier から code_challenge を計算する。

    - verifier が is_valid_verifier を満たさなければ ValueError。
    - method == "S256": BASE64URL(SHA256(ASCII(verifier)))（パディングなし）
    - method == "plain": verifier そのもの
    - それ以外は ValueError。

    >>> code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
    'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM'
    """
    raise NotImplementedError("演習（PKCE）: code_challenge を実装してください")


def verify_code_verifier(verifier: str, challenge: str, method: str = "S256", *, allow_plain: bool = False) -> bool:
    """認可サーバー側の検証。code_challenge(verifier, method) が challenge と一致すれば True。

    - method が "plain" で allow_plain が False なら False（plain は既定で拒否する）。
    - method が "S256"・"plain" 以外、verifier の形式が不正、challenge が str でない場合は
      例外ではなく False。
    - 比較は hmac.compare_digest（定数時間）で行う。
    """
    raise NotImplementedError("演習（PKCE）: verify_code_verifier を実装してください")
