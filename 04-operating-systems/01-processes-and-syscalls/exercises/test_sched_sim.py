"""4.1 CPU スケジューリングシミュレータ — テスト

実行: python3 tools/check.py 4.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from sched_sim import (
    IDLE,
    SWITCH,
    Metrics,
    Process,
    Slice,
    average,
    compute_metrics,
    fifo,
    mlfq,
    round_robin,
    sjf,
    srtf,
)

P = Process
S = Slice

# 教科書（Silberschatz ほか『Operating System Concepts』）の例
SILBERSCHATZ = [P("P1", 0, 8), P("P2", 1, 4), P("P3", 2, 9), P("P4", 3, 5)]
SILBERSCHATZ_SRTF = [S(0, 1, "P1"), S(1, 5, "P2"), S(5, 10, "P4"), S(10, 17, "P1"), S(17, 26, "P3")]
RR_EXAMPLE = [P("P1", 0, 24), P("P2", 0, 3), P("P3", 0, 3)]


def random_procs(rng: random.Random, max_n: int = 7, max_arrival: int = 15, max_burst: int = 9):
    n = rng.randint(1, max_n)
    return [P(f"J{i}", rng.randint(0, max_arrival), rng.randint(1, max_burst)) for i in range(n)]


class InvariantMixin:
    """どの方式のタイムラインでも成り立つべき性質を確かめる。"""

    def assert_valid_timeline(self, procs, timeline, allow_switch=False):
        msg = f"procs={procs}\ntimeline={timeline}"
        self.assertTrue(timeline, msg)
        self.assertEqual(timeline[0].start, 0, "タイムラインは時刻 0 から始まること\n" + msg)
        for a, b in zip(timeline, timeline[1:]):
            self.assertEqual(a.end, b.start, "区間は隙間なく連続していること\n" + msg)
            self.assertNotEqual(a.name, b.name, "隣り合う同名の区間は結合すること\n" + msg)
        for s in timeline:
            self.assertGreater(s.end, s.start, msg)
            if not allow_switch:
                self.assertNotEqual(s.name, SWITCH, msg)
        metrics = compute_metrics(procs, timeline)  # 実行時間の合計・到着前の実行もここで検査される
        # 仕事保存性: 実行可能なプロセスがいるのに CPU を遊ばせない
        for s in timeline:
            if s.name is IDLE:
                self.assertIn(s.end, {p.arrival for p in procs}, "アイドルは次の到着で終わること\n" + msg)
                for p in procs:
                    if p.arrival < s.end:
                        self.assertLessEqual(
                            metrics[p.name].completion, s.start,
                            f"{p.name} が実行可能なのに CPU がアイドルです\n" + msg,
                        )
        return metrics


class TestExercise1aMetrics(unittest.TestCase):
    def test_metrics_of_textbook_srtf_schedule(self):
        m = compute_metrics(SILBERSCHATZ, SILBERSCHATZ_SRTF)
        self.assertEqual(m["P1"], Metrics(completion=17, turnaround=17, waiting=9, response=0))
        self.assertEqual(m["P2"], Metrics(completion=5, turnaround=4, waiting=0, response=0))
        self.assertEqual(m["P3"], Metrics(completion=26, turnaround=24, waiting=15, response=15))
        self.assertEqual(m["P4"], Metrics(completion=10, turnaround=7, waiting=2, response=2))
        avg = average(m)
        self.assertAlmostEqual(avg.waiting, 6.5)
        self.assertAlmostEqual(avg.turnaround, 13.0)
        self.assertAlmostEqual(avg.response, 4.25)

    def test_idle_and_switch_slices_are_ignored(self):
        procs = [P("A", 2, 2), P("B", 2, 1)]
        timeline = [S(0, 2, IDLE), S(2, 4, "A"), S(4, 5, SWITCH), S(5, 6, "B")]
        m = compute_metrics(procs, timeline)
        self.assertEqual(m["A"], Metrics(4, 2, 0, 0))
        self.assertEqual(m["B"], Metrics(6, 4, 3, 3))

    def test_invalid_timelines_are_rejected(self):
        procs = [P("A", 0, 2), P("B", 1, 1)]
        bad = {
            "実行時間が burst と一致しない": [S(0, 1, "A"), S(1, 2, "B")],
            "到着前に実行している": [S(0, 1, "B"), S(1, 3, "A")],
            "未知のプロセス": [S(0, 2, "A"), S(2, 3, "Z")],
            "区間が重なっている": [S(0, 2, "A"), S(1, 2, "B")],
            "長さ 0 の区間": [S(0, 2, "A"), S(2, 2, "B"), S(2, 3, "B")],
            "一度も実行されないプロセス": [S(0, 2, "A")],
        }
        for label, timeline in bad.items():
            with self.assertRaises(ValueError, msg=label):
                compute_metrics(procs, timeline)

    def test_average_of_empty_metrics_is_an_error(self):
        with self.assertRaises(ValueError):
            average({})


class TestExercise1bFifoSjfSrtf(InvariantMixin, unittest.TestCase):
    def test_fifo_convoy_effect(self):
        procs = [P("A", 0, 100), P("B", 0, 10), P("C", 0, 10)]  # OSTEP の例
        timeline = fifo(procs)
        self.assertEqual(timeline, [S(0, 100, "A"), S(100, 110, "B"), S(110, 120, "C")])
        self.assertAlmostEqual(average(compute_metrics(procs, timeline)).turnaround, 110.0)

    def test_fifo_idles_until_next_arrival(self):
        procs = [P("A", 2, 3), P("B", 7, 1)]
        self.assertEqual(fifo(procs), [S(0, 2, IDLE), S(2, 5, "A"), S(5, 7, IDLE), S(7, 8, "B")])

    def test_fifo_ties_are_broken_by_input_order(self):
        procs = [P("B", 1, 2), P("A", 0, 1), P("C", 1, 1)]
        self.assertEqual(fifo(procs), [S(0, 1, "A"), S(1, 3, "B"), S(3, 4, "C")])

    def test_sjf_textbook(self):
        timeline = sjf(SILBERSCHATZ)
        self.assertEqual(timeline, [S(0, 8, "P1"), S(8, 12, "P2"), S(12, 17, "P4"), S(17, 26, "P3")])
        self.assertAlmostEqual(average(compute_metrics(SILBERSCHATZ, timeline)).waiting, 7.75)

    def test_sjf_all_at_zero_fixes_convoy(self):
        procs = [P("A", 0, 100), P("B", 0, 10), P("C", 0, 10)]
        self.assertEqual(sjf(procs), [S(0, 10, "B"), S(10, 20, "C"), S(20, 120, "A")])

    def test_sjf_is_non_preemptive(self):
        procs = [P("A", 0, 100), P("B", 10, 10), P("C", 10, 10)]
        timeline = sjf(procs)
        self.assertEqual(timeline[0], S(0, 100, "A"), "SJF は実行中のプロセスを横取りしない")
        self.assertAlmostEqual(average(compute_metrics(procs, timeline)).turnaround, 310 / 3)

    def test_srtf_textbook(self):
        timeline = srtf(SILBERSCHATZ)
        self.assertEqual(timeline, SILBERSCHATZ_SRTF)
        self.assertAlmostEqual(average(compute_metrics(SILBERSCHATZ, timeline)).waiting, 6.5)

    def test_srtf_preempts_long_job(self):
        procs = [P("A", 0, 100), P("B", 10, 10), P("C", 10, 10)]
        timeline = srtf(procs)
        self.assertEqual(timeline, [S(0, 10, "A"), S(10, 20, "B"), S(20, 30, "C"), S(30, 120, "A")])
        self.assertAlmostEqual(average(compute_metrics(procs, timeline)).turnaround, 50.0)

    def test_srtf_does_not_preempt_on_tie(self):
        procs = [P("A", 0, 4), P("B", 2, 2)]  # 時刻 2 で A の残りは 2、B も 2
        self.assertEqual(srtf(procs), [S(0, 4, "A"), S(4, 6, "B")])

    def test_empty_input(self):
        for f in (fifo, sjf, srtf):
            self.assertEqual(f([]), [], f.__name__)

    def test_invalid_processes(self):
        bad_inputs = [
            [P("A", 0, 1), P("A", 1, 1)],  # 名前の重複
            [P("A", -1, 1)],               # 負の到着時刻
            [P("A", 0, 0)],                # burst が 0
        ]
        for procs in bad_inputs:
            for f in (fifo, sjf, srtf):
                with self.assertRaises(ValueError, msg=f"{f.__name__}({procs})"):
                    f(procs)

    def test_random_invariants(self):
        rng = random.Random(41)
        for _ in range(300):
            procs = random_procs(rng)
            m_fifo = self.assert_valid_timeline(procs, fifo(procs))
            m_sjf = self.assert_valid_timeline(procs, sjf(procs))
            m_srtf = self.assert_valid_timeline(procs, srtf(procs))
            # FIFO と SJF は非プリエンプティブ: 各プロセスはちょうど 1 区間で走る
            for f in (fifo, sjf):
                names = [s.name for s in f(procs) if s.name is not IDLE]
                self.assertEqual(sorted(names), sorted(p.name for p in procs), f"{f.__name__}: {procs}")
            # FIFO は到着順（同時なら入力順）に走る
            order = [p.name for _, p in sorted(enumerate(procs), key=lambda x: (x[1].arrival, x[0]))]
            self.assertEqual([s.name for s in fifo(procs) if s.name is not IDLE], order)
            # SRTF は平均ターンアラウンド時間を最小にする（SRPT の最適性）
            best = average(m_srtf).turnaround
            for other in (m_fifo, m_sjf):
                self.assertLessEqual(best, average(other).turnaround + 1e-9, procs)

    def test_sjf_minimizes_waiting_when_all_arrive_together(self):
        rng = random.Random(42)
        for _ in range(200):
            procs = [P(f"J{i}", 0, rng.randint(1, 20)) for i in range(rng.randint(1, 8))]
            self.assertLessEqual(
                average(compute_metrics(procs, sjf(procs))).waiting,
                average(compute_metrics(procs, fifo(procs))).waiting + 1e-9,
                procs,
            )


class TestExercise2RoundRobin(InvariantMixin, unittest.TestCase):
    def test_textbook_quantum_4(self):
        timeline = round_robin(RR_EXAMPLE, 4)
        self.assertEqual(timeline, [S(0, 4, "P1"), S(4, 7, "P2"), S(7, 10, "P3"), S(10, 30, "P1")])
        m = compute_metrics(RR_EXAMPLE, timeline)
        self.assertEqual([m[n].waiting for n in ("P1", "P2", "P3")], [6, 4, 7])

    def test_new_arrival_is_queued_before_preempted_process(self):
        procs = [P("A", 0, 4), P("B", 2, 2)]
        self.assertEqual(round_robin(procs, 2), [S(0, 2, "A"), S(2, 4, "B"), S(4, 6, "A")])

    def test_quantum_1_gives_fast_response(self):
        procs = [P("A", 0, 5), P("B", 0, 5), P("C", 0, 5)]
        m = compute_metrics(procs, round_robin(procs, 1))
        self.assertEqual([m[n].response for n in "ABC"], [0, 1, 2])
        self.assertEqual([m[n].completion for n in "ABC"], [13, 14, 15])

    def test_huge_quantum_behaves_like_fifo(self):
        rng = random.Random(43)
        for _ in range(200):
            procs = random_procs(rng)
            self.assertEqual(round_robin(procs, 1000), fifo(procs), procs)

    def test_switch_cost_between_different_processes(self):
        procs = [P("A", 0, 3), P("B", 0, 3)]
        expected = [
            S(0, 1, "A"), S(1, 2, SWITCH), S(2, 3, "B"), S(3, 4, SWITCH), S(4, 5, "A"),
            S(5, 6, SWITCH), S(6, 7, "B"), S(7, 8, SWITCH), S(8, 9, "A"), S(9, 10, SWITCH),
            S(10, 11, "B"),
        ]
        self.assertEqual(round_robin(procs, 1, switch_cost=1), expected)

    def test_no_switch_cost_when_same_process_continues(self):
        self.assertEqual(round_robin([P("A", 0, 5)], 2, switch_cost=1), [S(0, 5, "A")])

    def test_no_switch_cost_after_idle(self):
        procs = [P("A", 0, 1), P("B", 3, 1)]
        self.assertEqual(round_robin(procs, 2, switch_cost=1), [S(0, 1, "A"), S(1, 3, IDLE), S(3, 4, "B")])

    def test_switch_cost_after_completion(self):
        procs = [P("A", 0, 1), P("B", 0, 1)]
        self.assertEqual(round_robin(procs, 2, switch_cost=1), [S(0, 1, "A"), S(1, 2, SWITCH), S(2, 3, "B")])

    def test_smaller_quantum_costs_more_with_switch_overhead(self):
        procs = [P("A", 0, 8), P("B", 1, 4), P("C", 2, 9), P("D", 3, 5)]
        makespans = [round_robin(procs, q, switch_cost=1)[-1].end for q in (1, 2, 4, 8)]
        self.assertEqual(makespans, sorted(makespans, reverse=True), "量子が小さいほど切り替えが増える")
        self.assertEqual(round_robin(procs, 1, switch_cost=0)[-1].end, 26)

    def test_invalid_parameters(self):
        for kwargs in ({"quantum": 0}, {"quantum": -1}, {"quantum": 1, "switch_cost": -1}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                round_robin([P("A", 0, 1)], **kwargs)

    def test_random_invariants(self):
        rng = random.Random(44)
        for _ in range(300):
            procs = random_procs(rng)
            q = rng.randint(1, 5)
            timeline = round_robin(procs, q)
            self.assert_valid_timeline(procs, timeline)
            with_cost = round_robin(procs, q, switch_cost=1)
            self.assertEqual(sum(s.end - s.start for s in with_cost if s.name not in (IDLE, SWITCH)),
                             sum(p.burst for p in procs))
            compute_metrics(procs, with_cost)


class TestExercise3Mlfq(InvariantMixin, unittest.TestCase):
    def test_demotion_after_using_allotment(self):
        procs = [P("A", 0, 6), P("B", 1, 1)]
        self.assertEqual(mlfq(procs, (1, 2, 4)), [S(0, 1, "A"), S(1, 2, "B"), S(2, 7, "A")])

    def test_new_arrival_preempts_lower_level_job(self):
        procs = [P("A", 0, 10), P("B", 3, 2)]
        self.assertEqual(mlfq(procs, (2, 4)), [S(0, 3, "A"), S(3, 5, "B"), S(5, 12, "A")])

    def test_short_interactive_jobs_finish_quickly(self):
        procs = [P("batch", 0, 50), P("ui1", 10, 2), P("ui2", 20, 2)]
        m = compute_metrics(procs, mlfq(procs, (2, 4, 8)))
        self.assertEqual((m["ui1"].response, m["ui1"].completion), (0, 12))
        self.assertEqual((m["ui2"].response, m["ui2"].completion), (0, 22))
        self.assertEqual(m["batch"].completion, 54)

    def test_single_level_is_round_robin(self):
        rng = random.Random(45)
        for _ in range(300):
            procs = random_procs(rng)
            q = rng.randint(1, 5)
            self.assertEqual(mlfq(procs, (q,)), round_robin(procs, q), (procs, q))

    def test_priority_boost_prevents_starvation(self):
        # 長いジョブ A の後ろから、短いジョブが 1 単位時間ごとに到着し続ける
        procs = [P("A", 0, 5)] + [P(f"S{i}", i, 1) for i in range(1, 31)]
        starved = compute_metrics(procs, mlfq(procs, (1, 2)))["A"]
        boosted = compute_metrics(procs, mlfq(procs, (1, 2), boost_interval=5))["A"]
        self.assertEqual(starved.completion, 35, "ブーストなしでは短いジョブが途切れるまで A は走れない")
        self.assertEqual(boosted.completion, 25, "ブーストがあれば A も定期的に CPU をもらえる")

    def test_invalid_parameters(self):
        for kwargs in ({"quanta": ()}, {"quanta": (2, 0)}, {"quanta": (2,), "boost_interval": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                mlfq([P("A", 0, 1)], **kwargs)

    def test_random_invariants(self):
        rng = random.Random(46)
        for _ in range(300):
            procs = random_procs(rng)
            quanta = tuple(rng.randint(1, 4) for _ in range(rng.randint(1, 3)))
            boost = rng.choice([None, 3, 7, 20])
            self.assert_valid_timeline(procs, mlfq(procs, quanta, boost))


if __name__ == "__main__":
    unittest.main()
