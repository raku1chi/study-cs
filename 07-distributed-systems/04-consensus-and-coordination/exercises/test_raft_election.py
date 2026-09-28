"""7.4 合意と協調 — Raft のリーダー選出（とログ複製）のテスト

実行: python3 tools/check.py 7.4   （またはこのディレクトリで python3 -m unittest -v test_raft_election）

シミュレータは 1 ms 刻みの決定的な離散時間で動くので、実時間は待ちません。
発展課題（ログ複製）のテストは、raft_election.ENABLE_LOG_REPLICATION が True のときだけ実行されます。
"""
import random
import unittest

import raft_election
from raft_election import (
    CANDIDATE,
    FOLLOWER,
    LEADER,
    AppendEntries,
    AppendEntriesReply,
    LogEntry,
    RaftCluster,
    RequestVote,
    RequestVoteReply,
)

REPLICATION = raft_election.ENABLE_LOG_REPLICATION
SKIP_MSG = "発展課題: ENABLE_LOG_REPLICATION = True にすると実行されます"


def assert_election_safety(test: unittest.TestCase, cluster: RaftCluster) -> None:
    for term, leaders in cluster.leader_history.items():
        test.assertLessEqual(len(leaders), 1, f"任期 {term} にリーダーが複数: {sorted(leaders)}")


def elect(test: unittest.TestCase, cluster: RaftCluster, timeout: int = 3000) -> int:
    ok = cluster.run_until(lambda: len(cluster.leaders()) == 1, timeout)
    test.assertTrue(ok, "時間内にリーダーが 1 人に決まらなかった")
    return cluster.leaders()[0]


class TestRequestVoteRules(unittest.TestCase):
    """RequestVote の受け手の規則を、ノード単体で確かめる（シミュレータは動かさない）。"""

    def setUp(self):
        self.cluster = RaftCluster(3, seed=1)
        self.node = self.cluster.nodes[0]

    def test_grants_vote_to_up_to_date_candidate_with_newer_term(self):
        reply = self.node.handle_request_vote(RequestVote(term=1, candidate_id=1, last_log_index=0, last_log_term=0))
        self.assertEqual(reply, RequestVoteReply(term=1, vote_granted=True, voter_id=0))
        self.assertEqual((self.node.current_term, self.node.voted_for), (1, 1))

    def test_granting_resets_election_timer(self):
        self.cluster.now = 1000
        self.node.handle_request_vote(RequestVote(1, 1, 0, 0))
        lo, hi = self.cluster.election_timeout
        self.assertTrue(1000 + lo <= self.node.election_deadline <= 1000 + hi)

    def test_rejects_stale_term(self):
        self.node.current_term = 5
        reply = self.node.handle_request_vote(RequestVote(4, 1, 0, 0))
        self.assertEqual(reply, RequestVoteReply(5, False, 0))
        self.assertIsNone(self.node.voted_for)

    def test_one_vote_per_term(self):
        self.assertTrue(self.node.handle_request_vote(RequestVote(1, 1, 0, 0)).vote_granted)
        self.assertFalse(self.node.handle_request_vote(RequestVote(1, 2, 0, 0)).vote_granted, "同じ任期に別の候補へは投票しない")
        self.assertTrue(self.node.handle_request_vote(RequestVote(1, 1, 0, 0)).vote_granted, "同じ候補への再送には再び賛成してよい")
        self.assertTrue(self.node.handle_request_vote(RequestVote(2, 2, 0, 0)).vote_granted, "新しい任期なら投票し直せる")

    def test_rejects_candidate_with_older_last_term(self):
        self.node.log = [LogEntry(1, "a"), LogEntry(3, "b")]
        reply = self.node.handle_request_vote(RequestVote(term=4, candidate_id=1, last_log_index=5, last_log_term=2))
        self.assertFalse(reply.vote_granted, "最後のエントリの term が古い候補は、ログが長くても不可")
        self.assertEqual(self.node.current_term, 4, "ただし term は更新する")

    def test_rejects_candidate_with_shorter_log_in_same_last_term(self):
        self.node.log = [LogEntry(1, "a"), LogEntry(2, "b"), LogEntry(2, "c")]
        self.assertFalse(self.node.handle_request_vote(RequestVote(3, 1, 2, 2)).vote_granted)
        self.assertTrue(self.node.handle_request_vote(RequestVote(3, 2, 3, 2)).vote_granted, "同じ長さなら可")

    def test_accepts_candidate_with_newer_last_term_even_if_shorter(self):
        self.node.log = [LogEntry(1, "a"), LogEntry(1, "b"), LogEntry(1, "c")]
        self.assertTrue(self.node.handle_request_vote(RequestVote(3, 1, 1, 2)).vote_granted)

    def test_leader_steps_down_on_higher_term(self):
        self.node.role = LEADER
        self.node.current_term = 2
        self.node.handle_request_vote(RequestVote(3, 1, 0, 0))
        self.assertEqual((self.node.role, self.node.current_term), (FOLLOWER, 3))
        self.assertGreater(self.node.election_deadline, self.cluster.now, "降格したら選挙タイマーを未来に設定し直す")


