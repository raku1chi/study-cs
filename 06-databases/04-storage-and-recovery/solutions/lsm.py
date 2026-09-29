"""6.4 ストレージエンジンと障害回復 — 演習2 解答例: 小さな LSM 木

演習の仕様は exercises/lsm.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import heapq
import json
import os
import re
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from pathlib import Path

# ---------------------------------------------------------------------------
# 提供済み: Bloom フィルタと SSTable（スタブと同じ）
# ---------------------------------------------------------------------------


class BloomFilter:
    def __init__(self, n_items: int, bits_per_item: int = 10, n_hashes: int = 7) -> None:
        self.m = max(8, n_items * bits_per_item)
        self.k = n_hashes
        self.bits = bytearray((self.m + 7) // 8)

    def _positions(self, key: str) -> Iterator[int]:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, key: str) -> None:
        for p in self._positions(key):
            self.bits[p // 8] |= 1 << (p % 8)

    def might_contain(self, key: str) -> bool:
        return all(self.bits[p // 8] & (1 << (p % 8)) for p in self._positions(key))


def fsync_directory(path: Path) -> None:
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


SSTABLE_NAME = re.compile(r"(\d{8})-t(\d+)\.sst")


class SSTable:
    BLOCK = 16

    def __init__(self, path: Path) -> None:
        m = SSTABLE_NAME.fullmatch(path.name)
        if m is None:
            raise ValueError(f"SSTable のファイル名ではありません: {path.name}")
        self.path = path
        self.seq = int(m.group(1))
        self.tier = int(m.group(2))
        self.reads = 0
        self.index: list[tuple[str, int]] = []
        keys: list[str] = []
        offset = 0
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                key = json.loads(line)[0]
                if i % self.BLOCK == 0:
                    self.index.append((key, offset))
                keys.append(key)
                offset += len(line)
        self.count = len(keys)
        self.min_key = keys[0] if keys else None
        self.max_key = keys[-1] if keys else None
        self.bloom = BloomFilter(self.count)
        for key in keys:
            self.bloom.add(key)

    @classmethod
    def write(cls, directory: Path, seq: int, tier: int, items: Iterable[tuple[str, str | None]]) -> SSTable:
        path = directory / f"{seq:08d}-t{tier}.sst"
        tmp = directory / (path.name + ".tmp")
        prev = None
        with open(tmp, "w", encoding="utf-8") as f:
            for key, value in items:
                if prev is not None and key <= prev:
                    raise ValueError("SSTable に書く項目は、キーの昇順で重複なしにしてください")
                f.write(json.dumps([key, value], ensure_ascii=False) + "\n")
                prev = key
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fsync_directory(directory)
        return cls(path)

    def get(self, key: str) -> tuple[bool, str | None]:
        if self.count == 0 or key < self.min_key or key > self.max_key:
            return False, None
        if not self.bloom.might_contain(key):
            return False, None
        i = bisect_right([k for k, _ in self.index], key) - 1
        if i < 0:
            return False, None
        self.reads += 1
        with open(self.path, "rb") as f:
            f.seek(self.index[i][1])
            for _ in range(self.BLOCK):
                line = f.readline()
                if not line:
                    break
                k, v = json.loads(line)
                if k == key:
                    return True, v
                if k > key:
                    break
        return False, None

    def items(self) -> Iterator[tuple[str, str | None]]:
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                k, v = json.loads(line)
                yield k, v

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return f"SSTable(seq={self.seq}, tier={self.tier}, count={self.count})"


WAL_FILE = "wal.log"


# ---------------------------------------------------------------------------
# 演習2: LSM 木
# ---------------------------------------------------------------------------

class LSMTree:
    def __init__(self, directory: str | os.PathLike, *, memtable_limit: int = 4, tier_size: int = 3,
                 sync: bool = False) -> None:
        if memtable_limit < 1:
            raise ValueError("memtable_limit は 1 以上")
        if tier_size < 2:
            raise ValueError("tier_size は 2 以上")
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.memtable_limit = memtable_limit
        self.tier_size = tier_size
        self.sync = sync
        for tmp in self.dir.glob("*.tmp"):
            tmp.unlink()  # 書きかけの SSTable（名前を変える前にクラッシュした）は捨てる
        self.sstables: list[SSTable] = sorted(
            (SSTable(p) for p in self.dir.glob("*.sst")), key=lambda s: s.seq, reverse=True
        )
        self._next_seq = max((s.seq for s in self.sstables), default=0) + 1
        self.memtable: dict[str, str | None] = {}
        self.wal_path = self.dir / WAL_FILE
        self.wal_truncated_bytes = self._replay_wal()
        self._wal = open(self.wal_path, "a", encoding="utf-8")

    # --- 演習2-1: WAL と memtable ----------------------------------------------

    def _replay_wal(self) -> int:
        if not self.wal_path.exists():
            return 0
        data = self.wal_path.read_bytes()
        pos = 0
        for line in data.splitlines(keepends=True):
            if not line.endswith(b"\n"):
                break  # 改行まで書かれていない最後の行は、書き込みの途中でクラッシュしたもの
            try:
                op = json.loads(line)
                if op[0] == "put":
                    self.memtable[op[1]] = op[2]
                elif op[0] == "del":
                    self.memtable[op[1]] = None
                else:
                    break
            except (ValueError, IndexError, TypeError):
                break
            pos += len(line)
        if pos < len(data):
            with open(self.wal_path, "r+b") as f:
                f.truncate(pos)
        return len(data) - pos

    def _log(self, op: list) -> None:
        # 先にログに書き、その後でメモリ（memtable）を変える（write-ahead）
        self._wal.write(json.dumps(op, ensure_ascii=False) + "\n")
        self._wal.flush()
        if self.sync:
            os.fsync(self._wal.fileno())

    @staticmethod
    def _check(*values: object) -> None:
        for v in values:
            if not isinstance(v, str):
                raise TypeError("キーと値は str にしてください")

    def put(self, key: str, value: str) -> None:
        self._check(key, value)
        self._log(["put", key, value])
        self.memtable[key] = value
        if len(self.memtable) >= self.memtable_limit:
            self.flush()

    def delete(self, key: str) -> None:
        self._check(key)
        self._log(["del", key])
        self.memtable[key] = None  # 墓標。古い SSTable にある値を隠すために必要
        if len(self.memtable) >= self.memtable_limit:
            self.flush()

    # --- 演習2-2: 読み取りの経路 ------------------------------------------------

    def get(self, key: str) -> str | None:
        self._check(key)
        if key in self.memtable:
            return self.memtable[key]  # 墓標なら None
        for sst in self.sstables:  # 新しい順に探し、最初に見つかったものが最新
            found, value = sst.get(key)
            if found:
                return value
        return None

    def _merged(self, sources: list[Iterable[tuple[str, str | None]]]) -> Iterator[tuple[str, str | None]]:
        """新しい順に並んだソースを k-way マージし、キーごとに最新の値（墓標を含む）を返す。"""
        streams = [((k, rank, v) for k, v in src) for rank, src in enumerate(sources)]
        last = None
        for key, _rank, value in heapq.merge(*streams):
            if key != last:  # 同じキーでは rank の小さい（新しい）ものが先に来る
                last = key
                yield key, value

    def scan(self, lo: str | None = None, hi: str | None = None) -> list[tuple[str, str]]:
        sources: list[Iterable[tuple[str, str | None]]] = [sorted(self.memtable.items())]
        sources.extend(sst.items() for sst in self.sstables)
        out = []
        for key, value in self._merged(sources):
            if lo is not None and key < lo:
                continue
            if hi is not None and key >= hi:
                break
            if value is not None:
                out.append((key, value))
        return out

    # --- 演習2-3: フラッシュとコンパクション ------------------------------------

    def flush(self) -> None:
        if not self.memtable:
            return
        sst = SSTable.write(self.dir, self._next_seq, 0, sorted(self.memtable.items()))
        self._next_seq += 1
        self.sstables.insert(0, sst)
        self.memtable.clear()
        # SSTable が永続化された後で WAL を空にする。この間にクラッシュしても、
        # WAL を再生して同じデータがもう一度 memtable に入るだけで、失われるものはない
        self._wal.close()
        self._wal = open(self.wal_path, "w", encoding="utf-8")
        if self.sync:
            os.fsync(self._wal.fileno())
        self._maybe_compact()

    def _maybe_compact(self) -> None:
        t = self.tier_size
        while len(self.sstables) >= t and all(s.tier == self.sstables[0].tier for s in self.sstables[:t]):
            self._merge(t, self.sstables[0].tier + 1)

    def _merge(self, n: int, new_tier: int) -> None:
        """新しい方から n 個の SSTable を 1 つにまとめ、new_tier の SSTable にする。"""
        tables = self.sstables[:n]
        # 墓標を捨ててよいのは、それより古いデータがどこにも残らないとき（全部をまとめるとき）だけ。
        # 一部だけのマージで墓標を捨てると、古い SSTable の値が「生き返って」しまう
        drop_tombstones = n == len(self.sstables)
        items = [(k, v) for k, v in self._merged([s.items() for s in tables])
                 if not (drop_tombstones and v is None)]
        rest = self.sstables[n:]
        if items:
            merged = SSTable.write(self.dir, self._next_seq, new_tier, items)
            self._next_seq += 1
            self.sstables = [merged, *rest]
        else:
            self.sstables = rest
        for s in tables:
            s.path.unlink()

    def compact_all(self) -> None:
        if not self.sstables:
            return
        self._merge(len(self.sstables), max(s.tier for s in self.sstables))

    def close(self) -> None:
        if not self._wal.closed:
            self._wal.close()

    def __enter__(self) -> LSMTree:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
