"""7.2 レプリケーションと一貫性 — CRDT のテスト

実行: python3 tools/check.py 7.2   （またはこのディレクトリで python3 -m unittest -v test_crdt）

シード付きの乱数で操作とマージの順序をばらばらにし、CRDT の性質（可換・結合・冪等、収束）を確かめます。
"""
import copy
import itertools
import random
import unittest

from crdt import GCounter, LWWRegister, ORSet, PNCounter

REPLICAS = ("A", "B", "C")


def check_semilattice_laws(test: unittest.TestCase, snapshots: list, rng: random.Random, trials: int = 150) -> None:
    for _ in range(trials):
        a, b, c = (rng.choice(snapshots) for _ in range(3))
        before = [copy.deepcopy(x) for x in (a, b, c)]
        test.assertEqual(a.merge(b), b.merge(a), "可換: a ⊔ b = b ⊔ a")
        test.assertEqual(a.merge(b).merge(c), a.merge(b.merge(c)), "結合: (a ⊔ b) ⊔ c = a ⊔ (b ⊔ c)")
        test.assertEqual(a.merge(a), a, "冪等: a ⊔ a = a")
        test.assertEqual([a, b, c], before, "merge は引数も自分自身も書き換えない")


def full_exchange(replicas: dict) -> dict:
    """全員の状態を 1 つにマージし、それを各レプリカに配る（ゴシップが行き渡った状態）。"""
    merged = None
    for r in replicas.values():
        merged = r if merged is None else merged.merge(r)
    return {rid: r.merge(merged) for rid, r in replicas.items()}


class TestExercise4Counters(unittest.TestCase):
    def test_gcounter_basics(self):
        a, b = GCounter("A"), GCounter("B")
        a.increment()
        a.increment(4)
        b.increment(2)
        self.assertEqual((a.value, b.value), (5, 2))
        m = a.merge(b)
        self.assertEqual(m.value, 7)
        self.assertEqual(m.replica_id, "A", "merge の結果は self のレプリカ ID を引き継ぐ")
        self.assertEqual(m.state(), {"A": 5, "B": 2})
        self.assertEqual(m.merge(b).merge(b).value, 7, "何度マージしても二重に数えない")

    def test_gcounter_merge_is_max_not_sum(self):
        a = GCounter("A", {"A": 3, "B": 1})
        b = GCounter("B", {"A": 2, "B": 4})
        self.assertEqual(a.merge(b).state(), {"A": 3, "B": 4})
        self.assertEqual(GCounter("A", {"A": 0}), GCounter("A"), "0 の要素は持たない形で比べる")

    def test_gcounter_validation(self):
        with self.assertRaises(ValueError):
            GCounter("A").increment(-1)
        with self.assertRaises(ValueError):
            GCounter("A", {"A": -2})

    def test_pncounter_basics(self):
        a, b = PNCounter("A"), PNCounter("B")
        a.increment(10)
        a.decrement(3)
        b.decrement(9)
        self.assertEqual(a.value, 7)
        self.assertEqual(a.merge(b).value, -2)
        with self.assertRaises(ValueError):
            a.increment(-1)
        with self.assertRaises(ValueError):
            a.decrement(-1)

    def run_counter(self, factory, seed: int, allow_decrement: bool):
        rng = random.Random(seed)
        replicas = {rid: factory(rid) for rid in REPLICAS}
        snapshots, expected = [], 0
        for _ in range(300):
            rid = rng.choice(REPLICAS)
            op = rng.random()
            if op < 0.45:
                n = rng.randrange(0, 5)
                replicas[rid].increment(n)
                expected += n
            elif op < 0.7 and allow_decrement:
                n = rng.randrange(0, 5)
                replicas[rid].decrement(n)
                expected -= n
            else:
                other = rng.choice(REPLICAS)
                replicas[rid] = replicas[rid].merge(replicas[other])
            snapshots.append(copy.deepcopy(replicas[rid]))
        return replicas, snapshots, expected

    def test_counters_obey_laws_and_converge(self):
        for factory, allow_dec in ((GCounter, False), (PNCounter, True)):
            for seed in range(3):
                replicas, snapshots, expected = self.run_counter(factory, seed, allow_dec)
                check_semilattice_laws(self, snapshots, random.Random(seed))
                final = full_exchange(replicas)
                values = {r.value for r in final.values()}
                self.assertEqual(values, {expected}, f"{factory.__name__} seed={seed}: 全レプリカが正しい値に収束")
                for x, y in itertools.combinations(final.values(), 2):
                    self.assertEqual(x, y)


