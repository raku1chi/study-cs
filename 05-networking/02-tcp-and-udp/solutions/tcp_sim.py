"""5.2 TCPとUDP — 解答例（tcp_sim）

演習の仕様は exercises/tcp_sim.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


class LossyChannel:
    def __init__(self, pattern: Sequence[bool]) -> None:
        self._pattern = list(pattern)
        self.sent = 0

    def transmit(self) -> bool:
        i = self.sent
        self.sent += 1
        return not (i < len(self._pattern) and self._pattern[i])


@dataclass
class SimResult:
    transmissions: int
    rounds: int
    delivered: list[int] = field(default_factory=list)
    log: list[tuple[int, int, bool]] = field(default_factory=list)


def _validate(n_packets: int, window: int) -> None:
    if n_packets < 0:
        raise ValueError(f"n_packets は 0 以上です: {n_packets}")
    if window < 1:
        raise ValueError(f"window は 1 以上です: {window}")


# ---------------------------------------------------------------------------
# 演習2: Go-Back-N と Selective Repeat
# ---------------------------------------------------------------------------

def simulate_go_back_n(n_packets: int, window: int, loss: Sequence[bool]) -> SimResult:
    _validate(n_packets, window)
    channel = LossyChannel(loss)
    result = SimResult(transmissions=0, rounds=0)
    base = 0  # まだ確認応答されていない最小の番号
    while base < n_packets:
        result.rounds += 1
        expected = base  # 受信側が次に受け取れる番号
        for seq in range(base, min(base + window, n_packets)):
            ok = channel.transmit()
            result.log.append((result.rounds, seq, ok))
            # Go-Back-N の受信側は順番どおりのものだけを受け取り、それ以外は捨てる
            if ok and seq == expected:
                result.delivered.append(seq)
                expected += 1
        # 累積 ACK で base が進む。途中で 1 つでも失われると、その後ろは全部送り直し
        base = expected
    result.transmissions = channel.sent
    return result


def simulate_selective_repeat(n_packets: int, window: int, loss: Sequence[bool]) -> SimResult:
    _validate(n_packets, window)
    channel = LossyChannel(loss)
    result = SimResult(transmissions=0, rounds=0)
    received = [False] * n_packets  # 受信側がバッファした（＝個別に ACK した）番号
    base = 0
    while base < n_packets:
        result.rounds += 1
        for seq in range(base, min(base + window, n_packets)):
            if received[seq]:
                continue  # 個別に ACK 済みのものは送り直さない
            ok = channel.transmit()
            result.log.append((result.rounds, seq, ok))
            if ok:
                received[seq] = True
        # 順番がそろった分だけアプリケーションに渡し、ウィンドウを進める
        while base < n_packets and received[base]:
            result.delivered.append(base)
            base += 1
    result.transmissions = channel.sent
    return result


# ---------------------------------------------------------------------------
# 演習3: 輻輳ウィンドウの変化（TCP Reno / Tahoe の簡略モデル）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CongestionState:
    cwnd: int
    ssthresh: int
    phase: str


class RenoCongestionControl:
    def __init__(self, *, initial_cwnd: int = 10, initial_ssthresh: int = 1 << 30, variant: str = "reno") -> None:
        if initial_cwnd < 1 or initial_ssthresh < 2:
            raise ValueError("initial_cwnd は 1 以上、initial_ssthresh は 2 以上です")
        if variant not in ("reno", "tahoe"):
            raise ValueError(f"variant は 'reno' か 'tahoe' です: {variant!r}")
        self.cwnd = initial_cwnd
        self.ssthresh = initial_ssthresh
        self.variant = variant
        self.in_fast_recovery = False
        self._dupacks = 0
        self._ca_count = 0  # 輻輳回避で「cwnd 個の ACK ごとに +1」を数えるカウンタ

    @property
    def phase(self) -> str:
        if self.in_fast_recovery:
            return "fast_recovery"
        return "slow_start" if self.cwnd < self.ssthresh else "congestion_avoidance"

    def on_ack(self) -> None:
        self._dupacks = 0
        if self.in_fast_recovery:
            # 新しいデータの ACK で高速回復を抜け、膨らませた cwnd を ssthresh に戻す
            self.in_fast_recovery = False
            self.cwnd = self.ssthresh
            self._ca_count = 0
        elif self.cwnd < self.ssthresh:
            self.cwnd += 1  # スロースタート: ACK 1 つにつき +1（1 RTT で約 2 倍）
        else:
            # 輻輳回避: cwnd 個の ACK（≒ 1 RTT）で +1。AIMD の「加算的増加」
            self._ca_count += 1
            if self._ca_count >= self.cwnd:
                self.cwnd += 1
                self._ca_count = 0

    def on_dupack(self) -> None:
        if self.in_fast_recovery:
            self.cwnd += 1  # 重複 ACK 1 つ ＝ 1 セグメントがネットワークから抜けた。その分を補う
            return
        self._dupacks += 1
        if self._dupacks == 3:
            # 高速再送。損失は起きたがデータは流れ続けているので、「乗算的減少」で半分にする
            self.ssthresh = max(self.cwnd // 2, 2)
            self._ca_count = 0
            if self.variant == "reno":
                self.cwnd = self.ssthresh + 3  # 3 つの重複 ACK の分だけ膨らませて高速回復へ
                self.in_fast_recovery = True
            else:
                self.cwnd = 1  # Tahoe には高速回復がなく、スロースタートからやり直す

    def on_timeout(self) -> None:
        # タイムアウトは深刻な輻輳のしるし。cwnd を 1 に戻してスロースタートから
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = 1
        self.in_fast_recovery = False
        self._dupacks = 0
        self._ca_count = 0

    def state(self) -> CongestionState:
        return CongestionState(self.cwnd, self.ssthresh, self.phase)


def cwnd_trace(
    events: Iterable[str],
    *,
    initial_cwnd: int = 10,
    initial_ssthresh: int = 1 << 30,
    variant: str = "reno",
) -> list[CongestionState]:
    cc = RenoCongestionControl(initial_cwnd=initial_cwnd, initial_ssthresh=initial_ssthresh, variant=variant)
    handlers = {"ack": cc.on_ack, "dupack": cc.on_dupack, "timeout": cc.on_timeout}
    trace: list[CongestionState] = []
    for event in events:
        if event not in handlers:
            raise ValueError(f"未知のイベントです: {event!r}")
        handlers[event]()
        trace.append(cc.state())
    return trace
