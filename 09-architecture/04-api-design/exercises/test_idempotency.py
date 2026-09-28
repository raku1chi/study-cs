"""9.4 API設計 — 冪等キーの層のテスト

スレッドを使うテストは、handler の中で threading.Event を待たせることで、
「実行中に同じキーが届いた」状況を決定的に作り出しています（sleep に頼らない）。

実行: python3 tools/check.py 9.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import threading
import time
import unittest

from idempotency import REPLAY_HEADER, IdempotencyLayer, Request, Response, fingerprint


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def charge(amount=1000, client="shop-1", path="/v1/payments"):
    return Request(client, "POST", path, {"amount": amount, "currency": "JPY", "customer": "c1"})


class CountingHandler:
    """呼ばれた回数を数え、支払い ID を順に払い出すハンドラ。"""

    def __init__(self, statuses=None, block=None, error=None):
        self.calls = 0
        self.statuses = list(statuses or [])
        self.block = block          # threading.Event: セットされるまで処理を終えない
        self.entered = threading.Event()
        self.error = error
        self.lock = threading.Lock()

    def __call__(self, request):
        with self.lock:
            self.calls += 1
            n = self.calls
        self.entered.set()
        if self.block is not None:
            assert self.block.wait(5), "テストがハンドラを解放しなかった"
        if self.error is not None:
            raise self.error
        status = self.statuses.pop(0) if self.statuses else 201
        return Response(status, {"payment_id": f"pay_{n}", "amount": request.body["amount"]})


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.001)
    return False


class TestExercise3Fingerprint(unittest.TestCase):
    def test_is_sha256_hex(self):
        fp = fingerprint(charge())
        self.assertEqual(len(fp), 64)
        int(fp, 16)

    def test_ignores_key_order_and_method_case(self):
        a = Request("c", "post", "/v1/payments", {"amount": 1000, "meta": {"x": 1, "y": "日本"}})
        b = Request("c", "POST", "/v1/payments", {"meta": {"y": "日本", "x": 1}, "amount": 1000})
        self.assertEqual(fingerprint(a), fingerprint(b))

    def test_detects_different_content(self):
        base = fingerprint(charge())
        self.assertNotEqual(base, fingerprint(charge(amount=1001)))
        self.assertNotEqual(base, fingerprint(charge(path="/v1/refunds")))
        self.assertNotEqual(base, fingerprint(Request("shop-1", "PUT", "/v1/payments", charge().body)))
        self.assertEqual(base, fingerprint(charge(client="other")), "client_id は指紋に含めない")


class TestExercise3Basics(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.handler = CountingHandler()
        self.layer = IdempotencyLayer(self.handler, ttl=3600, clock=self.clock)

    def test_missing_or_invalid_key(self):
        for key in (None, ""):
            r = self.layer.handle(key, charge())
            self.assertEqual(r.status, 400)
            self.assertTrue(r.body["type"].endswith("idempotency-key-required"))
        for key in ("x" * 256, "has space", "日本語のキー", "tab\tkey"):
            r = self.layer.handle(key, charge())
            self.assertEqual(r.status, 400, repr(key))
            self.assertTrue(r.body["type"].endswith("invalid-idempotency-key"))
        self.assertEqual(self.layer.handle("k" * 255, charge()).status, 201)
        self.assertEqual(self.handler.calls, 1)

    def test_retry_returns_stored_response(self):
        first = self.layer.handle("key-1", charge())
        self.assertEqual((first.status, first.body["payment_id"]), (201, "pay_1"))
        self.assertNotIn(REPLAY_HEADER, first.headers)
        again = self.layer.handle("key-1", charge())
        self.assertEqual((again.status, again.body), (first.status, first.body))
        self.assertEqual(again.headers.get(REPLAY_HEADER), "true")
        self.assertEqual(self.handler.calls, 1)
        self.assertEqual(self.layer.executions, 1)

    def test_new_key_executes_again(self):
        self.layer.handle("key-1", charge())
        self.assertEqual(self.layer.handle("key-2", charge()).body["payment_id"], "pay_2")

    def test_same_key_different_payload_is_rejected(self):
        self.layer.handle("key-1", charge(amount=1000))
        r = self.layer.handle("key-1", charge(amount=9999))
        self.assertEqual(r.status, 422)
        self.assertTrue(r.body["type"].endswith("idempotency-key-reused"))
        self.assertEqual(r.body["status"], 422)
        self.assertEqual(self.layer.handle("key-1", charge(amount=1000)).body["payment_id"], "pay_1",
                         "元のリクエストの再送は引き続き再生される")
        self.assertEqual(self.handler.calls, 1)

    def test_keys_are_scoped_per_client(self):
        a = self.layer.handle("key-1", charge(client="shop-1"))
        b = self.layer.handle("key-1", charge(client="shop-2"))
        self.assertNotEqual(a.body["payment_id"], b.body["payment_id"])
        self.assertEqual(self.handler.calls, 2)

    def test_returned_responses_are_copies(self):
        first = self.layer.handle("key-1", charge())
        first.body["payment_id"] = "tampered"
        first.headers["X-Debug"] = "1"
        again = self.layer.handle("key-1", charge())
        self.assertEqual(again.body["payment_id"], "pay_1")
        self.assertNotIn("X-Debug", again.headers)
        again.body["amount"] = 0
        self.assertEqual(self.layer.handle("key-1", charge()).body["amount"], 1000)

    def test_ttl_expiry_and_purge(self):
        self.layer.handle("key-1", charge())
        self.layer.handle("key-2", charge())
        self.clock.now += 3599
        self.assertEqual(self.layer.handle("key-1", charge()).body["payment_id"], "pay_1")
        self.assertEqual(self.layer.purge_expired(), 0)
        self.clock.now += 1
        self.assertEqual(self.layer.purge_expired(), 2)
        self.assertEqual(self.layer.handle("key-1", charge()).body["payment_id"], "pay_3",
                         "期限切れのキーは新しいリクエストとして処理される")

    def test_client_errors_are_stored(self):
        handler = CountingHandler(statuses=[402, 201])
        layer = IdempotencyLayer(handler, clock=self.clock)
        self.assertEqual(layer.handle("key-1", charge()).status, 402)
        self.assertEqual(layer.handle("key-1", charge()).status, 402, "4xx は処理の結果なので再生する")
        self.assertEqual(handler.calls, 1)


class TestExercise3Failures(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    def test_server_errors_are_not_stored_by_default(self):
        handler = CountingHandler(statuses=[503, 201])
        layer = IdempotencyLayer(handler, clock=self.clock)
        self.assertEqual(layer.handle("key-1", charge()).status, 503)
        retry = layer.handle("key-1", charge())
        self.assertEqual(retry.status, 201, "5xx の後の再試行は実行し直す")
        self.assertNotIn(REPLAY_HEADER, retry.headers)
        self.assertEqual(handler.calls, 2)

    def test_server_errors_can_be_stored(self):
        handler = CountingHandler(statuses=[503, 201])
        layer = IdempotencyLayer(handler, clock=self.clock, cache_server_errors=True)
        layer.handle("key-1", charge())
        self.assertEqual(layer.handle("key-1", charge()).status, 503)
        self.assertEqual(handler.calls, 1)

    def test_exception_releases_the_key(self):
        handler = CountingHandler(error=RuntimeError("DB 接続が切れた"))
        layer = IdempotencyLayer(handler, clock=self.clock)
        with self.assertRaises(RuntimeError):
            layer.handle("key-1", charge())
        handler.error = None
        self.assertEqual(layer.handle("key-1", charge()).status, 201)
        self.assertEqual(handler.calls, 2)


class Worker(threading.Thread):
    """結果か例外を記録するスレッド（例外で黙って死なないように）。"""

    def __init__(self, fn):
        super().__init__(daemon=True)
        self.fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001  テストで検査するために保存する
            self.error = exc


class TestExercise3Concurrency(unittest.TestCase):
    def start_first(self, layer, handler, key="key-1"):
        """最初のリクエストを別スレッドで送り、ハンドラの中に入るまで待つ。"""
        first = Worker(lambda: layer.handle(key, charge()))
        first.start()
        wait_until(lambda: handler.entered.is_set() or not first.is_alive())
        if not handler.entered.is_set():
            if first.error is not None:
                raise first.error
            self.fail("最初のリクエストがハンドラに入らない")
        return first

    def start_waiters(self, layer, n, key="key-1"):
        waiters = [Worker(lambda: layer.handle(key, charge())) for _ in range(n)]
        for w in waiters:
            w.start()
        self.assertTrue(wait_until(lambda: layer.waiting_count("shop-1", key) == n),
                        "重複リクエストが完了を待っていない")
        return waiters

    def join_all(self, workers):
        for w in workers:
            w.join(5)
            self.assertFalse(w.is_alive(), "スレッドが終わらない（デッドロック？）")

    def test_concurrent_duplicates_wait_and_share_the_response(self):
        release = threading.Event()
        handler = CountingHandler(block=release)
        layer = IdempotencyLayer(handler, wait_timeout=5)
        first = self.start_first(layer, handler)
        waiters = self.start_waiters(layer, 5)
        release.set()
        self.join_all([first, *waiters])
        self.assertEqual(handler.calls, 1, "同時の重複でもハンドラは 1 回だけ")
        self.assertIsNone(first.error)
        self.assertEqual((first.result.status, first.result.body["payment_id"]), (201, "pay_1"))
        self.assertNotIn(REPLAY_HEADER, first.result.headers)
        for w in waiters:
            self.assertIsNone(w.error)
            self.assertEqual((w.result.status, w.result.body["payment_id"]), (201, "pay_1"))
            self.assertEqual(w.result.headers.get(REPLAY_HEADER), "true")
        self.assertEqual(layer.waiting_count("shop-1", "key-1"), 0)

    def test_waiters_time_out_with_409(self):
        release = threading.Event()
        handler = CountingHandler(block=release)
        layer = IdempotencyLayer(handler, wait_timeout=0.05)
        first = self.start_first(layer, handler)
        r = layer.handle("key-1", charge())  # 実行中の重複。0.05 秒で待つのをやめる
        self.assertEqual(r.status, 409)
        self.assertTrue(r.body["type"].endswith("request-in-progress"))
        release.set()
        self.join_all([first])
        self.assertEqual(first.result.status, 201)
        self.assertEqual(layer.handle("key-1", charge()).headers.get(REPLAY_HEADER), "true")
        self.assertEqual(handler.calls, 1)

    def test_waiters_receive_500_when_first_attempt_raises(self):
        release = threading.Event()
        handler = CountingHandler(block=release, error=ConnectionError("決済代行に接続できない"))
        layer = IdempotencyLayer(handler, wait_timeout=5)
        first = self.start_first(layer, handler)
        (waiter,) = self.start_waiters(layer, 1)
        release.set()
        self.join_all([first, waiter])
        self.assertIsInstance(first.error, ConnectionError, "最初の呼び出し元には例外が届く")
        self.assertIsNone(waiter.error)
        self.assertEqual(waiter.result.status, 500)
        self.assertTrue(waiter.result.body["type"].endswith("internal-error"))
        handler.error, handler.block = None, None
        self.assertEqual(layer.handle("key-1", charge()).status, 201, "失敗は保存されず、再試行できる")

    def test_other_keys_are_not_blocked(self):
        release = threading.Event()
        blocking = CountingHandler(block=release)

        def router(request):
            if request.body["amount"] == 1:
                return blocking(request)
            return Response(201, {"payment_id": "fast"})

        layer = IdempotencyLayer(router, wait_timeout=5)
        slow = Worker(lambda: layer.handle("slow", charge(amount=1)))
        slow.start()
        wait_until(lambda: blocking.entered.is_set() or not slow.is_alive())
        if slow.error is not None:
            raise slow.error
        self.assertTrue(blocking.entered.is_set())
        started = time.monotonic()
        self.assertEqual(layer.handle("fast", charge(amount=2)).body["payment_id"], "fast")
        self.assertLess(time.monotonic() - started, 1.0, "別のキーの処理を待たせてはいけない")
        release.set()
        self.join_all([slow])


if __name__ == "__main__":
    unittest.main()
