"""7.1 分散システムの本質 — 演習: 故障検出器（解答例）

演習の仕様は exercises/failure_detector.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import statistics
import time
from collections import deque
from typing import Callable

# ---------------------------------------------------------------------------
# 演習6: 固定タイムアウトのハートビート故障検出器
# ---------------------------------------------------------------------------


class HeartbeatFailureDetector:
    def __init__(self, timeout: float, clock: Callable[[], float] = time.monotonic) -> None:
        if timeout <= 0:
            raise ValueError(f"timeout は正の数です: {timeout}")
        self.timeout = timeout
        # 経過時間を測るので、既定は壁時計（time.time）ではなく単調時計（time.monotonic）
        self.clock = clock
        self._last_seen: dict[str, float] = {}

    def heartbeat(self, node: str) -> None:
        now = self.clock()
        last = self._last_seen.get(node)
        if last is not None and now < last:
            raise ValueError("時計が巻き戻りました。経過時間の計測には単調時計を使ってください")
        self._last_seen[node] = now

    def is_alive(self, node: str) -> bool:
        last = self._last_seen.get(node)
        if last is None:
            return False  # 一度も便りのないノードは「生きている」と言えない
        return self.clock() - last <= self.timeout

    def suspects(self) -> list[str]:
        return sorted(n for n in self._last_seen if not self.is_alive(n))

    def alive_nodes(self) -> list[str]:
        return sorted(n for n in self._last_seen if self.is_alive(n))


# ---------------------------------------------------------------------------
# 演習7: φ accrual 故障検出器（簡略版）
# ---------------------------------------------------------------------------


class PhiAccrualFailureDetector:
    def __init__(
        self,
        threshold: float = 8.0,
        window_size: int = 100,
        min_std: float = 0.1,
        acceptable_pause: float = 0.0,
        first_heartbeat_estimate: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if threshold <= 0:
            raise ValueError(f"threshold は正の数です: {threshold}")
        if window_size < 1:
            raise ValueError(f"window_size は 1 以上です: {window_size}")
        if min_std <= 0:
            raise ValueError(f"min_std は正の数です: {min_std}")
        if acceptable_pause < 0:
            raise ValueError(f"acceptable_pause は 0 以上です: {acceptable_pause}")
        if first_heartbeat_estimate <= 0:
            raise ValueError(f"first_heartbeat_estimate は正の数です: {first_heartbeat_estimate}")
        self.threshold = threshold
        self.min_std = min_std
        self.acceptable_pause = acceptable_pause
        self.first_heartbeat_estimate = first_heartbeat_estimate
        self.clock = clock
        # 直近 window_size 個の到着間隔だけを使う（古い傾向を忘れ、変化に追従する）
        self._intervals: deque[float] = deque(maxlen=window_size)
        self._last: float | None = None

    def heartbeat(self) -> None:
        now = self.clock()
        if self._last is None:
            # 最初の 1 回は間隔が分からないので、推定値 ± 1/4 の 2 つの仮の標本で初期化する
            # （Akka の実装と同じ考え方）。これで「1 回だけ来て止まった」ノードも疑える
            est = self.first_heartbeat_estimate
            self._intervals.append(est - est / 4)
            self._intervals.append(est + est / 4)
        else:
            interval = now - self._last
            if interval < 0:
                raise ValueError("時計が巻き戻りました。経過時間の計測には単調時計を使ってください")
            self._intervals.append(interval)
        self._last = now

    def mean(self) -> float:
        if not self._intervals:
            raise ValueError("まだハートビートを受け取っていません")
        return statistics.fmean(self._intervals)

    def std(self) -> float:
        if not self._intervals:
            raise ValueError("まだハートビートを受け取っていません")
        return max(statistics.pstdev(self._intervals), self.min_std)

    def phi(self) -> float:
        if self._last is None:
            return 0.0  # 監視を始めていないノードは疑わない
        elapsed = self.clock() - self._last
        mean = self.mean() + self.acceptable_pause
        std = self.std()
        # P_later(t): 到着間隔が正規分布に従うとして、次のハートビートが t より後に来る確率
        p_later = 0.5 * math.erfc((elapsed - mean) / (std * math.sqrt(2)))
        if p_later <= 0.0:
            return math.inf  # 浮動小数点で表せないほど小さい確率 = ほぼ確実に故障
        return -math.log10(p_later)

    def is_available(self) -> bool:
        return self.phi() < self.threshold
