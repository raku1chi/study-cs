"""5.3 DNS・HTTP・TLS — 演習（http11）: HTTP/1.1 のリクエストのパースとレスポンスの組み立て

HTTP/1.1 のメッセージは「テキストの行」と「本文」でできていて、一見簡単に読めそうです。
しかし、区切り方（本文の長さの決め方）の解釈がサーバーとプロキシで食い違うと、
リクエストスマグリングのような深刻な脆弱性になります。この演習では、RFC 9112 に沿った
「厳格な」パーサを作ります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.3
    python3 tools/check.py -v 5.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_http11

制約:
    - http.client・http.server・email などの既存の HTTP パーサは使わないでください
      （テストでは答え合わせのために http.client を使っています）。
    - 数値の変換に int() を使うときは、先に正規表現などで「数字だけ」であることを確かめてください。
      int() は " 5"・"+5"・"5_0"・"0x10"（base=16 のとき）なども受け付けてしまいます。

HTTP/1.1 のリクエストの形（行の区切りは CRLF = "\\r\\n"）:

    POST /submit?x=1 HTTP/1.1          ← リクエスト行: メソッド SP ターゲット SP バージョン
    Host: example.com                  ← ヘッダ（フィールド）: 名前 ":" 空白 値
    Content-Length: 11
                                       ← 空行（ヘッダの終わり）
    hello world                        ← 本文（長さは Content-Length か chunked で決まる）
"""
from __future__ import annotations

import re  # noqa: F401
from dataclasses import dataclass, field
from http import HTTPStatus  # noqa: F401  理由句（"Not Found" など）の取得に使えます
from typing import Iterable, Iterator

# token（RFC 9110 5.6.2）: メソッド名・ヘッダ名に使える文字だけからなる 1 文字以上の列
TOKEN_RE = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")

DEFAULT_MAX_HEADER_BYTES = 16 * 1024
DEFAULT_MAX_HEADERS = 100
DEFAULT_MAX_BODY_BYTES = 1024 * 1024


class HTTPParseError(ValueError):
    """不正なリクエスト（実装済み）。status は返すべきステータスコード（400, 413, 431, 501, 505）。"""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"{status} {message}")
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# 演習1（★★☆）: ヘッダの集まり
# ---------------------------------------------------------------------------

class Headers:
    """HTTP のヘッダの集まり。

    - 名前の比較は大文字小文字を区別しない（"Content-Type" と "content-type" は同じ）。
    - 同じ名前のヘッダが複数あってもよい（Set-Cookie などは複数行になる）。
    - 追加した順序と、元の名前の書き方を保つ。

    >>> h = Headers([("Accept", "text/html")])
    >>> h.add("accept", "image/png")
    >>> h.get("ACCEPT"), h.get_all("Accept"), "accept" in h, len(h)
    ('text/html', ['text/html', 'image/png'], True, 2)
    """

    def __init__(self, items: Iterable[tuple[str, str]] = ()) -> None:
        raise NotImplementedError("演習1: Headers.__init__ を実装してください")

    def add(self, name: str, value: str) -> None:
        """末尾に 1 つ追加する。"""
        raise NotImplementedError("演習1: Headers.add を実装してください")

    def get(self, name: str, default: str | None = None) -> str | None:
        """最初に見つかった値を返す。なければ default。"""
        raise NotImplementedError("演習1: Headers.get を実装してください")

    def get_all(self, name: str) -> list[str]:
        """その名前のすべての値を、追加した順に返す。なければ []。"""
        raise NotImplementedError("演習1: Headers.get_all を実装してください")

    def __contains__(self, name: object) -> bool:
        raise NotImplementedError("演習1: Headers.__contains__ を実装してください")

    def items(self) -> list[tuple[str, str]]:
        """(元の名前, 値) のリストを追加した順に返す。"""
        raise NotImplementedError("演習1: Headers.items を実装してください")

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self.items())

    def __len__(self) -> int:
        raise NotImplementedError("演習1: Headers.__len__ を実装してください")


@dataclass
class Request:
    """パースしたリクエスト（path と query は実装済み）。"""

    method: str
    target: str  # リクエストターゲット（例: "/index.html?q=1"）
    version: str  # "HTTP/1.1" または "HTTP/1.0"
    headers: Headers
    body: bytes = b""
    trailers: Headers = field(default_factory=Headers)  # chunked の最後に付くトレーラ

    @property
    def path(self) -> str:
        """ターゲットの "?" より前。"""
        return self.target.split("?", 1)[0]

    @property
    def query(self) -> str:
        """ターゲットの "?" より後（なければ ""）。"""
        return self.target.split("?", 1)[1] if "?" in self.target else ""

    @property
    def keep_alive(self) -> bool:
        """この応答の後も接続を使い続けるか。

        - Connection ヘッダの値をカンマで区切ったトークン（大文字小文字を区別しない）を見る。
        - HTTP/1.1: "close" が含まれていなければ True（既定で持続接続）。
        - HTTP/1.0: "keep-alive" が含まれていれば True（既定では閉じる）。
        """
        raise NotImplementedError("演習1: Request.keep_alive を実装してください")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: リクエストのパース
# ---------------------------------------------------------------------------

