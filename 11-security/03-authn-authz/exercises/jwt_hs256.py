"""11.3 認証と認可 — 演習（jwt_hs256）

HS256（HMAC-SHA256）で署名された JWT（JSON Web Token）の発行と、**厳格な** 検証を実装します。
JWT の脆弱性の多くは暗号の弱さではなく「検証の手抜き」から生まれます。
alg=none の受理、アルゴリズムの取り違え、aud・iss・exp を見ない、といった
実際に起きてきた失敗を、テストの攻撃ケースで 1 つずつ塞いでいきます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.3
    python3 tools/check.py -v 11.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_jwt_hs256

JWT（JWS Compact Serialization）の構造:
    base64url(ヘッダーの JSON) "." base64url(ペイロードの JSON) "." base64url(署名)
    署名 = HMAC-SHA256(鍵, ASCII("ヘッダー部.ペイロード部"))
    base64url は URL で安全な Base64（+ の代わりに -、/ の代わりに _）で、末尾の '=' は付けない。

使ってよいもの: base64, json, hmac（hmac.new と hmac.compare_digest）, hashlib, re, time。
本番では自作せず、実績のあるライブラリを「アルゴリズムを固定し、aud・iss・exp を検証する」
設定で使ってください。
"""
from __future__ import annotations

import base64  # noqa: F401
import binascii  # noqa: F401
import hashlib  # noqa: F401
import hmac  # noqa: F401
import json  # noqa: F401
import re  # noqa: F401
import time  # noqa: F401
from typing import Any, Iterable

MIN_KEY_BYTES = 32  # RFC 7518: HS256 の鍵はハッシュの出力長（256 ビット）以上
SUPPORTED_ALGORITHMS = frozenset({"HS256"})


class JWTError(Exception):
    """JWT の検証に失敗したことを表す例外の基底クラス。"""


class DecodeError(JWTError):
    """形式が不正（区切り・base64url・JSON・クレームの型など）。"""


class InvalidAlgorithmError(JWTError):
    """許可されていない（または none の）アルゴリズム。"""


class InvalidSignatureError(JWTError):
    """署名が一致しない。"""


class ExpiredTokenError(JWTError):
    """有効期限（exp）切れ。"""


class NotYetValidError(JWTError):
    """まだ有効になっていない（nbf）。"""


class InvalidAudienceError(JWTError):
    """受け手（aud）が違う。"""


class InvalidIssuerError(JWTError):
    """発行者（iss）が違う。"""


class MissingClaimError(JWTError):
    """必須のクレームがない。"""


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: base64url（パディングなし）
# ---------------------------------------------------------------------------

def b64url_encode(data: bytes) -> str:
    """base64url でエンコードし、末尾の '=' を取り除いた文字列を返す。

    >>> b64url_encode(b"\\xff\\xfe")
    '__4'
    """
    raise NotImplementedError("演習1: b64url_encode を実装してください")


def b64url_decode(text: str) -> bytes:
    """パディングなしの base64url を **厳格に** デコードする。不正なら DecodeError。

    不正とみなすもの:
    - str でない
    - 使える文字（A-Z a-z 0-9 - _）以外を含む（'=' '+' '/' 空白 改行 など）
    - 長さを 4 で割った余りが 1（どんな入力からも生じない長さ）
    - 正規形でない: デコードしたバイト列を b64url_encode し直すと元の文字列に戻らない
      （末尾の使われないビットが 0 でない。例: "__4" は正規形、"__5" は同じバイト列を表す非正規形）

    なぜ非正規形を拒否するのか: 同じ署名を表す別の文字列が作れると、トークン文字列を
    キーにした失効リストなどを、見た目の違うトークンですり抜けられるから。
    """
    raise NotImplementedError("演習1: b64url_decode を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 署名付きトークンの発行
# ---------------------------------------------------------------------------

def encode(payload: dict[str, Any], key: bytes, *, headers: dict[str, Any] | None = None) -> str:
    """payload に HS256 で署名した JWT を返す。

    - key が bytes でない、または MIN_KEY_BYTES バイト未満なら ValueError。
    - payload が dict でなければ TypeError。
    - ヘッダーは {"alg": "HS256", "typ": "JWT"} の順で作り、headers の項目を後ろに追加する。
      headers に "alg" か "typ" が含まれていたら ValueError（上書きさせない）。
    - JSON は json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8") で作る
      （テストはこのバイト列に対する署名を期待します）。
    """
    raise NotImplementedError("演習2: encode を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 厳格な検証
# ---------------------------------------------------------------------------

def decode(
    token: str,
    key: bytes,
    *,
    algorithms: Iterable[str] = ("HS256",),
    audience: str | None = None,
    issuer: str | None = None,
    now: float | None = None,
    leeway: float = 0,
    require: Iterable[str] = ("exp",),
) -> dict[str, Any]:
    """JWT を検証し、ペイロード（dict）を返す。1 つでも問題があれば例外を送出する。

    次の順に検査すること（順序も大切: **署名を確かめる前にペイロードを信用しない**）。

    0. key が bytes でない、または MIN_KEY_BYTES バイト未満 → ValueError
    1. token が str で、ドットでちょうど 3 つに分かれる → そうでなければ DecodeError
    2. ヘッダー: b64url_decode → UTF-8 → JSON のオブジェクト（dict）でなければ DecodeError
    3. アルゴリズム: ヘッダーの "alg" が
         - str であり、
         - 大文字小文字を問わず "none" ではなく（許可リストに none があっても拒否）、
         - algorithms（許可リスト）と SUPPORTED_ALGORITHMS の **両方** に含まれる
       でなければ InvalidAlgorithmError
       （トークン自身が名乗るアルゴリズムを信じない。検証側が決めた許可リストで判断する）
    4. ヘッダーに "crit" があれば DecodeError（理解できない必須拡張は拒否するのが規則）
    5. 署名: b64url_decode（不正なら DecodeError）し、
       HMAC-SHA256(key, "ヘッダー部.ペイロード部" の ASCII バイト列) と hmac.compare_digest で比較。
       一致しなければ InvalidSignatureError
    6. ペイロード: ヘッダーと同様に JSON オブジェクトでなければ DecodeError
    7. require の各クレームがなければ MissingClaimError
    8. 時刻（now が None なら time.time()）:
         - "exp"・"nbf"・"iat" が存在するなら、int か float（bool は不可）でなければ DecodeError
         - now >= exp + leeway → ExpiredTokenError（exp ちょうどは期限切れ）
         - now <  nbf - leeway → NotYetValidError
    9. issuer が指定されていれば: "iss" がなければ MissingClaimError、違えば InvalidIssuerError
    10. audience が指定されていれば: "aud" がなければ MissingClaimError。
        "aud" は文字列か文字列のリストで、audience を含まなければ InvalidAudienceError
        （数値など、文字列でもリストでもない aud も InvalidAudienceError）
        audience が **指定されていない** のに "aud" があれば InvalidAudienceError
        （別サービス宛てのトークンの流用を防ぐため、安全側に倒す）
    """
    raise NotImplementedError("演習3: decode を実装してください")
