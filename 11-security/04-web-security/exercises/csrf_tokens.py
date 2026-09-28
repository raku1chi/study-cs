"""11.4 Webアプリケーションセキュリティ — 演習（csrf_tokens）

CSRF（Cross-Site Request Forgery, クロスサイトリクエストフォージェリ）を防ぐための
トークンを実装します。攻撃者のサイトから利用者のブラウザを使って勝手にリクエストを
送られても、攻撃者はこのトークンの値を知らない・作れないので、リクエストを拒否できます。

作るもの:
  - HMAC 署名付きの同期トークン（synchronizer token）。セッションに紐づき、有効期限を持つ。
    サーバー側に状態を持たなくても、鍵さえあれば発行・検証できる（ステートレス）。
  - double-submit cookie 方式で使う定数時間比較。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.4
    python3 tools/check.py -v 11.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_csrf_tokens

トークンの形式: "issued_at.nonce.signature"
    issued_at  発行時刻（UNIX 秒、10 進の整数の文字列）
    nonce      毎回異なるランダム値（base64url。secrets で生成する）
    signature  base64url(HMAC-SHA256(secret_key, "session_id:issued_at:nonce"))

使ってよいもの: hmac（hmac.new, hmac.compare_digest）, hashlib.sha256, secrets, base64, time。
"""
from __future__ import annotations

import base64  # noqa: F401
import hmac  # noqa: F401
import secrets  # noqa: F401
import time  # noqa: F401
from hashlib import sha256  # noqa: F401

TOKEN_BYTES = 16


def generate_token(secret_key: bytes, session_id: str, *, now: int | None = None) -> str:
    """署名付き CSRF トークン "issued_at.nonce.signature" を作る。

    - secret_key が bytes でない、または 16 バイト未満なら ValueError。
    - now が None なら現在時刻（int(time.time())）を発行時刻にする。
    - nonce は secrets.token_bytes(TOKEN_BYTES) を base64url（パディングなし）にしたもの。
    """
    raise NotImplementedError("演習: generate_token を実装してください")


def validate_token(
    secret_key: bytes,
    session_id: str,
    token: str,
    *,
    max_age_seconds: int = 3600,
    now: int | None = None,
) -> bool:
    """token が session_id 宛てに発行され、改ざんされておらず、期限内なら True を返す。

    次のいずれかなら False（例外は投げない）:
    - token が文字列でない、"." で 3 つに分かれない
    - issued_at が 10 進整数として解釈できない、または表記が正規でない（"007" や " 7" など）
    - 署名が一致しない（session_id・issued_at・nonce から張り直した HMAC と比較。定数時間で）
    - now（None なら現在時刻）が issued_at より前
    - now − issued_at が max_age_seconds を超える

    署名の比較には hmac.compare_digest を使うこと（== はタイミング攻撃の的になる）。
    """
    raise NotImplementedError("演習: validate_token を実装してください")


def constant_time_compare(a: str, b: str) -> bool:
    """double-submit cookie 方式で、Cookie の値とフォームの値を定数時間で比較する。

    a と b（ともに str）が等しければ True。文字列でないものが渡されたら False。
    """
    raise NotImplementedError("演習: constant_time_compare を実装してください")
