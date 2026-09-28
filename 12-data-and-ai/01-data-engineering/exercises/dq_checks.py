"""12.1 データ基盤とデータエンジニアリング — 演習3: データ品質チェック

行（辞書）のリストに対してデータ品質のチェックを行い、レポートを作る小さなフレームワークです。
dbt の汎用テスト（not_null / unique / accepted_values / relationships）に相当する列の制約チェックと、
データオブザーバビリティで使われる鮮度（freshness）・件数（volume）の監視を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.1
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_dq_checks

共通の約束:
    - 各チェックは CheckResult を返す。status は "pass" / "warn" / "fail" / "skip" のどれか。
    - severity="error"（既定）のチェックが不合格なら "fail"、severity="warn" なら "warn"。
      それ以外の severity は ValueError。
    - failures は不合格の件数、samples は不合格の例（最大 MAX_SAMPLES 個）。
    - 合格のときは failures=0, samples=()。
"""
from __future__ import annotations

import datetime as dt
import math  # noqa: F401  check_row_count_anomaly で使えます（math.inf）
import statistics  # noqa: F401  check_row_count_anomaly で使えます（fmean, stdev）
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

PASS, WARN, FAIL, SKIP = "pass", "warn", "fail", "skip"
MAX_SAMPLES = 5

Row = dict[str, Any]


@dataclass(frozen=True)
class CheckResult:
    """1 つのチェックの結果（実装済み）。"""

    name: str  # 例: "not_null(order_id)"
    status: str  # PASS / WARN / FAIL / SKIP
    failures: int = 0
    message: str = ""
    samples: tuple[Any, ...] = ()


# ---------------------------------------------------------------------------
# 演習3a（★☆☆〜★★☆）: 列の制約チェック
# ---------------------------------------------------------------------------

def check_not_null(rows: Sequence[Row], column: str, *, severity: str = "error") -> CheckResult:
    """column が None の行（列そのものがない行も含む）がないことを確かめる。

    - name は "not_null(列名)"。
    - failures は NULL の行数、samples は NULL だった **行番号**（0 始まり）。
    """
    raise NotImplementedError("演習3a: check_not_null を実装してください")


def check_unique(rows: Sequence[Row], columns: str | Sequence[str], *, severity: str = "error") -> CheckResult:
    """column（または列の組）の値が重複していないことを確かめる。

    - columns は列名 1 つ、または列名のリスト／タプル（複合キー）。
    - name は "unique(a)" や "unique(a, b)"。
    - いずれかの列が None の行は対象外（SQL の UNIQUE 制約や dbt の unique テストと同じ）。
    - failures は「重複している値の種類数」、samples はその値（初出順）。
      複合キーならタプル、単一列なら値そのもの。

    >>> check_unique([{"id": 1}, {"id": 1}, {"id": 2}], "id").samples   # doctest: +SKIP
    (1,)
    """
    raise NotImplementedError("演習3a: check_unique を実装してください")


def check_accepted_values(
    rows: Sequence[Row], column: str, accepted: Iterable[Any], *, severity: str = "error"
) -> CheckResult:
    """column の値が accepted のどれかであることを確かめる（None は対象外）。

    - name は "accepted_values(列名)"。
    - failures は不正な値の行数、samples は不正な値（重複なし・初出順）。
    """
    raise NotImplementedError("演習3a: check_accepted_values を実装してください")


def check_range(
    rows: Sequence[Row],
    column: str,
    *,
    min_value: Any = None,
    max_value: Any = None,
    severity: str = "error",
) -> CheckResult:
    """column の値が min_value 以上 max_value 以下（両端を含む）であることを確かめる。

    - None の値は対象外。min_value / max_value の片方は None（上限・下限なし）でよい。
    - 両方 None、または min_value > max_value なら ValueError。
    - 比較できない値（数値の列に文字列が入っているなど。比較で TypeError になる）も不合格に数える。
    - name は "range(列名)"。failures は範囲外の行数、samples は範囲外の値（重複なし・初出順）。
    """
    raise NotImplementedError("演習3a: check_range を実装してください")


def check_relationships(
    rows: Sequence[Row],
    column: str,
    parent_rows: Sequence[Row],
    parent_column: str,
    *,
    severity: str = "error",
) -> CheckResult:
    """参照整合性: column の値が、親テーブル parent_rows の parent_column に存在することを確かめる。

    - None は対象外（外部キー制約と同じ）。
    - name は "relationships(列名 -> 親の列名)"。
    - failures は親が見つからない行数、samples はその値（重複なし・初出順）。
    """
    raise NotImplementedError("演習3a: check_relationships を実装してください")


def check_schema(
    rows: Sequence[Row],
    expected: dict[str, type | tuple[type, ...]],
    *,
    allow_extra_columns: bool = True,
    severity: str = "error",
) -> CheckResult:
    """データ契約（data contract）のスキーマ部分: 列の存在と型を確かめる。

    - expected は {列名: 型 または 型のタプル}。例: {"order_id": int, "price": (int, float)}
    - 行ごとに、expected の列がない・値の型が違う（None は型チェックしない）・
      （allow_extra_columns=False のとき）想定外の列がある、のどれかがあれば、その行を不合格とする。
    - 注意: bool は int のサブクラスなので isinstance(True, int) は True になる。
      期待する型に bool が含まれていなければ、bool の値は型違いとして扱うこと。
    - name は "schema"。failures は不合格の **行数**、samples は問題の説明文字列
      （例: "行 3: 列 amount の型が str"。列名を含めること）。
    """
    raise NotImplementedError("演習3a: check_schema を実装してください")


