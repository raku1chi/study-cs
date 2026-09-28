"""7.4 合意と協調 — 2 相コミットのテスト

実行: python3 tools/check.py 7.4   （またはこのディレクトリで python3 -m unittest -v test_twopc）
"""
import random
import unittest

from twopc import (
    ABORTED,
    COMMITTED,
    INIT,
    PREPARED,
    AtomicityViolation,
    Coordinator,
    Participant,
    cooperative_termination,
    in_doubt,
    is_atomic,
)


def make(*votes: bool) -> list[Participant]:
    return [Participant(f"p{i}", vote=v) for i, v in enumerate(votes)]


class TestExercise1Participant(unittest.TestCase):
    def test_yes_vote_logs_prepared_before_answering(self):
        p = Participant("inventory")
        self.assertEqual((p.state, p.log, p.up), (INIT, [], True))
        self.assertIs(p.prepare(), True)
        self.assertEqual((p.state, p.log), (PREPARED, ["PREPARED"]))
        self.assertIs(p.prepare(), True, "重複した PREPARE には同じ答え")
        self.assertEqual(p.log, ["PREPARED"])

    def test_no_vote_aborts_unilaterally(self):
        p = Participant("payment", vote=False)
        self.assertIs(p.prepare(), False)
        self.assertEqual((p.state, p.log), (ABORTED, ["ABORT"]))

    def test_commit_and_abort_are_idempotent(self):
        p = Participant("a")
        p.prepare()
        self.assertTrue(p.commit())
        self.assertTrue(p.commit())
        self.assertEqual(p.log, ["PREPARED", "COMMIT"])
        q = Participant("b")
        q.prepare()
        self.assertTrue(q.abort())
        self.assertTrue(q.abort())
        self.assertEqual(q.log, ["PREPARED", "ABORT"])

    def test_contradictory_decisions_raise(self):
        p = Participant("a")
        p.prepare()
        p.commit()
        with self.assertRaises(AtomicityViolation):
            p.abort()
        q = Participant("b", vote=False)
        q.prepare()
        with self.assertRaises(AtomicityViolation):
            q.commit()

    def test_down_participant_does_not_respond(self):
        p = Participant("a")
        p.crash()
        self.assertFalse(p.up)
        self.assertIsNone(p.prepare())
        self.assertFalse(p.commit())
        self.assertFalse(p.abort())

    def test_crash_before_vote(self):
        p = Participant("a", crash_before_vote=True)
        self.assertIsNone(p.prepare())
        self.assertFalse(p.up)

    def test_recover_restores_state_from_log(self):
        p = Participant("a")
        p.prepare()
        p.crash()
        p.recover()
        self.assertEqual(p.state, PREPARED, "YES と約束した後は、復帰しても結果を待つしかない")
        q = Participant("b")
        q.prepare()
        q.commit()
        q.crash()
        q.recover()
        self.assertEqual(q.state, COMMITTED)
        r = Participant("c")
        r.crash()
        r.recover()
        self.assertEqual((r.state, r.log), (ABORTED, ["ABORT"]), "約束前に落ちたなら一方的にアボートしてよい")


class TestExercise2Coordinator(unittest.TestCase):
    def test_all_yes_commits(self):
        ps = make(True, True, True)
        c = Coordinator(ps)
        self.assertEqual(c.run(), COMMITTED)
        self.assertEqual([p.state for p in ps], [COMMITTED] * 3)
        self.assertEqual(c.log, ["COMMIT"])
        self.assertEqual(c.decision(), "COMMIT")

    def test_one_no_aborts_everyone(self):
        ps = make(True, False, True)
        self.assertEqual(Coordinator(ps).run(), ABORTED)
        self.assertEqual([p.state for p in ps], [ABORTED] * 3)
        self.assertEqual(in_doubt(ps), [])

    def test_participant_crash_before_vote_means_abort(self):
        ps = make(True, True)
        ps.append(Participant("p2", crash_before_vote=True))
        self.assertEqual(Coordinator(ps).run(), ABORTED, "応答がない参加者はタイムアウト = NO とみなす")
        ps[2].recover()
        self.assertEqual(ps[2].state, ABORTED)
        self.assertTrue(is_atomic(ps))

    def test_invalid_crash_point(self):
        with self.assertRaises(ValueError):
            Coordinator(make(True), crash_at="before_everything")