class TestAppendEntriesRules(unittest.TestCase):
    def setUp(self):
        self.cluster = RaftCluster(3, seed=2)
        self.node = self.cluster.nodes[0]

    def heartbeat(self, term, leader=1):
        return AppendEntries(term, leader, 0, 0, (), 0)

    def test_rejects_stale_leader(self):
        self.node.current_term = 3
        reply = self.node.handle_append_entries(self.heartbeat(2))
        self.assertEqual((reply.term, reply.success, reply.follower_id), (3, False, 0))
        self.assertIsNone(self.node.leader_id)

    def test_recognizes_leader_and_resets_timer(self):
        self.cluster.now = 500
        reply = self.node.handle_append_entries(self.heartbeat(1, leader=2))
        self.assertTrue(reply.success)
        self.assertEqual((self.node.current_term, self.node.leader_id, self.node.role), (1, 2, FOLLOWER))
        self.assertGreaterEqual(self.node.election_deadline, 500 + self.cluster.election_timeout[0])

    def test_candidate_steps_down_for_leader_of_same_term(self):
        self.node.role = CANDIDATE
        self.node.current_term = 4
        self.node.voted_for = 0
        self.node.handle_append_entries(self.heartbeat(4, leader=2))
        self.assertEqual(self.node.role, FOLLOWER)
        self.assertEqual(self.node.voted_for, 0, "同じ任期なので投票の記録は残る")

    def test_leader_steps_down_on_higher_term_reply(self):
        self.node.role = LEADER
        self.node.current_term = 2
        self.node.next_index = {1: 1, 2: 1}
        self.node.match_index = {1: 0, 2: 0}
        self.node.handle_append_entries_reply(AppendEntriesReply(5, False, 1, 0, 0))
        self.assertEqual((self.node.role, self.node.current_term), (FOLLOWER, 5))

    def test_candidate_counts_votes_and_ignores_stale_replies(self):
        self.node.start_election()
        self.assertEqual((self.node.role, self.node.current_term, self.node.voted_for), (CANDIDATE, 1, 0))
        self.node.handle_request_vote_reply(RequestVoteReply(0, True, 1))  # 古い任期の返事
        self.assertEqual(self.node.role, CANDIDATE)
        self.node.handle_request_vote_reply(RequestVoteReply(1, False, 1))
        self.assertEqual(self.node.role, CANDIDATE)
        self.node.handle_request_vote_reply(RequestVoteReply(1, True, 2))
        self.assertEqual(self.node.role, LEADER, "3 台中 2 票（自分＋1）で過半数")


