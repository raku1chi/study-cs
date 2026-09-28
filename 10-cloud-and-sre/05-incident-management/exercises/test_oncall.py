"""10.5 公平なオンコール表 — テスト

実行: python3 tools/check.py 10.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import unittest

from oncall import (
    Engineer,
    Schedule,
    ScheduleError,
    Site,
    build_schedule,
    coverage_gaps,
    load_spread,
    slot_weight,
    utc_coverage,
)

TOKYO, DUBLIN, SF = Site("tokyo", 9), Site("dublin", 0), Site("sf", -8)


def team(site, n, **unavailable):
    return [Engineer(f"{site}-{i}", site, frozenset(unavailable.get(f"{site}-{i}", ()))) for i in range(n)]


class TestExercise3Coverage(unittest.TestCase):
    def test_utc_coverage(self):
        cov = utc_coverage([TOKYO, DUBLIN, SF])
        self.assertEqual(len(cov), 24)
        self.assertEqual(cov[0], ["sf", "tokyo"], "UTC 0 時: 東京 9 時、SF 16 時（前日）")
        self.assertEqual(cov[3], ["tokyo"])
        self.assertEqual(cov[9], ["dublin"])
        self.assertEqual(cov[17], ["sf"])
        self.assertEqual(cov[8], [], "UTC 8 時: 東京 17 時・ダブリン 8 時で誰もいない")

    def test_coverage_gaps(self):
        self.assertEqual(coverage_gaps([TOKYO, DUBLIN, SF]), [(8, 9)])
        self.assertEqual(coverage_gaps([TOKYO]), [(8, 24)], "東京だけなら UTC 8〜24 時が空く")
        self.assertEqual(coverage_gaps([]), [(0, 24)])
        wide = [Site("tokyo", 9, 8, 17), Site("dublin", 0, 8, 17), Site("sf", -8, 8, 17)]
        self.assertEqual(coverage_gaps(wide), [], "8〜17 時にすれば 24 時間を覆える")

    def test_gap_across_midnight_is_split(self):
        only_dublin = [DUBLIN]
        self.assertEqual(coverage_gaps(only_dublin), [(0, 9), (17, 24)])

    def test_invalid_site(self):
        with self.assertRaises(ValueError):
            utc_coverage([Site("x", 0, 17, 9)])
        with self.assertRaises(ValueError):
            utc_coverage([Site("x", 0, 0, 25)])


class TestExercise4Schedule(unittest.TestCase):
    def test_slot_weight(self):
        holidays = {("tokyo", 1): 3}
        self.assertEqual(slot_weight("tokyo", 0, holidays, 2.0), 7)
        self.assertEqual(slot_weight("tokyo", 1, holidays, 2.0), 4 + 3 * 2.0)
        self.assertEqual(slot_weight("dublin", 1, holidays, 2.0), 7, "祝日は拠点ごと")
        with self.assertRaises(ValueError):
            slot_weight("tokyo", 0, {("tokyo", 0): 8}, 2.0)

    def test_simple_rotation(self):
        s = build_schedule(team("tokyo", 3), weeks=6)
        self.assertIsInstance(s, Schedule)
        order = [s.assignments[(w, "tokyo")] for w in range(6)]
        self.assertEqual(order, ["tokyo-0", "tokyo-1", "tokyo-2", "tokyo-0", "tokyo-1", "tokyo-2"])
        self.assertEqual(s.load, {"tokyo-0": 14, "tokyo-1": 14, "tokyo-2": 14})
        self.assertEqual(s.warnings, [])

    def test_follow_the_sun_assigns_each_site(self):
        engineers = team("tokyo", 3) + team("dublin", 3) + team("sf", 4)
        s = build_schedule(engineers, weeks=4)
        for week in range(4):
            for site in ("dublin", "sf", "tokyo"):
                name = s.assignments[(week, site)]
                self.assertTrue(name.startswith(site + "-"), f"{name} は {site} の人ではない")
        self.assertEqual(len(s.assignments), 12)

    def test_time_off_is_respected(self):
        engineers = team("tokyo", 3, **{"tokyo-0": {0, 1}, "tokyo-1": {2}})
        s = build_schedule(engineers, weeks=5)
        for week in range(5):
            name = s.assignments[(week, "tokyo")]
            engineer = next(e for e in engineers if e.name == name)
            self.assertNotIn(week, engineer.unavailable_weeks)

    def test_no_back_to_back(self):
        rng = random.Random(505)
        for _ in range(50):
            n = rng.randint(2, 6)
            engineers = team("tokyo", n)
            s = build_schedule(engineers, weeks=rng.randint(2, 20))
            weeks = sorted(w for w, _ in s.assignments)
            for w in weeks[1:]:
                self.assertNotEqual(s.assignments[(w, "tokyo")], s.assignments[(w - 1, "tokyo")])
            self.assertEqual(s.warnings, [])

    def test_back_to_back_only_when_unavoidable(self):
        engineers = team("tokyo", 2, **{"tokyo-1": {1}})
        s = build_schedule(engineers, weeks=2)
        self.assertEqual(s.assignments[(0, "tokyo")], "tokyo-0")
        self.assertEqual(s.assignments[(1, "tokyo")], "tokyo-0", "tokyo-1 が休みなので、やむを得ず連続")
        self.assertEqual(len(s.warnings), 1)
        self.assertIn("tokyo-0", s.warnings[0])

    def test_nobody_available(self):
        engineers = team("tokyo", 2, **{"tokyo-0": {3}, "tokyo-1": {3}})
        with self.assertRaises(ScheduleError):
            build_schedule(engineers, weeks=4)

    def test_duplicate_names(self):
        with self.assertRaises(ValueError):
            build_schedule([Engineer("a", "tokyo"), Engineer("a", "dublin")], weeks=1)

    def test_holiday_weeks_count_more(self):
        # 第 1 週はゴールデンウィーク（5 日が祝日）。その週の担当者 tokyo-1 は負荷が重いので、次の番が後回しになる
        holidays = {("tokyo", 1): 5}
        s = build_schedule(team("tokyo", 3), weeks=6, holidays=holidays)
        order = [s.assignments[(w, "tokyo")] for w in range(6)]
        self.assertEqual(order, ["tokyo-0", "tokyo-1", "tokyo-2", "tokyo-0", "tokyo-2", "tokyo-1"],
                         "単純な輪番なら第 4 週は tokyo-1 だが、負荷の小さい tokyo-2 が先に入る")
        self.assertEqual(s.load, {"tokyo-0": 14, "tokyo-1": 2 + 5 * 2.0 + 7, "tokyo-2": 14})

    def test_holiday_weight_reduces_shift_count_in_larger_team(self):
        s = build_schedule(team("tokyo", 4), weeks=9, holidays={("tokyo", 1): 5})
        counts = {name: sum(1 for n in s.assignments.values() if n == name) for name in s.load}
        self.assertEqual(s.assignments[(1, "tokyo")], "tokyo-1")
        self.assertEqual(counts, {"tokyo-0": 3, "tokyo-1": 2, "tokyo-2": 2, "tokyo-3": 2})

    def test_fairness_bound(self):
        rng = random.Random(1234)
        for _ in range(200):
            n = rng.randint(3, 7)
            weeks = rng.randint(4, 30)
            holidays = {("tokyo", w): rng.choice([0, 0, 0, 0, 1, 2, 3, 5]) for w in range(weeks)}
            engineers = team("tokyo", n)
            s = build_schedule(engineers, weeks, holidays=holidays)
            max_weight = max(slot_weight("tokyo", w, holidays, 2.0) for w in range(weeks))
            # 貪欲法なので最適ではないが、大きくは偏らない（連続禁止のため最小の人を選べない週がある）
            self.assertLessEqual(load_spread(s, engineers)["tokyo"], 2 * max_weight,
                                 "負荷の差は、1 回の担当の最大の重みの 2 倍を超えない")

    def test_deterministic(self):
        engineers = team("tokyo", 4) + team("sf", 3)
        holidays = {("tokyo", 2): 2, ("sf", 3): 1}
        a = build_schedule(engineers, 12, holidays=holidays)
        b = build_schedule(list(engineers), 12, holidays=dict(holidays))
        self.assertEqual(a.assignments, b.assignments)

    def test_load_spread(self):
        engineers = team("tokyo", 3) + team("sf", 2)
        s = build_schedule(engineers, weeks=4)
        self.assertEqual(load_spread(s, engineers), {"sf": 0.0, "tokyo": 7.0})


if __name__ == "__main__":
    unittest.main()
