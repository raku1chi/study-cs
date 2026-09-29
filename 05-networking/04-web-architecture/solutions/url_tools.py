"""5.4 Webの仕組みとネットワーク構成 — 解答例（url_tools）

演習の仕様は exercises/url_tools.py の docstring を参照してください。
RFC 3986（URI の汎用構文）に沿っています。
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass

# RFC 3986 付録 B の正規表現。どんな文字列も 5 つの部分に分解できる（妥当性の検査は別に行う）
URI_RE = re.compile(r"^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\?([^#]*))?(#(.*))?$", re.DOTALL)
SCHEME_RE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*")
UNRESERVED = set(string.ascii_letters + string.digits + "-._~")
GEN_DELIMS = set(":/?#[]@")
SUB_DELIMS = set("!$&'()*+,;=")
URI_CHARS = UNRESERVED | GEN_DELIMS | SUB_DELIMS | {"%"}
HEXDIG = set(string.hexdigits)
DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}


@dataclass
class URL:
    scheme: str | None = None
    userinfo: str | None = None
    host: str | None = None  # None ならオーソリティ（//…）がない
    port: int | None = None
    path: str = ""
    query: str | None = None
    fragment: str | None = None

    @property
    def authority(self) -> str | None:
        if self.host is None:
            return None
        userinfo = f"{self.userinfo}@" if self.userinfo is not None else ""
        port = f":{self.port}" if self.port is not None else ""
        return f"{userinfo}{self.host}{port}"

    def __str__(self) -> str:
        # RFC 3986 5.3 の再構成
        out = ""
        if self.scheme is not None:
            out += self.scheme + ":"
        if self.authority is not None:
            out += "//" + self.authority
        out += self.path
        if self.query is not None:
            out += "?" + self.query
        if self.fragment is not None:
            out += "#" + self.fragment
        return out


def _check_chars(text: str) -> None:
    for i, ch in enumerate(text):
        if ch not in URI_CHARS:  # 空白・制御文字・非 ASCII・< > " { } | \ ^ ` など
            raise ValueError(f"URI に使えない文字です: {ch!r}（位置 {i}）")
        if ch == "%":
            pair = text[i + 1 : i + 3]
            if len(pair) != 2 or not set(pair) <= HEXDIG:
                raise ValueError(f"不正なパーセントエンコーディングです（位置 {i}）")


def parse_url(url: str) -> URL:
    _check_chars(url)
    m = URI_RE.match(url)
    assert m is not None  # この正規表現はどんな文字列にも一致する
    scheme, authority, path, query, fragment = m.group(2), m.group(4), m.group(5), m.group(7), m.group(9)
    if scheme is not None and not SCHEME_RE.fullmatch(scheme):
        raise ValueError(f"不正なスキームです: {scheme!r}")
    if fragment is not None and "#" in fragment:
        raise ValueError("フラグメントに # は使えません")
    for part in (path, query or "", fragment or ""):
        if "[" in part or "]" in part:
            raise ValueError("[ と ] はホストの IP リテラルにしか使えません")
    result = URL(scheme=scheme, path=path, query=query, fragment=fragment)
    if authority is not None:
        userinfo, at, hostport = authority.rpartition("@")
        if at:
            if "[" in userinfo or "]" in userinfo or "@" in userinfo:
                raise ValueError(f"不正なユーザー情報です: {userinfo!r}")
            result.userinfo = userinfo
        if hostport.startswith("["):
            close = hostport.find("]")
            if close < 0:
                raise ValueError(f"IP リテラルの ] がありません: {hostport!r}")
            host, rest = hostport[: close + 1], hostport[close + 1 :]
            if rest and not rest.startswith(":"):
                raise ValueError(f"IP リテラルの後ろが不正です: {hostport!r}")
            port_text = rest[1:] if rest else None
        else:
            host, colon, port_text = hostport.partition(":")
            port_text = port_text if colon else None
            if "[" in host or "]" in host:
                raise ValueError(f"不正なホストです: {host!r}")
        if port_text:  # 空のポート（"host:"）は、ポートの指定なしと同じ
            if not port_text.isdigit() or not port_text.isascii():
                raise ValueError(f"不正なポートです: {port_text!r}")
            port = int(port_text)
            if port > 65535:
                raise ValueError(f"ポートが範囲外です: {port}")
            result.port = port
        result.host = host
    return result


def remove_dot_segments(path: str) -> str:
    # RFC 3986 5.2.4 のアルゴリズムをそのまま書いたもの
    inp = path
    out: list[str] = []  # 出力をセグメント（先頭の "/" を含む）のリストとして持つ
    while inp:
        if inp.startswith("../"):
            inp = inp[3:]  # A
        elif inp.startswith("./"):
            inp = inp[2:]  # A
        elif inp.startswith("/./"):
            inp = inp[2:]  # B: "/./" → "/"
        elif inp == "/.":
            inp = "/"  # B
        elif inp.startswith("/../"):
            inp = inp[3:]  # C: "/../" → "/" にし、出力の最後のセグメントを取り除く
            if out:
                out.pop()
        elif inp == "/..":
            inp = "/"  # C
            if out:
                out.pop()
        elif inp in (".", ".."):
            inp = ""  # D
        else:
            # E: 先頭のセグメント（先頭の "/" があれば含め、次の "/" の手前まで）を出力へ移す
            nxt = inp.find("/", 1 if inp.startswith("/") else 0)
            if nxt < 0:
                nxt = len(inp)
            out.append(inp[:nxt])
            inp = inp[nxt:]
    return "".join(out)


def _merge(base: URL, ref_path: str) -> str:
    # RFC 3986 5.2.3
    if base.host is not None and base.path == "":
        return "/" + ref_path
    return base.path[: base.path.rfind("/") + 1] + ref_path


def resolve_reference(base: str, ref: str) -> str:
    b = parse_url(base)
    if b.scheme is None:
        raise ValueError(f"基底 URI には スキームが必要です: {base!r}")
    r = parse_url(ref)
    t = URL()
    # RFC 3986 5.2.2（厳格な版）
    if r.scheme is not None:
        t.scheme, t.userinfo, t.host, t.port = r.scheme, r.userinfo, r.host, r.port
        t.path, t.query = remove_dot_segments(r.path), r.query
    else:
        if r.host is not None:
            t.userinfo, t.host, t.port = r.userinfo, r.host, r.port
            t.path, t.query = remove_dot_segments(r.path), r.query
        else:
            if r.path == "":
                t.path = b.path
                t.query = r.query if r.query is not None else b.query
            else:
                if r.path.startswith("/"):
                    t.path = remove_dot_segments(r.path)
                else:
                    t.path = remove_dot_segments(_merge(b, r.path))
                t.query = r.query
            t.userinfo, t.host, t.port = b.userinfo, b.host, b.port
        t.scheme = b.scheme
    t.fragment = r.fragment
    return str(t)


def _normalize_percent(text: str) -> str:
    # 非予約文字を表すパーセントエンコーディングは元の文字に戻し、それ以外は 16 進数を大文字にそろえる
    out = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "%":
            byte = int(text[i + 1 : i + 3], 16)
            decoded = chr(byte)
            out.append(decoded if byte < 0x80 and decoded in UNRESERVED else "%" + text[i + 1 : i + 3].upper())
            i += 3
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def normalize_url(url: str) -> str:
    u = parse_url(url)
    if u.scheme is None:
        raise ValueError(f"絶対 URI（スキーム付き）を指定してください: {url!r}")
    u.scheme = u.scheme.lower()  # スキームとホストは大文字小文字を区別しない
    if u.host is not None:
        u.host = _normalize_percent(u.host).lower()
        if u.userinfo is not None:
            u.userinfo = _normalize_percent(u.userinfo)  # ユーザー情報は大文字小文字を区別する
        if u.port is not None and DEFAULT_PORTS.get(u.scheme) == u.port:
            u.port = None  # 既定のポートは省略する
    u.path = remove_dot_segments(_normalize_percent(u.path))
    if u.host is not None and u.path == "" and u.scheme in DEFAULT_PORTS:
        u.path = "/"  # http などでは、空のパスと "/" は同じ意味
    if u.query is not None:
        u.query = _normalize_percent(u.query)
    if u.fragment is not None:
        u.fragment = _normalize_percent(u.fragment)
    return str(u)
