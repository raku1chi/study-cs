"""12.1 データ基盤とデータエンジニアリング — 演習1: インプロセス MapReduce

1 つのプロセスの中で、MapReduce（Dean & Ghemawat, 2004）の処理段階
「入力分割 → Map → Combiner → Partition → Shuffle/Sort → Reduce」を再現します。
分散はしませんが、各段階で何件のレコードが流れるか（カウンタ）を記録するので、
Combiner がシャッフル量をどれだけ減らすか、キーの偏り（スキュー）がどう現れるかを観察できます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.1
    python3 tools/check.py -v 12.1

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_mapreduce

制約:
    - 標準ライブラリのみ。itertools.groupby や sorted は自由に使ってかまいません。
    - パーティショナに組み込みの hash() を使ってはいけません（理由は hash_partitioner の docstring）。
"""
from __future__ import annotations

import itertools  # noqa: F401  run_mapreduce で使えます（groupby）
import re
import zlib  # noqa: F401  hash_partitioner で使えます（crc32）
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator  # noqa: F401

KeyValue = tuple[Any, Any]
Mapper = Callable[[Any], Iterable[KeyValue]]  # レコード 1 件 → (key, value) を 0 個以上
Reducer = Callable[[Any, list[Any]], Iterable[KeyValue]]  # (key, 値のリスト) → (key, value) を 0 個以上
Partitioner = Callable[[Any, int], int]  # (key, パーティション数) → 0〜パーティション数-1

# run_mapreduce が JobResult.counters に記録するカウンタ名
COUNTER_NAMES = (
    "map_input_records",  # Map に入力されたレコード数
    "map_output_records",  # Map が出力した (key, value) の数
    "combine_output_records",  # Combiner が出力した数（Combiner なしなら 0 のまま）
    "shuffle_records",  # Reducer に送られた（シャッフルされた）レコード数
    "reduce_input_groups",  # Reducer が呼ばれた回数（= 異なるキーの数）
    "reduce_output_records",  # Reducer が出力した数
)


def tokenize(line: str) -> list[str]:
    """英小文字・数字の連続を 1 単語とみなす簡易トークナイザ（実装済み）。

    >>> tokenize("The dog barks. The fox runs!")
    ['the', 'dog', 'barks', 'the', 'fox', 'runs']
    """
    return re.findall(r"[a-z0-9]+", line.lower())


@dataclass
class JobResult:
    """MapReduce ジョブの実行結果（実装済み）。

    - partitions[i]: i 番目の Reducer の出力。キーの昇順に並ぶ（実際の MapReduce の
      出力ファイル part-0000i に相当）。
    - counters: COUNTER_NAMES の各カウンタの値。
    - shuffle_sizes[i]: i 番目の Reducer が受け取ったレコード数（スキューの観察用）。
    """

    partitions: list[list[KeyValue]]
    counters: dict[str, int] = field(default_factory=dict)
    shuffle_sizes: list[int] = field(default_factory=list)

    def records(self) -> list[KeyValue]:
        """全パーティションの出力をパーティション順に連結して返す。"""
        return [kv for part in self.partitions for kv in part]

    def as_dict(self) -> dict[Any, Any]:
        """出力を {key: value} の辞書にする。キーが重複していれば ValueError。"""
        out: dict[Any, Any] = {}
        for key, value in self.records():
            if key in out:
                raise ValueError(f"キーが重複しています: {key!r}")
            out[key] = value
        return out


# ---------------------------------------------------------------------------
# 演習1a（★☆☆）: パーティショナと入力分割
# ---------------------------------------------------------------------------

def hash_partitioner(key: Any, num_partitions: int) -> int:
    """キーを 0〜num_partitions-1 のどれかに割り当てる。num_partitions < 1 なら ValueError。

    要件:
    - 同じキーは、いつ・どのプロセスで計算しても同じ番号になること。
    - 多数のキーが各パーティションにおおむね均等に散らばること。

    組み込みの hash() は使わないこと。str の hash() はプロセスごとにランダム化される
    （環境変数 PYTHONHASHSEED）ため、分散環境では「同じキーが別々の Reducer に届く」
    という致命的なバグになる。

    ヒント: repr(key) を UTF-8 でバイト列にし、zlib.crc32() で 32 ビットの値にしてから
    num_partitions で割った余りを返す。
    """
    raise NotImplementedError("演習1a: hash_partitioner を実装してください")


