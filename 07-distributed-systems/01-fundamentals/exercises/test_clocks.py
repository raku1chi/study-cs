"""7.1 分散システムの本質 — 論理時計のテスト

実行: python3 tools/check.py 7.1   （またはこのディレクトリで python3 -m unittest -v test_clocks）
"""
import itertools
import random
import unittest

from clocks import (
    Event,
    LamportClock,
    Ordering,
    VectorClock,
    concurrent_pairs,
    lamport_timestamps,
    lamport_total_order,
    vector_timestamps,
)

# 本文の図と同じトレース（A→B に m1、B→C に m2、C→A に m3）
SAMPLE_TRACE = [
    Event("a1", "A"),
    Event("a2", "A", "send", "m1"),
    Event("b1", "B"),
    Event("b2", "B", "recv", "m1"),
    Event("b3", "B", "send", "m2"),
    Event("c1", "C"),
    Event("c2", "C", "send", "m3"),
    Event("a3", "A", "recv", "m3"),
    Event("c3", "C", "recv", "m2"),
    Event("a4", "A"),
]


def random_trace(rng: random.Random, n_events: int = 40, nodes: str = "ABCD") -> list[Event]:
    """ランダムだが正しい（受信は必ず送信の後）トレースを作る。"""
    trace: list[Event] = []
    in_flight: list[tuple[str, str]] = []  # (msg, 宛先ノード)
    msg_no = 0
    for i in range(n_events):
        node = rng.choice(nodes)
        deliverable = [m for m in in_flight if m[1] == node]
        r = rng.random()
        if deliverable and r < 0.4:
            m = rng.choice(deliverable)
            in_flight.remove(m)
            trace.append(Event(f"e{i}", node, "recv", m[0]))
        elif r < 0.7:
            msg_no += 1
            dst = rng.choice([n for n in nodes if n != node])
            in_flight.append((f"m{msg_no}", dst))
            trace.append(Event(f"e{i}", node, "send", f"m{msg_no}"))
        else:
            trace.append(Event(f"e{i}", node))
    return trace


def happened_before_closure(trace: list[Event]) -> set[tuple[str, str]]:
    """happened-before 関係を「定義どおり」に計算する（正解データ）。

    辺: 同じノードで連続するイベント、send → 対応する recv。その推移閉包をとる。
    """
    succ: dict[str, set[str]] = {ev.name: set() for ev in trace}
    last_on_node: dict[str, str] = {}
    send_of: dict[str, str] = {}
    for ev in trace:
        if ev.node in last_on_node:
            succ[last_on_node[ev.node]].add(ev.name)
        last_on_node[ev.node] = ev.name
        if ev.kind == "send":
            send_of[ev.msg] = ev.name
        elif ev.kind == "recv":
            succ[send_of[ev.msg]].add(ev.name)
    closure: set[tuple[str, str]] = set()
    for start in succ:
        stack = list(succ[start])
        seen: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            closure.add((start, cur))
            stack.extend(succ[cur])
    return closure


class TestExercise1LamportClock(unittest.TestCase):
    def test_starts_at_zero_and_ticks(self):
        c = LamportClock()
        self.assertEqual(c.time, 0)
        self.assertEqual(c.tick(), 1)
        self.assertEqual(c.tick(), 2)
        self.assertEqual(c.time, 2)

    def test_send_advances_like_a_local_event(self):
        c = LamportClock()
        self.assertEqual(c.send(), 1)
        self.assertEqual(c.send(), 2)

    def test_receive_takes_max_plus_one(self):
        c = LamportClock()
        c.tick()  # 1
        self.assertEqual(c.receive(10), 11, "相手の方が進んでいれば max + 1")
        self.assertEqual(c.receive(3), 12, "自分の方が進んでいても、受信はイベントなので +1")
        self.assertEqual(c.time, 12)

    def test_message_exchange(self):
        a, b = LamportClock(), LamportClock()
        t = a.send()  # a: 1
        b.tick()
        b.tick()  # b: 2
        self.assertEqual(b.receive(t), 3)
        self.assertEqual(a.receive(b.send()), 5)  # b.send() = 4 → a = max(1, 4) + 1

    def test_negative_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            LamportClock().receive(-1)


