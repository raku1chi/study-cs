"""6.2 インデックスとクエリ処理 — 演習2 解答例: 結合アルゴリズム

演習の仕様は exercises/joins.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key
from typing import Any

Row = dict[str, Any]


@dataclass
class JoinStats:
    comparisons: int = 0
    hash_inserts: int = 0
    hash_probes: int = 0


def _non_null(rows: list[Row], key: str) -> list[Row]:
    # NULL（None）のキーは何とも一致しないので、最初に取り除いてよい
    return [row for row in rows if row[key] is not None]


# ---------------------------------------------------------------------------
# 演習2-1: 入れ子ループ結合
# ---------------------------------------------------------------------------

def nested_loop_join(
    left: list[Row], right: list[Row], left_key: str, right_key: str, stats: JoinStats | None = None
) -> list[tuple[Row, Row]]:
    stats = stats if stats is not None else JoinStats()
    lefts = _non_null(left, left_key)
    rights = _non_null(right, right_key)
    out: list[tuple[Row, Row]] = []
    # 外側の 1 行ごとに内側を全部なめる: 比較は |L| × |R| 回
    for l_row in lefts:
        lk = l_row[left_key]
        for r_row in rights:
            stats.comparisons += 1
            if lk == r_row[right_key]:
                out.append((l_row, r_row))
    return out


# ---------------------------------------------------------------------------
# 演習2-2: ハッシュ結合
# ---------------------------------------------------------------------------

def hash_join(
    left: list[Row], right: list[Row], left_key: str, right_key: str, stats: JoinStats | None = None
) -> list[tuple[Row, Row]]:
    stats = stats if stats is not None else JoinStats()
    lefts = _non_null(left, left_key)
    rights = _non_null(right, right_key)
    # 小さい方をビルド側にする（ハッシュ表がメモリに収まりやすく、作る手間も小さい）
    build_left = len(lefts) < len(rights)
    build, build_key, probe, probe_key = (
        (lefts, left_key, rights, right_key) if build_left else (rights, right_key, lefts, left_key)
    )
    table: dict[Any, list[Row]] = {}
    for row in build:  # ビルド: |小さい方| 回の登録
        table.setdefault(row[build_key], []).append(row)
        stats.hash_inserts += 1
    out: list[tuple[Row, Row]] = []
    for row in probe:  # プローブ: |大きい方| 回の検索
        stats.hash_probes += 1
        for match in table.get(row[probe_key], ()):
            # 結果は常に (左の行, 右の行) の向きにそろえる
            out.append((match, row) if build_left else (row, match))
    return out


# ---------------------------------------------------------------------------
# 演習2-3: ソートマージ結合
# ---------------------------------------------------------------------------

def sort_merge_join(
    left: list[Row],
    right: list[Row],
    left_key: str,
    right_key: str,
    stats: JoinStats | None = None,
    *,
    presorted: bool = False,
) -> list[tuple[Row, Row]]:
    stats = stats if stats is not None else JoinStats()

    def compare(a: Any, b: Any) -> int:
        stats.comparisons += 1
        return (a > b) - (a < b)

    lefts = _non_null(left, left_key)
    rights = _non_null(right, right_key)
    if not presorted:
        # 比較回数を数えるために cmp_to_key を使う（ソートは O(n log n) 回の比較）
        lefts = sorted(lefts, key=cmp_to_key(lambda a, b: compare(a[left_key], b[left_key])))
        rights = sorted(rights, key=cmp_to_key(lambda a, b: compare(a[right_key], b[right_key])))

    out: list[tuple[Row, Row]] = []
    i = j = 0
    n, m = len(lefts), len(rights)
    while i < n and j < m:
        c = compare(lefts[i][left_key], rights[j][right_key])
        if c < 0:
            i += 1
        elif c > 0:
            j += 1
        else:
            # 同じキーの「かたまり」を両側で見つけ、その直積を出力する（多対多に対応）
            key = lefts[i][left_key]
            i_end = i + 1
            while i_end < n and compare(lefts[i_end][left_key], key) == 0:
                i_end += 1
            j_end = j + 1
            while j_end < m and compare(rights[j_end][right_key], key) == 0:
                j_end += 1
            for l_row in lefts[i:i_end]:
                for r_row in rights[j:j_end]:
                    out.append((l_row, r_row))
            i, j = i_end, j_end
    return out
