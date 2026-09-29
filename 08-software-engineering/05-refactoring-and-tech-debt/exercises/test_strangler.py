"""8.5 演習2 — ストラングラー・フィグのルーターのテスト

実行: python3 tools/check.py 8.5   （またはこのディレクトリで python3 -m unittest -v test_strangler）
"""
import unittest

from strangler import InvalidTransition, Mismatch, RouteStats, StranglerRouter


class Backend:
    """呼ばれた回数を記録する、テスト用の実装。"""

    def __init__(self, name, fail_when=None, answer=None):
        self.name = name
        self.calls = []
        self.fail_when = fail_when or (lambda request: False)
        self.answer = answer or (lambda request: {"from": name, "path": request["path"]})

    def __call__(self, request):
        self.calls.append(request)
        if self.fail_when(request):
            raise RuntimeError(f"{self.name} failed")
        return self.answer(request)


def same_answer(request):
    return {"order": request["path"].rsplit("/", 1)[-1], "status": "open"}


def users(n, path="/orders/1"):
    return [{"path": path, "user_id": f"u{i}"} for i in range(n)]


class RouterTestCase(unittest.TestCase):
    def make(self, legacy=None, modern=None, **kwargs):
        self.legacy = legacy or Backend("legacy", answer=same_answer)
        self.modern = modern or Backend("modern", answer=same_answer)
        kwargs.setdefault("min_shadow_samples", 10)
        kwargs.setdefault("min_canary_samples", 10)
        router = StranglerRouter(self.legacy, self.modern, **kwargs)
        router.add_route("/orders")
        return router


class TestRouting(RouterTestCase):
    def test_prefix_matching_and_longest_prefix(self):
        # /orders/export 以外を modern に
        r2 = StranglerRouter(Backend("legacy"), Backend("modern"), min_shadow_samples=0, min_canary_samples=0)
        for prefix in ("/", "/orders", "/orders/export"):
            r2.add_route(prefix)
        r2.promote("/orders")
        r2.promote("/orders", 50)
        r2.promote("/orders")                      # modern
        self.assertEqual(r2.handle({"path": "/orders"})["from"], "modern")
        self.assertEqual(r2.handle({"path": "/orders/42"})["from"], "modern")
        self.assertEqual(r2.handle({"path": "/orders/export/2026"})["from"], "legacy", "より長い接頭辞が優先")
        self.assertEqual(r2.handle({"path": "/ordersheet"})["from"], "legacy", "/orders は /ordersheet に一致しない")
        self.assertEqual(r2.handle({"path": "/users/1"})["from"], "legacy", "接頭辞 / のルートは legacy のまま")

    def test_no_matching_route(self):
        router = self.make()
        self.assertEqual(router.handle({"path": "/users/1"}), same_answer({"path": "/users/1"}))
        self.assertEqual(len(self.modern.calls), 0)

    def test_route_registration(self):
        router = self.make()
        with self.assertRaises(ValueError):
            router.add_route("/orders")
        with self.assertRaises(ValueError):
            router.add_route("orders")
        with self.assertRaises(KeyError):
            router.mode("/nope")
        self.assertEqual(router.mode("/orders"), ("legacy", 0))
        self.assertEqual(router.stats("/orders"), RouteStats())


