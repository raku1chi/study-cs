"""7.4 合意と協調 — 演習: 2 相コミット（解答例）

演習の仕様は exercises/twopc.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import Sequence

INIT = "INIT"
PREPARED = "PREPARED"
COMMITTED = "COMMITTED"
ABORTED = "ABORTED"

COMMIT = "COMMIT"
ABORT = "ABORT"

CRASH_POINTS = ("after_prepare", "after_decision", "during_decision")


def _deliver(p: "Participant", decision: str) -> bool:
    return p.commit() if decision == COMMIT else p.abort()

# ---------------------------------------------------------------------------
# 演習1: 参加者
# ---------------------------------------------------------------------------


class AtomicityViolation(Exception):
    pass


class Participant:
    def __init__(self, name: str, vote: bool = True, crash_before_vote: bool = False) -> None:
        self.name = name
        self.vote = vote
        self.crash_before_vote = crash_before_vote
        self.up = True
        self.log: list[str] = []  # 永続ログ（クラッシュしても残る）
        self.state = INIT  # 揮発状態（ログから復元できる）

    def prepare(self) -> bool | None:
        if not self.up:
            return None
        if self.crash_before_vote:
            self.crash()
            return None  # 応答がない = コーディネーターから見ればタイムアウト
        if self.state != INIT:
            return self.state in (PREPARED, COMMITTED)  # 重複した PREPARE には同じ答えを返す
        if self.vote:
            # 「言われたら必ずコミットできる」状態を先に永続化してから YES と答える（約束）
            self.log.append(PREPARED)
            self.state = PREPARED
            return True
        # NO と答えた参加者は、その場で一方的にアボートしてよい
        self.log.append(ABORT)
        self.state = ABORTED
        return False

    def commit(self) -> bool:
        if not self.up:
            return False
        if self.state == COMMITTED:
            return True  # 冪等
        if self.state != PREPARED:
            raise AtomicityViolation(f"{self.name}: {self.state} の状態で COMMIT を受け取りました")
        self.log.append(COMMIT)
        self.state = COMMITTED
        return True

    def abort(self) -> bool:
        if not self.up:
            return False
        if self.state == ABORTED:
            return True
        if self.state == COMMITTED:
            raise AtomicityViolation(f"{self.name}: コミット済みなのに ABORT を受け取りました")
        self.log.append(ABORT)
        self.state = ABORTED
        return True

    def crash(self) -> None:
        self.up = False
        self.state = None  # type: ignore[assignment]  # メモリ上の状態は失われる

    def recover(self) -> None:
        self.up = True
        last = self.log[-1] if self.log else None
        if last == PREPARED:
            self.state = PREPARED  # 結果を知るまで、自分では決められない（in-doubt）
        elif last == COMMIT:
            self.state = COMMITTED
        elif last == ABORT:
            self.state = ABORTED
        else:
            # YES と約束する前に落ちたので、一方的にアボートしてよい
            self.log.append(ABORT)
            self.state = ABORTED

    def outcome(self) -> str | None:
        """永続ログから見た最終結果（COMMITTED / ABORTED）。まだ決まっていなければ None。"""
        last = self.log[-1] if self.log else None
        return {COMMIT: COMMITTED, ABORT: ABORTED}.get(last)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 演習2: コーディネーター
# ---------------------------------------------------------------------------


class Coordinator:
    def __init__(self, participants: Sequence[Participant], crash_at: str | None = None) -> None:
        if crash_at is not None and crash_at not in CRASH_POINTS:
            raise ValueError(f"crash_at は {CRASH_POINTS} のいずれかです: {crash_at!r}")
        self.participants = list(participants)
        self.crash_at = crash_at
        self.up = True
        self.log: list[str] = []

    def decision(self) -> str | None:
        return self.log[-1] if self.log else None

    def run(self) -> str:
        # フェーズ 1: 全員に PREPARE を送り、投票を集める。応答がなければ NO とみなす（タイムアウト）
        votes = [p.prepare() for p in self.participants]
        decision = COMMIT if all(v is True for v in votes) else ABORT
        if self.crash_at == "after_prepare":
            self.up = False
            return "CRASHED"  # 決定をログに書く前に落ちた
        # ここがコミットポイント。決定を永続化した瞬間に、トランザクションの結果が確定する
        self.log.append(decision)
        if self.crash_at == "after_decision":
            self.up = False
            return "CRASHED"
        # フェーズ 2: 決定を全員に伝える
        for i, p in enumerate(self.participants):
            _deliver(p, decision)  # 停止中の参加者には届かない（復帰後に finish で再送する）
            if self.crash_at == "during_decision" and i == 0:
                self.up = False
                return "CRASHED"
        return COMMITTED if decision == COMMIT else ABORTED

    def finish(self) -> None:
        decision = self.decision()
        if decision is None:
            return
        for p in self.participants:
            if p.up and p.outcome() is None:
                _deliver(p, decision)

    def recover(self) -> str:
        self.up = True
        if self.decision() is None:
            # 決定を記録する前に落ちた。まだ誰もコミットしていないはずなので、アボートで確定できる（presumed abort）
            self.log.append(ABORT)
        self.finish()
        return COMMITTED if self.decision() == COMMIT else ABORTED


# ---------------------------------------------------------------------------
# 演習3: 検査と協調的な終了
# ---------------------------------------------------------------------------


def in_doubt(participants: Sequence[Participant]) -> list[str]:
    # YES と約束した（PREPARED を記録した）が、結果をまだ知らない参加者。ロックを握ったまま待つしかない
    return sorted(p.name for p in participants if p.log and p.log[-1] == PREPARED)


def is_atomic(participants: Sequence[Participant]) -> bool:
    outcomes = {p.outcome() for p in participants} - {None}
    return len(outcomes) <= 1


def cooperative_termination(participants: Sequence[Participant]) -> str | None:
    up = [p for p in participants if p.up]
    decision = None
    for p in up:
        outcome = p.outcome()
        if outcome == COMMITTED:
            decision = COMMIT  # 誰かがコミットしたなら、決定は COMMIT だった
            break
        if outcome == ABORTED or not p.log:
            decision = ABORT  # 誰かが NO と言った／まだ投票していないなら、COMMIT は決定されえない
    if decision is None:
        return None  # 稼働中の全員が PREPARED（か停止中）: 誰も結果を知らない → ブロック
    for p in up:
        if p.log and p.log[-1] == PREPARED:
            _deliver(p, decision)
        elif not p.log:
            p.abort()  # まだ投票していない参加者も、ABORT を記録して以後の PREPARE に NO と答える
    return decision
