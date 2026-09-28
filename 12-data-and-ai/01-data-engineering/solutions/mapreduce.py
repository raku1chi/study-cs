"""12.1 データ基盤とデータエンジニアリング — 演習1: インプロセス MapReduce（解答例）

演習の仕様は exercises/mapreduce.py の docstring を参照してください。
1 台のプロセスの中で、Google の MapReduce（2004）と同じ段階
「入力分割 → Map → Combiner → Partition → Shuffle/Sort → Reduce」を再現します。
"""
from __future__ import annotations

import itertools
import re
import zlib
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

KeyValue = tuple[Any, Any]
Mapper = Callable[[Any], Iterable[KeyValue]]
Reducer = Callable[[Any, list[Any]], Iterable[KeyValue]]
Partitioner = Callable[[Any, int], int]

COUNTER_NAMES = (
    "map_input_records",
    "map_output_records",
    "combine_output_records",
    "shuffle_records",
    "reduce_input_groups",
    "reduce_output_records",
)


def tokenize(line: str) -> list[str]:
    """英小文字・数字の連続を 1 単語とみなす簡易トークナイザ（実装済み）。"""
    return re.findall(r"[a-z0-9]+", line.lower())


@dataclass
class JobResult:
    """MapReduce ジョブの実行結果（実装済み）。"""

    partitions: list[list[KeyValue]]
    counters: dict[str, int] = field(default_factory=dict)
    shuffle_sizes: list[int] = field(default_factory=list)

    def records(self) -> list[KeyValue]:
        return [kv for part in self.partitions for kv in part]

    def as_dict(self) -> dict[Any, Any]:
        out: dict[Any, Any] = {}
        for key, value in self.records():
            if key in out:
                raise ValueError(f"キーが重複しています: {key!r}")
            out[key] = value
        return out


# ---------------------------------------------------------------------------
# 演習1a: パーティショナと入力分割
# ---------------------------------------------------------------------------

def hash_partitioner(key: Any, num_partitions: int) -> int:
    if num_partitions < 1:
        raise ValueError(f"num_partitions は 1 以上: {num_partitions}")
    # 組み込みの hash() は str に対してプロセスごとにランダム化される（PYTHONHASHSEED）。
    # 分散環境では全マシンで同じキーが同じ Reducer に届かなければならないので、
    # 入力だけで決まる安定したハッシュ（ここでは CRC32）を使う。
    return zlib.crc32(repr(key).encode("utf-8")) % num_partitions


def split_input(records: list[Any], num_splits: int) -> list[list[Any]]:
    if num_splits < 1:
        raise ValueError(f"num_splits は 1 以上: {num_splits}")
    base, extra = divmod(len(records), num_splits)
    splits: list[list[Any]] = []
    start = 0
    for i in range(num_splits):
        size = base + (1 if i < extra else 0)  # 先頭の extra 個が 1 件多い
        splits.append(records[start:start + size])
        start += size
    return splits


# ---------------------------------------------------------------------------
# 演習1b: MapReduce の実行エンジン
# ---------------------------------------------------------------------------

def _sorted_groups(pairs: list[KeyValue]) -> Iterator[tuple[Any, list[Any]]]:
    """キーで安定ソートし、同じキーの値をまとめて返す（Shuffle/Sort の本体）。"""
    ordered = sorted(pairs, key=lambda kv: kv[0])  # 値は比較しない（比較不能でもよい）
    for key, group in itertools.groupby(ordered, key=lambda kv: kv[0]):
        yield key, [v for _, v in group]


