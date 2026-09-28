"""6.2 インデックスとクエリ処理 — 演習1 解答例: B+木

演習の仕様は exercises/bplustree.py の docstring を参照してください。
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 提供済み: ノードの型（スタブと同じ）
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class LeafNode:
    keys: list = field(default_factory=list)
    values: list = field(default_factory=list)
    next: LeafNode | None = field(default=None, repr=False)


@dataclass(eq=False)
class InternalNode:
    keys: list = field(default_factory=list)
    children: list = field(default_factory=list)



class BPlusTree:
    def __init__(self, order: int = 4) -> None:
        if order < 3:
            raise ValueError(f"order は 3 以上にしてください: {order}")
        self.order = order
        self.root: LeafNode | InternalNode = LeafNode()
        self.pages_read = 0
        self._size = 0

    # 非ルートのノードが持つべき最小量
    @property
    def min_leaf_keys(self) -> int:
        return self.order // 2  # = ceil((order - 1) / 2)

    @property
    def min_children(self) -> int:
        return (self.order + 1) // 2  # = ceil(order / 2)

    def __len__(self) -> int:
        return self._size

    def height(self) -> int:
        h, node = 1, self.root
        while isinstance(node, InternalNode):
            node = node.children[0]
            h += 1
        return h

    # -----------------------------------------------------------------------
    # 演習1-1: 検索
    # -----------------------------------------------------------------------

    def _find_leaf(self, key: Any) -> LeafNode:
        node = self.root
        self.pages_read += 1
        while isinstance(node, InternalNode):
            # 区切りキー k について「k 未満は左、k 以上は右」なので bisect_right を使う
            node = node.children[bisect_right(node.keys, key)]
            self.pages_read += 1
        return node

    def search(self, key: Any, default: Any = None) -> Any:
        leaf = self._find_leaf(key)
        i = bisect_left(leaf.keys, key)
        if i < len(leaf.keys) and leaf.keys[i] == key:
            return leaf.values[i]
        return default

    # -----------------------------------------------------------------------
    # 演習1-2: 挿入（分割）
    # -----------------------------------------------------------------------

    def insert(self, key: Any, value: Any) -> None:
        self.pages_read += 1
        split = self._insert(self.root, key, value)
        if split is not None:
            # ルートが分割されたら、新しいルートを 1 段上に作る。木が高くなるのはこのときだけで、
            # しかも全ての葉の深さが同時に 1 増えるので、木は常に平衡を保つ
            separator, right = split
            self.root = InternalNode(keys=[separator], children=[self.root, right])

    def _insert(self, node: LeafNode | InternalNode, key: Any, value: Any) -> tuple[Any, LeafNode | InternalNode] | None:
        if isinstance(node, LeafNode):
            i = bisect_left(node.keys, key)
            if i < len(node.keys) and node.keys[i] == key:
                node.values[i] = value  # 既存のキーなら値を上書き（件数は変わらない）
                return None
            node.keys.insert(i, key)
            node.values.insert(i, value)
            self._size += 1
            if len(node.keys) < self.order:  # 葉が持てるのは order - 1 個まで
                return None
            # 葉の分割: 前半 ceil(order/2) 個を残し、後半を新しい葉へ。
            # 右の葉の先頭キーを「コピー」して親に渡す（葉にもキーが残る＝B+木の特徴）
            mid = (len(node.keys) + 1) // 2
            right = LeafNode(keys=node.keys[mid:], values=node.values[mid:], next=node.next)
            del node.keys[mid:]
            del node.values[mid:]
            node.next = right  # 葉どうしの連結リストをつなぎ直す（範囲検索で使う）
            return right.keys[0], right

        i = bisect_right(node.keys, key)
        self.pages_read += 1
        split = self._insert(node.children[i], key, value)
        if split is None:
            return None
        separator, new_child = split
        node.keys.insert(i, separator)
        node.children.insert(i + 1, new_child)
        if len(node.children) <= self.order:
            return None
        # 内部ノードの分割: 中央のキーを親へ「移動」する（こちらはコピーではない）
        mid = len(node.keys) // 2
        up = node.keys[mid]
        right = InternalNode(keys=node.keys[mid + 1:], children=node.children[mid + 1:])
        del node.keys[mid:]
        del node.children[mid + 1:]
        return up, right

    # -----------------------------------------------------------------------
    # 演習1-3: 範囲検索
    # -----------------------------------------------------------------------

    def range_scan(self, lo: Any = None, hi: Any = None) -> list[tuple[Any, Any]]:
        if lo is not None and hi is not None and lo > hi:
            return []
        if lo is None:
            # 下限がなければ一番左の葉から
            node = self.root
            self.pages_read += 1
            while isinstance(node, InternalNode):
                node = node.children[0]
                self.pages_read += 1
            leaf: LeafNode | None = node
        else:
            leaf = self._find_leaf(lo)
        result: list[tuple[Any, Any]] = []
        while leaf is not None:
            for k, v in zip(leaf.keys, leaf.values):
                if lo is not None and k < lo:
                    continue
                if hi is not None and k > hi:
                    return result  # 上限を超えたら、それ以降の葉は読まない
                result.append((k, v))
            # 葉の連結リストをたどる: 木を上り下りせずに次の葉へ移れる
            leaf = leaf.next
            if leaf is not None:
                self.pages_read += 1
        return result

    # -----------------------------------------------------------------------
    # 演習1-4: 不変条件の検査
    # -----------------------------------------------------------------------

    def check_invariants(self) -> None:
        leaves: list[LeafNode] = []
        depths: set[int] = set()

        def fail(msg: str) -> None:
            raise AssertionError(msg)

        def walk(node: LeafNode | InternalNode, lo: Any, hi: Any, depth: int, is_root: bool) -> None:
            keys = node.keys
            for a, b in zip(keys, keys[1:]):
                if not a < b:
                    fail(f"ノード内のキーが狭義の昇順ではありません: {keys}")
            for k in keys:
                if (lo is not None and k < lo) or (hi is not None and k >= hi):
                    fail(f"キー {k!r} が区切りキーの範囲 [{lo!r}, {hi!r}) の外にあります")
            if isinstance(node, LeafNode):
                if len(node.values) != len(keys):
                    fail("葉のキーと値の数が一致しません")
                if len(keys) > self.order - 1:
                    fail(f"葉のキーが多すぎます: {len(keys)} > {self.order - 1}")
                if not is_root and len(keys) < self.min_leaf_keys:
                    fail(f"葉のキーが少なすぎます: {len(keys)} < {self.min_leaf_keys}")
                depths.add(depth)
                leaves.append(node)
                return
            if len(node.children) != len(keys) + 1:
                fail("内部ノードの子の数がキーの数 + 1 ではありません")
            if len(node.children) > self.order:
                fail(f"内部ノードの子が多すぎます: {len(node.children)} > {self.order}")
            if is_root and len(node.children) < 2:
                fail("内部ノードのルートは子を 2 つ以上持つ必要があります")
            if not is_root and len(node.children) < self.min_children:
                fail(f"内部ノードの子が少なすぎます: {len(node.children)} < {self.min_children}")
            bounds = [lo, *keys, hi]
            for i, child in enumerate(node.children):
                walk(child, bounds[i], bounds[i + 1], depth + 1, False)

        walk(self.root, None, None, 1, True)
        if len(depths) != 1:
            fail(f"葉の深さがそろっていません: {sorted(depths)}")
        # 葉の連結リストが、左から順にすべての葉をたどること
        node: LeafNode | None = leaves[0]
        for expected in leaves:
            if node is not expected:
                fail("葉の連結リスト（next）が、葉を左から順にたどっていません")
            node = node.next
        if node is not None:
            fail("最後の葉の next が None ではありません")
        total = sum(len(leaf.keys) for leaf in leaves)
        if total != self._size:
            fail(f"葉のキーの総数 {total} が len() = {self._size} と一致しません")

    # -----------------------------------------------------------------------
    # 演習1-5（発展）: 削除（借用と併合）
    # -----------------------------------------------------------------------

    def delete(self, key: Any) -> bool:
        if not self._delete(self.root, key):
            return False
        self._size -= 1
        if isinstance(self.root, InternalNode) and len(self.root.children) == 1:
            # ルートの子が 1 つになったら、その子を新しいルートにする（木が 1 段低くなる）
            self.root = self.root.children[0]
        return True

    def _delete(self, node: LeafNode | InternalNode, key: Any) -> bool:
        if isinstance(node, LeafNode):
            i = bisect_left(node.keys, key)
            if i == len(node.keys) or node.keys[i] != key:
                return False
            del node.keys[i]
            del node.values[i]
            return True
        i = bisect_right(node.keys, key)
        child = node.children[i]
        if not self._delete(child, key):
            return False
        # 親の区切りキーは、削除したキーと同じ値のまま残ってもよい（大小関係は保たれる）
        if isinstance(child, LeafNode):
            if len(child.keys) < self.min_leaf_keys:
                self._fix_leaf(node, i)
        elif len(child.children) < self.min_children:
            self._fix_internal(node, i)
        return True

    def _fix_leaf(self, parent: InternalNode, i: int) -> None:
        child = parent.children[i]
        left = parent.children[i - 1] if i > 0 else None
        right = parent.children[i + 1] if i + 1 < len(parent.children) else None
        if left is not None and len(left.keys) > self.min_leaf_keys:
            # 左の兄弟から末尾の 1 個を借りる
            child.keys.insert(0, left.keys.pop())
            child.values.insert(0, left.values.pop())
            parent.keys[i - 1] = child.keys[0]
        elif right is not None and len(right.keys) > self.min_leaf_keys:
            # 右の兄弟から先頭の 1 個を借りる
            child.keys.append(right.keys.pop(0))
            child.values.append(right.values.pop(0))
            parent.keys[i] = right.keys[0]
        elif left is not None:
            # 借りられないので左の兄弟と併合する（親の区切りキーを 1 つ消す）
            left.keys.extend(child.keys)
            left.values.extend(child.values)
            left.next = child.next
            del parent.keys[i - 1]
            del parent.children[i]
        else:
            assert right is not None
            child.keys.extend(right.keys)
            child.values.extend(right.values)
            child.next = right.next
            del parent.keys[i]
            del parent.children[i + 1]

    def _fix_internal(self, parent: InternalNode, i: int) -> None:
        child = parent.children[i]
        left = parent.children[i - 1] if i > 0 else None
        right = parent.children[i + 1] if i + 1 < len(parent.children) else None
        if left is not None and len(left.children) > self.min_children:
            # 親の区切りキーを下ろし、左の兄弟の末尾のキーを親へ上げる（回転）
            child.keys.insert(0, parent.keys[i - 1])
            child.children.insert(0, left.children.pop())
            parent.keys[i - 1] = left.keys.pop()
        elif right is not None and len(right.children) > self.min_children:
            child.keys.append(parent.keys[i])
            child.children.append(right.children.pop(0))
            parent.keys[i] = right.keys.pop(0)
        elif left is not None:
            # 併合: 左 + 親の区切りキー + 自分
            left.keys.append(parent.keys[i - 1])
            left.keys.extend(child.keys)
            left.children.extend(child.children)
            del parent.keys[i - 1]
            del parent.children[i]
        else:
            assert right is not None
            child.keys.append(parent.keys[i])
            child.keys.extend(right.keys)
            child.children.extend(right.children)
            del parent.keys[i]
            del parent.children[i + 1]