def parse_request(
    data: bytes,
    *,
    max_header_bytes: int = DEFAULT_MAX_HEADER_BYTES,
    max_headers: int = DEFAULT_MAX_HEADERS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
) -> tuple[Request, int] | None:
    """バイト列の先頭から HTTP/1.1 のリクエストを 1 つ読み取る。

    戻り値:
        - 完成したリクエストがあれば (Request, 消費したバイト数)。data の残り（消費したバイト数
          より後ろ）は、同じ接続で続けて送られた次のリクエスト（パイプライン化）の先頭。
        - まだ途中なら None（呼び出し側はデータを追加して、もう一度呼ぶ）。
        - 不正なら HTTPParseError（status に返すべきステータスコード）。

    行と区切り:
        - 行の区切りは CRLF。単独の LF や、LF が続かない CR があれば 400（途中のデータでも、
          その時点で分かるなら None ではなく 400 にする）。
        - リクエスト行の前の空行（CRLF）はいくつか無視してよい（RFC 9112 2.2）。
        - ヘッダの終わりは空行（"\\r\\n\\r\\n"）。そこまでのバイト数（リクエスト行と空行を含む）が
          max_header_bytes を超えたら 431。まだ空行が来ていないのに超えた場合も 431。
        - ヘッダ部分は ISO-8859-1（latin-1）として文字列にしてよい。

    リクエスト行（400: 形式が不正、505: 対応していないバージョン）:
        - ちょうど 1 つの空白で区切られた 3 つの部分: メソッド・ターゲット・バージョン。
        - メソッドは token。ターゲットは空白・制御文字を含まない 1 文字以上。
        - バージョンは "HTTP/数字.数字" の形でなければ 400。"HTTP/1.0" と "HTTP/1.1" 以外は 505。

    ヘッダ（400、数の上限を超えたら 431）:
        - 「名前:値」。名前は token（名前と ":" の間の空白は 400）。
        - 値の前後の空白（SP と HTAB）は取り除く。値に HTAB 以外の制御文字があれば 400。
        - 行頭が空白の行（古い折り返し形式 obs-fold）は 400。":" のない行は 400。
        - ヘッダの数が max_headers を超えたら 431。
        - HTTP/1.1 では Host ヘッダがちょうど 1 つ必要（0 個・2 個以上は 400）。
          HTTP/1.0 では Host がなくてもよい（2 個以上は 400）。

    本文の長さ（RFC 9112 6 節。リクエストスマグリングを防ぐため厳格に）:
        - Transfer-Encoding と Content-Length の両方があれば 400。
        - Transfer-Encoding があれば: 値をカンマで区切った転送コーディングの並び（大文字小文字は
          区別しない）の最後が "chunked" でなければ 400。"chunked" 以外のコーディングも含むなら
          501（この演習では chunked だけに対応する）。HTTP/1.0 のリクエストなら 400。
        - Content-Length があれば: 値（カンマで区切られた複数の値や、複数のヘッダ行でもよい）は
          すべて数字だけで、すべて同じ値でなければ 400。max_body_bytes を超えれば 413。
        - どちらもなければ本文は空。

    chunked の形式（各行の区切りは CRLF）:
        チャンクサイズ（16 進数 1〜16 桁）[;拡張] CRLF
        データ（チャンクサイズ バイト）CRLF
        ...
        0 CRLF
        トレーラ（ヘッダと同じ形式のフィールド 0 個以上）
        CRLF
        - 「;」以降の拡張は無視する。サイズが 16 進数でなければ 400。データの後ろが CRLF でなければ 400。
        - 本文の合計が max_body_bytes を超えたら 413。トレーラは Request.trailers に入れる。

    >>> req, n = parse_request(b"GET /a?b=1 HTTP/1.1\\r\\nHost: example.com\\r\\n\\r\\n")
    >>> (req.method, req.path, req.query, req.headers.get("host"), n)
    ('GET', '/a', 'b=1', 'example.com', 42)
    >>> parse_request(b"GET /a HTTP/1.1\\r\\nHost: exa") is None
    True

    ヒント: まず "\\r\\n\\r\\n" を探してヘッダ部分を切り出し、行に分けて処理する。
    本文の長さが決まったら、data が足りているかを確かめる。
    """
    raise NotImplementedError("演習1: parse_request を実装してください")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: レスポンスの組み立て
# ---------------------------------------------------------------------------

def serialize_response(
    status: int,
    headers: Iterable[tuple[str, str]] = (),
    body: bytes = b"",
    *,
    reason: str | None = None,
    head_request: bool = False,
) -> bytes:
    """HTTP/1.1 のレスポンスのバイト列を作る。

    - ステータス行は "HTTP/1.1 {status} {理由句}\\r\\n"。reason を省略したら標準の理由句
      （http.HTTPStatus(status).phrase。未知のコードなら ""）を使う。理由句が空でも、
      ステータスコードの後ろの空白 1 つは省略しない。
    - status が 100〜599 の範囲外なら ValueError。
    - ヘッダ名は token、値は改行などの制御文字（HTAB 以外）を含んではいけない。違反したら
      ValueError（値に CRLF を許すと、攻撃者がヘッダや本文を差し込める「レスポンス分割」になる）。
      理由句に CR・LF があっても ValueError。
    - 1xx・204・304 には本文を付けられない（body があれば ValueError）。Content-Length も付けない。
    - それ以外で、headers に Content-Length も Transfer-Encoding もなければ、
      Content-Length: len(body) を headers の後ろに追加する。
    - head_request=True（HEAD への応答）なら、ヘッダは GET と同じもの（Content-Length を含む）
      を返し、本文は付けない。

    >>> serialize_response(200, [("Content-Type", "text/plain")], b"hi")
    b'HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\nContent-Length: 2\\r\\n\\r\\nhi'
    """
    raise NotImplementedError("演習1: serialize_response を実装してください")
