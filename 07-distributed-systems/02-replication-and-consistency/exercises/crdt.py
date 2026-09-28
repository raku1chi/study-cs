"""7.2 レプリケーションと一貫性 — 演習: 状態ベースの CRDT

CRDT（Conflict-free Replicated Data Type）は、各レプリカが調整なしに更新し、あとで状態を
マージ（merge, ⊔）するだけで全レプリカが同じ状態に収束することが **数学的に保証された** データ型です。
状態ベースの CRDT では、merge が次の 3 つを満たせば、状態がどの順番で・何回・重複して届いても収束します。

    可換（commutative）:  a ⊔ b = b ⊔ a
    結合（associative）:  (a ⊔ b) ⊔ c = a ⊔ (b ⊔ c)
    冪等（idempotent）:   a ⊔ a = a

この演習では、代表的な 4 つの CRDT を実装します。

共通の約束:
    - コンストラクタの replica_id は、そのオブジェクトを更新するレプリカの名前。
    - merge(other) は **新しいオブジェクトを返し、self も other も変更しない**。結果の replica_id は self のもの。
      マージした後は、返り値のオブジェクトを使って更新を続けること。
    - __eq__ は replica_id を無視し、CRDT としての状態（ペイロード）だけを比べる。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.2
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_crdt
"""
from __future__ import annotations

from typing import Any, Hashable, Mapping

# ---------------------------------------------------------------------------
# 演習4（★☆☆）: G-Counter と PN-Counter
# ---------------------------------------------------------------------------


class GCounter:
    """増やすことしかできないカウンタ（Grow-only Counter）。

    状態は「レプリカ ID → そのレプリカが増やした量」の対応表。
    - increment(n=1): 自分（replica_id）の要素に n を足す。n < 0 なら ValueError。
    - value（プロパティ）: 全要素の合計。
    - merge(other): 要素ごとの **最大値**（合計ではない！）をとった新しい GCounter。
    - state(): 0 でない要素だけを、レプリカ ID の昇順に並べた dict（コピー）。
    - counts 引数で初期状態を与えられる。負の値は ValueError。0 の要素は持たない（{"A": 0} と {} は等しい）。

    >>> a, b = GCounter("A"), GCounter("B")
    >>> a.increment(3); b.increment(2)
    >>> a.merge(b).value, a.merge(b).merge(b).value
    (5, 5)

    考えてみよう: merge を「合計」にすると、どの性質が壊れるか。
    """

    def __init__(self, replica_id: str, counts: Mapping[str, int] | None = None) -> None:
        raise NotImplementedError("演習4: GCounter.__init__ を実装してください")

    def increment(self, n: int = 1) -> None:
        raise NotImplementedError("演習4: GCounter.increment を実装してください")

    @property
    def value(self) -> int:
        raise NotImplementedError("演習4: GCounter.value を実装してください")

    def state(self) -> dict[str, int]:
        raise NotImplementedError("演習4: GCounter.state を実装してください")

    def merge(self, other: GCounter) -> GCounter:
        raise NotImplementedError("演習4: GCounter.merge を実装してください")

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError("演習4: GCounter.__eq__ を実装してください")


