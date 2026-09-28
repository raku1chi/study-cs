"""2.4 基本データ構造 — 演習

各クラスの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.4          # 合格数を表示
    python3 tools/check.py -v 2.4       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

制約（学びのための縛り）:
    - 演習1 では collections.deque を使わず、最初に確保した固定長の list だけで実装してください。
    - 演習2・3 では、要素の格納に dict / set を使わないでください（自分でバケット・スロットを管理する）。
      キーのハッシュ値には組み込みの hash() を使ってかまいません。
    - 演習4 では OrderedDict や functools.lru_cache を使わないでください。
      キーからノードを引くための dict は使ってかまいません（それが LRU キャッシュの定石です）。
    - 演習5 では組み込みの hash() を使わず、hashlib.sha256 を使ってください（理由は docstring 参照）。
"""
from __future__ import annotations

import hashlib  # noqa: F401  演習5で使います
import math  # noqa: F401  演習5で使います
from typing import Callable, Generic, Hashable, Iterator, TypeVar

T = TypeVar("T")
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: リングバッファ（固定長の FIFO キュー）
# ---------------------------------------------------------------------------

class RingBuffer(Generic[T]):
    """容量固定の FIFO キュー。配列の端まで来たら先頭に戻って（環状に）使う。

    - RingBuffer(capacity, overwrite=False)。capacity < 1 なら ValueError。
    - push(item): 末尾に追加する。満杯のとき:
        - overwrite=False なら OverflowError（中身は変えない）
        - overwrite=True なら最も古い要素を捨てて追加する（「直近 N 件のログ」のような用途）
    - pop(): 最も古い要素を取り出して返す。空なら IndexError。
    - peek(): 最も古い要素を取り出さずに返す。空なら IndexError。
    - len(rb)、is_empty()、is_full()、capacity（プロパティ）
    - iter(rb): 古い順に要素を列挙する（取り出さない）。

    すべての操作は O(1)（__iter__ は O(n)）。list.pop(0) や list.insert(0, x) は O(n) なので使わない。

    >>> rb = RingBuffer(3)
    >>> for x in (1, 2, 3): rb.push(x)
    >>> rb.pop()
    1
    >>> rb.push(4)       # 配列の先頭（1 があった場所）に書き込まれる
    >>> list(rb)
    [2, 3, 4]

    ヒント: [None] * capacity の配列と、「先頭（最も古い要素）の位置」「要素数」の 2 つの整数で
    状態を表す。末尾の位置は (先頭 + 要素数) % capacity で求まる。
    """

    def __init__(self, capacity: int, overwrite: bool = False) -> None:
        raise NotImplementedError("演習1: RingBuffer.__init__ を実装してください")

    @property
    def capacity(self) -> int:
        raise NotImplementedError("演習1: RingBuffer.capacity を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習1: RingBuffer.__len__ を実装してください")

    def is_empty(self) -> bool:
        raise NotImplementedError("演習1: RingBuffer.is_empty を実装してください")

    def is_full(self) -> bool:
        raise NotImplementedError("演習1: RingBuffer.is_full を実装してください")

    def push(self, item: T) -> None:
        raise NotImplementedError("演習1: RingBuffer.push を実装してください")

    def pop(self) -> T:
        raise NotImplementedError("演習1: RingBuffer.pop を実装してください")

    def peek(self) -> T:
        raise NotImplementedError("演習1: RingBuffer.peek を実装してください")

    def __iter__(self) -> Iterator[T]:
        raise NotImplementedError("演習1: RingBuffer.__iter__ を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 連鎖法（separate chaining）のハッシュマップ
# ---------------------------------------------------------------------------

class ChainedHashMap(Generic[K, V]):
    """バケットの配列を持ち、同じバケットに入るキーをリスト（連鎖）でつなぐハッシュマップ。

    - ChainedHashMap(initial_capacity=8, max_load_factor=0.75)
        - initial_capacity < 1、または max_load_factor <= 0 なら ValueError。
        - 連鎖法では 1 バケットに複数の要素が入るので、max_load_factor は 1 を超えてもよい。
    - m[key] = value: 追加または更新。キーが新しい場合だけ要素数が増える。
      追加の結果 len(m) / capacity > max_load_factor になったら、バケット数を 2 倍にして
      全要素を入れ直す（再ハッシュ）。ちょうど等しいときは拡張しない。
    - m[key]: 値を返す。なければ KeyError。
    - m.get(key, default=None)、key in m、len(m)
    - del m[key]: 削除。なければ KeyError。（縮小は不要）
    - iter(m): すべてのキーを 1 回ずつ列挙する（順序は問わない）。
    - m.items(): (キー, 値) のタプルを列挙する。
    - capacity: バケット数。load_factor: len(m) / capacity。

    バケットの選び方: hash(key) % capacity。
    キーの一致判定は == で行う（ハッシュ値が同じでも別のキーでありうる＝衝突）。

    >>> m = ChainedHashMap()
    >>> m["apple"] = 100
    >>> m["apple"]
    100
    >>> "banana" in m
    False

    ヒント:
    - 各バケットは [ハッシュ値, キー, 値] のリスト（のリスト）にするとよい。ハッシュ値を
      保存しておくと、比較の前に整数で素早く絞り込めるうえ、再ハッシュ時に hash() を
      呼び直さずに済む（CPython の dict も同じ工夫をしている）。
    - 共通処理「キーを探して (バケット, 位置) を返す」を 1 つのメソッドにまとめると楽。
    """

    def __init__(self, initial_capacity: int = 8, max_load_factor: float = 0.75) -> None:
        raise NotImplementedError("演習2: ChainedHashMap.__init__ を実装してください")

    @property
    def capacity(self) -> int:
        raise NotImplementedError("演習2: ChainedHashMap.capacity を実装してください")

    @property
    def load_factor(self) -> float:
        raise NotImplementedError("演習2: ChainedHashMap.load_factor を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習2: ChainedHashMap.__len__ を実装してください")

    def __setitem__(self, key: K, value: V) -> None:
        raise NotImplementedError("演習2: ChainedHashMap.__setitem__ を実装してください")

    def __getitem__(self, key: K) -> V:
        raise NotImplementedError("演習2: ChainedHashMap.__getitem__ を実装してください")

    def get(self, key: K, default: V | None = None) -> V | None:
        raise NotImplementedError("演習2: ChainedHashMap.get を実装してください")

    def __contains__(self, key: object) -> bool:
        raise NotImplementedError("演習2: ChainedHashMap.__contains__ を実装してください")

    def __delitem__(self, key: K) -> None:
        raise NotImplementedError("演習2: ChainedHashMap.__delitem__ を実装してください")

    def __iter__(self) -> Iterator[K]:
        raise NotImplementedError("演習2: ChainedHashMap.__iter__ を実装してください")

    def items(self) -> Iterator[tuple[K, V]]:
        raise NotImplementedError("演習2: ChainedHashMap.items を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: オープンアドレス法（線形探査 + 墓標）のハッシュマップ
# ---------------------------------------------------------------------------

class LinearProbingHashMap(Generic[K, V]):
    """1 つの配列（スロット）にキーを直接置き、衝突したら隣のスロットを順に探すハッシュマップ。

    公開インターフェースは ChainedHashMap と同じ（capacity はスロット数）。加えて:
    - LinearProbingHashMap(initial_capacity=8, max_load_factor=0.5)
        - initial_capacity < 1、または max_load_factor が 0 < x < 1 でなければ ValueError。
    - tombstones: 現在の墓標（削除済みスロット）の数。

    探査: キーのハッシュ値を h として、h % capacity から 1 つずつ（末尾の次は 0 に戻って）調べる。
      - 空きスロット（一度も使われていない）に着いたら、キーは存在しない。
      - 墓標は「ここには何もないが、探査はこの先へ続ける」という印。

    削除: 削除したスロットには必ず墓標を置く（空きに戻してはいけない。理由は README 参照）。

    挿入:
      - まず探査でキーを探す。あれば値を更新して終わり（途中の墓標に新しく入れると
        同じキーが 2 か所に入ってしまう）。
      - なければ、探査の途中で最初に見つけた墓標を再利用する。墓標がなければ空きスロットに入れる。

    再構築（テストはこのルールを前提にしています）:
      - 新しいキーを挿入する直前に (len + tombstones + 1) > capacity × max_load_factor なら再構築する。
        墓標も探査を長くするので、負荷に含めて数える。
      - 新しい容量は、今の capacity から始めて (len + 1) <= 新容量 × max_load_factor / 2 に
        なるまで 2 倍にした値（縮小はしない）。再構築では墓標を捨て、生きている要素だけを入れ直す。
      - 「上限の半分」まで余裕を空けるのは、再構築の直後にまた再構築、を繰り返さないため
        （償却 O(1) にするため。削除と挿入を繰り返しても容量が増え続けない）。

    ヒント:
    - 空き・墓標・使用中を区別するため、空きは None、墓標は専用の番兵オブジェクト
      （_TOMBSTONE = object()）、使用中は [ハッシュ値, キー, 値] にするとよい。
    - 「探査してキーを探し、見つからなければ挿入すべき位置も返す」メソッドを 1 つ作ると、
      get・set・delete のすべてで使える。
    - 負荷率 < 1 を保っていれば空きスロットが必ず残るので、探査ループは必ず止まる。
    """

    def __init__(self, initial_capacity: int = 8, max_load_factor: float = 0.5) -> None:
        raise NotImplementedError("演習3: LinearProbingHashMap.__init__ を実装してください")

    @property
    def capacity(self) -> int:
        raise NotImplementedError("演習3: LinearProbingHashMap.capacity を実装してください")

    @property
    def tombstones(self) -> int:
        raise NotImplementedError("演習3: LinearProbingHashMap.tombstones を実装してください")

    @property
    def load_factor(self) -> float:
        raise NotImplementedError("演習3: LinearProbingHashMap.load_factor を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習3: LinearProbingHashMap.__len__ を実装してください")

    def __setitem__(self, key: K, value: V) -> None:
        raise NotImplementedError("演習3: LinearProbingHashMap.__setitem__ を実装してください")

    def __getitem__(self, key: K) -> V:
        raise NotImplementedError("演習3: LinearProbingHashMap.__getitem__ を実装してください")

    def get(self, key: K, default: V | None = None) -> V | None:
        raise NotImplementedError("演習3: LinearProbingHashMap.get を実装してください")

    def __contains__(self, key: object) -> bool:
        raise NotImplementedError("演習3: LinearProbingHashMap.__contains__ を実装してください")

    def __delitem__(self, key: K) -> None:
        raise NotImplementedError("演習3: LinearProbingHashMap.__delitem__ を実装してください")

    def __iter__(self) -> Iterator[K]:
        raise NotImplementedError("演習3: LinearProbingHashMap.__iter__ を実装してください")

    def items(self) -> Iterator[tuple[K, V]]:
        raise NotImplementedError("演習3: LinearProbingHashMap.items を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: LRU キャッシュ（ハッシュマップ + 双方向連結リスト）
# ---------------------------------------------------------------------------

class LRUCache(Generic[K, V]):
    """容量を超えたら「最も長く使われていない（Least Recently Used）」要素を追い出すキャッシュ。

    - LRUCache(capacity, on_evict=None)。capacity < 1 なら ValueError。
      on_evict が指定されていれば、追い出すたびに on_evict(key, value) を呼ぶ。
    - get(key, default=None): 値を返し、その要素を「最も最近使った」ことにする。
      なければ default を返す。見つかれば hits を、見つからなければ misses を 1 増やす。
    - put(key, value): 追加または更新し、その要素を「最も最近使った」ことにする。
      新しいキーの追加で容量を超えたら、最も長く使われていない要素を 1 つ追い出す。
    - key in cache: 含まれているか。順序も hits/misses も変えない。
    - len(cache)、capacity（プロパティ）、hits・misses（整数の属性）
    - keys(): キーのリストを「最も最近使った順」に返す。

    get と put は O(1) で動くこと（テストはキーの比較回数で確かめます）。

    >>> c = LRUCache(2)
    >>> c.put("a", 1); c.put("b", 2)
    >>> c.get("a")
    1
    >>> c.put("c", 3)      # b が最も長く使われていないので追い出される
    >>> c.keys()
    ['c', 'a']

    ヒント:
    - 双方向連結リストで「使った順」を管理し、dict で「キー → ノード」を引く。
      ノードが分かれば、リストの途中からの取り外しも先頭への移動も O(1)。
    - 番兵（sentinel）ノードを 1 つ置き、循環リストにすると「先頭が空」「末尾が空」の
      場合分けがなくなる。root.next を最新、root.prev を最古とする。
    - ノードのクラスには __slots__ を付けるとメモリを節約できる。
    """

    def __init__(self, capacity: int, on_evict: Callable[[K, V], None] | None = None) -> None:
        raise NotImplementedError("演習4: LRUCache.__init__ を実装してください")

    @property
    def capacity(self) -> int:
        raise NotImplementedError("演習4: LRUCache.capacity を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習4: LRUCache.__len__ を実装してください")

    def __contains__(self, key: object) -> bool:
        raise NotImplementedError("演習4: LRUCache.__contains__ を実装してください")

    def get(self, key: K, default: V | None = None) -> V | None:
        raise NotImplementedError("演習4: LRUCache.get を実装してください")

    def put(self, key: K, value: V) -> None:
        raise NotImplementedError("演習4: LRUCache.put を実装してください")

    def keys(self) -> list[K]:
        raise NotImplementedError("演習4: LRUCache.keys を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: ブルームフィルタ
# ---------------------------------------------------------------------------

class BloomFilter:
    """「確実に含まれていない」か「たぶん含まれている」かを、少ないメモリで答える集合。

    - BloomFilter(num_bits, num_hashes): m = num_bits ビットの配列と k = num_hashes 個の
      ハッシュ位置を使う。どちらかが 1 未満なら ValueError。num_bits・num_hashes は属性として読める。
    - BloomFilter.for_capacity(expected_items, fp_rate): 要素数 n と目標の偽陽性率 p から
      最適なパラメータで作る。
        m = ceil(-n × ln(p) / (ln 2)^2)
        k = max(1, round(m / n × ln 2))
      n < 1、または p が 0 < p < 1 でなければ ValueError。
    - positions(item): item が対応する k 個のビット位置（0 <= 位置 < m）のリストを返す。
      item は str（UTF-8 でバイト列にする）か bytes。それ以外は TypeError。
      位置は次のダブルハッシングで決める（テストは具体的な値を確かめます）:
        digest = hashlib.sha256(data).digest()
        h1 = digest の先頭 8 バイトをビッグエンディアンの符号なし整数にしたもの
        h2 = digest の 8〜15 バイト目を同様に整数にし、最下位ビットを 1 にしたもの（h2 | 1）
        i 番目の位置 = (h1 + i × h2) % m    （i = 0, 1, ..., k-1）
    - add(item): k 個の位置のビットを 1 にする。
    - item in bf: k 個の位置のビットがすべて 1 なら True。1 つでも 0 なら False。
      追加した要素に対して False を返すこと（偽陰性）は絶対にあってはならない。
    - expected_fp_rate(n=None): 理論上の偽陽性率 (1 - e^(-k n / m))^k を返す。
      n を省略したら、これまでに add() した回数を使う。

    >>> bf = BloomFilter.for_capacity(1000, 0.01)
    >>> (bf.num_bits, bf.num_hashes)
    (9586, 7)
    >>> bf.add("alice")
    >>> "alice" in bf
    True

    ヒント:
    - ビット配列は bytearray((m + 7) // 8) で持てる。位置 p のビットは
      bits[p >> 3] の (p & 7) ビット目。
    - 組み込みの hash() は str について起動ごとにランダム化される（ハッシュのランダム化）。
      フィルタをファイルに保存したり他のプロセスと共有したりするなら、hashlib のような
      決定的なハッシュ関数が必要になる。
    """

    def __init__(self, num_bits: int, num_hashes: int) -> None:
        raise NotImplementedError("演習5: BloomFilter.__init__ を実装してください")

    @classmethod
    def for_capacity(cls, expected_items: int, fp_rate: float) -> BloomFilter:
        raise NotImplementedError("演習5: BloomFilter.for_capacity を実装してください")

    def positions(self, item: str | bytes) -> list[int]:
        raise NotImplementedError("演習5: BloomFilter.positions を実装してください")

    def add(self, item: str | bytes) -> None:
        raise NotImplementedError("演習5: BloomFilter.add を実装してください")

    def __contains__(self, item: object) -> bool:
        raise NotImplementedError("演習5: BloomFilter.__contains__ を実装してください")

    def expected_fp_rate(self, n: int | None = None) -> float:
        raise NotImplementedError("演習5: BloomFilter.expected_fp_rate を実装してください")
