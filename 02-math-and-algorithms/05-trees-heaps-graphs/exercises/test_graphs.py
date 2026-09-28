"""2.5 木・ヒープ・グラフ — テスト（グラフ: 演習4・5）

実行: python3 tools/check.py 2.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import functools
import random
import threading
import unittest
from collections import deque

from graphs import (
    DependencyCycleError,
    UnionFind,
    bfs_shortest_path,
    blast_radius,
    dependency_cycles,
    dijkstra,
    kruskal_mst,
    rank_by_blast_radius,
    shortest_path,
    topological_sort,
)


def with_timeout(seconds: float):
    """クラスの各テストを別スレッドで実行し、seconds 秒で終わらなければ失敗にする。

    無限ループや指数時間の実装でも、テスト全体が止まらずに失敗として報告されるようにするため。
    """

    def wrap(fn):
        @functools.wraps(fn)
        def wrapper(self):
            errors: list[BaseException] = []

            def target() -> None:
                try:
                    fn(self)
                except BaseException as exc:  # noqa: BLE001 — テストのスレッドへ例外を運ぶ
                    errors.append(exc)

            t = threading.Thread(target=target, daemon=True)
            t.start()
            t.join(seconds)
            if t.is_alive():
                self.fail(f"{seconds} 秒以内に終わりません（無限ループや指数時間になっていませんか）")
            if errors:
                raise errors[0]

        return wrapper

    def decorate(cls):
        for name, value in list(vars(cls).items()):
            if name.startswith("test") and callable(value):
                setattr(cls, name, wrap(value))
        return cls

    return decorate


# ----------------------------------------------------------------------------
# テスト用の参照実装・ヘルパー（素朴だが確実なもの）
# ----------------------------------------------------------------------------

def all_nodes(graph):
    nodes = set(graph)
    for vs in graph.values():
        nodes.update(v[0] if isinstance(v, tuple) else v for v in vs)
    return nodes


def bfs_distances(graph, start):
    dist = {start: 0}
    q = deque([start])
    while q:
        u = q.popleft()
        for v in graph.get(u, ()):
            if v not in dist:
                dist[v] = dist[u] + 1
                q.append(v)
    return dist


def bellman_ford(graph, source):
    nodes = all_nodes(graph)
    dist = {n: float("inf") for n in nodes}
    dist[source] = 0
    for _ in range(len(nodes)):
        for u, es in graph.items():
            for v, w in es:
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
    return {n: d for n, d in dist.items() if d != float("inf")}


def reachable(graph, start):
    seen = {start}
    stack = [start]
    while stack:
        u = stack.pop()
        for v in graph.get(u, ()):
            if v not in seen:
                seen.add(v)
                stack.append(v)
    return seen


def random_digraph(rng, n, p):
    return {i: [j for j in range(n) if j != i and rng.random() < p] for i in range(n)}


class Opaque:
    """大小比較のできない頂点（heapq で頂点どうしを比べるとエラーになる）。"""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"Opaque({self.name})"


# ----------------------------------------------------------------------------
# 演習4a: BFS
# ----------------------------------------------------------------------------

@with_timeout(5)
class TestExercise4BFS(unittest.TestCase):
    def assert_valid_path(self, graph, path, start, goal):
        self.assertEqual(path[0], start)
        self.assertEqual(path[-1], goal)
        for u, v in zip(path, path[1:]):
            self.assertIn(v, graph.get(u, ()), f"{u} -> {v} という辺はありません")

    def test_example(self):
        g = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": ["E"], "E": []}
        path = bfs_shortest_path(g, "A", "E")
        self.assertEqual(len(path), 4)
        self.assert_valid_path(g, path, "A", "E")
        self.assertEqual(bfs_shortest_path(g, "A", "C"), ["A", "C"])

    def test_start_equals_goal_and_unreachable(self):
        g = {"A": ["B"], "B": [], "C": ["A"]}
        self.assertEqual(bfs_shortest_path(g, "A", "A"), ["A"])
        self.assertIsNone(bfs_shortest_path(g, "A", "C"), "辺の向きに注意（C -> A はあるが A -> C はない）")
        self.assertIsNone(bfs_shortest_path(g, "A", "Z"))

    def test_grid_with_walls(self):
        maze = [
            "S....#....",
            ".###.#.##.",
            ".#...#..#.",
            ".#.####.#.",
            ".#......#G",
        ]
        cells = {(r, c) for r, row in enumerate(maze) for c, ch in enumerate(row) if ch != "#"}
        graph = {
            (r, c): [(r + dr, c + dc) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)) if (r + dr, c + dc) in cells]
            for r, c in cells
        }
        path = bfs_shortest_path(graph, (0, 0), (4, 9))
        self.assert_valid_path(graph, path, (0, 0), (4, 9))
        self.assertEqual(len(path) - 1, bfs_distances(graph, (0, 0))[(4, 9)])

    def test_random_graphs_give_shortest_length(self):
        rng = random.Random(40)
        for _ in range(30):
            g = random_digraph(rng, 30, 0.08)
            s, t = rng.randrange(30), rng.randrange(30)
            path = bfs_shortest_path(g, s, t)
            dist = bfs_distances(g, s)
            if t not in dist:
                self.assertIsNone(path)
            else:
                self.assert_valid_path(g, path, s, t)
                self.assertEqual(len(path) - 1, dist[t])


# ----------------------------------------------------------------------------
# 演習4b: トポロジカルソート
# ----------------------------------------------------------------------------

@with_timeout(5)
class TestExercise4TopologicalSort(unittest.TestCase):
    def assert_topological(self, graph, order):
        self.assertEqual(len(order), len(set(order)), "同じ頂点が 2 回出てはいけない")
        self.assertEqual(set(order), all_nodes(graph), "すべての頂点（隣接先だけに現れる頂点も）を含むこと")
        pos = {u: i for i, u in enumerate(order)}
        for u, vs in graph.items():
            for v in vs:
                self.assertLess(pos[u], pos[v], f"辺 {u} -> {v} の順序が逆です")

    def test_project_plan(self):
        g = {
            "要件定義": ["設計"],
            "設計": ["実装", "テスト計画"],
            "実装": ["結合テスト"],
            "テスト計画": ["結合テスト"],
            "結合テスト": ["リリース"],
            "法務確認": ["リリース"],
        }
        order = topological_sort(g)
        self.assert_topological(g, order)
        self.assertEqual(order[-1], "リリース")

    def test_empty_and_isolated(self):
        self.assertEqual(topological_sort({}), [])
        g = {"a": [], "b": [], "c": ["d"]}
        self.assert_topological(g, topological_sort(g))

    def test_random_dags(self):
        rng = random.Random(41)
        for _ in range(50):
            n = rng.randrange(1, 40)
            labels = list(range(n))
            rng.shuffle(labels)
            g = {labels[i]: [labels[j] for j in range(i + 1, n) if rng.random() < 0.15] for i in range(n)}
            self.assert_topological(g, topological_sort(g))

    def test_accepts_iterators_as_adjacency(self):
        g = {"a": iter(["b", "c"]), "b": iter(["c"]), "c": iter([])}
        self.assertEqual(topological_sort(g), ["a", "b", "c"])

    def assert_cycle_path(self, graph, cycle):
        self.assertGreaterEqual(len(cycle), 2)
        self.assertEqual(cycle[0], cycle[-1], "循環の経路は始点に戻ってくること（例: ['a', 'b', 'a']）")
        for u, v in zip(cycle, cycle[1:]):
            self.assertIn(v, graph.get(u, ()), f"循環の経路に存在しない辺 {u} -> {v} があります")

    def test_cycle_is_reported_with_path(self):
        g = {"x": ["a"], "a": ["b"], "b": ["c"], "c": ["a"], "y": []}
        with self.assertRaises(DependencyCycleError) as cm:
            topological_sort(g)
        self.assert_cycle_path(g, cm.exception.cycle)
        self.assertEqual(set(cm.exception.cycle), {"a", "b", "c"})
        self.assertIn("->", str(cm.exception))

    def test_self_loop(self):
        g = {"a": ["a"]}
        with self.assertRaises(DependencyCycleError) as cm:
            topological_sort(g)
        self.assertEqual(cm.exception.cycle, ["a", "a"])

    def test_cycle_downstream_of_dag_part(self):
        g = {"s": ["a", "t"], "a": ["b"], "b": ["c"], "c": ["b", "d"], "t": []}
        with self.assertRaises(DependencyCycleError) as cm:
            topological_sort(g)
        self.assert_cycle_path(g, cm.exception.cycle)
        self.assertEqual(set(cm.exception.cycle), {"b", "c"})

    def test_random_graphs_with_cycles(self):
        rng = random.Random(42)
        for _ in range(50):
            g = random_digraph(rng, 15, 0.12)
            has_cycle = any(u in reachable(g, v) for u, vs in g.items() for v in vs)
            if has_cycle:
                with self.assertRaises(DependencyCycleError) as cm:
                    topological_sort(g)
                self.assert_cycle_path(g, cm.exception.cycle)
            else:
                self.assert_topological(g, topological_sort(g))


# ----------------------------------------------------------------------------
# 演習4c: ダイクストラ法
# ----------------------------------------------------------------------------

@with_timeout(5)
class TestExercise4Dijkstra(unittest.TestCase):
    GRAPH = {
        "東京": [("品川", 7), ("新宿", 9), ("池袋", 14)],
        "品川": [("新宿", 10), ("渋谷", 15)],
        "新宿": [("渋谷", 11), ("池袋", 2)],
        "池袋": [("上野", 9)],
        "渋谷": [("上野", 6)],
        "上野": [],
    }

    def test_distances_and_prev(self):
        dist, prev = dijkstra(self.GRAPH, "東京")
        self.assertEqual(dist, {"東京": 0, "品川": 7, "新宿": 9, "池袋": 11, "渋谷": 20, "上野": 20})
        self.assertEqual(prev["池袋"], "新宿", "直通（14）より新宿経由（9 + 2 = 11）の方が短い")
        self.assertNotIn("東京", prev)

    def test_shortest_path(self):
        self.assertEqual(shortest_path(self.GRAPH, "東京", "上野"), (20, ["東京", "新宿", "池袋", "上野"]))
        self.assertEqual(shortest_path(self.GRAPH, "東京", "東京"), (0, ["東京"]))
        self.assertIsNone(shortest_path(self.GRAPH, "上野", "東京"))

    def test_negative_weight_is_rejected(self):
        g = {"a": [("b", 1)], "b": [("c", -2)], "c": []}
        with self.assertRaises(ValueError):
            dijkstra(g, "a")

    def test_uncomparable_nodes_with_ties(self):
        a, b, c, d = (Opaque(x) for x in "abcd")
        g = {a: [(b, 1), (c, 1)], b: [(d, 1)], c: [(d, 1)], d: []}
        dist, _ = dijkstra(g, a)  # 距離が同じエントリがヒープに入っても頂点どうしを比較しないこと
        self.assertEqual(dist[d], 2)

    def test_random_graphs_against_bellman_ford(self):
        rng = random.Random(43)
        for _ in range(40):
            n = rng.randrange(2, 25)
            g = {i: [(j, rng.randrange(0, 20)) for j in range(n) if j != i and rng.random() < 0.2] for i in range(n)}
            src = rng.randrange(n)
            dist, _ = dijkstra(g, src)
            self.assertEqual(dist, bellman_ford(g, src))
            for t in dist:
                d, path = shortest_path(g, src, t)
                self.assertEqual(path[0], src)
                self.assertEqual(path[-1], t)
                weight = 0
                for u, v in zip(path, path[1:]):
                    weight += min(w for x, w in g[u] if x == v)
                self.assertEqual(weight, d, f"経路 {path} の重みの和が距離と一致しません")


# ----------------------------------------------------------------------------
# 演習4d: Union-Find とクラスカル法
# ----------------------------------------------------------------------------

@with_timeout(5)
class TestExercise4UnionFind(unittest.TestCase):
    def test_basic(self):
        uf = UnionFind("abcde")
        self.assertEqual((len(uf), uf.components), (5, 5))
        self.assertTrue(uf.union("a", "b"))
        self.assertTrue(uf.union("c", "d"))
        self.assertFalse(uf.union("b", "a"), "すでに同じ集合なら False")
        self.assertTrue(uf.connected("a", "b"))
        self.assertFalse(uf.connected("a", "c"))
        self.assertEqual(uf.components, 3)
        uf.union("b", "d")
        self.assertTrue(uf.connected("a", "c"))
        self.assertEqual(uf.component_size("c"), 4)
        self.assertEqual(uf.find("a"), uf.find("d"))

    def test_add_and_unknown(self):
        uf = UnionFind()
        uf.add(1)
        uf.add(1)
        self.assertEqual(len(uf), 1)
        self.assertIn(1, uf)
        with self.assertRaises(KeyError):
            uf.find(2)
        with self.assertRaises(KeyError):
            uf.union(1, 2)

    def test_random_against_naive_labels(self):
        rng = random.Random(44)
        n = 60
        uf = UnionFind(range(n))
        label = list(range(n))
        for _ in range(200):
            a, b = rng.randrange(n), rng.randrange(n)
            merged = uf.union(a, b)
            la, lb = label[a], label[b]
            self.assertEqual(merged, la != lb)
            label = [la if x == lb else x for x in label]
            x, y = rng.randrange(n), rng.randrange(n)
            self.assertEqual(uf.connected(x, y), label[x] == label[y])
        self.assertEqual(uf.components, len(set(label)))

    def test_long_chains_are_fast(self):
        # 経路圧縮も併合の工夫もないと、どちらかの向きの union で長い鎖ができて
        # find が O(n) になり、全体で O(n^2) になる（5 秒で打ち切る）
        n = 20_000
        for forward in (True, False):
            uf = UnionFind(range(n))
            for i in range(n - 1):
                if forward:
                    uf.union(i, i + 1)
                else:
                    uf.union(i + 1, i)
            for _ in range(3):
                for i in range(n):
                    uf.find(i)
            self.assertEqual(uf.components, 1)


def prim_total(nodes, edges):
    adj = {u: [] for u in nodes}
    for u, v, w in edges:
        adj[u].append((w, v))
        adj[v].append((w, u))
    total, seen = 0, set()
    for s in nodes:
        if s in seen:
            continue
        seen.add(s)
        frontier = list(adj[s])
        while frontier:
            frontier.sort(key=lambda t: t[0])
            w, v = frontier.pop(0)
            if v in seen:
                continue
            seen.add(v)
            total += w
            frontier.extend(adj[v])
    return total


class TestExercise4Kruskal(unittest.TestCase):
    def assert_forest(self, nodes, edges, chosen):
        edge_set = {(u, v, w) for u, v, w in edges} | {(v, u, w) for u, v, w in edges}
        uf_parent = {n: n for n in nodes}

        def root(x):
            while uf_parent[x] != x:
                x = uf_parent[x]
            return x

        for u, v, w in chosen:
            self.assertIn((u, v, w), edge_set, "入力にない辺を選んでいます")
            ru, rv = root(u), root(v)
            self.assertNotEqual(ru, rv, "選んだ辺が閉路を作っています")
            uf_parent[ru] = rv

    def test_example(self):
        nodes = "ABCDE"
        edges = [("A", "B", 4), ("A", "C", 1), ("B", "C", 2), ("B", "D", 5), ("C", "D", 8), ("D", "E", 3), ("C", "E", 9)]
        total, chosen = kruskal_mst(nodes, edges)
        self.assertEqual(total, 11)
        self.assertEqual(sorted(w for _, _, w in chosen), [1, 2, 3, 5])
        self.assert_forest(nodes, edges, chosen)

    def test_disconnected_graph_gives_forest(self):
        nodes = [1, 2, 3, 4, 5]
        edges = [(1, 2, 1.5), (3, 4, 2.5)]
        total, chosen = kruskal_mst(nodes, edges)
        self.assertEqual(total, 4.0)
        self.assertEqual(len(chosen), 2, "頂点 5 個・連結成分 3 個なら辺は 5 - 3 = 2 本")

    def test_empty_and_invalid(self):
        self.assertEqual(kruskal_mst([], []), (0, []))
        with self.assertRaises(ValueError):
            kruskal_mst(["a"], [("a", "b", 1)])

    def test_random_graphs_against_prim(self):
        rng = random.Random(45)
        for _ in range(40):
            n = rng.randrange(1, 30)
            nodes = list(range(n))
            edges = [(u, v, rng.randrange(-5, 50)) for u in range(n) for v in range(u + 1, n) if rng.random() < 0.3]
            total, chosen = kruskal_mst(nodes, edges)
            self.assertEqual(total, prim_total(nodes, edges))
            self.assert_forest(nodes, edges, chosen)
            self.assertEqual(sum(w for _, _, w in chosen), total)


# ----------------------------------------------------------------------------
# 演習5: マイクロサービスの依存グラフ
# ----------------------------------------------------------------------------

SERVICES = {
    "web-frontend": ["auth", "catalog", "cart"],
    "mobile-bff": ["auth", "catalog"],
    "cart": ["catalog", "pricing", "session-store"],
    "catalog": ["search", "product-db"],
    "search": ["catalog"],  # 循環（catalog <-> search）
    "auth": ["users", "session-store"],
    "users": ["auth", "user-db"],  # 循環（auth <-> users）
    "pricing": ["product-db"],
}


@with_timeout(5)
class TestExercise5DependencyGraph(unittest.TestCase):
    def test_dependency_cycles_example(self):
        self.assertEqual(dependency_cycles(SERVICES), [["auth", "users"], ["catalog", "search"]])

    def test_no_cycles_and_self_loop(self):
        self.assertEqual(dependency_cycles({"a": ["b"], "b": ["c"]}), [])
        self.assertEqual(dependency_cycles({"a": ["a", "b"], "b": []}), [["a"]])
        self.assertEqual(dependency_cycles({}), [])

    def test_cycles_match_mutual_reachability(self):
        rng = random.Random(46)
        for _ in range(40):
            g = {f"s{i}": [f"s{j}" for j in range(12) if rng.random() < 0.1] for i in range(12)}
            reach = {u: reachable(g, u) for u in g}
            expected = set()
            for u in g:
                comp = frozenset(v for v in g if v in reach[u] and u in reach[v])
                if len(comp) > 1 or u in g[u]:
                    expected.add(tuple(sorted(comp)))
            self.assertEqual(dependency_cycles(g), sorted(list(c) for c in expected))

    def test_large_cycle_does_not_hit_recursion_limit(self):
        n = 5000  # Python の再帰の上限（既定 1000）を超える深さ
        g = {f"svc{i:04d}": [f"svc{(i + 1) % n:04d}"] for i in range(n)}
        cycles = dependency_cycles(g)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(len(cycles[0]), n)

    def test_blast_radius_example(self):
        self.assertEqual(
            blast_radius(SERVICES, "product-db"),
            {"catalog", "search", "pricing", "cart", "web-frontend", "mobile-bff"},
        )
        self.assertEqual(blast_radius(SERVICES, "user-db"), {"users", "auth", "web-frontend", "mobile-bff"})
        self.assertEqual(blast_radius(SERVICES, "web-frontend"), set(), "誰からも依存されていない")

    def test_blast_radius_excludes_itself_even_in_cycle(self):
        self.assertEqual(blast_radius(SERVICES, "auth"), {"users", "web-frontend", "mobile-bff"})

    def test_blast_radius_unknown_service(self):
        with self.assertRaises(KeyError):
            blast_radius(SERVICES, "billing")

    def test_blast_radius_matches_reachability(self):
        rng = random.Random(47)
        for _ in range(30):
            g = {f"s{i}": [f"s{j}" for j in range(15) if j != i and rng.random() < 0.12] for i in range(15)}
            for s in g:
                expected = {u for u in g if u != s and s in reachable(g, u)}
                self.assertEqual(blast_radius(g, s), expected, s)

    def test_rank_by_blast_radius(self):
        ranking = rank_by_blast_radius(SERVICES)
        self.assertEqual(ranking[0], ("product-db", 6))
        self.assertEqual(ranking[1], ("session-store", 5), "共有のセッションストアは影響範囲が広い")
        self.assertEqual(ranking[2:5], [("catalog", 4), ("search", 4), ("user-db", 4)])
        self.assertEqual(len(ranking), len(all_nodes(SERVICES)))
        sizes = [s for _, s in ranking]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        zero = [name for name, size in ranking if size == 0]
        self.assertEqual(zero, sorted(zero), "同じ大きさなら名前の昇順")


if __name__ == "__main__":
    unittest.main()
