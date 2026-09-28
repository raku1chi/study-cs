"""12.1 データ基盤とデータエンジニアリング — 演習3: データ品質チェック（解答例）

演習の仕様は exercises/dq_checks.py の docstring を参照してください。
dbt のテスト（not_null / unique / accepted_values / relationships）と、データオブザーバビリティで
よく使われる鮮度・件数の監視を、行（辞書）のリストに対して行う小さなフレームワークです。
"""
from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
_SEVERITY_ORDER = {SKIP: 0, PASS: 1, WARN: 2, FAIL: 3}
MAX_SAMPLES = 5

Row = dict[str, Any]


@dataclass(frozen=True)
class CheckResult:
    """1 つのチェックの結果（実装済み）。"""

    name: str
    status: str
    failures: int = 0
    message: str = ""
    samples: tuple[Any, ...] = ()


def _failed_status(severity: str) -> str:
    if severity not in ("error", "warn"):
        raise ValueError(f"severity は 'error' か 'warn': {severity!r}")
    return FAIL if severity == "error" else WARN


def _unique_in_order(values: Iterable[Any]) -> list[Any]:
    seen: list[Any] = []
    for v in values:
        if v not in seen:
            seen.append(v)
    return seen


# ---------------------------------------------------------------------------
# 演習3a: 列の制約チェック
# ---------------------------------------------------------------------------

def check_not_null(rows: Sequence[Row], column: str, *, severity: str = "error") -> CheckResult:
    status_on_fail = _failed_status(severity)
    bad = [i for i, row in enumerate(rows) if row.get(column) is None]
    name = f"not_null({column})"
    if not bad:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, len(bad), f"NULL が {len(bad)} 行あります", tuple(bad[:MAX_SAMPLES]))


def check_unique(rows: Sequence[Row], columns: str | Sequence[str], *, severity: str = "error") -> CheckResult:
    status_on_fail = _failed_status(severity)
    cols = (columns,) if isinstance(columns, str) else tuple(columns)
    name = f"unique({', '.join(cols)})"
    counts: dict[Any, int] = {}
    for row in rows:
        key = tuple(row.get(c) for c in cols)
        if any(v is None for v in key):
            continue  # SQL の UNIQUE 制約や dbt の unique テストと同じく NULL は対象外
        key = key[0] if len(cols) == 1 else key
        counts[key] = counts.get(key, 0) + 1
    dups = [k for k, c in counts.items() if c > 1]  # dict は挿入順を保つ = 初出順
    if not dups:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, len(dups), f"重複した値が {len(dups)} 種類あります",
                       tuple(dups[:MAX_SAMPLES]))


def check_accepted_values(
    rows: Sequence[Row], column: str, accepted: Iterable[Any], *, severity: str = "error"
) -> CheckResult:
    status_on_fail = _failed_status(severity)
    allowed = set(accepted)
    name = f"accepted_values({column})"
    bad = [row[column] for row in rows if row.get(column) is not None and row[column] not in allowed]
    if not bad:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, len(bad), f"許可されていない値が {len(bad)} 行あります",
                       tuple(_unique_in_order(bad)[:MAX_SAMPLES]))


def check_range(
    rows: Sequence[Row],
    column: str,
    *,
    min_value: Any = None,
    max_value: Any = None,
    severity: str = "error",
) -> CheckResult:
    status_on_fail = _failed_status(severity)
    if min_value is None and max_value is None:
        raise ValueError("min_value と max_value の少なくとも一方を指定してください")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError(f"min_value > max_value です: {min_value} > {max_value}")
    name = f"range({column})"
    bad: list[Any] = []
    for row in rows:
        v = row.get(column)
        if v is None:
            continue
        try:
            ok = (min_value is None or v >= min_value) and (max_value is None or v <= max_value)
        except TypeError:
            ok = False  # 比較できない型（数値の列に文字列など）も不合格として数える
        if not ok:
            bad.append(v)
    if not bad:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, len(bad),
                       f"範囲 [{min_value}, {max_value}] の外の値が {len(bad)} 行あります",
                       tuple(_unique_in_order(bad)[:MAX_SAMPLES]))


def check_relationships(
    rows: Sequence[Row],
    column: str,
    parent_rows: Sequence[Row],
    parent_column: str,
    *,
    severity: str = "error",
) -> CheckResult:
    status_on_fail = _failed_status(severity)
    name = f"relationships({column} -> {parent_column})"
    parents = {p.get(parent_column) for p in parent_rows}
    bad = [row[column] for row in rows if row.get(column) is not None and row[column] not in parents]
    if not bad:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, len(bad), f"親が存在しない値が {len(bad)} 行あります",
                       tuple(_unique_in_order(bad)[:MAX_SAMPLES]))


def check_schema(
    rows: Sequence[Row],
    expected: dict[str, type | tuple[type, ...]],
    *,
    allow_extra_columns: bool = True,
    severity: str = "error",
) -> CheckResult:
    status_on_fail = _failed_status(severity)
    name = "schema"
    problems: list[str] = []
    bad_rows = 0
    for i, row in enumerate(rows):
        row_problems: list[str] = []
        for col, typ in expected.items():
            if col not in row:
                row_problems.append(f"行 {i}: 列 {col} がありません")
                continue
            v = row[col]
            if v is None:
                continue  # NULL を許すかどうかは not_null の担当
            types = typ if isinstance(typ, tuple) else (typ,)
            # bool は int のサブクラスなので、int の列に True が入っても isinstance では見逃す
            if isinstance(v, bool) and bool not in types:
                ok = False
            else:
                ok = isinstance(v, types)
            if not ok:
                row_problems.append(f"行 {i}: 列 {col} の型が {type(v).__name__}")
        if not allow_extra_columns:
            for col in row:
                if col not in expected:
                    row_problems.append(f"行 {i}: 想定外の列 {col}")
        if row_problems:
            bad_rows += 1
            problems.extend(row_problems)
    if not bad_rows:
        return CheckResult(name, PASS)
    return CheckResult(name, status_on_fail, bad_rows, f"スキーマ違反が {bad_rows} 行あります",
                       tuple(problems[:MAX_SAMPLES]))


