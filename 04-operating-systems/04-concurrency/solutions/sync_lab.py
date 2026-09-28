"""4.4 並行処理と同期 — 解答例: 同期プリミティブ・デッドロック・非同期の並行数制限

演習の仕様は exercises/sync_lab.py の docstring を参照してください。
"""
from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections import deque
from typing import Any, Awaitable, Generic, Hashable, Iterable, Iterator, Mapping, TypeVar

T = TypeVar("T")


def _deadline(timeout: float | None) -> float | None:
    if timeout is not None and timeout < 0:
        raise ValueError(f"timeout は 0 以上: {timeout}")
    return None if timeout is None else time.monotonic() + timeout


def _remaining(deadline: float | None) -> float | None:
    return None if deadline is None else deadline - time.monotonic()


# ---------------------------------------------------------------------------
# 演習1: 有界ブロッキングキュー
# ---------------------------------------------------------------------------

class QueueClosed(Exception):
    """閉じられたキューに put した、または閉じられて空になったキューから get した。"""


class BoundedBlockingQueue(Generic[T]):
    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"capacity は 1 以上: {capacity}")
        self._capacity = capacity
        self._items: deque[T] = deque()
        self._lock = threading.Lock()
        # 1 つのロックに 2 つの条件変数。「空でなくなった」と「満杯でなくなった」を別々に待てる
        self._not_empty = threading.Condition(self._lock)
        self._not_full = threading.Condition(self._lock)
        self._closed = False

    def put(self, item: T, timeout: float | None = None) -> None:
        deadline = _deadline(timeout)
        with self._not_full:
            # 条件は必ず while で確かめ直す。起こされても、条件が満たされているとは限らない
            # （他のスレッドに先を越された、見せかけの起床（spurious wakeup）など）
            while True:
                if self._closed:
                    raise QueueClosed("キューは閉じられています")
                if len(self._items) < self._capacity:
                    break
                remaining = _remaining(deadline)
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("put がタイムアウトしました")
                self._not_full.wait(remaining)  # ロックを手放して眠り、起きたらロックを取り直す
            self._items.append(item)
            self._not_empty.notify()  # get で待っている誰か 1 人を起こす

    def get(self, timeout: float | None = None) -> T:
        deadline = _deadline(timeout)
        with self._not_empty:
            while not self._items:
                if self._closed:
                    raise QueueClosed("キューは閉じられ、空になりました")
                remaining = _remaining(deadline)
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("get がタイムアウトしました")
                self._not_empty.wait(remaining)
            item = self._items.popleft()
            self._not_full.notify()
            return item

    def close(self) -> None:
        with self._lock:
            self._closed = True
            # 待っている全員を起こし、閉じられたことに気づかせる
            self._not_empty.notify_all()
            self._not_full.notify_all()

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


# ---------------------------------------------------------------------------
# 演習2: 書き込み優先の読み書きロック
# ---------------------------------------------------------------------------

class ReadWriteLock:
    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._readers = 0  # 読み取り中のスレッド数
        self._writer = False  # 書き込み中のスレッドがいるか
        self._waiting_writers = 0  # 書き込みの順番を待っているスレッド数

    def acquire_read(self, timeout: float | None = None) -> bool:
        deadline = _deadline(timeout)
        with self._cond:
            # 書き込み優先: 書き込み中だけでなく、書き込みを待っている人がいても新しい読み手は待つ。
            # そうしないと、読み手が途切れない限り書き手が永遠に入れない（飢餓）
            while self._writer or self._waiting_writers:
                remaining = _remaining(deadline)
                if remaining is not None and remaining <= 0:
                    return False
                self._cond.wait(remaining)
            self._readers += 1
            return True

    def release_read(self) -> None:
        with self._cond:
            if self._readers == 0:
                raise RuntimeError("読み取りロックを保持していません")
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()  # 待っている書き手を起こす

    def acquire_write(self, timeout: float | None = None) -> bool:
        deadline = _deadline(timeout)
        with self._cond:
            self._waiting_writers += 1
            acquired = False
            try:
                while self._writer or self._readers:
                    remaining = _remaining(deadline)
                    if remaining is not None and remaining <= 0:
                        return False
                    self._cond.wait(remaining)
                self._writer = acquired = True
                return True
            finally:
                self._waiting_writers -= 1
                if not acquired:
                    # タイムアウトで諦めた。自分が待っていたせいで止まっていた読み手を起こす（忘れやすい）
                    self._cond.notify_all()

    def release_write(self) -> None:
        with self._cond:
            if not self._writer:
                raise RuntimeError("書き込みロックを保持していません")
            self._writer = False
            self._cond.notify_all()

    @contextlib.contextmanager
    def read_locked(self) -> Iterator[None]:
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextlib.contextmanager
    def write_locked(self) -> Iterator[None]:
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()


