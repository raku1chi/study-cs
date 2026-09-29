"""7.5 メッセージングとイベント駆動 — 演習: パーティション分割されたログ型ブローカー（Kafka の縮小版）

Kafka のようなログ型のブローカーでは、トピックが複数のパーティションに分かれ、各パーティションは
追記しかできないログ（レコードの列）です。コンシューマは「どこまで読んだか」（オフセット）を自分で管理し、
コンシューマグループの中では、1 つのパーティションを 1 人のメンバーだけが読みます。
この演習では、その仕組みをメモリ上で実装し、次のことをテストで確かめます。

    - 同じキーのレコードは同じパーティションに入り、書いた順に読まれる
    - メンバーの参加・離脱でパーティションが割り当て直される（リバランス）
    - 処理した後、コミットする前に落ちると、同じレコードが再び配送される（at-least-once）
    - グループから外されたメンバー（ゾンビ）のコミットは、世代番号で拒否される

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.5
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_minilog

用語:
    オフセット: パーティション内のレコードの通し番号（0 から）。
    コミット済みオフセット: グループが「次に読むべき位置」として記録した値（最後に処理したレコードのオフセット + 1）。
    世代（generation）: グループのメンバー構成が変わる（リバランスが起きる）たびに 1 増える番号。
"""
from __future__ import annotations

import zlib  # noqa: F401  演習1で使います（zlib.crc32）
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

TopicPartition = tuple[str, int]  # (トピック名, パーティション番号)


@dataclass(frozen=True)
class Record:
    topic: str
    partition: int
    offset: int
    key: str | None
    value: Any


class CommitFailedError(Exception):
    """コミットが拒否された（グループから外された、世代が古い、担当していないパーティション）。"""


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: キーによるパーティションの決定と、レンジ割り当て
# ---------------------------------------------------------------------------


def partition_for_key(key: str, num_partitions: int) -> int:
    """zlib.crc32(key を UTF-8 で符号化したバイト列) % num_partitions を返す。num_partitions < 1 なら ValueError。

    （Kafka の既定の分割は murmur2 ハッシュを使うが、考え方は同じ。組み込みの hash() は使わないこと）
    """
    raise NotImplementedError("演習1: partition_for_key を実装してください")