# ---------------------------------------------------------------------------
# 演習3b: 鮮度と件数の監視
# ---------------------------------------------------------------------------

def parse_timestamp(value: str | dt.datetime) -> dt.datetime:
    if isinstance(value, dt.datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"時刻として解釈できません: {value!r}")
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"  # Python 3.10 の fromisoformat は 'Z' を読めない
    return dt.datetime.fromisoformat(text)


def check_freshness(
    rows: Sequence[Row],
    column: str,
    *,
    now: dt.datetime,
    warn_after: dt.timedelta,
    error_after: dt.timedelta,
) -> CheckResult:
    if warn_after > error_after:
        raise ValueError("warn_after は error_after 以下にしてください")
    name = f"freshness({column})"
    stamps = [parse_timestamp(row[column]) for row in rows if row.get(column) is not None]
    if not stamps:
        return CheckResult(name, FAIL, 1, "時刻の入った行がありません")
    if any((s.tzinfo is None) != (now.tzinfo is None) for s in stamps):
        raise ValueError("タイムゾーン付きの時刻と、タイムゾーンなしの時刻が混在しています")
    latest = max(stamps)
    age = now - latest
    if age < dt.timedelta(0):
        # 例: JST の時刻を UTC として保存すると、9 時間未来のデータに見える
        return CheckResult(name, WARN, 1, f"最新の時刻 {latest.isoformat()} が現在より未来です"
                                          "（時計のずれ・タイムゾーンの誤りの可能性）")
    if age > error_after:
        return CheckResult(name, FAIL, 1, f"最新のデータが {age} 前です（上限 {error_after}）")
    if age > warn_after:
        return CheckResult(name, WARN, 1, f"最新のデータが {age} 前です（警告 {warn_after}）")
    return CheckResult(name, PASS, 0, f"最新のデータは {age} 前")


def check_row_count_anomaly(
    history: Sequence[int],
    current: int,
    *,
    z_threshold: float = 3.0,
    min_history: int = 7,
    severity: str = "error",
) -> CheckResult:
    status_on_fail = _failed_status(severity)
    if z_threshold <= 0:
        raise ValueError("z_threshold は正の数にしてください")
    if min_history < 2:
        raise ValueError("標準偏差を計算するには min_history >= 2 が必要です")
    name = "row_count_anomaly"
    if len(history) < min_history:
        return CheckResult(name, SKIP, 0, f"履歴が {len(history)} 件しかありません（{min_history} 件必要）")
    mean = statistics.fmean(history)
    stdev = statistics.stdev(history)  # 標本標準偏差（n-1 で割る）
    if stdev == 0:
        z = 0.0 if current == mean else math.inf
    else:
        z = (current - mean) / stdev
    message = f"今回 {current} 件、過去の平均 {mean:.1f} 件、z = {z:.2f}"
    if abs(z) > z_threshold:
        return CheckResult(name, status_on_fail, 1, message)
    return CheckResult(name, PASS, 0, message)


# ---------------------------------------------------------------------------
# 演習3c: スイートの実行とレポート
# ---------------------------------------------------------------------------

@dataclass
class SuiteReport:
    results: list[CheckResult]

    @property
    def status(self) -> str:
        worst = PASS
        for r in self.results:
            if r.status != SKIP and _SEVERITY_ORDER[r.status] > _SEVERITY_ORDER[worst]:
                worst = r.status
        return worst

    @property
    def should_block(self) -> bool:
        # 下流（ダッシュボードや ML の学習）への公開を止めるべきか。fail が 1 つでもあれば止める
        return any(r.status == FAIL for r in self.results)

    def counts(self) -> dict[str, int]:
        out = {PASS: 0, WARN: 0, FAIL: 0, SKIP: 0}
        for r in self.results:
            out[r.status] += 1
        return out

    def to_text(self) -> str:
        lines = []
        for r in self.results:
            line = f"[{r.status.upper()}] {r.name}"
            if r.message:
                line += f" — {r.message}"
            if r.samples:
                line += " 例: " + ", ".join(repr(s) for s in r.samples)
            lines.append(line)
        c = self.counts()
        lines.append(
            f"結果: {self.status.upper()}（pass {c[PASS]} / warn {c[WARN]} / fail {c[FAIL]} / skip {c[SKIP]}）"
        )
        return "\n".join(lines)


def run_suite(checks: Iterable[Callable[[], CheckResult]]) -> SuiteReport:
    results: list[CheckResult] = []
    for check in checks:
        try:
            results.append(check())
        except Exception as exc:  # noqa: BLE001  1 つのチェックの不具合で他の結果を失わない
            func = getattr(check, "func", check)  # functools.partial なら元の関数
            name = f"error:{getattr(func, '__name__', repr(func))}"
            results.append(CheckResult(name, FAIL, 1, f"チェックの実行中に例外: {exc!r}"))
    return SuiteReport(results)
