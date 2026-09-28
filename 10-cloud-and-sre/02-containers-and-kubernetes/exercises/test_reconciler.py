"""10.2 ミニ Deployment コントローラ — テスト

時刻を 1 ずつ進めながら reconcile を呼び、ローリングアップデートの不変条件を確かめます。
実行: python3 tools/check.py 10.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from reconciler import Cluster, Deployment, Pod, deletion_order, resolve_fenceposts, sync_replicaset


class TestExercise4Fenceposts(unittest.TestCase):
    def test_default_percentages(self):
        self.assertEqual(resolve_fenceposts("25%", "25%", 4), (1, 1))
        self.assertEqual(resolve_fenceposts("25%", "25%", 10), (3, 2), "surge は切り上げ、unavailable は切り捨て")
        self.assertEqual(resolve_fenceposts("25%", "25%", 1), (1, 0))
        self.assertEqual(resolve_fenceposts("50%", "50%", 3), (2, 1))
        self.assertEqual(resolve_fenceposts("100%", 0, 3), (3, 0))

    def test_absolute_numbers(self):
        self.assertEqual(resolve_fenceposts(2, 1, 10), (2, 1))
        self.assertEqual(resolve_fenceposts(1, 0, 3), (1, 0))

    def test_both_zero_becomes_one_unavailable(self):
        self.assertEqual(resolve_fenceposts(0, 0, 5), (0, 1))
        self.assertEqual(resolve_fenceposts("0%", "10%", 5), (0, 1), "10% × 5 = 0.5 は切り捨てで 0 → 1 にする")

    def test_invalid(self):
        for surge, unavailable in [(-1, 0), (0, -1), ("25", 0), ("x%", 0), (1.5, 0), (True, 0), ("-5%", 0)]:
            with self.assertRaises(ValueError, msg=(surge, unavailable)):
                resolve_fenceposts(surge, unavailable, 4)
        with self.assertRaises(ValueError):
            resolve_fenceposts(1, 1, -1)


class TestExercise5ReplicaSet(unittest.TestCase):
    def test_deletion_order(self):
        pods = [
            Pod("a", 1, created_at=0, ready_at=5),
            Pod("b", 1, created_at=2, ready_at=8),
            Pod("c", 1, created_at=9, ready_at=None),
            Pod("d", 1, created_at=7, ready_at=12),   # now=10 ではまだ Ready でない
            Pod("e", 1, created_at=3, ready_at=8),
        ]
        order = [p.name for p in deletion_order(pods, now=10)]
        self.assertEqual(order, ["c", "d", "e", "b", "a"],
                         "Ready でないもの（作成の新しい順）→ Ready になって日が浅いもの → 同時なら作成の新しいもの")

    def test_deletion_order_ties_prefer_newer_names(self):
        pods = [Pod("web-r1-001", 1, 0, 1), Pod("web-r1-003", 1, 0, 1), Pod("web-r1-002", 1, 0, 1)]
        self.assertEqual([p.name for p in deletion_order(pods, now=5)], ["web-r1-003", "web-r1-002", "web-r1-001"])

    def test_sync_creates_missing_pods(self):
        c = Cluster()
        self.assertEqual(sync_replicaset(c, 1, 3, now=0), (3, []))
        self.assertEqual([p.name for p in c.pods_of(1)], ["web-r1-001", "web-r1-002", "web-r1-003"])
        self.assertEqual(sync_replicaset(c, 1, 3, now=1), (0, []), "すでに一致していれば何もしない")

    def test_sync_deletes_unready_first(self):
        c = Cluster({1: 1, 2: None})
        sync_replicaset(c, 1, 2, now=0)
        c.startup[1] = 100                      # 以降に作る Pod はなかなか Ready にならない
        sync_replicaset(c, 1, 3, now=5)
        created, deleted = sync_replicaset(c, 1, 1, now=6)
        self.assertEqual(created, 0)
        self.assertEqual(deleted, ["web-r1-003", "web-r1-002"], "Ready でない 003 を先に、次に新しい方")
        self.assertEqual([p.name for p in c.pods_of(1)], ["web-r1-001"])

    def test_sync_touches_only_its_revision(self):
        c = Cluster()
        sync_replicaset(c, 1, 2, now=0)
        sync_replicaset(c, 2, 1, now=0)
        sync_replicaset(c, 1, 0, now=1)
        self.assertEqual([p.revision for p in c.pods.values()], [2])
        with self.assertRaises(ValueError):
            sync_replicaset(c, 1, -1, now=1)


def run(deploy, cluster, until, start=0, on_tick=None):
    for t in range(start, until):
        deploy.reconcile(t)
        if on_tick:
            on_tick(t)


class TestExercise6Deployment(unittest.TestCase):
    def test_initial_creation(self):
        c = Cluster({1: 2})
        d = Deployment(c, 4)
        d.reconcile(0)
        self.assertEqual(len(c.pods_of(1)), 4)
        self.assertEqual(d.status(0), "progressing")
        run(d, c, until=3, start=1)
        self.assertEqual(c.ready_count(2), 4)
        self.assertEqual(d.status(2), "complete")

    def test_self_healing(self):
        c = Cluster()
        d = Deployment(c, 3)
        run(d, c, until=3)
        victim = c.pods_of(1)[0].name
        c.delete_pod(victim)                    # ノード障害などで Pod が消えた
        self.assertEqual(len(c.pods), 2)
        d.reconcile(3)
        self.assertEqual(len(c.pods), 3, "次の調整で desired に戻る")
        self.assertNotIn(victim, c.pods)

    def test_rolling_update_exact_trace(self):
        c = Cluster({1: 1, 2: 2})
        d = Deployment(c, 4, max_surge=1, max_unavailable=1)
        run(d, c, until=3)
        d.rollout(2, now=3)
        trace = []
        for t in range(3, 10):
            d.reconcile(t)
            old, new = c.pods_of(1), c.pods_of(2)
            trace.append((len(old), c.ready_count(t, 1), len(new), c.ready_count(t, 2)))
        # (旧Pod数, 旧Ready数, 新Pod数, 新Ready数)
        self.assertEqual(trace, [
            (3, 3, 1, 0),   # t=3: 新を 1 増やし、旧を 1 減らす（Ready 3 = 4 - maxUnavailable）
            (3, 3, 2, 0),   # t=4: 合計 5 = 4 + maxSurge まで新を増やす。新が Ready でないので旧は減らせない
            (2, 2, 2, 1),   # t=5: 新が 1 つ Ready になったので旧を 1 減らす
            (1, 1, 3, 2),
            (1, 1, 4, 2),
            (0, 0, 4, 3),
            (0, 0, 4, 4),   # t=9: 完了
        ])
        self.assertEqual(d.status(9), "complete")

    def check_rollout(self, replicas, surge, unavailable, startup_new, horizon=120):
        c = Cluster({1: 1, 2: startup_new})
        d = Deployment(c, replicas, max_surge=surge, max_unavailable=unavailable)
        run(d, c, until=3)
        self.assertEqual(d.status(2), "complete")
        max_surge, max_unavailable = resolve_fenceposts(surge, unavailable, replicas)
        d.rollout(2, now=3)
        for t in range(3, horizon):
            d.reconcile(t)
            label = f"replicas={replicas} surge={surge} unavailable={unavailable} t={t}"
            self.assertLessEqual(len(c.pods), replicas + max_surge, "Pod の総数が replicas + maxSurge を超えた: " + label)
            self.assertGreaterEqual(c.ready_count(t), replicas - max_unavailable,
                                    "Ready な Pod が replicas - maxUnavailable を下回った: " + label)
            if d.status(t) == "complete":
                break
        else:
            self.fail(f"{horizon} までに完了しなかった: replicas={replicas} surge={surge} unavailable={unavailable}")
        self.assertEqual(len(c.pods_of(1)), 0)
        self.assertEqual(len(c.pods_of(2)), replicas)

    def test_invariants_hold_for_many_settings(self):
        settings = [
            (4, 1, 0, 2), (4, 0, 1, 2), (4, "25%", "25%", 3), (10, "25%", "25%", 3), (5, 2, 2, 1),
            (3, "100%", 0, 2), (6, 0, "50%", 4), (1, 1, 0, 2), (1, 0, 1, 2), (7, 3, 0, 1),
        ]
        for replicas, surge, unavailable, startup in settings:
            with self.subTest(replicas=replicas, surge=surge, unavailable=unavailable):
                self.check_rollout(replicas, surge, unavailable, startup)

    def test_broken_revision_stalls_without_losing_capacity(self):
        c = Cluster({1: 1, 2: None})  # 新しいリビジョンは Ready にならない（CrashLoopBackOff）
        d = Deployment(c, 4, progress_deadline=10)
        run(d, c, until=3)
        d.rollout(2, now=3)
        for t in range(3, 30):
            d.reconcile(t)
            self.assertGreaterEqual(c.ready_count(t), 3, f"t={t}: maxUnavailable(25% → 1)を超えて止めてはいけない")
            self.assertLessEqual(len(c.pods), 5)
        self.assertEqual(d.status(29), "stalled")
        self.assertEqual((len(c.pods_of(1)), len(c.pods_of(2))), (3, 2), "旧 3 + 新 2 のまま止まる")
        self.assertEqual(d.status(14), "progressing", "最後の進捗(t=4)から 10 以内はまだ progressing")

    def test_rollback_recovers(self):
        c = Cluster({1: 1, 2: None})
        d = Deployment(c, 4)
        run(d, c, until=3)
        d.rollout(2, now=3)
        run(d, c, until=20, start=3)
        d.rollout(1, now=20)                     # kubectl rollout undo に相当
        run(d, c, until=30, start=20)
        self.assertEqual(len(c.pods_of(2)), 0, "Ready にならない新しい Pod は片付けられる")
        self.assertEqual(c.ready_count(29, 1), 4)
        self.assertEqual(d.status(29), "complete")

    def test_scale_up_and_down(self):
        c = Cluster()
        d = Deployment(c, 4)
        run(d, c, until=3)
        d.replicas = 7
        run(d, c, until=6, start=3)
        self.assertEqual(len(c.pods_of(1)), 7)
        d.replicas = 2
        d.reconcile(6)
        self.assertEqual(len(c.pods_of(1)), 2)
        self.assertEqual(d.status(6), "complete")

    def test_status_progressing_during_rollout(self):
        c = Cluster({1: 1, 2: 3})
        d = Deployment(c, 2, max_surge=1, max_unavailable=0)
        run(d, c, until=3)
        d.rollout(2, now=3)
        d.reconcile(3)
        self.assertEqual(d.status(3), "progressing")


if __name__ == "__main__":
    unittest.main()
