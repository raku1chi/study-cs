"""5.3 DNS・HTTP・TLS — 演習（http_cache）: HTTP キャッシュの鮮度の判定

キャッシュ（ブラウザや CDN）は、保存した応答を「そのまま使ってよいか」「オリジンに確認
（再検証）すべきか」を、応答のヘッダと時刻から判断します。この演習では、その計算を
RFC 9111（HTTP Caching）の 4.2 節に沿って実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.3
    python3 tools/check.py -v 5.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_http_cache

約束:
    - 時刻はすべて UNIX 時間（秒、float）で引数として受け取る。関数の中で現在時刻を取得しない。
    - headers は {ヘッダ名: 値} の辞書。ヘッダ名は大文字小文字を区別せずに探すこと。
    - shared=True は共有キャッシュ（CDN やプロキシ）、False はプライベートキャッシュ（ブラウザ）。
"""
from __future__ import annotations

import email.utils  # noqa: F401  HTTP の日時の解析に使えます
from datetime import timezone  # noqa: F401
from typing import Mapping


# ---------------------------------------------------------------------------
# 演習4（★★☆）: ヘッダの解析
# ---------------------------------------------------------------------------

def parse_cache_control(value: str | None) -> dict[str, str | None]:
    """Cache-Control ヘッダの値を {ディレクティブ名: 引数} の辞書にする。

    - ディレクティブはカンマで区切られる。名前は小文字にそろえる（大文字小文字を区別しない）。
    - 引数のないディレクティブの値は None。"max-age=60" の値は "60"（文字列のまま）。
    - 引数は token か quoted-string（"..."）。quoted-string の中のカンマは区切りではなく、
      \\ は次の 1 文字をそのまま表す。引用符は取り除く。
    - 空の要素は無視する。同じディレクティブが複数あれば最初のものを使う。
    - value が None や "" なら {}。

    >>> parse_cache_control('max-age=60, Public, private="Set-Cookie, X-Token"')
    {'max-age': '60', 'public': None, 'private': 'Set-Cookie, X-Token'}
    """
    raise NotImplementedError("演習4: parse_cache_control を実装してください")


def parse_http_date(value: str | None) -> float | None:
    """HTTP の日時を UNIX 時間に変換する。不正なら None。

    RFC 9110 は、受信側に次の 3 つの形式をすべて受け付けるよう求めている:
        "Sun, 06 Nov 1994 08:49:37 GMT"     IMF-fixdate（送るときはこれを使う）
        "Sunday, 06-Nov-94 08:49:37 GMT"    廃止された RFC 850 形式
        "Sun Nov  6 08:49:37 1994"          C の asctime() 形式

    >>> parse_http_date("Sun, 06 Nov 1994 08:49:37 GMT")
    784111777.0

    ヒント: email.utils.parsedate_to_datetime はこの 3 つを解釈できる（不正なら例外を送出する）。
    ただし asctime 形式にはタイムゾーンがないため、タイムゾーンなし（naive）の datetime が返り、
    そのまま .timestamp() を呼ぶと実行環境のローカル時刻として解釈されてしまう。HTTP の日時は
    常に UTC なので、tzinfo が None なら tzinfo=timezone.utc を設定すること。
    """
    raise NotImplementedError("演習4: parse_http_date を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 鮮度の寿命と経過時間
# ---------------------------------------------------------------------------

def freshness_lifetime(headers: Mapping[str, str], *, shared: bool, response_time: float) -> float:
    """応答の「鮮度の寿命」（新鮮とみなせる秒数）を返す（RFC 9111 4.2.1）。

    次の順に、最初に当てはまるものを使う:
        1. 共有キャッシュ（shared=True）で Cache-Control に s-maxage があれば、その値。
        2. Cache-Control に max-age があれば、その値。
           1・2 の値が数字だけでない（負号・小数・空など）なら 0（期限切れ扱い）。
           非常に大きな値は 2**31 で頭打ちにする。
        3. Expires があれば「Expires − Date」（負なら 0）。Date がなければ response_time を Date と
           みなす。Expires が不正な日時（"0" など）なら 0（「すでに期限切れ」を意味する）。
        4. Last-Modified があり Date より前なら、経験的に「(Date − Last-Modified) × 0.1」
           （簡略化のため、ステータスコードは 200 とみなす）。
        5. どれもなければ 0。

    >>> freshness_lifetime({"Cache-Control": "max-age=600, s-maxage=60"}, shared=True, response_time=0)
    60.0
    """
    raise NotImplementedError("演習4: freshness_lifetime を実装してください")


def current_age(headers: Mapping[str, str], *, request_time: float, response_time: float, now: float) -> float:
    """保存した応答の「現在の経過時間」を返す（RFC 9111 4.2.3）。

    request_time はリクエストを送った時刻、response_time は応答を受け取った時刻、now は現在時刻。

        age_value = Age ヘッダの値（数字だけでなければ・なければ 0）
        date_value = Date ヘッダの時刻（不正・なければ response_time）
        apparent_age = max(0, response_time - date_value)
        response_delay = response_time - request_time
        corrected_age_value = age_value + response_delay
        corrected_initial_age = max(apparent_age, corrected_age_value)
        resident_time = now - response_time
        current_age = corrected_initial_age + resident_time

    Date はオリジンの時計、response_time は自分の時計の値なので、両者がずれていても
    大きく間違えないように、2 つの見積もりの大きい方（安全側）を採っています。
    """
    raise NotImplementedError("演習4: current_age を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: キャッシュの判断
# ---------------------------------------------------------------------------

def cache_status(
    headers: Mapping[str, str], *, request_time: float, response_time: float, now: float, shared: bool
) -> str:
    """保存した応答をどう扱うかを、次の 4 つのいずれかで返す。

        "no-store"         保存してはいけない
        "fresh"            新鮮。オリジンに問い合わせずにそのまま返してよい
        "stale"            期限切れ。通常は再検証（条件付きリクエスト）が必要だが、オリジンに
                           接続できない場合などには、古い応答を返すことが許されうる
        "must-revalidate"  使う前に必ずオリジンで検証しなければならない（検証できなければ返せない）

    判断の順序:
        1. Cache-Control に no-store があれば "no-store"。共有キャッシュで private があれば "no-store"。
        2. no-cache があれば "must-revalidate"（no-cache は「保存するな」ではなく「毎回確認せよ」）。
        3. freshness_lifetime > current_age なら "fresh"（等しいときは新鮮ではない）。
        4. 期限切れで、must-revalidate があれば "must-revalidate"。共有キャッシュでは
           proxy-revalidate または s-maxage があっても "must-revalidate"（s-maxage は共有キャッシュに
           対して proxy-revalidate の意味も持つ）。
        5. それ以外は "stale"。

    簡略化: private="..." や no-cache="..." のようにフィールド名を指定した形も、指定のない形と
    同じに扱う（より安全側の解釈）。
    """
    raise NotImplementedError("演習4: cache_status を実装してください")
