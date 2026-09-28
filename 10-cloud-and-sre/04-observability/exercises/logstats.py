"""10.4 オブザーバビリティ — 演習: 構造化ログから RED メトリクスを作る

JSON Lines 形式のアクセスログ（exercises/data/access.jsonl）を読み、エンドポイントごと・
1 分ごとの RED（Rate・Errors・Duration）を計算して、障害の兆候と「誰が負荷をかけているか」を
見つけます。ログを信頼できるメトリクスに変えるときに必要な、壊れた行の扱い・パスの正規化
（カーディナリティの抑制）・分位点の計算を身につけます。

- 演習3（★★☆）: parse_line, parse_logs, normalize_path, endpoint_of
- 演習4（★★☆）: percentile, red_by_endpoint, per_minute, top_offenders, slowest

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.4

ログの 1 行の例（1 行に 1 つの JSON オブジェクト）:
    {"ts":"2026-09-01T10:00:00.228Z","level":"info","method":"POST","path":"/api/checkout",
     "status":201,"duration_ms":155.3,"client_ip":"203.0.113.15","trace_id":"6733688b..."}
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
# 演習3（★★☆）: 解析と正規化
# ===========================================================================

def parse_line(line: str) -> LogRecord | None:
    """1 行を LogRecord に変換する。不正な行なら None を返す（例外は投げない）。

    必須フィールド: ts, method, path, status, duration_ms。次のどれかに当てはまれば不正:
    - JSON として読めない、または JSON のオブジェクト（dict）でない
    - 必須フィールドが欠けている
    - status が int でない（bool や "200" のような文字列は不可）、または 100〜599 の外
    - duration_ms が int / float でない（bool は不可）、有限でない、または負
    - method が空文字列または文字列でない。path が "/" で始まる文字列でない
    - ts が ISO 8601 の文字列として読めない、またはタイムゾーンがない
    ts は UTC に変換して持つ。"Z" は "+00:00" と同じ意味。client_ip と trace_id は任意（なければ ""）。

    ヒント: Python 3.10 の datetime.fromisoformat は末尾の "Z" を読めないので、"+00:00" に置き換えてから読む。
    """
    raise NotImplementedError("演習3: parse_line を実装してください")


def parse_logs(lines: Iterable[str]) -> tuple[list[LogRecord], int]:
    """各行を parse_line し、(正しく読めた LogRecord のリスト, 不正な行の数) を返す。

    空行（空白だけの行を含む）は読み飛ばし、不正な行にも数えない。
    """
    raise NotImplementedError("演習3: parse_logs を実装してください")


def normalize_path(path: str) -> str:
    """集計用にパスを正規化する。

    1. "?" 以降（クエリ文字列）と "#" 以降を取り除く
    2. "/" で区切った各部分のうち、数字だけのものを "{id}"、UUID（8-4-4-4-12 桁の 16 進数）を "{uuid}" に置き換える
    3. 末尾の "/" を取り除く（ただしルート "/" はそのまま）

    >>> normalize_path("/api/users/42/orders/7?expand=items")
    '/api/users/{id}/orders/{id}'

    なぜ必要か: ID ごとに別の値として集計すると、系列の数（カーディナリティ）が ID の数だけ増え、
    メトリクス基盤の費用と性能を破壊する。
    """
    raise NotImplementedError("演習3: normalize_path を実装してください")


def endpoint_of(record: LogRecord) -> str:
    """"メソッド 正規化したパス" を返す。例: "GET /api/items/{id}"。"""
    raise NotImplementedError("演習3: endpoint_of を実装してください")


# ===========================================================================
# 演習4（★★☆）: RED メトリクス
# ===========================================================================

def percentile(values: Sequence[float], p: float) -> float:
    """最近順位法（nearest-rank）の p パーセンタイル: 昇順に並べて ceil(p/100 × n) 番目（1 始まり）の値。

    values が空、または p が 0 < p <= 100 でなければ ValueError。
    （パーセンタイルの定義は複数ある。NumPy の既定は線形補間なので値が違うことに注意）
    """
    raise NotImplementedError("演習4: percentile を実装してください")


def red_by_endpoint(records: Sequence[LogRecord], window_seconds: float) -> dict[str, EndpointStats]:
    """endpoint_of ごとに EndpointStats を計算し、エンドポイント名の昇順の dict で返す。

    - count: 件数、errors: status >= 500 の件数（4xx はクライアントの誤りなので含めない）
    - error_ratio: errors / count、rate_per_sec: count / window_seconds
    - p50 / p95 / p99: duration_ms の percentile
    window_seconds が正でなければ ValueError。
    """
    raise NotImplementedError("演習4: red_by_endpoint を実装してください")


def per_minute(records: Sequence[LogRecord]) -> dict[str, dict[str, EndpointStats]]:
    """1 分ごとに red_by_endpoint(その分のレコード, 60) を計算する。

    キーは UTC の分 "2026-09-01T10:04Z" の形（ts.strftime("%Y-%m-%dT%H:%MZ")）で、時刻の昇順。
    レコードがない分は含めない。
    """
    raise NotImplementedError("演習4: per_minute を実装してください")


def top_offenders(records: Sequence[LogRecord], by: str, metric: str, n: int = 3) -> list[tuple[str, float]]:
    """by でまとめた metric の合計の上位 n 件を [(キー, 合計), ...] で返す。

    - by: "client_ip" または "endpoint"（endpoint_of）
    - metric: "requests"（件数）、"errors"（status >= 500 の件数）、"client_errors"（400〜499 の件数）、
      "time"（duration_ms の合計。サーバーの時間を誰が使っているか）
    - 合計の降順、同じならキーの昇順。合計が 0 のものは含めない。
    - by や metric が上記以外なら ValueError。
    """
    raise NotImplementedError("演習4: top_offenders を実装してください")


def slowest(records: Sequence[LogRecord], n: int = 3) -> list[tuple[float, str, str]]:
    """最も遅いリクエストの上位 n 件を [(duration_ms, endpoint, trace_id), ...] で返す。

    duration_ms の降順、同じなら ts の昇順、次に trace_id の昇順。trace_id を使えば、そのリクエストの
    トレースを開いて原因を調べられる（メトリクス → ログ → トレースの行き来）。
    """
    raise NotImplementedError("演習4: slowest を実装してください")
