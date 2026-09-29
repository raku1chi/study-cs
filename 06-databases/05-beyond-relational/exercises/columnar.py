"""6.5 データモデルの多様性とデータストアの選定 — 演習3: 行指向と列指向、圧縮と読み取りコスト

分析用のデータベース（BigQuery・Snowflake・ClickHouse・DuckDB など）や Parquet ファイルが
なぜ集計に強いのかを、「読むバイト数」の簡単なモデルで確かめます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.5
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_columnar

大きさのモデル（簡略化している。実際のファイル形式はヘッダ・統計情報・汎用の圧縮も使う）:
    - 値の大きさは value_size(v): int は 8 バイト、str は 4 バイト（長さ）＋ UTF-8 のバイト数。
    - 行指向（row store）: 行ごとに全部の列を並べて格納する。1 列だけが必要でも、全部の列を読む。
    - 列指向（column store）: 列ごとに値を並べて格納する。必要な列だけを読む。列ごとに符号化を選べる:
        plain … そのまま
        rle   … ランレングス符号化: (値, 連続する回数) の列。1 つの連続（ラン）は「値の大きさ + 4 バイト」
        dict  … 辞書符号化: 値の種類の一覧（辞書）と、各行の辞書の番号（符号）。
                 大きさ = 辞書の値の大きさの合計 + ceil(行数 × ビット数 / 8)。
                 ビット数 = max(1, ceil(log2(辞書の大きさ)))（辞書が空なら全体で 0）
"""
from __future__ import annotations

import math  # noqa: F401  演習3-3 で使えます
from collections.abc import Mapping, Sequence
from typing import Any

Row = dict[str, Any]
ENCODINGS = ("plain", "rle", "dict")


# ---------------------------------------------------------------------------
# 提供済み: 値の大きさのモデル（変更しなくてよい）
# ---------------------------------------------------------------------------

def value_size(value: Any) -> int:
    """値を格納するのに必要なバイト数のモデル。None は 1 バイト。int・str・None 以外は TypeError。

    >>> value_size(2025), value_size("関東"), value_size("")
    (8, 10, 4)
    """
    if value is None:
        return 1
    if isinstance(value, bool):
        raise TypeError("bool は扱いません")
    if isinstance(value, int):
        return 8
    if isinstance(value, str):
        return 4 + len(value.encode("utf-8"))
    raise TypeError(f"扱えない型です: {type(value).__name__}")


# ---------------------------------------------------------------------------
# 演習3-1（★☆☆）: 行指向と列指向の変換
# ---------------------------------------------------------------------------

