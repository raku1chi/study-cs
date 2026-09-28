"""9.5 スケーラビリティとパフォーマンス — 演習2〜4 のテスト（レート制限・サーキットブレーカー・リトライ）

時計はすべて偽物（FakeClock）で、実際には待ちません。

実行: python3 tools/check.py 9.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import threading
import unittest

from resilience import (
    CircuitBreaker,
    CircuitOpenError,
    RetryBudget,
    SlidingWindowCounter,
    TokenBucket,
    full_jitter_delay,
    retry_call,
)


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds

    def sleep(self, seconds):  # retry_call に渡す「待つ関数」: 時計を進めるだけ
        self.slept.append(seconds)
        self.now += seconds

    slept = None


# ---------------------------------------------------------------------------
# 演習2: レート制限
# ---------------------------------------------------------------------------

class TestExercise2TokenBucket(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.bucket = TokenBucket(rate=2.0, capacity=4.0, clock=self.clock)

    def test_burst_up_to_capacity(self):
        self.assertEqual([self.bucket.try_acquire() for _ in range(5)], [True, True, True, True, False])

    def test_refills_at_rate(self):
        for _ in range(4):
            self.bucket.try_acquire()
        self.clock.advance(0.5)                     # 0.5 秒 × 2 個/秒 = 1 個
        self.assertTrue(self.bucket.try_acquire())
        self.assertFalse(self.bucket.try_acquire())
        self.clock.advance(100)                     # 長く待っても capacity を超えない
        self.assertEqual(self.bucket.tokens, 4.0)

    def test_wait_time(self):
        for _ in range(4):
            self.bucket.try_acquire()
        self.assertEqual(self.bucket.wait_time(), 0.5)
        self.assertEqual(self.bucket.wait_time(3), 1.5)
        self.clock.advance(0.5)
        self.assertEqual(self.bucket.wait_time(), 0.0)

    def test_failed_acquire_takes_nothing(self):
        self.bucket.try_acquire(3)
        self.assertFalse(self.bucket.try_acquire(2))
        self.assertEqual(self.bucket.tokens, 1.0)

    def test_clock_going_backwards_does_not_remove_tokens(self):
        self.bucket.try_acquire(2)
        self.clock.advance(-10)
        self.assertEqual(self.bucket.tokens, 2.0)

    def test_validation(self):
        for kwargs in ({"rate": 0, "capacity": 1}, {"rate": 1, "capacity": 0}, {"rate": -1, "capacity": 1}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                TokenBucket(clock=self.clock, **kwargs)
        for n in (0, -1, 5):
            with self.assertRaises(ValueError, msg=str(n)):
                self.bucket.try_acquire(n)

    def test_thread_safety(self):
        bucket = TokenBucket(rate=1e-9, capacity=1000, clock=self.clock)
        granted = []

        def worker():
            n = sum(bucket.try_acquire() for _ in range(300))
            granted.append(n)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual(sum(granted), 1000, "同時に呼ばれても、ちょうど capacity 個だけ許可する")


class TestExercise2SlidingWindow(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = SlidingWindowCounter(limit=10, window=10.0, clock=self.clock)

    def test_limit_within_one_window(self):
        results = [self.limiter.try_acquire() for _ in range(12)]
        self.assertEqual(results.count(True), 10)
        self.assertFalse(results[-1])

    def test_previous_window_is_weighted(self):
        for _ in range(10):
            self.limiter.try_acquire()             # 0〜10 秒の窓で 10 件
        self.clock.now = 12.5                       # 次の窓の 25% の位置: 前の窓と 75% 重なる
        self.assertEqual(self.limiter.estimated(), 7.5)
        self.assertEqual([self.limiter.try_acquire() for _ in range(3)], [True, True, False])
        self.assertEqual(self.limiter.estimated(), 9.5)
        self.clock.now = 17.5                       # 重なり 25%: 10 × 0.25 + 2 = 4.5
        self.assertEqual(self.limiter.estimated(), 4.5)

    def test_no_double_burst_at_window_boundary(self):
        self.clock.now = 9.9
        burst1 = sum(self.limiter.try_acquire() for _ in range(10))
        self.clock.now = 10.0                       # 窓が切り替わった直後
        burst2 = sum(self.limiter.try_acquire() for _ in range(10))
        self.assertEqual(burst1, 10)
        self.assertEqual(burst2, 0, "固定窓なら 20 件通ってしまうが、推定では前の窓の 10 件がまだ効いている")

    def test_skipping_windows_forgets_old_counts(self):
        for _ in range(10):
            self.limiter.try_acquire()
        self.clock.now = 25.0                       # 2 つ先の窓: 前の窓（10〜20 秒）は 0 件
        self.assertEqual(self.limiter.estimated(), 0)
        self.assertTrue(self.limiter.try_acquire())

    def test_validation(self):
        with self.assertRaises(ValueError):
            SlidingWindowCounter(limit=0, window=1, clock=self.clock)
        with self.assertRaises(ValueError):
            SlidingWindowCounter(limit=1, window=0, clock=self.clock)


# ---------------------------------------------------------------------------
# 演習3: サーキットブレーカー
# ---------------------------------------------------------------------------

class Flaky:
    """fail が True の間は失敗する依存先。"""

    def __init__(self):
        self.fail = False
        self.calls = 0

    def __call__(self, value="ok"):
        self.calls += 1
        if self.fail:
            raise ConnectionError("依存先が応答しない")
        return value


class TestExercise3CircuitBreaker(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.dep = Flaky()
        self.cb = CircuitBreaker(failure_threshold=0.5, window_size=10, minimum_calls=4, cooldown=30,
                                 half_open_max_calls=2, clock=self.clock)

    def fail_n(self, n):
        self.dep.fail = True
        for _ in range(n):
            with self.assertRaises(ConnectionError):
                self.cb.call(self.dep)
        self.dep.fail = False

    def test_closed_passes_calls_through(self):
        self.assertEqual(self.cb.call(self.dep, "hello"), "hello")
        self.assertEqual(self.cb.call(lambda a, b=0: a + b, 1, b=2), 3)
        self.assertEqual(self.cb.state, CircuitBreaker.CLOSED)

    def test_minimum_calls_before_opening(self):
        self.fail_n(3)
        self.assertEqual(self.cb.state, CircuitBreaker.CLOSED, "記録が minimum_calls 未満では開かない")
        self.assertEqual(self.cb.failure_rate(), 1.0)
        self.fail_n(1)
        self.assertEqual(self.cb.state, CircuitBreaker.OPEN)

    def test_failure_rate_threshold(self):
        for _ in range(6):
            self.cb.call(self.dep)
        self.fail_n(4)                              # 10 件中 4 件失敗 = 40%
        self.assertEqual(self.cb.state, CircuitBreaker.CLOSED)
        self.fail_n(1)                              # 直近 10 件（成功 5・失敗 5）= 50%
        self.assertEqual(self.cb.state, CircuitBreaker.OPEN)

    def test_open_rejects_without_calling(self):
        self.fail_n(4)
        calls = self.dep.calls
        self.clock.advance(10)
        with self.assertRaises(CircuitOpenError) as cm:
            self.cb.call(self.dep)
        self.assertEqual(self.dep.calls, calls, "開いている間は依存先を呼ばない")
        self.assertAlmostEqual(cm.exception.retry_after, 20)

    def test_half_open_success_closes(self):
        self.fail_n(4)
        self.clock.advance(30)
        self.assertEqual(self.cb.state, CircuitBreaker.HALF_OPEN)
        self.cb.call(self.dep)
        self.assertEqual(self.cb.state, CircuitBreaker.HALF_OPEN)
        self.cb.call(self.dep)
        self.assertEqual(self.cb.state, CircuitBreaker.CLOSED)
        self.assertEqual(self.cb.failure_rate(), 0.0, "閉じたら記録は空から")

    def test_half_open_failure_reopens(self):
        self.fail_n(4)
        self.clock.advance(30)
        self.fail_n(1)
        self.assertEqual(self.cb.state, CircuitBreaker.OPEN)
        self.clock.advance(29)
        self.assertEqual(self.cb.state, CircuitBreaker.OPEN, "冷却期間は最初からやり直し")
        self.clock.advance(1)
        self.assertEqual(self.cb.state, CircuitBreaker.HALF_OPEN)

    def test_half_open_limits_concurrent_trials(self):
        self.fail_n(4)
        self.clock.advance(30)
        entered = threading.Semaphore(0)
        release = threading.Event()
        errors = []

        def slow_trial():
            entered.release()
            release.wait(5)
            return "ok"

        def run():
            try:
                self.cb.call(slow_trial)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        trials = [threading.Thread(target=run, daemon=True) for _ in range(2)]
        for t in trials:
            t.start()
        for _ in range(2):  # 2 つの試行が両方とも実行中になるまで待つ
            if not entered.acquire(timeout=5):
                release.set()
                self.fail(f"試行が始まらない: {errors}")
        calls = self.dep.calls
        with self.assertRaises(CircuitOpenError, msg="試行の枠を超えた呼び出しは通さない"):
            self.cb.call(self.dep)
        self.assertEqual(self.dep.calls, calls)
        release.set()
        for t in trials:
            t.join(5)
            self.assertFalse(t.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(self.cb.state, CircuitBreaker.CLOSED)

    def test_ignored_exceptions_count_as_success(self):
        class NotFound(Exception):
            pass

        cb = CircuitBreaker(minimum_calls=2, window_size=4, clock=self.clock,
                            is_failure=lambda exc: not isinstance(exc, NotFound))

        def missing():
            raise NotFound("該当なし")

        for _ in range(4):
            with self.assertRaises(NotFound):
                cb.call(missing)
        self.assertEqual(cb.state, CircuitBreaker.CLOSED)
        self.assertEqual(cb.failure_rate(), 0.0)

    def test_validation(self):
        for kwargs in ({"failure_threshold": 0}, {"failure_threshold": 1.5}, {"minimum_calls": 0},
                       {"minimum_calls": 30, "window_size": 20}, {"cooldown": -1}, {"half_open_max_calls": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                CircuitBreaker(clock=self.clock, **kwargs)


# ---------------------------------------------------------------------------
# 演習4: リトライ
# ---------------------------------------------------------------------------

class Failing:
    def __init__(self, failures, exc=ConnectionError):
        self.failures = failures
        self.calls = 0
        self.exc = exc

    def __call__(self):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.exc(f"失敗 {self.calls}")
        return "ok"


class TestExercise4Retry(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(100.0)
        self.clock.slept = []

    def expected_delays(self, seed, n, base=0.1, cap=2.0):
        rng = random.Random(seed)
        return [rng.uniform(0, min(cap, base * 2 ** k)) for k in range(n)]

    def test_full_jitter_delay(self):
        rng = random.Random(1)
        delays = [full_jitter_delay(a, 0.1, 1.0, rng) for a in range(1, 8)]
        ref = random.Random(1)
        self.assertEqual(delays, [ref.uniform(0, min(1.0, 0.1 * 2 ** (a - 1))) for a in range(1, 8)])
        for a, d in enumerate(delays, start=1):
            self.assertLessEqual(d, min(1.0, 0.1 * 2 ** (a - 1)))

    def test_retries_until_success(self):
        fn = Failing(2)
        result = retry_call(fn, rng=random.Random(42), sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(result, "ok")
        self.assertEqual(fn.calls, 3)
        self.assertEqual(self.clock.slept, self.expected_delays(42, 2))

    def test_gives_up_after_max_attempts(self):
        fn = Failing(10)
        with self.assertRaises(ConnectionError) as cm:
            retry_call(fn, max_attempts=4, rng=random.Random(7), sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(str(cm.exception), "失敗 4", "最後の例外をそのまま送出する")
        self.assertEqual(fn.calls, 4)
        self.assertEqual(len(self.clock.slept), 3)

    def test_non_retryable_errors_are_raised_immediately(self):
        fn = Failing(10, exc=ValueError)
        with self.assertRaises(ValueError):
            retry_call(fn, retry_on=lambda e: isinstance(e, ConnectionError), sleep=self.clock.sleep,
                       clock=self.clock, rng=random.Random(0))
        self.assertEqual(fn.calls, 1)
        self.assertEqual(self.clock.slept, [])

    def test_delays_are_capped(self):
        fn = Failing(9)
        retry_call(fn, max_attempts=10, base_delay=1.0, max_delay=4.0, rng=random.Random(3),
                   sleep=self.clock.sleep, clock=self.clock)
        self.assertEqual(self.clock.slept, self.expected_delays(3, 9, base=1.0, cap=4.0))
        self.assertTrue(all(d <= 4.0 for d in self.clock.slept))

    def test_deadline_stops_retrying(self):
        fn = Failing(100)
        with self.assertRaises(ConnectionError):
            retry_call(fn, max_attempts=100, base_delay=1.0, max_delay=8.0, deadline=10.0,
                       rng=random.Random(5), sleep=self.clock.sleep, clock=self.clock)
        self.assertLessEqual(self.clock.now - 100.0, 10.0, "期限を超えて待たない")
        # 期限を超えないぎりぎりまで再試行している（次の待ち時間を足すと期限を超える）
        rng = random.Random(5)
        elapsed, attempts = 0.0, 0
        while True:
            attempts += 1
            d = rng.uniform(0, min(8.0, 1.0 * 2 ** (attempts - 1)))
            if elapsed + d > 10.0:
                break
            elapsed += d
        self.assertEqual(fn.calls, attempts)

    def test_retry_budget(self):
        budget = RetryBudget(ratio=0.1, initial_tokens=2, max_tokens=5)
        self.assertEqual(budget.tokens, 2)
        fn = Failing(100)
        with self.assertRaises(ConnectionError):
            retry_call(fn, max_attempts=10, budget=budget, rng=random.Random(0), sleep=self.clock.sleep,
                       clock=self.clock)
        # 最初の試行で 0.1 を積み立て、残高 2.1 のうち 2 回分だけ再試行できる
        self.assertEqual(fn.calls, 3)
        self.assertAlmostEqual(budget.tokens, 0.1)

    def test_budget_accumulates_and_caps(self):
        budget = RetryBudget(ratio=0.5, initial_tokens=0, max_tokens=2)
        self.assertFalse(budget.try_spend())
        budget.on_request()
        budget.on_request()
        self.assertTrue(budget.try_spend())
        for _ in range(100):
            budget.on_request()
        self.assertEqual(budget.tokens, 2)
        self.assertEqual(RetryBudget(initial_tokens=500, max_tokens=100).tokens, 100)
        with self.assertRaises(ValueError):
            RetryBudget(ratio=-0.1)

    def test_max_attempts_validation(self):
        with self.assertRaises(ValueError):
            retry_call(lambda: 1, max_attempts=0)


if __name__ == "__main__":
    unittest.main()
