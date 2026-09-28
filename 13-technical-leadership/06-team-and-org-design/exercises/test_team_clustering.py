"""13.6 チームと組織の設計 — テスト（変更の結合からチームの境界を提案する）

実行: python3 tools/check.py 13.6   （またはこのディレクトリで python3 -m unittest -v test_team_clustering）
"""
import json
import random
import unittest
from itertools import combinations
from pathlib import Path

from team_clustering import change_coupling, dependency_score, greedy_teams, refine_teams

DATA = Path(__file__).parent / "data" / "commits.json"

# 本文の例: 各コンポーネントに必要な人数の目安と、現在の（技術レイヤー別の）組織
BOOK_LOAD = {
    "order-api": 2, "cart": 1, "payment": 2, "invoice": 1, "inventory": 2, "warehouse": 1.5,
    "shipping": 1.5, "catalog": 1.5, "search": 2, "recommend": 1.5, "member": 1.5, "auth": 1,
    "points": 1, "notify": 1,
}
BOOK_CURRENT = [
    ["cart", "catalog", "recommend", "search"],
    ["inventory", "invoice", "order-api", "payment", "points"],
    ["auth", "member", "notify", "shipping", "warehouse"],
]
BOOK_PROPOSAL = [
    ["auth", "member", "notify", "points"],
    ["cart", "invoice", "order-api", "payment"],
    ["catalog", "recommend", "search"],
    ["inventory", "shipping", "warehouse"],
]

# 貪欲法が最適を逃す小さな例（本文でも使う）
TRAP_COUPLING = {("a", "b"): 10, ("a", "c"): 8, ("a", "d"): 8, ("b", "e"): 8, ("b", "f"): 8,
                 ("c", "d"): 1, ("e", "f"): 1}
TRAP_LOAD = {c: 1 for c in "abcdef"}


def load_fixture():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)
    return data["components"], data["commits"]


def cut_weight(teams, coupling):
    owner = {c: i for i, t in enumerate(teams) for c in t}
    return sum(w for (a, b), w in coupling.items() if owner[a] != owner[b])


class TestExercise2Coupling(unittest.TestCase):
    def test_docstring_example(self):
        got = change_coupling([["b", "a"], ["a", "b", "c"], ["c"]], ["a", "b", "c"])
        self.assertEqual(got, {("a", "b"): 2, ("a", "c"): 1, ("b", "c"): 1})
        self.assertEqual(list(got), sorted(got), "キーの昇順")

    def test_duplicates_in_a_commit_count_once(self):
        got = change_coupling([["a", "b", "a", "b"]], ["a", "b"])
        self.assertEqual(got, {("a", "b"): 1})

    def test_no_pairs(self):
        self.assertEqual(change_coupling([["a"], ["b"], []], ["a", "b"]), {})

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            change_coupling([["a", "x"]], ["a", "b"])
        with self.assertRaises(ValueError):
            change_coupling([["a"]], ["a", "a"])

    def test_fixture(self):
        components, commits = load_fixture()
        got = change_coupling(commits, components)
        self.assertEqual(len(commits), 420)
        self.assertEqual(got[("auth", "points")], 34)
        self.assertEqual(got[("inventory", "shipping")], 34)
        self.assertEqual(got[("catalog", "search")], 25)
        for a, b in got:
            self.assertLess(a, b)

    def test_dependency_score(self):
        coupling = {("a", "b"): 3, ("b", "c"): 1}
        self.assertAlmostEqual(dependency_score([["a", "b"], ["c"]], coupling), 0.25)
        self.assertAlmostEqual(dependency_score([["a", "b", "c"]], coupling), 0.0)
        self.assertAlmostEqual(dependency_score([["a"], ["b"], ["c"]], coupling), 1.0)
        self.assertEqual(dependency_score([["a"], ["b"]], {}), 0.0)

    def test_dependency_score_invalid(self):
        with self.assertRaises(ValueError):
            dependency_score([["a"], ["b"]], {("a", "c"): 1})
        with self.assertRaises(ValueError):
            dependency_score([["a", "b"], ["b"]], {("a", "b"): 1})

    def test_book_current_vs_proposal(self):
        components, commits = load_fixture()
        coupling = change_coupling(commits, components)
        self.assertAlmostEqual(dependency_score(BOOK_CURRENT, coupling), 0.50, places=2)
        self.assertAlmostEqual(dependency_score(BOOK_PROPOSAL, coupling), 0.15, places=2)


