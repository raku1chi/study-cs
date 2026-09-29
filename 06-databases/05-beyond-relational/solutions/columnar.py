"""6.5 データモデルの多様性とデータストアの選定 — 演習3 解答例: 行指向と列指向、圧縮と読み取りコスト

演習の仕様は exercises/columnar.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

Row = dict[str, Any]
ENCODINGS = ("plain", "rle", "dict")


# ---------------------------------------------------------------------------
# 提供済み: 値の大きさのモデル（スタブと同じ）
# ---------------------------------------------------------------------------

def value_size(value: Any) -> int:
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
# 演習3-1: 行指向と列指向の変換
# ---------------------------------------------------------------------------

def to_columns(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> dict[str, list[Any]]:
    return {c: [row[c] for row in rows] for c in columns}


def to_rows(columns: Mapping[str, Sequence[Any]]) -> list[Row]:
    lengths = {len(v) for v in columns.values()}
    if len(lengths) > 1:
        raise ValueError(f"列の長さがそろっていません: {sorted(lengths)}")
    n = lengths.pop() if lengths else 0
    return [{name: values[i] for name, values in columns.items()} for i in range(n)]


# ---------------------------------------------------------------------------
# 演習3-2: ランレングス符号化と辞書符号化
# ---------------------------------------------------------------------------

def rle_encode(values: Sequence[Any]) -> list[tuple[Any, int]]:
    runs: list[tuple[Any, int]] = []
    for v in values:
        if runs and runs[-1][0] == v:
            runs[-1] = (v, runs[-1][1] + 1)  # 直前と同じ値なら、回数を 1 増やすだけ
        else:
            runs.append((v, 1))
    return runs


def rle_decode(runs: Sequence[tuple[Any, int]]) -> list[Any]:
    out: list[Any] = []
    for value, count in runs:
        if count <= 0:
            raise ValueError(f"回数は 1 以上: {count}")
        out.extend([value] * count)
    return out


def dict_encode(values: Sequence[Any]) -> tuple[list[Any], list[int]]:
    # 辞書を値の昇順にすると、符号（整数）の大小と元の値の大小が一致する（順序を保つ辞書）。
    # 範囲条件（region >= 'k'）を、文字列に戻さずに整数の比較で評価できる
    dictionary = sorted(set(values))
    code_of = {v: i for i, v in enumerate(dictionary)}
    return dictionary, [code_of[v] for v in values]


def dict_decode(dictionary: Sequence[Any], codes: Sequence[int]) -> list[Any]:
    return [dictionary[c] for c in codes]


# ---------------------------------------------------------------------------
# 演習3-3: 大きさと読み取りコストのモデル
# ---------------------------------------------------------------------------

def row_store_size(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> int:
    return sum(value_size(row[c]) for row in rows for c in columns)


def column_size(values: Sequence[Any], encoding: str = "plain") -> int:
    if encoding == "plain":
        return sum(value_size(v) for v in values)
    if encoding == "rle":
        return sum(value_size(v) + 4 for v, _ in rle_encode(values))  # 値 + 4 バイトの回数
    if encoding == "dict":
        dictionary, _ = dict_encode(values)
        if not dictionary:
            return 0
        bits = max(1, math.ceil(math.log2(len(dictionary))))  # 符号 1 つに必要なビット数
        return sum(value_size(v) for v in dictionary) + math.ceil(len(values) * bits / 8)
    raise ValueError(f"未対応の符号化です: {encoding!r}")


def bytes_read_row_store(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> int:
    # 行指向では、ページに行がまるごと入っているので、1 列だけ必要でも全部の列を読むことになる
    return row_store_size(rows, columns)


def bytes_read_column_store(
    table: Mapping[str, Sequence[Any]], needed: Sequence[str], encodings: Mapping[str, str] | None = None
) -> int:
    encodings = encodings or {}
    # 列指向では、必要な列のファイル（ブロック）だけを読めばよい
    return sum(column_size(table[c], encodings.get(c, "plain")) for c in needed)


# ---------------------------------------------------------------------------
# 演習3-4: 符号化したまま集計する
# ---------------------------------------------------------------------------

def sum_rle(runs: Sequence[tuple[int, int]]) -> int:
    return sum(value * count for value, count in runs)  # 展開せずに「値 × 回数」を足す


def sales_by_region(columns: Mapping[str, Sequence[Any]], year: int) -> dict[str, int]:
    totals: dict[str, int] = {}
    for region, y, amount in zip(columns["region"], columns["year"], columns["amount"]):
        if y == year:
            totals[region] = totals.get(region, 0) + amount
    return dict(sorted(totals.items()))


def sales_by_region_encoded(
    year_runs: Sequence[tuple[int, int]],
    region_dictionary: Sequence[str],
    region_codes: Sequence[int],
    amounts: Sequence[int],
    year: int,
) -> dict[str, int]:
    totals = [0] * len(region_dictionary)
    seen = [False] * len(region_dictionary)
    pos = 0
    for value, count in year_runs:
        if value == year:
            # 該当する年の「行の範囲」だけを処理する。地域は整数の符号のまま配列の添字に使い、
            # 文字列に戻すのは最後の結果の作成時だけ（遅延実体化、late materialization）
            for i in range(pos, pos + count):
                code = region_codes[i]
                totals[code] += amounts[i]
                seen[code] = True
        pos += count  # 該当しない年の範囲は、中身を見ずに読み飛ばす
    return {region_dictionary[c]: totals[c] for c in range(len(region_dictionary)) if seen[c]}
