"""2.5 木・ヒープ・グラフ — 解答例（グラフ）

演習の仕様は exercises/graphs.py の docstring を参照してください。
大きなグラフでも Python の再帰上限（既定 1000）に当たらないよう、探索はすべて反復で書いています。
"""
from __future__ import annotations

import heapq
import itertools
from collections import deque
from typing import Generic, Hashable, Iterable, Mapping, TypeVar

N = TypeVar("N", bound=Hashable)


def _adjacency(graph: Mapping[N, Iterable[N]]) -> dict[N, list[N]]:
    """隣接リストを list に固定し、隣接先にしか現れない頂点も（出る辺なしで）加える。

    graph の値がジェネレータでも 2 回以上走査できるように、最初に一度だけ list にする。
    dict は挿入順を保つので、頂点の順序（=結果の順序）が決定的になる。
    """
    adj: dict[N, list[N]] = {u: list(vs) for u, vs in graph.items()}
    for vs in list(adj.values()):
        for v in vs:
            adj.setdefault(v, [])
    return adj


# ---------------------------------------------------------------------------
# 演習4a: 幅優先探索による最短経路（重みなし）
# ---------------------------------------------------------------------------

def bfs_shortest_path(graph: Mapping[N, Iterable[N]], start: N, goal: N) -> list[N] | None:
    if start == goal:
        return [start]
    parent: dict[N, N] = {}
    seen = {start}
    queue = deque([start])
    while queue:
        u = queue.popleft()
        for v in graph.get(u, ()):
            if v in seen:
                continue
            seen.add(v)  # キューに入れる時点で「発見済み」にする（同じ頂点を二重に入れない）
            parent[v] = u
            if v == goal:
                # BFS は始点から近い順に頂点を発見するので、最初に見つけた経路が最短
                path = [v]
                while path[-1] != start:
                    path.append(parent[path[-1]])
                path.reverse()
                return path
            queue.append(v)
    return None


# ---------------------------------------------------------------------------
# 演習4b: トポロジカルソート（Kahn のアルゴリズム）と循環の検出
# ---------------------------------------------------------------------------

class DependencyCycleError(Exception):
    """グラフに循環があってトポロジカル順序が存在しない。cycle 属性に循環の経路を持つ。"""

    def __init__(self, cycle: list) -> None:
        self.cycle = cycle
        super().__init__("循環があります: " + " -> ".join(map(str, cycle)))


def topological_sort(graph: Mapping[N, Iterable[N]]) -> list[N]:
    adj = _adjacency(graph)
    indeg = {u: 0 for u in adj}
    for vs in adj.values():
        for v in vs:
            indeg[v] += 1
    # 入次数 0（=前提がすべて満たされた）頂点から順に出力し、その出る辺を消していく
    ready = deque(u for u in adj if indeg[u] == 0)
    order: list[N] = []
    while ready:
        u = ready.popleft()
        order.append(u)
        for v in adj[u]:
            indeg[v] -= 1
            if indeg[v] == 0:
                ready.append(v)
    if len(order) == len(adj):
        return order

    # 出力できずに残った頂点は、どれも「残った頂点からの入る辺」を持つ。
    # したがって残った頂点の中で前任者（predecessor）をたどり続けると、必ずどこかで同じ頂点に戻る
    remaining = {u for u in adj if indeg[u] > 0}
    preds: dict[N, list[N]] = {u: [] for u in remaining}
    for u in remaining:
        for v in adj[u]:
            if v in remaining:
                preds[v].append(u)
    walk: list[N] = []
    pos: dict[N, int] = {}
    x = next(u for u in adj if u in remaining)
    while x not in pos:
        pos[x] = len(walk)
        walk.append(x)
        x = preds[x][0]
    # walk は辺を逆向きにたどった列なので、反転すると辺の向きの循環になる
    cycle = list(reversed(walk[pos[x]:] + [x]))
    raise DependencyCycleError(cycle)


# ---------------------------------------------------------------------------
# 演習4c: ダイクストラ法
# ---------------------------------------------------------------------------

def dijkstra(
    graph: Mapping[N, Iterable[tuple[N, float]]], source: N
) -> tuple[dict[N, float], dict[N, N]]:
    adj = {u: list(es) for u, es in graph.items()}
    for u, es in adj.items():
        for v, w in es:
            if w < 0:
                raise ValueError(f"負の重みの辺があります: {u} -> {v} ({w})")
    dist: dict[N, float] = {source: 0}
    prev: dict[N, N] = {}
    done: set[N] = set()
    counter = itertools.count()  # 距離が同じとき頂点どうしを比較しないための通し番号
    heap: list[tuple[float, int, N]] = [(0, next(counter), source)]
    while heap:
        d, _, u = heapq.heappop(heap)
        if u in done:
            continue  # 古いエントリ（もっと短い距離で確定済み）は読み捨てる（遅延削除）
        # 未確定の中で最小の距離を持つ頂点は、これ以上短くならない（重みが非負だから）
        done.add(u)
        for v, w in adj.get(u, ()):
            nd = d + w
            if v not in dist or nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, next(counter), v))
    return dist, prev


