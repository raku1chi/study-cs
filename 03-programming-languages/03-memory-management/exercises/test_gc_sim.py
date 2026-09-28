"""3.3 メモリ管理とランタイム — 演習1・3・4（GC のシミュレーション）のテスト

実行: python3 tools/check.py 3.3   （またはこのディレクトリで python3 -m unittest -v test_gc_sim）
"""
import random
import unittest

from gc_sim import (
    HeapError,
    ObjectGraph,
    Ref,
    RefCountHeap,
    SemiSpaceHeap,
    collect,
    mark,
    sweep,
)

LONG = 100_000  # 再帰で書くと RecursionError になる長さ


def reachable_reference(graph):
    """テスト用の参照実装（到達可能なオブジェクトの集合）。"""
    seen, stack = set(), list(graph.roots)
    while stack:
        oid = stack.pop()
        if oid not in seen:
            seen.add(oid)
            stack.extend(graph.objects[oid])
    return seen


class TestExercise1MarkSweep(unittest.TestCase):
    def test_unreachable_objects_are_freed(self):
        g = ObjectGraph()
        a = g.new(root=True)
        b = g.new()
        g.link(a, b)
        c = g.new()  # どこからも参照されない
        self.assertEqual(mark(g), {a, b})
        self.assertEqual(collect(g), {c})
        self.assertEqual(set(g.objects), {a, b})

    def test_cycles_are_collected(self):
        # 参照カウントでは回収できない循環も、ルートから届かなければ回収できる
        g = ObjectGraph()
        g.new(root=True)
        b = g.new()
        c = g.new(b)
        g.link(b, c)
        self_loop = g.new()
        g.link(self_loop, self_loop)
        self.assertEqual(collect(g), {b, c, self_loop})

    def test_reachable_cycles_are_kept(self):
        g = ObjectGraph()
        a = g.new(root=True)
        b = g.new()
        c = g.new(b)
        g.link(b, c)
        g.link(a, b)
        self.assertEqual(collect(g), set())
        self.assertEqual(set(g.objects), {a, b, c})

    def test_shared_objects_and_multiple_roots(self):
        g = ObjectGraph()
        shared = g.new()
        r1 = g.new(shared, root=True)
        r2 = g.new(shared, shared, root=True)  # 同じ参照が 2 つあってもよい
        self.assertEqual(mark(g), {shared, r1, r2})
        g.roots.discard(r1)
        self.assertEqual(collect(g), {r1})
        g.roots.discard(r2)
        self.assertEqual(collect(g), {r2, shared})
        self.assertEqual(g.objects, {})

    def test_mark_does_not_modify_graph(self):
        g = ObjectGraph()
        a = g.new(root=True)
        g.new(a)
        before = {k: list(v) for k, v in g.objects.items()}
        mark(g)
        self.assertEqual(g.objects, before)

    def test_sweep_uses_given_marks(self):
        g = ObjectGraph()
        a, b, c = g.new(), g.new(), g.new()
        self.assertEqual(sweep(g, {b}), {a, c})
        self.assertEqual(set(g.objects), {b})

    def test_empty_heap(self):
        g = ObjectGraph()
        self.assertEqual(mark(g), set())
        self.assertEqual(collect(g), set())

    def test_long_chain_without_recursion(self):
        g = ObjectGraph()
        head = g.new(root=True)
        prev = head
        for _ in range(LONG):
            prev_new = g.new()
            g.link(prev, prev_new)
            prev = prev_new
        self.assertEqual(len(mark(g)), LONG + 1)
        g.objects[head].clear()  # 先頭で鎖を切ると、残り全部がゴミになる
        self.assertEqual(len(collect(g)), LONG)

    def test_dangling_reference_is_detected(self):
        g = ObjectGraph()
        a = g.new(root=True)
        g.objects[a].append(999)  # 存在しないオブジェクトへの参照（壊れたヒープ）
        with self.assertRaises(ValueError):
            mark(g)
        g2 = ObjectGraph()
        g2.roots.add(42)
        with self.assertRaises(ValueError):
            mark(g2)

    def test_random_graphs_match_reference(self):
        rng = random.Random(33)
        for _ in range(50):
            g = ObjectGraph()
            ids = [g.new() for _ in range(rng.randrange(1, 40))]
            for _ in range(rng.randrange(0, 80)):
                g.link(rng.choice(ids), rng.choice(ids))
            g.roots.update(rng.sample(ids, rng.randrange(0, min(4, len(ids)) + 1)))
            expected_live = reachable_reference(g)
            freed = collect(g)
            self.assertEqual(set(g.objects), expected_live)
            self.assertEqual(freed, set(ids) - expected_live)


