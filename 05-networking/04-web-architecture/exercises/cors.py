"""5.4 Webの仕組みとネットワーク構成 — 演習（cors）: CORS のサーバー側とブラウザ側の判定

ブラウザは、ある Web ページ（オリジン A）の JavaScript が、別のオリジン B の応答を読むことを
原則として禁止しています（同一オリジンポリシー）。B のサーバーが CORS のヘッダで許可したときだけ、
ブラウザは応答を JavaScript に渡します。この演習では、

    - サーバー側: 設定（CorsPolicy）に従って、返すべき CORS のヘッダを決める
    - ブラウザ側: 受け取ったヘッダから、応答を JavaScript に渡してよいかを判定する

の両方を実装します。ブラウザ側の規則は WHATWG の Fetch Standard（「CORS check」と
「CORS-preflight fetch」）を簡略化したものです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.4
    python3 tools/check.py -v 5.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_cors

用語:
    - オリジン: "スキーム://ホスト[:ポート]"（例: "https://app.example.com"）。ブラウザが送る Origin
      ヘッダは小文字で、既定のポート（http の 80、https の 443）は省略される。サンドボックス化された
      iframe などからのリクエストでは "null" になる。
    - プリフライト: PUT などのメソッドや独自のヘッダを使うリクエストの前に、ブラウザが自動で送る
      OPTIONS リクエスト。Access-Control-Request-Method と Access-Control-Request-Headers で、
      これから送るリクエストの内容を伝える。
    - 資格情報（credentials）: Cookie や HTTP 認証の情報。JavaScript で credentials: "include" を
      指定したリクエストでは、サーバーはオリジンを「*」ではなく具体的に返し、
      Access-Control-Allow-Credentials: true も返さなければならない。
"""
from __future__ import annotations

import re  # noqa: F401
from dataclasses import dataclass, field
from typing import Mapping, Sequence

SAFELISTED_METHODS = {"GET", "HEAD", "POST"}  # 許可がなくても使えるメソッド
DEFAULT_PORTS = {"http": 80, "https": 443}


