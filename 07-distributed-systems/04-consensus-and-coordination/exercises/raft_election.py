"""7.4 合意と協調 — 演習: Raft のリーダー選出（発展: ログ複製）

Raft（Ongaro と Ousterhout, 2014）は、理解しやすさを重視して設計された合意アルゴリズムで、
etcd・Consul・CockroachDB などが採用しています。この演習では、1 ms 刻みの決定的な離散時間
シミュレータ（RaftCluster, 実装済み）の上で、各ノードの振る舞い（RaftNode のメソッド）を実装します。

    演習4 基本（★★★）: 任期（term）、投票、ランダムな選挙タイムアウト、RequestVote の規則
                       （ログの新しさの検査を含む）、ハートビートによるリーダーの維持
    演習5 発展（★★★）: AppendEntries によるログ複製と、過半数への複製によるコミット
                       → ENABLE_LOG_REPLICATION = True にすると、発展課題のテストも実行されます

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.4
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_raft_election

進め方のヒント:
    1. まず Raft の論文の Figure 2（"State" "RequestVote RPC" "AppendEntries RPC" "Rules for Servers"）を
       手元に置く。このファイルのメソッドは、ほぼその規則に 1 対 1 で対応している。
    2. TestRequestVoteRules と TestAppendEntriesRules（ノード単体のテスト）から通す。
    3. 次に TestElectionSimulation（シミュレーション全体）を通す。失敗したら、テストと同じ seed で
       RaftCluster を作り、cluster.step() を 1 ms ずつ進めながら各ノードの role と current_term を print すると
       原因を追える（決定的なので何度でも同じ状況を再現できる）。

共通の規則（すべての RPC の要求と応答で最初に適用する。Figure 2 "All Servers"）:
    受け取ったメッセージの term が自分の current_term より大きければ、current_term をその値にし、
    フォロワーになる（become_follower）。
"""
from __future__ import annotations

import heapq
import random
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

# 発展課題（ログ複製）に取り組むときは True にする。False の間は、発展課題のテストはスキップされる
ENABLE_LOG_REPLICATION = False

FOLLOWER = "follower"
CANDIDATE = "candidate"
LEADER = "leader"


# ---------------------------------------------------------------------------
# メッセージ（Raft の論文の Figure 2 に対応。実装済み）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LogEntry:
    term: int  # このエントリを作ったリーダーの任期
    command: object  # 状態機械に適用するコマンド


@dataclass(frozen=True)
class RequestVote:
    term: int  # 候補者の任期
    candidate_id: int
    last_log_index: int  # 候補者のログの最後のインデックス（空なら 0）
    last_log_term: int  # 候補者のログの最後のエントリの term（空なら 0）


@dataclass(frozen=True)
class RequestVoteReply:
    term: int  # 返信者の current_term（候補者が古ければ、これを見て降りる）
    vote_granted: bool
    voter_id: int


@dataclass(frozen=True)
class AppendEntries:
    term: int  # リーダーの任期
    leader_id: int
    prev_log_index: int  # 新しいエントリの直前のインデックス
    prev_log_term: int  # その term
    entries: tuple[LogEntry, ...]  # 空ならハートビート
    leader_commit: int  # リーダーの commit_index


@dataclass(frozen=True)
class AppendEntriesReply:
    term: int
    success: bool
    follower_id: int
    match_index: int  # 成功時: リーダーのログと一致を確認できた最後のインデックス（= prev_log_index + len(entries)）
    last_log_index: int  # フォロワーのログの長さ（失敗時に、リーダーが next_index を戻すヒントにする）


# ---------------------------------------------------------------------------
# ノード
# ---------------------------------------------------------------------------


