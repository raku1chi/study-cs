"""5.3 DNS・HTTP・TLS — 解答例（http11）

演習の仕様は exercises/http11.py の docstring を参照してください。
RFC 9110（HTTP のセマンティクス）と RFC 9112（HTTP/1.1）に沿った、厳格なパーサです。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Iterable, Iterator

# token = 1*tchar（RFC 9110 5.6.2）。メソッド名・ヘッダ名に使える文字
TOKEN_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
VERSION_RE = re.compile(r"HTTP/([0-9])\.([0-9])")
TARGET_RE = re.compile(r"[\x21-\x7e]+")  # 空白・制御文字を含まない表示可能な ASCII
DIGITS_RE = re.compile(r"[0-9]+")
HEX_RE = re.compile(r"[0-9A-Fa-f]{1,16}")
# フィールド値に許されない文字（HTAB 以外の制御文字と DEL）
BAD_VALUE_CHAR_RE = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")

DEFAULT_MAX_HEADER_BYTES = 16 * 1024
DEFAULT_MAX_HEADERS = 100
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
MAX_CHUNK_LINE = 1024


class HTTPParseError(ValueError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status} {message}")
        self.status = status
        self.message = message


class Headers:
    def __init__(self, items: Iterable[tuple[str, str]] = ()) -> None:
        self._items: list[tuple[str, str]] = []
        for name, value in items:
            self.add(name, value)

    def add(self, name: str, value: str) -> None:
        self._items.append((name, value))

    def get(self, name: str, default: str | None = None) -> str | None:
        key = name.lower()
        for n, v in self._items:
            if n.lower() == key:
                return v
        return default

    def get_all(self, name: str) -> list[str]:
        key = name.lower()
        return [v for n, v in self._items if n.lower() == key]

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and self.get(name) is not None

    def items(self) -> list[tuple[str, str]]:
        return list(self._items)

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(list(self._items))

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Headers({self._items!r})"


@dataclass
class Request:
    method: str
    target: str
    version: str
    headers: Headers
    body: bytes = b""
    trailers: Headers = field(default_factory=Headers)

    @property
    def path(self) -> str:
        return self.target.split("?", 1)[0]

    @property
    def query(self) -> str:
        return self.target.split("?", 1)[1] if "?" in self.target else ""

    @property
    def keep_alive(self) -> bool:
        tokens = {t.strip().lower() for v in self.headers.get_all("Connection") for t in v.split(",")}
        if self.version == "HTTP/1.0":
            return "keep-alive" in tokens  # HTTP/1.0 は明示されたときだけ持続接続
        return "close" not in tokens  # HTTP/1.1 は既定で持続接続


# ---------------------------------------------------------------------------
# 演習1: リクエストのパース
# ---------------------------------------------------------------------------

def _check_line_endings(head: bytes, complete: bool) -> None:
    """CR と LF は CRLF の組でしか現れてはいけない（単独の LF・CR は拒否する）。"""
    for i, b in enumerate(head):
        if b == 0x0A and (i == 0 or head[i - 1] != 0x0D):
            raise HTTPParseError(400, "CRLF ではない改行（単独の LF）があります")
        if b == 0x0D and i + 1 < len(head) and head[i + 1] != 0x0A:
            raise HTTPParseError(400, "単独の CR があります")
    if complete and head.endswith(b"\r"):
        raise HTTPParseError(400, "単独の CR があります")


def _parse_field_line(line: str, headers: Headers, max_headers: int) -> None:
    if line[:1] in (" ", "\t"):
        # 行頭の空白は古い「折り返し（obs-fold）」。RFC 9112 はサーバーに 400 か空白への置換を求める
        raise HTTPParseError(400, "ヘッダの折り返し（obs-fold）は受け付けません")
    name, colon, value = line.partition(":")
    if not colon:
        raise HTTPParseError(400, f"ヘッダに「:」がありません: {line!r}")
    if not TOKEN_RE.fullmatch(name):
        # 名前と「:」の間の空白もここで拒否される（リクエストスマグリングの温床になるため）
        raise HTTPParseError(400, f"不正なヘッダ名です: {name!r}")
    value = value.strip(" \t")
    if BAD_VALUE_CHAR_RE.search(value):
        raise HTTPParseError(400, f"ヘッダ値に制御文字があります: {name}")
    if len(headers) >= max_headers:
        raise HTTPParseError(431, "ヘッダの数が多すぎます")
    headers.add(name, value)


def _parse_head(head: str, max_headers: int) -> tuple[str, str, str, Headers]:
    lines = head.split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) != 3 or not all(parts):
        raise HTTPParseError(400, f"リクエスト行が不正です: {lines[0]!r}")
    method, target, version = parts
    if not TOKEN_RE.fullmatch(method):
        raise HTTPParseError(400, f"不正なメソッドです: {method!r}")
    if not TARGET_RE.fullmatch(target):
        raise HTTPParseError(400, f"不正なリクエストターゲットです: {target!r}")
    m = VERSION_RE.fullmatch(version)
    if not m:
        raise HTTPParseError(400, f"不正なバージョン表記です: {version!r}")
    if version not in ("HTTP/1.0", "HTTP/1.1"):
        raise HTTPParseError(505, f"対応していないバージョンです: {version}")
    headers = Headers()
    for line in lines[1:]:
        _parse_field_line(line, headers, max_headers)
    return method, target, version, headers


def _content_length(values: list[str], max_body: int) -> int:
    lengths = set()
    for v in values:
        for item in v.split(","):
            item = item.strip(" \t")
            # int() は " 5" "+5" "5_0" なども受け付けてしまうので、先に厳密に検査する
            if not DIGITS_RE.fullmatch(item):
                raise HTTPParseError(400, f"不正な Content-Length です: {v!r}")
            lengths.add(int(item))
    if len(lengths) != 1:
        raise HTTPParseError(400, f"矛盾する Content-Length があります: {values!r}")
    length = lengths.pop()
    if length > max_body:
        raise HTTPParseError(413, f"本文が大きすぎます: {length} > {max_body}")
    return length


def _decode_chunked(
    data: bytes, pos: int, max_body: int, max_headers: int
) -> tuple[bytes, Headers, int] | None:
    body = bytearray()
    while True:
        eol = data.find(b"\r\n", pos)
        if eol < 0:
            if len(data) - pos > MAX_CHUNK_LINE:
                raise HTTPParseError(400, "チャンクサイズの行が長すぎます")
            return None
        line = data[pos:eol].decode("latin-1")
        size_text = line.split(";", 1)[0].rstrip(" \t")  # 「;」以降はチャンク拡張（無視する）
        if not HEX_RE.fullmatch(size_text):
            raise HTTPParseError(400, f"不正なチャンクサイズです: {line!r}")
        size = int(size_text, 16)
        pos = eol + 2
        if size == 0:
            break
        if len(body) + size > max_body:
            raise HTTPParseError(413, "本文が大きすぎます")
        if len(data) < pos + size + 2:
            return None
        if data[pos + size : pos + size + 2] != b"\r\n":
            raise HTTPParseError(400, "チャンクのデータの後ろに CRLF がありません")
        body += data[pos : pos + size]
        pos += size + 2
    # トレーラ部: 空行が来るまでヘッダと同じ形式のフィールドが続く
    trailers = Headers()
    while True:
        eol = data.find(b"\r\n", pos)
        if eol < 0:
            if len(data) - pos > DEFAULT_MAX_HEADER_BYTES:
                raise HTTPParseError(431, "トレーラが大きすぎます")
            return None
        line = data[pos:eol]
        pos = eol + 2
        if not line:
            return bytes(body), trailers, pos
        if b"\r" in line or b"\n" in line:
            raise HTTPParseError(400, "トレーラに不正な改行があります")
        _parse_field_line(line.decode("latin-1"), trailers, max_headers)


def parse_request(
    data: bytes,
    *,
    max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES,
    max_headers: int = DEFAULT_MAX_HEADERS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> tuple[Request, int] | None:
    # リクエスト行の前の空行は無視する（RFC 9112 2.2。POST の本文の後に余分な CRLF を送る古い実装への配慮）
    skip = 0
    while data.startswith(b"\r\n", skip):
        skip += 2
        if skip > max_header_bytes:
            raise HTTPParseError(400, "リクエスト行の前の空行が多すぎます")
    end = data.find(b"\r\n\r\n", skip)
    head_bytes = data[skip:] if end < 0 else data[skip:end]
    # まだ途中でも、明らかに不正な改行はすぐに拒否する
    _check_line_endings(head_bytes[: max_header_bytes + 1], complete=end >= 0)
    if end < 0:
        if len(head_bytes) > max_header_bytes:
            raise HTTPParseError(431, "ヘッダが大きすぎます")
        return None  # ヘッダの終わり（空行）がまだ届いていない
    if len(head_bytes) + 4 > max_header_bytes:
        raise HTTPParseError(431, "ヘッダが大きすぎます")

    # ヘッダは ASCII が基本だが、歴史的に ISO-8859-1 として扱われてきた
    method, target, version, headers = _parse_head(head_bytes.decode("latin-1"), max_headers)

    hosts = headers.get_all("Host")
    if len(hosts) > 1 or (version == "HTTP/1.1" and len(hosts) != 1):
        raise HTTPParseError(400, "HTTP/1.1 では Host ヘッダがちょうど 1 つ必要です")

    start = end + 4
    te_values = headers.get_all("Transfer-Encoding")
    cl_values = headers.get_all("Content-Length")
    trailers = Headers()
    if te_values:
        if cl_values:
            # 両方あると、経路上の機器ごとに本文の長さの解釈が分かれうる（リクエストスマグリング）
            raise HTTPParseError(400, "Transfer-Encoding と Content-Length が両方あります")
        if version == "HTTP/1.0":
            raise HTTPParseError(400, "HTTP/1.0 で Transfer-Encoding は使えません")
        codings = [c.strip(" \t").lower() for v in te_values for c in v.split(",") if c.strip(" \t")]
        if not codings or codings[-1] != "chunked":
            raise HTTPParseError(400, "chunked が最後の転送コーディングではありません")
        if len(codings) > 1:
            raise HTTPParseError(501, f"対応していない転送コーディングです: {codings}")
        decoded = _decode_chunked(data, start, max_body_bytes, max_headers)
        if decoded is None:
            return None
        body, trailers, consumed = decoded
    elif cl_values:
        length = _content_length(cl_values, max_body_bytes)
        if len(data) < start + length:
            return None
        body, consumed = data[start : start + length], start + length
    else:
        body, consumed = b"", start  # リクエストで長さの指定がなければ本文はない

    return Request(method, target, version, headers, bytes(body), trailers), consumed


# ---------------------------------------------------------------------------
# 演習1: レスポンスの組み立て
# ---------------------------------------------------------------------------

def serialize_response(
    status: int,
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
    *,
    reason: str | None = None,
    head_request: bool = False,
) -> bytes:
    if not 100 <= status <= 599:
        raise ValueError(f"ステータスコードは 100〜599 です: {status}")
    if reason is None:
        try:
            reason = HTTPStatus(status).phrase
        except ValueError:
            reason = ""
    if "\r" in reason or "\n" in reason:
        raise ValueError("理由句に改行は使えません")
    items = list(headers)
    for name, value in items:
        if not TOKEN_RE.fullmatch(name):
            raise ValueError(f"不正なヘッダ名です: {name!r}")
        if BAD_VALUE_CHAR_RE.search(value):
            # CR・LF を許すと、攻撃者がヘッダや本文を差し込めてしまう（レスポンス分割）
            raise ValueError(f"ヘッダ値に改行・制御文字があります: {name}")
    names = {name.lower() for name, _ in items}
    no_body = status < 200 or status in (204, 304)
    if no_body:
        if body:
            raise ValueError(f"ステータス {status} のレスポンスに本文は付けられません")
    elif "content-length" not in names and "transfer-encoding" not in names:
        items.append(("Content-Length", str(len(body))))
    lines = [f"HTTP/1.1 {status} {reason}"] + [f"{name}: {value}" for name, value in items]
    head = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
    # HEAD への応答では、GET と同じヘッダ（Content-Length を含む）を返し、本文は送らない
    return head if head_request else head + bytes(body)