@dataclass
class CorsPolicy:
    """サーバーの CORS の設定。

    allowed_origins の各要素は次のいずれか:
        "*"                          すべてのオリジン（資格情報付きとは併用できない）
        "https://app.example.com"    完全一致（ポートを書くなら "http://localhost:3000"）
        "https://*.example.com"      サブドメイン（1 段以上）。example.com 自身は含まない
    allowed_methods はメソッド名（大文字にそろえて保持する）。allowed_headers はヘッダ名（小文字に
    そろえて保持する）。どちらも "*" を含めてよいが、資格情報付きとは併用できない。

    __post_init__ で次を検査し、違反なら ValueError:
        - allowed_origins の要素が "*" か、"http(s)://ホスト[:ポート]"（ホストの先頭に "*." を
          付けてもよい。ホストは小文字の英数字・ハイフン・ドット）の形であること。"null" や、
          パスの付いたもの（末尾の "/" を含む）は不可
        - allow_credentials=True なのに allowed_origins・allowed_headers・allowed_methods に "*" がある
    """

    allowed_origins: list[str]
    allowed_methods: list[str] = field(default_factory=lambda: ["GET", "HEAD", "POST"])
    allowed_headers: list[str] = field(default_factory=list)
    exposed_headers: list[str] = field(default_factory=list)
    allow_credentials: bool = False
    max_age: int | None = None

    def __post_init__(self) -> None:
        raise NotImplementedError("演習2: CorsPolicy.__post_init__ を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: サーバー側
# ---------------------------------------------------------------------------

def origin_allowed(policy: CorsPolicy, origin: str | None) -> bool:
    """origin（リクエストの Origin ヘッダの値）が、ポリシーで許可されているか。

    - origin が None なら False。ポリシーに "*" があれば常に True（"null" も含む）。
    - そうでなければ、origin を "http(s)://ホスト[:ポート]" として解釈し（できなければ False）、
      スキームとポート（省略時は既定のポート）が一致し、ホストが完全一致するか、
      "*.example.com" の形なら ".example.com" で終わるときに True。

    注意: 単純に host.endswith("example.com") とすると、"evil-example.com" も許可してしまう。

    >>> p = CorsPolicy(["https://*.example.com"])
    >>> origin_allowed(p, "https://app.example.com"), origin_allowed(p, "https://evil-example.com")
    (True, False)
    """
    raise NotImplementedError("演習2: origin_allowed を実装してください")


def preflight_response_headers(policy: CorsPolicy, request_headers: Mapping[str, str]) -> dict[str, str]:
    """プリフライト（OPTIONS）に対して返す CORS のヘッダを {名前: 値} で返す。

    リクエストのヘッダ名は大文字小文字を区別せずに探すこと。

    許可しない場合（次のいずれか）は、ポリシーに "*" がなければ {"Vary": "Origin"}、あれば {} を返す:
        - Origin が許可されていない、または Access-Control-Request-Method がない
        - 要求されたメソッド（大文字にそろえる）が allowed_methods になく、"*" もない
        - Access-Control-Request-Headers（カンマ区切り。小文字にそろえる）のどれかが
          allowed_headers になく、"*" でも許可されない（"*" は "authorization" を含まない）

    許可する場合は次を返す:
        "Access-Control-Allow-Origin"       ポリシーに "*" があれば "*"、なければリクエストの Origin
        "Access-Control-Allow-Credentials"  allow_credentials なら "true"（そうでなければ付けない）
        "Access-Control-Allow-Methods"      allowed_methods を ", " で連結
        "Access-Control-Allow-Headers"      要求されたヘッダ（小文字）を ", " で連結（要求がなければ付けない）
        "Access-Control-Max-Age"            max_age が None でなければその値
        "Vary"                              ポリシーに "*" がなければ "Origin"

    Vary: Origin を付けるのは、応答の内容がリクエストの Origin によって変わることを、CDN などの
    キャッシュに伝えるため（付けないと、別のオリジン向けの応答がキャッシュから返ってしまう）。
    """
    raise NotImplementedError("演習2: preflight_response_headers を実装してください")


def actual_response_headers(policy: CorsPolicy, request_headers: Mapping[str, str]) -> dict[str, str]:
    """プリフライト以外の（実際の）リクエストへの応答に付ける CORS のヘッダを返す。

    - Origin が許可されていなければ、ポリシーに "*" がなければ {"Vary": "Origin"}、あれば {}。
    - 許可されていれば、Access-Control-Allow-Origin・Access-Control-Allow-Credentials（上と同じ規則）、
      exposed_headers があれば "Access-Control-Expose-Headers"（", " で連結）、そして
      ポリシーに "*" がなければ "Vary": "Origin"。
    """
    raise NotImplementedError("演習2: actual_response_headers を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ブラウザ側
# ---------------------------------------------------------------------------

def browser_cors_check(response_headers: Mapping[str, str], *, origin: str, credentials: bool) -> bool:
    """ブラウザが、応答を JavaScript に渡してよいか（Fetch Standard の CORS check）。

    応答のヘッダ名は大文字小文字を区別せずに探す。値の前後の空白は無視する。
        1. Access-Control-Allow-Origin がなければ False。
        2. その値が "*" なら、credentials が False のときだけ True。
        3. その値が origin と完全に一致しなければ False（大文字小文字も区別する）。
        4. credentials が True なら、Access-Control-Allow-Credentials がちょうど "true" のときだけ True。
        5. それ以外は True。
    """
    raise NotImplementedError("演習2: browser_cors_check を実装してください")


def browser_preflight_check(
    response_headers: Mapping[str, str],
    *,
    origin: str,
    method: str,
    request_headers: Sequence[str],
    credentials: bool,
) -> bool:
    """プリフライトの応答を見て、ブラウザが本来のリクエストを送ってよいか。

        1. browser_cors_check が False なら False。
        2. Access-Control-Allow-Methods（カンマ区切り、大文字にそろえる）について:
           method（大文字にそろえる）が GET・HEAD・POST のいずれかなら許可がなくてよい。
           それ以外は、一覧に含まれるか、credentials が False で一覧に "*" があれば OK。
        3. request_headers（送ろうとしている、許可が必要なヘッダ。小文字にそろえる）のそれぞれが、
           Access-Control-Allow-Headers（カンマ区切り、小文字にそろえる）に含まれるか、
           credentials が False で一覧に "*" があれば OK。ただし "authorization" は "*" では
           許可されず、明示的に含まれている必要がある。
    """
    raise NotImplementedError("演習2: browser_preflight_check を実装してください")
