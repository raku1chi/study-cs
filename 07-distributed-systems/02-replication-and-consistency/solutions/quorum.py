"""7.2 レプリケーションと一貫性 — 演習: Dynamo 風のクォーラム読み書き（解答例）

演習の仕様は exercises/quorum.py の docstring を参照してください。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Versioned:
    value: Any
    version: int


class QuorumError(Exception):
    pass


class Replica:
    def __init__(self, name: str) -> None:
        self.name = name
        self.up = True
        self.store: dict[str, Versioned] = {}

    def write(self, key: str, item: Versioned) -> bool:
        current = self.store.get(key)
        # バージョンが新しいときだけ上書きする。古い書き込みが遅れて届いても巻き戻らない
        if current is None or item.version > current.version:
            self.store[key] = item
            return True
        return False

    def read(self, key: str) -> Versioned | None:
        return self.store.get(key)


class QuorumCluster:
    def __init__(self, n: int = 3, w: int = 2, r: int = 2, seed: int = 0) -> None:
        if n < 1:
            raise ValueError(f"n は 1 以上です: {n}")
        if not 1 <= w <= n or not 1 <= r <= n:
            raise ValueError(f"w と r は 1〜n の範囲です: n={n}, w={w}, r={r}")
        self.n, self.w, self.r = n, w, r
        self.replicas = [Replica(f"r{i}") for i in range(n)]
        self.rng = random.Random(seed)
        self.read_repairs = 0
        self._version = 0

    @property
    def is_strict_quorum(self) -> bool:
        # 書き込み集合と読み取り集合が必ず 1 台以上重なる条件（鳩の巣原理）
        return self.w + self.r > self.n

    def fail(self, i: int) -> None:
        self.replicas[i].up = False

    def recover(self, i: int) -> None:
        # 停止中の書き込みは受け取っていないので、データは古いまま戻ってくる
        self.replicas[i].up = True

    def _up(self) -> list[int]:
        return [i for i, rep in enumerate(self.replicas) if rep.up]

    def put(self, key: str, value: Any) -> int:
        up = self._up()
        if len(up) < self.w:
            raise QuorumError(f"書き込みに必要な {self.w} 台が稼働していません（稼働 {len(up)} 台）")
        self._version += 1
        item = Versioned(value, self._version)
        # 「最初に ACK を返した W 台」を乱数で模擬する。残りの台には（まだ）届いていない
        for i in self.rng.sample(up, self.w):
            self.replicas[i].write(key, item)
        return self._version

    def get(self, key: str) -> Versioned | None:
        up = self._up()
        if len(up) < self.r:
            raise QuorumError(f"読み取りに必要な {self.r} 台が稼働していません（稼働 {len(up)} 台）")
        chosen = self.rng.sample(up, self.r)
        answers = [(i, self.replicas[i].read(key)) for i in chosen]
        found = [v for _, v in answers if v is not None]
        if not found:
            return None
        latest = max(found, key=lambda v: v.version)
        # リードリペア: 読んだついでに、古い値を返したレプリカを最新に直す
        for i, v in answers:
            if v is None or v.version < latest.version:
                self.replicas[i].write(key, latest)
                self.read_repairs += 1
        return latest

    def anti_entropy(self) -> int:
        up = self._up()
        keys = set().union(*(self.replicas[i].store.keys() for i in up)) if up else set()
        repaired = 0
        for key in sorted(keys):
            versions = [self.replicas[i].read(key) for i in up]
            latest = max((v for v in versions if v is not None), key=lambda v: v.version)
            for i in up:
                if self.replicas[i].write(key, latest):
                    repaired += 1
        return repaired