class TestModes(RouterTestCase):
    def test_legacy_mode_calls_only_legacy(self):
        router = self.make()
        router.handle({"path": "/orders/1"})
        self.assertEqual((len(self.legacy.calls), len(self.modern.calls)), (1, 0))

    def test_shadow_returns_legacy_and_records_mismatches(self):
        modern = Backend("modern", answer=lambda r: {"order": "1", "status": "OPEN"})
        router = self.make(modern=modern)
        router.promote("/orders")
        response = router.handle({"path": "/orders/1", "user_id": "u1"})
        self.assertEqual(response, {"order": "1", "status": "open"}, "利用者には常に旧実装の応答を返す")
        self.assertEqual(len(modern.calls), 1, "新実装にも同じリクエストを流す")
        self.assertEqual(router.stats("/orders"), RouteStats(shadow_compared=1, shadow_mismatches=1))
        (m,) = router.mismatches
        self.assertIsInstance(m, Mismatch)
        self.assertEqual((m.route, m.legacy, m.modern, m.error),
                         ("/orders", {"order": "1", "status": "open"}, {"order": "1", "status": "OPEN"}, None))
        self.assertEqual(m.request["user_id"], "u1")

    def test_shadow_errors_never_reach_the_user(self):
        router = self.make(modern=Backend("modern", fail_when=lambda r: True))
        router.promote("/orders")
        self.assertEqual(router.handle({"path": "/orders/7"}), same_answer({"path": "/orders/7"}))
        (m,) = router.mismatches
        self.assertIsNone(m.modern)
        self.assertIn("RuntimeError", m.error)

    def test_shadow_matching_responses_are_not_recorded(self):
        router = self.make()
        router.promote("/orders")
        for request in users(20):
            router.handle(request)
        self.assertEqual(router.stats("/orders"), RouteStats(shadow_compared=20, shadow_mismatches=0))
        self.assertEqual(router.mismatches, [])

    def test_custom_comparator(self):
        legacy = Backend("legacy", answer=lambda r: {"total": 100, "generated_at": "10:00:00"})
        modern = Backend("modern", answer=lambda r: {"total": 100, "generated_at": "10:00:01"})

        def ignore_timestamps(a, b):
            return {k: v for k, v in a.items() if k != "generated_at"} == {k: v for k, v in b.items() if k != "generated_at"}

        router = self.make(legacy=legacy, modern=modern, comparator=ignore_timestamps)
        router.promote("/orders")
        router.handle({"path": "/orders/1"})
        self.assertEqual(router.stats("/orders").shadow_mismatches, 0, "意味のない差（時刻）は比較から除く")

    def test_mismatch_records_are_capped_but_counted(self):
        router = self.make(modern=Backend("modern", answer=lambda r: "different"), max_recorded_mismatches=5)
        router.promote("/orders")
        for request in users(12):
            router.handle(request)
        self.assertEqual(len(router.mismatches), 5)
        self.assertEqual(router.stats("/orders").shadow_mismatches, 12)

    def test_canary_is_sticky_and_proportional(self):
        router = self.make()
        router.promote("/orders")
        for request in users(10):
            router.handle(request)
        router.promote("/orders", 30)
        self.assertEqual(router.mode("/orders"), ("canary", 30))
        self.modern.calls.clear()
        requests = users(2000)
        for request in requests:
            router.handle(request)
        first = {r["user_id"] for r in self.modern.calls}
        self.assertTrue(500 <= len(first) <= 700, f"約 30% が新実装へ: {len(first)}")
        self.modern.calls.clear()
        for request in requests:
            router.handle(request)
        self.assertEqual({r["user_id"] for r in self.modern.calls}, first, "同じ利用者は同じ実装に振り分けられる")
        self.assertEqual(router.stats("/orders").canary_requests, 2 * len(first))

    def test_canary_errors_fall_back_to_legacy(self):
        modern = Backend("modern", fail_when=lambda r: r["user_id"].endswith("7"), answer=same_answer)
        router = self.make(modern=modern, max_mismatch_rate=0.5)
        router.promote("/orders")
        for request in users(10):
            router.handle(request)
        router.promote("/orders", 99)
        for request in users(100):
            self.assertEqual(router.handle(request), same_answer(request), "失敗しても利用者には応答を返す")
        stats = router.stats("/orders")
        self.assertGreater(stats.canary_errors, 0)
        self.assertLessEqual(stats.canary_errors, 10)

    def test_modern_and_retired_call_only_modern(self):
        router = self.make()
        router.promote("/orders")
        for request in users(10):
            router.handle(request)
        router.promote("/orders", 50)
        for request in users(100):
            router.handle(request)
        router.promote("/orders")
        self.assertEqual(router.mode("/orders"), ("modern", 100))
        self.legacy.calls.clear()
        router.handle({"path": "/orders/9", "user_id": "x"})
        router.promote("/orders")
        self.assertEqual(router.mode("/orders"), ("retired", 100))
        router.handle({"path": "/orders/9", "user_id": "x"})
        self.assertEqual(len(self.legacy.calls), 0)


