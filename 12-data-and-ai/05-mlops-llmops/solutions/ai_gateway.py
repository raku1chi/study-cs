"""12.5 AIシステムの本番運用 — 演習3: AI ゲートウェイ（解答例）

演習の仕様は exercises/ai_gateway.py の docstring を参照してください。
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable, Protocol, Sequence

# ---------------------------------------------------------------------------
# 実装済み: 部品
# ---------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


@dataclass(frozen=True)
class ModelSpec:
    name: str
    provider: str
    tier: int
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    latency_ms: int
    max_context_tokens: int


@dataclass(frozen=True)
class Completion:
    text: str
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderTimeout(ProviderError):
    def __init__(self, message: str = "タイムアウト") -> None:
        super().__init__(message, retryable=True)


class Provider(Protocol):
    def complete(self, model: str, prompt: str, max_output_tokens: int) -> Completion: ...


class FakeProvider:
    def __init__(self, name: str, *, failures: Sequence[Exception | None] = ()) -> None:
        self.name = name
        self._failures = list(failures)
        self.calls: list[tuple[str, str]] = []

    def complete(self, model: str, prompt: str, max_output_tokens: int) -> Completion:
        self.calls.append((model, prompt))
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        text = f"[{model}] {prompt[:20]} への回答"
        return Completion(text, estimate_tokens(prompt), min(max_output_tokens, estimate_tokens(text)))


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class Request:
    team: str
    prompt: str
    quality: str = "standard"
    max_output_tokens: int = 256
    max_latency_ms: int | None = None
    temperature: float = 0.0
    cacheable: bool = True


@dataclass(frozen=True)
class Response:
    text: str
    model: str
    cached: bool
    input_tokens: int
    output_tokens: int
    cost: Decimal
    attempts: tuple[tuple[str, str], ...] = ()


@dataclass
class Usage:
    requests: int = 0
    cache_hits: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    provider_failures: int = 0


class GatewayError(Exception):
    pass


class RateLimited(GatewayError):
    pass


class BudgetExceeded(GatewayError):
    pass


class NoEligibleModel(GatewayError):
    pass


class AllProvidersFailed(GatewayError):
    def __init__(self, attempts: list[tuple[str, str]]) -> None:
        super().__init__("すべてのモデルが失敗しました: " + ", ".join(f"{m}={o}" for m, o in attempts))
        self.attempts = attempts


QUALITY_MIN_TIER = {"low": 1, "standard": 2, "high": 3}
MILLION = Decimal(1_000_000)


# ---------------------------------------------------------------------------
# 演習3a: レート制限（トークンバケット）
# ---------------------------------------------------------------------------

class TokenBucket:
    def __init__(self, capacity: int, refill_per_second: float, clock: Callable[[], float]) -> None:
        if capacity < 1 or refill_per_second <= 0:
            raise ValueError("capacity >= 1, refill_per_second > 0")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._tokens = float(capacity)
        self._last = clock()

    def allow(self) -> bool:
        now = self._clock()
        # 前回からの経過時間に応じて補充する（上限は容量）
        self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.refill_per_second)
        self._last = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False


# ---------------------------------------------------------------------------
# 演習3b: ゲートウェイ
# ---------------------------------------------------------------------------

class AIGateway:
    def __init__(
        self,
        models: Sequence[ModelSpec],
        providers: dict[str, Provider],
        *,
        clock: Callable[[], float],
        team_token_budgets: dict[str, int] | None = None,
        budget_period_seconds: int = 86_400,
        rate_limits: dict[str, tuple[int, float]] | None = None,
        cache_size: int = 1_000,
    ) -> None:
        for m in models:
            if m.provider not in providers:
                raise ValueError(f"{m.name} の提供元 {m.provider} が登録されていません")
        self.models = list(models)
        self.providers = providers
        self._clock = clock
        self._budgets = dict(team_token_budgets or {})
        self._period = budget_period_seconds
        self._spent: dict[str, tuple[int, int]] = {}  # チーム → (期間の番号, 使ったトークン数)
        self._buckets = {team: TokenBucket(cap, rate, clock) for team, (cap, rate) in (rate_limits or {}).items()}
        self._cache: OrderedDict[tuple, Response] = OrderedDict()
        self._cache_size = cache_size
        self._usage: dict[str, Usage] = {}

    # --- 経路の選択 -------------------------------------------------------------
    def _estimated_cost(self, m: ModelSpec, request: Request) -> Decimal:
        return (estimate_tokens(request.prompt) * m.input_price_per_mtok
                + request.max_output_tokens * m.output_price_per_mtok) / MILLION

    def candidates(self, request: Request) -> list[ModelSpec]:
        if request.quality not in QUALITY_MIN_TIER:
            raise ValueError(f"quality は {sorted(QUALITY_MIN_TIER)} のどれか: {request.quality!r}")
        needed = estimate_tokens(request.prompt) + request.max_output_tokens
        eligible = [
            m for m in self.models
            if m.tier >= QUALITY_MIN_TIER[request.quality]
            and (request.max_latency_ms is None or m.latency_ms <= request.max_latency_ms)
            and m.max_context_tokens >= needed
        ]
        # 条件を満たすものの中で、見積もりの費用が安い順（同じなら速い順、名前の順）
        return sorted(eligible, key=lambda m: (self._estimated_cost(m, request), m.latency_ms, m.name))

    # --- 予算 -------------------------------------------------------------------
    def _spent_in_period(self, team: str) -> int:
        period = int(self._clock() // self._period)
        stored_period, spent = self._spent.get(team, (period, 0))
        return spent if stored_period == period else 0  # 期間が変われば使用量は 0 に戻る

    def _add_spent(self, team: str, tokens: int) -> None:
        period = int(self._clock() // self._period)
        self._spent[team] = (period, self._spent_in_period(team) + tokens)

    def remaining_budget(self, team: str) -> int | None:
        if team not in self._budgets:
            return None
        return self._budgets[team] - self._spent_in_period(team)

    # --- 本体 -------------------------------------------------------------------
    def handle(self, request: Request) -> Response:
        bucket = self._buckets.get(request.team)
        if bucket is not None and not bucket.allow():
            raise RateLimited(f"チーム {request.team} のレート制限を超えました")
        candidates = self.candidates(request)
        if not candidates:
            raise NoEligibleModel("条件（品質・遅延・文脈の長さ）を満たすモデルがありません")
        usage = self._usage.setdefault(request.team, Usage())

        # 温度 0 の決定的な要求だけをキャッシュする。チーム（テナント）ごとに分けて、共有による漏えいを防ぐ
        key = (request.team, request.quality, request.max_output_tokens, request.prompt)
        use_cache = request.cacheable and request.temperature == 0
        if use_cache and key in self._cache:
            self._cache.move_to_end(key)
            hit = self._cache[key]
            usage.requests += 1
            usage.cache_hits += 1
            return Response(hit.text, hit.model, True, hit.input_tokens, hit.output_tokens, Decimal("0"), ())

        # 呼ぶ前に、最悪の場合（出力が上限まで出る）のトークン数で予算を確かめる
        remaining = self.remaining_budget(request.team)
        estimated = estimate_tokens(request.prompt) + request.max_output_tokens
        if remaining is not None and estimated > remaining:
            raise BudgetExceeded(f"チーム {request.team} の予算の残り {remaining} トークン < 見積もり {estimated}")

        attempts: list[tuple[str, str]] = []
        for m in candidates:
            try:
                result = self.providers[m.provider].complete(m.name, request.prompt, request.max_output_tokens)
            except ProviderError as exc:
                usage.provider_failures += 1
                attempts.append((m.name, "timeout" if isinstance(exc, ProviderTimeout) else "error"))
                if not exc.retryable:
                    # 要求そのものが不正（400 番台など）なら、別のモデルに回しても直らない
                    raise
                continue  # 一時的な障害なら次の候補へ（フォールバック）
            attempts.append((m.name, "ok"))
            cost = (result.input_tokens * m.input_price_per_mtok + result.output_tokens * m.output_price_per_mtok) / MILLION
            usage.requests += 1
            usage.input_tokens += result.input_tokens
            usage.output_tokens += result.output_tokens
            usage.cost += cost
            self._add_spent(request.team, result.input_tokens + result.output_tokens)
            response = Response(result.text, m.name, False, result.input_tokens, result.output_tokens, cost, tuple(attempts))
            if use_cache:
                self._cache[key] = response
                self._cache.move_to_end(key)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)  # 最も長く使われていないものを捨てる（LRU）
            return response
        raise AllProvidersFailed(attempts)

    def usage_report(self) -> dict[str, Usage]:
        return {team: self._usage[team] for team in sorted(self._usage)}
