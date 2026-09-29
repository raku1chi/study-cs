"""9.4 API設計 — 演習1: Webhook の署名と検証

Webhook は、あなたのサーバーに「外から」届く HTTP リクエストです。受け取った側は、
それが本当に送信元（決済代行など）から届いたもので、途中で改ざんされておらず、
過去の通知の再送（リプレイ攻撃）でもないことを確かめなければなりません。

この演習の署名方式（この章のための独自方式。Stripe や Standard Webhooks も同じ考え方を使っている）:

    ヘッダー Study-Webhook-Id:        msg_2f8a1c    （通知ごとに一意な ID）
    ヘッダー Study-Webhook-Signature: t=1767225600,v1=<署名1>,v1=<署名2>

    署名 = HMAC-SHA256(共有秘密鍵, "{msg_id}.{timestamp}." のバイト列 + 本文のバイト列) の 16 進文字列
    - v1 は複数並べられる（鍵のローテーション中は、新旧 2 つの鍵で署名する）
    - 知らない方式（v2= など）は無視する（将来の拡張のため）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.4

制約: 署名の比較には必ず hmac.compare_digest を使うこと（== は一致しない位置で早く終わるため、
応答時間から署名を 1 文字ずつ推測される「タイミング攻撃」の余地を残す）。
"""
from __future__ import annotations

import hashlib  # noqa: F401
import hmac  # noqa: F401
import re
from typing import Sequence

SIGNATURE_HEADER = "Study-Webhook-Signature"
ID_HEADER = "Study-Webhook-Id"
DEFAULT_TOLERANCE = 300   # 秒

_MSG_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_DIGITS = re.compile(r"^[0-9]{1,15}$")


class WebhookVerificationError(Exception):
    """検証の失敗の基底クラス。受信側はこれを捕まえて 400 や 401 を返し、処理を行わない。"""


class InvalidHeaderError(WebhookVerificationError):
    pass


class TimestampOutsideToleranceError(WebhookVerificationError):
    pass


class SignatureMismatchError(WebhookVerificationError):
    pass


class ReplayError(WebhookVerificationError):
    pass


def _check_msg_id(msg_id: str) -> None:
    """msg_id は英数字・"_"・"-" の 1〜128 文字（実装済み）。違反は InvalidHeaderError。

    署名の対象は "id.timestamp.body" の連結なので、id に "." を許すと区切りの位置をずらした
    別の解釈が同じ署名になりうる。使える文字を制限して曖昧さをなくしている。
    """
    if not isinstance(msg_id, str) or not _MSG_ID.match(msg_id):
        raise InvalidHeaderError(f"メッセージ ID の形式が不正です: {msg_id!r}")


def compute_signature(secret: bytes, msg_id: str, timestamp: int, body: bytes) -> str:
    """署名（16 進文字列）を計算する。msg_id は _check_msg_id で検査すること。"""
    raise NotImplementedError("演習1: compute_signature を実装してください")


def build_signature_header(secrets: Sequence[bytes], msg_id: str, timestamp: int, body: bytes) -> str:
    """送信側: "t=<timestamp>,v1=<鍵1の署名>,v1=<鍵2の署名>..." を返す。secrets が空なら ValueError。"""
    raise NotImplementedError("演習1: build_signature_header を実装してください")


def parse_signature_header(header: str) -> tuple[int, list[str]]:
    """署名ヘッダーを (timestamp, [v1 の署名...]) に分解する。

    - "," で区切り、各部分は前後の空白を除いてから "名前=値" として解釈する
    - t はちょうど 1 つ、1〜15 桁の数字。v1 は 1 つ以上。知らない名前は無視する
    - それ以外（"=" がない、t が数字でない・重複・ない、v1 がない）は InvalidHeaderError
    """
    raise NotImplementedError("演習1: parse_signature_header を実装してください")


def verify(
    secrets: Sequence[bytes],
    msg_id: str,
    header: str,
    body: bytes,
    now: int,
    tolerance: int = DEFAULT_TOLERANCE,
) -> int:
    """受信側: 通知を検証し、タイムスタンプを返す。失敗したら WebhookVerificationError のサブクラス。

    1. msg_id とヘッダーの形式を検査する（InvalidHeaderError）
    2. |now - timestamp| > tolerance なら TimestampOutsideToleranceError（古すぎても未来すぎても拒否）
    3. secrets のどれかの鍵で計算した署名が、ヘッダーの v1 のどれかと一致すれば成功。
       なければ SignatureMismatchError。比較は hmac.compare_digest で行う。
       ヘッダーの値は攻撃者が自由に作れるので、v1 に非 ASCII の文字が入っていても SignatureMismatchError に
       すること（hmac.compare_digest は非 ASCII の文字を含む str どうしを比較できず TypeError を送出する。
       bytes にしてから比較するとよい）。
    """
    raise NotImplementedError("演習1: verify を実装してください")


class ReplayGuard:
    """同じ msg_id の通知が、許容時間内に 2 回届いたら拒否する（リプレイ攻撃・重複配信への対策）。

    window 秒より古いタイムスタンプの ID は忘れてよい（それより古い通知は verify が拒否するため）。
    これにより、覚えておく ID の数が際限なく増えない。
    """

    def __init__(self, window: int = DEFAULT_TOLERANCE) -> None:
        self._window = window
        self._seen: dict[str, int] = {}

    def check(self, msg_id: str, timestamp: int, now: int) -> None:
        """初めての msg_id なら記録する。既に記録があれば ReplayError。

        記録する前に、タイムスタンプが now - window より古い記録を消すこと。
        """
        raise NotImplementedError("演習1: ReplayGuard.check を実装してください")

    def __len__(self) -> int:
        return len(self._seen)
