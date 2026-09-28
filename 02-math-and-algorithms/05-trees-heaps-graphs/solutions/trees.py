"""2.5 木・ヒープ・グラフ — 解答例（木とヒープ）

演習の仕様は exercises/trees.py の docstring を参照してください。
退化した木（高さ n）でも Python の再帰上限に当たらないよう、すべて反復で書いています。
"""
from __future__ import annotations

from typing import Any, Callable, Generic, Iterable, TypeVar

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1: 二分探索木
# ---------------------------------------------------------------------------

class _BSTNode:
    __slots__ = ("key", "value", "left", "right")

    def __init__(self, key, value) -> None:
        self.key = key
        self.value = value
        self.left: _BSTNode | None = None
        self.right: _BSTNode | None = None


class BST(Generic[K, V]):
    def __init__(self) -> None:
        self._root: _BSTNode | None = None
        self._size = 0

    def __len__(self) -> int:
        return self._size

    def insert(self, key: K, value: V | None = None) -> None:
        if self._root is None:
            self._root = _BSTNode(key, value)
            self._size = 1
            return
        node = self._root
        while True:
            if key == node.key:
                node.value = value  # 既存のキーは値だけ更新
                return
            # 「小さければ左、大きければ右」を葉まで繰り返す。1 回の比較で探索範囲の片側を捨てられる
            child = "left" if key < node.key else "right"
            nxt = getattr(node, child)
            if nxt is None:
                setattr(node, child, _BSTNode(key, value))
                self._size += 1
                return
            node = nxt

    def _find(self, key: K) -> _BSTNode | None:
        node = self._root
        while node is not None and node.key != key:
            node = node.left if key < node.key else node.right
        return node

    def get(self, key: K, default: V | None = None) -> V | None:
        node = self._find(key)
        return node.value if node is not None else default

    def __contains__(self, key: object) -> bool:
        return self._find(key) is not None  # type: ignore[arg-type]

    def delete(self, key: K) -> None:
        parent: _BSTNode | None = None
        node = self._root
        while node is not None and node.key != key:
            parent = node
            node = node.left if key < node.key else node.right
        if node is None:
            raise KeyError(key)

        if node.left is not None and node.right is not None:
            # 子が 2 つ: 右部分木の最小ノード（後続ノード）で置き換える。
            # 後続ノードは左の子を持たないので、取り外しは「子が 1 つ以下」の場合に帰着する
            succ_parent, succ = node, node.right
            while succ.left is not None:
                succ_parent, succ = succ, succ.left
            node.key, node.value = succ.key, succ.value
            parent, node = succ_parent, succ

        # ここでは node の子は高々 1 つ。その子（または None）で node を置き換える
        child = node.left if node.left is not None else node.right
        if parent is None:
            self._root = child
        elif parent.left is node:
            parent.left = child
        else:
            parent.right = child
        self._size -= 1

    def inorder(self) -> list[K]:
        # 明示的なスタックによる中間順（in-order）走査: 左部分木 → 自分 → 右部分木
        out: list[K] = []
        stack: list[_BSTNode] = []
        node = self._root
        while stack or node is not None:
            while node is not None:
                stack.append(node)
                node = node.left
            node = stack.pop()
            out.append(node.key)
            node = node.right
        return out

    def height(self) -> int:
        # 幅優先で段数を数える（ノード数で数えるので、空なら 0、根だけなら 1）
        if self._root is None:
            return 0
        level = [self._root]
        h = 0
        while level:
            h += 1
            level = [c for n in level for c in (n.left, n.right) if c is not None]
        return h

    def min(self) -> K:
        if self._root is None:
            raise ValueError("空の木です")
        node = self._root
        while node.left is not None:
            node = node.left
        return node.key

    def max(self) -> K:
        if self._root is None:
            raise ValueError("空の木です")
        node = self._root
        while node.right is not None:
            node = node.right
        return node.key

    def range_keys(self, lo: K, hi: K) -> list[K]:
        # lo <= key < hi のキーを昇順に。範囲外の部分木には降りないので O(高さ + 結果の件数)
        out: list[K] = []
        stack: list[_BSTNode] = []
        node = self._root
        while stack or node is not None:
            while node is not None:
                if node.key < lo:
                    node = node.right  # node と左部分木はすべて lo 未満なので飛ばす
                else:
                    stack.append(node)
                    node = node.left
            if not stack:
                break
            node = stack.pop()
            if not node.key < hi:
                break  # 以降は中間順でさらに大きいキーしか出てこない
            out.append(node.key)
            node = node.right
        return out


# ---------------------------------------------------------------------------
# 演習2: 二分ヒープ（最小ヒープ）と top-k
# ---------------------------------------------------------------------------

