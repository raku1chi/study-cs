"""7.3 パーティショニング — 演習: ハッシュ分割とレンジ分割（解答例）

演習の仕様は exercises/partitioning.py の docstring を参照してください。
"""
from __future__ import annotations

import bisect
import hashlib
from typing import Any, Iterable, Sequence


def stable_hash(s: str) -> int:
    # Python の組み込み hash() はプロセスごとに値が変わる（ハッシュのランダム化）ので分割には使えない
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# ---------------------------------------------------------------------------
# 演習1: 剰余による分割とランデブーハッシュ
# ---------------------------------------------------------------------------


def mod_n_partition(key: str, n: int) -> int:
    if n < 1:
        raise ValueError(f"n は 1 以上です: {n}")
    return stable_hash(key) % n


def _scores(key: str, nodes: Iterable[str]) -> list[tuple[int, str]]:
    return [(stable_hash(f"{node}:{key}"), node) for node in nodes]


def rendezvous_node(key: str, nodes: Iterable[str]) -> str:
    scores = _scores(key, nodes)
    if not scores:
        raise LookupError("ノードがありません")
    # 各ノードとキーの組の「くじ」を引き、最大のノードが担当する
    return max(scores)[1]


def rendezvous_nodes(key: str, nodes: Iterable[str], k: int) -> list[str]:
    scores = _scores(key, nodes)
    if not 1 <= k <= len(scores):
        raise ValueError(f"k は 1〜ノード数（{len(scores)}）です: {k}")
    # 上位 k 個 = そのキーのレプリカの置き場所。ノードが抜けても順位の繰り上がりだけで済む
    return [node for _, node in sorted(scores, reverse=True)[:k]]


# ---------------------------------------------------------------------------
# 演習2: 仮想ノード付きのコンシステントハッシュ
# ---------------------------------------------------------------------------


class ConsistentHashRing:
    def __init__(self, nodes: Iterable[str] = (), vnodes: int = 100) -> None:
        if vnodes < 1:
            raise ValueError(f"vnodes は 1 以上です: {vnodes}")
        self.vnodes = vnodes
        self._nodes: set[str] = set()
        self._ring: list[tuple[int, str]] = []  # (リング上の位置, 物理ノード) を位置の昇順に保つ
        for node in nodes:
            self.add_node(node)

    @property
    def nodes(self) -> list[str]:
        return sorted(self._nodes)

    def add_node(self, node: str) -> None:
        if node in self._nodes:
            raise ValueError(f"ノード {node} は追加済みです")
        self._nodes.add(node)
        for i in range(self.vnodes):
            bisect.insort(self._ring, (stable_hash(f"{node}#{i}"), node))

    def remove_node(self, node: str) -> None:
        if node not in self._nodes:
            raise KeyError(node)
        self._nodes.remove(node)
        self._ring = [entry for entry in self._ring if entry[1] != node]

    def _start(self, key: str) -> int:
        if not self._ring:
            raise LookupError("リングにノードがありません")
        # キーの位置以上で最初の仮想ノード（時計回りの後継）。末尾を越えたら先頭に戻る
        i = bisect.bisect_left(self._ring, (stable_hash(key), ""))
        return i % len(self._ring)

    def get_node(self, key: str) -> str:
        return self._ring[self._start(key)][1]

    def get_nodes(self, key: str, n: int) -> list[str]:
        if not 1 <= n <= len(self._nodes):
            raise ValueError(f"n は 1〜ノード数（{len(self._nodes)}）です: {n}")
        result: list[str] = []
        i = self._start(key)
        # 時計回りに進み、まだ選んでいない物理ノードを集める（Dynamo の preference list）
        while len(result) < n:
            node = self._ring[i][1]
            if node not in result:
                result.append(node)
            i = (i + 1) % len(self._ring)
        return result


# ---------------------------------------------------------------------------
# 演習3: レンジ分割と、ホットなパーティションの分割
# ---------------------------------------------------------------------------


class RangePartitioner:
    def __init__(self, max_partition_size: int = 1000, split_points: Sequence[str] = ()) -> None:
        if max_partition_size < 2:
            raise ValueError(f"max_partition_size は 2 以上です: {max_partition_size}")
        points = list(split_points)
        if any(a >= b for a, b in zip(points, points[1:])):
            raise ValueError("split_points は重複のない昇順で指定してください")
        self.max_partition_size = max_partition_size
        self._bounds = points  # パーティション i は [bounds[i-1], bounds[i]) を担当
        self._data: list[dict[str, Any]] = [{} for _ in range(len(points) + 1)]
        self._loads = [0] * (len(points) + 1)

    @property
    def num_partitions(self) -> int:
        return len(self._data)

    @property
    def boundaries(self) -> list[str]:
        return list(self._bounds)

    def partition_for(self, key: str) -> int:
        # 境界と等しいキーは右側のパーティション（下限を含み、上限を含まない）
        return bisect.bisect_right(self._bounds, key)

    def put(self, key: str, value: Any) -> None:
        i = self.partition_for(key)
        self._data[i][key] = value
        self._loads[i] += 1
        if len(self._data[i]) > self.max_partition_size:
            self.split(i)  # 大きくなりすぎたら中央値で 2 つに割る（動的分割）

    def get(self, key: str) -> Any:
        i = self.partition_for(key)
        self._loads[i] += 1
        return self._data[i].get(key)

    def _range_of(self, index: int) -> tuple[str | None, str | None]:
        lower = self._bounds[index - 1] if index > 0 else None
        upper = self._bounds[index] if index < len(self._bounds) else None
        return lower, upper

    def split(self, index: int, at: str | None = None) -> str:
        if not 0 <= index < self.num_partitions:
            raise IndexError(f"パーティション番号が範囲外です: {index}")
        keys = sorted(self._data[index])
        if at is None:
            if len(keys) < 2:
                raise ValueError("キーが 2 つ未満のパーティションは中央値で分割できません")
            at = keys[len(keys) // 2]
        lower, upper = self._range_of(index)
        if (lower is not None and at <= lower) or (upper is not None and at >= upper):
            raise ValueError(f"分割点 {at!r} がパーティションの範囲 [{lower!r}, {upper!r}) の内側にありません")
        data = self._data[index]
        left = {k: v for k, v in data.items() if k < at}
        right = {k: v for k, v in data.items() if k >= at}
        self._bounds.insert(index, at)
        self._data[index : index + 1] = [left, right]
        self._loads[index : index + 1] = [0, 0]  # 分割後は負荷を測り直す
        return at

    def partition_sizes(self) -> list[int]:
        return [len(d) for d in self._data]

    def loads(self) -> list[int]:
        return list(self._loads)

    def reset_loads(self) -> None:
        self._loads = [0] * self.num_partitions

    def hottest(self) -> int:
        return max(range(self.num_partitions), key=lambda i: (self._loads[i], -i))

    def partitions_for_range(self, start: str, end: str) -> list[int]:
        if start > end:
            raise ValueError(f"start <= end で指定してください: {start!r}, {end!r}")
        if start == end:
            return []
        first = self.partition_for(start)
        # end は含まない。end がちょうど境界なら、その境界から始まるパーティションは不要
        last = bisect.bisect_left(self._bounds, end)
        return list(range(first, last + 1))

    def scan(self, start: str, end: str) -> list[tuple[str, Any]]:
        items: list[tuple[str, Any]] = []
        for i in self.partitions_for_range(start, end):
            self._loads[i] += 1
            items.extend((k, v) for k, v in self._data[i].items() if start <= k < end)
        return sorted(items)
