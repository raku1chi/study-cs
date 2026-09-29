"""12.5 AIシステムの本番運用 — 演習3: AI ゲートウェイ（★★★）

社内のアプリケーションが LLM を呼ぶときの「関所」を作ります。すべての呼び出しをここに通すことで、

    - ルーティング: 要求の品質の段階・遅延の上限・文脈の長さを満たすモデルのうち、最も安いものを選ぶ
    - フォールバック: タイムアウトや一時的な障害なら、次の候補のモデル（別の提供元）に切り替える
    - 予算とレート制限: チームごとのトークンの予算（期間ごとに戻る）と、要求の頻度の上限
    - キャッシュ: 温度 0 の同じ要求には、保存した応答を返す（完全一致・LRU）
    - 利用量の記録: チームごとのリクエスト数・トークン数・費用（Decimal）・障害の回数

を 1 か所で実現します。提供元は偽物（FakeProvider）、時計は手で進める ManualClock を使うので、
ネットワークなしで決定的にテストできます。価格はすべて架空の値です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.5
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_ai_gateway

金額は float ではなく Decimal で扱います（[1.1 情報の表現] で学んだ理由から）。
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
    """トークン数の粗い見積もり（UTF-8 のバイト数 ÷ 4 の切り上げ、最低 1）。

    実際のトークン数はトークナイザで決まる（12.3 の BPE）。ここでは予算の事前チェックに使う概算。
    """
    return max(1, math.ceil(len(text.encode("utf-8")) / 4))


@dataclass(frozen=True)
class ModelSpec:
    """ゲートウェイが使えるモデル。tier は品質の段階（1: 小、2: 中、3: 大）。価格は 100 万トークンあたり。"""

    name: str
    provider: str
    tier: int
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    latency_ms: int
    max_context_tokens: int


@dataclass(frozen=True)
class Completion:
    """提供元の応答（実際に使ったトークン数つき）。"""

    text: str
    input_tokens: int
    output_tokens: int


class ProviderError(Exception):
    """提供元の失敗。retryable=True なら一時的な障害（別のモデルで再試行してよい）。"""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class ProviderTimeout(ProviderError):
    """タイムアウト（常に再試行してよい）。"""

    def __init__(self, message: str = "タイムアウト") -> None:
        super().__init__(message, retryable=True)


class Provider(Protocol):
    def complete(self, model: str, prompt: str, max_output_tokens: int) -> Completion: ...


class FakeProvider:
    """テスト用の提供元。failures に例外を並べると、呼ばれるたびに先頭から順に投げる（None なら成功）。"""

    def __init__(self, name: str, *, failures: Sequence[Exception | None] = ()) -> None:
        self.name = name
        self._failures = list(failures)
        self.calls: list[tuple[str, str]] = []  # (モデル名, プロンプト)

    def complete(self, model: str, prompt: str, max_output_tokens: int) -> Completion:
        self.calls.append((model, prompt))
        if self._failures:
            failure = self._failures.pop(0)
            if failure is not None:
                raise failure
        text = f"[{model}] {prompt[:20]} への回答"
        return Completion(text, estimate_tokens(prompt), min(max_output_tokens, estimate_tokens(text)))


class ManualClock:
    """手で進める時計（秒）。clock() で現在時刻、advance(秒) で進める。"""

    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@dataclass(frozen=True)
class Request:
    """ゲートウェイへの要求。quality は "low" / "standard" / "high"。"""

    team: str
    prompt: str
    quality: str = "standard"
    max_output_tokens: int = 256
    max_latency_ms: int | None = None
    temperature: float = 0.0
    cacheable: bool = True


@dataclass(frozen=True)
class Response:
    """ゲートウェイの応答。attempts は試したモデルと結果 ("ok" / "timeout" / "error") の組。"""

    text: str
    model: str
    cached: bool
    input_tokens: int
    output_tokens: int
    cost: Decimal
    attempts: tuple[tuple[str, str], ...] = ()


@dataclass
class Usage:
    """チームごとの利用量。"""

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


QUALITY_MIN_TIER = {"low": 1, "standard": 2, "high": 3}  # 品質の要求 → 必要な tier の下限
MILLION = Decimal(1_000_000)


# ---------------------------------------------------------------------------
# 演習3a（★☆☆）: レート制限（トークンバケット）
# ---------------------------------------------------------------------------

class TokenBucket:
    """トークンバケット。最大 capacity 個のトークンを持ち、1 秒に refill_per_second 個ずつ補充される。

    - 作成時は満杯。allow() は、前回の呼び出しからの経過時間ぶん補充してから（上限は capacity）、
      トークンが 1 個以上あれば 1 個消費して True、なければ False を返す。
    - capacity < 1 または refill_per_second <= 0 なら ValueError。時刻は clock() から得る。
    """

    def __init__(self, capacity: int, refill_per_second: float, clock: Callable[[], float]) -> None:
        raise NotImplementedError("演習3a: TokenBucket.__init__ を実装してください")

    def allow(self) -> bool:
        raise NotImplementedError("演習3a: TokenBucket.allow を実装してください")


# ---------------------------------------------------------------------------
# 演習3b（★★★）: ゲートウェイ
# ---------------------------------------------------------------------------

class AIGateway:
    """AI ゲートウェイ。

    コンストラクタ（実装済み）の引数:
        models: 使えるモデルの一覧。各モデルの provider が providers にないと ValueError。
        providers: {提供元の名前: Provider}
        clock: 現在時刻（秒）を返す関数
        team_token_budgets: {チーム: 1 期間に使えるトークン数}（ないチームは無制限）
        budget_period_seconds: 予算の期間の長さ。期間の番号は int(clock() // budget_period_seconds)
        rate_limits: {チーム: (容量, 1 秒あたりの補充数)}（ないチームは無制限）
        cache_size: キャッシュに保存する応答の最大数
    """

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
        self._spent: dict[str, tuple[int, int]] = {}  # チーム → (期間の番号, その期間に使ったトークン数)
        self._rate_limits = dict(rate_limits or {})
        self._buckets: dict[str, TokenBucket] = {}  # チーム → TokenBucket（必要になったときに作ってもよい）
        self._cache: OrderedDict[tuple, Response] = OrderedDict()  # LRU キャッシュ
        self._cache_size = cache_size
        self._usage: dict[str, Usage] = {}

    def candidates(self, request: Request) -> list[ModelSpec]:
        """要求を満たすモデルを、見積もりの費用が安い順に返す。

        - request.quality が QUALITY_MIN_TIER にないなら ValueError。
        - 条件: tier >= QUALITY_MIN_TIER[quality]、max_latency_ms が指定されていれば latency_ms <= それ、
          max_context_tokens >= estimate_tokens(prompt) + max_output_tokens。
        - 見積もりの費用 = (estimate_tokens(prompt) × 入力単価 + max_output_tokens × 出力単価) ÷ 100 万。
          費用が同じなら latency_ms の小さい順、それも同じなら名前の順。
        """
        raise NotImplementedError("演習3b: candidates を実装してください")

    def remaining_budget(self, team: str) -> int | None:
        """現在の期間の予算の残り（トークン数）。予算が設定されていないチームは None。

        期間の番号が変わったら、そのチームの使用量は 0 に戻る。
        """
        raise NotImplementedError("演習3b: remaining_budget を実装してください")

    def handle(self, request: Request) -> Response:
        """要求を処理する。次の順に行うこと:

        1. レート制限: チームに rate_limits があれば、そのチームの TokenBucket の allow() が False なら RateLimited。
        2. candidates(request) が空なら NoEligibleModel。
        3. キャッシュ: cacheable かつ temperature == 0 の要求だけが対象。キーは
           (team, quality, max_output_tokens, prompt)（チームをまたいで共有しない）。
           保存済みなら、その応答を cached=True、cost=Decimal("0")、attempts=() にして返す
           （利用量は requests と cache_hits を 1 増やすだけ。トークンは数えない）。LRU の順番も更新する。
        4. 予算: 予算のあるチームで、estimate_tokens(prompt) + max_output_tokens が残りより大きければ
           BudgetExceeded（提供元を **呼ぶ前に** 止める）。
        5. 候補の順に、providers[モデルの provider].complete(モデル名, prompt, max_output_tokens) を呼ぶ:
           - ProviderError が起きたら、provider_failures を 1 増やし、attempts に (モデル名, "timeout"
             （ProviderTimeout の場合）または "error") を追加する。retryable でなければその例外をそのまま
             投げ直す（別のモデルに回しても直らない）。retryable なら次の候補へ（フォールバック）。
           - 成功したら attempts に (モデル名, "ok") を追加し、費用
             = (実際の入力トークン × 入力単価 + 実際の出力トークン × 出力単価) ÷ 100 万（Decimal）を計算する。
             利用量（requests, input_tokens, output_tokens, cost）と、予算の使用量（入力 + 出力のトークン）を更新し、
             キャッシュの対象ならキャッシュに保存して（cache_size を超えたら最も古く使われたものを捨てる）、
             Response(cached=False, attempts=試した順のタプル) を返す。
        6. すべての候補が retryable な失敗なら AllProvidersFailed(attempts)。
        """
        raise NotImplementedError("演習3b: handle を実装してください")

    def usage_report(self) -> dict[str, Usage]:
        """チーム名の昇順の {チーム: Usage}。"""
        raise NotImplementedError("演習3b: usage_report を実装してください")
