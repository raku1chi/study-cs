"""5.2 TCPとUDP — テスト（tcp_sim）

実行: python3 tools/check.py 5.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import unittest

from tcp_sim import (
    CongestionState,
    LossyChannel,
    RenoCongestionControl,
    cwnd_trace,
    simulate_go_back_n,
    simulate_selective_repeat,
)

T, F = True, False  # T = その送信は失われる


class TestLossyChannel(unittest.TestCase):
    def test_pattern_then_no_loss(self):
        ch = LossyChannel([F, T, T])
        self.assertEqual([ch.transmit() for _ in range(5)], [True, False, False, True, True])
        self.assertEqual(ch.sent, 5)


class TestExercise2GoBackN(unittest.TestCase):
    def test_single_loss(self):
        # 送信 0: #0 成功, 送信 1: #1 喪失, 送信 2: #2 は届くが順番が違うので捨てられる
        r = simulate_go_back_n(5, 3, [F, T])
        self.assertEqual(r.transmissions, 7)
        self.assertEqual(r.rounds, 3)
        self.assertEqual(r.delivered, [0, 1, 2, 3, 4])
        self.assertEqual(r.log[:6], [(1, 0, True), (1, 1, False), (1, 2, True), (2, 1, True), (2, 2, True), (2, 3, True)])

    def test_burst_loss(self):
        r = simulate_go_back_n(8, 4, [F, T, T, F])
        self.assertEqual((r.transmissions, r.rounds), (11, 3))

    def test_no_loss(self):
        for n, w in [(10, 4), (10, 1), (3, 10), (0, 5), (12, 12)]:
            r = simulate_go_back_n(n, w, [])
            self.assertEqual(r.transmissions, n, (n, w))
            self.assertEqual(r.rounds, math.ceil(n / w), (n, w))
            self.assertEqual(r.delivered, list(range(n)))

    def test_stop_and_wait(self):
        r = simulate_go_back_n(3, 1, [T, F, T, F])
        self.assertEqual((r.transmissions, r.rounds), (5, 5))

    def test_invalid(self):
        with self.assertRaises(ValueError):
            simulate_go_back_n(5, 0, [])
        with self.assertRaises(ValueError):
            simulate_go_back_n(-1, 3, [])


class TestExercise2SelectiveRepeat(unittest.TestCase):
    def test_single_loss(self):
        r = simulate_selective_repeat(5, 3, [F, T])
        self.assertEqual(r.transmissions, 6, "届いた #2 は送り直さない")
        self.assertEqual(r.rounds, 3)
        self.assertEqual(r.delivered, [0, 1, 2, 3, 4])
        self.assertEqual(r.log[:5], [(1, 0, True), (1, 1, False), (1, 2, True), (2, 1, True), (2, 3, True)])

    def test_burst_loss(self):
        r = simulate_selective_repeat(8, 4, [F, T, T, F])
        self.assertEqual((r.transmissions, r.rounds), (10, 3))

    def test_no_loss_matches_gbn(self):
        for n, w in [(10, 4), (7, 1), (0, 3)]:
            a, b = simulate_selective_repeat(n, w, []), simulate_go_back_n(n, w, [])
            self.assertEqual((a.transmissions, a.rounds), (b.transmissions, b.rounds))

    def test_stop_and_wait_is_the_same_for_both(self):
        pattern = [T, F, T, F, T, T, F]
        a, b = simulate_selective_repeat(4, 1, pattern), simulate_go_back_n(4, 1, pattern)
        self.assertEqual((a.transmissions, a.rounds, a.log), (b.transmissions, b.rounds, b.log))


class TestExercise2Properties(unittest.TestCase):
    def test_random_patterns(self):
        rng = random.Random(523)
        for _ in range(300):
            n, w = rng.randrange(0, 40), rng.randrange(1, 9)
            pattern = [rng.random() < 0.3 for _ in range(rng.randrange(0, 80))]
            gbn = simulate_go_back_n(n, w, pattern)
            sr = simulate_selective_repeat(n, w, pattern)
            for r in (gbn, sr):
                self.assertEqual(r.delivered, list(range(n)), "すべて順番どおりに届く")
                self.assertEqual(len(r.log), r.transmissions)
                self.assertEqual([ok for _, _, ok in r.log],
                                 [not (i < len(pattern) and pattern[i]) for i in range(r.transmissions)],
                                 "通信路のパターンを送信順に消費する")
                self.assertTrue(all(len({s for rd, s, _ in r.log if rd == k}) <= w for k in range(1, r.rounds + 1)),
                                "1 ラウンドに送るのはウィンドウの数まで")
            lost_sr = sum(1 for _, _, ok in sr.log if not ok)
            self.assertEqual(sr.transmissions, n + lost_sr, "SR は失われた分だけ送り直す")
            lost_gbn = sum(1 for _, _, ok in gbn.log if not ok)
            self.assertGreaterEqual(gbn.transmissions, n + lost_gbn)


class TestExercise3Congestion(unittest.TestCase):
    def cw(self, events, **kw):
        return [s.cwnd for s in cwnd_trace(events, **kw)]

    def test_slow_start_then_congestion_avoidance(self):
        trace = cwnd_trace(["ack"] * 15, initial_cwnd=1, initial_ssthresh=8)
        self.assertEqual([s.cwnd for s in trace], [2, 3, 4, 5, 6, 7, 8, 8, 8, 8, 8, 8, 8, 8, 9])
        self.assertEqual(trace[5].phase, "slow_start")
        self.assertEqual(trace[6].phase, "congestion_avoidance", "cwnd が ssthresh に達したら輻輳回避")
        self.assertEqual(trace[0], CongestionState(2, 8, "slow_start"))

    def test_slow_start_doubles_per_round_trip(self):
        # 1 RTT ＝ そのときの cwnd 個の ACK。スロースタートでは 1 RTT ごとに 2 倍になる
        cc = RenoCongestionControl(initial_cwnd=1, initial_ssthresh=1000)
        sizes = []
        for _ in range(6):
            for _ in range(cc.cwnd):
                cc.on_ack()
            sizes.append(cc.cwnd)
        self.assertEqual(sizes, [2, 4, 8, 16, 32, 64])

    def test_congestion_avoidance_adds_one_per_round_trip(self):
        cc = RenoCongestionControl(initial_cwnd=20, initial_ssthresh=10)
        sizes = []
        for _ in range(4):
            for _ in range(cc.cwnd):
                cc.on_ack()
            sizes.append(cc.cwnd)
        self.assertEqual(sizes, [21, 22, 23, 24])

    def test_reno_fast_retransmit_and_recovery(self):
        trace = cwnd_trace(["dupack"] * 5 + ["ack"], initial_cwnd=10, initial_ssthresh=5)
        self.assertEqual(
            [(s.cwnd, s.ssthresh, s.phase) for s in trace],
            [
                (10, 5, "congestion_avoidance"),
                (10, 5, "congestion_avoidance"),
                (8, 5, "fast_recovery"),   # 3 つ目の重複 ACK: ssthresh = 10 // 2, cwnd = ssthresh + 3
                (9, 5, "fast_recovery"),   # 以後の重複 ACK で膨らませる
                (10, 5, "fast_recovery"),
                (5, 5, "congestion_avoidance"),  # 新しい ACK で ssthresh に戻して高速回復を抜ける
            ],
        )

    def test_tahoe_restarts_slow_start(self):
        trace = cwnd_trace(["dupack"] * 3 + ["ack"] * 4, initial_cwnd=10, initial_ssthresh=5, variant="tahoe")
        self.assertEqual([(s.cwnd, s.phase) for s in trace],
                         [(10, "congestion_avoidance"), (10, "congestion_avoidance"), (1, "slow_start"),
                          (2, "slow_start"), (3, "slow_start"), (4, "slow_start"), (5, "congestion_avoidance")])
        self.assertEqual(trace[2].ssthresh, 5)

    def test_timeout(self):
        trace = cwnd_trace(["timeout", "ack", "ack"], initial_cwnd=20, initial_ssthresh=100)
        self.assertEqual([(s.cwnd, s.ssthresh, s.phase) for s in trace],
                         [(1, 10, "slow_start"), (2, 10, "slow_start"), (3, 10, "slow_start")])

    def test_timeout_during_fast_recovery(self):
        trace = cwnd_trace(["dupack"] * 3 + ["timeout"], initial_cwnd=10, initial_ssthresh=5)
        self.assertEqual((trace[-1].cwnd, trace[-1].ssthresh, trace[-1].phase), (1, 4, "slow_start"))

    def test_ssthresh_floor_is_two(self):
        trace = cwnd_trace(["dupack"] * 3, initial_cwnd=3, initial_ssthresh=2)
        self.assertEqual((trace[-1].ssthresh, trace[-1].cwnd), (2, 5))
        self.assertEqual(cwnd_trace(["timeout"], initial_cwnd=1)[-1].ssthresh, 2)

    def test_new_ack_resets_duplicate_count(self):
        self.assertEqual(self.cw(["dupack", "dupack", "ack", "dupack", "dupack"], initial_cwnd=10, initial_ssthresh=5),
                         [10, 10, 10, 10, 10], "重複 ACK は連続して 3 つ来たときだけ高速再送")

    def test_aimd_sawtooth(self):
        # 輻輳回避中に「cwnd が 16 になるたびに損失」を繰り返すと、8〜16 の間を往復する
        cc = RenoCongestionControl(initial_cwnd=16, initial_ssthresh=8)
        lows = []
        for _ in range(3):
            for _ in range(3):
                cc.on_dupack()
            cc.on_ack()
            lows.append(cc.cwnd)
            while cc.cwnd < 16:
                cc.on_ack()
        self.assertEqual(lows, [8, 8, 8])

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            cwnd_trace(["ack", "nack"])
        with self.assertRaises(ValueError):
            cwnd_trace([], variant="cubic")


if __name__ == "__main__":
    unittest.main()