class TestExercise5Register(unittest.TestCase):
    def test_set_and_merge(self):
        a, b = LWWRegister("A"), LWWRegister("B")
        self.assertIsNone(a.value)
        self.assertIsNone(a.stamp)
        self.assertTrue(a.set("x", 10))
        self.assertTrue(b.set("y", 20))
        self.assertEqual(a.merge(b).value, "y")
        self.assertEqual(b.merge(a).value, "y")
        self.assertEqual(a.merge(b).stamp, (20, "B"))
        self.assertEqual(a.value, "x", "merge は自分を書き換えない")

    def test_older_local_write_is_ignored(self):
        a = LWWRegister("A")
        a.set("new", 100)
        self.assertFalse(a.set("older", 50))
        self.assertEqual(a.value, "new")

    def test_ties_are_broken_by_replica_id(self):
        a, b = LWWRegister("A"), LWWRegister("B")
        a.set("from A", 42)
        b.set("from B", 42)
        self.assertEqual(a.merge(b).value, "from B")
        self.assertEqual(b.merge(a).value, "from B", "どちらでマージしても同じ勝者（(時刻, ID) の全順序）")

    def test_clock_skew_silently_loses_the_later_write(self):
        # A の時計は 10 秒進んでおり、B の時計は正確。実時間では B の書き込みの方が後
        a, b = LWWRegister("A"), LWWRegister("B")
        a.set("先に書いた値", timestamp=1_000 + 10)  # 実時刻 1000 に書いたが、時計は 1010
        b.set("後で書いた値", timestamp=1_005)  # 実時刻 1005
        self.assertEqual(a.merge(b).value, "先に書いた値", "LWW は時計のずれで新しい書き込みを失う")

    def test_register_converges_to_max_stamp(self):
        for seed in range(3):
            rng = random.Random(seed)
            replicas = {rid: LWWRegister(rid) for rid in REPLICAS}
            snapshots, best = [], None
            for step in range(200):
                rid = rng.choice(REPLICAS)
                if rng.random() < 0.5:
                    ts = rng.randrange(0, 50)  # 衝突しやすいよう狭い範囲
                    replicas[rid].set(f"{rid}@{step}", ts)
                    if best is None or (ts, rid) > best[0]:
                        best = ((ts, rid), f"{rid}@{step}")
                else:
                    replicas[rid] = replicas[rid].merge(replicas[rng.choice(REPLICAS)])
                snapshots.append(copy.deepcopy(replicas[rid]))
            check_semilattice_laws(self, snapshots, rng)
            final = full_exchange(replicas)
            self.assertEqual({r.value for r in final.values()}, {best[1]})


class ORSetModel:
    """OR-Set の意味の参照モデル: 各追加は一意な ID を持ち、削除はそのレプリカが知っている追加だけを消す。"""

    def __init__(self) -> None:
        self.known: dict[str, set] = {rid: set() for rid in REPLICAS}  # レプリカが知っている (要素, 追加ID)
        self.removed: dict[str, set] = {rid: set() for rid in REPLICAS}
        self.next_id = 0

    def add(self, rid: str, e) -> None:
        self.next_id += 1
        self.known[rid].add((e, self.next_id))

    def remove(self, rid: str, e) -> None:
        self.removed[rid] |= {(x, i) for x, i in self.known[rid] if x == e}

    def merge(self, rid: str, other: str) -> None:
        self.known[rid] |= self.known[other]
        self.removed[rid] |= self.removed[other]

    def final_elements(self) -> set:
        known = set().union(*self.known.values())
        removed = set().union(*self.removed.values())
        return {e for e, i in known - removed}


class TestExercise5ORSet(unittest.TestCase):
    def test_add_remove_readd(self):
        s = ORSet("A")
        s.add("apple")
        s.add("banana")
        self.assertIn("apple", s)
        self.assertEqual(s.elements(), {"apple", "banana"})
        s.remove("apple")
        self.assertNotIn("apple", s)
        s.add("apple")
        self.assertIn("apple", s, "削除後に追加し直せる（2P-Set との違い）")
        s.remove("cherry")  # ない要素の削除は何もしない
        self.assertEqual(s.elements(), {"apple", "banana"})

    def test_concurrent_add_and_remove_add_wins(self):
        a, b = ORSet("A"), ORSet("B")
        a.add("milk")
        b = b.merge(a)  # B も milk を知る
        a.remove("milk")  # A は milk を削除
        b.add("milk")  # 同時に B は milk をもう一度追加（A はこの追加を知らない）
        self.assertIn("milk", a.merge(b))
        self.assertIn("milk", b.merge(a), "並行な追加と削除では追加が勝つ（add-wins）")

    def test_removed_element_is_not_resurrected_by_stale_replica(self):
        a, b = ORSet("A"), ORSet("B")
        a.add("x")
        b = b.merge(a)
        a.remove("x")
        # B は古い状態のまま。マージしても、観測済みの追加は墓標で消されたまま
        self.assertNotIn("x", a.merge(b))
        self.assertNotIn("x", b.merge(a))

    def test_tags_stay_unique_after_merge(self):
        a, b = ORSet("A"), ORSet("B")
        a.add("x")
        b = b.merge(a)
        a = a.merge(b)
        a.add("y")
        b.add("z")
        a.remove("y")
        m = a.merge(b)
        self.assertEqual(m.elements(), {"x", "z"})

    def test_orset_laws_and_convergence_against_model(self):
        items = ["a", "b", "c", "d"]
        for seed in range(4):
            rng = random.Random(seed)
            replicas = {rid: ORSet(rid) for rid in REPLICAS}
            model = ORSetModel()
            snapshots = []
            for _ in range(250):
                rid = rng.choice(REPLICAS)
                op = rng.random()
                e = rng.choice(items)
                if op < 0.4:
                    replicas[rid].add(e)
                    model.add(rid, e)
                elif op < 0.65:
                    replicas[rid].remove(e)
                    model.remove(rid, e)
                else:
                    other = rng.choice(REPLICAS)
                    replicas[rid] = replicas[rid].merge(replicas[other])
                    model.merge(rid, other)
                snapshots.append(copy.deepcopy(replicas[rid]))
            check_semilattice_laws(self, snapshots, rng, trials=100)
            final = full_exchange(replicas)
            for r in final.values():
                self.assertEqual(r.elements(), model.final_elements(), f"seed={seed}")
            for x, y in itertools.combinations(final.values(), 2):
                self.assertEqual(x, y)


if __name__ == "__main__":
    unittest.main()
