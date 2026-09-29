"""12.5 演習3: AI ゲートウェイ — テスト

実行: python3 tools/check.py 12.5   （またはこのディレクトリで python3 -m unittest -v test_ai_gateway）
提供元は偽物（FakeProvider）、時計は手で進める ManualClock を使うので、ネットワークも待ち時間もありません。
価格はすべて架空のものです。
"""
import unittest
from decimal import Decimal

from ai_gateway import (
    AIGateway,
    AllProvidersFailed,
    BudgetExceeded,
    FakeProvider,
    ManualClock,
    ModelSpec,
    NoEligibleModel,
    ProviderError,
    ProviderTimeout,
    RateLimited,
    Request,
    TokenBucket,
    Usage,
    estimate_tokens,
)

MODELS = [
    ModelSpec("small-fast", "alpha", 1, Decimal("100"), Decimal("400"), 300, 8_000),
    ModelSpec("mid", "beta", 2, Decimal("500"), Decimal("2000"), 800, 32_000),
    ModelSpec("mid-alt", "alpha", 2, Decimal("600"), Decimal("2400"), 600, 32_000),
    ModelSpec("large", "gamma", 3, Decimal("3000"), Decimal("12000"), 2000, 128_000),
]


def names(models):
    return [m.name for m in models]


class GatewayTestCase(unittest.TestCase):
    def make(self, failures=None, **kwargs):
        failures = failures or {}
        self.providers = {p: FakeProvider(p, failures=failures.get(p, ())) for p in ("alpha", "beta", "gamma")}
        self.clock = ManualClock(1_000_000.0)
        return AIGateway(MODELS, self.providers, clock=self.clock, **kwargs)


class TestTokenBucket(unittest.TestCase):
    def test_capacity_and_refill(self):
        clock = ManualClock()
        bucket = TokenBucket(2, 1.0, clock)
        self.assertEqual([bucket.allow(), bucket.allow(), bucket.allow()], [True, True, False])
        clock.advance(0.5)
        self.assertFalse(bucket.allow(), "0.5 秒では 1 つ分たまらない")
        clock.advance(0.5)
        self.assertTrue(bucket.allow())
        clock.advance(100)
        self.assertEqual([bucket.allow(), bucket.allow(), bucket.allow()], [True, True, False], "容量より多くはたまらない")

    def test_invalid(self):
        with self.assertRaises(ValueError):
            TokenBucket(0, 1.0, ManualClock())
        with self.assertRaises(ValueError):
            TokenBucket(1, 0.0, ManualClock())


class TestRouting(GatewayTestCase):
    def test_candidates_by_quality_and_cost(self):
        gw = self.make()
        self.assertEqual(names(gw.candidates(Request("t", "こんにちは", quality="low"))),
                         ["small-fast", "mid", "mid-alt", "large"])
        self.assertEqual(names(gw.candidates(Request("t", "こんにちは"))), ["mid", "mid-alt", "large"])
        self.assertEqual(names(gw.candidates(Request("t", "こんにちは", quality="high"))), ["large"])

    def test_latency_and_context_limits(self):
        gw = self.make()
        self.assertEqual(names(gw.candidates(Request("t", "q", max_latency_ms=700))), ["mid-alt"])
        long_prompt = "あ" * 12_000  # 約 9,000 トークン
        self.assertEqual(names(gw.candidates(Request("t", long_prompt, quality="low"))), ["mid", "mid-alt", "large"])
        with self.assertRaises(ValueError):
            gw.candidates(Request("t", "q", quality="best"))

    def test_no_eligible_model_and_configuration_errors(self):
        gw = self.make()
        with self.assertRaises(NoEligibleModel):
            gw.handle(Request("t", "q", quality="high", max_latency_ms=500))
        with self.assertRaises(ValueError):  # 提供元が登録されていないモデル（コンストラクタは実装済み）
            AIGateway(MODELS, {"alpha": FakeProvider("alpha")}, clock=ManualClock())