def range_assign(members: Iterable[str], num_partitions: int) -> dict[str, list[int]]:
    """Kafka の RangeAssignor と同じ方法で、パーティション 0〜num_partitions-1 をメンバーに割り当てる。

    メンバーを名前の昇順に並べ、q, r = divmod(パーティション数, メンバー数) として、
    先頭から r 人には q + 1 個、残りには q 個の **連続した** パーティションを順に割り当てる。
    メンバーが空なら {}。

    >>> range_assign(["b", "a"], 5)
    {'a': [0, 1, 2], 'b': [3, 4]}
    """
    raise NotImplementedError("演習1: range_assign を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★★）: ブローカー（ログとコンシューマグループの調整役）
# ---------------------------------------------------------------------------


class Broker:
    """メモリ上のログ型ブローカー。

    ログ:
        - create_topic(topic, partitions): 作成済みなら ValueError、partitions < 1 なら ValueError。
        - partitions(topic): パーティション数。
        - produce(topic, value, key=None) -> (partition, offset):
            key があれば partition_for_key(key, パーティション数) のパーティションへ、
            key が None ならトピックごとのラウンドロビン（0, 1, 2, …, 0, 1, …）で追記する。
            オフセットは、そのパーティションのそれまでのレコード数（0 から）。
        - fetch(topic, partition, offset, max_records=100) -> list[Record]:
            offset から最大 max_records 件。offset が 0〜end_offset の範囲外、max_records < 1 なら ValueError。
            offset == end_offset なら []。
        - end_offset(topic, partition): 次に書かれるオフセット（= レコード数）。
        - 未知のトピックは KeyError、存在しないパーティション番号は ValueError。

    コンシューマグループ（グループは初めて参照されたときに作られる。世代は 0 から）:
        - join_group(group, member_id, topics) -> 新しい世代:
            メンバーを登録（既存ならトピックを更新）してリバランスする。未知のトピックなら KeyError。
        - leave_group(group, member_id): メンバーだったら削除してリバランスする（メンバーでなければ何もしない）。
        - リバランス: 世代を 1 増やし、トピックごとに、そのトピックを購読しているメンバーだけで
          range_assign した結果を、メンバーごとの (topic, partition) のリストにまとめる。
        - generation(group): 現在の世代。
        - assignment(group, member_id): そのメンバーの (topic, partition) の昇順リスト（メンバーでなければ []）。
        - commit(group, member_id, generation, offsets):
            * メンバーでない、または generation が現在の世代と違えば CommitFailedError（ゾンビや古い世代の拒否）。
            * offsets の (topic, partition) がそのメンバーの担当でなければ CommitFailedError。
            * オフセットが 0〜end_offset の範囲外なら ValueError。
            * 検査をすべて通ったら、まとめて記録する（途中で失敗したら何も記録しない）。
        - committed(group, topic, partition): コミット済みオフセット（なければ None）。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習2: Broker.__init__ を実装してください")

    def create_topic(self, topic: str, partitions: int) -> None:
        raise NotImplementedError("演習2: Broker.create_topic を実装してください")

    def partitions(self, topic: str) -> int:
        raise NotImplementedError("演習2: Broker.partitions を実装してください")

    def produce(self, topic: str, value: Any, key: str | None = None) -> tuple[int, int]:
        raise NotImplementedError("演習2: Broker.produce を実装してください")

    def fetch(self, topic: str, partition: int, offset: int, max_records: int = 100) -> list[Record]:
        raise NotImplementedError("演習2: Broker.fetch を実装してください")

    def end_offset(self, topic: str, partition: int) -> int:
        raise NotImplementedError("演習2: Broker.end_offset を実装してください")

    def join_group(self, group: str, member_id: str, topics: Sequence[str]) -> int:
        raise NotImplementedError("演習2: Broker.join_group を実装してください")

    def leave_group(self, group: str, member_id: str) -> None:
        raise NotImplementedError("演習2: Broker.leave_group を実装してください")

    def generation(self, group: str) -> int:
        raise NotImplementedError("演習2: Broker.generation を実装してください")

    def assignment(self, group: str, member_id: str) -> list[TopicPartition]:
        raise NotImplementedError("演習2: Broker.assignment を実装してください")

    def commit(self, group: str, member_id: str, generation: int, offsets: Mapping[TopicPartition, int]) -> None:
        raise NotImplementedError("演習2: Broker.commit を実装してください")

    def committed(self, group: str, topic: str, partition: int) -> int | None:
        raise NotImplementedError("演習2: Broker.committed を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: コンシューマ
# ---------------------------------------------------------------------------


class Consumer:
    """コンシューマグループの 1 メンバー。

    属性: broker, group, member_id, topics, generation（初期値 -1）, positions（(topic, partition) → 次に読む位置）

    - __init__: broker.join_group でグループに参加し、_sync 相当の処理で割り当てを受け取る。
    - 同期（poll や assignment のたびに最初に行う）: broker.generation(group) が自分の generation と違えば
      （リバランスが起きていたら）、generation を更新し、assignment を受け取り直して、**すべての** 担当パーティションの
      positions を、コミット済みオフセット（なければ 0）にリセットする。コミットしていない進捗は捨てる。
    - assignment(): 同期してから、担当する (topic, partition) の昇順リストを返す。
    - position(topic, partition): 次に読む位置。
    - poll(max_records=100): 同期してから、担当パーティションを (topic, partition) の昇順に回り、
      合計 max_records 件まで fetch して返す。読んだ分だけ positions を進める。
    - commit(): broker.commit(group, member_id, generation, 現在の positions) を呼ぶ（失敗すれば例外がそのまま出る）。
    - close(): 自分の generation が現在の世代と同じならコミットしてから、グループを抜ける（正常終了）。
    - crash(): コミットせずにグループを抜ける（異常終了。ブローカーがセッションのタイムアウトで検知した、という簡略化）。

    ヒント: at-least-once にするには「処理してからコミット」、at-most-once なら「コミットしてから処理」。
    どちらになるかは、コンシューマを使う側のコードの順序で決まる。
    """

    def __init__(self, broker: Broker, group: str, member_id: str, topics: Sequence[str]) -> None:
        raise NotImplementedError("演習3: Consumer.__init__ を実装してください")

    def assignment(self) -> list[TopicPartition]:
        raise NotImplementedError("演習3: Consumer.assignment を実装してください")

    def position(self, topic: str, partition: int) -> int:
        raise NotImplementedError("演習3: Consumer.position を実装してください")

    def poll(self, max_records: int = 100) -> list[Record]:
        raise NotImplementedError("演習3: Consumer.poll を実装してください")

    def commit(self) -> None:
        raise NotImplementedError("演習3: Consumer.commit を実装してください")

    def close(self) -> None:
        raise NotImplementedError("演習3: Consumer.close を実装してください")

    def crash(self) -> None:
        raise NotImplementedError("演習3: Consumer.crash を実装してください")
