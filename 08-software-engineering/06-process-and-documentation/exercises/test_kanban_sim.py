"""8.6 演習2 — カンバンのシミュレーターのテスト

実行: python3 tools/check.py 8.6   （またはこのディレクトリで python3 -m unittest -v test_kanban_sim）
"""
import unittest

from kanban_sim import Completed, Item, SimulationResult, Stage, generate_items, simulate

# 過負荷の実験: 1 日 1 件ずつ到着するが、ボトルネックの「開発」は 2 人で 1 件 3〜5 人日（1 日約 0.5 件）
WORK = [(1, 2), (3, 5), (1, 3)]
UNLIMITED = [Stage("分析", 2), Stage("開発", 2), Stage("テスト", 2)]
LIMITED = [Stage("分析", 2, wip_limit=2), Stage("開発", 2, wip_limit=3), Stage("テスト", 2, wip_limit=2)]


def overload_items():
    return generate_items(120, WORK, arrivals_per_day=1, seed=1)


class TestSmallBoards(unittest.TestCase):
    def test_single_item_single_stage(self):
        result = simulate([Stage("開発", 1)], [Item("a", 0, (3,))], until_empty=True)
        self.assertIsInstance(result, SimulationResult)
        self.assertEqual(result.completed, (Completed("a", 0, 3),))
        self.assertEqual(result.completed[0].lead_time, 3)
        self.assertEqual((result.days, result.wip_by_day), (4, (1, 1, 1, 0)))
        self.assertAlmostEqual(result.throughput, 0.25)
        self.assertAlmostEqual(result.average_wip, 0.75)
        self.assertAlmostEqual(result.average_lead_time, 3.0)

    def test_items_move_to_the_next_stage_on_the_following_day(self):
        result = simulate([Stage("a", 1), Stage("b", 1)], [Item("x", 0, (1, 1))], until_empty=True)
        self.assertEqual(result.completed, (Completed("x", 0, 2),))
        self.assertEqual(result.wip_by_day, (1, 1, 0))

    def test_workers_limit_parallel_work(self):
        one = simulate([Stage("a", 1)], [Item("a", 0, (2,)), Item("b", 0, (2,))], until_empty=True)
        self.assertEqual(one.completed, (Completed("a", 0, 2), Completed("b", 0, 4)))
        self.assertEqual(one.wip_by_day, (2, 2, 1, 1, 0))
        two = simulate([Stage("a", 2)], [Item("a", 0, (2,)), Item("b", 0, (2,))], until_empty=True)
        self.assertEqual(two.completed, (Completed("a", 0, 2), Completed("b", 0, 2)))

    def test_wip_limit_delays_start_and_shortens_lead_time(self):
        result = simulate([Stage("a", 1, wip_limit=1)], [Item("a", 0, (2,)), Item("b", 0, (2,))], until_empty=True)
        # b はバックログで待ってから開始するので、開始から完了までは 2 日（WIP 制限なしなら 4 日）
        self.assertEqual(result.completed, (Completed("a", 0, 2), Completed("b", 2, 4)))
        self.assertEqual(result.wip_by_day, (1, 1, 1, 1, 0))

    def test_downstream_limit_blocks_upstream(self):
        stages = [Stage("a", 1, wip_limit=1), Stage("b", 1, wip_limit=1)]
        result = simulate(stages, [Item("x", 0, (1, 3)), Item("y", 0, (1, 3))], until_empty=True)
        # y は工程 a の作業を 1 日目に終えるが、工程 b が空くまで（4 日目まで）a に留まる
        self.assertEqual(result.completed, (Completed("x", 0, 4), Completed("y", 1, 7)))
        self.assertEqual(result.wip_by_day, (1, 2, 2, 2, 1, 1, 1, 0))

    def test_fixed_number_of_days(self):
        result = simulate([Stage("a", 1)], [Item("a", 0, (1,)), Item("b", 5, (1,))], days=3)
        self.assertEqual(result.days, 3)
        self.assertEqual(result.completed, (Completed("a", 0, 1),), "3 日目までに到着しない b は含まれない")
        self.assertEqual(result.wip_by_day, (1, 0, 0))

    def test_empty_item_list(self):
        result = simulate([Stage("a", 1)], [], until_empty=True)
        self.assertEqual((result.completed, result.average_lead_time), ((), 0.0))

    def test_invalid_arguments(self):
        stage = [Stage("a", 1)]
        bad_calls = [
            lambda: simulate([], [], until_empty=True),
            lambda: simulate([Stage("a", 0)], [], until_empty=True),
            lambda: simulate([Stage("a", 1, wip_limit=0)], [], until_empty=True),
            lambda: simulate(stage, [Item("a", 0, (1, 1))], until_empty=True),
            lambda: simulate(stage, [Item("a", 0, (0,))], until_empty=True),
            lambda: simulate(stage, [Item("a", -1, (1,))], until_empty=True),
            lambda: simulate(stage, [Item("a", 0, (1,)), Item("a", 1, (1,))], until_empty=True),
            lambda: simulate(stage, [], days=5, until_empty=True),
            lambda: simulate(stage, []),
            lambda: simulate(stage, [], days=0),
        ]
        for i, call in enumerate(bad_calls):
            with self.assertRaises(ValueError, msg=f"{i} 番目の呼び出し"):
                call()


