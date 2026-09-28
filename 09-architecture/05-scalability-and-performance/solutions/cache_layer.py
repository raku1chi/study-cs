"""9.5 スケーラビリティとパフォーマンス — 解答例: 単一飛行（single-flight）と stale-while-revalidate のキャッシュ

演習の仕様は exercises/cache_layer.py の docstring を参照してください。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from typing import Callable, Generic, TypeVar

V = TypeVar("V")


@dataclass(frozen=True)
class CacheStats:
    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    loads: int = 0
    coalesced: int = 0
    refresh_errors: int = 0


@dataclass
class _Entry(Generic[V]):
    value: V
    loaded_at: float


class _Flight:
    """実行中の読み込み 1 つ。待っている呼び出しは event で完了を待つ。"""

    def __init__(self) -> None:
        self.event = threading.Event()
        self.value = None
        self.error: BaseException | None = None
        self.waiters = 0


def _start_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


class CoalescingCache(Generic[V]):
    def __init__(
        self,
        loader: Callable[[str], V],
        *,
        ttl: float,
        stale_ttl: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _start_thread,
    ) -> None:
        if ttl <= 0 or stale_ttl < 0:
            raise ValueError("ttl は正、stale_ttl は 0 以上です")
        self._loader = loader
        self._ttl = ttl
        self._stale_ttl = stale_ttl
        self._clock = clock
        self._spawn = spawn
        self._entries: dict[str, _Entry[V]] = {}
        self._flights: dict[str, _Flight] = {}
        self._refreshing: set[str] = set()
        self._generation: dict[str, int] = {}
        self._stats = CacheStats()
        self._lock = threading.Lock()

    @property
    def stats(self) -> CacheStats:
        with self._lock:
            return self._stats

    def _count(self, **deltas: int) -> None:
        self._stats = replace(self._stats, **{k: getattr(self._stats, k) + v for k, v in deltas.items()})

    def get(self, key: str) -> V:
        refresh = None
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                age = self._clock() - entry.loaded_at
                if age < self._ttl:
                    self._count(hits=1)
                    return entry.value
                if age < self._ttl + self._stale_ttl:
                    # 古いが許容範囲内: すぐに古い値を返し、裏で 1 回だけ更新する
                    self._count(stale_hits=1)
                    if key not in self._refreshing:
                        self._refreshing.add(key)
                        generation = self._generation.get(key, 0)
                        refresh = lambda: self._refresh(key, generation)  # noqa: E731
                    stale_value = entry.value
                else:
                    entry = None
            if entry is None:
                self._count(misses=1)
                flight = self._flights.get(key)
                if flight is not None:
                    # 同じキーの読み込みが実行中: 自分では読み込まず、その結果を待つ（single-flight）
                    flight.waiters += 1
                    self._count(coalesced=1)
                    leader = False
                else:
                    flight = _Flight()
                    self._flights[key] = flight
                    generation = self._generation.get(key, 0)
                    self._count(loads=1)
                    leader = True

        if entry is not None:
            # 更新の依頼はロックを放してから（spawn がその場で実行する実装でもデッドロックしない）
            if refresh is not None:
                self._spawn(refresh)
            return stale_value

        if not leader:
            flight.event.wait()
            with self._lock:
                flight.waiters -= 1
            if flight.error is not None:
                raise flight.error
            return flight.value

        # 読み込みはロックの外で行う（遅いオリジンを待つ間、他のキーを止めない）
        try:
            value = self._loader(key)
        except BaseException as exc:
            with self._lock:
                flight.error = exc
                del self._flights[key]  # 失敗は保存しない。次の get はまた読み込む
            flight.event.set()
            raise
        with self._lock:
            flight.value = value
            # 読み込みの間に invalidate されていたら、古いかもしれない値を保存しない
            if self._generation.get(key, 0) == generation:
                self._entries[key] = _Entry(value, self._clock())
            del self._flights[key]
        flight.event.set()
        return value

    def _refresh(self, key: str, generation: int) -> None:
        try:
            value = self._loader(key)
        except Exception:
            with self._lock:
                self._count(refresh_errors=1)
                self._refreshing.discard(key)  # 古い値は残す。次の古い読み取りで再び更新を試みる
            return
        with self._lock:
            if self._generation.get(key, 0) == generation:
                self._entries[key] = _Entry(value, self._clock())
            self._refreshing.discard(key)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._entries.pop(key, None)
            # 世代を進めて、実行中の読み込み・更新の結果が保存されないようにする
            self._generation[key] = self._generation.get(key, 0) + 1

    def waiting_count(self, key: str) -> int:
        with self._lock:
            flight = self._flights.get(key)
            return flight.waiters if flight is not None else 0
