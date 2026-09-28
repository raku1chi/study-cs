"""時刻の扱い（UTC・ISO 8601）。

時刻は常に UTC で扱い、保存と API では「2026-04-01T09:00:00.000Z」形式の文字列にします
（1.1 章「実務のデータ型設計」）。桁数を固定しているので、文字列の順序がそのまま時刻の順序になります。
テストでは時計（datetime を返す関数）を注入して、時刻を固定・操作します。
"""
from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """タイムゾーン付きの datetime を、UTC・ミリ秒精度の ISO 8601 文字列にする。

    >>> to_iso(datetime(2026, 4, 1, 18, 0, tzinfo=timezone.utc))
    '2026-04-01T18:00:00.000Z'
    """
    if dt.tzinfo is None:
        raise ValueError("タイムゾーンのない datetime は受け付けません")
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