class TestStateMachine(RouterTestCase):
    def shadow(self, router, n, mismatch_every=None):
        for i, request in enumerate(users(n)):
            if mismatch_every and i % mismatch_every == 0:
                self.modern.answer = lambda r: "wrong"
            else:
                self.modern.answer = same_answer
            router.handle(request)
        self.modern.answer = same_answer

    def test_shadow_needs_enough_samples(self):
        router = self.make()
        router.promote("/orders")
        self.shadow(router, 9)
        with self.assertRaises(InvalidTransition):
            router.promote("/orders", 5)
        self.shadow(router, 1)
        router.promote("/orders", 5)
        self.assertEqual(router.mode("/orders"), ("canary", 5))

    def test_shadow_blocks_on_mismatches(self):
        router = self.make(max_mismatch_rate=0.05)
        router.promote("/orders")
        self.shadow(router, 100, mismatch_every=10)  # 10% 不一致
        with self.assertRaises(InvalidTransition):
            router.promote("/orders", 5)
        self.assertEqual(router.mode("/orders"), ("shadow", 0))

    def test_default_canary_percent_and_validation(self):
        router = self.make()
        router.promote("/orders")
        self.shadow(router, 10)
        for bad in (0, 100, 150, 2.5):
            with self.assertRaises(ValueError, msg=bad):
                router.promote("/orders", bad)
        router.promote("/orders")
        self.assertEqual(router.mode("/orders"), ("canary", 1))

    def test_canary_ramp_requires_samples_and_low_error_rate(self):
        modern = Backend("modern", fail_when=lambda r: r["user_id"] in {"u3", "u8"}, answer=same_answer)
        router = self.make(modern=modern, max_error_rate=0.01, max_mismatch_rate=0.5)
        router.promote("/orders")
        for request in users(10):
            router.handle(request)
        router.promote("/orders", 99)
        with self.assertRaises(InvalidTransition, msg="まだ canary の標本がない"):
            router.promote("/orders", 100)
        for request in users(40):
            router.handle(request)
        with self.assertRaises(InvalidTransition, msg="エラーの割合が高すぎる"):
            router.promote("/orders")
        with self.assertRaises(ValueError, msg="割合は上げる方向にだけ変えられる"):
            router.promote("/orders", 50)

    def test_ramp_up_then_modern(self):
        router = self.make()
        router.promote("/orders")
        self.shadow(router, 10)
        router.promote("/orders", 10)
        for request in users(500):
            router.handle(request)
        router.promote("/orders", 50)
        self.assertEqual(router.mode("/orders"), ("canary", 50))
        router.promote("/orders", 100)
        self.assertEqual(router.mode("/orders"), ("modern", 100))

    def test_rollback(self):
        router = self.make()
        with self.assertRaises(InvalidTransition, msg="legacy からは戻せない"):
            router.rollback("/orders")
        router.promote("/orders")
        self.shadow(router, 10)
        router.rollback("/orders")
        self.assertEqual(router.mode("/orders"), ("legacy", 0))
        self.assertEqual(router.stats("/orders"), RouteStats(), "戻したら統計はやり直し")
        router.promote("/orders")
        self.shadow(router, 10)
        router.promote("/orders", 50)
        for request in users(100):
            router.handle(request)
        router.promote("/orders")
        router.rollback("/orders")
        self.assertEqual(router.mode("/orders"), ("legacy", 0), "modern からも戻せる")

    def test_retired_is_the_point_of_no_return(self):
        router = StranglerRouter(Backend("legacy"), Backend("modern"), min_shadow_samples=0, min_canary_samples=0)
        router.add_route("/orders")
        router.promote("/orders")
        router.promote("/orders", 10)
        router.promote("/orders")
        router.promote("/orders")
        self.assertEqual(router.mode("/orders"), ("retired", 100))
        with self.assertRaises(InvalidTransition):
            router.rollback("/orders")
        with self.assertRaises(InvalidTransition):
            router.promote("/orders")


if __name__ == "__main__":
    unittest.main()