class TestExercise2VectorClock(unittest.TestCase):
    def test_empty_and_get(self):
        vc = VectorClock()
        self.assertEqual(vc.get("A"), 0)
        self.assertEqual(vc.to_dict(), {})

    def test_increment_returns_new_clock(self):
        vc = VectorClock()
        vc2 = vc.increment("A")
        self.assertEqual(vc.to_dict(), {}, "元の時計を書き換えないこと（不変）")
        self.assertEqual(vc2.to_dict(), {"A": 1})
        self.assertEqual(vc2.increment("A").increment("B").to_dict(), {"A": 2, "B": 1})

    def test_merge_takes_elementwise_max(self):
        a = VectorClock({"A": 3, "B": 1})
        b = VectorClock({"B": 4, "C": 2})
        self.assertEqual(a.merge(b).to_dict(), {"A": 3, "B": 4, "C": 2})
        self.assertEqual(a.merge(b), b.merge(a))
        self.assertEqual(a.to_dict(), {"A": 3, "B": 1}, "merge も元の時計を書き換えない")

    def test_compare_all_outcomes(self):
        a = VectorClock({"A": 1})
        b = VectorClock({"A": 2, "B": 1})
        c = VectorClock({"B": 1})
        self.assertIs(a.compare(b), Ordering.BEFORE)
        self.assertIs(b.compare(a), Ordering.AFTER)
        self.assertIs(a.compare(c), Ordering.CONCURRENT)
        self.assertIs(c.compare(a), Ordering.CONCURRENT)
        self.assertIs(b.compare(VectorClock({"B": 1, "A": 2})), Ordering.EQUAL)
        self.assertIs(VectorClock().compare(a), Ordering.BEFORE)
        self.assertIs(VectorClock().compare(VectorClock()), Ordering.EQUAL)

    def test_zero_entries_are_normalized(self):
        self.assertEqual(VectorClock({"A": 0, "B": 2}), VectorClock({"B": 2}))
        self.assertEqual(VectorClock({"A": 0}).to_dict(), {})
        self.assertEqual(hash(VectorClock({"A": 0, "B": 2})), hash(VectorClock({"B": 2})))

    def test_invalid_counts(self):
        with self.assertRaises(ValueError):
            VectorClock({"A": -1})