class TestHandle(GatewayTestCase):
    def test_happy_path_and_cost_accounting(self):
        gw = self.make()
        r = gw.handle(Request("search", "経費精算の締め切りは？", max_output_tokens=100))
        self.assertEqual((r.model, r.cached), ("mid", False))
        self.assertEqual(r.attempts, (("mid", "ok"),))
        self.assertEqual(r.input_tokens, estimate_tokens("経費精算の締め切りは？"))
        expected = (Decimal(r.input_tokens) * 500 + Decimal(r.output_tokens) * 2000) / Decimal(1_000_000)
        self.assertEqual(r.cost, expected, "金額は Decimal で正確に計算する")
        self.assertIsInstance(r.cost, Decimal)
        usage = gw.usage_report()["search"]
        self.assertIsInstance(usage, Usage)
        self.assertEqual((usage.requests, usage.input_tokens, usage.output_tokens, usage.cost),
                         (1, r.input_tokens, r.output_tokens, r.cost))
        self.assertEqual(self.providers["beta"].calls, [("mid", "経費精算の締め切りは？")])

    def test_fallback_on_timeout_and_retryable_error(self):
        gw = self.make({"beta": [ProviderTimeout()]})
        r = gw.handle(Request("t", "q"))
        self.assertEqual(r.model, "mid-alt")
        self.assertEqual(r.attempts, (("mid", "timeout"), ("mid-alt", "ok")))
        self.assertEqual(gw.usage_report()["t"].provider_failures, 1)
        gw = self.make({"beta": [ProviderError("503", retryable=True)]})
        self.assertEqual(gw.handle(Request("t", "q")).attempts, (("mid", "error"), ("mid-alt", "ok")))

    def test_non_retryable_error_is_raised_immediately(self):
        gw = self.make({"beta": [ProviderError("400 不正な要求", retryable=False)]})
        with self.assertRaises(ProviderError):
            gw.handle(Request("t", "q"))
        self.assertEqual(self.providers["alpha"].calls, [], "直らない誤りで別のモデルを呼ばない")

    def test_all_providers_fail(self):
        gw = self.make({"alpha": [ProviderTimeout()], "beta": [ProviderTimeout()], "gamma": [ProviderTimeout()]})
        with self.assertRaises(AllProvidersFailed) as cm:
            gw.handle(Request("t", "q"))
        self.assertEqual(cm.exception.attempts, [("mid", "timeout"), ("mid-alt", "timeout"), ("large", "timeout")])


class TestBudgetsAndRateLimits(GatewayTestCase):
    def test_budget_is_checked_before_calling(self):
        gw = self.make(team_token_budgets={"marketing": 205}, budget_period_seconds=86_400)
        first = gw.handle(Request("marketing", "質問", max_output_tokens=200))  # 見積もり 2 + 200 = 202
        spent = first.input_tokens + first.output_tokens
        self.assertEqual(gw.remaining_budget("marketing"), 205 - spent)
        with self.assertRaises(BudgetExceeded):
            gw.handle(Request("marketing", "質問2", max_output_tokens=200))
        self.assertEqual(len(self.providers["beta"].calls), 1, "予算を超える要求は提供元に送らない")
        self.clock.advance(86_400)  # 次の期間になれば予算は戻る
        self.assertEqual(gw.remaining_budget("marketing"), 205)
        self.assertEqual(gw.handle(Request("marketing", "質問2", max_output_tokens=200)).model, "mid")
        self.assertIsNone(gw.remaining_budget("other"), "予算のないチームは無制限")

    def test_rate_limit_per_team(self):
        gw = self.make(rate_limits={"batch": (2, 1.0)})
        gw.handle(Request("batch", "a"))
        gw.handle(Request("batch", "b"))
        with self.assertRaises(RateLimited):
            gw.handle(Request("batch", "c"))
        gw.handle(Request("interactive", "c"))  # 他のチームには影響しない
        self.clock.advance(1.0)
        self.assertEqual(gw.handle(Request("batch", "c")).model, "mid")


class TestCache(GatewayTestCase):
    def test_exact_match_cache(self):
        gw = self.make()
        req = Request("support", "有給休暇は何日？")
        first = gw.handle(req)
        second = gw.handle(req)
        self.assertTrue(second.cached)
        self.assertEqual(second.text, first.text)
        self.assertEqual(second.cost, Decimal("0"))
        self.assertEqual(len(self.providers["beta"].calls), 1)
        usage = gw.usage_report()["support"]
        self.assertEqual((usage.requests, usage.cache_hits), (2, 1))
        self.assertEqual(usage.input_tokens, first.input_tokens, "キャッシュの応答はトークンを数えない")

    def test_cache_is_not_shared_or_used_when_unsafe(self):
        gw = self.make()
        gw.handle(Request("support", "同じ質問"))
        self.assertFalse(gw.handle(Request("sales", "同じ質問")).cached, "チームをまたいで共有しない")
        self.assertFalse(gw.handle(Request("support", "同じ質問", max_output_tokens=10)).cached, "条件が違えば別物")
        gw.handle(Request("support", "創作して", temperature=0.8))
        self.assertFalse(gw.handle(Request("support", "創作して", temperature=0.8)).cached, "温度 > 0 は保存しない")
        gw.handle(Request("support", "最新の在庫は？", cacheable=False))
        self.assertFalse(gw.handle(Request("support", "最新の在庫は？", cacheable=False)).cached)

    def test_lru_eviction(self):
        gw = self.make(cache_size=2)
        for prompt in ("A", "B", "A", "C"):  # A は途中で使われたので、C を入れると B が追い出される
            gw.handle(Request("t", prompt))
        calls = len(self.providers["beta"].calls)
        self.assertTrue(gw.handle(Request("t", "A")).cached)
        self.assertFalse(gw.handle(Request("t", "B")).cached)
        self.assertEqual(len(self.providers["beta"].calls), calls + 1)

    def test_usage_report_is_sorted(self):
        gw = self.make()
        for team in ("zeta", "alpha-team", "mid-team"):
            gw.handle(Request(team, "q"))
        self.assertEqual(list(gw.usage_report()), ["alpha-team", "mid-team", "zeta"])


if __name__ == "__main__":
    unittest.main()