class TestExercise3Greedy(unittest.TestCase):
    def test_docstring_example(self):
        coupling = {("a", "b"): 5, ("c", "d"): 4, ("b", "c"): 1}
        got = greedy_teams(["a", "b", "c", "d"], coupling, {c: 1 for c in "abcd"}, max_load=2)
        self.assertEqual(got, [["a", "b"], ["c", "d"]])

    def test_book_example_recovers_structure(self):
        components, commits = load_fixture()
        coupling = change_coupling(commits, components)
        got = greedy_teams(components, coupling, BOOK_LOAD, max_load=7)
        self.assertEqual(got, BOOK_PROPOSAL)
        for team in got:
            self.assertLessEqual(sum(BOOK_LOAD[c] for c in team), 7)

    def test_target_teams_stops_early(self):
        coupling = {("a", "b"): 5, ("c", "d"): 4, ("b", "c"): 1}
        got = greedy_teams(["d", "c", "b", "a"], coupling, {c: 1 for c in "abcd"}, max_load=4, target_teams=3)
        self.assertEqual(got, [["a", "b"], ["c"], ["d"]])

    def test_target_teams_packs_uncoupled_components(self):
        got = greedy_teams(["a", "b", "c", "d"], {}, {c: 1 for c in "abcd"}, max_load=2, target_teams=2)
        self.assertEqual(got, [["a", "b"], ["c", "d"]])

    def test_without_target_uncoupled_components_stay_apart(self):
        got = greedy_teams(["a", "b", "c"], {}, {c: 1 for c in "abc"}, max_load=5)
        self.assertEqual(got, [["a"], ["b"], ["c"]])

    def test_target_may_be_unreachable(self):
        components, commits = load_fixture()
        coupling = change_coupling(commits, components)
        got = greedy_teams(components, coupling, BOOK_LOAD, max_load=7, target_teams=2)
        self.assertEqual(got, BOOK_PROPOSAL, "上限 7 人では 2 チームにはできない")

    def test_greedy_can_miss_the_optimum(self):
        got = greedy_teams(list("abcdef"), TRAP_COUPLING, TRAP_LOAD, max_load=3)
        self.assertEqual(got, [["a", "b", "c"], ["d"], ["e", "f"]])
        self.assertEqual(cut_weight(got, TRAP_COUPLING), 25)

    def test_tie_breaking_by_names(self):
        coupling = {("a", "b"): 1, ("c", "d"): 1}
        got = greedy_teams(["a", "b", "c", "d"], coupling, {c: 1 for c in "abcd"}, max_load=4, target_teams=3)
        self.assertEqual(got, [["a", "b"], ["c"], ["d"]], "同点なら代表の組 (a, b) が (c, d) より先")

    def test_invalid_inputs(self):
        load = {c: 1 for c in "ab"}
        with self.assertRaises(ValueError):
            greedy_teams([], {}, load, 2)
        with self.assertRaises(ValueError):
            greedy_teams(["a", "a"], {}, load, 2)
        with self.assertRaises(ValueError):
            greedy_teams(["a", "z"], {}, load, 2)
        with self.assertRaises(ValueError):
            greedy_teams(["a", "b"], {}, {"a": 3, "b": 1}, 2)
        with self.assertRaises(ValueError):
            greedy_teams(["a", "b"], {}, load, 2, target_teams=0)


