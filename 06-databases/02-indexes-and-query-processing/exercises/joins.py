"""6.2 インデックスとクエリ処理 — 演習2: 結合アルゴリズムを実装する

DBMS の実行エンジンが使う 3 つの等価結合（equi-join）のアルゴリズムを実装し、
比較やハッシュ表の操作の回数を数えて、コストの違いを体感します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.2
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_joins

共通の約束:
    - 行は dict。left の行の left_key 列と、right の行の right_key 列が等しい組を結合する。
    - 結果は (left の行, right の行) のタプルのリスト。行の順序は問わない（テストは並べ替えて比べる）。
    - キーが None（SQL の NULL）の行は、どの行とも結合しない。比較の回数にも数えない。
    - 同じキーが両側に複数あれば、そのすべての組み合わせを出力する（多対多）。
    - 入力のリストを書き換えないこと（並べ替えるならコピーする）。
    - stats（JoinStats）が渡されたら、そこに回数を加算する。None なら数えなくてよい。
    - キーの列が行にない場合は KeyError を送出すること（row[key] で参照すれば自然に送出される。
      row.get(key) を使うと None とみなされて送出されないので注意）。

使ってはいけないもの: 結合そのものを行うライブラリ（sqlite3 など）。
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cmp_to_key  # noqa: F401  演習2-3 で比較回数を数えるのに使えます
from typing import Any

Row = dict[str, Any]


@dataclass
class JoinStats:
    """結合のコストを数えるカウンタ（提供済み）。

    - comparisons: キーどうしの比較（==, <, > の判定）の回数
    - hash_inserts: ハッシュ表への登録の回数
    - hash_probes: ハッシュ表の検索の回数
    """

    comparisons: int = 0
    hash_inserts: int = 0
    hash_probes: int = 0


# ---------------------------------------------------------------------------
# 演習2-1（★☆☆）: 入れ子ループ結合（nested loop join）
# ---------------------------------------------------------------------------

def nested_loop_join(
    left: list[Row], right: list[Row], left_key: str, right_key: str, stats: JoinStats | None = None
) -> list[tuple[Row, Row]]:
    """左の各行について右の全行と比べる、最も素朴な結合。

    キーが None でない左の行と右の行のすべての組について 1 回ずつ比較し、
    stats.comparisons を 1 増やす（合計で「左の非 NULL 行数 × 右の非 NULL 行数」回）。

    >>> L = [{"id": 1}, {"id": 2}]
    >>> R = [{"cid": 2, "x": "a"}, {"cid": 2, "x": "b"}, {"cid": 3, "x": "c"}]
    >>> s = JoinStats()
    >>> [(l["id"], r["x"]) for l, r in nested_loop_join(L, R, "id", "cid", s)]
    [(2, 'a'), (2, 'b')]
    >>> s.comparisons
    6
    """
    raise NotImplementedError("演習2-1: nested_loop_join を実装してください")


# ---------------------------------------------------------------------------
# 演習2-2（★★☆）: ハッシュ結合（hash join）
# ---------------------------------------------------------------------------

def hash_join(
    left: list[Row], right: list[Row], left_key: str, right_key: str, stats: JoinStats | None = None
) -> list[tuple[Row, Row]]:
    """小さい方の入力でハッシュ表を作り（ビルド）、大きい方の各行で引く（プローブ）結合。

    - ビルド側: キーが None でない行の数が少ない方。同数なら right をビルド側にする。
    - ビルド側の各行（キーが None でないもの）を dict（キー → 行のリスト）に登録するたびに
      stats.hash_inserts を 1 増やす。
    - プローブ側の各行（キーが None でないもの）で dict を引くたびに stats.hash_probes を 1 増やす。
    - comparisons は数えなくてよい（dict の中の比較は数えられないため）。
    - どちらをビルド側にしても、結果の組は (left の行, right の行) の向きにすること。

    合計の手間は「左 + 右」の行数に比例し、入れ子ループの「左 × 右」よりずっと小さい。
    ただし等価条件（=）の結合にしか使えない。
    """
    raise NotImplementedError("演習2-2: hash_join を実装してください")


# ---------------------------------------------------------------------------
# 演習2-3（★★☆）: ソートマージ結合（sort-merge join）
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
    """両方の入力をキーで並べ替え、先頭から同時にたどって結合する。

    - presorted=False: キーが None でない行を、キーの昇順に並べ替える（コピーを作る）。
      並べ替えで行ったキーの比較も stats.comparisons に数えること。
    - presorted=True: 入力はすでにキーの昇順に並んでいるとみなし、並べ替えない
      （インデックスを順に読んだ結果を入力にする場合にあたる）。
    - マージ: 2 つの位置 i, j を進めながらキーを比較する（比較 1 回ごとに comparisons を 1 増やす）。
      左が小さければ i を、右が小さければ j を進める。等しければ、両側で同じキーが続く範囲を
      見つけ、その範囲どうしのすべての組を出力してから、両方をその範囲の後ろへ進める。

    マージの比較回数は「左 + 右」の行数の数倍以内に収まり、並べ替えは O(n log n) 回の比較で済む。

    ヒント: sorted(rows, key=cmp_to_key(比較関数)) を使うと、比較関数の中で回数を数えられる。
    比較関数は a < b なら負、a == b なら 0、a > b なら正を返す。
    """
    raise NotImplementedError("演習2-3: sort_merge_join を実装してください")
