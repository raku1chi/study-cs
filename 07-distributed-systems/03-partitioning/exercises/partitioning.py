"""7.3 パーティショニング — 演習: ハッシュ分割とレンジ分割

データを複数のノード（パーティション）に分けるとき、「どのキーをどこに置くか」の決め方が、
負荷の偏り、ノードの追加・削除時のデータ移動量、範囲検索のしやすさを決めます。
この演習では次の 4 つを実装して、それぞれの性質をテストで確かめます。

    演習1: 剰余による分割（hash(key) mod N）と、ランデブーハッシュ（HRW）
    演習2: 仮想ノード付きのコンシステントハッシュ
    演習3: レンジ分割と、大きくなった・熱くなったパーティションの分割

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.3
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_partitioning

注意: Python の組み込み hash() は、文字列に対してプロセスごとに異なる値を返します（ハッシュのランダム化）。
プロセスをまたいで同じ結果が必要な分割には使えないので、この演習では stable_hash（実装済み）を使います。
"""
from __future__ import annotations

import bisect  # noqa: F401  演習2・3で使えます（bisect.bisect_left, bisect.insort など）
import hashlib
from typing import Any, Iterable, Sequence


def stable_hash(s: str) -> int:
    """文字列の SHA-256 の先頭 8 バイトを、ビッグエンディアンの 64 ビット整数にしたもの（実装済み）。"""
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 剰余による分割とランデブーハッシュ
# ---------------------------------------------------------------------------


def mod_n_partition(key: str, n: int) -> int:
    """stable_hash(key) % n を返す。n < 1 なら ValueError。

    最も素朴な方法。均等に分散するが、n が変わるとほとんどのキーの担当が変わる（テストで確かめます）。
    """
    raise NotImplementedError("演習1: mod_n_partition を実装してください")


def rendezvous_node(key: str, nodes: Iterable[str]) -> str:
    """ランデブーハッシュ（Highest Random Weight）で key の担当ノードを返す。

    各ノードについてスコア stable_hash(f"{node}:{key}") を計算し、(スコア, ノード名) が最大のノードを選ぶ。
    ノードが空なら LookupError。

    性質: ノードが 1 台抜けても、そのノードが担当していたキーだけが（次点のノードに）移動する。
    """
    raise NotImplementedError("演習1: rendezvous_node を実装してください")