class TestElectionSimulation(unittest.TestCase):
    def test_single_leader_is_elected(self):
        for seed in range(5):
            c = RaftCluster(5, seed=seed)
            leader = elect(self, c)
            c.run(500)
            self.assertEqual(c.leaders(), [leader], f"seed={seed}: その後も 1 人のまま")
            term = c.nodes[leader].current_term
            for node in c.nodes:
                self.assertEqual((node.current_term, node.leader_id), (term, leader))
            assert_election_safety(self, c)

    def test_single_node_cluster_elects_itself(self):
        c = RaftCluster(1, seed=0)
        self.assertEqual(elect(self, c, 1000), 0)

    def test_heartbeats_keep_leadership_stable(self):
        c = RaftCluster(5, seed=3)
        leader = elect(self, c)
        term = c.nodes[leader].current_term
        c.run(5000)
        self.assertEqual(c.leaders(), [leader])
        self.assertEqual(c.nodes[leader].current_term, term, "障害がなければ選挙は起きない")

    def test_reelection_after_leader_crash(self):
        c = RaftCluster(5, seed=4)
        old = elect(self, c)
        old_term = c.nodes[old].current_term
        c.crash(old)
        new = elect(self, c)
        self.assertNotEqual(new, old)
        self.assertGreater(c.nodes[new].current_term, old_term)
        c.restart(old)
        c.run(1000)
        self.assertEqual(c.leaders(), [new], "復帰した元リーダーはフォロワーになる")
        self.assertEqual(c.nodes[old].role, FOLLOWER)
        assert_election_safety(self, c)

    def test_minority_partition_cannot_elect(self):
        c = RaftCluster(5, seed=5)
        leader = elect(self, c)
        old_term = c.nodes[leader].current_term
        others = [i for i in range(5) if i != leader]
        minority = {others[0], others[1]}
        majority = set(range(5)) - minority
        c.partition(minority, majority)
        c.run(3000)
        for i in minority:
            self.assertNotEqual(c.nodes[i].role, LEADER, "2 台では過半数（3 票）を集められない")
            self.assertGreater(c.nodes[i].current_term, old_term, "選挙を繰り返して term だけが進む")
        self.assertEqual([i for i in c.leaders() if i in majority], [leader], "多数派側のリーダーはそのまま")

    def test_old_leader_in_minority_is_replaced(self):
        c = RaftCluster(5, seed=6)
        leader = elect(self, c)
        old_term = c.nodes[leader].current_term
        minority = {leader, (leader + 1) % 5}
        majority = set(range(5)) - minority
        c.partition(minority, majority)
        ok = c.run_until(lambda: any(c.nodes[i].role == LEADER for i in majority), 3000)
        self.assertTrue(ok, "多数派側で新しいリーダーが選ばれる")
        new = next(i for i in majority if c.nodes[i].role == LEADER)
        self.assertGreater(c.nodes[new].current_term, old_term)
        self.assertEqual(c.nodes[leader].current_term, old_term, "少数派の古いリーダーは古い任期のまま")
        c.heal()
        ok = c.run_until(lambda: len(c.leaders()) == 1, 3000)
        self.assertTrue(ok, "分断が直れば 1 人に収束する")
        assert_election_safety(self, c)

    def test_four_nodes_tolerate_only_one_failure(self):
        c4 = RaftCluster(4, seed=7)
        c4.crash(0)
        c4.crash(1)
        c4.run(3000)
        self.assertEqual(c4.leaders(), [], "4 台中 2 台が止まると過半数（3）を作れない")
        c5 = RaftCluster(5, seed=7)
        c5.crash(0)
        c5.crash(1)
        self.assertIn(elect(self, c5), {2, 3, 4}, "5 台なら 2 台止まっても選べる")

    def test_fixed_timeouts_can_livelock(self):
        # 全員が同じ瞬間にタイムアウトすると、全員が自分に投票して票が割れ続ける
        c = RaftCluster(5, seed=8, election_timeout=(150, 150), network_delay=(1, 1))
        c.run(3000)
        self.assertEqual(c.leaders(), [])
        self.assertGreater(c.nodes[0].current_term, 10, "選挙だけが延々と繰り返される")
        randomized = RaftCluster(5, seed=8, network_delay=(1, 1))
        elect(self, randomized)

    def test_at_most_one_leader_per_term_under_chaos(self):
        for seed in range(8):
            c = RaftCluster(5, seed=seed)
            rng = random.Random(1000 + seed)
            for _ in range(40):
                r = rng.random()
                up = [i for i in range(5) if i not in c.down]
                if r < 0.15 and len(up) > 2:
                    c.crash(rng.choice(up))
                elif r < 0.35 and c.down:
                    c.restart(rng.choice(sorted(c.down)))
                elif r < 0.45:
                    nodes = list(range(5))
                    rng.shuffle(nodes)
                    cut = rng.randrange(1, 5)
                    c.partition(set(nodes[:cut]), set(nodes[cut:]))
                elif r < 0.6:
                    c.heal()
                c.run(100)
                assert_election_safety(self, c)
            c.heal()
            for i in sorted(c.down):
                c.restart(i)
            self.assertTrue(c.run_until(lambda: len(c.leaders()) == 1, 5000), f"seed={seed}")
            assert_election_safety(self, c)