def shortest_path(
    graph: Mapping[N, Iterable[tuple[N, float]]], source: N, target: N
) -> tuple[float, list[N]] | None:
    dist, prev = dijkstra(graph, source)
    if target not in dist:
        return None
    path = [target]
    while path[-1] != source:
        path.append(prev[path[-1]])
    path.reverse()
    return dist[target], path


# ---------------------------------------------------------------------------
# 演習4d: Union-Find とクラスカル法
# ---------------------------------------------------------------------------

class UnionFind(Generic[N]):
    def __init__(self, elements: Iterable[N] = ()) -> None:
        self._parent: dict[N, N] = {}
        self._size: dict[N, int] = {}
        self._components = 0
        for x in elements:
            self.add(x)

    def add(self, x: N) -> None:
        if x in self._parent:
            return
        self._parent[x] = x
        self._size[x] = 1
        self._components += 1

    def __len__(self) -> int:
        return len(self._parent)

    def __contains__(self, x: object) -> bool:
        return x in self._parent

    @property
    def components(self) -> int:
        return self._components

    def find(self, x: N) -> N:
        parent = self._parent
        if x not in parent:
            raise KeyError(x)
        root = x
        while parent[root] != root:
            root = parent[root]
        # 経路圧縮: たどった頂点をすべて根に直接つなぎ直す（次からは 1 歩で根に着く）
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a: N, b: N) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # サイズによる併合: 小さい木を大きい木の下につなぐ。木の高さが O(log n) に抑えられる
        if self._size[ra] < self._size[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        self._size[ra] += self._size[rb]
        self._components -= 1
        return True

    def connected(self, a: N, b: N) -> bool:
        return self.find(a) == self.find(b)

    def component_size(self, x: N) -> int:
        return self._size[self.find(x)]


def kruskal_mst(
    nodes: Iterable[N], edges: Iterable[tuple[N, N, float]]
) -> tuple[float, list[tuple[N, N, float]]]:
    uf: UnionFind[N] = UnionFind(nodes)
    total: float = 0
    chosen: list[tuple[N, N, float]] = []
    # 軽い辺から順に見て、「異なる木をつなぐ辺」だけを採用する（貪欲法）。
    # 同じ木の中の辺を足すと閉路ができるので捨てる。その判定を Union-Find がほぼ O(1) で行う
    for u, v, w in sorted(edges, key=lambda e: e[2]):
        if u not in uf or v not in uf:
            raise ValueError(f"nodes にない頂点を含む辺です: {(u, v, w)}")
        if uf.union(u, v):
            chosen.append((u, v, w))
            total += w
    return total, chosen


# ---------------------------------------------------------------------------
# 演習5: マイクロサービスの依存グラフ
# ---------------------------------------------------------------------------

def dependency_cycles(deps: Mapping[str, Iterable[str]]) -> list[list[str]]:
    adj = _adjacency(deps)
    # コサラジュのアルゴリズム（強連結成分分解）
    # 1) 元のグラフで DFS し、「帰りがけ（全子孫を調べ終えた）順」に頂点を並べる
    finished: list[str] = []
    visited: set[str] = set()
    for s in adj:
        if s in visited:
            continue
        visited.add(s)
        stack = [(s, iter(adj[s]))]
        while stack:
            u, it = stack[-1]
            for v in it:
                if v not in visited:
                    visited.add(v)
                    stack.append((v, iter(adj[v])))
                    break
            else:
                stack.pop()
                finished.append(u)
    # 2) 辺を逆向きにしたグラフで、帰りがけ順の遅いものから DFS する。1 回の DFS で届く範囲が 1 つの成分
    radj: dict[str, list[str]] = {u: [] for u in adj}
    for u, vs in adj.items():
        for v in vs:
            radj[v].append(u)
    assigned: set[str] = set()
    cycles: list[list[str]] = []
    for s in reversed(finished):
        if s in assigned:
            continue
        comp = [s]
        assigned.add(s)
        stack2 = [s]
        while stack2:
            u = stack2.pop()
            for v in radj[u]:
                if v not in assigned:
                    assigned.add(v)
                    comp.append(v)
                    stack2.append(v)
        # 2 頂点以上の成分、または自己ループのある 1 頂点が「循環」
        if len(comp) > 1 or s in adj[s]:
            cycles.append(sorted(comp))
    return sorted(cycles)


def blast_radius(deps: Mapping[str, Iterable[str]], service: str) -> set[str]:
    adj = _adjacency(deps)
    if service not in adj:
        raise KeyError(service)
    # 「service に（推移的に）依存しているサービス」= 逆向きのグラフで service から届く頂点
    radj: dict[str, list[str]] = {u: [] for u in adj}
    for u, vs in adj.items():
        for v in vs:
            radj[v].append(u)
    affected: set[str] = set()
    queue = deque([service])
    while queue:
        u = queue.popleft()
        for v in radj[u]:
            if v not in affected:
                affected.add(v)
                queue.append(v)
    affected.discard(service)  # 循環があると自分自身にも戻ってくるが、自分は含めない
    return affected


def rank_by_blast_radius(deps: Mapping[str, Iterable[str]]) -> list[tuple[str, int]]:
    adj = _adjacency(deps)
    ranking = [(s, len(blast_radius(adj, s))) for s in adj]
    return sorted(ranking, key=lambda t: (-t[1], t[0]))
