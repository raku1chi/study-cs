"""最小限の WSGI ツールキット: Request / Response / HTTPError / Router。

フレームワークを使わずに書いているのは、HTTP サーバーとアプリケーションの境界（WSGI, PEP 3333）で
何が起きているかを見えるようにするためです。あなたのプロジェクトでは、使い慣れた言語や
フレームワークに置き換えてかまいません。

エラーは RFC 9457（Problem Details for HTTP APIs）の形式で返します:
    {"type": "about:blank", "title": "Not Found", "status": 404, "detail": "project not found"}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Callable
from urllib.parse import parse_qs

JSON_TYPE = "application/json"
PROBLEM_TYPE = "application/problem+json"


class HTTPError(Exception):
    """ハンドラから送出すると、Problem Details 形式のエラーレスポンスになる。"""

    def __init__(self, status: int, detail: str = "", *, headers: list[tuple[str, str]] | None = None) -> None:
        super().__init__(detail or HTTPStatus(status).phrase)
        self.status = status
        self.detail = detail
        self.headers = list(headers or [])


@dataclass
class Request:
    method: str
    path: str
    query: dict[str, list[str]]
    headers: dict[str, str]  # キーは小文字（例: "content-type", "x-tenant-id"）
    body: bytes
    path_params: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_environ(cls, environ: dict[str, Any], *, max_body_bytes: int) -> "Request":
        headers: dict[str, str] = {}
        for key, value in environ.items():
            if key.startswith("HTTP_"):
                headers[key[5:].replace("_", "-").lower()] = value
        if environ.get("CONTENT_TYPE"):
            headers["content-type"] = environ["CONTENT_TYPE"]

        # PEP 3333 では PATH_INFO は「バイト列を latin-1 で文字列にしたもの」。UTF-8 として読み直す。
        try:
            path = (environ.get("PATH_INFO") or "/").encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            raise HTTPError(400, "request path is not valid UTF-8") from None

        # ボディは Content-Length の分だけ読む（長さを指定せずに read() するとソケットで待ち続ける）。
        raw_length = environ.get("CONTENT_LENGTH") or "0"
        if not re.fullmatch(r"[0-9]+", raw_length):
            raise HTTPError(400, "invalid Content-Length")
        length = int(raw_length)
        if length > max_body_bytes:
            raise HTTPError(413, f"request body must be at most {max_body_bytes} bytes")
        body = environ["wsgi.input"].read(length) if length else b""

        return cls(
            method=environ["REQUEST_METHOD"].upper(),
            path=path,
            query=parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True),
            headers=headers,
            body=body,
        )

    def header(self, name: str, default: str | None = None) -> str | None:
        return self.headers.get(name.lower(), default)

    def query_param(self, name: str, default: str | None = None) -> str | None:
        values = self.query.get(name)
        return values[0] if values else default

    def json(self) -> Any:
        """ボディを JSON として読む。Content-Type と構文を厳密に検査する。"""
        media_type = (self.header("content-type") or "").split(";", 1)[0].strip().lower()
        if media_type != JSON_TYPE:
            raise HTTPError(415, "Content-Type must be application/json")
        try:
            # NaN / Infinity は JSON の規格外なので拒否する（1.1 章）
            return json.loads(self.body.decode("utf-8"), parse_constant=_reject_constant)
        except RecursionError:
            # 深く入れ子にした JSON は、再帰の上限を超えて RecursionError になる。500 ではなく 400 にする
            raise HTTPError(400, "JSON is nested too deeply") from None
        except (UnicodeDecodeError, ValueError):  # json.JSONDecodeError は ValueError のサブクラス
            raise HTTPError(400, "request body is not valid JSON") from None


def _reject_constant(name: str) -> Any:
    raise ValueError(f"{name} is not allowed in JSON")


@dataclass
class Response:
    status: int = 200
    body: bytes = b""
    headers: list[tuple[str, str]] = field(default_factory=list)


def json_response(data: Any, status: int = 200, headers: list[tuple[str, str]] | None = None) -> Response:
    # application/json には charset パラメータが定義されていない（JSON は UTF-8。RFC 8259）
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(status, body, [("Content-Type", JSON_TYPE), *(headers or [])])


def problem_response(status: int, detail: str = "", headers: list[tuple[str, str]] | None = None) -> Response:
    payload: dict[str, Any] = {"type": "about:blank", "title": HTTPStatus(status).phrase, "status": status}
    if detail:
        payload["detail"] = detail
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(status, body, [("Content-Type", PROBLEM_TYPE), *(headers or [])])


Handler = Callable[[Request], Response]
_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True)
class Route:
    method: str
    template: str  # 例: "/v1/projects/{project_id}"。メトリクスのラベルにはこちらを使う（M4）
    pattern: re.Pattern
    handler: Handler


class Router:
    """"/v1/projects/{project_id}" 形式のテンプレートでルートを登録し、リクエストを振り分ける。"""

    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, template: str, handler: Handler) -> None:
        self._routes.append(Route(method.upper(), template, _compile(template), handler))

    @property
    def routes(self) -> list[Route]:
        return list(self._routes)

    def match(self, method: str, path: str) -> tuple[Route, dict[str, str]]:
        """一致したルートとパスパラメータを返す。

        パスは一致するがメソッドが違えば 405（Allow ヘッダ付き）、パスが一致しなければ 404。
        """
        allowed: set[str] = set()
        for route in self._routes:
            m = route.pattern.fullmatch(path)
            if m is None:
                continue
            if route.method == method:
                return route, m.groupdict()
            allowed.add(route.method)
        if allowed:
            raise HTTPError(405, f"method {method} is not allowed", headers=[("Allow", ", ".join(sorted(allowed)))])
        raise HTTPError(404, "no route matches this path")


def _compile(template: str) -> re.Pattern:
    if not template.startswith("/"):
        raise ValueError(f"template must start with '/': {template!r}")
    parts: list[str] = []
    pos = 0
    for m in _PARAM_RE.finditer(template):
        parts.append(re.escape(template[pos:m.start()]))
        parts.append(f"(?P<{m.group(1)}>[^/]+)")  # パラメータは '/' をまたがない
        pos = m.end()
    parts.append(re.escape(template[pos:]))
    return re.compile("".join(parts))