class PNCounter:
    """増減できるカウンタ（Positive-Negative Counter）。

    増加分 P と減少分 N を別々の GCounter で持ち、value = P.value - N.value とする。
    - increment(n=1) / decrement(n=1): n < 0 なら ValueError。
    - merge: P どうし、N どうしをそれぞれ merge した新しい PNCounter。
    - __eq__: P と N がともに等しい。

    考えてみよう: 1 つの GCounter の要素を減らす実装では、なぜ正しく収束しないのか。
    """

    def __init__(self, replica_id: str) -> None:
        raise NotImplementedError("演習4: PNCounter.__init__ を実装してください")

    def increment(self, n: int = 1) -> None:
        raise NotImplementedError("演習4: PNCounter.increment を実装してください")

    def decrement(self, n: int = 1) -> None:
        raise NotImplementedError("演習4: PNCounter.decrement を実装してください")

    @property
    def value(self) -> int:
        raise NotImplementedError("演習4: PNCounter.value を実装してください")

    def merge(self, other: PNCounter) -> PNCounter:
        raise NotImplementedError("演習4: PNCounter.merge を実装してください")

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError("演習4: PNCounter.__eq__ を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: LWW-Register と OR-Set
# ---------------------------------------------------------------------------


class LWWRegister:
    """最後の書き込みが勝つレジスタ（Last-Writer-Wins Register）。

    状態は (value, stamp)。stamp は (timestamp, 書いたレプリカの ID) のタプルで、初期値は None（値も None）。
    - set(value, timestamp): stamp = (timestamp, self.replica_id) が現在の stamp より **大きい**
      （または現在が None）なら値を置き換えて True。そうでなければ何もせず False。
    - merge(other): stamp が大きい方の (value, stamp) を持つ新しいレジスタ（None は最小とみなす）。
      タイムスタンプが同じなら、レプリカ ID の大きい方が勝つ（タプルの比較で自然にそうなる）。
    - value / stamp（プロパティ）、__eq__（stamp と value が等しい）。

    注意: 実時刻のタイムスタンプを使うと、時計が進んでいるレプリカの古い書き込みが、
    時計が正確なレプリカの新しい書き込みに「勝って」しまい、後者は黙って失われる（テストで確かめます）。
    """

    def __init__(self, replica_id: str) -> None:
        raise NotImplementedError("演習5: LWWRegister.__init__ を実装してください")

    @property
    def value(self) -> Any:
        raise NotImplementedError("演習5: LWWRegister.value を実装してください")

    @property
    def stamp(self) -> tuple[float, str] | None:
        raise NotImplementedError("演習5: LWWRegister.stamp を実装してください")

    def set(self, value: Any, timestamp: float) -> bool:
        raise NotImplementedError("演習5: LWWRegister.set を実装してください")

    def merge(self, other: LWWRegister) -> LWWRegister:
        raise NotImplementedError("演習5: LWWRegister.merge を実装してください")

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError("演習5: LWWRegister.__eq__ を実装してください")


class ORSet:
    """観測済み削除セット（Observed-Remove Set）。並行な追加と削除では追加が勝つ（add-wins）。

    状態:
        adds: 要素 → その要素を追加したときのタグの集合。タグは (replica_id, 通し番号) で一意。
        removed: 削除されたタグの集合（墓標, tombstone）。
    操作:
        - add(e): 自分の通し番号を 1 進めて新しいタグ (replica_id, 番号) を作り、adds[e] に加える。
        - remove(e): **いま見えている**（adds[e] にあって removed にない）タグをすべて removed に加える。
          見えていない（他のレプリカで並行に行われた）追加は消さない。要素がなければ何もしない。
        - e in s / elements(): adds[e] に removed でないタグが 1 つでもあれば含まれる。
        - merge(other): adds は要素ごとにタグの和集合、removed も和集合。
          結果の通し番号は、自分の番号と、結果に含まれる「自分の replica_id のタグ」の最大番号の大きい方から続ける
          （マージ後に add しても、既存のタグと重複しないようにするため）。
        - __eq__: adds（空のタグ集合の要素は除く）と removed が等しい。

    >>> a, b = ORSet("A"), ORSet("B")
    >>> a.add("milk"); b = b.merge(a)
    >>> a.remove("milk"); b.add("milk")      # 並行な削除と追加
    >>> "milk" in a.merge(b)
    True
    """

    def __init__(self, replica_id: str) -> None:
        raise NotImplementedError("演習5: ORSet.__init__ を実装してください")

    def add(self, element: Hashable) -> None:
        raise NotImplementedError("演習5: ORSet.add を実装してください")

    def remove(self, element: Hashable) -> None:
        raise NotImplementedError("演習5: ORSet.remove を実装してください")

    def __contains__(self, element: Hashable) -> bool:
        raise NotImplementedError("演習5: ORSet.__contains__ を実装してください")

    def elements(self) -> set:
        raise NotImplementedError("演習5: ORSet.elements を実装してください")

    def merge(self, other: ORSet) -> ORSet:
        raise NotImplementedError("演習5: ORSet.merge を実装してください")

    def __eq__(self, other: object) -> bool:
        raise NotImplementedError("演習5: ORSet.__eq__ を実装してください")
