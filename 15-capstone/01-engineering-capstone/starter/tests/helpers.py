"""テスト用の補助: 一時 DB と固定の時計でアプリを組み立て、ネットワークを使わずに呼び出す。"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import warnings
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from wsgiref import validate
from wsgiref.util import setup_testing_defaults

from taskapi import db, store
from taskapi.app import create_app
from taskapi.config import Config


class FakeClock:
    """注入用の時計。テストの中で時刻を自由に進められる。"""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


@dataclass
class WsgiResponse:
    status: int
    headers: dict[str, str]  # キーは小文字
    body: bytes

    def json(self) -> Any:
        return json.loads(self.body)


def call_wsgi(
    app: Callable[..., Any],
    method: str,
    path: str,
    *,
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> WsgiResponse:
    """app を WSGI の仕様どおりに呼び出す。

    wsgiref.validate.validator で包むので、アプリが WSGI の仕様に違反していればテストが失敗する
    （例: ステータス行の形式、ヘッダの型、Content-Type の有無、長さを指定しない read()）。
    """
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    path_info, _, query = path.partition("?")
    environ.update(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path_info,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(body)),
            "wsgi.input": io.BytesIO(body),
        }
    )
    for name, value in (headers or {}).items():
        key = name.upper().replace("-", "_")
        environ[key if key in ("CONTENT_TYPE", "CONTENT_LENGTH") else "HTTP_" + key] = value

    captured: dict[str, Any] = {}

    def start_response(status: str, response_headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
        captured["status"] = status
        captured["headers"] = response_headers
        return lambda data: None  # WSGI の write() 呼び出し口（このアプリでは使わない）

    with warnings.catch_warnings():
        warnings.simplefilter("error", validate.WSGIWarning)  # 仕様上の警告もエラーとして扱う
        result = validate.validator(app)(environ, start_response)
        try:
            payload = b"".join(result)
        finally:
            result.close()
    status = int(captured["status"].split(" ", 1)[0])
    return WsgiResponse(status, {k.lower(): v for k, v in captured["headers"]}, payload)


class AppTestCase(unittest.TestCase):
    """一時ディレクトリの SQLite と固定の時計でアプリを組み立てる基底クラス。"""

    START = datetime(2026, 4, 1, 9, 0, 0, tzinfo=timezone.utc)

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config = Config(db_path=os.path.join(tmp.name, "test.db"))
        with closing(db.connect(self.config.db_path)) as conn:
            db.migrate(conn)
        self.clock = FakeClock(self.START)
        self.app = create_app(self.config, clock=self.clock)

    def create_tenant(self, name: str = "acme") -> str:
        with closing(db.connect(self.config.db_path)) as conn, db.transaction(conn):
            return store.create_tenant(conn, name, self.clock())["id"]

    def request(
        self,
        method: str,
        path: str,
        *,
        tenant: str | None = None,
        json_body: Any = None,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> WsgiResponse:
        all_headers = dict(headers or {})
        if tenant is not None:
            all_headers.setdefault("X-Tenant-Id", tenant)
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            all_headers.setdefault("Content-Type", "application/json")
        return call_wsgi(self.app, method, path, body=body or b"", headers=all_headers)