# ---------------------------------------------------------------------------
# 演習3: デッドロックの検出と回避
# ---------------------------------------------------------------------------

def build_wait_for_graph(
    holders: Mapping[Hashable, Hashable], waiting: Mapping[Hashable, Hashable]
) -> dict[Hashable, set[Hashable]]:
    graph: dict[Hashable, set[Hashable]] = {}
    for thread, lock in waiting.items():
        holder = holders.get(lock)
        if holder is not None:
            # thread は、lock を持っている holder が手放すのを待っている（自分自身なら自己デッドロック）
            graph.setdefault(thread, set()).add(holder)
    return graph


def find_deadlock(wait_for: Mapping[Hashable, Iterable[Hashable]]) -> list[Hashable] | None:
    WHITE, GRAY, BLACK = 0, 1, 2  # 未訪問・探索中（今の経路上）・探索済み
    color: dict[Hashable, int] = {}
    for root in list(wait_for):
        if color.get(root, WHITE) != WHITE:
            continue
        # 再帰を使わない深さ優先探索（長い鎖でも再帰の深さの上限に当たらない）
        path: list[Hashable] = [root]
        iters: list[Iterator[Hashable]] = [iter(wait_for.get(root, ()))]
        color[root] = GRAY
        while iters:
            nxt = next(iters[-1], None)
            if nxt is None:
                color[path.pop()] = BLACK
                iters.pop()
                continue
            c = color.get(nxt, WHITE)
            if c == GRAY:
                return path[path.index(nxt):]  # 今の経路上のノードに戻ってきた = 循環待ち
            if c == WHITE:
                color[nxt] = GRAY
                path.append(nxt)
                iters.append(iter(wait_for.get(nxt, ())))
    return None


class InsufficientFunds(Exception):
    pass


class Account:
    def __init__(self, account_id: int, balance: int = 0) -> None:
        self.id = account_id
        self.balance = balance
        self.lock = threading.Lock()


def transfer(src: Account, dst: Account, amount: int) -> None:
    if amount <= 0:
        raise ValueError(f"amount は正の整数: {amount}")
    if src is dst or src.id == dst.id:
        raise ValueError("同じ口座どうしの送金はできません")
    # ロックは常に ID の小さい口座から取る。全員が同じ順序で取れば循環待ちは起こりえない
    first, second = (src, dst) if src.id < dst.id else (dst, src)
    with first.lock:
        with second.lock:
            if src.balance < amount:
                raise InsufficientFunds(f"口座 {src.id} の残高不足")
            src.balance -= amount
            dst.balance += amount


# ---------------------------------------------------------------------------
# 演習4: asyncio で並行数を制限しつつ、順序を保って結果を集める
# ---------------------------------------------------------------------------

async def gather_with_concurrency_limit(
    aws: Iterable[Awaitable[Any]],
    limit: int,
    *,
    timeout: float | None = None,
    return_exceptions: bool = False,
) -> list[Any]:
    aws = list(aws)
    if limit < 1:
        for aw in aws:
            _close(aw)  # 実行しないコルーチンは閉じておく（「一度も await されなかった」警告を防ぐ）
        raise ValueError(f"limit は 1 以上: {limit}")
    results: list[Any] = [None] * len(aws)
    pending = iter(enumerate(aws))  # 全ワーカーで共有する「次の仕事」の取り出し口

    async def worker() -> None:
        for i, aw in pending:
            try:
                if timeout is None:
                    results[i] = await aw
                else:
                    # タイムアウトは「実際に始まってから」数える
                    results[i] = await asyncio.wait_for(aw, timeout)
            except Exception as e:  # CancelledError（BaseException）はここで捕まえない
                if not return_exceptions:
                    raise
                results[i] = e

    # タスクを len(aws) 個ではなく limit 個だけ作る（ワーカープール）。仕事が 100 万個でも軽い
    workers = [asyncio.ensure_future(worker()) for _ in range(min(limit, len(aws)))]
    try:
        await asyncio.gather(*workers)
    except BaseException:
        for w in workers:
            w.cancel()  # 1 つが失敗したら残りを止める（結果を待つ人はもういない）
        await asyncio.gather(*workers, return_exceptions=True)
        for _, aw in pending:
            _close(aw)
        raise
    return results


def _close(aw: object) -> None:
    close = getattr(aw, "close", None)
    if callable(close):
        close()
