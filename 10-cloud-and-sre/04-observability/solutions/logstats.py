"""10.4 オブザーバビリティ — 演習（構造化ログから RED メトリクス）の解答例

演習の仕様は exercises/logstats.py の docstring を参照してください。
"""
from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass(frozen=True)
class LogRecord:
    ts: datetime            # タイムゾーン付き（UTC に変換済み）
    method: str
    path: str               # 生のパス（クエリ文字列を含む）
    status: int
    duration_ms: float
    client_ip: str = ""
    trace_id: str = ""


@dataclass(frozen=True)
class EndpointStats:
    endpoint: str           # "GET /api/items/{id}"
    count: int              # Rate の元になるリクエスト数
    errors: int             # Errors: ステータス 500 以上の数
    error_ratio: float
    rate_per_sec: float
    p50: float              # Duration の分位点（ミリ秒）
    p95: float
    p99: float


# ===========================================================================
# 演習3: 解析と正規化
# ===========================================================================

_REQUIRED = ("ts", "method", "path", "status", "duration_ms")
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _parse_ts(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("ts は文字列")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value  # Python 3.10 の fromisoformat は Z を読めない
    ts = datetime.fromisoformat(text)
    if ts.tzinfo is None:
        raise ValueError("タイムゾーンのない時刻は受け付けない")
    return ts.astimezone(timezone.utc)


def parse_line(line: str) -> LogRecord | None:
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict) or any(k not in obj for k in _REQUIRED):
        return None
    status, duration = obj["status"], obj["duration_ms"]
    # bool は int の一種なので明示的に除く。"200" のような文字列の数値も受け付けない（型の約束を守らせる）
    if isinstance(status, bool) or not isinstance(status, int) or not 100 <= status <= 599:
        return None
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
        return None
    method, path = obj["method"], obj["path"]
    if not isinstance(method, str) or not method or not isinstance(path, str) or not path.startswith("/"):
        return None
    try:
        ts = _parse_ts(obj["ts"])
    except ValueError:
        return None
    client_ip, trace_id = obj.get("client_ip", ""), obj.get("trace_id", "")
    return LogRecord(ts, method, path, status, float(duration),
                     client_ip if isinstance(client_ip, str) else "",
                     trace_id if isinstance(trace_id, str) else "")


def parse_logs(lines: Iterable[str]) -> tuple[list[LogRecord], int]:
    records, errors = [], 0
    for line in lines:
        if not line.strip():
            continue
        record = parse_line(line)
        if record is None:
            errors += 1  # 壊れた行で処理全体を止めない。ただし数は必ず報告する
        else:
            records.append(record)
    return records, errors


def normalize_path(path: str) -> str:
    path = path.split("?", 1)[0].split("#", 1)[0]
    segments = []
    for seg in path.split("/"):
        if seg.isdigit():
            seg = "{id}"
        elif _UUID_RE.fullmatch(seg):
            seg = "{uuid}"
        segments.append(seg)
    normalized = "/".join(segments)
    # ID ごとに別の系列にすると、系列の数（カーディナリティ）が爆発する
    return normalized.rstrip("/") or "/"


def endpoint_of(record: LogRecord) -> str:
    return f"{record.method} {normalize_path(record.path)}"


# ===========================================================================
# 演習4: RED メトリクス
# ===========================================================================

def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("values が空です")
    if not 0 < p <= 100:
        raise ValueError(f"p は 0 < p <= 100: {p}")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]  # 最近順位法


def _stats(endpoint: str, group: Sequence[LogRecord], window_seconds: float) -> EndpointStats:
    durations = [r.duration_ms for r in group]
    errors = sum(1 for r in group if r.status >= 500)
    return EndpointStats(
        endpoint, len(group), errors, errors / len(group), len(group) / window_seconds,
        percentile(durations, 50), percentile(durations, 95), percentile(durations, 99),
    )


def red_by_endpoint(records: Sequence[LogRecord], window_seconds: float) -> dict[str, EndpointStats]:
    if window_seconds <= 0:
        raise ValueError("window_seconds は正の数")
    groups: dict[str, list[LogRecord]] = defaultdict(list)
    for r in records:
        groups[endpoint_of(r)].append(r)
    return {ep: _stats(ep, groups[ep], window_seconds) for ep in sorted(groups)}


def per_minute(records: Sequence[LogRecord]) -> dict[str, dict[str, EndpointStats]]:
    buckets: dict[str, list[LogRecord]] = defaultdict(list)
    for r in records:
        buckets[r.ts.strftime("%Y-%m-%dT%H:%MZ")].append(r)
    return {minute: red_by_endpoint(buckets[minute], 60) for minute in sorted(buckets)}


def top_offenders(records: Sequence[LogRecord], by: str, metric: str, n: int = 3) -> list[tuple[str, float]]:
    keys = {"client_ip": lambda r: r.client_ip, "endpoint": endpoint_of}
    values = {
        "requests": lambda r: 1,
        "errors": lambda r: 1 if r.status >= 500 else 0,
        "client_errors": lambda r: 1 if 400 <= r.status < 500 else 0,
        "time": lambda r: r.duration_ms,
    }
    if by not in keys or metric not in values:
        raise ValueError(f"by は {sorted(keys)}、metric は {sorted(values)} のいずれか")
    totals: dict[str, float] = defaultdict(float)
    for r in records:
        totals[keys[by](r)] += values[metric](r)
    ranked = sorted(((k, v) for k, v in totals.items() if v > 0), key=lambda kv: (-kv[1], kv[0]))
    return ranked[:n]


def slowest(records: Sequence[LogRecord], n: int = 3) -> list[tuple[float, str, str]]:
    ranked = sorted(records, key=lambda r: (-r.duration_ms, r.ts, r.trace_id))
    return [(r.duration_ms, endpoint_of(r), r.trace_id) for r in ranked[:n]]
