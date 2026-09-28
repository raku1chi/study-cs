"""2.5 木・ヒープ・グラフ — 演習（グラフ: 演習4・5）

各クラス・関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.5          # 合格数を表示（trees と graphs の両方）
    python3 tools/check.py -v 2.5       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_graphs

グラフの表し方（この演習の約束）:
    - 重みなしの有向グラフ: 隣接リストの dict。graph[u] は u から辺が出ている頂点の並び。
          {"A": ["B", "C"], "B": ["C"], "C": []}
    - 重み付きの有向グラフ: graph[u] は (隣の頂点, 重み) の並び。
          {"東京": [("品川", 7), ("新宿", 9)], "品川": [], "新宿": []}
    - 隣接先にだけ現れてキーにない頂点は「出る辺のない頂点」とみなす。
    - graph[u] はリストとは限らない（1 回しか走査できないイテレータのこともある）。
      何度も走査するなら、最初に list にしておくこと。
    - 頂点はハッシュ可能な任意の値（文字列・整数・タプルなど）。大小比較できるとは限らない。

制約: graphlib モジュールは使わないでください（ヒープには heapq を使ってかまいません）。
注意: グラフが大きいと、再帰で書いた DFS は Python の再帰の上限（既定 1000）に当たります。
      演習5 のテストには 5000 頂点の循環があるので、明示的なスタックを使って反復で書いてください。
"""
from __future__ import annotations

import heapq  # noqa: F401  演習4c で使えます
import itertools  # noqa: F401  演習4c で使えます（itertools.count で通し番号を作る）
from collections import deque  # noqa: F401  BFS のキューに使えます
from typing import Generic, Hashable, Iterable, Mapping, TypeVar

N = TypeVar("N", bound=Hashable)


# ---------------------------------------------------------------------------
# 演習4（★★★）: グラフアルゴリズム
# ---------------------------------------------------------------------------

def bfs_shortest_path(graph: Mapping[N, Iterable[N]], start: N, goal: N) -> list[N] | None:
    """演習4a: 重みなしグラフで、start から goal への最短経路（辺の数が最小）を返す。

    - 戻り値は [start, ..., goal] の頂点のリスト。最短経路が複数あればどれでもよい。
    - start == goal なら [start]。たどり着けなければ None。

    >>> g = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
    >>> len(bfs_shortest_path(g, "A", "D"))
    3

    ヒント: 幅優先探索（キューは collections.deque）。頂点を「発見」したときに
    「どの頂点から来たか」（parent）を記録し、goal を見つけたら parent を逆にたどる。
    """
    raise NotImplementedError("演習4a: bfs_shortest_path を実装してください")


class DependencyCycleError(Exception):
    """グラフに循環があってトポロジカル順序が存在しないことを表す例外（実装済み）。

    cycle 属性に循環の経路を持つ。経路は始点に戻ってくる形のリストで、
    隣り合う頂点の間には必ず辺がある（例: ["a", "b", "c", "a"] は a->b->c->a）。
    """

    def __init__(self, cycle: list) -> None:
        self.cycle = cycle
        super().__init__("循環があります: " + " -> ".join(map(str, cycle)))


def topological_sort(graph: Mapping[N, Iterable[N]]) -> list[N]:
    """演習4b: 辺 u -> v を「u は v より前に来なければならない」と読み、全頂点を並べて返す。

    - すべての辺 u -> v について、結果の中で u が v より前にあること。
    - すべての頂点（隣接先にだけ現れる頂点も）をちょうど 1 回ずつ含むこと。
    - 条件を満たす順序が複数あるときは、どれを返してもよい。
    - 循環があれば DependencyCycleError(cycle) を送出する。cycle は実在する循環の経路
      （自己ループ a -> a なら ["a", "a"]）。

    >>> topological_sort({"設計": ["実装"], "実装": ["テスト"], "テスト": []})
    ['設計', '実装', 'テスト']

    ヒント（Kahn のアルゴリズム）:
    1. 各頂点の入次数（入ってくる辺の数）を数える。
    2. 入次数 0 の頂点をキューに入れ、取り出すたびに結果に加え、そこから出る辺を消す
       （行き先の入次数を 1 減らし、0 になったらキューに入れる）。
    3. 全頂点を出力できなければ循環がある。残った頂点はどれも「残った頂点からの入る辺」を
       持つので、残った頂点の中で「前の頂点（predecessor）」をたどり続けると必ず同じ頂点に戻る。
       たどった列を反転すれば、辺の向きの循環になる。
    """
    raise NotImplementedError("演習4b: topological_sort を実装してください")


