"""実際に 127.0.0.1 のソケットで待ち受けるサーバーのスモークテストと、CLI のテスト。"""
from __future__ import annotations

import http.client
import io
import json
import os
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from unittest import mock

from taskapi import db, store
from taskapi.__main__ import main
from taskapi.app import create_app
from taskapi.config import Config
from taskapi.server import make_server
from taskapi.timeutil import utc_now


class RealServerTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        config = Config(db_path=os.path.join(tmp.name, "server.db"))
        with closing(db.connect(config.db_path)) as conn:
            db.migrate(conn)
            with db.transaction(conn):
                self.tenant = store.create_tenant(conn, "acme", utc_now())["id"]

        self.server = make_server(create_app(config), "127.0.0.1", 0)  # port 0: 空いているポートを使う
        thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()

        def stop() -> None:
            self.server.shutdown()
            self.server.server_close()
            thread.join(timeout=5)

        self.addCleanup(stop)  # addCleanup は登録と逆順に実行される（サーバー停止 → 一時ディレクトリ削除）

    def roundtrip(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            headers = {"X-Tenant-Id": self.tenant}
            payload = None
            if body is not None:
                payload = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            return response.status, json.loads(response.read())
        finally:
            conn.close()

    def test_http_roundtrip_over_loopback(self) -> None:
        self.assertEqual(self.roundtrip("GET", "/healthz"), (200, {"status": "ok"}))
        status, created = self.roundtrip("POST", "/v1/projects", {"name": "ソケット越し"})
        self.assertEqual(status, 201)
        status, listed = self.roundtrip("GET", "/v1/projects")
        self.assertEqual(status, 200)
        self.assertEqual([p["id"] for p in listed["items"]], [created["id"]])


class CliTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = mock.patch.dict(os.environ, {"TASKAPI_DB_PATH": os.path.join(tmp.name, "cli.db")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_migrate_then_create_tenant(self) -> None:
        code, out, _ = self.run_cli("migrate")
        self.assertEqual(code, 0)
        self.assertIn("applied 0001_initial", out)
        self.assertEqual(self.run_cli("migrate")[1].strip(), "no pending migrations")

        code, out, _ = self.run_cli("create-tenant", "Acme")
        self.assertEqual(code, 0)
        self.assertRegex(out.strip(), r"^ten_[0-9a-f]{32}$")

    def test_commands_refuse_to_run_with_pending_migrations(self) -> None:
        for command in (["create-tenant", "Acme"], ["serve"]):
            with self.subTest(command=command):
                code, _, err = self.run_cli(*command)
                self.assertEqual(code, 1)
                self.assertIn("0001_initial", err)


if __name__ == "__main__":
    unittest.main()
