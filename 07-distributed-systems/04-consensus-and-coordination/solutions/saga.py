"""7.4 合意と協調 — 演習: Saga オーケストレーター（解答例）

演習の仕様は exercises/saga.py の docstring を参照してください。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Sequence

RUNNING = "RUNNING"
COMPENSATING = "COMPENSATING"
COMPLETED = "COMPLETED"
COMPENSATED = "COMPENSATED"
FAILED = "FAILED"


class RetryableError(Exception):
    pass


class SimulatedCrash(BaseException):
    """オーケストレーターのプロセスが落ちたことを表す（テスト用）。except Exception では捕まらない。"""


@dataclass
class Step:
    name: str
    action: Callable[[dict], None]
    compensation: Callable[[dict], None] | None = None
    max_attempts: int = 1


@dataclass
class SagaResult:
    saga_id: str
    status: str
    completed: list[str]
    compensated: list[str]
    error: str | None
    ctx: dict


class InMemorySagaStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self.saves = 0

    def save(self, saga_id: str, state: dict) -> None:
        self._data[saga_id] = json.dumps(state, ensure_ascii=False)
        self.saves += 1

    def load(self, saga_id: str) -> dict | None:
        raw = self._data.get(saga_id)
        return None if raw is None else json.loads(raw)


class SagaOrchestrator:
    def __init__(self, steps: Sequence[Step], store: InMemorySagaStore, compensation_attempts: int = 3) -> None:
        names = [s.name for s in steps]
        if len(set(names)) != len(names):
            raise ValueError("ステップ名が重複しています")
        if any(s.max_attempts < 1 for s in steps) or compensation_attempts < 1:
            raise ValueError("試行回数は 1 以上です")
        self.steps = list(steps)
        self.store = store
        self.compensation_attempts = compensation_attempts
        self._by_name = {s.name: s for s in steps}

    def start(self, saga_id: str, ctx: dict) -> SagaResult:
        if self.store.load(saga_id) is not None:
            raise ValueError(f"Saga {saga_id} はすでに存在します（resume を使ってください）")
        state = {
            "status": RUNNING,
            "ctx": json.loads(json.dumps(ctx)),  # 永続化できる値だけを受け付ける（コピーも兼ねる）
            "completed": [],
            "compensated": [],
            "current": None,
            "error": None,
        }
        self.store.save(saga_id, state)
        return self._drive(saga_id, state)

    def resume(self, saga_id: str) -> SagaResult:
        state = self.store.load(saga_id)
        if state is None:
            raise KeyError(saga_id)
        return self._drive(saga_id, state)

    def _drive(self, saga_id: str, state: dict) -> SagaResult:
        if state["status"] == RUNNING:
            self._run_forward(saga_id, state)
        if state["status"] in (COMPENSATING, FAILED):
            self._compensate(saga_id, state)
        return SagaResult(
            saga_id,
            state["status"],
            list(state["completed"]),
            list(state["compensated"]),
            state["error"],
            dict(state["ctx"]),
        )

    def _run_forward(self, saga_id: str, state: dict) -> None:
        ctx = state["ctx"]
        for step in self.steps:
            if step.name in state["completed"]:
                continue  # 再開時: 完了を記録済みのステップは実行しない
            # 「このステップを始める」ことを先に記録する。ここで落ちたら、再開時にこのステップからやり直す
            # （＝同じステップが 2 回実行されうるので、各ステップは冪等でなければならない）
            state["current"] = step.name
            self.store.save(saga_id, state)
            error = self._attempt(step, ctx)
            if error is not None:
                state["status"] = COMPENSATING
                state["error"] = error
                state["current"] = None
                self.store.save(saga_id, state)
                return
            state["completed"].append(step.name)
            state["current"] = None
            self.store.save(saga_id, state)
        state["status"] = COMPLETED
        self.store.save(saga_id, state)

    @staticmethod
    def _attempt(step: Step, ctx: dict) -> str | None:
        for attempt in range(1, step.max_attempts + 1):
            try:
                step.action(ctx)
                return None
            except RetryableError as exc:
                if attempt == step.max_attempts:
                    return f"{step.name}: {exc!r}（{attempt} 回試行）"
                # 一時的な失敗は、冪等なステップに限って再試行する（実務では指数バックオフを入れる）
            except Exception as exc:  # 恒久的な失敗（在庫切れ、カード拒否など）は再試行しない
                return f"{step.name}: {exc!r}"
        return None  # pragma: no cover

    def _compensate(self, saga_id: str, state: dict) -> None:
        ctx = state["ctx"]
        if state["status"] != COMPENSATING:
            state["status"] = COMPENSATING  # FAILED からの再開（運用者が原因を取り除いた後）
            self.store.save(saga_id, state)
        # 完了したステップだけを、逆順に取り消す。失敗したステップ自体は完了していないので補償しない
        for name in reversed(state["completed"]):
            step = self._by_name[name]
            if name in state["compensated"] or step.compensation is None:
                continue
            last_error: Exception | None = None
            for _ in range(self.compensation_attempts):
                try:
                    step.compensation(ctx)
                    last_error = None
                    break
                except Exception as exc:  # 補償は失敗しても諦められない。再試行する
                    last_error = exc
            if last_error is not None:
                state["status"] = FAILED  # 人手の介入が必要。原因を直したら resume で続きから補償する
                state["error"] = f"補償 {name} に失敗: {last_error!r}"
                self.store.save(saga_id, state)
                return
            state["compensated"].append(name)
            self.store.save(saga_id, state)
        state["status"] = COMPENSATED
        self.store.save(saga_id, state)
