"""2.5 木・ヒープ・グラフ — 演習（木とヒープ: 演習1〜3）

各クラス・関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。
グラフの演習（演習4・5）は graphs.py にあります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.5          # 合格数を表示（trees と graphs の両方）
    python3 tools/check.py -v 2.5       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_trees

制約（学びのための縛り）:
    - 演習2 では heapq・sorted()・list.sort() を使わないでください（ヒープを自分で実装する）。
    - 演習3 では、接頭辞の検索に全単語の走査（startswith で全件を調べる等）を使わないでください。

注意: 昇順に挿入した二分探索木は高さ n の「一本道」になります。再帰で書くと、
深さが Python の再帰の上限（既定 1000）を超えて RecursionError になることがあります。
テストの木は深さ 300 程度までですが、反復（while ループと明示的なスタック）で書く練習をしましょう。
"""
from __future__ import annotations

from typing import Any, Callable, Generic, Iterable, TypeVar

K = TypeVar("K")
V = TypeVar("V")
T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 二分探索木
# ---------------------------------------------------------------------------

class BST(Generic[K, V]):
    """キーの大小で左右に振り分けて格納する二分探索木（Binary Search Tree）。キー → 値の対応表。

    どのノードについても「左部分木のキー < ノードのキー < 右部分木のキー」が成り立つ（BST 条件）。
    バランスは取らない（そのため挿入順によっては高さが n になる。README 参照）。

    - insert(key, value=None): 追加。キーが既にあれば値だけを更新する（要素数は増えない）。
    - get(key, default=None): 値を返す。なければ default。
    - key in t、len(t)
    - delete(key): 削除。なければ KeyError。
        - 葉: そのまま取り除く
        - 子が 1 つ: その子で置き換える
        - 子が 2 つ: 右部分木の最小ノード（後続ノード, successor）のキーと値を写し、
          後続ノードの方を取り除く（後続ノードは左の子を持たないので、上の 2 つのどちらかになる）
    - inorder(): キーを昇順に並べたリストを返す（中間順走査, in-order traversal）。
    - height(): 木の高さ。根から葉までの最長経路上の「ノード数」で数える。空なら 0、根だけなら 1。
    - min() / max(): 最小・最大のキー。空なら ValueError。
    - range_keys(lo, hi): lo <= key < hi を満たすキーを昇順のリストで返す。
      範囲に関係のない部分木には降りないこと（O(高さ + 結果の件数)）。lo >= hi なら []。

    >>> t = BST()
    >>> for k in (50, 30, 70, 20, 40): t.insert(k)
    >>> t.inorder()
    [20, 30, 40, 50, 70]
    >>> t.height()
    3
    >>> t.range_keys(25, 50)
    [30, 40]

    ヒント:
    - ノードは key・value・left・right を持つ小さなクラスにする（__slots__ を付けるとよい）。
    - delete では「削除するノード」と「その親」を両方覚えながら降りると、つなぎ替えが書きやすい。
    - inorder は「左へ降りられるだけ降りてスタックに積む → 1 つ取り出して出力 → 右の子へ」を繰り返す。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習1: BST.__init__ を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習1: BST.__len__ を実装してください")

    def insert(self, key: K, value: V | None = None) -> None:
        raise NotImplementedError("演習1: BST.insert を実装してください")

    def get(self, key: K, default: V | None = None) -> V | None:
        raise NotImplementedError("演習1: BST.get を実装してください")

    def __contains__(self, key: object) -> bool:
        raise NotImplementedError("演習1: BST.__contains__ を実装してください")

    def delete(self, key: K) -> None:
        raise NotImplementedError("演習1: BST.delete を実装してください")

    def inorder(self) -> list[K]:
        raise NotImplementedError("演習1: BST.inorder を実装してください")

    def height(self) -> int:
        raise NotImplementedError("演習1: BST.height を実装してください")

    def min(self) -> K:
        raise NotImplementedError("演習1: BST.min を実装してください")

    def max(self) -> K:
        raise NotImplementedError("演習1: BST.max を実装してください")

    def range_keys(self, lo: K, hi: K) -> list[K]:
        raise NotImplementedError("演習1: BST.range_keys を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 二分ヒープ（最小ヒープ）と top-k
# ---------------------------------------------------------------------------

class MinHeap(Generic[T]):
    """配列で表した二分ヒープ。根（添字 0）が常に最小の要素になる優先度付きキュー。

    配列の添字 i の要素について、子は 2i+1 と 2i+2、親は (i-1)//2。
    ヒープ条件: どの i についても a[i] <= a[2i+1] かつ a[i] <= a[2i+2]（子が存在すれば）。

    - MinHeap(items=()): items からヒープを作る。ボトムアップ構築（Floyd の方法）で O(n) にすること。
      （テストは、降順の 1000 要素から作るときの比較回数が 2000 回以下であることを確かめます）
    - push(item): O(log n)。末尾に追加して、親より小さい間は上へ移動する（sift up）。
    - pop(): 最小の要素を取り出して返す。O(log n)。空なら IndexError。
      末尾の要素を根に移し、子より大きい間は小さい方の子と入れ替えて下へ移動する（sift down）。
    - peek(): 最小の要素を取り出さずに返す。空なら IndexError。
    - len(h)
    - to_list(): 内部の配列のコピーを返す（テストがヒープ条件を確かめるために使う）。

    要素どうしの比較には < だけを使えば十分です（(優先度, 名前) のようなタプルも入れられる）。

    >>> h = MinHeap([5, 3, 8, 1])
    >>> h.pop(), h.pop()
    (1, 3)
    >>> h.push(2); h.peek()
    2

    ヒント: ボトムアップ構築は「最後の内部ノード（添字 n//2 - 1）から根に向かって、順に sift down する」。
    """

    def __init__(self, items: Iterable[T] = ()) -> None:
        raise NotImplementedError("演習2: MinHeap.__init__ を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習2: MinHeap.__len__ を実装してください")

    def to_list(self) -> list[T]:
        raise NotImplementedError("演習2: MinHeap.to_list を実装してください")

    def push(self, item: T) -> None:
        raise NotImplementedError("演習2: MinHeap.push を実装してください")

    def peek(self) -> T:
        raise NotImplementedError("演習2: MinHeap.peek を実装してください")

    def pop(self) -> T:
        raise NotImplementedError("演習2: MinHeap.pop を実装してください")


def top_k(items: Iterable[T], k: int, key: Callable[[T], Any] | None = None) -> list[T]:
    """items の中で key(x) が大きい上位 k 件を、大きい順のリストで返す。

    - key を省略したら要素そのものを比べる。
    - k < 0 なら ValueError、k == 0 なら []。件数が k 未満なら全件を大きい順に返す。
    - キーが等しい要素どうしの順序は問わない。
    - items は 1 回しか走査できないイテレータでもよい（ログのストリームなどを想定）。
    - 全体をソートせず、サイズ k の MinHeap を使って O(n log k) 時間・O(k) メモリで求めること。
      （テストは、1 万件から上位 10 件を選ぶときの比較回数が 3 万回未満であることを確かめます）

    >>> top_k([5, 1, 9, 3, 7], 2)
    [9, 7]
    >>> top_k(["kiwi", "banana", "fig"], 1, key=len)
    ['banana']

    ヒント:
    - ヒープの根は「現時点の上位 k 件の中で最小のもの」。新しい要素がそれより大きいときだけ入れ替える。
    - ヒープには (キー, 通し番号, 要素) のタプルを入れるとよい。キーが等しいとき、
      通し番号で順序が決まるので、要素そのもの（比較できないかもしれない）を比べずに済む。
    """
    raise NotImplementedError("演習2: top_k を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: トライ木（接頭辞木）とオートコンプリート
# ---------------------------------------------------------------------------

class Trie:
    """文字列の集合を、1 文字ずつの枝をたどる木で表す。共通の接頭辞を持つ単語は途中まで道を共有する。

    - insert(word): 単語を追加する。すでにあれば何もしない。空文字列 "" も単語として扱える。
    - word in trie: 単語として登録されているか（接頭辞にすぎないものは False）。
    - starts_with(prefix): prefix で始まる単語が 1 つでもあるか。
    - autocomplete(prefix, limit=10): prefix で始まる単語を辞書順（Python の文字列の大小順）に
      最大 limit 件返す。prefix 自身が単語なら先頭に含まれる。limit < 0 なら ValueError、0 なら []。
    - len(trie): 登録されている単語の数。

    >>> t = Trie()
    >>> for w in ["car", "card", "care", "cat", "dog"]: t.insert(w)
    >>> t.autocomplete("car")
    ['car', 'card', 'care']
    >>> t.autocomplete("ca", limit=2)
    ['car', 'card']

    ヒント:
    - ノードは「子ノードの辞書（文字 → ノード）」と「ここで単語が終わるか（bool）」を持つ。
    - prefix の位置のノードまで降りたら、そこから深さ優先で、子を文字の昇順にたどる
      （行きがけ順に出力する）と辞書順になる。limit 件に達したら打ち切る。
    - 明示的なスタックを使うなら、子を「逆順に」積むと、昇順に取り出せる。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習3: Trie.__init__ を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習3: Trie.__len__ を実装してください")

    def insert(self, word: str) -> None:
        raise NotImplementedError("演習3: Trie.insert を実装してください")

    def __contains__(self, word: object) -> bool:
        raise NotImplementedError("演習3: Trie.__contains__ を実装してください")

    def starts_with(self, prefix: str) -> bool:
        raise NotImplementedError("演習3: Trie.starts_with を実装してください")

    def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        raise NotImplementedError("演習3: Trie.autocomplete を実装してください")