def dijkstra(
    graph: Mapping[N, Iterable[tuple[N, float]]], source: N
) -> tuple[dict[N, float], dict[N, N]]:
    """演習4c: 重み付きグラフで、source から各頂点への最短距離を求める（ダイクストラ法）。

    - 戻り値は (dist, prev)。
        - dist[v]: source から v への最短距離。到達できる頂点だけを含む（dist[source] == 0）。
        - prev[v]: 最短経路で v の直前にある頂点。source 自身は含まない。
    - 負の重みの辺が 1 本でもあれば（到達できるかどうかに関わらず）ValueError。

    ヒント:
    - heapq に (距離, 通し番号, 頂点) を入れる。距離が同じとき頂点どうしが比較されないよう、
      通し番号（itertools.count()）をはさむ。頂点が大小比較できるとは限らないため。
    - 距離が更新されるたびに新しいエントリを push し、取り出したときに確定済みなら読み捨てる
      （遅延削除）。「ヒープの中の値を減らす」操作は heapq にはない。
    """
    raise NotImplementedError("演習4c: dijkstra を実装してください")


def shortest_path(
    graph: Mapping[N, Iterable[tuple[N, float]]], source: N, target: N
) -> tuple[float, list[N]] | None:
    """演習4c: source から target への (最短距離, 経路の頂点リスト) を返す。到達できなければ None。

    dijkstra() の prev を target から逆にたどって経路を復元する。source == target なら (0, [source])。

    >>> g = {"東京": [("品川", 7), ("新宿", 9)], "品川": [("新宿", 1)], "新宿": []}
    >>> shortest_path(g, "東京", "新宿")
    (8, ['東京', '品川', '新宿'])
    """
    raise NotImplementedError("演習4c: shortest_path を実装してください")


class UnionFind(Generic[N]):
    """演習4d: 互いに素な集合を管理する Union-Find（素集合データ構造, disjoint-set）。

    - UnionFind(elements=()): 各要素を 1 要素の集合として登録する。
    - add(x): 要素を追加する（すでにあれば何もしない）。
    - find(x): x が属する集合の代表元（根）を返す。未登録なら KeyError。
    - union(a, b): a と b の集合を 1 つにまとめる。まとめたら True、もともと同じ集合なら False。
      未登録の要素なら KeyError。
    - connected(a, b): 同じ集合に属するか。
    - component_size(x): x が属する集合の要素数。
    - components（プロパティ）: 集合の数。len(uf): 要素の数。x in uf: 登録済みか。

    次の 2 つの工夫を両方入れること（テストは 2 万要素の鎖を作って速さを確かめます）:
    - 経路圧縮（path compression）: find でたどった要素を、根に直接つなぎ直す。
    - サイズ（または rank）による併合: 小さい木の根を、大きい木の根の下につなぐ。

    >>> uf = UnionFind("abcd")
    >>> uf.union("a", "b"), uf.union("b", "a")
    (True, False)
    >>> uf.connected("a", "b"), uf.components
    (True, 3)

    ヒント: parent（要素 → 親）と size（根 → 集合の要素数）の 2 つの dict で表せる。
    find は再帰でも書けるが、鎖が長いと再帰の上限に当たるので、ループで 2 回たどる
    （1 回目で根を見つけ、2 回目で経路上の要素の親を根に書き換える）とよい。
    """

    def __init__(self, elements: Iterable[N] = ()) -> None:
        raise NotImplementedError("演習4d: UnionFind.__init__ を実装してください")

    def add(self, x: N) -> None:
        raise NotImplementedError("演習4d: UnionFind.add を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習4d: UnionFind.__len__ を実装してください")

    def __contains__(self, x: object) -> bool:
        raise NotImplementedError("演習4d: UnionFind.__contains__ を実装してください")

    @property
    def components(self) -> int:
        raise NotImplementedError("演習4d: UnionFind.components を実装してください")

    def find(self, x: N) -> N:
        raise NotImplementedError("演習4d: UnionFind.find を実装してください")

    def union(self, a: N, b: N) -> bool:
        raise NotImplementedError("演習4d: UnionFind.union を実装してください")

    def connected(self, a: N, b: N) -> bool:
        raise NotImplementedError("演習4d: UnionFind.connected を実装してください")

    def component_size(self, x: N) -> int:
        raise NotImplementedError("演習4d: UnionFind.component_size を実装してください")


