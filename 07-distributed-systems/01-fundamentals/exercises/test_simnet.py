"""7.1 分散システムの本質 — ネットワークシミュレータと実質1回の処理のテスト

実行: python3 tools/check.py 7.1   （またはこのディレクトリで python3 -m unittest -v test_simnet）
"""
import unittest

from simnet import IdempotentReceiver, Message, Network, ReliableSender


def make_echo_net(seed: int, **kwargs) -> tuple[Network, list[Message]]:
    """A と B の 2 ノード。B は受け取ったメッセージを記録するだけ。"""
    net = Network(seed, **kwargs)
    received: list[Message] = []
    net.register("A", lambda m: None)
    net.register("B", received.append)
    return net, received


def run_scenario(seed: int) -> tuple[list, dict]:
    net, _ = make_echo_net(seed, drop_rate=0.2, duplicate_rate=0.2)
    for i in range(50):
        net.send("A", "B", i)
    net.run()
    return net.log, dict(net.stats)


class TestExercise4Network(unittest.TestCase):
    def test_delivers_with_delay_in_range(self):
        net, received = make_echo_net(1, min_delay=2.0, max_delay=5.0)
        net.send("A", "B", "hello")
        self.assertEqual(received, [], "send しただけでは届かない（run で時間を進める）")
        net.run()
        self.assertEqual(len(received), 1)
        msg = received[0]
        self.assertEqual((msg.src, msg.dst, msg.payload, msg.sent_at), ("A", "B", "hello", 0.0))
        self.assertTrue(2.0 <= net.now <= 5.0, net.now)
        self.assertEqual(net.log, [(net.now, "A", "B", "hello")])

    def test_same_seed_same_execution(self):
        self.assertEqual(run_scenario(42), run_scenario(42), "シードが同じなら完全に同じ実行になること")

    def test_different_seed_different_execution(self):
        self.assertNotEqual(run_scenario(1)[0], run_scenario(2)[0])

    def test_messages_can_be_reordered(self):
        net, received = make_echo_net(3, min_delay=1.0, max_delay=10.0)
        for i in range(100):
            net.send("A", "B", i)
        net.run()
        payloads = [m.payload for m in received]
        self.assertEqual(sorted(payloads), list(range(100)))
        self.assertNotEqual(payloads, list(range(100)), "遅延がランダムなので順序が入れ替わるはず")
        times = [t for t, *_ in net.log]
        self.assertEqual(times, sorted(times), "log は配送時刻の順")
        self.assertTrue(all(1.0 <= t <= 10.0 for t in times))

    def test_drop_rate_statistics(self):
        net, received = make_echo_net(4, drop_rate=0.3)
        for i in range(3000):
            net.send("A", "B", i)
        net.run()
        self.assertEqual(net.stats["sent"], 3000)
        ratio = net.stats["dropped"] / 3000
        self.assertTrue(0.25 < ratio < 0.35, ratio)
        self.assertEqual(len(received), 3000 - net.stats["dropped"])

    def test_duplicate_rate_statistics(self):
        net, received = make_echo_net(5, duplicate_rate=0.5)
        for i in range(2000):
            net.send("A", "B", i)
        net.run()
        ratio = net.stats["duplicated"] / 2000
        self.assertTrue(0.45 < ratio < 0.55, ratio)
        self.assertEqual(len(received), 2000 + net.stats["duplicated"])

    def test_stats_invariant(self):
        net, received = make_echo_net(6, drop_rate=0.25, duplicate_rate=0.25)
        for i in range(500):
            net.send("A", "B", i)
        net.run()
        s = net.stats
        self.assertEqual(s["delivered"], s["sent"] - s["dropped"] + s["duplicated"])
        self.assertEqual(s["delivered"], len(received))

    def test_timers_fire_in_time_order_and_fifo_on_ties(self):
        net = Network(0)
        fired: list[str] = []
        net.schedule(5.0, lambda: fired.append("t5"))
        net.schedule(1.0, lambda: fired.append("t1-a"))
        net.schedule(1.0, lambda: fired.append("t1-b"))
        net.schedule(0.0, lambda: fired.append("t0"))
        self.assertEqual(net.run(), 4)
        self.assertEqual(fired, ["t0", "t1-a", "t1-b", "t5"])
        self.assertEqual(net.now, 5.0)

    def test_run_until_stops_and_advances_clock(self):
        net = Network(0)
        fired: list[float] = []
        for t in (1.0, 2.0, 30.0):
            net.schedule(t, lambda t=t: fired.append(t))
        self.assertEqual(net.run(until=10.0), 2)
        self.assertEqual(fired, [1.0, 2.0])
        self.assertEqual(net.now, 10.0, "until まで時計を進める")
        self.assertEqual(net.pending(), 1)
        net.run()
        self.assertEqual(fired, [1.0, 2.0, 30.0])

    def test_callbacks_can_schedule_more_events(self):
        net = Network(0)
        ticks: list[float] = []

        def tick() -> None:
            ticks.append(net.now)
            if len(ticks) < 5:
                net.schedule(10.0, tick)

        net.schedule(0.0, tick)
        net.run()
        self.assertEqual(ticks, [0.0, 10.0, 20.0, 30.0, 40.0])

    def test_partition_and_heal(self):
        net = Network(7)
        got: dict[str, list] = {"A": [], "B": [], "C": []}
        for node in got:
            net.register(node, lambda m, node=node: got[node].append(m.payload))
        net.partition({"A", "B"}, {"C"})
        net.send("A", "B", "ab")
        net.send("A", "C", "ac")
        net.send("C", "A", "ca")
        net.run()
        self.assertEqual(got, {"A": [], "B": ["ab"], "C": []})
        net.heal()
        net.send("A", "C", "ac2")
        net.run()
        self.assertEqual(got["C"], ["ac2"])

    def test_partition_at_delivery_time_drops_in_flight_messages(self):
        net, received = make_echo_net(8, min_delay=5.0, max_delay=5.0)
        net.send("A", "B", "in-flight")
        net.schedule(1.0, lambda: net.partition({"A"}, {"B"}))
        net.run()
        self.assertEqual(received, [], "配送の瞬間に分断されていれば届かない")
        self.assertEqual(net.stats["dropped"], 1)

    def test_validation(self):
        for kwargs in (
            {"drop_rate": -0.1},
            {"drop_rate": 1.5},
            {"duplicate_rate": 2.0},
            {"min_delay": -1.0},
            {"min_delay": 5.0, "max_delay": 1.0},
        ):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                Network(0, **kwargs)
        net, _ = make_echo_net(0)
        with self.assertRaises(ValueError):
            net.register("A", lambda m: None)
        with self.assertRaises(ValueError):
            net.send("A", "Z", "unknown node")
        with self.assertRaises(ValueError):
            net.schedule(-1.0, lambda: None)

    def test_max_events_guard(self):
        net = Network(0)

        def forever() -> None:
            net.schedule(1.0, forever)

        net.schedule(0.0, forever)
        with self.assertRaises(RuntimeError):
            net.run(max_events=1000)