class TestExercise3RefCount(unittest.TestCase):
    def test_new_and_decref(self):
        h = RefCountHeap()
        a = h.new()
        self.assertEqual(a, 1)
        self.assertEqual(h.refcount[a], 1)
        h.incref(a)
        self.assertEqual(h.decref(a), [])
        self.assertTrue(h.is_alive(a))
        self.assertEqual(h.decref(a), [a])
        self.assertFalse(h.is_alive(a))
        self.assertEqual(h.freed_log, [a])

    def test_cascading_free(self):
        h = RefCountHeap()
        a, b, c = h.new(), h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, c)
        h.decref(b)
        h.decref(c)
        self.assertEqual(h.refcount, {a: 1, b: 1, c: 1})
        self.assertEqual(sorted(h.decref(a)), [a, b, c])
        self.assertEqual(h.refcount, {})
        self.assertEqual(h.refs, {})

    def test_shared_child_survives(self):
        h = RefCountHeap()
        a, b, c = h.new(), h.new(), h.new()
        h.add_ref(a, c)
        h.add_ref(b, c)
        h.decref(c)
        self.assertEqual(h.refcount[c], 2)
        self.assertEqual(h.decref(a), [a])
        self.assertTrue(h.is_alive(c))
        self.assertEqual(h.refcount[c], 1)
        self.assertEqual(sorted(h.decref(b)), [b, c])

    def test_duplicate_references(self):
        h = RefCountHeap()
        a, b = h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(a, b)
        h.decref(b)
        self.assertEqual(h.refcount[b], 2)
        self.assertEqual(h.remove_ref(a, b), [])
        self.assertEqual(h.remove_ref(a, b), [b])
        with self.assertRaises(HeapError):
            h.remove_ref(a, a)  # a は a を参照していない

    def test_use_after_free_is_detected(self):
        h = RefCountHeap()
        a, b = h.new(), h.new()
        h.decref(a)
        for op in (lambda: h.decref(a), lambda: h.incref(a), lambda: h.add_ref(b, a),
                   lambda: h.add_ref(a, b), lambda: h.remove_ref(b, a), lambda: h.decref(999)):
            with self.assertRaises(HeapError):
                op()

    def test_cycle_leaks_without_cycle_collector(self):
        h = RefCountHeap()
        a, b = h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, a)
        self.assertEqual(h.decref(a), [])
        self.assertEqual(h.decref(b), [])
        # 誰も外から参照していないのに、互いの参照でカウントが 1 のまま残る
        self.assertEqual(h.refcount, {a: 1, b: 1})

    def test_collect_cycles(self):
        h = RefCountHeap()
        a, b = h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, a)
        h.decref(a)
        h.decref(b)
        self.assertEqual(h.collect_cycles(), {a, b})
        self.assertEqual(h.refcount, {})
        self.assertEqual(h.refs, {})
        self.assertEqual(sorted(h.freed_log), [a, b])

    def test_self_cycle(self):
        h = RefCountHeap()
        a = h.new()
        h.add_ref(a, a)
        h.decref(a)
        self.assertTrue(h.is_alive(a))
        self.assertEqual(h.collect_cycles(), {a})

    def test_externally_referenced_cycle_is_kept(self):
        h = RefCountHeap()
        a, b = h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, a)
        h.decref(b)  # a はまだ外部参照を持っている
        self.assertEqual(h.collect_cycles(), set())
        self.assertEqual(h.refcount, {a: 2, b: 1})

    def test_cycle_reachable_from_live_object_is_kept(self):
        h = RefCountHeap()
        x, a, b = h.new(), h.new(), h.new()
        h.add_ref(x, a)
        h.add_ref(a, b)
        h.add_ref(b, a)
        h.decref(a)
        h.decref(b)
        self.assertEqual(h.collect_cycles(), set())
        self.assertEqual(sorted(h.decref(x)), [x])  # x の解放後も a と b は循環で残る
        self.assertEqual(h.collect_cycles(), {a, b})

    def test_garbage_hanging_off_a_cycle(self):
        h = RefCountHeap()
        a, b, d = h.new(), h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, a)
        h.add_ref(a, d)  # d は循環からだけ参照される
        for o in (a, b, d):
            h.decref(o)
        self.assertEqual(h.collect_cycles(), {a, b, d})

    def test_garbage_pointing_to_live_object(self):
        h = RefCountHeap()
        a, b, c = h.new(), h.new(), h.new()
        h.add_ref(a, b)
        h.add_ref(b, a)
        h.add_ref(a, c)  # 循環（ゴミ）が、外から参照されている c を参照している
        h.decref(a)
        h.decref(b)
        self.assertEqual(h.refcount[c], 2)
        self.assertEqual(h.collect_cycles(), {a, b})
        self.assertEqual(h.refcount, {c: 1}, "ゴミからの参照の分だけ c のカウントが減る")
        self.assertEqual(h.decref(c), [c])

    def test_long_chain_cascade_without_recursion(self):
        h = RefCountHeap()
        head = h.new()
        prev = head
        for _ in range(LONG):
            nxt = h.new()
            h.add_ref(prev, nxt)
            h.decref(nxt)
            prev = nxt
        self.assertEqual(len(h.decref(head)), LONG + 1)
        self.assertEqual(h.refcount, {})

    def test_random_operations_agree_with_tracing(self):
        """参照カウント＋循環回収の結果が、「外部参照から到達可能か」という定義と一致すること。"""
        rng = random.Random(34)
        for _ in range(30):
            h = RefCountHeap()
            external = {}  # オブジェクト → 外部参照の数（テスト側で管理）
            for _ in range(60):
                op = rng.random()
                live = [o for o in h.refcount]
                if op < 0.3 or not live:
                    o = h.new()
                    external[o] = 1
                elif op < 0.6:
                    h.add_ref(rng.choice(live), rng.choice(live))
                elif op < 0.8:
                    holders = [o for o in live if external.get(o, 0) > 0]
                    if holders:
                        o = rng.choice(holders)
                        external[o] -= 1
                        h.decref(o)
                else:
                    src = rng.choice(live)
                    if h.refs[src]:
                        h.remove_ref(src, rng.choice(h.refs[src]))
            h.collect_cycles()
            # 定義: 外部参照を持つオブジェクトから到達できるものだけが生き残る
            roots = [o for o, n in external.items() if n > 0 and h.is_alive(o)]
            seen, stack = set(), list(roots)
            while stack:
                o = stack.pop()
                if o not in seen:
                    seen.add(o)
                    stack.extend(h.refs[o])
            self.assertEqual(set(h.refcount), seen)
            for o in seen:
                internal = sum(children.count(o) for children in h.refs.values())
                self.assertEqual(h.refcount[o], internal + external.get(o, 0), f"オブジェクト {o} の参照カウント")