def to_columns(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> dict[str, list[Any]]:
    """行（dict）のリストを、{列名: その列の値のリスト} に変換する（columns の順）。

    行に列がなければ KeyError（row[列名] で自然に送出される）。

    >>> to_columns([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}], ["a", "b"])
    {'a': [1, 2], 'b': ['x', 'y']}
    """
    raise NotImplementedError("演習3-1: to_columns を実装してください")


def to_rows(columns: Mapping[str, Sequence[Any]]) -> list[Row]:
    """to_columns の逆。列の長さがそろっていなければ ValueError。列がなければ []。"""
    raise NotImplementedError("演習3-1: to_rows を実装してください")


# ---------------------------------------------------------------------------
# 演習3-2（★☆☆）: ランレングス符号化と辞書符号化
# ---------------------------------------------------------------------------

def rle_encode(values: Sequence[Any]) -> list[tuple[Any, int]]:
    """同じ値の連続を (値, 回数) にまとめる。

    >>> rle_encode(["a", "a", "b", "a"])
    [('a', 2), ('b', 1), ('a', 1)]
    """
    raise NotImplementedError("演習3-2: rle_encode を実装してください")


def rle_decode(runs: Sequence[tuple[Any, int]]) -> list[Any]:
    """rle_encode の逆。回数が 0 以下なら ValueError。"""
    raise NotImplementedError("演習3-2: rle_decode を実装してください")


def dict_encode(values: Sequence[Any]) -> tuple[list[Any], list[int]]:
    """(辞書, 符号の列) を返す。辞書は異なる値を **昇順** に並べたもの、符号は各値の辞書での位置。

    辞書を昇順にすると、符号の大小と元の値の大小が一致する（順序を保つ辞書）。

    >>> dict_encode(["tokyo", "osaka", "tokyo", "nagoya"])
    (['nagoya', 'osaka', 'tokyo'], [2, 1, 2, 0])
    """
    raise NotImplementedError("演習3-2: dict_encode を実装してください")


def dict_decode(dictionary: Sequence[Any], codes: Sequence[int]) -> list[Any]:
    """dict_encode の逆。"""
    raise NotImplementedError("演習3-2: dict_decode を実装してください")


# ---------------------------------------------------------------------------
# 演習3-3（★★☆）: 大きさと読み取りコストのモデル
# ---------------------------------------------------------------------------

def row_store_size(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> int:
    """行指向で格納したときの大きさ（すべての行のすべての列の value_size の合計）。"""
    raise NotImplementedError("演習3-3: row_store_size を実装してください")


def column_size(values: Sequence[Any], encoding: str = "plain") -> int:
    """1 つの列を encoding（"plain" / "rle" / "dict"）で格納したときの大きさ。未対応なら ValueError。

    >>> v = ["関東"] * 6 + ["近畿"] * 2
    >>> column_size(v, "plain"), column_size(v, "rle"), column_size(v, "dict")
    (80, 28, 21)
    """
    raise NotImplementedError("演習3-3: column_size を実装してください")


def bytes_read_row_store(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> int:
    """行指向の表から、いくつかの列を使う集計をするときに読むバイト数（＝表全体の大きさ）。"""
    raise NotImplementedError("演習3-3: bytes_read_row_store を実装してください")


def bytes_read_column_store(
    table: Mapping[str, Sequence[Any]], needed: Sequence[str], encodings: Mapping[str, str] | None = None
) -> int:
    """列指向の表 table（{列名: 値のリスト}）から、needed の列だけを読むときのバイト数。

    encodings は {列名: 符号化}。指定のない列は "plain"。
    """
    raise NotImplementedError("演習3-3: bytes_read_column_store を実装してください")


# ---------------------------------------------------------------------------
# 演習3-4（★★☆）: 符号化したまま集計する
# ---------------------------------------------------------------------------

def sum_rle(runs: Sequence[tuple[int, int]]) -> int:
    """RLE の列の合計を、展開せずに求める（Σ 値 × 回数）。"""
    raise NotImplementedError("演習3-4: sum_rle を実装してください")


def sales_by_region(columns: Mapping[str, Sequence[Any]], year: int) -> dict[str, int]:
    """SELECT region, SUM(amount) FROM sales WHERE year = :year GROUP BY region を、列指向の表で計算する。

    columns は少なくとも "region"・"year"・"amount" の列を持つ（他の列は読まないこと）。
    結果は {地域: 合計}。該当する行のある地域だけを、地域名の昇順に並べた dict で返す。
    """
    raise NotImplementedError("演習3-4: sales_by_region を実装してください")


def sales_by_region_encoded(
    year_runs: Sequence[tuple[int, int]],
    region_dictionary: Sequence[str],
    region_codes: Sequence[int],
    amounts: Sequence[int],
    year: int,
) -> dict[str, int]:
    """sales_by_region と同じ集計を、符号化された列のまま行う。

    - year 列は RLE（year_runs）、region 列は辞書符号化（region_dictionary と region_codes）、
      amount 列はそのまま（amounts）。3 つの列の i 番目が同じ行を表す。
    - year 列は展開しないこと: ランを順にたどって行の位置を数え、year と一致するランの範囲の行だけを
      処理する（一致しないランは中身を見ずに読み飛ばす）。
    - 地域ごとの合計は、符号（整数）を添字にした配列に足していき、最後に辞書で名前に戻す
      （遅延実体化、late materialization）。
    - 結果の形は sales_by_region と同じ（該当する行のある地域だけ。辞書が昇順なので、符号の順に作れば地域名の昇順になる）。
    """
    raise NotImplementedError("演習3-4: sales_by_region_encoded を実装してください")
