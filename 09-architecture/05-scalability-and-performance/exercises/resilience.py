"""9.5 スケーラビリティとパフォーマンス — 演習2〜4: 過負荷から身を守る部品

    演習2（★★☆）: レート制限 TokenBucket / SlidingWindowCounter
    演習3（★★☆）: サーキットブレーカー CircuitBreaker
    演習4（★★☆）: 指数バックオフ＋フルジッターのリトライ retry_call と、リトライ予算 RetryBudget

時間に依存する部品は、すべて「時計」（clock: 現在時刻の秒を返す関数）と「待つ関数」（sleep）を
引数で受け取ります。テストでは偽の時計を渡すので、実際に待つことなく一瞬で決定的に検証できます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.5

いずれの部品も、複数のスレッドから同時に呼ばれてもよいよう、状態の更新は self._lock で守ること。
"""
from __future__ import annotations

import math  # noqa: F401
import random
import threading
import time
from collections import deque
from typing import Callable, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: レート制限
# ---------------------------------------------------------------------------

class TokenBucket:
    """トークンバケット: 平均 rate 回/秒を上限としつつ、capacity 回までの瞬間的な集中（バースト）を許す。

    - バケットには最大 capacity 個のトークンが入る。最初は満タン。
    - トークンは経過時間 × rate の速さで補充される（capacity を超えない）。
      時計が戻った（経過時間が負）ときは補充しない。
    - try_acquire(n): 補充したうえで、n 個以上あれば n 個取り出して True。なければ何も取り出さず False。
    - wait_time(n): n 個がたまるまでの秒数（今あれば 0.0）。429 応答の Retry-After の計算に使える。
    - rate・capacity は正（違反は ValueError）。n は 0 より大きく capacity 以下（違反は ValueError。
      capacity を超える n は永久に取り出せないため）。
    """

    def __init__(self, rate: float, capacity: float, clock: Callable[[], float] = time.monotonic) -> None:
        raise NotImplementedError("演習2: TokenBucket.__init__ を実装してください")

    def try_acquire(self, n: float = 1.0) -> bool:
        raise NotImplementedError("演習2: TokenBucket.try_acquire を実装してください")

    def wait_time(self, n: float = 1.0) -> float:
        raise NotImplementedError("演習2: TokenBucket.wait_time を実装してください")

    @property
    def tokens(self) -> float:
        """補充を反映した現在のトークン数。"""
        raise NotImplementedError("演習2: TokenBucket.tokens を実装してください")


class SlidingWindowCounter:
    """スライディングウィンドウ・カウンタ: 直近 window 秒の要求数を limit 以下に抑える（近似）。

    固定の窓（0〜window, window〜2*window, ...）ごとに件数を数え、次の式で「直近 window 秒の件数」を推定する:

        推定値 = 前の窓の件数 × (今の窓とまだ重なっている割合) + 今の窓の件数
        重なっている割合 = (window − 今の窓の開始からの経過時間) ÷ window

    - try_acquire(): 推定値 + 1 が limit 以下なら、今の窓の件数を 1 増やして True。そうでなければ False
      （拒否した要求は数えない）。
    - 窓が 1 つ進んだら「今の窓の件数」が「前の窓の件数」になる。2 つ以上進んだら前の窓は 0 件。
    - estimated(): 現在の推定値（テスト・監視用）。
    - limit・window は正（違反は ValueError）。

    ヒント: 窓は「何番目の窓か」を math.floor(now / window) の整数で管理すると、浮動小数点の
    開始時刻どうしを == で比べずに済む。
    固定窓の単純なカウンタは、窓の境界の直前と直後に limit ずつ、合計 2 倍のバーストを許してしまう。
    この近似はそれを防ぎつつ、窓 2 つ分の整数だけで済む。
    """

    def __init__(self, limit: int, window: float, clock: Callable[[], float] = time.monotonic) -> None:
        raise NotImplementedError("演習2: SlidingWindowCounter.__init__ を実装してください")

    def estimated(self) -> float:
        raise NotImplementedError("演習2: SlidingWindowCounter.estimated を実装してください")

    def try_acquire(self) -> bool:
        raise NotImplementedError("演習2: SlidingWindowCounter.try_acquire を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: サーキットブレーカー
# ---------------------------------------------------------------------------

class CircuitOpenError(Exception):
    """サーキットが開いているので呼び出さなかった。retry_after は再試行できるまでの秒数の目安。"""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"サーキットが開いています（{retry_after:.1f} 秒後に再試行できます）")
        self.retry_after = retry_after