def kruskal_mst(
    nodes: Iterable[N], edges: Iterable[tuple[N, N, float]]
) -> tuple[float, list[tuple[N, N, float]]]:
    """演習4d: 無向グラフの最小全域木（最小全域森）をクラスカル法で求める。

    - nodes: すべての頂点。edges: (u, v, 重み) の無向辺。重みは負でもよい。
    - 戻り値は (重みの合計, 選んだ辺のリスト)。選んだ辺は入力と同じ (u, v, 重み) の形で返す。
    - グラフが連結でなければ、各連結成分の最小全域木を合わせたもの（最小全域森）を返す。
      このとき選ぶ辺の数は「頂点数 − 連結成分の数」。
    - nodes にない頂点を含む辺があれば ValueError。

    >>> kruskal_mst("ABC", [("A", "B", 1), ("B", "C", 2), ("A", "C", 3)])
    (3, [('A', 'B', 1), ('B', 'C', 2)])

    ヒント: 辺を重みの小さい順に見て、両端がまだ別の集合なら採用して union する（貪欲法）。
    同じ集合どうしをつなぐ辺は閉路を作るので捨てる。
    """
    raise NotImplementedError("演習4d: kruskal_mst を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: マイクロサービスの依存グラフ（循環の検出と影響範囲）
# ---------------------------------------------------------------------------
# deps[a] = [b, c] は「サービス a がサービス b と c を呼び出している（依存している）」を表す。
# b が止まると、b に依存している a も影響を受ける。

def dependency_cycles(deps: Mapping[str, Iterable[str]]) -> list[list[str]]:
    """依存関係の循環を、強連結成分（strongly connected component）として列挙する。

    - 互いに（推移的に）依存し合っているサービスの集まり（強連結成分）のうち、
      2 つ以上のサービスからなるもの、または自分自身に依存している（自己ループのある）1 サービスを返す。
    - 各成分は名前の昇順のリスト。全体は成分のリストの昇順（先頭の名前で比べる）。
    - 循環がなければ []。

    >>> dependency_cycles({"a": ["b"], "b": ["a", "c"], "c": []})
    [['a', 'b']]

    ヒント（コサラジュのアルゴリズム）:
    1. 元のグラフで DFS し、各頂点を「帰りがけ順」（その頂点から先をすべて調べ終えた順）に並べる。
    2. 辺をすべて逆向きにしたグラフで、帰りがけ順の遅いものから DFS する。
       まだ割り当てていない頂点のうち、1 回の DFS で届く範囲が 1 つの強連結成分になる。
    （タージャンのアルゴリズムでもよい。どちらも O(V + E)。再帰ではなく反復で書くこと）
    """
    raise NotImplementedError("演習5: dependency_cycles を実装してください")


def blast_radius(deps: Mapping[str, Iterable[str]], service: str) -> set[str]:
    """service が停止したときに影響を受けうる、すべてのサービス（推移的な依存元）の集合を返す。

    - service に直接または間接的に依存しているサービスをすべて含む。service 自身は含めない
      （循環があって自分に戻ってきても含めない）。
    - service がグラフのどこにも（キーにも依存先にも）現れなければ KeyError。

    >>> blast_radius({"web": ["api"], "api": ["db"], "batch": ["db"]}, "db") == {"web", "api", "batch"}
    True

    ヒント: 辺を逆向きにしたグラフ（「誰に依存されているか」）を作り、service から BFS/DFS する。
    """
    raise NotImplementedError("演習5: blast_radius を実装してください")


def rank_by_blast_radius(deps: Mapping[str, Iterable[str]]) -> list[tuple[str, int]]:
    """全サービスについて (サービス名, 影響範囲の大きさ) を求め、影響範囲の大きい順に並べて返す。

    - 影響範囲の大きさ = len(blast_radius(deps, サービス))。
    - 依存先にだけ現れるサービス（データベースなど）も含める。
    - 大きさが同じなら名前の昇順。

    設計レビューや障害訓練で「どこが止まると一番まずいか」を洗い出すのに使える。
    """
    raise NotImplementedError("演習5: rank_by_blast_radius を実装してください")
