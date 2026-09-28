"""9.5 スケーラビリティとパフォーマンス — 解答例: レート制限・サーキットブレーカー・リトライ

演習の仕様は exercises/resilience.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import random
import threading
import time
from collections import deque
from typing import Callable, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1: レート制限
# ---------------------------------------------------------------------------

class TokenBucket:
    def __init__(self, rate: float, capacity: float, clock: Callable[[], float] = time.monotonic) -> None:
        if rate <= 0 or capacity <= 0:
            raise ValueError("rate と capacity は正の数です")
        self.rate = rate
        self.capacity = capacity
        self._clock = clock
        self._tokens = float(capacity)  # 最初は満タン（起動直後のバーストを許す）
        self._last = clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._last)  # 時計が戻っても、トークンを減らさない
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last = now

    def _check(self, n: float) -> None:
        if n <= 0 or n > self.capacity:
            raise ValueError(f"n は 0 より大きく capacity 以下です: {n}")

    def try_acquire(self, n: float = 1.0) -> bool:
        self._check(n)
        with self._lock:
            self._refill()
            if self._tokens >= n:
                self._tokens -= n
                return True
            return False

    def wait_time(self, n: float = 1.0) -> float:
        self._check(n)
        with self._lock:
            self._refill()
            return max(0.0, (n - self._tokens) / self.rate)

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens


class SlidingWindowCounter:
    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        if limit <= 0 or window <= 0:
            raise ValueError("limit と window は正の数です")
        self.limit = limit
        self.window = window
        self._clock = clock
        # 窓は「何番目の窓か」という整数で管理する（浮動小数点の窓の開始時刻どうしを == で比べない）
        self._index = math.floor(clock() / window)
        self._curr = 0
        self._prev = 0
        self._lock = threading.Lock()

    def _roll(self, now: float) -> None:
        index = math.floor(now / self.window)
        if index <= self._index:
            return  # 同じ窓（または時計が戻った）
        # 1 つ前の窓の件数だけを覚えておく。2 つ以上進んだら、前の窓は空だったことになる
        self._prev = self._curr if index == self._index + 1 else 0
        self._curr = 0
        self._index = index

    def _estimate(self, now: float) -> float:
        # 前の窓の件数を「今の窓と重なっている割合」で按分する（前の窓の中では一様に来たと仮定する近似）
        elapsed = max(0.0, now - self._index * self.window)
        overlap = max(0.0, (self.window - elapsed) / self.window)
        return self._prev * overlap + self._curr

    def estimated(self) -> float:
        with self._lock:
            now = self._clock()
            self._roll(now)
            return self._estimate(now)

    def try_acquire(self) -> bool:
        with self._lock:
            now = self._clock()
            self._roll(now)
            if self._estimate(now) + 1 <= self.limit:
                self._curr += 1
                return True
            return False


# ---------------------------------------------------------------------------
# 演習2: サーキットブレーカー
# ---------------------------------------------------------------------------

class CircuitOpenError(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__(f"サーキットが開いています（{retry_after:.1f} 秒後に再試行できます）")
        self.retry_after = retry_after


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(
        self,
        *,
        failure_threshold: float = 0.5,
        window_size: int = 20,
        minimum_calls: int = 10,
        cooldown: float = 30.0,
        half_open_max_calls: int = 3,
        clock: Callable[[], float] = time.monotonic,
        is_failure: Callable[[BaseException], bool] = lambda exc: True,
    ) -> None:
        if not 0 < failure_threshold <= 1:
            raise ValueError("failure_threshold は (0, 1] の範囲です")
        if window_size <= 0 or not 0 < minimum_calls <= window_size:
            raise ValueError("0 < minimum_calls <= window_size である必要があります")
        if cooldown < 0 or half_open_max_calls <= 0:
            raise ValueError("cooldown は 0 以上、half_open_max_calls は正の数です")
        self.failure_threshold = failure_threshold
        self.minimum_calls = minimum_calls
        self.cooldown = cooldown
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._is_failure = is_failure
        self._window: deque[bool] = deque(maxlen=window_size)  # True = 失敗
        self._state = self.CLOSED
        self._opened_at = 0.0
        self._trials_started = 0
        self._trial_successes = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            self._maybe_half_open()
            return self._state

    def failure_rate(self) -> float:
        with self._lock:
            return sum(self._window) / len(self._window) if self._window else 0.0

    def _maybe_half_open(self) -> None:
        if self._state == self.OPEN and self._clock() - self._opened_at >= self.cooldown:
            self._state = self.HALF_OPEN
            self._trials_started = 0
            self._trial_successes = 0

    def _open(self) -> None:
        self._state = self.OPEN
        self._opened_at = self._clock()
        self._window.clear()

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        with self._lock:
            self._maybe_half_open()
            if self._state == self.OPEN:
                raise CircuitOpenError(self.cooldown - (self._clock() - self._opened_at))
            if self._state == self.HALF_OPEN:
                if self._trials_started >= self.half_open_max_calls:
                    # 試行の枠を使い切っている間は、結果が出るまで他の呼び出しを通さない
                    raise CircuitOpenError(0.0)
                self._trials_started += 1
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:
            self._record(failed=self._is_failure(exc))
            raise
        self._record(failed=False)
        return result

    def _record(self, failed: bool) -> None:
        with self._lock:
            if self._state == self.HALF_OPEN:
                if failed:
                    self._open()  # 試行が 1 つでも失敗したら、また冷却期間に戻る
                else:
                    self._trial_successes += 1
                    if self._trial_successes >= self.half_open_max_calls:
                        self._state = self.CLOSED
                        self._window.clear()
                return
            if self._state == self.OPEN:
                return  # 開く前に始まった呼び出しの結果は数えない
            self._window.append(failed)
            if len(self._window) >= self.minimum_calls:
                if sum(self._window) / len(self._window) >= self.failure_threshold:
                    self._open()


# ---------------------------------------------------------------------------
# 演習3: 指数バックオフ＋フルジッターのリトライと、リトライ予算
# ---------------------------------------------------------------------------

class RetryBudget:
    def __init__(self, ratio: float = 0.1, initial_tokens: float = 10.0, max_tokens: float = 100.0) -> None:
        if ratio < 0 or initial_tokens < 0 or max_tokens <= 0:
            raise ValueError("不正なパラメータです")
        self.ratio = ratio
        self.max_tokens = max_tokens
        self._tokens = min(initial_tokens, max_tokens)
        self._lock = threading.Lock()

    @property
    def tokens(self) -> float:
        with self._lock:
            return self._tokens

    def on_request(self) -> None:
        with self._lock:
            self._tokens = min(self.max_tokens, self._tokens + self.ratio)

    def try_spend(self) -> bool:
        with self._lock:
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False


def full_jitter_delay(attempt: int, base: float, cap: float, rng: random.Random) -> float:
    # Marc Brooker の "Exponential Backoff And Jitter"（AWS, 2015）の Full Jitter:
    #   sleep = random_between(0, min(cap, base * 2 ** attempt))
    return rng.uniform(0, min(cap, base * 2 ** (attempt - 1)))


def retry_call(
    fn: Callable[[], T],
    *,
    max_attempts: int = 4,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    deadline: float | None = None,
    retry_on: Callable[[BaseException], bool] = lambda exc: True,
    rng: random.Random | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    budget: RetryBudget | None = None,
) -> T:
    if max_attempts < 1:
        raise ValueError("max_attempts は 1 以上です")
    rng = rng or random.Random()
    start = clock()
    if budget is not None:
        budget.on_request()  # 最初の試行（本来のリクエスト）が予算を積み立てる
    attempt = 1
    while True:
        try:
            return fn()
        except Exception as exc:
            if not retry_on(exc) or attempt >= max_attempts:
                raise
            delay = full_jitter_delay(attempt, base_delay, max_delay, rng)
            # 待っても期限内に次の試行を始められないなら、ここで諦める（無駄な待ちをしない）
            if deadline is not None and (clock() - start) + delay > deadline:
                raise
            # 予算がなければ再試行しない（障害時にリトライが負荷を何倍にも増やすのを防ぐ）
            if budget is not None and not budget.try_spend():
                raise
            sleep(delay)
            attempt += 1