class RaftNode:
    """1 台の Raft サーバー。

    状態（__init__ で用意済み）:
        永続状態（クラッシュしても残る）: current_term, voted_for, log
        揮発状態: role, leader_id, votes（候補者のとき集めた票の集合）, commit_index, last_applied,
                  applied（状態機械に適用したコマンドのリスト）, next_index, match_index,
                  election_deadline（この時刻になったら選挙を始める）, next_heartbeat（リーダーが次に送る時刻）
    ログのインデックスは 1 始まり（log[i - 1] がインデックス i のエントリ）。

    実装済みの補助メソッド: peers, majority(), last_log_index(), last_log_term(), term_at(i),
    send(dst, msg), reset_election_timer(), receive(msg)（メッセージの振り分け）, restart()

    現在時刻は self.cluster.now、ハートビートの間隔は self.cluster.heartbeat_interval で参照できます。
    乱数が必要なら（選挙タイマーのリセット以外では不要なはず）self.cluster.rng を使うこと。
    """

    def __init__(self, node_id: int, cluster: RaftCluster) -> None:
        self.id = node_id
        self.cluster = cluster
        # 永続状態（実システムでは、RPC に応答する前にディスクへ書く）
        self.current_term = 0
        self.voted_for: int | None = None
        self.log: list[LogEntry] = []
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

    # ---- 実装済みの補助メソッド ----

    @property
    def peers(self) -> list[int]:
        """自分以外のノードの ID。"""
        return [i for i in range(self.cluster.n) if i != self.id]

    def majority(self) -> int:
        """過半数に必要な票数（n // 2 + 1）。"""
        return self.cluster.n // 2 + 1

    def last_log_index(self) -> int:
        return len(self.log)

    def last_log_term(self) -> int:
        return self.log[-1].term if self.log else 0

    def term_at(self, index: int) -> int:
        """インデックス index のエントリの term（index == 0 なら 0）。"""
        return self.log[index - 1].term if index > 0 else 0

    def send(self, dst: int, msg: object) -> None:
        self.cluster.send(self.id, dst, msg)

    def reset_election_timer(self) -> None:
        """選挙の締め切りを「現在時刻 + election_timeout の範囲の乱数」に設定し直す。"""
        lo, hi = self.cluster.election_timeout
        self.election_deadline = self.cluster.now + self.cluster.rng.randint(lo, hi)

    def receive(self, msg: object) -> None:
        """届いたメッセージを種類ごとのハンドラに振り分け、要求には応答を送り返す。"""
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
        """クラッシュからの再起動。永続状態（term・投票先・ログ）だけが残り、揮発状態は初期化される。"""
        self.role = FOLLOWER
        self.leader_id = None
        self.votes = set()
        self.commit_index = 0
        self.last_applied = 0
        self.applied = []
        self.next_index = {}
        self.match_index = {}
        self.reset_election_timer()

    # ---- 演習4（基本）: リーダー選出 ----

    def become_follower(self, term: int) -> None:
        """フォロワーになる。

        - term > current_term なら current_term = term とし、voted_for = None にする（新しい任期ではまだ投票していない）。
        - role = FOLLOWER、votes を空にする。
        - **リーダーから降格する場合に限り**、leader_id = None にして reset_election_timer() を呼ぶ
          （リーダーの選挙の締め切りは古いままなので、そのままだと降格した直後に選挙を始めてしまう）。
        """
        raise NotImplementedError("演習4（基本）: become_follower を実装してください")

    def on_tick(self) -> None:
        """シミュレータが 1 ms ごとに呼ぶ。

        - リーダーなら、現在時刻が next_heartbeat 以上のとき send_heartbeats() を呼ぶ。
        - リーダー以外（フォロワー・候補者）なら、現在時刻が election_deadline 以上のとき start_election() を呼ぶ。
        """
        raise NotImplementedError("演習4（基本）: on_tick を実装してください")

    def start_election(self) -> None:
        """選挙を始める（Figure 2 "Candidates"）。

        1. role = CANDIDATE、current_term を 1 増やし、自分に投票する（voted_for = 自分、votes = {自分}）。
           leader_id = None。
        2. reset_election_timer()（票が割れたら、この締め切りで次の選挙を始める）。
        3. 全ピアに RequestVote(current_term, 自分, last_log_index(), last_log_term()) を送る。
        4. votes がすでに過半数なら（1 台構成）become_leader()。
        """
        raise NotImplementedError("演習4（基本）: start_election を実装してください")

    def handle_request_vote(self, msg: RequestVote) -> RequestVoteReply:
        """RequestVote を受け取り、応答を返す（Figure 2 "RequestVote RPC"）。

        1. 共通の規則: msg.term > current_term なら become_follower(msg.term)。
        2. 次のすべてを満たせば投票する（vote_granted = True）:
             - msg.term == current_term（古い任期の候補者には投票しない）
             - voted_for が None か、msg.candidate_id と同じ（1 つの任期に 1 票。同じ候補への再送には再び賛成）
             - 候補者のログが自分と同じか、より新しい（論文 5.4.1 節）:
               候補者の last_log_term が自分の last_log_term() より大きい、
               または等しくて候補者の last_log_index が自分の last_log_index() 以上
        3. 投票したら voted_for = 候補者にして、reset_election_timer() を呼ぶ。投票しないときはタイマーを触らない。
        4. RequestVoteReply(current_term, 投票したか, 自分の ID) を返す。

        考えてみよう: ログの新しさの検査がないと、コミット済みのエントリを持たないノードがリーダーになり、
        そのエントリを消してしまう。なぜ「過半数に複製されたエントリは、次のリーダーのログに必ずある」と言えるのか。
        """
        raise NotImplementedError("演習4（基本）: handle_request_vote を実装してください")

    def handle_request_vote_reply(self, msg: RequestVoteReply) -> None:
        """RequestVote への返事を処理する。

        1. msg.term > current_term なら become_follower(msg.term) して終わり。
        2. 自分が候補者でない、または msg.term != current_term（古い選挙の返事）なら無視する。
        3. 賛成なら votes に msg.voter_id を加え、過半数に達したら become_leader()。
        """
        raise NotImplementedError("演習4（基本）: handle_request_vote_reply を実装してください")

    def become_leader(self) -> None:
        """リーダーになる。

        role = LEADER、leader_id = 自分。全ピアについて next_index = last_log_index() + 1、match_index = 0。
        そして直ちに send_heartbeats() を呼ぶ（他のノードの選挙を止めるため）。
        注意: 就任時に no-op エントリを追加する最適化（論文 8 節）は、この演習では **行わない** こと。
        """
        raise NotImplementedError("演習4（基本）: become_leader を実装してください")

    def send_heartbeats(self) -> None:
        """全ピアに AppendEntries を送り、next_heartbeat = 現在時刻 + heartbeat_interval にする。

        【基本】空のハートビート AppendEntries(current_term, 自分, 0, 0, (), commit_index) でよい。
        【発展】ピア p ごとに prev = next_index[p] - 1 とし、
                AppendEntries(current_term, 自分, prev, term_at(prev), tuple(log[prev:]), commit_index) を送る
                （足りないエントリをまとめて送る。何もなければ空のハートビートになる）。
        """
        raise NotImplementedError("演習4（基本）: send_heartbeats を実装してください")

    def handle_append_entries(self, msg: AppendEntries) -> AppendEntriesReply:
        """AppendEntries を受け取り、応答を返す（Figure 2 "AppendEntries RPC"）。

        【基本】
        1. msg.term > current_term なら become_follower(msg.term)。
        2. msg.term < current_term なら、AppendEntriesReply(current_term, False, 自分, 0, last_log_index()) を返す
           （古いリーダーへの拒否。返した term を見て、古いリーダーは降りる）。
        3. 同じ任期の正当なリーダーからのメッセージなので: 自分が候補者（など）なら become_follower(msg.term)、
           leader_id = msg.leader_id、reset_election_timer()。
        4. 基本だけなら、AppendEntriesReply(current_term, True, 自分, 0, last_log_index()) を返してよい。
        【発展】3 の後に、次を行う。
        5. 一貫性の検査: msg.prev_log_index > last_log_index()、または term_at(msg.prev_log_index) != msg.prev_log_term
           なら、失敗（success=False, match_index=0, last_log_index=自分のログの長さ）を返す。
        6. msg.entries をインデックス prev_log_index + 1 から順に照合する。同じインデックスに **term の異なる**
           エントリがあれば、そこから後ろをすべて削除してから追加する。ログにないインデックスのものは追加する。
           （一致するエントリは何もしない。遅れて届いた古いメッセージでログを縮めないため、矛盾がなければ削除しない）
        7. match = prev_log_index + len(entries)。msg.leader_commit > commit_index なら
           commit_index = max(commit_index, min(msg.leader_commit, match)) にして apply_committed()。
        8. AppendEntriesReply(current_term, True, 自分, match, last_log_index()) を返す。
        """
        raise NotImplementedError("演習4（基本）: handle_append_entries を実装してください")

    def handle_append_entries_reply(self, msg: AppendEntriesReply) -> None:
        """AppendEntries への返事を処理する。

        【基本】msg.term > current_term なら become_follower(msg.term)。それ以外は何もしなくてよい。
        【発展】自分がリーダーで msg.term == current_term のときだけ、次を行う（古い返事は無視）。
            - 成功: match_index[f] = max(match_index[f], msg.match_index)、
                    next_index[f] = max(next_index[f], match_index[f] + 1)、advance_commit_index()。
            - 失敗: next_index[f] = max(1, min(next_index[f] - 1, msg.last_log_index + 1))
                    （次のハートビートで、もっと前から送り直す）。
        """
        raise NotImplementedError("演習4（基本）: handle_append_entries_reply を実装してください")

    # ---- 演習5（発展）: ログ複製 ----

    def client_request(self, command: object) -> bool:
        """【発展】クライアントからのコマンドを受け付ける。

        リーダーでなければ False。リーダーなら LogEntry(current_term, command) をログに追加し、
        advance_commit_index() を呼んで（1 台構成なら即座にコミットされる）True を返す。
        フォロワーへの複製は、次の send_heartbeats() で行われる。
        """
        raise NotImplementedError("演習5（発展）: client_request を実装してください")

    def advance_commit_index(self) -> None:
        """【発展】過半数に複製されたエントリまで commit_index を進める。

        インデックス n を last_log_index() から commit_index + 1 まで降順に調べ、
            - log[n-1].term != current_term になったら打ち切る（**過去の任期のエントリは、複製数を数えて
              直接コミットしてはいけない**。論文の Figure 8 の状況を防ぐ規則。現在の任期のエントリがコミットされれば、
              それより前のエントリも一緒にコミットされる）
            - 自分（1）+ match_index[p] >= n であるピアの数 が majority() 以上なら、commit_index = n として
              apply_committed() を呼び、終わる。
        """
        raise NotImplementedError("演習5（発展）: advance_commit_index を実装してください")

    def apply_committed(self) -> None:
        """【発展】last_applied < commit_index の間、last_applied を 1 進めてそのエントリの command を applied に追加する。"""
        raise NotImplementedError("演習5（発展）: apply_committed を実装してください")


# ---------------------------------------------------------------------------
# 決定的な離散時間シミュレータ（実装済み。変更しないこと）
# ---------------------------------------------------------------------------


class RaftCluster:
    """n 台の RaftNode を、1 ms 刻みの離散時間で動かすシミュレータ。

    - step(): 時刻を 1 ms 進め、配送時刻になったメッセージを届け（宛先が停止中・分断中なら捨てる）、
      稼働中の各ノードの on_tick() を ID 順に呼ぶ。
    - メッセージの遅延は rng.randint(*network_delay) ms。すべての乱数は rng（seed で固定）から取るので、
      同じ seed なら毎回まったく同じ実行になる。
    - crash(i) / restart(i): ノードの停止と再起動。partition(*groups) / heal(): ネットワークの分断と回復。
    - leader_history: {任期: その任期にリーダーだったノードの集合}（安全性の検査に使う）。
    """

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
        """稼働中で、自分をリーダーだと思っているノードの ID（分断中は古いリーダーも含まれうる）。"""
        return [n.id for n in self.nodes if n.id not in self.down and n.role == LEADER]

    def newest_leader(self) -> int | None:
        leaders = [self.nodes[i] for i in self.leaders()]
        return max(leaders, key=lambda n: n.current_term).id if leaders else None
