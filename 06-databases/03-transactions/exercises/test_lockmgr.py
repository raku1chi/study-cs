"""6.3 演習2（ロックマネージャとデッドロック検出）のテスト

実行: python3 tools/check.py 6.3   （またはこのディレクトリで python3 -m unittest -v test_lockmgr）
"""
import random
import unittest

from lockmgr import LockError, LockManager


class TestCompatibilityAndQueues(unittest.TestCase):
    def test_shared_locks_are_compatible(self):
        lm = LockManager()
        self.assertEqual(lm.acquire(1, "A", "S"), "granted")
        self.assertEqual(lm.acquire(2, "A", "S"), "granted")
        self.assertEqual(lm.holders("A"), {1: "S", 2: "S"})

    def test_exclusive_lock_conflicts(self):
        lm = LockManager()
        self.assertEqual(lm.acquire(1, "A", "X"), "granted")
        self.assertEqual(lm.acquire(2, "A", "S"), "waiting")
        self.assertEqual(lm.acquire(3, "A", "X"), "waiting")
        self.assertEqual(lm.status(2), "waiting")
        self.assertEqual(lm.waiters("A"), [(2, "S"), (3, "X")])
        self.assertEqual(lm.holders("A"), {1: "X"})

    def test_different_resources_do_not_conflict(self):
        lm = LockManager()
        self.assertEqual(lm.acquire(1, "A", "X"), "granted")
        self.assertEqual(lm.acquire(2, "B", "X"), "granted")

    def test_reacquire_and_weaker_request(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        self.assertEqual(lm.acquire(1, "A", "X"), "granted")
        self.assertEqual(lm.acquire(1, "A", "S"), "granted", "X を持っていれば S も満たされる")
        self.assertEqual(lm.holders("A"), {1: "X"})

    def test_fifo_prevents_starvation_of_writers(self):
        lm = LockManager()
        lm.acquire(1, "A", "S")
        self.assertEqual(lm.acquire(2, "A", "X"), "waiting")
        # T3 の S は T1 の S とは両立するが、先に待っている T2 の X を追い越してはいけない
        self.assertEqual(lm.acquire(3, "A", "S"), "waiting")
        self.assertEqual(lm.release_all(1), [2])
        self.assertEqual(lm.holders("A"), {2: "X"})
        self.assertEqual(lm.release_all(2), [3])

    def test_release_grants_all_compatible_waiters_in_order(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        for t in (2, 3, 4):
            lm.acquire(t, "A", "S")
        lm.acquire(5, "A", "X")
        lm.acquire(6, "A", "S")
        self.assertEqual(lm.release_all(1), [2, 3, 4], "先頭から両立する S をまとめて与え、X で止まる")
        self.assertEqual(lm.waiters("A"), [(5, "X"), (6, "S")])
        self.assertEqual(lm.status(3), "running")

    def test_release_all_releases_every_resource(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(1, "B", "S")
        lm.acquire(2, "B", "X")
        lm.acquire(3, "A", "S")
        self.assertEqual(lm.release_all(1), [3, 2], "資源名の昇順（A → B）に待ちを処理する")
        self.assertEqual(lm.holders("A"), {3: "S"})
        self.assertEqual(lm.holders("B"), {2: "X"})
        self.assertEqual(lm.status(1), "finished")

    def test_release_all_cancels_pending_request(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(2, "A", "X")
        lm.acquire(3, "A", "X")
        self.assertEqual(lm.release_all(2), [], "待ち中のトランザクションの終了: 要求を取り消す")
        self.assertEqual(lm.waiters("A"), [(3, "X")])
        self.assertEqual(lm.release_all(1), [3])

    def test_upgrade_when_sole_holder(self):
        lm = LockManager()
        lm.acquire(1, "A", "S")
        self.assertEqual(lm.acquire(1, "A", "X"), "granted")
        self.assertEqual(lm.holders("A"), {1: "X"})

    def test_upgrade_waits_for_other_readers_and_goes_first(self):
        lm = LockManager()
        lm.acquire(1, "A", "S")
        lm.acquire(2, "A", "S")
        lm.acquire(3, "A", "X")                      # 普通の X 要求が先に待っている
        self.assertEqual(lm.acquire(1, "A", "X"), "waiting")
        self.assertEqual(lm.waiters("A")[0], (1, "X"), "昇格要求は待ち行列の先頭に入る")
        self.assertEqual(lm.release_all(2), [1])
        self.assertEqual(lm.holders("A"), {1: "X"})
        self.assertEqual(lm.waiters("A"), [(3, "X")])

    def test_errors(self):
        lm = LockManager()
        with self.assertRaises(ValueError):
            lm.acquire(1, "A", "IX")
        lm.acquire(1, "A", "X")
        lm.acquire(2, "A", "X")
        with self.assertRaises(LockError, msg="待ち中は新しい要求を出せない"):
            lm.acquire(2, "B", "S")
        lm.release_all(1)
        lm.release_all(2)
        with self.assertRaises(LockError, msg="終了したトランザクションは新しいロックを取れない（2PL）"):
            lm.acquire(1, "C", "S")
        self.assertEqual(lm.release_all(1), [])


class TestWaitForGraph(unittest.TestCase):
    def test_edges_to_holders_and_earlier_waiters(self):
        lm = LockManager()
        lm.acquire(1, "A", "S")
        lm.acquire(2, "A", "X")   # 2 は 1（S 保持）を待つ
        lm.acquire(3, "A", "S")   # 3 は 1 とは両立するが、前にいる 2（X 要求）を待つ
        self.assertEqual(lm.wait_for_graph(), {2: {1}, 3: {2}})

    def test_no_edge_between_compatible_waiters(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(2, "A", "S")
        lm.acquire(3, "A", "S")   # 前の 2 も S なので、3 は 2 を待たない
        self.assertEqual(lm.wait_for_graph(), {2: {1}, 3: {1}})

    def test_find_cycle_on_chain_is_none(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(2, "A", "X")
        lm.acquire(3, "A", "X")
        self.assertIsNone(lm.find_cycle(3))
        self.assertIsNone(lm.find_cycle(1))


class TestDeadlocks(unittest.TestCase):
    def test_two_transactions_requester_is_youngest(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(2, "B", "X")
        self.assertEqual(lm.acquire(1, "B", "X"), "waiting")
        self.assertEqual(lm.acquire(2, "A", "X"), "aborted", "閉路 {1, 2} の最も若い 2（要求者）が犠牲になる")
        self.assertEqual(lm.aborted, [2])
        self.assertEqual(lm.status(2), "aborted")
        self.assertEqual(lm.holders("B"), {1: "X"}, "犠牲者のロックが解放され、T1 が B を得る")
        self.assertEqual(lm.status(1), "running")
        self.assertEqual(lm.wait_for_graph(), {})
        with self.assertRaises(LockError):
            lm.acquire(2, "C", "S")

    def test_two_transactions_other_is_youngest(self):
        lm = LockManager()
        lm.acquire(2, "A", "X")
        lm.acquire(1, "B", "X")
        self.assertEqual(lm.acquire(2, "B", "X"), "waiting")
        self.assertEqual(lm.acquire(1, "A", "X"), "granted", "犠牲は若い T2。T2 が解放した A を T1 が得る")
        self.assertEqual(lm.aborted, [2])
        self.assertEqual(lm.holders("A"), {1: "X"})
        self.assertEqual(lm.waiters("B"), [], "犠牲者の待ち要求も取り除かれる")

    def test_three_way_cycle(self):
        lm = LockManager()
        lm.acquire(1, "A", "X")
        lm.acquire(2, "B", "X")
        lm.acquire(3, "C", "X")
        self.assertEqual(lm.acquire(1, "B", "X"), "waiting")
        self.assertEqual(lm.acquire(2, "C", "X"), "waiting")
        self.assertEqual(lm.find_cycle(1), None)
        self.assertEqual(lm.acquire(3, "A", "X"), "aborted")
        self.assertEqual(lm.aborted, [3])
        self.assertEqual(lm.holders("C"), {2: "X"})
        self.assertEqual(lm.status(1), "waiting", "T1 はまだ T2 を待っている（デッドロックではない）")
        self.assertEqual(lm.release_all(2), [1])

    def test_find_cycle_order(self):
        lm = LockManager()
        lm.acquire(3, "A", "X")
        lm.acquire(5, "B", "X")
        lm.acquire(7, "C", "X")
        lm.acquire(5, "A", "X")        # 5 → 3
        lm.acquire(7, "B", "X")        # 7 → 5
        # ここで 3 が C を要求すると 3 → 7 → 5 → 3 の閉路ができる（犠牲は 7）
        self.assertEqual(lm.acquire(3, "C", "X"), "granted")
        self.assertEqual(lm.aborted, [7])
        self.assertEqual(lm.holders("C"), {3: "X"})

    def test_conversion_deadlock(self):
        # 2 人が S を持ったまま、そろって X に昇格しようとする（典型的なデッドロック）
        lm = LockManager()
        lm.acquire(1, "A", "S")
        lm.acquire(2, "A", "S")
        self.assertEqual(lm.acquire(1, "A", "X"), "waiting")
        self.assertEqual(lm.acquire(2, "A", "X"), "aborted")
        self.assertEqual(lm.holders("A"), {1: "X"}, "T2 の S が解放され、T1 の昇格が通る")

    def test_waiter_edge_deadlock(self):
        # 保持者ではなく「前に並んでいる要求」を待つことで生じる閉路
        lm = LockManager()
        lm.acquire(1, "A", "S")
        lm.acquire(2, "B", "X")
        self.assertEqual(lm.acquire(2, "A", "X"), "waiting")  # 2 → 1
        self.assertEqual(lm.acquire(3, "A", "S"), "waiting")  # 3 → 2（前にいる X 要求）
        lm.release_all(1)                                     # 2 が A の X を得る。3 は 2 を待つ
        self.assertEqual(lm.holders("A"), {2: "X"})
        self.assertEqual(lm.wait_for_graph(), {3: {2}})
        self.assertEqual(lm.acquire(4, "C", "X"), "granted")
        self.assertEqual(lm.acquire(2, "C", "S"), "waiting")  # 2 → 4
        # 4 → 2（A の X の保持者）。前に並ぶ 3 の S 要求とは両立するので、3 への辺はない
        self.assertEqual(lm.acquire(4, "A", "S"), "aborted", "閉路 4 → 2 → 4 の最も若い 4 が犠牲になる")
        self.assertEqual(lm.holders("C"), {2: "S"})


class TestRandomSchedules(unittest.TestCase):
    def test_invariants_hold_on_random_schedules(self):
        rng = random.Random(63)
        resources = "ABC"
        for trial in range(150):
            lm = LockManager()
            for _ in range(40):
                txn = rng.randrange(1, 7)
                if lm.status(txn) != "running":
                    continue
                if rng.random() < 0.2:
                    lm.release_all(txn)
                else:
                    result = lm.acquire(txn, rng.choice(resources), rng.choice("SX"))
                    self.assertIn(result, ("granted", "waiting", "aborted"))
                # 不変条件 1: X の保持者がいれば、保持者はその 1 人だけ
                for r in resources:
                    modes = list(lm.holders(r).values())
                    if "X" in modes:
                        self.assertEqual(len(modes), 1, f"trial={trial} {r}: {lm.holders(r)}")
                # 不変条件 2: 待ち中のトランザクションは、ちょうど 1 つの待ち行列にいる
                queued = [t for r in resources for t, _ in lm.waiters(r)]
                self.assertEqual(len(queued), len(set(queued)), f"trial={trial}")
                for t in range(1, 7):
                    self.assertEqual(lm.status(t) == "waiting", t in queued, f"trial={trial} txn={t}")
                # 不変条件 3: デッドロックは残っていない
                for t in set(queued):
                    self.assertIsNone(lm.find_cycle(t), f"trial={trial}: 閉路が残っている {lm.wait_for_graph()}")
                # 不変条件 4: 中断・終了したトランザクションはロックを持たない
                for t in range(1, 7):
                    if lm.status(t) in ("aborted", "finished"):
                        self.assertFalse(any(t in lm.holders(r) for r in resources), f"trial={trial} txn={t}")


if __name__ == "__main__":
    unittest.main()