def _check_pair(kv: Any, where: str) -> KeyValue:
    if not (isinstance(kv, tuple) and len(kv) == 2):
        raise ValueError(f"{where} は (key, value) のタプルを返してください: {kv!r}")
    return kv


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
    if num_partitions < 1 or num_map_tasks < 1:
        raise ValueError("num_partitions と num_map_tasks は 1 以上で指定してください")
    counters = dict.fromkeys(COUNTER_NAMES, 0)
    # 各 Reducer 宛ての「中間ファイル」。実際の MapReduce では Map タスクのローカルディスクに書かれ、
    # Reducer がネットワーク越しに取りに来る（これがシャッフルのコスト）。
    buckets: list[list[KeyValue]] = [[] for _ in range(num_partitions)]

    for split in split_input(list(records), num_map_tasks):
        # --- Map フェーズ（Map タスク 1 つ分）---
        emitted: list[KeyValue] = []
        for record in split:
            counters["map_input_records"] += 1
            for kv in mapper(record):
                emitted.append(_check_pair(kv, "mapper"))
        counters["map_output_records"] += len(emitted)

        # --- Combiner: Map タスクの中だけで事前集約し、シャッフル量を減らす ---
        if combiner is not None:
            combined: list[KeyValue] = []
            for key, values in _sorted_groups(emitted):
                for kv in combiner(key, values):
                    combined.append(_check_pair(kv, "combiner"))
            emitted = combined
            counters["combine_output_records"] += len(emitted)

        # --- Partition: どの Reducer に送るかをキーだけで決める ---
        for key, value in emitted:
            p = partitioner(key, num_partitions)
            if not isinstance(p, int) or not 0 <= p < num_partitions:
                raise ValueError(f"partitioner が範囲外の値を返しました: {p!r}")
            buckets[p].append((key, value))

    # --- Shuffle/Sort → Reduce（Reducer ごと）---
    partitions: list[list[KeyValue]] = []
    for bucket in buckets:
        counters["shuffle_records"] += len(bucket)
        out: list[KeyValue] = []
        for key, values in _sorted_groups(bucket):
            counters["reduce_input_groups"] += 1
            for kv in reducer(key, values):
                out.append(_check_pair(kv, "reducer"))
        counters["reduce_output_records"] += len(out)
        partitions.append(out)

    return JobResult(partitions, counters, [len(b) for b in buckets])


# ---------------------------------------------------------------------------
# 演習1c: ジョブ（Map 関数と Reduce 関数を書く）
# ---------------------------------------------------------------------------

def word_count(
    lines: Iterable[str],
    *,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
    use_combiner: bool = True,
) -> JobResult:
    def mapper(line: str) -> Iterator[KeyValue]:
        for word in tokenize(line):
            yield word, 1

    def reducer(word: str, counts: list[int]) -> Iterator[KeyValue]:
        # 足し算は結合的・可換なので、Reducer をそのまま Combiner に使える
        yield word, sum(counts)

    return run_mapreduce(
        lines,
        mapper,
        reducer,
        num_partitions=num_partitions,
        num_map_tasks=num_map_tasks,
        combiner=reducer if use_combiner else None,
    )


def inverted_index(
    docs: dict[str, str],
    *,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
) -> JobResult:
    def mapper(record: tuple[str, str]) -> Iterator[KeyValue]:
        doc_id, text = record
        # 同じ文書内の重複は Map 側で除く（ローカル集約）。順序は初出順で決定的にする
        for term in dict.fromkeys(tokenize(text)):
            yield term, doc_id

    def reducer(term: str, doc_ids: list[str]) -> Iterator[KeyValue]:
        yield term, sorted(set(doc_ids))

    return run_mapreduce(
        list(docs.items()),
        mapper,
        reducer,
        num_partitions=num_partitions,
        num_map_tasks=num_map_tasks,
    )


def reduce_side_join(
    left: list[dict[str, Any]],
    right: list[dict[str, Any]],
    *,
    left_key: str,
    right_key: str,
    num_partitions: int = 4,
    num_map_tasks: int = 4,
) -> JobResult:
    # 2 つの入力を 1 本のレコード列にまとめ、どちらの入力から来たかをタグで区別する
    tagged = [("L", row) for row in left] + [("R", row) for row in right]

    def mapper(record: tuple[str, dict[str, Any]]) -> Iterator[KeyValue]:
        tag, row = record
        key = row.get(left_key if tag == "L" else right_key)
        if key is None:
            return  # SQL と同じく NULL のキーはどの行とも一致しない
        yield key, (tag, row)

    def reducer(key: Any, values: list[tuple[str, dict[str, Any]]]) -> Iterator[KeyValue]:
        # 同じキーを持つ行はすべて同じ Reducer に集まる。ここで片側をメモリに保持する必要があり、
        # 巨大なキー（ホットキー）があると 1 つの Reducer だけが遅くなる・メモリが溢れる（スキュー）
        lefts = [row for tag, row in values if tag == "L"]
        rights = [row for tag, row in values if tag == "R"]
        for lrow in lefts:
            for rrow in rights:
                yield key, {**lrow, **rrow}

    return run_mapreduce(
        tagged,
        mapper,
        reducer,
        num_partitions=num_partitions,
        num_map_tasks=num_map_tasks,
    )