class TestFlow(unittest.TestCase):
    def test_littles_law_holds_exactly_when_the_board_empties(self):
        for stages in (UNLIMITED, LIMITED):
            result = simulate(stages, overload_items(), until_empty=True)
            self.assertEqual(len(result.completed), 120)
            self.assertAlmostEqual(result.average_wip, result.throughput * result.average_lead_time, places=9)
            self.assertEqual(sum(result.wip_by_day), sum(c.lead_time for c in result.completed),
                             "毎日数えた WIP の合計は、全項目のリードタイムの合計に等しい")

    def test_wip_limits_cut_lead_time_without_hurting_throughput(self):
        free = simulate(UNLIMITED, overload_items(), until_empty=True)
        limited = simulate(LIMITED, overload_items(), until_empty=True)
        self.assertEqual(free.days, limited.days, "ボトルネックが同じなので、全部終わる日は同じ")
        self.assertAlmostEqual(free.throughput, limited.throughput)
        self.assertLess(limited.average_lead_time, free.average_lead_time / 3,
                        f"WIP 制限でリードタイムが大きく縮むはず: {limited.average_lead_time:.1f} 日 vs {free.average_lead_time:.1f} 日")
        self.assertLess(max(limited.wip_by_day), 8)
        self.assertGreater(max(free.wip_by_day), 40)

    def test_littles_law_needs_a_stable_system(self):
        # 100 日で打ち切ると、WIP 制限のない過負荷のボードでは仕掛かりが増え続けていて、関係が大きく崩れる
        free = simulate(UNLIMITED, overload_items(), days=100)
        self.assertGreater(free.average_wip, 1.5 * free.throughput * free.average_lead_time)
        # WIP を制限したボードは安定しているので、打ち切っても近い値になる
        limited = simulate(LIMITED, overload_items(), days=100)
        ratio = limited.average_wip / (limited.throughput * limited.average_lead_time)
        self.assertTrue(0.85 <= ratio <= 1.15, ratio)

    def test_completed_items_are_in_completion_order(self):
        result = simulate(LIMITED, overload_items(), until_empty=True)
        finish_days = [c.finish_day for c in result.completed]
        self.assertEqual(finish_days, sorted(finish_days))
        self.assertTrue(all(c.lead_time >= 5 for c in result.completed),
                        "リードタイムは作業量の合計（最低 1 + 3 + 1 = 5 人日）より短くならない")


if __name__ == "__main__":
    unittest.main()
