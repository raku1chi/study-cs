"""5.4 Webの仕組みとネットワーク構成 — 解答例（cdn_sim）

演習の仕様は exercises/cdn_sim.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit

# RFC 9110 15.1 で「経験的にキャッシュしてよい」とされるステータスコード
CACHEABLE_STATUSES = {200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501}
DEFAULT_IGNORED_PARAMS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid")


@dataclass
class OriginResponse:
    status: int = 200
    body: str = ""
    ttl: float = 60.0
    vary: tuple[str, ...] = ()
    stale_while_revalidate: float = 0.0
    age: float = 0.0


@dataclass
class EdgeResponse:
    status: int
    body: str
    cache: str  # "HIT" / "MISS" / "STALE" / "BYPASS"
    age: float


Origin = Callable[[str, Mapping[str, str]], OriginResponse]


@dataclass
class _Entry:
    vary: tuple[str, ...]
    vary_values: tuple[str, ...]
    response: OriginResponse
    stored_at: float  # 「応答が生成された時刻」（受け取った時刻 − 上流での経過時間）


@dataclass
class CacheStats:
    requests: int = 0
    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    bypasses: int = 0
    origin_requests: int = 0

    @property
    def hit_ratio(self) -> float:
        return (self.hits + self.stale_hits) / self.requests if self.requests else 0.0


class CDNCache:
    def __init__(
        self,
        origin: Origin,
        clock: Callable[[], float],
        *,
        ignored_query_params: Iterable[str] = DEFAULT_IGNORED_PARAMS,
        normalize_accept_encoding: bool = True,
    ) -> None:
        self.origin = origin
        self.clock = clock
        self.ignored_query_params = set(ignored_query_params)
        self.normalize_accept_encoding = normalize_accept_encoding
        self.stats = CacheStats()
        self._store: dict[str, list[_Entry]] = {}

    # --------------------------------------------------------------- キャッシュキー
    def cache_key(self, url: str) -> str:
        parts = urlsplit(url)
        # 追跡用のパラメータを取り除き、順序をそろえる。?a=1&b=2 と ?b=2&a=1 を同じものとして扱う
        params = sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                        if k not in self.ignored_query_params)
        query = urlencode(params)
        return f"{parts.scheme.lower()}://{parts.netloc.lower()}{parts.path or '/'}" + (f"?{query}" if query else "")

    def _vary_value(self, headers: Mapping[str, str], name: str) -> str:
        value = next((v for k, v in headers.items() if k.lower() == name), "")
        if name == "accept-encoding" and self.normalize_accept_encoding:
            # 無数にある書き方を、実際に配る表現の種類（br / gzip / なし）にまとめて断片化を防ぐ
            tokens = {t.split(";")[0].strip().lower() for t in value.split(",")}
            return "br" if "br" in tokens else "gzip" if "gzip" in tokens else "identity"
        return " ".join(value.split())

    # --------------------------------------------------------------- 取得
    def get(self, url: str, headers: Mapping[str, str] | None = None) -> EdgeResponse:
        headers = dict(headers or {})
        now = self.clock()
        self.stats.requests += 1
        if any(k.lower() == "authorization" for k in headers):
            # 利用者ごとに異なりうる応答は、保存も再利用もしない
            self.stats.bypasses += 1
            resp = self._fetch(url, headers)
            return EdgeResponse(resp.status, resp.body, "BYPASS", resp.age)

        key = self.cache_key(url)
        entry = self._lookup(key, headers)
        if entry is not None:
            age = now - entry.stored_at
            if age < entry.response.ttl:
                self.stats.hits += 1
                return EdgeResponse(entry.response.status, entry.response.body, "HIT", age)
            if age < entry.response.ttl + entry.response.stale_while_revalidate:
                # 古いものをすぐに返し、裏で更新する（このシミュレーションでは直後に同期的に更新）
                self.stats.stale_hits += 1
                stale = EdgeResponse(entry.response.status, entry.response.body, "STALE", age)
                self._refresh(key, url, headers)
                return stale
            self._store[key].remove(entry)  # 期限切れ

        self.stats.misses += 1
        resp = self._refresh(key, url, headers)
        return EdgeResponse(resp.status, resp.body, "MISS", resp.age)

    def _lookup(self, key: str, headers: Mapping[str, str]) -> _Entry | None:
        # 同じキーに保存された「表現」のうち、Vary に挙がったヘッダの値が一致するものを探す
        return next((e for e in self._store.get(key, []) if self._matches(e, headers)), None)

    def _matches(self, entry: _Entry, headers: Mapping[str, str]) -> bool:
        if "*" in entry.vary:
            return False  # Vary: * の応答は再利用できない
        return tuple(self._vary_value(headers, n) for n in entry.vary) == entry.vary_values

    def _fetch(self, url: str, headers: Mapping[str, str]) -> OriginResponse:
        self.stats.origin_requests += 1
        return self.origin(url, headers)

    def _refresh(self, key: str, url: str, headers: Mapping[str, str]) -> OriginResponse:
        resp = self._fetch(url, headers)
        vary = tuple(name.lower() for name in resp.vary)
        if resp.status in CACHEABLE_STATUSES and resp.ttl > 0 and "*" not in vary:
            values = tuple(self._vary_value(headers, n) for n in vary)
            entries = [e for e in self._store.get(key, []) if not (e.vary == vary and e.vary_values == values)]
            entries.append(_Entry(vary, values, resp, self.clock() - resp.age))
            self._store[key] = entries
        return resp

    # --------------------------------------------------------------- パージ
    def purge(self, url: str) -> int:
        return len(self._store.pop(self.cache_key(url), []))

    def purge_prefix(self, prefix: str) -> int:
        keys = [k for k in self._store if k.startswith(prefix)]
        return sum(len(self._store.pop(k)) for k in keys)

    # --------------------------------------------------------------- 多段構成
    def as_origin(self) -> Origin:
        """このキャッシュを、別のキャッシュのオリジンとして使うための関数（オリジンシールド）。"""

        def fetch(url: str, headers: Mapping[str, str]) -> OriginResponse:
            edge = self.get(url, headers)
            entry = self._lookup(self.cache_key(url), headers) if edge.cache in ("HIT", "MISS") else None
            if entry is None:
                # 保存しなかった応答や、期限切れの古い応答は、下流にもキャッシュさせない
                return OriginResponse(edge.status, edge.body, ttl=0.0)
            r = entry.response
            # 下流には「上流での経過時間」を Age として伝え、残りの寿命だけキャッシュさせる
            return OriginResponse(edge.status, edge.body, r.ttl, r.vary, r.stale_while_revalidate,
                                  age=max(0.0, self.clock() - entry.stored_at))

        return fetch
