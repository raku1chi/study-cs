"""2.4 基本データ構造 — 解答例

演習の仕様は exercises/structures.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import hashlib
import math
from typing import Callable, Generic, Hashable, Iterator, TypeVar

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


# ---------------------------------------------------------------------------
# 演習1: リングバッファ
# ---------------------------------------------------------------------------

class RingBuffer(Generic[T]):
    def __init__(self, capacity: int, overwrite: bool = False) -> None:
        if capacity < 1:
            raise ValueError(f"capacity は 1 以上で指定してください: {capacity}")
        # 最初に固定長の配列を確保し、以後は一切再確保しない
        self._buf: list[T | None] = [None] * capacity
        self._head = 0  # 最も古い要素の位置
        self._size = 0
        self._overwrite = overwrite

    @property
    def capacity(self) -> int:
        return len(self._buf)

    def __len__(self) -> int:
        return self._size

    def is_empty(self) -> bool:
        return self._size == 0

    def is_full(self) -> bool:
        return self._size == len(self._buf)

    def push(self, item: T) -> None:
        cap = len(self._buf)
        if self._size == cap:
            if not self._overwrite:
                raise OverflowError("RingBuffer が満杯です")
            # 満杯なら最も古い要素を上書きし、先頭（最古の位置）を 1 つ進める
            self._buf[self._head] = item
            self._head = (self._head + 1) % cap
            return
        # 末尾の位置は「先頭 + 要素数」を容量で割った余り（端まで来たら 0 に戻る）
        self._buf[(self._head + self._size) % cap] = item
        self._size += 1

    def pop(self) -> T:
        if self._size == 0:
            raise IndexError("空の RingBuffer から pop しました")
        item = self._buf[self._head]
        self._buf[self._head] = None  # 参照を切り、取り出した要素を GC できるようにする
        self._head = (self._head + 1) % len(self._buf)
        self._size -= 1
        return item  # type: ignore[return-value]

    def peek(self) -> T:
        if self._size == 0:
            raise IndexError("空の RingBuffer を peek しました")
        return self._buf[self._head]  # type: ignore[return-value]

    def __iter__(self) -> Iterator[T]:
        cap = len(self._buf)
        for i in range(self._size):
            yield self._buf[(self._head + i) % cap]  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 演習2: 連鎖法（separate chaining）のハッシュマップ
# ---------------------------------------------------------------------------

class ChainedHashMap(Generic[K, V]):
    def __init__(self, initial_capacity: int = 8, max_load_factor: float = 0.75) -> None:
        if initial_capacity < 1:
            raise ValueError(f"initial_capacity は 1 以上: {initial_capacity}")
        if max_load_factor <= 0:
            raise ValueError(f"max_load_factor は正の数: {max_load_factor}")
        # 各バケットは [ハッシュ値, キー, 値] のリスト（=連鎖）
        self._buckets: list[list[list]] = [[] for _ in range(initial_capacity)]
        self._size = 0
        self._max_load = max_load_factor

    @property
    def capacity(self) -> int:
        return len(self._buckets)

    @property
    def load_factor(self) -> float:
        return self._size / len(self._buckets)

    def __len__(self) -> int:
        return self._size

    def _find(self, key: K) -> tuple[list[list], int, int]:
        """(キーが入るべきバケット, バケット内の位置 or -1, ハッシュ値) を返す。"""
        h = hash(key)
        bucket = self._buckets[h % len(self._buckets)]
        for i, entry in enumerate(bucket):
            # ハッシュ値を先に比べる（安い整数比較で大半を除外し、== は一致しそうなときだけ）
            # `is` を先に試すのは CPython の dict と同じ工夫（NaN のように自分と == でない値も探せる）
            if entry[0] == h and (entry[1] is key or entry[1] == key):
                return bucket, i, h
        return bucket, -1, h

    def __setitem__(self, key: K, value: V) -> None:
        bucket, i, h = self._find(key)
        if i >= 0:
            bucket[i][2] = value  # 既存キーの更新: 要素数は変わらない
            return
        bucket.append([h, key, value])
        self._size += 1
        if self._size > len(self._buckets) * self._max_load:
            self._resize(len(self._buckets) * 2)

    def _resize(self, new_capacity: int) -> None:
        old = self._buckets
        self._buckets = [[] for _ in range(new_capacity)]
        for bucket in old:
            for entry in bucket:
                # 保存しておいたハッシュ値を再利用する（hash() を呼び直さない）
                self._buckets[entry[0] % new_capacity].append(entry)

    def __getitem__(self, key: K) -> V:
        bucket, i, _ = self._find(key)
        if i < 0:
            raise KeyError(key)
        return bucket[i][2]

    def get(self, key: K, default: V | None = None) -> V | None:
        bucket, i, _ = self._find(key)
        return bucket[i][2] if i >= 0 else default

    def __contains__(self, key: object) -> bool:
        return self._find(key)[1] >= 0  # type: ignore[arg-type]

    def __delitem__(self, key: K) -> None:
        bucket, i, _ = self._find(key)
        if i < 0:
            raise KeyError(key)
        # 連鎖の中の順序には意味がないので、末尾と入れ替えて pop する（O(1)）
        bucket[i] = bucket[-1]
        bucket.pop()
        self._size -= 1

    def __iter__(self) -> Iterator[K]:
        for bucket in self._buckets:
            for entry in bucket:
                yield entry[1]

    def items(self) -> Iterator[tuple[K, V]]:
        for bucket in self._buckets:
            for entry in bucket:
                yield entry[1], entry[2]


# ---------------------------------------------------------------------------
# 演習3: オープンアドレス法（線形探査 + 墓標）のハッシュマップ
# ---------------------------------------------------------------------------

# 「削除済み」を表す番兵。None（一度も使われていない空き）と区別するのがポイント
_TOMBSTONE = object()


class LinearProbingHashMap(Generic[K, V]):
    def __init__(self, initial_capacity: int = 8, max_load_factor: float = 0.5) -> None:
        if initial_capacity < 1:
            raise ValueError(f"initial_capacity は 1 以上: {initial_capacity}")
        if not 0 < max_load_factor < 1:
            # 1 以上を許すと空きスロットがなくなり、探査が止まらなくなる
            raise ValueError(f"max_load_factor は 0 より大きく 1 未満: {max_load_factor}")
        # スロットは None（空き）/ _TOMBSTONE（墓標）/ [ハッシュ値, キー, 値]
        self._slots: list = [None] * initial_capacity
        self._size = 0
        self._tombstones = 0
        self._max_load = max_load_factor

    @property
    def capacity(self) -> int:
        return len(self._slots)

    @property
    def tombstones(self) -> int:
        return self._tombstones

    @property
    def load_factor(self) -> float:
        return self._size / len(self._slots)

    def __len__(self) -> int:
        return self._size

    def _probe(self, key: K, h: int) -> tuple[int, bool]:
        """キーを探す。見つかれば (位置, True)。
        見つからなければ (挿入すべき位置, False)。挿入位置は「途中で最初に見た墓標」、
        なければ探査を打ち切った空きスロット。"""
        cap = len(self._slots)
        i = h % cap
        first_tombstone = -1
        # 負荷率 < 1 を保っているので空きスロットが必ずあり、このループは必ず止まる
        while True:
            slot = self._slots[i]
            if slot is None:
                # 空きに到達 = キーはこの先にも存在しない（挿入時に空きを飛び越えることはないため）
                return (first_tombstone if first_tombstone >= 0 else i), False
            if slot is _TOMBSTONE:
                # 墓標では探査を止めない。止めると、この先に置かれたキーが見つからなくなる
                if first_tombstone < 0:
                    first_tombstone = i
            elif slot[0] == h and (slot[1] is key or slot[1] == key):
                return i, True
            i = (i + 1) % cap

    def __setitem__(self, key: K, value: V) -> None:
        h = hash(key)
        i, found = self._probe(key, h)
        if found:
            self._slots[i][2] = value
            return
        # 新しいキー: 墓標も探査を長くするので、負荷の判定に含める
        if (self._size + self._tombstones + 1) > len(self._slots) * self._max_load:
            self._rebuild()
            i, _ = self._probe(key, h)
        if self._slots[i] is _TOMBSTONE:
            self._tombstones -= 1  # 墓標を再利用
        self._slots[i] = [h, key, value]
        self._size += 1

    def _rebuild(self) -> None:
        # 再構築後、生きている要素だけで負荷率が上限の半分以下になるまで容量を 2 倍にする。
        # 余裕を残しておくことで、次の再構築までに十分な回数の操作ができ、償却 O(1) になる。
        cap = len(self._slots)
        while self._size + 1 > cap * self._max_load / 2:
            cap *= 2
        old = self._slots
        self._slots = [None] * cap
        self._tombstones = 0  # 墓標は捨てる（ここで「掃除」される）
        for slot in old:
            if slot is None or slot is _TOMBSTONE:
                continue
            i = slot[0] % cap
            while self._slots[i] is not None:
                i = (i + 1) % cap
            self._slots[i] = slot

    def __getitem__(self, key: K) -> V:
        i, found = self._probe(key, hash(key))
        if not found:
            raise KeyError(key)
        return self._slots[i][2]

    def get(self, key: K, default: V | None = None) -> V | None:
        i, found = self._probe(key, hash(key))
        return self._slots[i][2] if found else default

    def __contains__(self, key: object) -> bool:
        return self._probe(key, hash(key))[1]  # type: ignore[arg-type]

    def __delitem__(self, key: K) -> None:
        i, found = self._probe(key, hash(key))
        if not found:
            raise KeyError(key)
        # None にしてはいけない: 同じ探査列の後ろにあるキーが見つからなくなる
        self._slots[i] = _TOMBSTONE
        self._size -= 1
        self._tombstones += 1

    def __iter__(self) -> Iterator[K]:
        for slot in self._slots:
            if slot is not None and slot is not _TOMBSTONE:
                yield slot[1]

    def items(self) -> Iterator[tuple[K, V]]:
        for slot in self._slots:
            if slot is not None and slot is not _TOMBSTONE:
                yield slot[1], slot[2]


# ---------------------------------------------------------------------------
# 演習4: LRU キャッシュ（ハッシュマップ + 双方向連結リスト）
# ---------------------------------------------------------------------------

class _Node:
    __slots__ = ("key", "value", "prev", "next")

    def __init__(self, key, value) -> None:
        self.key = key
        self.value = value
        self.prev: _Node = self
        self.next: _Node = self


class LRUCache(Generic[K, V]):
    def __init__(self, capacity: int, on_evict: Callable[[K, V], None] | None = None) -> None:
        if capacity < 1:
            raise ValueError(f"capacity は 1 以上: {capacity}")
        self._capacity = capacity
        self._on_evict = on_evict
        self._map: dict[K, _Node] = {}  # キー → ノード（O(1) でノードにたどり着くため）
        # 番兵ノード 1 個の循環リスト。root.next が最も最近使ったもの（MRU）、
        # root.prev が最も長く使われていないもの（LRU）。番兵があると端の場合分けが消える
        self._root = _Node(None, None)
        self.hits = 0
        self.misses = 0

    @property
    def capacity(self) -> int:
        return self._capacity

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key: object) -> bool:
        return key in self._map  # 参照しただけでは「使った」ことにしない

    def _unlink(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _push_front(self, node: _Node) -> None:
        root = self._root
        node.prev = root
        node.next = root.next
        root.next.prev = node
        root.next = node

    def get(self, key: K, default: V | None = None) -> V | None:
        node = self._map.get(key)
        if node is None:
            self.misses += 1
            return default
        self.hits += 1
        # 使われたので先頭（MRU）へ移動。つなぎ替えは定数回のポインタ操作
        self._unlink(node)
        self._push_front(node)
        return node.value

    def put(self, key: K, value: V) -> None:
        node = self._map.get(key)
        if node is not None:
            node.value = value
            self._unlink(node)
            self._push_front(node)
            return
        node = _Node(key, value)
        self._map[key] = node
        self._push_front(node)
        if len(self._map) > self._capacity:
            lru = self._root.prev  # 末尾 = 最も長く使われていない
            self._unlink(lru)
            del self._map[lru.key]
            if self._on_evict is not None:
                self._on_evict(lru.key, lru.value)

    def keys(self) -> list[K]:
        out = []
        node = self._root.next
        while node is not self._root:
            out.append(node.key)
            node = node.next
        return out


# ---------------------------------------------------------------------------
# 演習5: ブルームフィルタ
# ---------------------------------------------------------------------------

class BloomFilter:
    def __init__(self, num_bits: int, num_hashes: int) -> None:
        if num_bits < 1:
            raise ValueError(f"num_bits は 1 以上: {num_bits}")
        if num_hashes < 1:
            raise ValueError(f"num_hashes は 1 以上: {num_hashes}")
        self.num_bits = num_bits
        self.num_hashes = num_hashes
        self._bits = bytearray((num_bits + 7) // 8)  # 1 ビット単位で詰めて持つ
        self._added = 0

    @classmethod
    def for_capacity(cls, expected_items: int, fp_rate: float) -> BloomFilter:
        if expected_items < 1:
            raise ValueError(f"expected_items は 1 以上: {expected_items}")
        if not 0 < fp_rate < 1:
            raise ValueError(f"fp_rate は 0 より大きく 1 未満: {fp_rate}")
        ln2 = math.log(2)
        # 最適な k を使ったときの偽陽性率 p ≈ exp(-(m/n)(ln 2)^2) を m について解く
        m = math.ceil(-expected_items * math.log(fp_rate) / (ln2 * ln2))
        k = max(1, round(m / expected_items * ln2))  # 最適な k = (m/n) ln 2
        return cls(m, k)

    def positions(self, item: str | bytes) -> list[int]:
        if isinstance(item, str):
            data = item.encode("utf-8")
        elif isinstance(item, (bytes, bytearray)):
            data = bytes(item)
        else:
            raise TypeError(f"str か bytes を指定してください: {type(item).__name__}")
        # 組み込みの hash() はプロセスごとにランダム化されるので使わない。
        # hashlib なら、どのマシン・どのプロセスでも同じ位置になる（保存・共有できる）
        digest = hashlib.sha256(data).digest()
        h1 = int.from_bytes(digest[0:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1  # 0 にならないよう奇数にする
        # ダブルハッシング: 2 つのハッシュ値から k 個の位置を作る（Kirsch–Mitzenmacher）
        return [(h1 + i * h2) % self.num_bits for i in range(self.num_hashes)]

    def add(self, item: str | bytes) -> None:
        for p in self.positions(item):
            self._bits[p >> 3] |= 1 << (p & 7)
        self._added += 1

    def __contains__(self, item: object) -> bool:
        # 1 か所でも 0 なら「確実に入っていない」。全部 1 なら「たぶん入っている」
        return all(self._bits[p >> 3] >> (p & 7) & 1 for p in self.positions(item))  # type: ignore[arg-type]

    def expected_fp_rate(self, n: int | None = None) -> float:
        if n is None:
            n = self._added
        if n < 0:
            raise ValueError(f"n は 0 以上: {n}")
        k, m = self.num_hashes, self.num_bits
        return (1 - math.exp(-k * n / m)) ** k
