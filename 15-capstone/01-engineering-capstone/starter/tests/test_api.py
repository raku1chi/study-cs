"""HTTP API の結合テスト（WSGI をプロセス内で呼び出す。ネットワークは使わない）。"""
from __future__ import annotations

import re
import unittest

from taskapi.web import HTTPError

from .helpers import AppTestCase


class HealthTest(AppTestCase):
    def test_healthz_needs_no_authentication(self) -> None:
        response = self.request("GET", "/healthz")
        self.assertEqual(response.status, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class ProjectApiTest(AppTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.tenant = self.create_tenant("acme")

    def create_project(self, name: str, tenant: str | None = None):
        return self.request("POST", "/v1/projects", tenant=tenant or self.tenant, json_body={"name": name})

    def test_create_then_get(self) -> None:
        created = self.create_project("ウェブサイト刷新")
        self.assertEqual(created.status, 201)
        body = created.json()
        self.assertRegex(body["id"], r"^prj_[0-9a-f]{32}$")
        self.assertEqual(body["name"], "ウェブサイト刷新")
        self.assertEqual(body["created_at"], "2026-04-01T09:00:00.000Z", "時刻は注入した時計から取る")
        self.assertEqual(created.headers["location"], f"/v1/projects/{body['id']}")

        fetched = self.request("GET", created.headers["location"], tenant=self.tenant)
        self.assertEqual(fetched.status, 200)
        self.assertEqual(fetched.json(), body)

    def test_list_is_ordered_by_creation_time_and_limited(self) -> None:
        for name in ("A", "B", "C"):
            self.create_project(name)
            self.clock.advance(1)
        items = self.request("GET", "/v1/projects", tenant=self.tenant).json()["items"]
        self.assertEqual([p["name"] for p in items], ["A", "B", "C"])
        limited = self.request("GET", "/v1/projects?limit=2", tenant=self.tenant).json()["items"]
        self.assertEqual([p["name"] for p in limited], ["A", "B"])

    def test_invalid_limit_is_400(self) -> None:
        for value in ("0", "-1", "abc", "201", "1.5", ""):
            with self.subTest(limit=value):
                response = self.request("GET", f"/v1/projects?limit={value}", tenant=self.tenant)
                self.assertEqual(response.status, 400)

    def test_duplicate_name_is_409(self) -> None:
        self.assertEqual(self.create_project("基盤").status, 201)
        self.assertEqual(self.create_project("基盤").status, 409)

    def test_names_are_nfc_normalized_before_uniqueness_check(self) -> None:
        composed = "が"            # 「が」（1 コードポイント）
        decomposed = "が"    # 「か」＋結合用濁点（見た目は同じ「が」）
        self.assertEqual(self.create_project(composed).status, 201)
        self.assertEqual(self.create_project(decomposed).status, 409)

    def test_validation_errors_are_422_problem_details(self) -> None:
        cases = [{}, {"name": ""}, {"name": "   "}, {"name": 123}, {"name": None}, {"name": "x" * 201}]
        for payload in cases:
            with self.subTest(payload=payload):
                response = self.request("POST", "/v1/projects", tenant=self.tenant, json_body=payload)
                self.assertEqual(response.status, 422)
                self.assertEqual(response.headers["content-type"], "application/problem+json")
                self.assertEqual(response.json()["status"], 422)

    def test_non_object_body_is_400(self) -> None:
        response = self.request("POST", "/v1/projects", tenant=self.tenant, json_body=["name"])
        self.assertEqual(response.status, 400)

    def test_deeply_nested_json_is_400_not_500(self) -> None:
        # 深い入れ子は json モジュールの再帰上限に達して RecursionError になりうる。500 にしてはいけない
        depth = 100_000
        response = self.request(
            "POST", "/v1/projects", tenant=self.tenant,
            body=b"[" * depth + b"]" * depth, headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status, 400)

    def test_wrong_content_type_is_415(self) -> None:
        response = self.request(
            "POST", "/v1/projects", tenant=self.tenant, body=b"name=x",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(response.status, 415)

    def test_unknown_method_is_405(self) -> None:
        response = self.request("DELETE", "/v1/projects", tenant=self.tenant)
        self.assertEqual(response.status, 405)
        self.assertEqual(response.headers["allow"], "GET, POST")


class TenantIsolationTest(AppTestCase):
    """テナント分離: 別テナントのデータは、見えない・触れない・存在も分からない。"""

    def setUp(self) -> None:
        super().setUp()
        self.acme = self.create_tenant("acme")
        self.globex = self.create_tenant("globex")
        response = self.request("POST", "/v1/projects", tenant=self.acme, json_body={"name": "極秘プロジェクト"})
        self.acme_project_id = response.json()["id"]

    def test_list_shows_only_own_projects(self) -> None:
        items = self.request("GET", "/v1/projects", tenant=self.globex).json()["items"]
        self.assertEqual(items, [])

    def test_other_tenants_project_is_404_not_403(self) -> None:
        response = self.request("GET", f"/v1/projects/{self.acme_project_id}", tenant=self.globex)
        self.assertEqual(response.status, 404, "403 だと「存在する」ことが漏れる")

    def test_same_name_is_allowed_in_different_tenants(self) -> None:
        response = self.request("POST", "/v1/projects", tenant=self.globex, json_body={"name": "極秘プロジェクト"})
        self.assertEqual(response.status, 201)


class AuthenticationTest(AppTestCase):
    def test_missing_credentials_is_401_with_challenge(self) -> None:
        response = self.request("GET", "/v1/projects")
        self.assertEqual(response.status, 401)
        self.assertIn("www-authenticate", response.headers, "401 には WWW-Authenticate が必須（RFC 9110）")

    def test_unknown_tenant_is_401(self) -> None:
        response = self.request("GET", "/v1/projects", tenant="ten_does_not_exist")
        self.assertEqual(response.status, 401)

    def test_every_v1_route_requires_authentication(self) -> None:
        """ルート表を列挙して、認証なしで通るルートがないことを確かめる。

        ルートを追加するたびにテストを書き足さなくても、認証のかけ忘れを検出できる。
        M3 では「別テナントの ID を指定したら 404 になるか」も同じ方法で全ルートに対して確かめるとよい。
        """
        checked = 0
        for route in self.app.router.routes:
            if not route.template.startswith("/v1/"):
                continue
            path = re.sub(r"\{[^}]+\}", "x", route.template)
            body = {} if route.method in ("POST", "PUT", "PATCH") else None
            with self.subTest(route=f"{route.method} {route.template}"):
                response = self.request(route.method, path, json_body=body)
                self.assertEqual(response.status, 401)
            checked += 1
        self.assertGreater(checked, 0)


class ErrorHandlingTest(AppTestCase):
    def test_unexpected_exception_is_500_without_internal_details(self) -> None:
        def broken(request):
            raise RuntimeError("no such column: tasks.owner (/srv/taskapi/store.py:42)")

        self.app.router.add("GET", "/boom", broken)
        with self.assertLogs("taskapi", level="ERROR") as logs:
            response = self.request("GET", "/boom")
        self.assertEqual(response.status, 500)
        self.assertNotIn(b"store.py", response.body, "内部の情報（SQL・ファイルパス）をレスポンスに含めてはいけない")
        self.assertIn("store.py", "\n".join(logs.output), "原因の調査のためにログには残す")

    def test_http_error_from_handler_becomes_problem_details(self) -> None:
        def teapot(request):
            raise HTTPError(418, "short and stout")

        self.app.router.add("GET", "/teapot", teapot)
        response = self.request("GET", "/teapot")
        self.assertEqual(response.status, 418)
        self.assertEqual(response.json()["detail"], "short and stout")


if __name__ == "__main__":
    unittest.main()
