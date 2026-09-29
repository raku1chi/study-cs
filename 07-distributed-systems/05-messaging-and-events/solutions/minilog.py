"""7.5 メッセージングとイベント駆動 — 演習: パーティション分割されたログ型ブローカー（解答例）

演習の仕様は exercises/minilog.py の docstring を参照してください。
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

TopicPartition = tuple[str, int]


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    key: str | None
    value: Any


class CommitFailedError(Exception):
    pass


# ---------------------------------------------------------------------------
# 演習1: キーによるパーティションの決定と、レンジ割り当て
# ---------------------------------------------------------------------------


def partition_for_key(key: str, num_partitions: int) -> int:
    if num_partitions < 1:
        raise ValueError(f"パーティション数は 1 以上です: {num_partitions}")
    # 組み込みの hash() はプロセスごとに値が変わるので使わない。同じキーは常に同じパーティションへ
    return zlib.crc32(key.encode("utf-8")) % num_partitions


def range_assign(members: Iterable[str], num_partitions: int) -> dict[str, list[int]]:
    ordered = sorted(members)
    if not ordered:
        return {}
    per_member, extra = divmod(num_partitions, len(ordered))
    result: dict[str, list[int]] = {}
    start = 0
    for i, member in enumerate(ordered):
        count = per_member + (1 if i < extra else 0)  # 先頭の extra 人が 1 つ多く持つ
        result[member] = list(range(start, start + count))
        start += count
    return result


# ---------------------------------------------------------------------------
# 演習2: ブローカー（ログとコンシューマグループの調整役）
# ---------------------------------------------------------------------------


@dataclass
class _Group:
    members: dict[str, list[str]] = field(default_factory=dict)  # メンバー → 購読するトピック
    generation: int = 0
    assignments: dict[str, list[TopicPartition]] = field(default_factory=dict)
    committed: dict[TopicPartition, int] = field(default_factory=dict)


class Broker:
    def __init__(self) -> None:
        self._logs: dict[str, list[list[Record]]] = {}
        self._round_robin: dict[str, int] = {}
        self._groups: dict[str, _Group] = {}

    # ---- ログ ----

    def create_topic(self, topic: str, partitions: int) -> None:
        if topic in self._logs:
            raise ValueError(f"トピック {topic} は作成済みです")
        if partitions < 1:
            raise ValueError(f"パーティション数は 1 以上です: {partitions}")
        self._logs[topic] = [[] for _ in range(partitions)]
        self._round_robin[topic] = 0

    def partitions(self, topic: str) -> int:
        return len(self._log(topic))

    def _log(self, topic: str) -> list[list[Record]]:
        if topic not in self._logs:
            raise KeyError(topic)
        return self._logs[topic]

    def _partition(self, topic: str, partition: int) -> list[Record]:
        log = self._log(topic)
        if not 0 <= partition < len(log):
            raise ValueError(f"{topic} にパーティション {partition} はありません")
        return log[partition]

    def produce(self, topic: str, value: Any, key: str | None = None) -> tuple[int, int]:
        log = self._log(topic)
        if key is None:
            partition = self._round_robin[topic] % len(log)  # キーがなければ順番に散らす（順序の保証はない）
            self._round_robin[topic] += 1
        else:
            partition = partition_for_key(key, len(log))
        records = log[partition]
        record = Record(topic, partition, len(records), key, value)
        records.append(record)  # 追記のみ。オフセットはパーティション内の通し番号
        return partition, record.offset

    def fetch(self, topic: str, partition: int, offset: int, max_records: int = 100) -> list[Record]:
        records = self._partition(topic, partition)
        if not 0 <= offset <= len(records):
            raise ValueError(f"オフセット {offset} は範囲外です（0〜{len(records)}）")
        if max_records < 1:
            raise ValueError("max_records は 1 以上です")
        return records[offset : offset + max_records]

    def end_offset(self, topic: str, partition: int) -> int:
        return len(self._partition(topic, partition))

    # ---- コンシューマグループ ----

    def _group(self, group: str) -> _Group:
        return self._groups.setdefault(group, _Group())

    def _rebalance(self, g: _Group) -> None:
        # メンバーが変わるたびに世代を進め、全員の割り当てを計算し直す（eager リバランスの簡略版）
        g.generation += 1
        g.assignments = {m: [] for m in g.members}
        for topic in sorted({t for topics in g.members.values() for t in topics}):
            subscribers = [m for m, topics in g.members.items() if topic in topics]
            for member, parts in range_assign(subscribers, self.partitions(topic)).items():
                g.assignments[member].extend((topic, p) for p in parts)

    def join_group(self, group: str, member_id: str, topics: Sequence[str]) -> int:
        for t in topics:
            self._log(t)  # 未知のトピックなら KeyError
        g = self._group(group)
        g.members[member_id] = list(topics)
        self._rebalance(g)
        return g.generation

    def leave_group(self, group: str, member_id: str) -> None:
        g = self._group(group)
        if g.members.pop(member_id, None) is not None:
            self._rebalance(g)

    def generation(self, group: str) -> int:
        return self._group(group).generation

    def assignment(self, group: str, member_id: str) -> list[TopicPartition]:
        return sorted(self._group(group).assignments.get(member_id, []))

    def commit(self, group: str, member_id: str, generation: int, offsets: Mapping[TopicPartition, int]) -> None:
        g = self._group(group)
        if member_id not in g.members or generation != g.generation:
            # グループから外された（ゾンビ）か、リバランスの前の世代のままのコンシューマ。
            # 受け付けると、今の担当者の進捗を古い値で上書きしてしまう（世代番号によるフェンシング）
            raise CommitFailedError(f"{member_id}: 世代 {generation} のコミットは無効です（現在 {g.generation}）")
        owned = set(g.assignments.get(member_id, []))
        for tp, offset in offsets.items():
            if tp not in owned:
                raise CommitFailedError(f"{member_id} は {tp} を担当していません")
            if not 0 <= offset <= self.end_offset(*tp):
                raise ValueError(f"{tp} のオフセット {offset} は範囲外です")
        for tp, offset in offsets.items():
            g.committed[tp] = offset

    def committed(self, group: str, topic: str, partition: int) -> int | None:
        return self._group(group).committed.get((topic, partition))


# ---------------------------------------------------------------------------
# 演習3: コンシューマ
# ---------------------------------------------------------------------------


class Consumer:
    def __init__(self, broker: Broker, group: str, member_id: str, topics: Sequence[str]) -> None:
        self.broker = broker
        self.group = group
        self.member_id = member_id
        self.topics = list(topics)
        self.generation = -1
        self.positions: dict[TopicPartition, int] = {}
        broker.join_group(group, member_id, self.topics)
        self._sync()

    def _sync(self) -> None:
        generation = self.broker.generation(self.group)
        if generation != self.generation:
            # リバランスが起きた: 新しい割り当てを受け取り、読む位置をコミット済みのオフセットに戻す。
            # コミットしていない進捗は捨てられる → 次の担当者（や自分）が同じレコードを再び読む（at-least-once）
            self.generation = generation
            assigned = self.broker.assignment(self.group, self.member_id)
            self.positions = {tp: self.broker.committed(self.group, *tp) or 0 for tp in assigned}

    def assignment(self) -> list[TopicPartition]:
        self._sync()
        return sorted(self.positions)

    def position(self, topic: str, partition: int) -> int:
        return self.positions[(topic, partition)]

    def poll(self, max_records: int = 100) -> list[Record]:
        self._sync()
        out: list[Record] = []
        for tp in sorted(self.positions):
            if len(out) >= max_records:
                break
            records = self.broker.fetch(tp[0], tp[1], self.positions[tp], max_records - len(out))
            if records:
                self.positions[tp] = records[-1].offset + 1
                out.extend(records)
        return out

    def commit(self) -> None:
        self.broker.commit(self.group, self.member_id, self.generation, dict(self.positions))

    def close(self) -> None:
        # 正常終了: 進捗をコミットしてからグループを抜ける。世代が古ければコミットせずに抜ける
        if self.generation == self.broker.generation(self.group):
            self.commit()
        self.broker.leave_group(self.group, self.member_id)

    def crash(self) -> None:
        # 異常終了: コミットせずにいなくなる（ブローカーがセッションのタイムアウトで検知した、という簡略化）
        self.broker.leave_group(self.group, self.member_id)
