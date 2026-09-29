"""4.4 並行処理と同期 — interleave のテスト

実行: python3 tools/check.py 4.4   （またはこのディレクトリで python3 -m unittest -v test_interleave）

本物のスレッドは使いません。すべてのインターリーブを網羅的に数えるので、結果は毎回同じです。
"""
import unittest
from collections import Counter

from interleave import ExploreResult, count_interleavings, explore, increment_program

LOST_UPDATE = [("read", "x"), ("inc",), ("write", "x")]


class TestExercise5CountInterleavings(unittest.TestCase):
    def test_values(self):
        self.assertEqual(count_interleavings([3, 3]), 20)
        self.assertEqual(count_interleavings([2, 2, 2]), 90)
        self.assertEqual(count_interleavings([5]), 1)
        self.assertEqual(count_interleavings([]), 1)
        self.assertEqual(count_interleavings([0, 4]), 1)
        self.assertEqual(count_interleavings([10, 10]), 184756)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            count_interleavings([3, -1])


class TestExercise5Explore(unittest.TestCase):
    def test_single_thread(self):
        r = explore([LOST_UPDATE], {"x": 41})
        self.assertEqual(r, ExploreResult(Counter({(("x", 42),): 1}), 0, 1))

    def test_lost_update_with_two_threads(self):
        r = explore([LOST_UPDATE, LOST_UPDATE], {"x": 0})
        self.assertEqual(r.schedules, 20, "3 命令 × 2 スレッドのインターリーブは 20 通り")
        self.assertEqual(r.deadlocks, 0)
        self.assertEqual(r.outcomes, Counter({(("x", 1),): 18, (("x", 2),): 2}),
                         "正しく 2 になるのは、一方がもう一方の完了後に読む 2 通りだけ")

    def test_lock_makes_the_outcome_unique(self):
        prog = increment_program("x", lock="L")
        r = explore([prog, prog], {"x": 0})
        self.assertEqual(r.outcomes, Counter({(("x", 2),): 2}))
        self.assertEqual((r.schedules, r.deadlocks), (2, 0), "ロックがあると、実行できる並びは 2 通りだけ")

    def test_three_threads(self):
        r = explore([LOST_UPDATE] * 3, {"x": 0})
        self.assertEqual(r.schedules, count_interleavings([3, 3, 3]))
        self.assertEqual(set(r.outcomes), {(("x", 1),), (("x", 2),), (("x", 3),)})
        self.assertEqual(r.outcomes[(("x", 3),)], 6, "正しい結果になるのは 3! = 6 通りの逐次実行だけ")
        locked = increment_program("x", lock="L")
        r = explore([locked] * 3, {"x": 0})
        self.assertEqual(r.outcomes, Counter({(("x", 3),): 6}))

    def test_opposite_lock_order_deadlocks(self):
        t1 = [("lock", "A"), ("lock", "B"), ("unlock", "B"), ("unlock", "A")]
        t2 = [("lock", "B"), ("lock", "A"), ("unlock", "A"), ("unlock", "B")]
        r = explore([t1, t2], {})
        self.assertEqual(r.deadlocks, 2, "T1 が A を、T2 が B を取った時点で、互いに相手を待つ")
        self.assertEqual(r.schedules, 6)
        self.assertEqual(r.outcomes, Counter({(): 4}))

    def test_same_lock_order_never_deadlocks(self):
        t = [("lock", "A"), ("lock", "B"), ("unlock", "B"), ("unlock", "A")]
        r = explore([t, list(t)], {})
        self.assertEqual((r.deadlocks, r.schedules), (0, 2))

    def test_add_and_multiple_variables(self):
        t1 = [("read", "x"), ("add", 10), ("write", "x")]
        t2 = [("read", "y"), ("add", -1), ("write", "y"), ("read", "x"), ("write", "y")]
        r = explore([t1, t2], {"x": 1, "y": 5})
        self.assertEqual(r.schedules, count_interleavings([3, 5]))
        # y は、t2 が x を読んだ時点の x の値（1 または 11）になる
        self.assertEqual(set(r.outcomes), {(("x", 11), ("y", 1)), (("x", 11), ("y", 11))})

    def test_thread_holding_a_lock_at_exit_blocks_others(self):
        t1 = [("lock", "L")]  # 解放し忘れ
        t2 = [("lock", "L"), ("unlock", "L")]
        r = explore([t1, t2], {})
        self.assertEqual(r.deadlocks, 1, "t1 が先に取ると、t2 は永遠に待つ")
        self.assertEqual(r.outcomes, Counter({(): 1}))

    def test_invalid_programs(self):
        bad = [
            [[("jump", 3)]],                 # 不明な命令
            [[("read",)]],                   # 引数の数が違う
            [[("read", "nope")]],            # 初期値のない変数
            [[("add", "1")]],                # add の引数が整数でない
        ]
        for threads in bad:
            with self.assertRaises(ValueError, msg=str(threads)):
                explore(threads, {"x": 0})
        with self.assertRaises(ValueError, msg="持っていないロックの解放"):
            explore([[("unlock", "L")]], {})


if __name__ == "__main__":
    unittest.main()