class TestExercise3Blocking(unittest.TestCase):
    def test_coordinator_crash_after_prepare_blocks_participants(self):
        ps = make(True, True, True)
        c = Coordinator(ps, crash_at="after_prepare")
        self.assertEqual(c.run(), "CRASHED")
        self.assertFalse(c.up)
        self.assertIsNone(c.decision())
        self.assertEqual(in_doubt(ps), ["p0", "p1", "p2"], "全員が YES と約束したまま結果を知らない")
        self.assertIsNone(cooperative_termination(ps), "参加者どうしで話しても決められない = ブロック")
        self.assertEqual([p.state for p in ps], [PREPARED] * 3)
        self.assertEqual(c.recover(), ABORTED, "決定の記録がなければアボートで確定する（presumed abort）")
        self.assertEqual([p.state for p in ps], [ABORTED] * 3)
        self.assertEqual(in_doubt(ps), [])

    def test_coordinator_crash_after_prepare_with_a_no_vote_can_be_resolved(self):
        ps = make(True, False, True)
        Coordinator(ps, crash_at="after_prepare").run()
        self.assertEqual(in_doubt(ps), ["p0", "p2"])
        self.assertEqual(cooperative_termination(ps), "ABORT", "NO と答えた参加者がいれば COMMIT はありえない")
        self.assertEqual([p.state for p in ps], [ABORTED] * 3)

    def test_crash_after_decision_logged(self):
        ps = make(True, True, True)
        c = Coordinator(ps, crash_at="after_decision")
        self.assertEqual(c.run(), "CRASHED")
        self.assertEqual(c.log, ["COMMIT"], "決定は記録済み（コミットポイントを過ぎた）")
        self.assertEqual(in_doubt(ps), ["p0", "p1", "p2"])
        self.assertIsNone(cooperative_termination(ps))
        self.assertEqual(c.recover(), COMMITTED, "復帰したら記録どおり COMMIT を再送する")
        self.assertEqual([p.state for p in ps], [COMMITTED] * 3)

    def test_crash_during_decision_resolved_by_peers(self):
        ps = make(True, True, True)
        c = Coordinator(ps, crash_at="during_decision")
        self.assertEqual(c.run(), "CRASHED")
        self.assertEqual([p.state for p in ps], [COMMITTED, PREPARED, PREPARED])
        self.assertTrue(is_atomic(ps), "COMMIT と ABORT が混在していなければ原子性は保たれている")
        self.assertEqual(cooperative_termination(ps), "COMMIT", "p0 がコミット済みなので決定を知っている")
        self.assertEqual([p.state for p in ps], [COMMITTED] * 3)
        self.assertEqual(c.recover(), COMMITTED)

    def test_participant_down_during_phase2_learns_on_recovery(self):
        ps = make(True, True, True)
        c = Coordinator(ps, crash_at="after_decision")
        c.run()
        ps[1].crash()
        c.recover()
        self.assertEqual([ps[0].state, ps[2].state], [COMMITTED, COMMITTED])
        self.assertEqual(in_doubt(ps), ["p1"], "停止中の参加者はまだ結果を知らない")
        ps[1].recover()
        self.assertEqual(ps[1].state, PREPARED)
        c.finish()
        self.assertEqual(ps[1].state, COMMITTED)

    def test_is_atomic_detects_mixed_outcomes(self):
        a, b = Participant("a"), Participant("b")
        a.prepare()
        b.prepare()
        a.commit()
        b.abort()
        self.assertFalse(is_atomic([a, b]))

    def test_randomized_scenarios_are_always_atomic(self):
        rng = random.Random(7)
        crash_points = [None, "after_prepare", "after_decision", "during_decision"]
        for trial in range(300):
            ps = [
                Participant(f"p{i}", vote=rng.random() < 0.85, crash_before_vote=rng.random() < 0.05)
                for i in range(rng.randrange(1, 6))
            ]
            c = Coordinator(ps, crash_at=rng.choice(crash_points))
            c.run()
            for p in ps:
                if p.up and rng.random() < 0.2:
                    p.crash()
            self.assertTrue(is_atomic(ps), f"trial={trial}")
            if rng.random() < 0.5:
                cooperative_termination(ps)
                self.assertTrue(is_atomic(ps), f"trial={trial}")
            for p in ps:
                if not p.up:
                    p.recover()
            c.recover()
            self.assertTrue(is_atomic(ps), f"trial={trial}")
            self.assertEqual(in_doubt(ps), [], "全員が復帰すれば、ブロックは解消する")
            all_yes = all(p.vote and not p.crash_before_vote for p in ps)
            if not all_yes:
                self.assertEqual({p.state for p in ps}, {ABORTED}, "1 人でも YES でなければコミットしない")


if __name__ == "__main__":
    unittest.main()
