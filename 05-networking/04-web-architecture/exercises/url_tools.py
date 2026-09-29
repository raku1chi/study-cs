"""5.4 Webの仕組みとネットワーク構成 — 演習（url_tools）: URL の解析・参照の解決・正規化

ブラウザは URL を入力されると、まずそれを部品に分解し、ページの中の相対的なリンクを絶対 URL に
解決し、キャッシュのキーや同一オリジンの判定のために正規化します。この演習では、その規則を
RFC 3986（URI の汎用構文）に沿って実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.4
    python3 tools/check.py -v 5.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_url_tools

制約:
    - urllib.parse は使わないでください（テストでも使っていません）。正規表現（re）は使ってかまいません。

URI の構造（RFC 3986 3 節）:

      https://user:pw@example.com:8443/a/b?x=1#frag
      \\___/   \\_____________________/\\__/ \\_/ \\__/
     scheme          authority        path query fragment
                  （userinfo@host:port）

    どんな文字列も、RFC 3986 付録 B の次の正規表現で 5 つの部分に分解できます（妥当性は別に検査する）:
        ^(([^:/?#]+):)?(//([^/?#]*))?([^?#]*)(\\?([^#]*))?(#(.*))?
         グループ 2 = scheme、4 = authority、5 = path、7 = query、9 = fragment
"""
from __future__ import annotations

import re  # noqa: F401
import string
from dataclasses import dataclass

UNRESERVED = set(string.ascii_letters + string.digits + "-._~")  # 非予約文字
GEN_DELIMS = set(":/?#[]@")
SUB_DELIMS = set("!$&'()*+,;=")
URI_CHARS = UNRESERVED | GEN_DELIMS | SUB_DELIMS | {"%"}  # URI に現れてよい文字
DEFAULT_PORTS = {"http": 80, "https": 443, "ws": 80, "wss": 443, "ftp": 21}


@dataclass
class URL:
    """解析した URI（実装済み）。値のない部分は None（空文字列とは区別する）。

    host が None ならオーソリティ（"//…"）がない。"file:///etc/hosts" のように "//" の後が空なら
    host は ""。port は整数か None（"host:" のような空のポートも None）。
    """

    scheme: str | None = None
    userinfo: str | None = None
    host: str | None = None
    port: int | None = None
    path: str = ""
    query: str | None = None
    fragment: str | None = None

    @property
    def authority(self) -> str | None:
        """"userinfo@host:port" の形に組み立てたもの。host が None なら None。"""
        if self.host is None:
            return None
        userinfo = f"{self.userinfo}@" if self.userinfo is not None else ""
        port = f":{self.port}" if self.port is not None else ""
        return f"{userinfo}{self.host}{port}"

    def __str__(self) -> str:
        """RFC 3986 5.3 の規則で文字列に戻す。"""
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


# ---------------------------------------------------------------------------
# 演習3（★★★）: 解析
# ---------------------------------------------------------------------------