class MinHeap(Generic[T]):
    def __init__(self, items: Iterable[T] = ()) -> None:
        self._a: list[T] = list(items)
        # 後ろ半分は葉なので何もしなくてよい。最後の内部ノードから根に向かって sift down する。
        # 低いノードほど数が多く、しかも移動距離が短いので、全体で O(n) になる（Floyd の方法）
        for i in reversed(range(len(self._a) // 2)):
            self._sift_down(i)

    def __len__(self) -> int:
        return len(self._a)

    def to_list(self) -> list[T]:
        return list(self._a)

    def push(self, item: T) -> None:
        self._a.append(item)
        self._sift_up(len(self._a) - 1)

    def peek(self) -> T:
        if not self._a:
            raise IndexError("空のヒープです")
        return self._a[0]

    def pop(self) -> T:
        a = self._a
        if not a:
            raise IndexError("空のヒープです")
        last = a.pop()
        if not a:
            return last
        top = a[0]
        a[0] = last  # 末尾の要素を根に置き、正しい位置まで沈める
        self._sift_down(0)
        return top

    def _sift_up(self, i: int) -> None:
        a = self._a
        item = a[i]
        while i > 0:
            parent = (i - 1) // 2
            if not item < a[parent]:
                break
            a[i] = a[parent]  # 親を下ろす（交換ではなく「穴」を上へ動かすと代入が半分で済む）
            i = parent
        a[i] = item

    def _sift_down(self, i: int) -> None:
        a = self._a
        n = len(a)
        item = a[i]
        while True:
            child = 2 * i + 1
            if child >= n:
                break
            right = child + 1
            if right < n and a[right] < a[child]:
                child = right  # 小さい方の子と比べる
            if not a[child] < item:
                break
            a[i] = a[child]
            i = child
        a[i] = item


def top_k(items: Iterable[T], k: int, key: Callable[[T], Any] | None = None) -> list[T]:
    if k < 0:
        raise ValueError(f"k は 0 以上: {k}")
    if k == 0:
        return []
    keyf = key if key is not None else (lambda x: x)
    # 「上位 k 件の中で最小のもの」を根に持つ、サイズ k の最小ヒープを保つ。
    # 新しい要素が根より大きいときだけ入れ替えるので、O(n log k) 時間・O(k) メモリ。
    # (キー, 通し番号, 要素) にするのは、キーが等しいときに要素どうしを比較させないため
    heap: MinHeap[tuple[Any, int, T]] = MinHeap()
    for i, x in enumerate(items):
        kx = keyf(x)
        if len(heap) < k:
            heap.push((kx, i, x))
        elif heap.peek()[0] < kx:
            heap.pop()
            heap.push((kx, i, x))
    out: list[tuple[Any, int, T]] = []
    while len(heap):
        out.append(heap.pop())  # 小さい順に出てくる
    out.reverse()
    return [x for _, _, x in out]


# ---------------------------------------------------------------------------
# 演習3: トライ木
# ---------------------------------------------------------------------------

class _TrieNode:
    __slots__ = ("children", "is_word")

    def __init__(self) -> None:
        self.children: dict[str, _TrieNode] = {}
        self.is_word = False


class Trie:
    def __init__(self) -> None:
        self._root = _TrieNode()
        self._count = 0

    def __len__(self) -> int:
        return self._count

    def insert(self, word: str) -> None:
        node = self._root
        for ch in word:
            node = node.children.setdefault(ch, _TrieNode())
        if not node.is_word:
            node.is_word = True
            self._count += 1

    def _walk(self, prefix: str) -> _TrieNode | None:
        node = self._root
        for ch in prefix:
            node = node.children.get(ch)  # type: ignore[assignment]
            if node is None:
                return None
        return node

    def __contains__(self, word: object) -> bool:
        if not isinstance(word, str):
            return False
        node = self._walk(word)
        return node is not None and node.is_word

    def starts_with(self, prefix: str) -> bool:
        return self._walk(prefix) is not None

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        if limit < 0:
            raise ValueError(f"limit は 0 以上: {limit}")
        node = self._walk(prefix)
        if node is None or limit == 0:
            return []
        out: list[str] = []
        # 深さ優先（行きがけ順）で、子を文字の昇順にたどると辞書順に単語が出てくる。
        # スタックには逆順に積む（最後に積んだものが先に取り出されるため）。
        # limit 件に達した時点で打ち切るので、候補が何万あっても必要な分しか見ない
        stack: list[tuple[_TrieNode, str]] = [(node, prefix)]
        while stack:
            cur, word = stack.pop()
            if cur.is_word:
                out.append(word)
                if len(out) == limit:
                    break
            for ch in sorted(cur.children, reverse=True):
                stack.append((cur.children[ch], word + ch))
        return out

