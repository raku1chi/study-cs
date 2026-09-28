"""アプリケーション本体: ルートの定義・ハンドラ・入力の検証。

層の分け方:
    web.py     HTTP の世界（ヘッダ・ステータス・JSON）
    app.py     ユースケース（認証 → 入力検証 → トランザクション → レスポンス）
    store.py   SQL の世界（テナントで絞り込んだ読み書き）
ハンドラの中で SQL を書かず、store の関数の中で HTTP のステータスを決めない、という分担を保つと、
M2 以降で機能が増えても見通しが保てます。
"""
from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from contextlib import closing
from datetime import datetime
from http import HTTPStatus
from typing import Any, Callable, Iterable

from . import db, store
from .auth import resolve_principal
from .config import Config
from .timeutil import utc_now
from .web import HTTPError, Request, Response, Router, json_response, problem_response

logger = logging.getLogger("taskapi")

MAX_NAME_LENGTH = 200
DEFAULT_LIMIT = 50
MAX_LIMIT = 200
_LIMIT_RE = re.compile(r"[0-9]{1,6}")


class App:
    """WSGI アプリケーション。create_app() で作る。"""

    def __init__(self, config: Config, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.config = config
        self.clock = clock  # 時刻は注入する（テストで固定・操作できるように）
        self.router = Router()
        self._register_routes()

    def _register_routes(self) -> None:
        add = self.router.add
        add("GET", "/healthz", self.healthz)
        add("GET", "/v1/projects", self.list_projects)
        add("POST", "/v1/projects", self.create_project)
        add("GET", "/v1/projects/{project_id}", self.get_project)
        # TODO(M2): tasks / comments / users のエンドポイントを追加する
        # TODO(M4): GET /readyz（DB に接続でき、マイグレーションが適用済みか）と GET /metrics を追加する

    # ------------------------------------------------------------------
    # WSGI のエントリポイント
    # ------------------------------------------------------------------
    def __call__(self, environ: dict[str, Any], start_response: Callable[..., Any]) -> Iterable[bytes]:
        # TODO(M4): リクエストIDの採番・構造化ログ・メトリクス計測を、ここ（またはミドルウェア）で行う
        # TODO(M5): レート制限・冪等性キー・リクエスト全体のタイムアウトもこの周辺に入る
        try:
            request = Request.from_environ(environ, max_body_bytes=self.config.max_body_bytes)
            route, params = self.router.match(request.method, request.path)
            request.path_params = params
            response = route.handler(request)
        except HTTPError as exc:
            response = problem_response(exc.status, exc.detail, headers=exc.headers)
        except Exception:
            # 想定外のエラーの詳細（スタックトレース・SQL・内部の値）は利用者に返さず、ログにだけ残す
            logger.exception("unhandled error")
            response = problem_response(500, "internal server error")
        status_line = f"{response.status} {HTTPStatus(response.status).phrase}"
        start_response(status_line, response.headers + [("Content-Length", str(len(response.body)))])
        return [response.body]

    def connect(self) -> "closing[sqlite3.Connection]":
        """リクエストごとの DB 接続。`with self.connect() as conn:` で使い、抜けるときに閉じる。"""
        return closing(db.connect(self.config.db_path))

    # ------------------------------------------------------------------
    # ハンドラ
    # ------------------------------------------------------------------
    def healthz(self, request: Request) -> Response:
        """生存確認（liveness）。プロセスが応答できるかだけを見る。DB には触れない。"""
        return json_response({"status": "ok"})

    def create_project(self, request: Request) -> Response:
        with self.connect() as conn:
            principal = resolve_principal(request, conn)  # 認証を先に（未認証の入力は処理しない）
            name = _required_string(request.json(), "name", max_length=MAX_NAME_LENGTH)
            try:
                with db.transaction(conn):
                    project = store.create_project(conn, principal.tenant_id, name=name, now=self.clock())
            except store.Conflict:
                raise HTTPError(409, "a project with the same name already exists") from None
        return json_response(project, status=201, headers=[("Location", f"/v1/projects/{project['id']}")])

    def list_projects(self, request: Request) -> Response:
        with self.connect() as conn:
            principal = resolve_principal(request, conn)
            limit = _limit_param(request)
            projects = store.list_projects(conn, principal.tenant_id, limit=limit)
        # TODO(M2): カーソル方式のページネーションにして、次のページのカーソル（next_cursor）を返す
        return json_response({"items": projects})

    def get_project(self, request: Request) -> Response:
        with self.connect() as conn:
            principal = resolve_principal(request, conn)
            try:
                project = store.get_project(conn, principal.tenant_id, request.path_params["project_id"])
            except store.NotFound:
                # 他テナントのプロジェクトも「存在しない」と答える（403 だと存在を教えてしまう）
                raise HTTPError(404, "project not found") from None
        return json_response(project)


def create_app(config: Config | None = None, *, clock: Callable[[], datetime] = utc_now) -> App:
    return App(config if config is not None else Config.from_env(), clock=clock)


# ----------------------------------------------------------------------
# 入力の検証
#   400: JSON として読めない・形が違う（構文の誤り）
#   422: 形は正しいが値が要件を満たさない（意味の誤り）
# ----------------------------------------------------------------------

def _required_string(payload: Any, field: str, *, max_length: int) -> str:
    if not isinstance(payload, dict):
        raise HTTPError(400, "request body must be a JSON object")
    value = payload.get(field)
    if not isinstance(value, str):
        raise HTTPError(422, f"'{field}' is required and must be a string")
    # 見た目が同じ文字列を同一に扱うため NFC に正規化してから、前後の空白を除いて長さを数える（1.1 章）
    value = unicodedata.normalize("NFC", value).strip()
    if not value:
        raise HTTPError(422, f"'{field}' must not be empty")
    if len(value) > max_length:
        raise HTTPError(422, f"'{field}' must be at most {max_length} characters")
    return value


def _limit_param(request: Request) -> int:
    raw = request.query_param("limit")
    if raw is None:
        return DEFAULT_LIMIT
    if not _LIMIT_RE.fullmatch(raw) or not 1 <= int(raw) <= MAX_LIMIT:
        raise HTTPError(400, f"limit must be an integer between 1 and {MAX_LIMIT}")
    return int(raw)
