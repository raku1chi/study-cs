"""5.3 DNS・HTTP・TLS — 解答例（http_cache）

演習の仕様は exercises/http_cache.py の docstring を参照してください。
計算方法は RFC 9111（HTTP Caching）の 4.2 節に従っています。
"""
from __future__ import annotations

import email.utils
import re
from datetime import timezone
from typing import Mapping

DELTA_RE = re.compile(r"[0-9]+")
MAX_DELTA = 2**31  # RFC 9111 1.2.2: 表せないほど大きな値は 2^31 とみなす
HEURISTIC_FRACTION = 0.1  # 経験的な鮮度: Last-Modified からの経過時間の 10%


def _header(headers: Mapping[str, str], name: str) -> str | None:
    key = name.lower()
    for k, v in headers.items():
        if k.lower() == key:
            return v
    return None


def parse_cache_control(value: str | None) -> dict[str, str | None]:
    directives: dict[str, str | None] = {}
    if not value:
        return directives
    i, n = 0, len(value)
    while i < n:
        # ディレクティブ名（大文字小文字を区別しない）
        j = i
        while j < n and value[j] not in ",=":
            j += 1
        name = value[i:j].strip().lower()
        arg: str | None = None
        i = j
        if i < n and value[i] == "=":
            i += 1
            while i < n and value[i] in " \t":
                i += 1
            if i < n and value[i] == '"':
                # quoted-string: 中のカンマは区切りではない。\ は次の 1 文字をそのまま使う
                i += 1
                chars = []
                while i < n and value[i] != '"':
                    if value[i] == "\\" and i + 1 < n:
                        i += 1
                    chars.append(value[i])
                    i += 1
                arg = "".join(chars)
                i += 1  # 閉じの " を飛ばす
                while i < n and value[i] != ",":
                    i += 1
            else:
                j = i
                while j < n and value[j] != ",":
                    j += 1
                arg = value[i:j].strip()
                i = j
        i += 1  # カンマを飛ばす
        if name and name not in directives:  # 同じディレクティブが重なったら最初のものを使う
            directives[name] = arg
    return directives


def parse_http_date(value: str | None) -> float | None:
    if not value:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # asctime 形式にはタイムゾーンがないが、HTTP の日時は常に UTC
    return dt.timestamp()


def _delta_seconds(value: str | None) -> int | None:
    if value is None or not DELTA_RE.fullmatch(value):
        return None  # 数字以外（空、負号、小数など）は不正
    return min(int(value), MAX_DELTA)


def freshness_lifetime(headers: Mapping[str, str], *, shared: bool, response_time: float) -> float:
    cc = parse_cache_control(_header(headers, "Cache-Control"))
    # 優先順位: s-maxage（共有キャッシュのみ）> max-age > Expires > 経験則
    for directive in (("s-maxage", "max-age") if shared else ("max-age",)):
        if directive in cc:
            delta = _delta_seconds(cc[directive])
            return float(delta) if delta is not None else 0.0  # 不正な値は「期限切れ」とみなす
    date = parse_http_date(_header(headers, "Date"))
    if date is None:
        date = response_time  # Date がなければ受信した時刻で代用する
    expires_text = _header(headers, "Expires")
    if expires_text is not None:
        expires = parse_http_date(expires_text)
        if expires is None:
            return 0.0  # "0" のような不正な日時は「すでに期限切れ」（RFC 9111 5.3）
        return max(0.0, expires - date)
    last_modified = parse_http_date(_header(headers, "Last-Modified"))
    if last_modified is not None and date > last_modified:
        return HEURISTIC_FRACTION * (date - last_modified)
    return 0.0


def current_age(headers: Mapping[str, str], *, request_time: float, response_time: float, now: float) -> float:
    age_value = _delta_seconds((_header(headers, "Age") or "").strip()) or 0
    date_value = parse_http_date(_header(headers, "Date"))
    if date_value is None:
        date_value = response_time
    # 時計のずれに強い見積もりと、経路上のキャッシュが付けた Age のうち、大きい方を採る
    apparent_age = max(0.0, response_time - date_value)
    response_delay = response_time - request_time
    corrected_age_value = age_value + response_delay
    corrected_initial_age = max(apparent_age, corrected_age_value)
    resident_time = now - response_time  # 自分のキャッシュに入ってからの時間
    return corrected_initial_age + resident_time


def cache_status(
    headers: Mapping[str, str], *, request_time: float, response_time: float, now: float, shared: bool
) -> str:
    cc = parse_cache_control(_header(headers, "Cache-Control"))
    if "no-store" in cc or (shared and "private" in cc):
        return "no-store"
    if "no-cache" in cc:
        return "must-revalidate"  # 保存はしてよいが、使うたびにオリジンに確認する
    lifetime = freshness_lifetime(headers, shared=shared, response_time=response_time)
    age = current_age(headers, request_time=request_time, response_time=response_time, now=now)
    if lifetime > age:
        return "fresh"
    if "must-revalidate" in cc or (shared and ("proxy-revalidate" in cc or "s-maxage" in cc)):
        return "must-revalidate"  # 期限切れのまま返すことは、オリジンに接続できなくても許されない
    return "stale"