class TestExercise3Trace(unittest.TestCase):
    def test_lamport_timestamps_of_sample_trace(self):
        self.assertEqual(
            lamport_timestamps(SAMPLE_TRACE),
            {"a1": 1, "a2": 2, "b1": 1, "b2": 3, "b3": 4, "c1": 1, "c2": 2, "a3": 3, "c3": 5, "a4": 4},
        )

    def test_vector_timestamps_of_sample_trace(self):
        got = {name: vc.to_dict() for name, vc in vector_timestamps(SAMPLE_TRACE).items()}
        self.assertEqual(
            got,
            {
                "a1": {"A": 1},
                "a2": {"A": 2},
                "b1": {"B": 1},
                "b2": {"A": 2, "B": 2},
                "b3": {"A": 2, "B": 3},
                "c1": {"C": 1},
                "c2": {"C": 2},
                "a3": {"A": 3, "C": 2},
                "c3": {"A": 2, "B": 3, "C": 3},
                "a4": {"A": 4, "C": 2},
            },
        )

    def test_lamport_total_order_breaks_ties_by_node(self):
        self.assertEqual(
            lamport_total_order(SAMPLE_TRACE),
            ["a1", "b1", "c1", "a2", "c2", "a3", "b2", "a4", "b3", "c3"],
        )

    def test_lamport_cannot_detect_concurrency(self):
        # b1 と a2 は並行だが、Lamport 時刻は 1 < 2 になる（逆は成り立たない）
        lam = lamport_timestamps(SAMPLE_TRACE)
        vec = vector_timestamps(SAMPLE_TRACE)
        self.assertLess(lam["b1"], lam["a2"])
        self.assertIs(vec["b1"].compare(vec["a2"]), Ordering.CONCURRENT)

    def test_concurrent_pairs_of_selected_events(self):
        self.assertEqual(concurrent_pairs(SAMPLE_TRACE, ["a3", "b3", "c3"]), [("b3", "a3"), ("a3", "c3")])
        self.assertEqual(concurrent_pairs(SAMPLE_TRACE, ["a1", "b2", "c3"]), [])
        # 並びはトレース上の出現順（引数の順序に依存しない）
        self.assertEqual(concurrent_pairs(SAMPLE_TRACE, ["c3", "a4"]), [("c3", "a4")])

    def test_concurrent_writes_on_two_replicas(self):
        # 2 つのレプリカが互いのことを知らずに同じキーへ書き込む → 並行な書き込み
        trace = [
            Event("w1", "R1"),
            Event("sync1", "R1", "send", "s1"),
            Event("w2", "R2"),
            Event("recv1", "R2", "recv", "s1"),
            Event("w3", "R2"),  # R1 の w1 を知った後の書き込み
        ]
        self.assertEqual(concurrent_pairs(trace, ["w1", "w2", "w3"]), [("w1", "w2")])

    def test_unknown_name_raises_key_error(self):
        with self.assertRaises(KeyError):
            concurrent_pairs(SAMPLE_TRACE, ["a1", "zz"])

    def test_vector_clocks_match_happened_before_definition(self):
        rng = random.Random(71)
        for _ in range(30):
            trace = random_trace(rng)
            hb = happened_before_closure(trace)
            vec = vector_timestamps(trace)
            lam = lamport_timestamps(trace)
            for a, b in itertools.combinations([ev.name for ev in trace], 2):
                order = vec[a].compare(vec[b])
                if (a, b) in hb:
                    self.assertIs(order, Ordering.BEFORE, (a, b))
                    self.assertLess(lam[a], lam[b], "a → b なら L(a) < L(b)（時計条件）")
                elif (b, a) in hb:
                    self.assertIs(order, Ordering.AFTER, (a, b))
                else:
                    self.assertIs(order, Ordering.CONCURRENT, (a, b))

    def test_total_order_is_consistent_with_causality(self):
        rng = random.Random(72)
        for _ in range(20):
            trace = random_trace(rng)
            order = lamport_total_order(trace)
            self.assertEqual(sorted(order), sorted(ev.name for ev in trace))
            pos = {name: i for i, name in enumerate(order)}
            for a, b in happened_before_closure(trace):
                self.assertLess(pos[a], pos[b], (a, b))

    def test_invalid_traces(self):
        bad_traces = {
            "未送信メッセージの受信": [Event("x", "A", "recv", "m9")],
            "名前の重複": [Event("x", "A"), Event("x", "B")],
            "不明な種類": [Event("x", "A", "broadcast", "m1")],
            "send に msg がない": [Event("x", "A", "send")],
            "同じメッセージを 2 回送信": [Event("x", "A", "send", "m1"), Event("y", "A", "send", "m1")],
            "同じメッセージを 2 回受信": [
                Event("x", "A", "send", "m1"),
                Event("y", "B", "recv", "m1"),
                Event("z", "C", "recv", "m1"),
            ],
            "受信が送信より先": [Event("y", "B", "recv", "m1"), Event("x", "A", "send", "m1")],
        }
        for label, trace in bad_traces.items():
            with self.assertRaises(ValueError, msg=label):
                lamport_timestamps(trace)
            with self.assertRaises(ValueError, msg=label):
                vector_timestamps(trace)


if __name__ == "__main__":
    unittest.main()