def build_pair(seed: int, **net_kwargs) -> tuple[Network, ReliableSender, IdempotentReceiver]:
    net = Network(seed, min_delay=1.0, max_delay=10.0, **net_kwargs)
    sender = ReliableSender(net, "S", retry_interval=30.0, max_attempts=30)
    receiver = IdempotentReceiver(net, "R")
    return net, sender, receiver


class TestExercise5EffectivelyOnce(unittest.TestCase):
    def test_reliable_network_needs_one_attempt(self):
        net, sender, receiver = build_pair(10)
        ids = [sender.send("R", f"order-{i}") for i in range(20)]
        net.run()
        self.assertEqual(len(set(ids)), 20, "メッセージ ID は一意")
        self.assertEqual(sorted(receiver.processed), sorted(f"order-{i}" for i in range(20)))
        self.assertEqual(sender.acked, set(ids))
        self.assertEqual(sender.pending, {})
        self.assertEqual(set(sender.attempts.values()), {1}, "損失がなければ再送は不要")
        self.assertEqual(receiver.duplicates, 0)

    def test_lossy_network_effectively_once(self):
        for seed in range(5):
            net, sender, receiver = build_pair(seed, drop_rate=0.3, duplicate_rate=0.2)
            bodies = [f"payment-{seed}-{i}" for i in range(200)]
            for b in bodies:
                sender.send("R", b)
            net.run()
            self.assertEqual(sender.failed, set(), f"seed={seed}: 十分な再送回数があれば全て ACK される")
            self.assertEqual(len(sender.acked), 200)
            self.assertEqual(
                sorted(receiver.processed), sorted(bodies), f"seed={seed}: 各メッセージをちょうど 1 回処理"
            )
            self.assertGreater(receiver.duplicates, 0, "重複（再送・ネットワークの複製）は実際に届いている")
            deliveries_to_r = sum(1 for _, _, dst, _ in net.log if dst == "R")
            self.assertGreater(deliveries_to_r, 200, "冪等でない受信側なら二重処理していた")

    def test_retries_survive_a_temporary_partition(self):
        net, sender, receiver = build_pair(11)
        net.partition({"S"}, {"R"})
        net.schedule(200.0, net.heal)
        for i in range(10):
            sender.send("R", i)
        net.run()
        self.assertEqual(sorted(receiver.processed), list(range(10)))
        self.assertEqual(sender.failed, set())
        self.assertTrue(all(n > 1 for n in sender.attempts.values()), "分断中は再送が必要だった")

    def test_permanent_partition_gives_up(self):
        net = Network(12)
        sender = ReliableSender(net, "S", retry_interval=30.0, max_attempts=4)
        receiver = IdempotentReceiver(net, "R")
        net.partition({"S"}, {"R"})
        ids = {sender.send("R", i) for i in range(3)}
        net.run()
        self.assertEqual(sender.failed, ids)
        self.assertEqual(sender.pending, {})
        self.assertEqual(set(sender.attempts.values()), {4})
        self.assertEqual(receiver.processed, [])

    def test_receiver_acks_duplicates_and_calls_process_once(self):
        net = Network(13)
        acks: list = []
        calls: list = []
        net.register("S", lambda m: acks.append(m.payload))
        receiver = IdempotentReceiver(net, "R", process=calls.append)
        data = {"type": "DATA", "id": "S-1", "body": "x"}
        for _ in range(3):
            net.send("S", "R", data)
        net.run()
        self.assertEqual(calls, ["x"])
        self.assertEqual(receiver.processed, ["x"])
        self.assertEqual(receiver.duplicates, 2)
        self.assertEqual(acks, [{"type": "ACK", "id": "S-1"}] * 3, "重複にも ACK を返すこと")

    def test_sender_validation(self):
        net = Network(0)
        with self.assertRaises(ValueError):
            ReliableSender(net, "S", retry_interval=0.0)
        with self.assertRaises(ValueError):
            ReliableSender(net, "S2", max_attempts=0)


if __name__ == "__main__":
    unittest.main()
