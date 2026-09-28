"""7.1 分散システムの本質 — 演習: 故障検出器（ハートビートと φ accrual）

ネットワーク越しでは「相手が死んだのか、遅いだけなのか」を区別できません。故障検出器にできるのは、
ハートビート（定期的な「生きています」の通知）が途絶えた時間から「疑う」ことだけです。
この演習では、固定タイムアウトの検出器と、到着間隔の統計から「疑いの強さ φ」を連続値で出す
φ accrual 故障検出器（Hayashibara ら, 2004。Cassandra や Akka が採用）を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.1
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_failure_detector

時計について:
    どちらの検出器も clock 引数で時計を注入できます（既定は time.monotonic）。
    経過時間の計測には、NTP の補正やうるう秒で巻き戻りうる壁時計（time.time）ではなく、
    単調時計を使うのが鉄則です（本文 4 節）。テストでは偽の時計を渡して、一瞬で時間を進めます。
"""
from __future__ import annotations

import math  # noqa: F401  演習7で使えます（math.erfc, math.log10, math.inf）
import statistics  # noqa: F401  演習7で使えます（statistics.fmean, statistics.pstdev）
import time
from collections import deque  # noqa: F401  演習7で使えます（deque(maxlen=...)）
from typing import Callable

# ---------------------------------------------------------------------------
# 演習6（★☆☆）: 固定タイムアウトのハートビート故障検出器
# ---------------------------------------------------------------------------


class HeartbeatFailureDetector:
    """最後のハートビートから timeout 秒を超えたノードを「故障の疑いあり」とする検出器。

    - heartbeat(node): 時刻 clock() を、そのノードの最終受信時刻として記録する。
      同じノードについて、前回より小さい時刻が来たら（時計の巻き戻り）ValueError。
    - is_alive(node): clock() - 最終受信時刻 <= timeout なら True。一度もハートビートのないノードは False。
    - suspects(): ハートビートを受けたことのあるノードのうち、生存でないものを名前順で返す。
    - alive_nodes(): 生存しているノードを名前順で返す。
    - timeout <= 0 なら ValueError。

    >>> t = [100.0]
    >>> fd = HeartbeatFailureDetector(timeout=3.0, clock=lambda: t[0])
    >>> fd.heartbeat("n1"); t[0] = 104.0
    >>> fd.is_alive("n1"), fd.suspects()
    (False, ['n1'])

    考えてみよう: timeout を短くすると何が起き、長くすると何が起きるか（本文 3 節）。
    """

    def __init__(self, timeout: float, clock: Callable[[], float] = time.monotonic) -> None:
        raise NotImplementedError("演習6: HeartbeatFailureDetector.__init__ を実装してください")

    def heartbeat(self, node: str) -> None:
        raise NotImplementedError("演習6: HeartbeatFailureDetector.heartbeat を実装してください")

    def is_alive(self, node: str) -> bool:
        raise NotImplementedError("演習6: HeartbeatFailureDetector.is_alive を実装してください")

    def suspects(self) -> list[str]:
        raise NotImplementedError("演習6: HeartbeatFailureDetector.suspects を実装してください")

    def alive_nodes(self) -> list[str]:
        raise NotImplementedError("演習6: HeartbeatFailureDetector.alive_nodes を実装してください")


# ---------------------------------------------------------------------------
# 演習7（★★☆）: φ accrual 故障検出器（簡略版）
# ---------------------------------------------------------------------------


class PhiAccrualFailureDetector:
    """1 つのノードを監視する φ accrual 故障検出器。

    考え方: 直近のハートビートの到着間隔が正規分布 N(μ, σ²) に従うと仮定する。
    最後のハートビートから t 秒たったとき、「次のハートビートが t より後に来る確率」は

        P_later(t) = 1 - Φ((t - μ) / σ) = 0.5 × erfc((t - μ) / (σ × √2))

    で、疑いの強さを φ(t) = -log10(P_later(t)) で表す。
    φ = 1 なら「今、故障と判断すると 10% の確率で誤り」、φ = 3 なら 0.1%、φ = 8 なら 10⁻⁸。
    固定のタイムアウトと違い、ハートビートのリズムやゆらぎが大きいノードほど、疑うまでの時間が自動的に長くなる。

    仕様:
        - heartbeat(): clock() を受信時刻として記録する。
            * 最初の 1 回は間隔が分からないので、est = first_heartbeat_estimate として
              est - est/4 と est + est/4 の 2 つを到着間隔の窓に入れる（平均 est、標準偏差 est/4 になる）。
            * 2 回目以降は「今回 - 前回」を窓に追加する。負なら（時計の巻き戻り）ValueError。
            * 窓は直近 window_size 個だけを保持する（古いものから捨てる）。
        - mean(): 窓の平均。std(): 窓の母標準偏差（statistics.pstdev）と min_std の大きい方。
          まだハートビートがなければ、どちらも ValueError。
        - phi(): まだハートビートがなければ 0.0。それ以外は elapsed = clock() - 最終受信時刻、
          μ = mean() + acceptable_pause、σ = std() として上の式で φ を計算する。
          P_later が 0（浮動小数点の下限を下回る）なら math.inf を返す（例外にしない）。
        - is_available(): phi() < threshold。
        - 引数の検証（ValueError）: threshold <= 0, window_size < 1, min_std <= 0,
          acceptable_pause < 0, first_heartbeat_estimate <= 0。

    パラメータの意味:
        min_std: ばらつきが 0 に近いと、わずかな遅れで φ が跳ね上がる。その下限。
        acceptable_pause: GC 停止などで想定される一時停止の長さ。その分だけ分布を後ろにずらす。

    ヒント: math.erfc(x) は相補誤差関数。例えば t = μ のとき P_later = 0.5、φ ≈ 0.301。
    """

    def __init__(
        self,
        threshold: float = 8.0,
        window_size: int = 100,
        min_std: float = 0.1,
        acceptable_pause: float = 0.0,
        first_heartbeat_estimate: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.__init__ を実装してください")

    def heartbeat(self) -> None:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.heartbeat を実装してください")

    def mean(self) -> float:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.mean を実装してください")

    def std(self) -> float:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.std を実装してください")

    def phi(self) -> float:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.phi を実装してください")

    def is_available(self) -> bool:
        raise NotImplementedError("演習7: PhiAccrualFailureDetector.is_available を実装してください")
