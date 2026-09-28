"""5.4 Webの仕組みとネットワーク構成 — 解答例（lb）

演習の仕様は exercises/lb.py の docstring を参照してください。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass
class Backend:
    name: str
    weight: int = 1
    healthy: bool = True
    draining: bool = False
    active_connections: int = 0


class NoAvailableBackend(RuntimeError):
    """振り分け先の候補が 1 つもない。"""


class Strategy(Protocol):
    def choose(self, candidates: Sequence[Backend]) -> Backend: ...


# ---------------------------------------------------------------------------
# 演習1: 振り分けのアルゴリズム
# ---------------------------------------------------------------------------

class RoundRobin:
    def __init__(self) -> None:
        self._counter = 0

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        backend = candidates[self._counter % len(candidates)]
        self._counter += 1
        return backend


class SmoothWeightedRoundRobin:
    """nginx の重み付きラウンドロビン。重いサーバーに連続して偏らず、なめらかに混ぜる。"""

    def __init__(self) -> None:
        self._current: dict[str, int] = {}

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        total = 0
        best: Backend | None = None
        for backend in candidates:
            # 各候補の「現在の重み」に、設定された重みを足す
            self._current[backend.name] = self._current.get(backend.name, 0) + backend.weight
            total += backend.weight
            if best is None or self._current[backend.name] > self._current[best.name]:
                best = backend  # 同点なら先に現れた方
        assert best is not None
        # 選ばれたものからは全体の重みを引く。これで次は選ばれにくくなる
        self._current[best.name] -= total
        return best


class LeastConnections:
    def choose(self, candidates: Sequence[Backend]) -> Backend:
        return min(candidates, key=lambda b: b.active_connections)  # min は同点なら先頭を返す


class PowerOfTwoChoices:
    """ランダムに 2 つ選び、接続の少ない方を使う。全体を調べずに、偏りを大きく減らせる。"""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def choose(self, candidates: Sequence[Backend]) -> Backend:
        if len(candidates) == 1:
            return candidates[0]
        a, b = self.rng.sample(list(candidates), 2)
        return b if b.active_connections < a.active_connections else a


# ---------------------------------------------------------------------------
# 演習1: ロードバランサ本体（ヘルスチェックとコネクションドレイン）
# ---------------------------------------------------------------------------

class LoadBalancer:
    def __init__(self, backends: Sequence[Backend], strategy: Strategy) -> None:
        names = [b.name for b in backends]
        if not backends or len(set(names)) != len(names):
            raise ValueError(f"バックエンドは 1 つ以上、名前の重複なしで指定してください: {names}")
        for b in backends:
            if b.weight < 1:
                raise ValueError(f"重みは 1 以上です: {b.name}={b.weight}")
        self.backends = list(backends)
        self.strategy = strategy
        self._by_name = {b.name: b for b in backends}

    def backend(self, name: str) -> Backend:
        return self._by_name[name]  # なければ KeyError

    def eligible(self) -> list[Backend]:
        # 新しい接続を受けてよいのは「正常」かつ「ドレイン中でない」もの（設定の順序を保つ）
        return [b for b in self.backends if b.healthy and not b.draining]

    def acquire(self) -> Backend:
        candidates = self.eligible()
        if not candidates:
            raise NoAvailableBackend("正常なバックエンドがありません")
        backend = self.strategy.choose(candidates)
        backend.active_connections += 1
        return backend

    def release(self, backend: Backend | str) -> None:
        b = self.backend(backend) if isinstance(backend, str) else self.backend(backend.name)
        if b.active_connections <= 0:
            raise ValueError(f"{b.name} には解放する接続がありません")
        b.active_connections -= 1

    def set_health(self, name: str, healthy: bool) -> None:
        self.backend(name).healthy = healthy

    def drain(self, name: str) -> None:
        # 新しい接続は送らないが、処理中の接続はそのまま終わるのを待つ
        self.backend(name).draining = True

    def undrain(self, name: str) -> None:
        self.backend(name).draining = False

    def is_drained(self, name: str) -> bool:
        b = self.backend(name)
        return b.draining and b.active_connections == 0


class HealthChecker:
    """連続した成功・失敗の回数で状態を切り替える（HAProxy の rise / fall と同じ考え方）。"""

    def __init__(self, lb: LoadBalancer, *, rise: int = 2, fall: int = 3) -> None:
        if rise < 1 or fall < 1:
            raise ValueError("rise と fall は 1 以上です")
        self.lb = lb
        self.rise = rise
        self.fall = fall
        self._successes: dict[str, int] = {}
        self._failures: dict[str, int] = {}

    def record(self, name: str, ok: bool) -> None:
        backend = self.lb.backend(name)
        if ok:
            self._failures[name] = 0
            self._successes[name] = self._successes.get(name, 0) + 1
            if not backend.healthy and self._successes[name] >= self.rise:
                backend.healthy = True
        else:
            self._successes[name] = 0
            self._failures[name] = self._failures.get(name, 0) + 1
            if backend.healthy and self._failures[name] >= self.fall:
                backend.healthy = False  # 1 回の失敗では外さない（一時的な揺らぎで振り分けが暴れないように）
