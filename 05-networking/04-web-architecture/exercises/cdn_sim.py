"""5.4 Webの仕組みとネットワーク構成 — 演習（cdn_sim）: CDN のキャッシュのシミュレーション

CDN のエッジサーバーは、オリジン（本来のサーバー）の応答をキャッシュし、利用者の近くで応答します。
この演習では、キャッシュキーの決め方・TTL・Vary・パージ・stale-while-revalidate・多段構成
（オリジンシールド）を持つ、CDN のキャッシュのシミュレータを作ります。ネットワークの通信はせず、
オリジンは関数、時計も関数として外から与えます（テストでは偽物に置き換えます）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.4
    python3 tools/check.py -v 5.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_cdn_sim

使ってよいもの: URL の分解には urllib.parse（urlsplit, parse_qsl, urlencode）を使ってかまいません
（この演習の主題はキャッシュの判断です）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit  # noqa: F401

# RFC 9110 15.1 で「経験的にキャッシュしてよい」とされるステータスコード（実装済み）
CACHEABLE_STATUSES = {200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501}
DEFAULT_IGNORED_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid")


@dataclass
class OriginResponse:
    """オリジン（または上流のキャッシュ）の応答（実装済み）。

    ttl: キャッシュしてよい秒数（Cache-Control の s-maxage にあたる）。0 以下なら保存しない。
    vary: 応答を選ぶのに使ったリクエストヘッダの名前（Vary ヘッダ）。"*" を含むなら再利用できない。
    stale_while_revalidate: 期限切れ後、この秒数の間は古い応答を返しつつ裏で更新してよい。
    age: 上流のキャッシュですでに経過していた秒数（Age ヘッダ）。オリジン自身なら 0。
    """

    status: int = 200
    body: str = ""
    ttl: float = 60.0
    vary: tuple[str, ...] = ()
    stale_while_revalidate: float = 0.0
    age: float = 0.0


@dataclass
class EdgeResponse:
    """エッジが利用者に返す応答（実装済み）。

    cache: "HIT"（キャッシュから新鮮な応答）、"STALE"（期限切れだが stale-while-revalidate の範囲内の
    古い応答）、"MISS"（オリジンから取得）、"BYPASS"（キャッシュを使わなかった）
    age: 応答が生成されてからの経過秒数
    """

    status: int
    body: str
    cache: str
    age: float


Origin = Callable[[str, Mapping[str, str]], OriginResponse]


@dataclass
class CacheStats:
    """統計（実装済み）。hit_ratio は (hits + stale_hits) / requests（リクエストがなければ 0）。"""

    requests: int = 0
    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    bypasses: int = 0
    origin_requests: int = 0

    @property
    def hit_ratio(self) -> float:
        return (self.hits + self.stale_hits) / self.requests if self.requests else 0.0


# ---------------------------------------------------------------------------
# 演習4（★★☆）: CDN のキャッシュ
# ---------------------------------------------------------------------------

class CDNCache:
    """CDN のエッジ（または中間）のキャッシュ。

    cache_key(url):
        "スキーム://ホスト/パス?クエリ" を返す。スキームとホストは小文字、パスが空なら "/"。
        クエリは ignored_query_params に含まれるパラメータ（広告の追跡用など）を取り除き、
        （名前, 値）の順に並べ替えて urlencode した文字列。空なら "?" も付けない。
        例: "https://Example.COM/p?b=2&a=1&utm_source=mail" → "https://example.com/p?a=1&b=2"

    get(url, headers):
        1. stats.requests を 1 増やす。headers（ヘッダ名は大文字小文字を区別しない）に Authorization が
           あれば、キャッシュを一切使わず（読みも書きもせず）オリジンに問い合わせて "BYPASS" で返す
           （stats.bypasses を 1 増やす）。
        2. キャッシュキーに保存された応答（Vary によって 1 つのキーに複数ありうる）のうち、Vary に
           挙がったヘッダの値（下記の正規化をしたもの）が、このリクエストと一致するものを探す。
        3. 見つかれば、経過時間 age = 現在時刻 − 保存時刻 として:
           - age < ttl なら "HIT"（stats.hits）。
           - age < ttl + stale_while_revalidate なら "STALE"（stats.stale_hits）で古い応答を返し、
             その直後にオリジンから取得してキャッシュを更新する（本物の CDN では裏で並行して行う）。
           - それ以外は期限切れとして取り除き、4 へ。
        4. 見つからなければ "MISS"（stats.misses）。オリジンから取得し、次の条件をすべて満たせば保存する:
           status が CACHEABLE_STATUSES に含まれる、ttl > 0、vary に "*" がない。
           同じキーに同じ Vary の値の古い応答があれば置き換える。
        オリジンを呼ぶたびに stats.origin_requests を 1 増やす（1・3・4 のすべて）。

        保存時刻は「受け取った時刻 − 応答の age」とする。上流のキャッシュで 5 秒経過していた応答は、
        受け取った時点ですでに 5 秒経っているものとして扱う（上流と同じ時刻に期限が切れる）。
        HIT・STALE の age は現在時刻 − 保存時刻、MISS・BYPASS の age は応答の age。

    Vary に使うヘッダの値の正規化:
        ヘッダ名は小文字で比べる。値は前後の空白を除き、連続する空白を 1 つにする（ないときは ""）。
        normalize_accept_encoding=True なら Accept-Encoding は、カンマで区切ったトークン（";" 以降の
        q 値を除き、小文字）に "br" があれば "br"、なければ "gzip" があれば "gzip"、どちらもなければ
        "identity" にまとめる（書き方の違いでキャッシュが細切れになるのを防ぐ）。

    purge(url): そのキャッシュキーに保存されたすべての応答を消し、消した数を返す。
    purge_prefix(prefix): キャッシュキーが prefix で始まるすべての応答を消し、消した数を返す。

    as_origin(): このキャッシュを、別のキャッシュのオリジンとして使うための関数を返す（多段構成、
        オリジンシールド）。関数は (url, headers) を受け取って self.get を呼び、
        - 結果が HIT か MISS で、そのリクエストに一致する応答が保存されていれば、その応答の
          ttl・vary・stale_while_revalidate と、age = 現在時刻 − 保存時刻 を持つ OriginResponse を返す。
        - それ以外（保存されなかった、STALE、BYPASS）は ttl=0 の OriginResponse を返す
          （下流にキャッシュさせない）。

    >>> t = [0.0]
    >>> cdn = CDNCache(lambda url, h: OriginResponse(body="hello", ttl=60), lambda: t[0])
    >>> cdn.get("https://example.com/").cache
    'MISS'
    >>> t[0] = 30
    >>> cdn.get("https://example.com/")
    EdgeResponse(status=200, body='hello', cache='HIT', age=30.0)
    """

    def __init__(
        self,
        origin: Origin,
        clock: Callable[[], float],
        *,
        ignored_query_params: Iterable[str] = DEFAULT_IGNORED_PARAMS,
        normalize_accept_encoding: bool = True,
    ) -> None:
        """設定を保存する（実装済み）。キャッシュの保存場所などの属性は自由に追加してください。"""
        self.origin = origin
        self.clock = clock
        self.ignored_query_params = set(ignored_query_params)
        self.normalize_accept_encoding = normalize_accept_encoding
        self.stats = CacheStats()

    def cache_key(self, url: str) -> str:
        raise NotImplementedError("演習4: CDNCache.cache_key を実装してください")

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> EdgeResponse:
        raise NotImplementedError("演習4: CDNCache.get を実装してください")

    def purge(self, url: str) -> int:
        raise NotImplementedError("演習4: CDNCache.purge を実装してください")

    def purge_prefix(self, prefix: str) -> int:
        raise NotImplementedError("演習4: CDNCache.purge_prefix を実装してください")

    def as_origin(self) -> Origin:
        raise NotImplementedError("演習4: CDNCache.as_origin を実装してください")
