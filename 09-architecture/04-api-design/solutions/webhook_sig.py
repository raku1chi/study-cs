"""9.4 API設計 — 解答例: Webhook の署名と検証

演習の仕様は exercises/webhook_sig.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import hmac
import re
from typing import Sequence

SIGNATURE_HEADER = "Study-Webhook-Signature"
ID_HEADER = "Study-Webhook-Id"
DEFAULT_TOLERANCE = 300

_MSG_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_DIGITS = re.compile(r"^[0-9]{1,15}$")


class WebhookVerificationError(Exception):
    pass


class InvalidHeaderError(WebhookVerificationError):
    pass


class TimestampOutsideToleranceError(WebhookVerificationError):
    pass


class SignatureMismatchError(WebhookVerificationError):
    pass


class ReplayError(WebhookVerificationError):
    pass


def _check_msg_id(msg_id: str) -> None:
    # 署名の対象は "id.timestamp.body" の連結。id に "." を許すと、区切りの位置をずらした
    # 別の解釈が同じ署名になりうるので、使える文字を制限して曖昧さをなくす
    if not isinstance(msg_id, str) or not _MSG_ID.match(msg_id):
        raise InvalidHeaderError(f"メッセージ ID の形式が不正です: {msg_id!r}")


def compute_signature(secret: bytes, msg_id: str, timestamp: int, body: bytes) -> str:
    _check_msg_id(msg_id)
    signed = f"{msg_id}.{timestamp}.".encode("ascii") + body
    return hmac.new(secret, signed, hashlib.sha256).hexdigest()


def build_signature_header(secrets: Sequence[bytes], msg_id: str, timestamp: int, body: bytes) -> str:
    if not secrets:
        raise ValueError("署名の鍵が 1 つもありません")
    parts = [f"t={timestamp}"]
    parts += [f"v1={compute_signature(s, msg_id, timestamp, body)}" for s in secrets]
    return ",".join(parts)


def parse_signature_header(header: str) -> tuple[int, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        name, sep, value = part.strip().partition("=")
        if not sep:
            raise InvalidHeaderError(f"署名ヘッダーの形式が不正です: {part!r}")
        if name == "t":
            if timestamp is not None or not _DIGITS.match(value):
                raise InvalidHeaderError("タイムスタンプが不正か、重複しています")
            timestamp = int(value)
        elif name == "v1":
            signatures.append(value)
        # 知らない方式（v2= など）は無視する: 送信側が新しい方式を追加しても受信側が壊れない
    if timestamp is None or not signatures:
        raise InvalidHeaderError("t= と v1= の両方が必要です")
    return timestamp, signatures


def verify(
    secrets: Sequence[bytes],
    msg_id: str,
    header: str,
    body: bytes,
    now: int,
    tolerance: int = DEFAULT_TOLERANCE,
) -> int:
    _check_msg_id(msg_id)
    timestamp, signatures = parse_signature_header(header)
    # 古すぎる（盗聴した通知の再送）も、未来すぎる（時計のずれ・偽造）も拒否する
    if abs(now - timestamp) > tolerance:
        raise TimestampOutsideToleranceError(f"タイムスタンプが許容範囲（±{tolerance} 秒）の外です")
    matched = False
    for secret in secrets:
        expected = compute_signature(secret, msg_id, timestamp, body)
        for candidate in signatures:
            # == ではなく定数時間の比較。途中で打ち切らないよう、見つかっても全組み合わせを比較する。
            # ヘッダーの値は攻撃者が自由に作れる。compare_digest は非 ASCII の str を比較できず
            # TypeError になるので、bytes にしてから比べる（どんな値でも「不一致」として扱える）
            if hmac.compare_digest(expected.encode("ascii"), candidate.encode("utf-8", "replace")):
                matched = True
    if not matched:
        raise SignatureMismatchError("署名が一致しません")
    return timestamp


class ReplayGuard:
    def __init__(self, window: int = DEFAULT_TOLERANCE) -> None:
        self._window = window
        self._seen: dict[str, int] = {}

    def check(self, msg_id: str, timestamp: int, now: int) -> None:
        # 許容範囲より古い通知は verify が拒否するので、それより古い ID は覚えておく必要がない
        cutoff = now - self._window
        for old in [m for m, ts in self._seen.items() if ts < cutoff]:
            del self._seen[old]
        if msg_id in self._seen:
            raise ReplayError(f"同じ通知が再送されました: {msg_id}")
        self._seen[msg_id] = timestamp

    def __len__(self) -> int:
        return len(self._seen)