class TestExercise4Refine(unittest.TestCase):
    def test_docstring_example(self):
        coupling = {("a", "b"): 1, ("a", "c"): 5}
        got = refine_teams([["a", "b"], ["c"]], coupling, {c: 1 for c in "abc"}, max_load=2)
        self.assertEqual(got, [["a", "c"], ["b"]])

    def test_fixes_the_greedy_trap(self):
        greedy = greedy_teams(list("abcdef"), TRAP_COUPLING, TRAP_LOAD, max_load=3)
        got = refine_teams(greedy, TRAP_COUPLING, TRAP_LOAD, max_load=3)
        self.assertEqual(got, [["a", "c", "d"], ["b", "e", "f"]])
        self.assertEqual(cut_weight(got, TRAP_COUPLING), 10)

    def test_book_example_local_optimum(self):
        # 現在の組織から 1 つずつ動かすだけでは 0.25 で止まる（貪欲法でゼロから作ると 0.15）
        components, commits = load_fixture()
        coupling = change_coupling(commits, components)
        got = refine_teams(BOOK_CURRENT, coupling, BOOK_LOAD, max_load=8)
        self.assertEqual(got, [
            ["auth", "member", "notify", "points", "shipping", "warehouse"],
            ["cart", "invoice", "order-api", "payment"],
            ["catalog", "inventory", "recommend", "search"],
        ])
        self.assertAlmostEqual(dependency_score(got, coupling), 0.25, places=2)

    def test_already_optimal_is_unchanged(self):
        components, commits = load_fixture()
        coupling = change_coupling(commits, components)
        self.assertEqual(refine_teams(BOOK_PROPOSAL, coupling, BOOK_LOAD, max_load=7), BOOK_PROPOSAL)

    def test_input_is_normalized_and_empty_teams_removed(self):
        got = refine_teams([["b", "a"], [], ["c"]], {}, {c: 1 for c in "abc"}, max_load=3)
        self.assertEqual(got, [["a", "b"], ["c"]])

    def test_random_instances_reach_a_local_optimum(self):
        rng = random.Random(606)
        names = [f"c{i}" for i in range(9)]
        for trial in range(40):
            coupling = {}
            for a, b in combinations(names, 2):
                if rng.random() < 0.35:
                    coupling[(a, b)] = rng.randint(1, 9)
            load = {c: rng.choice([1, 1, 2]) for c in names}
            max_load = 5
            # 容量を守る初期の分け方
            teams, current = [], []
            for c in rng.sample(names, len(names)):
                if sum(load[x] for x in current) + load[c] > max_load:
                    teams.append(current)
                    current = []
                current.append(c)
            teams.append(current)
            before = cut_weight(teams, coupling)
            got = refine_teams(teams, coupling, load, max_load)
            self.assertEqual(sorted(c for t in got for c in t), sorted(names), trial)
            self.assertLessEqual(cut_weight(got, coupling), before, trial)
            for t in got:
                self.assertTrue(t, trial)
                self.assertLessEqual(sum(load[c] for c in t), max_load, trial)
            # 局所最適: 容量を守る移動で、利得が正のものは残っていない
            owner = {c: i for i, t in enumerate(got) for c in t}
            for c in names:
                for dst, team in enumerate(got):
                    if dst == owner[c] or sum(load[x] for x in team) + load[c] > max_load:
                        continue
                    moved = [[x for x in t if x != c] + ([c] if i == dst else []) for i, t in enumerate(got)]
                    moved = [t for t in moved if t]
                    self.assertGreaterEqual(cut_weight(moved, coupling), cut_weight(got, coupling), (trial, c))

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            refine_teams([["a", "b"], ["b"]], {}, {c: 1 for c in "ab"}, max_load=3)
        with self.assertRaises(ValueError):
            refine_teams([["a", "b", "c"]], {}, {c: 1 for c in "abc"}, max_load=2)


if __name__ == "__main__":
    unittest.main()
