"""認証: 「だれがリクエストしているか」を解決する。

!!! 注意: これは開発用の仮実装で、認証になっていません !!!

クライアントが送ってきた X-Tenant-Id ヘッダをそのまま信用するので、テナントIDを知っている
（または推測できる）人は、だれでもそのテナントになりすませます。M3 で、認証済みの資格情報
（API トークンやセッション）からテナントとユーザーを導出する実装に置き換えてください。
置き換えるまで、このサービスをインターネットに公開してはいけません。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from . import store
from .web import HTTPError, Request

# 401 を返すときは WWW-Authenticate ヘッダが必須（RFC 9110）。
# M3 で Bearer トークン方式に置き換える想定なので、今から Bearer を宣言しておく。
_CHALLENGE = [("WWW-Authenticate", 'Bearer realm="taskapi"')]


@dataclass(frozen=True)
class Principal:
    """認証済みの主体。TODO(M3): user_id とロールを追加し、認可の判断に使う。"""

    tenant_id: str


def resolve_principal(request: Request, conn: sqlite3.Connection) -> Principal:
    """TODO(M3): 仮実装。ヘッダの値を信用せず、資格情報を検証する実装に置き換える。"""
    tenant_id = request.header("x-tenant-id")
    if not tenant_id:
        raise HTTPError(401, "authentication required", headers=_CHALLENGE)
    if not store.tenant_exists(conn, tenant_id):
        raise HTTPError(401, "authentication failed", headers=_CHALLENGE)
    return Principal(tenant_id=tenant_id)