def split_input(records: list[Any], num_splits: int) -> list[list[Any]]:
    """レコード列を、順序を保ったまま num_splits 個の連続した塊（入力スプリット）に分ける。

    - 各スプリットの件数の差は最大 1。件数の多いスプリットを先頭側に置く。
    - レコードが足りなければ空のスプリットができてよい（戻り値の長さは常に num_splits）。
    - num_splits < 1 なら ValueError。

    >>> split_input(list(range(10)), 3)
    [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]]
    >>> split_input([1, 2], 4)
    [[1], [2], [], []]
    """
    raise NotImplementedError("演習1a: split_input を実装してください")


# ---------------------------------------------------------------------------
# 演習1b（★★☆）: MapReduce の実行エンジン
# ---------------------------------------------------------------------------

def run_mapreduce(
    records: Iterable[Any],
    mapper: Mapper,
    reducer: Reducer,
    *,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
    combiner: Reducer | None = None,
    partitioner: Partitioner = hash_partitioner,
) -> JobResult:
    """MapReduce ジョブを 1 プロセス内で実行する。

    手順:
    1. records を split_input で num_map_tasks 個のスプリットに分ける（1 スプリット = 1 Map タスク）。
    2. 各 Map タスクで、スプリット内の各レコードに mapper を適用し、出力を集める。
    3. combiner が指定されていれば、その Map タスクの出力だけをキーでまとめて combiner に渡し、
       その出力で置き換える（Map タスクをまたいだ集約はしない）。
    4. 各 (key, value) を partitioner(key, num_partitions) 番のバケツに入れる。
       戻り値が int でない、または範囲外なら ValueError。
    5. バケツごとに、キーで **安定ソート** してから同じキーの値をリストにまとめ、
       reducer(key, values) を呼ぶ。values の並びは「Map タスクの順 → 各タスク内の出力順」。
       ソートはキーだけで行う（値は比較できないこともある）。
    6. JobResult(partitions, counters, shuffle_sizes) を返す。

    - mapper / combiner / reducer が (key, value) の 2 要素タプル以外を返したら ValueError。
    - num_partitions < 1 または num_map_tasks < 1 なら ValueError。
    - counters には COUNTER_NAMES のすべてのキーを含める（使わないものは 0）。

    ヒント: itertools.groupby は「隣り合う同じキー」をまとめるので、先にソートが必要。
    """
    raise NotImplementedError("演習1b: run_mapreduce を実装してください")


# ---------------------------------------------------------------------------
# 演習1c（★★☆）: ジョブを書く（Map 関数と Reduce 関数）
# ---------------------------------------------------------------------------

def word_count(
    lines: Iterable[str],
    *,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
    use_combiner: bool = True,
) -> JobResult:
    """単語の出現回数を数える。出力は (単語, 回数)。

    - 単語の切り出しには tokenize() を使う。
    - use_combiner=True なら、Reducer と同じ関数を Combiner にも使う
      （足し算は結合的・可換なので、Map 側で部分和を取っても結果は変わらない）。

    >>> sorted(word_count(["a b a"]).as_dict().items())   # 出力はパーティション順なので並べ替えて比べる
    [('a', 2), ('b', 1)]
    """
    raise NotImplementedError("演習1c: word_count を実装してください")


def inverted_index(
    docs: dict[str, str],
    *,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
) -> JobResult:
    """転置インデックスを作る。入力は {文書ID: 本文}、出力は (単語, 文書IDの昇順リスト)。

    - 入力レコードは (文書ID, 本文) のタプルにして run_mapreduce に渡す。
    - 同じ文書に同じ単語が何度出てきても、Map の出力は 1 回だけにする（Map 側で重複除去）。
    - Reducer は文書 ID を重複なしの昇順リストにする。

    >>> inverted_index({"d1": "big data", "d2": "data"}).as_dict()["data"]
    ['d1', 'd2']
    """
    raise NotImplementedError("演習1c: inverted_index を実装してください")


def reduce_side_join(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    left_key: str,
    right_key: str,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
) -> JobResult:
    """2 つの表（辞書のリスト）を Reduce 側で内部結合（inner join）する。

    - 入力レコードを ("L", 行) / ("R", 行) のようにタグ付けして 1 本の列にまとめる。
    - Mapper は結合キーの値をキーにして (key, (タグ, 行)) を出力する。
      キーが None（または列がない）の行は出力しない（SQL と同じく NULL は何とも一致しない）。
    - Reducer は同じキーの左の行と右の行の直積をとり、(key, {**左の行, **右の行}) を出力する
      （同名の列は右の値で上書き）。

    考えてみよう: 1 つのキーに行が極端に集中すると、何が起きるだろうか。
    """
    raise NotImplementedError("演習1c: reduce_side_join を実装してください")
