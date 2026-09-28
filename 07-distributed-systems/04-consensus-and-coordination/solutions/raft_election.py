"""7.4 合意と協調 — 演習: Raft のリーダー選出（とログ複製）（解答例）

演習の仕様は exercises/raft_election.py の docstring を参照してください。
RaftCluster（シミュレータ）はスタブと同じものです。RaftNode の各メソッドが解答です。
この解答例は発展課題（ログ複製）まで実装しているので、ENABLE_LOG_REPLICATION = True にしています。
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

# 発展課題（ログ複製）のテストを実行するかどうか。スタブでは False
ENABLE_LOG_REPLICATION = True

FOLLOWER = "follower"
CANDIDATE = "candidate"
LEADER = "leader"


# ---------------------------------------------------------------------------
# メッセージ（Raft の論文の Figure 2 に対応）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogEntry:
    term: int
    command: object


@dataclass(frozen=True)
class RequestVote:
    term: int
    candidate_id: int
    last_log_index: int
    last_log_term: int


@dataclass(frozen=True)
class RequestVoteReply:
    term: int
    vote_granted: bool
    voter_id: int


@dataclass(frozen=True)
class AppendEntries:
    term: int
    leader_id: int
    prev_log_index: int
    prev_log_term: int
    entries: tuple[LogEntry, ...]
    leader_commit: int


@dataclass(frozen=True)
class AppendEntriesReply:
    term: int
    success: bool
    follower_id: int
    match_index: int  # 成功時: 一致を確認できた最後のインデックス
    last_log_index: int  # 失敗時のヒント: フォロワーのログの長さ


# ---------------------------------------------------------------------------
# ノード
# ---------------------------------------------------------------------------


class RaftNode:
    def __init__(self, node_id: int, cluster: RaftCluster) -> None:
        self.id = node_id
        self.cluster = cluster
        # 永続状態（クラッシュしても失われない。実システムでは応答前にディスクへ書く）
        self.current_term = 0
        self.voted_for: int | None = None
        self.log: list[LogEntry] = []  # インデックスは 1 始まり: log[i - 1] がインデックス i
        # 揮発状態
        self.role = FOLLOWER
        self.leader_id: int | None = None
        self.votes: set[int] = set()
        self.commit_index = 0
        self.last_applied = 0
        self.applied: list[object] = []
        self.next_index: dict[int, int] = {}
        self.match_index: dict[int, int] = {}
        self.election_deadline = 0
        self.next_heartbeat = 0
        self.reset_election_timer()

    # ---- 提供されている補助メソッド ----

    @property
    def peers(self) -> list[int]:
        return [i for i in range(self.cluster.n) if i != self.id]

    def majority(self) -> int:
        return self.cluster.n // 2 + 1

    def last_log_index(self) -> int:
        return len(self.log)

    def last_log_term(self) -> int:
        return self.log[-1].term if self.log else 0

    def term_at(self, index: int) -> int:
        return self.log[index - 1].term if index > 0 else 0

    def send(self, dst: int, msg: object) -> None:
        self.cluster.send(self.id, dst, msg)

    def reset_election_timer(self) -> None:
        lo, hi = self.cluster.election_timeout
        self.election_deadline = self.cluster.now + self.cluster.rng.randint(lo, hi)

    def receive(self, msg: object) -> None:
        if isinstance(msg, RequestVote):
            self.send(msg.candidate_id, self.handle_request_vote(msg))
        elif isinstance(msg, RequestVoteReply):
            self.handle_request_vote_reply(msg)
        elif isinstance(msg, AppendEntries):
            self.send(msg.leader_id, self.handle_append_entries(msg))
        elif isinstance(msg, AppendEntriesReply):
            self.handle_append_entries_reply(msg)
        else:
            raise TypeError(f"不明なメッセージ: {msg!r}")

    def restart(self) -> None:
        # クラッシュからの再起動: 永続状態（term・投票先・ログ）だけが残る
        self.role = FOLLOWER
        self.leader_id = None
        self.votes = set()
        self.commit_index = 0
        self.last_applied = 0
        self.applied = []
        self.next_index = {}
        self.match_index = {}
        self.reset_election_timer()

    # ---- 演習: リーダー選出 ----

    def become_follower(self, term: int) -> None:
        was_leader = self.role == LEADER
        if term > self.current_term:
            # 新しい任期を知ったら、その任期ではまだ誰にも投票していない
            self.current_term = term
            self.voted_for = None
        self.role = FOLLOWER
        self.votes = set()
        if was_leader:
            self.leader_id = None
            self.reset_election_timer()  # 古い締め切りのままだと、降格した直後に選挙を始めてしまう

    def on_tick(self) -> None:
        now = self.cluster.now
        if self.role == LEADER:
            if now >= self.next_heartbeat:
                self.send_heartbeats()
        elif now >= self.election_deadline:
            self.start_election()

    def start_election(self) -> None:
        self.role = CANDIDATE
        self.current_term += 1
        self.voted_for = self.id  # 自分に投票
        self.votes = {self.id}
        self.leader_id = None
        self.reset_election_timer()  # 票が割れたら、この締め切りで次の選挙を始める
        request = RequestVote(self.current_term, self.id, self.last_log_index(), self.last_log_term())
        for p in self.peers:
            self.send(p, request)
        if len(self.votes) >= self.majority():  # 1 台構成
            self.become_leader()

    def _candidate_log_is_up_to_date(self, msg: RequestVote) -> bool:
        # 最後のエントリの term が大きい方が新しい。同じなら長い方が新しい（Raft の論文 5.4.1 節）
        if msg.last_log_term != self.last_log_term():
            return msg.last_log_term > self.last_log_term()
        return msg.last_log_index >= self.last_log_index()

    def handle_request_vote(self, msg: RequestVote) -> RequestVoteReply:
        if msg.term > self.current_term:
            self.become_follower(msg.term)
        granted = (
            msg.term == self.current_term
            and self.voted_for in (None, msg.candidate_id)  # 1 つの任期に 1 票だけ（同じ候補への再送は OK）
            and self._candidate_log_is_up_to_date(msg)
        )
        if granted:
            self.voted_for = msg.candidate_id
            self.reset_election_timer()  # 投票したら、しばらくは自分から選挙を始めない
        return RequestVoteReply(self.current_term, granted, self.id)

    def handle_request_vote_reply(self, msg: RequestVoteReply) -> None:
        if msg.term > self.current_term:
            self.become_follower(msg.term)
            return
        if self.role != CANDIDATE or msg.term != self.current_term:
            return  # 古い選挙への返事は無視する
        if msg.vote_granted:
            self.votes.add(msg.voter_id)
            if len(self.votes) >= self.majority():
                self.become_leader()

    def become_leader(self) -> None:
        self.role = LEADER
        self.leader_id = self.id
        self.next_index = {p: self.last_log_index() + 1 for p in self.peers}
        self.match_index = {p: 0 for p in self.peers}
        self.send_heartbeats()  # すぐに存在を知らせ、他のノードの選挙を止める

    def send_heartbeats(self) -> None:
        for p in self.peers:
            prev = self.next_index[p] - 1
            entries = tuple(self.log[prev:])  # フォロワーに足りないエントリをまとめて送る（空ならただのハートビート）
            self.send(
                p,
                AppendEntries(self.current_term, self.id, prev, self.term_at(prev), entries, self.commit_index),
            )
        self.next_heartbeat = self.cluster.now + self.cluster.heartbeat_interval

    def handle_append_entries(self, msg: AppendEntries) -> AppendEntriesReply:
        if msg.term > self.current_term:
            self.become_follower(msg.term)
        if msg.term < self.current_term:
            return AppendEntriesReply(self.current_term, False, self.id, 0, self.last_log_index())
        if self.role != FOLLOWER:
            self.become_follower(msg.term)  # 同じ任期のリーダーが現れた → 候補者は降りる
        self.leader_id = msg.leader_id
        self.reset_election_timer()
        # 一貫性の検査: 直前のエントリが一致しなければ、リーダーにもっと前から送り直してもらう
        if msg.prev_log_index > self.last_log_index() or self.term_at(msg.prev_log_index) != msg.prev_log_term:
            return AppendEntriesReply(self.current_term, False, self.id, 0, self.last_log_index())
        index = msg.prev_log_index
        for entry in msg.entries:
            index += 1
            if index <= self.last_log_index():
                if self.log[index - 1].term != entry.term:
                    del self.log[index - 1 :]  # 矛盾するエントリ以降を捨てて、リーダーのログに合わせる
                    self.log.append(entry)
            else:
                self.log.append(entry)
        match = msg.prev_log_index + len(msg.entries)
        if msg.leader_commit > self.commit_index:
            self.commit_index = max(self.commit_index, min(msg.leader_commit, match))
            self.apply_committed()
        return AppendEntriesReply(self.current_term, True, self.id, match, self.last_log_index())

    def handle_append_entries_reply(self, msg: AppendEntriesReply) -> None:
        if msg.term > self.current_term:
            self.become_follower(msg.term)
            return
        if self.role != LEADER or msg.term != self.current_term:
            return
        f = msg.follower_id
        if msg.success:
            self.match_index[f] = max(self.match_index[f], msg.match_index)
            self.next_index[f] = max(self.next_index[f], self.match_index[f] + 1)
            self.advance_commit_index()
        else:
            # 1 つ前から送り直す。フォロワーのログが短ければ、その末尾まで一気に戻る
            self.next_index[f] = max(1, min(self.next_index[f] - 1, msg.last_log_index + 1))

    # ---- 発展: ログ複製 ----

    def client_request(self, command: object) -> bool:
        if self.role != LEADER:
            return False
        self.log.append(LogEntry(self.current_term, command))
        self.advance_commit_index()  # 1 台構成なら即座にコミットできる
        return True

    def advance_commit_index(self) -> None:
        for n in range(self.last_log_index(), self.commit_index, -1):
            if self.log[n - 1].term != self.current_term:
                break  # 過去の任期のエントリは、数を数えて直接コミットしてはいけない（論文の Figure 8）
            replicated = 1 + sum(1 for p in self.peers if self.match_index.get(p, 0) >= n)
            if replicated >= self.majority():
                self.commit_index = n
                self.apply_committed()
                return

    def apply_committed(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            self.applied.append(self.log[self.last_applied - 1].command)


# ---------------------------------------------------------------------------
# 決定的な離散時間シミュレータ（スタブと同じ。実装済み）
# ---------------------------------------------------------------------------


class RaftCluster:
    def __init__(
        self,
        n: int = 5,
        seed: int = 0,
        *,
        election_timeout: tuple[int, int] = (150, 300),
        heartbeat_interval: int = 50,
        network_delay: tuple[int, int] = (2, 10),
    ) -> None:
        if n < 1:
            raise ValueError("n は 1 以上です")
        self.n = n
        self.rng = random.Random(seed)
        self.now = 0
        self.election_timeout = election_timeout
        self.heartbeat_interval = heartbeat_interval
        self.network_delay = network_delay
        self.down: set[int] = set()
        self.leader_history: dict[int, set[int]] = defaultdict(set)
        self._queue: list[tuple[int, int, int, int, object]] = []
        self._seq = 0
        self._groups: list[frozenset[int]] | None = None
        self.nodes = [RaftNode(i, self) for i in range(n)]

    def connected(self, a: int, b: int) -> bool:
        if a == b or self._groups is None:
            return True
        return any(a in g and b in g for g in self._groups)

    def send(self, src: int, dst: int, msg: object) -> None:
        self._seq += 1
        at = self.now + self.rng.randint(*self.network_delay)
        heapq.heappush(self._queue, (at, self._seq, src, dst, msg))

    def _observe(self, node: RaftNode) -> None:
        if node.role == LEADER:
            self.leader_history[node.current_term].add(node.id)

    def step(self) -> None:
        self.now += 1
        while self._queue and self._queue[0][0] <= self.now:
            _, _, src, dst, msg = heapq.heappop(self._queue)
            if dst in self.down or not self.connected(src, dst):
                continue  # 宛先が停止中、または配送の時点で分断されていれば届かない
            node = self.nodes[dst]
            node.receive(msg)
            self._observe(node)
        for node in self.nodes:
            if node.id not in self.down:
                node.on_tick()
                self._observe(node)

    def run(self, ms: int) -> None:
        for _ in range(ms):
            self.step()

    def run_until(self, predicate: Callable[[], bool], timeout_ms: int) -> bool:
        for _ in range(timeout_ms):
            if predicate():
                return True
            self.step()
        return predicate()

    def crash(self, i: int) -> None:
        self.down.add(i)

    def restart(self, i: int) -> None:
        if i in self.down:
            self.down.remove(i)
            self.nodes[i].restart()

    def partition(self, *groups: set[int]) -> None:
        self._groups = [frozenset(g) for g in groups]

    def heal(self) -> None:
        self._groups = None

    def leaders(self) -> list[int]:
        return [n.id for n in self.nodes if n.id not in self.down and n.role == LEADER]

    def newest_leader(self) -> int | None:
        leaders = [self.nodes[i] for i in self.leaders()]
        return max(leaders, key=lambda n: n.current_term).id if leaders else None