class TestExercise4Cheney(unittest.TestCase):
    def test_bump_allocation(self):
        h = SemiSpaceHeap(8)
        self.assertEqual(h.alloc([1, 2]), Ref(0))
        self.assertEqual(h.alloc([]), Ref(3))
        self.assertEqual(h.alloc([None]), Ref(4))
        self.assertEqual(h.free, 6)
        self.assertEqual(h.fields(Ref(0)), [1, 2])

    def test_alloc_validates_fields(self):
        h = SemiSpaceHeap(8)
        with self.assertRaises(TypeError):
            h.alloc(["text"])
        with self.assertRaises(TypeError):
            h.alloc([1.5])

    def test_collect_without_roots_frees_everything(self):
        h = SemiSpaceHeap(16)
        h.alloc([1, 2, 3])
        h.alloc([4])
        self.assertEqual(h.collect(), 0)
        self.assertEqual(h.free, 0)
        self.assertEqual(h.collections, 1)

    def test_breadth_first_copy_order(self):
        h = SemiSpaceHeap(32)
        garbage = h.alloc([7, 7, 7])
        d = h.alloc([4])
        c = h.alloc([3])
        b = h.alloc([d, 2])
        a = h.alloc([b, c, 1])
        h.roots.append(a)
        self.assertEqual(garbage, Ref(0))
        self.assertEqual(h.collect(), 4 + 3 + 2 + 2)  # a, b, c, d のワード数の合計
        # ルート a → a のフィールド順に b, c → b のフィールドの d、の幅優先の順に並ぶ
        self.assertEqual(h.roots, [Ref(0)])
        self.assertEqual(h.fields(Ref(0)), [Ref(4), Ref(7), 1])
        self.assertEqual(h.fields(Ref(4)), [Ref(9), 2])
        self.assertEqual(h.fields(Ref(7)), [3])
        self.assertEqual(h.fields(Ref(9)), [4])
        self.assertEqual(h.free, 11)

    def test_sharing_is_preserved(self):
        h = SemiSpaceHeap(32)
        shared = h.alloc([42])
        pair = h.alloc([shared, shared])
        h.roots.append(pair)
        h.roots.append(shared)
        live = h.collect()
        self.assertEqual(live, 3 + 2, "共有されたオブジェクトは 1 回だけコピーされる")
        p = h.roots[0]
        first, second = h.fields(p)
        self.assertEqual(first, second)
        self.assertEqual(h.roots[1], first)
        self.assertEqual(h.fields(first), [42])

    def test_cycles_are_preserved(self):
        h = SemiSpaceHeap(32)
        a = h.alloc([None, 1])
        b = h.alloc([a, 2])
        h.write(a, 0, b)  # a ⇄ b
        h.alloc([9, 9, 9])  # ゴミ
        h.roots.append(b)
        self.assertEqual(h.collect(), 6)
        nb = h.roots[0]
        na = h.read(nb, 0)
        self.assertEqual(h.read(na, 0), nb)
        self.assertEqual((h.read(na, 1), h.read(nb, 1)), (1, 2))

    def test_integers_are_not_treated_as_pointers(self):
        h = SemiSpaceHeap(16)
        h.alloc([1, 1, 1])  # ゴミ
        obj = h.alloc([0, 1, 2])  # 0, 1, 2 はアドレスに見えるがただの数値
        h.roots.append(obj)
        h.collect()
        self.assertEqual(h.fields(h.roots[0]), [0, 1, 2])
        self.assertEqual(h.free, 4)

    def test_none_roots_and_fields(self):
        h = SemiSpaceHeap(16)
        x = h.alloc([None, 3])
        h.roots.extend([None, x, None])
        h.collect()
        self.assertEqual(h.roots, [None, Ref(0), None])
        self.assertEqual(h.fields(Ref(0)), [None, 3])

    def test_alloc_triggers_gc_when_full(self):
        h = SemiSpaceHeap(10)
        keep = h.alloc([1])
        h.roots.append(keep)
        for _ in range(4):
            h.alloc([0])  # ゴミを作り続ける
        self.assertEqual(h.free, 10)
        self.assertEqual(h.collections, 0)
        new = h.alloc([2, 3])  # 空きがないので GC が走る
        self.assertEqual(h.collections, 1)
        self.assertEqual(h.fields(h.roots[0]), [1])
        self.assertEqual(h.fields(new), [2, 3])
        self.assertEqual(new, Ref(2))

    def test_alloc_updates_references_in_fields_during_gc(self):
        h = SemiSpaceHeap(10)
        h.alloc([0, 0, 0])  # ゴミ（GC で消えるので、target は前に詰められて移動する）
        target = h.alloc([99])
        h.roots.append(target)
        h.alloc([0, 0, 0])  # ゴミ。これでヒープは満杯
        # GC を起こす alloc に、移動するオブジェクトへの参照を渡す
        node = h.alloc([h.roots[0], 5])
        self.assertEqual(h.collections, 1)
        moved = h.roots[0]
        self.assertEqual(moved, Ref(0))
        self.assertEqual(h.fields(node), [moved, 5], "fields の参照も移動後のアドレスに更新する")
        self.assertEqual(len(h.roots), 1, "一時的に追加したルートは元に戻す")

    def test_out_of_memory(self):
        h = SemiSpaceHeap(8)
        big = h.alloc([1, 2, 3, 4, 5])
        h.roots.append(big)
        with self.assertRaises(MemoryError):
            h.alloc([1, 2, 3])  # 生きている 6 ワード + 4 ワード > 8
        self.assertEqual(h.fields(h.roots[0]), [1, 2, 3, 4, 5])
        with self.assertRaises(MemoryError):
            SemiSpaceHeap(4).alloc([1, 2, 3, 4])

    def test_linked_list_survives_many_collections(self):
        h = SemiSpaceHeap(64)
        h.roots.append(None)
        for i in range(200):
            # 先頭に要素を追加しつつ、長さ 5 を超えた分は切り捨てる（ゴミが大量に出る）
            h.roots[0] = h.alloc([i, h.roots[0]])
            node, length = h.roots[0], 1
            while h.read(node, 1) is not None and length < 5:
                node, length = h.read(node, 1), length + 1
            h.write(node, 1, None)
        values, node = [], h.roots[0]
        while node is not None:
            values.append(h.read(node, 0))
            node = h.read(node, 1)
        self.assertEqual(values, [199, 198, 197, 196, 195])
        self.assertGreater(h.collections, 5)


if __name__ == "__main__":
    unittest.main()
