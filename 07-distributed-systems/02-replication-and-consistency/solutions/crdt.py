"""7.2 レプリケーションと一貫性 — 演習: 状態ベースの CRDT（解答例）

演習の仕様は exercises/crdt.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import Any, Hashable, Mapping

# ---------------------------------------------------------------------------
# 演習4: G-Counter と PN-Counter
# ---------------------------------------------------------------------------


class GCounter:
    def __init__(self, replica_id: str, counts: Mapping[str, int] | None = None) -> None:
        self.replica_id = replica_id
        self._counts: dict[str, int] = {}
        for rid, c in (counts or {}).items():
            if c < 0:
                raise ValueError(f"カウントは 0 以上です: {rid}={c}")
            if c:
                self._counts[rid] = c

    def increment(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError(f"G-Counter は減らせません: {n}")
        # 自分の要素だけを増やす。他のレプリカの要素には触らない（だから競合しない）
        if n:
            self._counts[self.replica_id] = self._counts.get(self.replica_id, 0) + n

    @property
    def value(self) -> int:
        return sum(self._counts.values())

    def state(self) -> dict[str, int]:
        return dict(sorted(self._counts.items()))

    def merge(self, other: GCounter) -> GCounter:
        # 要素ごとの最大値: 可換・結合的・冪等なので、どの順で何度マージしても同じ結果になる
        ids = self._counts.keys() | other._counts.keys()
        merged = {rid: max(self._counts.get(rid, 0), other._counts.get(rid, 0)) for rid in ids}
        return GCounter(self.replica_id, merged)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, GCounter):
            return NotImplemented
        return self._counts == other._counts

    def __repr__(self) -> str:
        return f"GCounter({self.replica_id!r}, {self.state()})"


class PNCounter:
    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        # 増加分と減少分を別々の G-Counter で持つ（1 つの要素を減らすと max のマージが壊れるため）
        self._p = GCounter(replica_id)
        self._n = GCounter(replica_id)

    def increment(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError(f"increment の引数は 0 以上です: {n}")
        self._p.increment(n)

    def decrement(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError(f"decrement の引数は 0 以上です: {n}")
        self._n.increment(n)

    @property
    def value(self) -> int:
        return self._p.value - self._n.value

    def state(self) -> tuple[dict[str, int], dict[str, int]]:
        return self._p.state(), self._n.state()

    def merge(self, other: PNCounter) -> PNCounter:
        result = PNCounter(self.replica_id)
        result._p = self._p.merge(other._p)
        result._n = self._n.merge(other._n)
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, PNCounter):
            return NotImplemented
        return self._p == other._p and self._n == other._n

    def __repr__(self) -> str:
        return f"PNCounter({self.replica_id!r}, value={self.value})"


# ---------------------------------------------------------------------------
# 演習5: LWW-Register と OR-Set
# ---------------------------------------------------------------------------


class LWWRegister:
    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self._value: Any = None
        self._stamp: tuple[float, str] | None = None  # (タイムスタンプ, 書いたレプリカ)

    @property
    def value(self) -> Any:
        return self._value

    @property
    def stamp(self) -> tuple[float, str] | None:
        return self._stamp

    def set(self, value: Any, timestamp: float) -> bool:
        stamp = (timestamp, self.replica_id)
        # 同じタイムスタンプならレプリカ ID で決める。こうして全順序にしないと、レプリカごとに勝者が変わる
        if self._stamp is None or stamp > self._stamp:
            self._value, self._stamp = value, stamp
            return True
        return False  # 手元の値より「古い」書き込みは黙って捨てられる（時計が遅れていると起きる）

    def merge(self, other: LWWRegister) -> LWWRegister:
        result = LWWRegister(self.replica_id)
        winner = self
        if other._stamp is not None and (self._stamp is None or other._stamp > self._stamp):
            winner = other
        result._value, result._stamp = winner._value, winner._stamp
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LWWRegister):
            return NotImplemented
        return self._stamp == other._stamp and self._value == other._value

    def __repr__(self) -> str:
        return f"LWWRegister({self.replica_id!r}, value={self._value!r}, stamp={self._stamp})"


Tag = tuple  # (replica_id, 通し番号)


class ORSet:
    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id
        self._adds: dict[Hashable, set[Tag]] = {}
        self._removed: set[Tag] = set()  # 墓標（tombstone）: 削除された追加のタグ
        self._counter = 0

    def add(self, element: Hashable) -> None:
        # 追加のたびに一意なタグを付ける。同じ要素でも「どの追加か」を区別できる
        self._counter += 1
        self._adds.setdefault(element, set()).add((self.replica_id, self._counter))

    def remove(self, element: Hashable) -> None:
        # 観測済みの追加だけを消す（observed-remove）。並行に行われた未観測の追加は残る → add-wins
        self._removed |= self._live_tags(element)

    def _live_tags(self, element: Hashable) -> set[Tag]:
        return self._adds.get(element, set()) - self._removed

    def __contains__(self, element: Hashable) -> bool:
        return bool(self._live_tags(element))

    def elements(self) -> set:
        return {e for e in self._adds if self._live_tags(e)}

    def merge(self, other: ORSet) -> ORSet:
        result = ORSet(self.replica_id)
        for source in (self, other):
            for element, tags in source._adds.items():
                result._adds.setdefault(element, set()).update(tags)
        result._removed = self._removed | other._removed
        # 自分の ID のタグと重複しないよう、見えている自分のタグの最大番号から続ける
        own = [n for tags in result._adds.values() for rid, n in tags if rid == self.replica_id]
        result._counter = max([self._counter, *own])
        return result

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ORSet):
            return NotImplemented
        mine = {e: t for e, t in self._adds.items() if t}
        theirs = {e: t for e, t in other._adds.items() if t}
        return mine == theirs and self._removed == other._removed

    def __repr__(self) -> str:
        return f"ORSet({self.replica_id!r}, {sorted(map(repr, self.elements()))})"
