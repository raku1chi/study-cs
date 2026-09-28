"""10.4 W3C Trace Context とスパンの解析 — テスト

実行: python3 tools/check.py 10.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from tracectx import (
    Span,
    TraceParent,
    build_tree,
    child,
    critical_path,
    format_traceparent,
    new_trace,
    parse_traceparent,
    self_time_by_service,
    self_times,
)

EXAMPLE = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def checkout_spans():
    return [
        Span("a1", None, "POST /checkout", "frontend", 0, 520),
        Span("b1", "a1", "auth.verify", "auth", 5, 35),
        Span("c1", "a1", "cart.get", "cart", 40, 120),
        Span("c2", "c1", "SELECT cart_items", "cart-db", 50, 110),
        Span("d1", "a1", "inventory.reserve", "inventory", 125, 300),
        Span("d2", "d1", "UPDATE stock", "inventory-db", 140, 290),
        Span("e1", "a1", "pricing.quote", "pricing", 125, 220),     # inventory と並行
        Span("f1", "a1", "payment.charge", "payment", 305, 500),
        Span("f2", "f1", "POST psp/charges", "payment", 320, 490),
    ]


class TestExercise5TraceParent(unittest.TestCase):
    def test_parse_spec_example(self):
        tp = parse_traceparent(EXAMPLE)
        self.assertEqual(tp, TraceParent("00", "4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", 1))
        self.assertTrue(tp.sampled)
        self.assertFalse(parse_traceparent(EXAMPLE[:-2] + "00").sampled)
        self.assertEqual(parse_traceparent("  " + EXAMPLE + "\t"), tp, "前後の空白・タブは無視する")

    def test_invalid(self):
        bad = {
            "大文字": EXAMPLE.upper(),
            "trace-id がすべて 0": "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
            "parent-id がすべて 0": "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
            "バージョン ff": "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "trace-id が短い": "00-4bf92f3577b34da6a3ce929d0e0e473-00f067aa0ba902b7-01",
            "16 進数でない": "00-4bf92f3577b34da6a3ce929d0e0e473g-00f067aa0ba902b7-01",
            "区切りが違う": "00_4bf92f3577b34da6a3ce929d0e0e4736_00f067aa0ba902b7_01",
            "flags が 1 桁": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-1",
            "バージョン 00 に余分なフィールド": EXAMPLE + "-extra",
            "バージョンが 16 進数でない": "0x-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "空": "",
            "将来のバージョンでも flags の直後は - か終わり": "cc-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01x",
        }
        for label, header in bad.items():
            with self.assertRaises(ValueError, msg=label):
                parse_traceparent(header)

    def test_future_versions_are_parsed_leniently(self):
        tp = parse_traceparent("cc-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01-what-the-future-holds")
        self.assertEqual((tp.version, tp.trace_id, tp.parent_id, tp.flags),
                         ("cc", "4bf92f3577b34da6a3ce929d0e0e4736", "00f067aa0ba902b7", 1))
        self.assertEqual(parse_traceparent("01-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-09").flags, 9)

    def test_format_round_trip(self):
        self.assertEqual(format_traceparent(parse_traceparent(EXAMPLE)), EXAMPLE)
        self.assertEqual(format_traceparent(TraceParent("00", "a" * 32, "b" * 16, 0)), f"00-{'a' * 32}-{'b' * 16}-00")

    def test_new_trace_is_valid_and_deterministic(self):
        tp1, tp2 = new_trace(random.Random(1)), new_trace(random.Random(1))
        self.assertEqual(tp1, tp2, "同じシードなら同じ ID")
        self.assertEqual(parse_traceparent(format_traceparent(tp1)), tp1)
        self.assertEqual(tp1.version, "00")
        self.assertTrue(tp1.sampled)
        self.assertFalse(new_trace(random.Random(2), sampled=False).sampled)
        rng = random.Random(3)
        ids = {new_trace(rng).trace_id for _ in range(200)}
        self.assertEqual(len(ids), 200)

    def test_zero_ids_are_never_generated(self):
        class ZeroFirst(random.Random):
            def __init__(self):
                super().__init__(0)
                self.calls = 0

            def getrandbits(self, k):
                self.calls += 1
                return 0 if self.calls <= 2 else super().getrandbits(k)

        tp = new_trace(ZeroFirst())
        self.assertNotEqual(tp.trace_id, "0" * 32)
        self.assertNotEqual(tp.parent_id, "0" * 16)
        self.assertEqual(len(tp.trace_id), 32)

    def test_child_propagation(self):
        rng = random.Random(10)
        parent = parse_traceparent(EXAMPLE)
        c = child(parent, rng)
        self.assertEqual(c.trace_id, parent.trace_id, "同じトレース")
        self.assertNotEqual(c.parent_id, parent.parent_id, "新しいスパンの ID")
        self.assertEqual((c.version, c.flags), ("00", 1))
        unknown_bits = TraceParent("cc", parent.trace_id, parent.parent_id, 0xff)
        c2 = child(unknown_bits, rng)
        self.assertEqual((c2.version, c2.flags), ("00", 1), "知らないビットは 0 にし、バージョン 00 で送る")
        self.assertFalse(child(TraceParent("00", parent.trace_id, parent.parent_id, 0), rng).sampled)


class TestExercise6Spans(unittest.TestCase):
    def test_build_tree(self):
        tree = build_tree(checkout_spans())
        self.assertEqual(tree.root.span_id, "a1")
        self.assertEqual([s.span_id for s in tree.children["a1"]], ["b1", "c1", "d1", "e1", "f1"])
        self.assertEqual(tree.children["b1"], [])
        self.assertEqual(len(tree.spans), 9)

    def test_build_tree_errors(self):
        spans = checkout_spans()
        cases = {
            "ルートが 2 つ": spans + [Span("z", None, "x", "s", 0, 1)],
            "ルートがない": [s for s in spans if s.parent_id is not None],
            "親がいない": spans + [Span("z", "nope", "x", "s", 0, 1)],
            "ID の重複": spans + [Span("b1", "a1", "x", "s", 0, 1)],
            "end < start": spans + [Span("z", "a1", "x", "s", 5, 1)],
            "循環": spans + [Span("x", "y", "x", "s", 0, 1), Span("y", "x", "y", "s", 0, 1)],
        }
        for label, case in cases.items():
            with self.assertRaises(ValueError, msg=label):
                build_tree(case)

    def test_self_times(self):
        times = self_times(build_tree(checkout_spans()))
        self.assertEqual(times, {"a1": 40, "b1": 30, "c1": 20, "c2": 60, "d1": 25, "d2": 150,
                                 "e1": 95, "f1": 25, "f2": 170})
        self.assertEqual(sum(times.values()), 615, "並行する子があるので、合計はルートの時間 520 を超える")

    def test_self_time_with_overlapping_children(self):
        spans = [
            Span("r", None, "r", "s", 0, 100),
            Span("x", "r", "x", "s", 10, 60),
            Span("y", "r", "y", "s", 40, 90),     # x と重なる
            Span("z", "r", "z", "s", 95, 130),    # 親の終わりを超えている（時計のずれ）
        ]
        self.assertEqual(self_times(build_tree(spans))["r"], 100 - (80 + 5), "子の区間の和集合を、親の区間に切り詰めて引く")

    def test_self_time_by_service(self):
        by_service = self_time_by_service(build_tree(checkout_spans()))
        self.assertEqual(list(by_service.items())[:3], [("payment", 195), ("inventory-db", 150), ("pricing", 95)])

    def test_critical_path(self):
        path = critical_path(build_tree(checkout_spans()))
        self.assertEqual(path, [
            ("a1", 0, 5), ("b1", 5, 35), ("a1", 35, 40), ("c1", 40, 50), ("c2", 50, 110), ("c1", 110, 120),
            ("a1", 120, 125), ("d1", 125, 140), ("d2", 140, 290), ("d1", 290, 300), ("a1", 300, 305),
            ("f1", 305, 320), ("f2", 320, 490), ("f1", 490, 500), ("a1", 500, 520),
        ])
        self.assertNotIn("e1", {sid for sid, _, _ in path}, "並行して先に終わる pricing は遅延に効いていない")

    def assert_valid_path(self, spans, path):
        tree = build_tree(spans)
        self.assertEqual(path[0][1], tree.root.start)
        self.assertEqual(path[-1][2], tree.root.end)
        for (_, _, e1), (_, s2, _) in zip(path, path[1:]):
            self.assertEqual(e1, s2, "区間は隙間なく連続する")
        for sid, s, e in path:
            self.assertLess(s, e, "長さ 0 の区間は含めない")
            self.assertTrue(tree.spans[sid].start <= s and e <= tree.spans[sid].end or sid == tree.root.span_id)

    def test_critical_path_properties_on_random_trees(self):
        rng = random.Random(44)
        for _ in range(200):
            spans = [Span("s0", None, "root", "svc", 0, 1000)]
            for i in range(1, rng.randrange(2, 15)):
                parent = rng.choice(spans)
                a = rng.uniform(parent.start, parent.end)
                b = rng.uniform(a, parent.end)
                spans.append(Span(f"s{i}", parent.span_id, f"op{i}", "svc", round(a, 3), round(b, 3)))
            path = critical_path(build_tree(spans))
            self.assert_valid_path(spans, path)

    def test_parallel_children_pick_the_last_to_finish(self):
        spans = [
            Span("r", None, "r", "s", 0, 100),
            Span("fast", "r", "fast", "s", 10, 50),
            Span("slow", "r", "slow", "s", 10, 90),
        ]
        self.assertEqual(critical_path(build_tree(spans)), [("r", 0, 10), ("slow", 10, 90), ("r", 90, 100)])

    def test_clock_skew_is_clipped(self):
        spans = [Span("r", None, "r", "s", 0, 100), Span("late", "r", "late", "s", 80, 130)]
        self.assertEqual(critical_path(build_tree(spans)), [("r", 0, 80), ("late", 80, 100)])


if __name__ == "__main__":
    unittest.main()
