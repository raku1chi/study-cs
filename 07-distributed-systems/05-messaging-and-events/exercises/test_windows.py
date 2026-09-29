"""7.5 メッセージングとイベント駆動 — イベント時刻のウィンドウ集計のテスト

実行: python3 tools/check.py 7.5   （またはこのディレクトリで python3 -m unittest -v test_windows）
"""
import random
import unittest
from collections import defaultdict

from windows import Event, WindowedAggregator, WindowResult


def feed(agg: WindowedAggregator, events) -> list[WindowResult]:
    out = []
    for e in events:
        out.extend(agg.process(e))
    return out


def ev(t: int, key: str = "k", value: float = 1.0) -> Event:
    return Event(key, value, t)


def brute_force(events, size: int, slide: int) -> dict:
    """すべてのイベントを見てから計算した「正解」: (key, start) → (count, total)。"""
    acc = defaultdict(lambda: [0, 0.0])
    for e in events:
        start = e.event_time - e.event_time % slide
        while start > e.event_time - size:
            acc[(e.key, start)][0] += 1
            acc[(e.key, start)][1] += e.value
            start -= slide
    return {k: (c, round(t, 6)) for k, (c, t) in acc.items()}


def final_results(results) -> dict:
    """発火・更新された結果のうち、各ウィンドウの最後のものを残す。"""
    last = {}
    for r in results:
        last[(r.key, r.start)] = (r.count, round(r.total, 6))
    return last


class TestExercise7Windows(unittest.TestCase):
    def test_window_assignment(self):
        tumbling = WindowedAggregator(size=10)
        self.assertEqual(tumbling.windows_for(0), [0])
        self.assertEqual(tumbling.windows_for(9), [0])
        self.assertEqual(tumbling.windows_for(10), [10])
        sliding = WindowedAggregator(size=10, slide=5)
        self.assertEqual(sliding.windows_for(7), [0, 5])
        self.assertEqual(sliding.windows_for(3), [-5, 0], "先頭付近では開始が負のウィンドウにも属する")
        self.assertEqual(sliding.windows_for(10), [5, 10])
        hopping = WindowedAggregator(size=10, slide=2)
        self.assertEqual(hopping.windows_for(11), [2, 4, 6, 8, 10])

    def test_tumbling_in_order(self):
        agg = WindowedAggregator(size=10)
        self.assertIsNone(agg.watermark)
        out = feed(agg, [ev(1, value=2.0), ev(2, value=3.0)])
        self.assertEqual(out, [])
        self.assertEqual(agg.watermark, 2)
        out = agg.process(ev(11, value=1.0))
        self.assertEqual(out, [WindowResult("k", 0, 10, 2, 5.0)], "ウォーターマークが 10 を越えたら [0,10) を出す")
        out = feed(agg, [ev(12), ev(25)])
        self.assertEqual(out, [WindowResult("k", 10, 20, 2, 2.0)])
        self.assertEqual(agg.flush(), [WindowResult("k", 20, 30, 1, 1.0)])
        self.assertEqual(agg.flush(), [], "flush の後は状態が空")

    def test_out_of_order_events_within_bound_are_counted(self):
        agg = WindowedAggregator(size=10, max_out_of_orderness=5)
        self.assertEqual(feed(agg, [ev(1), ev(12)]), [])
        self.assertEqual(agg.watermark, 7, "ウォーターマーク = 最大のイベント時刻 - 5")
        self.assertEqual(agg.process(ev(8)), [], "遅れて届いたが、[0,10) はまだ閉じていない")
        self.assertEqual(agg.process(ev(16)), [WindowResult("k", 0, 10, 2, 2.0)])
        self.assertEqual(agg.late_events, [])

    def test_too_late_events_go_to_side_output(self):
        agg = WindowedAggregator(size=10)
        feed(agg, [ev(1), ev(20)])
        self.assertEqual(agg.process(ev(5)), [])
        self.assertEqual(agg.late_events, [ev(5)], "閉じたウィンドウに属するイベントはサイド出力へ")

    def test_allowed_lateness_updates_fired_window(self):
        agg = WindowedAggregator(size=10, allowed_lateness=10)
        self.assertEqual(feed(agg, [ev(1), ev(15)]), [WindowResult("k", 0, 10, 1, 1.0)])
        self.assertEqual(
            agg.process(ev(5)), [WindowResult("k", 0, 10, 2, 2.0, is_update=True)], "許容遅延の間は更新を出す"
        )
        feed(agg, [ev(30)])  # ウォーターマーク 30 >= 10 + 10 → [0,10) の状態は捨てられる
        self.assertEqual(agg.process(ev(7)), [])
        self.assertEqual(agg.late_events, [ev(7)])

    def test_watermark_never_goes_back(self):
        agg = WindowedAggregator(size=10, max_out_of_orderness=3)
        feed(agg, [ev(50), ev(20), ev(40)])
        self.assertEqual(agg.watermark, 47)

    def test_keys_are_aggregated_separately_and_results_are_ordered(self):
        agg = WindowedAggregator(size=10)
        out = feed(agg, [ev(1, "b", 1), ev(2, "a", 10), ev(15, "a", 5), ev(3, "b", 1), ev(31, "c", 0)])
        self.assertEqual(
            out,
            [
                WindowResult("a", 0, 10, 1, 10.0),
                WindowResult("b", 0, 10, 1, 1.0),
                WindowResult("a", 10, 20, 1, 5.0),
            ],
            "ウィンドウの終わり → キー → 開始 の順",
        )
        self.assertEqual(agg.late_events, [ev(3, "b", 1)])

    def test_sliding_windows_match_brute_force(self):
        rng = random.Random(1)
        t = 0
        events = []
        for _ in range(300):
            t += rng.randrange(0, 4)
            events.append(ev(t, rng.choice("xyz"), rng.randrange(1, 10)))
        agg = WindowedAggregator(size=10, slide=5)
        results = feed(agg, events) + agg.flush()
        self.assertTrue(all(not r.is_update for r in results))
        self.assertEqual(final_results(results), brute_force(events, 10, 5))
        self.assertEqual(len(results), len(brute_force(events, 10, 5)), "各ウィンドウを 1 回ずつ出す")

    def test_bounded_disorder_gives_exact_results(self):
        for seed in range(5):
            rng = random.Random(seed)
            ooo = rng.randrange(1, 8)
            base = 0
            events = []
            for _ in range(400):
                base += rng.randrange(0, 3)
                # 到着の順序はばらばらだが、遅れは高々 ooo（ウォーターマークの仮定が正しい）
                events.append(ev(base - rng.randrange(0, ooo + 1) if base > ooo else base, rng.choice("pq"), 1.0))
            size, slide = rng.choice([(10, 10), (10, 5), (6, 3)])
            agg = WindowedAggregator(size=size, slide=slide, max_out_of_orderness=ooo)
            results = feed(agg, events) + agg.flush()
            self.assertEqual(agg.late_events, [], f"seed={seed}")
            self.assertEqual(final_results(results), brute_force(events, size, slide), f"seed={seed}")

    def test_validation(self):
        for kwargs in (
            {"size": 0},
            {"size": 10, "slide": 0},
            {"size": 10, "slide": 11},
            {"size": 10, "allowed_lateness": -1},
            {"size": 10, "max_out_of_orderness": -1},
        ):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                WindowedAggregator(**kwargs)
        with self.assertRaises(ValueError):
            WindowedAggregator(size=10).process(ev(-1))


if __name__ == "__main__":
    unittest.main()
