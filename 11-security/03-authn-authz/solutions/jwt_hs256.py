"""11.3 認証と認可 — 解答例（jwt_hs256）

演習の仕様は exercises/jwt_hs256.py の docstring を参照してください。
本番では、実績のあるライブラリ（PyJWT、joserfc など）を正しい設定で使います。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import re
import time
from typing import Any, Iterable

MIN_KEY_BYTES = 32
SUPPORTED_ALGORITHMS = frozenset({"HS256"})
_B64URL_RE = re.compile(r"[A-Za-z0-9_-]*")


class JWTError(Exception):
    """JWT の検証に失敗したことを表す例外の基底クラス。"""


class DecodeError(JWTError):
    pass


class InvalidAlgorithmError(JWTError):
    pass


class InvalidSignatureError(JWTError):
    pass


class ExpiredTokenError(JWTError):
    pass


class NotYetValidError(JWTError):
    pass


class InvalidAudienceError(JWTError):
    pass


class InvalidIssuerError(JWTError):
    pass


class MissingClaimError(JWTError):
    pass


# ---------------------------------------------------------------------------
# 演習1: base64url（パディングなし）
# ---------------------------------------------------------------------------

def b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    # 許す文字を明示的に限定する（'=' や '+' '/'、空白、改行などを受け付けない）
    if not isinstance(text, str) or not _B64URL_RE.fullmatch(text) or len(text) % 4 == 1:
        raise DecodeError("base64url として不正です")
    try:
        data = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise DecodeError("base64url として不正です") from exc
    # 末尾の使われないビットが 0 でない「正規形でない」表現も拒否する。
    # 許すと、同じ署名を表す別の文字列が作れてしまい、トークン文字列をキーにした
    # 失効リスト（denylist）などをすり抜けられる
    if b64url_encode(data) != text:
        raise DecodeError("base64url の正規形ではありません")
    return data


def _check_key(key: bytes) -> None:
    if not isinstance(key, (bytes, bytearray)) or len(key) < MIN_KEY_BYTES:
        # RFC 7518: HS256 の鍵はハッシュ出力と同じ 256 ビット以上でなければならない
        raise ValueError(f"HS256 の鍵は {MIN_KEY_BYTES} バイト以上の bytes にしてください")


def _json_segment(obj: dict[str, Any]) -> str:
    return b64url_encode(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def _sign(key: bytes, signing_input: bytes) -> bytes:
    return hmac.new(key, signing_input, hashlib.sha256).digest()


# ---------------------------------------------------------------------------
# 演習2: 署名付きトークンの発行
# ---------------------------------------------------------------------------

def encode(payload: dict[str, Any], key: bytes, *, headers: dict[str, Any] | None = None) -> str:
    _check_key(key)
    if not isinstance(payload, dict):
        raise TypeError("payload は dict です")
    header: dict[str, Any] = {"alg": "HS256", "typ": "JWT"}
    for name, value in (headers or {}).items():
        if name in ("alg", "typ"):
            raise ValueError(f"ヘッダー {name!r} は上書きできません")
        header[name] = value
    signing_input = f"{_json_segment(header)}.{_json_segment(payload)}"
    return f"{signing_input}.{b64url_encode(_sign(key, signing_input.encode('ascii')))}"


# ---------------------------------------------------------------------------
# 演習3: 厳格な検証
# ---------------------------------------------------------------------------

def _load_json_object(segment: str, what: str) -> dict[str, Any]:
    try:
        obj = json.loads(b64url_decode(segment).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DecodeError(f"{what} が JSON として不正です") from exc
    if not isinstance(obj, dict):
        raise DecodeError(f"{what} は JSON オブジェクトでなければなりません")
    return obj


def _numeric_date(payload: dict[str, Any], name: str) -> float | None:
    if name not in payload:
        return None
    value = payload[name]
    # bool は int のサブクラスなので明示的に除外する（"exp": true を 1 と解釈しない）
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DecodeError(f"{name} は数値（NumericDate）でなければなりません")
    return float(value)


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
    _check_key(key)
    # 1. 形式: ちょうど 3 つの部分
    if not isinstance(token, str) or token.count(".") != 2:
        raise DecodeError("JWT はドットで区切られた 3 つの部分からなります")
    header_seg, payload_seg, signature_seg = token.split(".")

    # 2. ヘッダーとアルゴリズム。"none" は許可リストに何が書かれていても拒否する
    header = _load_json_object(header_seg, "ヘッダー")
    alg = header.get("alg")
    allowed = set(algorithms) & SUPPORTED_ALGORITHMS
    if not isinstance(alg, str) or alg.lower() == "none" or alg not in allowed:
        raise InvalidAlgorithmError(f"許可されていないアルゴリズムです: {alg!r}")
    if "crit" in header:
        # crit は「この拡張を理解できないなら拒否せよ」という指定。何も理解しないので拒否する
        raise DecodeError("crit ヘッダーには対応していません")

    # 3. 署名の検証（ペイロードを信用する前に）。定数時間で比較する
    signature = b64url_decode(signature_seg)
    expected = _sign(key, f"{header_seg}.{payload_seg}".encode("ascii"))
    if not hmac.compare_digest(signature, expected):
        raise InvalidSignatureError("署名が一致しません")

    # 4. ペイロードとクレーム
    payload = _load_json_object(payload_seg, "ペイロード")
    for name in require:
        if name not in payload:
            raise MissingClaimError(f"必須のクレームがありません: {name}")
    current = time.time() if now is None else now

    exp = _numeric_date(payload, "exp")
    if exp is not None and current >= exp + leeway:
        raise ExpiredTokenError("有効期限（exp）を過ぎています")
    nbf = _numeric_date(payload, "nbf")
    if nbf is not None and current < nbf - leeway:
        raise NotYetValidError("まだ有効になっていません（nbf）")
    _numeric_date(payload, "iat")  # 型だけ検査する

    if issuer is not None:
        if "iss" not in payload:
            raise MissingClaimError("iss がありません")
        if payload["iss"] != issuer:
            raise InvalidIssuerError(f"発行者が違います: {payload['iss']!r}")

    if audience is not None:
        if "aud" not in payload:
            raise MissingClaimError("aud がありません")
        aud = payload["aud"]
        audiences = [aud] if isinstance(aud, str) else aud
        if not isinstance(audiences, list) or audience not in audiences:
            raise InvalidAudienceError("このサービス宛てのトークンではありません")
    elif "aud" in payload:
        # 受け手を指定せずに aud 付きのトークンを受理すると、
        # 別のサービス宛てのトークンを流用される（トークンの「横流し」）
        raise InvalidAudienceError("aud 付きのトークンを受け付けるには audience を指定してください")
    return payload