# ---------------------------------------------------------------------------
# 発展課題: ログ複製
# ---------------------------------------------------------------------------


def record_commits(test: unittest.TestCase, cluster: RaftCluster, committed: dict) -> None:
    """状態機械の安全性: 一度どこかでコミットされたインデックスのエントリは、決して変わらない。"""
    for node in cluster.nodes:
        for index in range(1, node.commit_index + 1):
            entry = node.log[index - 1]
            if index in committed:
                test.assertEqual(entry, committed[index], f"インデックス {index} のコミット済みエントリが食い違う")
            else:
                committed[index] = entry


def run_checked(test, cluster, ms, committed):
    for _ in range(ms):
        cluster.step()
        record_commits(test, cluster, committed)


def stable_leader(cluster: RaftCluster):
    """リーダーが 1 人で、全ノードが同じ任期にいてそのリーダーを認識していれば、その ID を返す。"""
    leaders = cluster.leaders()
    if len(leaders) != 1:
        return None
    term = cluster.nodes[leaders[0]].current_term
    if all(n.current_term == term and n.leader_id == leaders[0] for n in cluster.nodes):
        return leaders[0]
    return None


def fully_converged(cluster: RaftCluster) -> bool:
    logs = {tuple(n.log) for n in cluster.nodes}
    return len(logs) == 1 and all(n.commit_index == len(n.log) for n in cluster.nodes)


