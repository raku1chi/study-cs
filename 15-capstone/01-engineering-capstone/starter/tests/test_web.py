"""web.py（ルーティング・リクエストの解釈）の単体テスト。DB を使わない。"""
from __future__ import annotations

import io
import json
import unittest

from taskapi.web import HTTPError, Request, Response, Router, problem_response


def ok(request: Request) -> Response:
    return Response(200, b"ok", [("Content-Type", "text/plain")])


def make_request(body: bytes = b"", content_type: str | None = "application/json", length: str | None = None) -> Request:
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/",
        "QUERY_STRING": "",
        "CONTENT_LENGTH": str(len(body)) if length is None else length,
        "wsgi.input": io.BytesIO(body),
    }
    if content_type is not None:
        environ["CONTENT_TYPE"] = content_type
    return Request.from_environ(environ, max_body_bytes=1024)


class RouterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.router = Router()
        self.router.add("GET", "/v1/projects", ok)
        self.router.add("POST", "/v1/projects", ok)
        self.router.add("GET", "/v1/projects/{project_id}", ok)

    def test_matches_static_route(self) -> None:
        route, params = self.router.match("GET", "/v1/projects")
        self.assertEqual(route.template, "/v1/projects")
        self.assertEqual(params, {})

    def test_extracts_path_parameters(self) -> None:
        route, params = self.router.match("GET", "/v1/projects/prj_123")
        self.assertEqual(route.template, "/v1/projects/{project_id}")
        self.assertEqual(params, {"project_id": "prj_123"})

    def test_parameter_does_not_cross_slash(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self.router.match("GET", "/v1/projects/a/b")
        self.assertEqual(ctx.exception.status, 404)

    def test_unknown_path_is_404(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self.router.match("GET", "/v2/projects")
        self.assertEqual(ctx.exception.status, 404)

    def test_wrong_method_is_405_with_allow_header(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            self.router.match("DELETE", "/v1/projects")
        self.assertEqual(ctx.exception.status, 405)
        self.assertIn(("Allow", "GET, POST"), ctx.exception.headers)

    def test_template_must_be_absolute(self) -> None:
        with self.assertRaises(ValueError):
            self.router.add("GET", "v1/projects", ok)


class RequestTest(unittest.TestCase):
    def test_json_body_is_parsed(self) -> None:
        self.assertEqual(make_request(b'{"name": "x"}').json(), {"name": "x"})

    def test_content_type_parameters_are_allowed(self) -> None:
        request = make_request(b"[]", content_type="application/json; charset=utf-8")
        self.assertEqual(request.json(), [])

    def test_wrong_content_type_is_415(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            make_request(b"{}", content_type="text/plain").json()
        self.assertEqual(ctx.exception.status, 415)

    def test_invalid_json_is_400(self) -> None:
        for body in (b"{", b"\xff\xfe", b"{'single': 'quotes'}"):
            with self.subTest(body=body), self.assertRaises(HTTPError) as ctx:
                make_request(body).json()
            self.assertEqual(ctx.exception.status, 400)

    def test_nan_and_infinity_are_rejected(self) -> None:
        for body in (b"NaN", b'{"x": Infinity}', b"[-Infinity]"):
            with self.subTest(body=body), self.assertRaises(HTTPError) as ctx:
                make_request(body).json()
            self.assertEqual(ctx.exception.status, 400)

    def test_body_larger_than_limit_is_413(self) -> None:
        with self.assertRaises(HTTPError) as ctx:
            make_request(b"x" * 1025)
        self.assertEqual(ctx.exception.status, 413)

    def test_malformed_content_length_is_400(self) -> None:
        for length in ("-1", "abc", "1e3"):
            with self.subTest(length=length), self.assertRaises(HTTPError) as ctx:
                make_request(b"{}", length=length)
            self.assertEqual(ctx.exception.status, 400)


class ProblemResponseTest(unittest.TestCase):
    def test_problem_details_format(self) -> None:
        response = problem_response(404, "project not found")
        self.assertEqual(response.status, 404)
        self.assertIn(("Content-Type", "application/problem+json"), response.headers)
        self.assertEqual(
            json.loads(response.body),
            {"type": "about:blank", "title": "Not Found", "status": 404, "detail": "project not found"},
        )


if __name__ == "__main__":
    unittest.main()