class CircuitBreaker:
    """サーキットブレーカー: 失敗が続く依存先への呼び出しを一時的に止め、相手と自分を守る。

    状態:
    - CLOSED（通常）: 呼び出しを通し、直近 window_size 回の結果（成功・失敗）を記録する。
      記録が minimum_calls 件以上あり、失敗率が failure_threshold 以上になったら OPEN へ
      （OPEN になった時刻を覚え、記録は消す）。
    - OPEN（遮断）: fn を呼ばずに CircuitOpenError(retry_after=cooldown − 経過時間) を送出する。
      OPEN になってから cooldown 秒以上経ったら HALF_OPEN へ（state を読んだとき、または call のときに移る）。
    - HALF_OPEN（試行）: 最大 half_open_max_calls 回の試行の呼び出しだけを通す（それを超える呼び出しは
      CircuitOpenError(0.0)）。試行が 1 つでも失敗したら OPEN へ戻る（冷却期間をやり直す）。
      試行が half_open_max_calls 回成功したら CLOSED へ（記録は空から始める）。

    失敗とは、fn が Exception を送出し、かつ is_failure(例外) が True のこと。is_failure が False の例外
    （例: 「見つからない」のような業務上のエラー）は、送出はするが成功として数える。
    例外は常に呼び出し元にそのまま送出する。OPEN の間に完了した（OPEN になる前に始まった）呼び出しの
    結果は数えない。

    パラメータの検査（違反は ValueError）: 0 < failure_threshold <= 1、0 < minimum_calls <= window_size、
    cooldown >= 0、half_open_max_calls > 0。
    """

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
        raise NotImplementedError("演習3: CircuitBreaker.__init__ を実装してください")

    @property
    def state(self) -> str:
        """現在の状態（CLOSED / OPEN / HALF_OPEN）。冷却期間が過ぎていれば HALF_OPEN に移ってから返す。"""
        raise NotImplementedError("演習3: CircuitBreaker.state を実装してください")

    def failure_rate(self) -> float:
        """CLOSED の記録の失敗率（記録がなければ 0.0）。"""
        raise NotImplementedError("演習3: CircuitBreaker.failure_rate を実装してください")

    def call(self, fn: Callable[..., T], *args, **kwargs) -> T:
        """状態に応じて fn(*args, **kwargs) を呼ぶ。fn はロックの外で呼ぶこと。"""
        raise NotImplementedError("演習3: CircuitBreaker.call を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 指数バックオフ＋フルジッターのリトライと、リトライ予算
# ---------------------------------------------------------------------------

class RetryBudget:
    """リトライ予算（トークン方式）: リトライが本来のリクエストの一定割合を超えないようにする。

    - 本来のリクエスト（1 回目の試行）のたびに on_request() で ratio 個のトークンを積み立てる（max_tokens まで）。
    - リトライのたびに try_spend() でトークンを 1 個使う。1 個未満なら False（リトライしない）。
    - initial_tokens: 起動直後や低負荷時にも少しはリトライできるよう、最初から持っているトークン。
    例えば ratio=0.1 なら、定常状態ではリトライは本来のリクエストの約 10% までに抑えられる。
    ratio・initial_tokens は 0 以上、max_tokens は正（違反は ValueError）。initial_tokens は max_tokens で頭打ち。
    """

    def __init__(self, ratio: float = 0.1, initial_tokens: float = 10.0, max_tokens: float = 100.0) -> None:
        raise NotImplementedError("演習4: RetryBudget.__init__ を実装してください")

    @property
    def tokens(self) -> float:
        raise NotImplementedError("演習4: RetryBudget.tokens を実装してください")

    def on_request(self) -> None:
        raise NotImplementedError("演習4: RetryBudget.on_request を実装してください")

    def try_spend(self) -> bool:
        raise NotImplementedError("演習4: RetryBudget.try_spend を実装してください")


def full_jitter_delay(attempt: int, base: float, cap: float, rng: random.Random) -> float:
    """attempt 回目の試行が失敗した後に待つ秒数（Full Jitter）。

        rng.uniform(0, min(cap, base × 2^(attempt − 1)))

    1 回目の失敗の後は [0, base]、2 回目の後は [0, 2*base]、... と上限が倍々になり、cap で頭打ち。
    rng.uniform をちょうど 1 回だけ呼ぶこと（テストが同じ種の乱数列で期待値を計算するため）。
    """
    raise NotImplementedError("演習4: full_jitter_delay を実装してください")


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
    """fn() を呼び、失敗したらバックオフしながら再試行する。成功すればその値を返す。

    1. 最初に clock() で開始時刻を記録し、budget があれば budget.on_request() を 1 回呼ぶ。
    2. fn() が Exception を送出したら、次のどれかなら **その例外をそのまま送出して** 諦める:
       - retry_on(例外) が False（例: 400 番台のエラー。再試行しても無駄）
       - すでに max_attempts 回試行した
       - 待ち時間 delay = full_jitter_delay(試行回数, base_delay, max_delay, rng) を計算し、
         (clock() − 開始時刻) + delay が deadline を超える（deadline が None なら期限なし）
       - budget があり、budget.try_spend() が False
    3. そうでなければ sleep(delay) してから再試行する。
    max_attempts が 1 未満なら ValueError。rng が None なら random.Random() を使う。
    """
    raise NotImplementedError("演習4: retry_call を実装してください")