@unittest.skipUnless(REPLICATION, SKIP_MSG)
class TestLogReplication(unittest.TestCase):
    def test_non_leader_rejects_client_requests(self):
        c = RaftCluster(3, seed=10)
        leader = elect(self, c)
        follower = (leader + 1) % 3
        self.assertFalse(c.nodes[follower].client_request("x"))
        self.assertTrue(c.nodes[leader].client_request("x"))

    def test_entries_are_replicated_and_committed(self):
        c = RaftCluster(5, seed=11)
        leader = elect(self, c)
        for cmd in ("set x=1", "set y=2", "del x"):
            self.assertTrue(c.nodes[leader].client_request(cmd))
        self.assertEqual(c.nodes[leader].commit_index, 0, "過半数に複製されるまではコミットしない")
        c.run(500)
        term = c.nodes[leader].current_term
        for node in c.nodes:
            self.assertEqual(node.log, [LogEntry(term, cmd) for cmd in ("set x=1", "set y=2", "del x")])
            self.assertEqual(node.commit_index, 3)
            self.assertEqual(node.applied, ["set x=1", "set y=2", "del x"], "全員が同じ順序で適用する")

    def test_single_node_commits_immediately(self):
        c = RaftCluster(1, seed=12)
        elect(self, c, 1000)
        c.nodes[0].client_request("a")
        self.assertEqual((c.nodes[0].commit_index, c.nodes[0].applied), (1, ["a"]))

    def test_follower_catches_up_after_restart(self):
        c = RaftCluster(3, seed=13)
        leader = elect(self, c)
        lagging = (leader + 1) % 3
        c.crash(lagging)
        for i in range(10):
            c.nodes[leader].client_request(i)
        c.run(300)
        self.assertEqual(c.nodes[leader].commit_index, 10, "3 台中 2 台で過半数")
        c.restart(lagging)
        c.run(1000)
        self.assertEqual(c.nodes[lagging].log, c.nodes[leader].log)
        self.assertEqual(c.nodes[lagging].applied, list(range(10)))

    def test_append_entries_consistency_check_and_conflict_repair(self):
        c = RaftCluster(3, seed=14)
        node = c.nodes[0]
        node.log = [LogEntry(1, "a"), LogEntry(1, "b"), LogEntry(2, "stale")]
        node.current_term = 2
        mismatch = node.handle_append_entries(AppendEntries(3, 1, 3, 3, (LogEntry(3, "d"),), 0))
        self.assertFalse(mismatch.success, "prev_log_index の term が一致しなければ拒否")
        self.assertEqual(mismatch.last_log_index, 3)
        ok = node.handle_append_entries(AppendEntries(3, 1, 2, 1, (LogEntry(3, "c"), LogEntry(3, "d")), 1))
        self.assertTrue(ok.success)
        self.assertEqual(ok.match_index, 4)
        self.assertEqual([e.command for e in node.log], ["a", "b", "c", "d"], "矛盾するエントリ以降は置き換える")
        self.assertEqual((node.commit_index, node.applied), (1, ["a"]))
        stale = node.handle_append_entries(AppendEntries(3, 1, 1, 1, (LogEntry(1, "b"),), 1))
        self.assertTrue(stale.success)
        self.assertEqual(len(node.log), 4, "遅れて届いた古いメッセージでログを縮めない")

    def test_minority_leader_cannot_commit_and_is_overwritten(self):
        c = RaftCluster(5, seed=15)
        committed: dict = {}
        old = elect(self, c)
        c.nodes[old].client_request("before-partition")
        run_checked(self, c, 300, committed)
        minority = {old, (old + 1) % 5}
        majority = set(range(5)) - minority
        c.partition(minority, majority)
        c.nodes[old].client_request("lost-write")
        run_checked(self, c, 1500, committed)
        self.assertEqual(c.nodes[old].commit_index, 1, "少数派のリーダーはコミットできない")
        new = next(i for i in majority if c.nodes[i].role == LEADER)
        c.nodes[new].client_request("majority-write")
        run_checked(self, c, 500, committed)
        c.heal()
        run_checked(self, c, 1500, committed)
        commands = [e.command for e in c.nodes[old].log]
        self.assertEqual(commands, ["before-partition", "majority-write"], "コミットされなかった書き込みは上書きされる")
        for node in c.nodes:
            self.assertEqual(node.applied, ["before-partition", "majority-write"])

    def test_state_machine_safety_under_chaos(self):
        for seed in range(6):
            c = RaftCluster(5, seed=100 + seed)
            rng = random.Random(seed)
            committed: dict = {}
            counter = 0
            for _ in range(30):
                r = rng.random()
                up = [i for i in range(5) if i not in c.down]
                if r < 0.15 and len(up) > 2:
                    c.crash(rng.choice(up))
                elif r < 0.35 and c.down:
                    c.restart(rng.choice(sorted(c.down)))
                elif r < 0.45:
                    nodes = list(range(5))
                    rng.shuffle(nodes)
                    cut = rng.randrange(1, 5)
                    c.partition(set(nodes[:cut]), set(nodes[cut:]))
                elif r < 0.6:
                    c.heal()
                for leader in c.leaders():
                    counter += 1
                    c.nodes[leader].client_request(f"cmd-{counter}")
                run_checked(self, c, 100, committed)
                assert_election_safety(self, c)
            c.heal()
            for i in sorted(c.down):
                c.restart(i)
            self.assertTrue(c.run_until(lambda: stable_leader(c) is not None, 5000), f"seed={seed}")
            # 新しいリーダーは、自分の任期のエントリがコミットされるまで過去の任期のエントリをコミットできない。
            # そこで、全員のログが一致して全部コミットされるまで、リーダーにコマンドを送る
            for attempt in range(10):
                leader = stable_leader(c)
                if leader is not None:
                    c.nodes[leader].client_request(f"final-{attempt}")
                run_checked(self, c, 300, committed)
                if fully_converged(c):
                    break
            self.assertTrue(fully_converged(c), f"seed={seed}: 最終的に全員のログが一致し、すべてコミットされる")
            final = c.nodes[0]
            for index, entry in committed.items():
                self.assertEqual(final.log[index - 1], entry, "コミット済みのエントリは失われない")


if __name__ == "__main__":
    unittest.main()