def parse_url(url: str) -> URL:
    """URI（または相対参照）を URL に分解する。大文字小文字の変換などはしない（ありのまま）。

    次の場合は ValueError:
        - URI_CHARS 以外の文字（空白・制御文字・非 ASCII・< > " { } | \\ ^ ` など）がある
        - "%" の後ろに 16 進数が 2 桁続かない
        - scheme が「英字で始まり、英数字と + - . だけからなる」形でない
        - fragment に "#" がある、path・query・fragment に "[" や "]" がある
        - authority の userinfo（最後の "@" より前）に "[" "]" "@" がある
        - host が "[" で始まるのに "]" で閉じていない、"]" の後ろが ":ポート" でない。
          "[" で始まらない host に "[" や "]" がある
        - port が数字だけでない、または 65535 を超える

    >>> parse_url("https://user@Example.COM:8443/a?x=1#top")
    URL(scheme='https', userinfo='user', host='Example.COM', port=8443, path='/a', query='x=1', fragment='top')
    >>> parse_url("../g?y")
    URL(scheme=None, userinfo=None, host=None, port=None, path='../g', query='y', fragment=None)

    ヒント: authority は最後の "@" で userinfo と hostport に分け、hostport は IP リテラル（[…]）を
    先に処理してから ":" でポートを分ける（IPv6 アドレスの中の ":" と区別するため）。
    """
    raise NotImplementedError("演習3: parse_url を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: ドットセグメントの除去と参照の解決
# ---------------------------------------------------------------------------

def remove_dot_segments(path: str) -> str:
    """パスから "." と ".." のセグメントを取り除く（RFC 3986 5.2.4 のアルゴリズム）。

    入力バッファ（最初は path）が空になるまで、次の A〜E の最初に当てはまるものを繰り返す:
        A. 先頭が "../" か "./" なら、それを取り除く
        B. 先頭が "/./" なら "/" に置き換える。全体が "/." なら "/" にする
        C. 先頭が "/../" なら "/" に置き換え、出力バッファの最後のセグメントを（その前の "/" ごと）
           取り除く。全体が "/.." のときも同様（"/" にする）
        D. 全体が "." か ".." なら、空にする
        E. 先頭のセグメント（先頭の "/" があればそれを含め、次の "/" の手前まで）を出力バッファの
           末尾へ移す

    >>> remove_dot_segments("/a/b/c/./../../g")
    '/a/g'
    >>> remove_dot_segments("mid/content=5/../6")
    'mid/6'

    ヒント: 出力バッファを「セグメント（先頭の "/" を含む）のリスト」にすると、C の「最後のセグメントを
    取り除く」が pop() で書ける。
    """
    raise NotImplementedError("演習3: remove_dot_segments を実装してください")


def resolve_reference(base: str, ref: str) -> str:
    """基底 URI base に対して、参照 ref を解決した絶対 URI を返す（RFC 3986 5.2.2、厳格な版）。

    base にスキームがなければ ValueError。R = parse_url(ref)、B = parse_url(base) として:

        if R.scheme がある:
            T = R の scheme・authority・query、T.path = remove_dot_segments(R.path)
        else:
            if R に authority がある（R.host が None でない）:
                T の authority・query = R のもの、T.path = remove_dot_segments(R.path)
            else:
                if R.path == "":
                    T.path = B.path、T.query = R.query があれば R.query、なければ B.query
                else:
                    if R.path が "/" で始まる: T.path = remove_dot_segments(R.path)
                    else: T.path = remove_dot_segments(merge(B, R.path))
                    T.query = R.query
                T の authority = B のもの
            T.scheme = B.scheme
        T.fragment = R.fragment

    merge(B, R.path)（5.2.3）: B に authority があり B.path が "" なら "/" + R.path、
    そうでなければ B.path の最後の "/" まで（"/" を含む）+ R.path。

    >>> resolve_reference("http://a/b/c/d;p?q", "../g")
    'http://a/b/g'
    >>> resolve_reference("http://a/b/c/d;p?q", "?y")
    'http://a/b/c/d;p?y'
    """
    raise NotImplementedError("演習3: resolve_reference を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 正規化
# ---------------------------------------------------------------------------

def normalize_url(url: str) -> str:
    """URI を正規化する（RFC 3986 6.2.2 と 6.2.3）。同じ資源を指す表記の揺れをそろえる。

    - スキームを持たない（相対参照の）ときは ValueError。
    - スキームとホストを小文字にする（パス・クエリ・userinfo は大文字小文字を区別するので変えない）。
    - パーセントエンコーディングの正規化（host・userinfo・path・query・fragment のすべて）:
      非予約文字（英数字と - . _ ~）を表す "%XX" は元の文字に戻す（"%7E" → "~"、"%41" → "A"）。
      それ以外（"/" を表す "%2F" など。戻すと意味が変わる）は、16 進数を大文字にそろえる（"%2f" → "%2F"）。
      ホストは、この後で小文字にする。
    - パスに remove_dot_segments を適用する。
    - スキームの既定のポート（DEFAULT_PORTS）と同じポートは省略する。
    - authority があり、パスが空で、スキームが DEFAULT_PORTS にあるなら、パスを "/" にする。
    - クエリの順序は変えない（パラメータの並べ替えは意味を変えうるので、正規化には含めない）。

    >>> normalize_url("HTTP://www.Example.com:80/a/./b/../%7Euser/%41%2fc")
    'http://www.example.com/a/~user/A%2Fc'
    """
    raise NotImplementedError("演習3: normalize_url を実装してください")