# ---------------------------------------------------------------------------
# 演習3b（★★☆）: 鮮度と件数の監視
# ---------------------------------------------------------------------------

def parse_timestamp(value: str | dt.datetime) -> dt.datetime:
    """ISO 8601 の文字列（または datetime）を datetime にする。

    - datetime ならそのまま返す。
    - 末尾の "Z" は "+00:00" とみなす（Python 3.10 の datetime.fromisoformat は "Z" を読めない）。
    - 文字列でも datetime でもなければ ValueError。

    >>> parse_timestamp("2026-04-01T13:30:00Z")   # doctest: +SKIP
    datetime.datetime(2026, 4, 1, 13, 30, tzinfo=datetime.timezone.utc)
    """
    raise NotImplementedError("演習3b: parse_timestamp を実装してください")


def check_freshness(
    rows: Sequence[Row],
    column: str,
    *,
    now: dt.datetime,
    warn_after: dt.timedelta,
    error_after: dt.timedelta,
) -> CheckResult:
    """最新のデータが十分に新しいか（パイプラインが止まっていないか）を確かめる。

    - 現在時刻 now は引数で受け取る（テストで時計を固定できるように。datetime.now() を呼ばない）。
    - 最新の時刻 latest = column の最大値（None は無視）。age = now - latest。
    - warn_after > error_after なら ValueError。
    - 時刻の入った行がなければ "fail"。
    - タイムゾーン付き／なしの時刻が now と混在していたら ValueError。
    - age < 0（未来の時刻）なら "warn"。message に「未来」という語を含めること
      （JST の時刻を UTC として保存するなどのバグで、データが 9 時間未来に見えることがある）。
    - age > error_after なら "fail"、age > warn_after なら "warn"、それ以外は "pass"。
    - name は "freshness(列名)"。failures は不合格なら 1、合格なら 0。
    """
    raise NotImplementedError("演習3b: check_freshness を実装してください")


def check_row_count_anomaly(
    history: Sequence[int],
    current: int,
    *,
    z_threshold: float = 3.0,
    min_history: int = 7,
    severity: str = "error",
) -> CheckResult:
    """今回の件数が過去の件数から見て異常でないかを z スコアで判定する（ボリュームの監視）。

    - z = (current - 平均) / 標本標準偏差（statistics.stdev。n-1 で割る）。
    - |z| > z_threshold なら不合格。
    - 標準偏差が 0 なら、current が平均と等しければ z = 0、違えば z = inf とする。
    - history が min_history 件未満なら判定せず "skip"（学習期間が足りない）。
    - z_threshold <= 0 や min_history < 2 は ValueError。
    - name は "row_count_anomaly"。message に "z = 3.02" のように小数 2 桁の z を含める。
    """
    raise NotImplementedError("演習3b: check_row_count_anomaly を実装してください")


# ---------------------------------------------------------------------------
# 演習3c（★★☆）: スイートの実行とレポート
# ---------------------------------------------------------------------------

@dataclass
class SuiteReport:
    """チェック結果の集まり。"""

    results: list[CheckResult]

    @property
    def status(self) -> str:
        """全体の状態: fail > warn > pass の順に「最も悪いもの」。skip は無視（空なら pass）。"""
        raise NotImplementedError("演習3c: SuiteReport.status を実装してください")

    @property
    def should_block(self) -> bool:
        """下流への公開を止めるべきか（"fail" が 1 つでもあれば True）。"""
        raise NotImplementedError("演習3c: SuiteReport.should_block を実装してください")

    def counts(self) -> dict[str, int]:
        """{"pass": n, "warn": n, "fail": n, "skip": n}（4 つのキーを必ず含める）。"""
        raise NotImplementedError("演習3c: SuiteReport.counts を実装してください")

    def to_text(self) -> str:
        """人が読むレポートを返す。

        - 結果 1 件につき 1 行。行頭は "[PASS] " / "[WARN] " / "[FAIL] " / "[SKIP] " + チェック名。
          その後ろに message や samples を自由に書いてよい。
        - 最後の行は "結果: " + 全体の状態の大文字（例: "結果: FAIL（pass 4 / warn 1 / fail 2 / skip 0）"）。
        """
        raise NotImplementedError("演習3c: SuiteReport.to_text を実装してください")


def run_suite(checks: Iterable[Callable[[], CheckResult]]) -> SuiteReport:
    """引数なしで呼べるチェック（functools.partial など）を順に実行して SuiteReport を返す。

    チェックが例外を投げても止まらずに次へ進み、その結果を
    CheckResult(name="error:関数名", status="fail", failures=1, message=例外の内容を含む文字列)
    として記録する（1 つのチェックの不具合で、他のチェック結果を失わないため）。
    functools.partial の場合、関数名は .func.__name__ で取れる。
    """
    raise NotImplementedError("演習3c: run_suite を実装してください")
