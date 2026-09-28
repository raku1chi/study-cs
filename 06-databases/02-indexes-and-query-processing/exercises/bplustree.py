"""6.2 インデックスとクエリ処理 — 演習1: B+木を実装する

データベースのインデックスの標準的な構造である B+木（B+ tree）を、メモリ上に実装します。
ディスク上の B+木では 1 つのノードが 1 ページ（8KB や 16KB）に対応します。ここではノードを
訪れた回数を `pages_read` に数えて、「ページを何枚読んだか」という I/O コストを観察します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.2
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_bplustree

木の形の約束（order = 1 つのノードが持てる子の最大数、3 以上）:
    - 内部ノード（InternalNode）は keys（区切りキー）と children を持ち、
      len(children) == len(keys) + 1。子の数は最大 order。
    - 区切りキー keys[i] について、children[i] の中のキーはすべて keys[i] 未満、
      children[i+1] の中のキーはすべて keys[i] 以上。
    - 葉（LeafNode）は keys と values を持つ（keys[j] の値が values[j]）。キーの数は最大 order - 1。
      葉は next で右隣の葉につながる（一番右の葉の next は None）。
    - ルート以外のノードは半分以上埋まっている:
        葉のキーの数 >= order // 2、内部ノードの子の数 >= (order + 1) // 2
    - ルートが内部ノードなら子は 2 つ以上。ルートが葉なら 0 個以上 order - 1 個以下のキー。
    - すべての葉は同じ深さにある。キーは木全体で一意（同じキーの挿入は値の上書き）。

    例（order = 4）:
                        [ 7 | 13 ]                  ← 内部ノード（ルート）
                 /          |          \\
          [1 3 5] ──→ [7 9 11] ──→ [13 20]         ← 葉（next でつながる）

テストは `tree.root` から LeafNode / InternalNode をたどって木の形を確かめます。
下の 2 つのノードのクラスを使い、`self.root` に木の根を置いてください。
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right  # noqa: F401  ノード内の探索に使えます
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 提供済み: ノードの型（変更しなくてよい）
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class LeafNode:
    """葉。keys は昇順、values[j] が keys[j] の値。next は右隣の葉。"""

    keys: list = field(default_factory=list)
    values: list = field(default_factory=list)
    next: LeafNode | None = field(default=None, repr=False)


@dataclass(eq=False)
class InternalNode:
    """内部ノード。keys は区切りキー（昇順）、len(children) == len(keys) + 1。"""

    keys: list = field(default_factory=list)
    children: list = field(default_factory=list)


class BPlusTree:
    """B+木（キーは互いに比較できる値。キーの重複はない）。

    >>> t = BPlusTree(order=4)
    >>> for k in [5, 1, 9, 3, 7]:
    ...     t.insert(k, f"v{k}")
    >>> t.search(7), t.search(4)
    ('v7', None)
    >>> t.range_scan(3, 7)
    [(3, 'v3'), (5, 'v5'), (7, 'v7')]
    >>> len(t), t.height()
    (5, 2)
    """

    def __init__(self, order: int = 4) -> None:
        """空の木を作る。order が 3 未満なら ValueError。

        - self.order: order
        - self.root: 空の LeafNode
        - self.pages_read: 0（ノードを 1 つ訪れるたびに 1 増やすカウンタ。利用者が 0 に戻してよい）
        """
        if order < 3:
            raise ValueError(f"order は 3 以上にしてください: {order}")
        self.order = order
        self.root: LeafNode | InternalNode = LeafNode()
        self.pages_read = 0
        self._size = 0

    def __len__(self) -> int:
        """格納しているキーの数。"""
        return self._size

    def height(self) -> int:
        """木の高さ（段数）。葉だけの木は 1。"""
        h, node = 1, self.root
        while isinstance(node, InternalNode):
            node = node.children[0]
            h += 1
        return h

    # -----------------------------------------------------------------------
    # 演習1-1（★☆☆）: 検索
    # -----------------------------------------------------------------------

    def search(self, key: Any, default: Any = None) -> Any:
        """key の値を返す。なければ default。

        ルートから葉まで 1 本の道をたどる。訪れたノードの数だけ pages_read を増やすこと
        （つまり 1 回の検索で pages_read はちょうど height() 増える）。

        ヒント: 内部ノードでは bisect_right(node.keys, key) が進むべき子の番号になる
        （区切りキーと等しいキーは右の子にある）。
        """
        raise NotImplementedError("演習1-1: search を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-2（★★★）: 挿入と分割
    # -----------------------------------------------------------------------

    def insert(self, key: Any, value: Any) -> None:
        """key に value を格納する。既に key があれば値を上書きする（len は変わらない）。

        葉があふれたら（キーが order 個になったら）分割する:
          - 前半 (order + 1) // 2 個を元の葉に残し、残りを新しい葉に移す。
          - 新しい葉を next の連結リストに挿入する。
          - 新しい葉の先頭キーを「コピーして」親に区切りキーとして追加する。
        内部ノードがあふれたら（子が order + 1 個になったら）分割する:
          - 中央のキー keys[len(keys) // 2] を親に「移動」し（分割後のどちらのノードにも残さない）、
            その左側のキーと子を元のノードに、右側を新しいノードに分ける。
        ルートが分割されたら、2 つの子を持つ新しいルートを作る（木が 1 段高くなる）。

        pages_read は、検索と同じくたどったノードの数だけ増やしてよい（テストでは検査しない）。

        ヒント: 再帰で書き、子の分割が起きたら (区切りキー, 新しいノード) を親に返すとよい。
        """
        raise NotImplementedError("演習1-2: insert を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-3（★★☆）: 範囲検索
    # -----------------------------------------------------------------------

    def range_scan(self, lo: Any = None, hi: Any = None) -> list[tuple[Any, Any]]:
        """lo <= key <= hi のキーと値の組を、キーの昇順のリストで返す。

        - lo が None なら下限なし、hi が None なら上限なし。lo > hi なら空リスト。
        - lo の位置の葉まで木を 1 回だけ下り、あとは葉の next をたどること
          （木を何度も上り下りしない）。hi を超えるキーに出会ったら、そこで止める。
        - pages_read は、下るときのノードと、たどった葉の数だけ増やす。

        SQL の `WHERE key BETWEEN lo AND hi ORDER BY key` を、インデックスで実行する動きそのもの。
        """
        raise NotImplementedError("演習1-3: range_scan を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-4（★★☆）: 不変条件の検査
    # -----------------------------------------------------------------------

    def check_invariants(self) -> None:
        """木がモジュールの docstring の約束をすべて満たしているか検査する。

        違反があれば AssertionError を送出する（assert 文ではなく raise AssertionError(...) を
        使うこと。python -O で assert 文は無効になるため）。検査する項目:
          1. 各ノードの keys が狭義の昇順
          2. 各キーが、親の区切りキーから決まる範囲 [下限, 上限) に収まっている
          3. 内部ノードで len(children) == len(keys) + 1
          4. ノードの充填率（最大数・最小数。ルートの特例に注意）、葉の len(values) == len(keys)
          5. すべての葉が同じ深さ
          6. 葉の next をたどると、すべての葉を左から順に 1 回ずつ訪れ、最後が None
          7. 葉のキーの総数が len(self) と等しい

        ヒント: 再帰関数に (ノード, 下限, 上限, 深さ) を渡す。子 i の範囲は
        [keys[i-1], keys[i])（端は親から受け取った範囲）になる。
        """
        raise NotImplementedError("演習1-4: check_invariants を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-5（★★★ 発展・任意）: 削除
    # -----------------------------------------------------------------------

    def delete(self, key: Any) -> bool:
        """key を削除し、削除したら True、なければ False を返す。

        ノードが最小数を下回ったら、兄弟ノードから 1 つ借りる（再分配）か、兄弟と併合する。
        併合で親が最小数を下回ったら、同じ処理を親に対して繰り返す。ルートの内部ノードの子が
        1 つになったら、その子を新しいルートにする（木が 1 段低くなる）。

        - 葉から借りたら、親の区切りキーを「右側の葉の先頭キー」に更新する。
        - 内部ノードどうしでは、親の区切りキーを下ろし、兄弟の端のキーを親へ上げる（回転）。
        - 削除したキーと同じ値の区切りキーが上の階層に残っていても構わない（範囲の不変条件は保たれる）。

        発展課題です。実装しない場合は、この NotImplementedError をそのまま残してください
        （削除のテストはスキップされます）。
        """
        raise NotImplementedError("演習1-5（発展）: delete は未実装です")