def rendezvous_nodes(key: str, nodes: Iterable[str], k: int) -> list[str]:
    """(スコア, ノード名) の大きい順に上位 k 台を返す（レプリカの置き場所に使える）。

    k が 1〜ノード数の範囲外なら ValueError。先頭は rendezvous_node(key, nodes) と一致する。
    """
    raise NotImplementedError("演習1: rendezvous_nodes を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 仮想ノード付きのコンシステントハッシュ
# ---------------------------------------------------------------------------


class ConsistentHashRing:
    """0〜2^64-1 の値を円（リング）とみなし、ノードとキーを同じリング上に置くコンシステントハッシュ。

    - 物理ノード node は、vnodes 個の仮想ノードとしてリング上の位置 stable_hash(f"{node}#{i}")
      （i = 0, 1, …, vnodes-1）に置く。
    - キーの位置は stable_hash(key)。担当は、キーの位置 **以上** で最初に現れる仮想ノードの物理ノード
      （時計回りの後継）。キーの位置より大きい仮想ノードがなければ、リングの先頭（最小の位置）に戻る。
      万一、同じ位置に複数の仮想ノードがあれば、(位置, ノード名) の順で先のものとする。
    - add_node: 追加済みなら ValueError。remove_node: 存在しなければ KeyError。
    - get_node: ノードが 1 台もなければ LookupError。
    - get_nodes(key, n): 担当の仮想ノードから時計回りに進み、まだ選んでいない物理ノードを n 台集める
      （Dynamo の preference list。レプリカの置き場所）。n が 1〜ノード数の範囲外なら ValueError。
    - nodes（プロパティ）: 物理ノード名の昇順リスト。vnodes < 1 なら ValueError。

    性質（テストで確かめます）:
        - ノードを追加すると、移動するのは新しいノードが担当するキーだけで、その割合はおよそ 1/(N+1)
        - ノードを削除すると、移動するのは削除したノードが担当していたキーだけ
        - 仮想ノードを増やすほど、ノード間の負荷の偏りが小さくなる

    ヒント: (位置, ノード名) のタプルを昇順に並べたリストを持ち、bisect で探す。
    """

    def __init__(self, nodes: Iterable[str] = (), vnodes: int = 100) -> None:
        raise NotImplementedError("演習2: ConsistentHashRing.__init__ を実装してください")

    @property
    def nodes(self) -> list[str]:
        raise NotImplementedError("演習2: ConsistentHashRing.nodes を実装してください")

    def add_node(self, node: str) -> None:
        raise NotImplementedError("演習2: ConsistentHashRing.add_node を実装してください")

    def remove_node(self, node: str) -> None:
        raise NotImplementedError("演習2: ConsistentHashRing.remove_node を実装してください")

    def get_node(self, key: str) -> str:
        raise NotImplementedError("演習2: ConsistentHashRing.get_node を実装してください")

    def get_nodes(self, key: str, n: int) -> list[str]:
        raise NotImplementedError("演習2: ConsistentHashRing.get_nodes を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: レンジ分割と、ホットなパーティションの分割
# ---------------------------------------------------------------------------


class RangePartitioner:
    """キーの辞書順の範囲でデータを分けるレンジパーティショナー。

    境界（boundaries）を昇順に b0 < b1 < … とすると、パーティション 0 は b0 未満、
    パーティション i は [b(i-1), b(i))、最後のパーティションは最後の境界以上のキーを担当する。
    **境界と等しいキーは右側** のパーティションに入る（下限を含み、上限を含まない）。

    - __init__: max_partition_size < 2 なら ValueError。split_points が重複のない昇順でなければ ValueError。
    - partition_for(key): 担当パーティションの番号。
    - put(key, value): 保存し、そのパーティションの負荷（load）を 1 増やす。保存後、そのパーティションの
      キー数が max_partition_size を **超えたら**、split(i) で中央値分割する（動的分割）。
    - get(key): 値（なければ None）。担当パーティションの負荷を 1 増やす。
    - split(index, at=None) -> 分割点:
        * at が None なら、そのパーティションのキーを昇順に並べた len//2 番目のキーを分割点にする。
          キーが 2 つ未満なら ValueError。
        * 分割点はパーティションの範囲の **内側**（下限より大きく、上限より小さい）でなければ ValueError。
        * 分割点未満のキーが左、以上のキーが右のパーティションになる。2 つの負荷はどちらも 0 から数え直す。
        * index が範囲外なら IndexError。
    - partition_sizes(): 各パーティションのキー数のリスト。loads(): 各パーティションの負荷のリスト。
      reset_loads(): 負荷をすべて 0 にする。hottest(): 負荷が最大のパーティション番号（同点なら小さい番号）。
    - partitions_for_range(start, end): 範囲 [start, end) と重なるパーティション番号の昇順リスト。
      start == end なら []。start > end なら ValueError。
    - scan(start, end): [start, end) のキーの (key, value) をキー順に並べたリスト。
      触れたパーティションの負荷をそれぞれ 1 増やす。

    >>> rp = RangePartitioner(split_points=["g", "p"])
    >>> [rp.partition_for(k) for k in ("apple", "g", "grape", "zebra")]
    [0, 1, 1, 2]
    """

    def __init__(self, max_partition_size: int = 1000, split_points: Sequence[str] = ()) -> None:
        raise NotImplementedError("演習3: RangePartitioner.__init__ を実装してください")

    @property
    def num_partitions(self) -> int:
        raise NotImplementedError("演習3: RangePartitioner.num_partitions を実装してください")

    @property
    def boundaries(self) -> list[str]:
        raise NotImplementedError("演習3: RangePartitioner.boundaries を実装してください")

    def partition_for(self, key: str) -> int:
        raise NotImplementedError("演習3: RangePartitioner.partition_for を実装してください")

    def put(self, key: str, value: Any) -> None:
        raise NotImplementedError("演習3: RangePartitioner.put を実装してください")

    def get(self, key: str) -> Any:
        raise NotImplementedError("演習3: RangePartitioner.get を実装してください")

    def split(self, index: int, at: str | None = None) -> str:
        raise NotImplementedError("演習3: RangePartitioner.split を実装してください")

    def partition_sizes(self) -> list[int]:
        raise NotImplementedError("演習3: RangePartitioner.partition_sizes を実装してください")

    def loads(self) -> list[int]:
        raise NotImplementedError("演習3: RangePartitioner.loads を実装してください")

    def reset_loads(self) -> None:
        raise NotImplementedError("演習3: RangePartitioner.reset_loads を実装してください")

    def hottest(self) -> int:
        raise NotImplementedError("演習3: RangePartitioner.hottest を実装してください")

    def partitions_for_range(self, start: str, end: str) -> list[int]:
        raise NotImplementedError("演習3: RangePartitioner.partitions_for_range を実装してください")

    def scan(self, start: str, end: str) -> list[tuple[str, Any]]:
        raise NotImplementedError("演習3: RangePartitioner.scan を実装してください")
