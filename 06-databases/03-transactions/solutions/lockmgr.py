"""6.3 トランザクションと同時実行制御 — 演習2 解答例: ロックマネージャとデッドロック検出

演習の仕様は exercises/lockmgr.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass

MODES = ("S", "X")


class LockError(Exception):
    pass


def compatible(held: str, requested: str) -> bool:
    return held == "S" and requested == "S"


@dataclass
class Request:
    txn: int
    mode: str
    upgrade: bool = False


class LockManager:
    def __init__(self) -> None:
        self._holders: dict[str, dict[int, str]] = {}
        self._queues: dict[str, list[Request]] = {}
        self._waiting_on: dict[int, str] = {}   # 待っているトランザクション → 資源
        self._finished: set[int] = set()
        self.aborted: list[int] = []

    # --- 参照用 --------------------------------------------------------------

    def holders(self, resource: str) -> dict[int, str]:
        return dict(sorted(self._holders.get(resource, {}).items()))

    def waiters(self, resource: str) -> list[tuple[int, str]]:
        return [(r.txn, r.mode) for r in self._queues.get(resource, [])]

    def status(self, txn: int) -> str:
        if txn in self.aborted:
            return "aborted"
        if txn in self._finished:
            return "finished"
        if txn in self._waiting_on:
            return "waiting"
        return "running"

    # --- 演習2-1: 獲得と解放 --------------------------------------------------

    def acquire(self, txn: int, resource: str, mode: str) -> str:
        if mode not in MODES:
            raise ValueError(f"mode は 'S' か 'X': {mode!r}")
        state = self.status(txn)
        if state != "running":
            raise LockError(f"トランザクション {txn} は {state} なので、ロックを要求できません")
        holders = self._holders.setdefault(resource, {})
        queue = self._queues.setdefault(resource, [])
        held = holders.get(txn)
        if held == "X" or held == mode:
            return "granted"  # すでに十分な強さのロックを持っている
        if held == "S":  # S → X への昇格
            if len(holders) == 1:
                holders[txn] = "X"
                return "granted"
            # 昇格要求は待ち行列の先頭に入れる（既に S を持っているので、後ろに並ばせると
            # 自分の S を解放するまで誰も進めなくなる）
            queue.insert(0, Request(txn, "X", upgrade=True))
        else:
            # FIFO: 待ち行列が空で、保持者全員と両立するときだけ、すぐに与える
            if not queue and all(compatible(h, mode) for h in holders.values()):
                holders[txn] = mode
                return "granted"
            queue.append(Request(txn, mode))
        self._waiting_on[txn] = resource
        self._resolve_deadlocks(txn)
        state = self.status(txn)  # 犠牲者の解放によって、待たずに済んだ可能性もある
        return "granted" if state == "running" else state

    def release_all(self, txn: int) -> list[int]:
        if txn in self._finished or txn in self.aborted:
            return []
        granted = self._release(txn)
        self._finished.add(txn)
        return granted

    def _release(self, txn: int) -> list[int]:
        touched: list[str] = []
        waiting = self._waiting_on.pop(txn, None)
        if waiting is not None:
            self._queues[waiting] = [r for r in self._queues[waiting] if r.txn != txn]
            touched.append(waiting)
        for resource, holders in self._holders.items():
            if txn in holders:
                del holders[txn]
                touched.append(resource)
        granted: list[int] = []
        for resource in sorted(set(touched)):
            granted.extend(self._grant_waiters(resource))
        return granted

    def _grant_waiters(self, resource: str) -> list[int]:
        holders = self._holders.setdefault(resource, {})
        queue = self._queues.setdefault(resource, [])
        granted: list[int] = []
        # 先頭から順に、与えられるものを与える。与えられない要求に当たったら止める（追い越し禁止）
        while queue:
            req = queue[0]
            others = [m for t, m in holders.items() if t != req.txn]
            if not all(compatible(m, req.mode) for m in others):
                break
            queue.pop(0)
            holders[req.txn] = req.mode
            del self._waiting_on[req.txn]
            granted.append(req.txn)
        return granted

    # --- 演習2-2: 待ちグラフとデッドロック検出 ---------------------------------

    def wait_for_graph(self) -> dict[int, set[int]]:
        graph: dict[int, set[int]] = {}
        for resource, queue in self._queues.items():
            holders = self._holders.get(resource, {})
            for i, req in enumerate(queue):
                edges = {t for t, m in holders.items() if t != req.txn and not compatible(m, req.mode)}
                # FIFO なので、前に並んでいる両立しない要求が先に与えられるのを待つことになる
                edges |= {r.txn for r in queue[:i] if r.txn != req.txn and not compatible(r.mode, req.mode)}
                if edges:
                    graph.setdefault(req.txn, set()).update(edges)
        return {t: graph[t] for t in sorted(graph)}

    def find_cycle(self, start: int) -> list[int] | None:
        graph = self.wait_for_graph()
        path: list[int] = []
        visited: set[int] = set()

        def dfs(node: int) -> list[int] | None:
            path.append(node)
            visited.add(node)
            for nxt in sorted(graph.get(node, ())):
                if nxt == start:
                    return list(path)
                if nxt not in visited:
                    found = dfs(nxt)
                    if found:
                        return found
            path.pop()
            return None

        return dfs(start)

    def _resolve_deadlocks(self, requester: int) -> None:
        # 新しい待ちで生まれる閉路は、必ず要求者を通る
        while self.status(requester) == "waiting":
            cycle = self.find_cycle(requester)
            if cycle is None:
                return
            victim = max(cycle)  # 最も若い（番号の大きい）トランザクションを犠牲にする
            self.aborted.append(victim)
            self._release(victim)
