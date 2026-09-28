"""5.4 Webの仕組みとネットワーク構成 — 解答例（cors）

演習の仕様は exercises/cors.py の docstring を参照してください。
ブラウザ側の判定は、WHATWG Fetch Standard の「CORS check」と「CORS-preflight fetch」に沿っています。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

SAFELISTED_METHODS = {"GET", "HEAD", "POST"}
DEFAULT_PORTS = {"http": 80, "https": 443}
# 「スキーム://ホスト[:ポート]」。ブラウザが送る Origin は小文字で、既定のポートは省略される
ORIGIN_RE = re.compile(r"(https?)://([a-z0-9.-]+)(?::([0-9]{1,5}))?")
PATTERN_RE = re.compile(r"(https?)://((?:\*\.)?[a-z0-9.-]+)(?::([0-9]{1,5}))?")


def _header(headers: Mapping[str, str], name: str) -> str | None:
    key = name.lower()
    for k, v in headers.items():
        if k.lower() == key:
            return v
    return None


def _split_list(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _parse(regex: re.Pattern[str], text: str) -> tuple[str, str, int] | None:
    m = regex.fullmatch(text)
    if not m:
        return None
    scheme, host, port = m.group(1), m.group(2), m.group(3)
    port_num = int(port) if port else DEFAULT_PORTS[scheme]
    if not 0 < port_num <= 65535 or host.startswith(".") or host.endswith(".") or ".." in host:
        return None
    return scheme, host, port_num


@dataclass
class CorsPolicy:
    allowed_origins: list[str]
    allowed_methods: list[str] = field(default_factory=lambda: ["GET", "HEAD", "POST"])
    allowed_headers: list[str] = field(default_factory=list)
    exposed_headers: list[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age: int | None = None

    def __post_init__(self) -> None:
        for entry in self.allowed_origins:
            if entry == "*":
                continue
            if entry == "null" or _parse(PATTERN_RE, entry) is None:
                # "null" はサンドボックスの iframe や file:// など、正体の分からない送信元が名乗るので許可しない
                raise ValueError(f"許可するオリジンの書式が不正です: {entry!r}")
        if self.allow_credentials and "*" in self.allowed_origins:
            # 「どのサイトからでも、利用者の Cookie 付きで読める」設定は、ブラウザも許さない危険な構成
            raise ValueError("allow_credentials=True と '*' は同時に指定できません")
        if self.allow_credentials and ("*" in self.allowed_headers or "*" in self.allowed_methods):
            raise ValueError("資格情報付きでは、ヘッダやメソッドのワイルドカード '*' は使えません")
        self.allowed_methods = [m.upper() for m in self.allowed_methods]
        self.allowed_headers = [h.lower() for h in self.allowed_headers]

    @property
    def wildcard(self) -> bool:
        return "*" in self.allowed_origins


# ---------------------------------------------------------------------------
# 演習2: サーバー側 — ポリシーに従って CORS のヘッダを返す
# ---------------------------------------------------------------------------

def origin_allowed(policy: CorsPolicy, origin: str | None) -> bool:
    if origin is None:
        return False
    if policy.wildcard:
        return True
    parsed = _parse(ORIGIN_RE, origin)
    if parsed is None:
        return False  # "null" や、パスの付いた不正な値
    scheme, host, port = parsed
    for entry in policy.allowed_origins:
        p_scheme, p_host, p_port = _parse(PATTERN_RE, entry)  # __post_init__ で検査済み
        if (scheme, port) != (p_scheme, p_port):
            continue  # スキームとポートは完全一致が必要（http と https は別のオリジン）
        if p_host.startswith("*."):
            # "*.example.com" はサブドメインだけに一致させる。単純な endswith("example.com") だと
            # "evil-example.com" にも一致してしまう。先頭のドットまで含めて比べる
            if host.endswith(p_host[1:]):
                return True
        elif host == p_host:
            return True
    return False


def _allow_origin_headers(policy: CorsPolicy, origin: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    if policy.wildcard:
        headers["Access-Control-Allow-Origin"] = "*"
    else:
        headers["Access-Control-Allow-Origin"] = origin  # 許可したオリジンだけをそのまま返す
    if policy.allow_credentials:
        headers["Access-Control-Allow-Credentials"] = "true"
    return headers


def _vary(policy: CorsPolicy) -> dict[str, str]:
    # 応答がリクエストの Origin によって変わるなら、キャッシュにそれを伝える（取り違えを防ぐ）
    return {} if policy.wildcard else {"Vary": "Origin"}


def preflight_response_headers(policy: CorsPolicy, request_headers: Mapping[str, str]) -> dict[str, str]:
    origin = _header(request_headers, "Origin")
    method = (_header(request_headers, "Access-Control-Request-Method") or "").strip()
    requested = [h.lower() for h in _split_list(_header(request_headers, "Access-Control-Request-Headers"))]
    denied = _vary(policy)
    if not origin_allowed(policy, origin) or not method:
        return denied
    methods = set(policy.allowed_methods)
    if method.upper() not in methods and "*" not in methods:
        return denied
    for name in requested:
        if name in policy.allowed_headers:
            continue
        # ヘッダのワイルドカードは Authorization を含まない（Fetch Standard の規定）
        if "*" in policy.allowed_headers and name != "authorization":
            continue
        return denied
    assert origin is not None
    headers = _allow_origin_headers(policy, origin)
    headers["Access-Control-Allow-Methods"] = ", ".join(policy.allowed_methods)
    if requested:
        headers["Access-Control-Allow-Headers"] = ", ".join(requested)
    if policy.max_age is not None:
        headers["Access-Control-Max-Age"] = str(policy.max_age)
    headers.update(_vary(policy))
    return headers


def actual_response_headers(policy: CorsPolicy, request_headers: Mapping[str, str]) -> dict[str, str]:
    origin = _header(request_headers, "Origin")
    if not origin_allowed(policy, origin):
        return _vary(policy)
    assert origin is not None
    headers = _allow_origin_headers(policy, origin)
    if policy.exposed_headers:
        headers["Access-Control-Expose-Headers"] = ", ".join(policy.exposed_headers)
    headers.update(_vary(policy))
    return headers


# ---------------------------------------------------------------------------
# 演習2: ブラウザ側 — 応答を JavaScript に渡してよいか
# ---------------------------------------------------------------------------

def browser_cors_check(response_headers: Mapping[str, str], *, origin: str, credentials: bool) -> bool:
    allow_origin = _header(response_headers, "Access-Control-Allow-Origin")
    if allow_origin is None:
        return False
    allow_origin = allow_origin.strip()
    if allow_origin == "*":
        return not credentials  # 資格情報付きのリクエストに「*」は通用しない
    if allow_origin != origin:
        return False  # 大文字小文字も含めて完全一致
    if credentials:
        return (_header(response_headers, "Access-Control-Allow-Credentials") or "").strip() == "true"
    return True


def browser_preflight_check(
    response_headers: Mapping[str, str],
    *,
    origin: str,
    method: str,
    request_headers: Sequence[str],
    credentials: bool,
) -> bool:
    if not browser_cors_check(response_headers, origin=origin, credentials=credentials):
        return False
    methods = {m.upper() for m in _split_list(_header(response_headers, "Access-Control-Allow-Methods"))}
    names = {h.lower() for h in _split_list(_header(response_headers, "Access-Control-Allow-Headers"))}
    method = method.upper()
    if method not in SAFELISTED_METHODS and method not in methods and (credentials or "*" not in methods):
        return False
    for name in (h.lower() for h in request_headers):
        if name in names:
            continue
        if name == "authorization":
            return False  # ワイルドカードでは許可されない
        if credentials or "*" not in names:
            return False
    return True
