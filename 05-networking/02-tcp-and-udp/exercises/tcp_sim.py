"""5.2 TCPとUDP — 演習（tcp_sim）: 再送制御と輻輳制御のシミュレーション

この演習では、TCP の信頼性と輻輳制御の核となる仕組みを、決定的（毎回同じ結果になる）な
シミュレーションとして実装します。本物の TCP をそのまま再現するのではなく、仕組みの本質が
見えるように簡略化したモデルです（簡略化の内容は各 docstring に書いてあります）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.2
    python3 tools/check.py -v 5.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_tcp_sim
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence


class LossyChannel:
    """決定的にパケットを失う通信路（実装済み）。

    pattern[i] が True なら、i 回目（0 始まり）の送信は失われます。
    pattern を使い切った後の送信は、すべて届きます。

    >>> ch = LossyChannel([False, True])
    >>> [ch.transmit(), ch.transmit(), ch.transmit()]
    [True, False, True]
    >>> ch.sent
    3
    """

    def __init__(self, pattern: Sequence[bool]) -> None:
        self._pattern = list(pattern)
        self.sent = 0

    def transmit(self) -> bool:
        """1 回送信し、届いたら True、失われたら False を返す。"""
        i = self.sent
        self.sent += 1
        return not (i < len(self._pattern) and self._pattern[i])


@dataclass
class SimResult:
    """シミュレーションの結果（実装済み）。

    transmissions: データパケットを送信した総回数（再送を含む）
    rounds: かかったラウンド数（1 ラウンド ≒ 1 RTT）
    delivered: 受信側がアプリケーションに渡したパケット番号（順番どおりなら [0, 1, ..., n-1]）
    log: 送信 1 回ごとの (ラウンド番号（1 始まり）, パケット番号, 届いたか) のリスト
    """

    transmissions: int
    rounds: int
    delivered: list[int] = field(default_factory=list)
    log: list[tuple[int, int, bool]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 演習2（★★★）: Go-Back-N と Selective Repeat
# ---------------------------------------------------------------------------
#
# 共通のモデル（ラウンド単位に簡略化したもの）:
#   - 送信側は番号 0〜n_packets-1 のパケットを、ウィンドウ window 個まで確認応答を待たずに送れる。
#   - 1 ラウンドでは、ウィンドウ [base, base + window) の中の送るべきパケットを、番号の小さい順に
#     1 つずつ channel.transmit() で送る（この順番で損失パターンを消費すること）。
#   - ACK は失われない。ラウンドの終わりに、送信側は受信側の状態を ACK で知り、base を進める。
#   - base が n_packets に達したら終わり。n_packets == 0 なら 0 ラウンドで終わる。
#   - n_packets < 0 または window < 1 なら ValueError。
#   - 各送信を log に (ラウンド番号, パケット番号, 届いたか) として記録する。


def simulate_go_back_n(n_packets: int, window: int, loss: Sequence[bool]) -> SimResult:
    """Go-Back-N をシミュレーションする。

    - 受信側は「次に期待する番号」のパケットだけを受け取り（delivered に追加）、それ以外
      （順番が飛んだもの）は届いても捨てる。ACK は「ここまで順番どおりに受け取った」という
      累積 ACK になる。
    - 送信側は毎ラウンド、ウィンドウ内のパケットをすべて送る（前のラウンドで届いていたものも）。
      ラウンドの終わりに base を「受信側が次に期待する番号」まで進める。

    例: n=5, window=3, 2 回目の送信（#1）だけが失われる場合
        ラウンド 1: #0 届く / #1 失われる / #2 届くが順番が飛んでいるので捨てられる → base=1
        ラウンド 2: #1, #2, #3 がすべて届く → base=4
        ラウンド 3: #4 が届く → base=5 で終了。送信 7 回、3 ラウンド

    >>> r = simulate_go_back_n(5, 3, [False, True])
    >>> (r.transmissions, r.rounds, r.delivered)
    (7, 3, [0, 1, 2, 3, 4])
    """
    raise NotImplementedError("演習2: simulate_go_back_n を実装してください")


def simulate_selective_repeat(n_packets: int, window: int, loss: Sequence[bool]) -> SimResult:
    """Selective Repeat をシミュレーションする。

    - 受信側は、順番が飛んでいても届いたパケットをバッファし、パケットごとに個別の ACK を返す。
      順番がそろった分から delivered に追加する（delivered は常に番号順）。
    - 送信側は毎ラウンド、ウィンドウ内の「まだ ACK されていない」パケットだけを送る。
      ラウンドの終わりに、base を「まだ ACK されていない最小の番号」まで進める。

    同じ例（n=5, window=3, 2 回目の送信だけが失われる）では:
        ラウンド 1: #0 届く / #1 失われる / #2 届く（バッファされる） → base=1
        ラウンド 2: ウィンドウは [1, 4)。#2 は ACK 済みなので、#1 と #3 だけを送る → base=4
        ラウンド 3: #4 → 終了。送信 6 回、3 ラウンド

    >>> r = simulate_selective_repeat(5, 3, [False, True])
    >>> (r.transmissions, r.rounds)
    (6, 3)
    """
    raise NotImplementedError("演習2: simulate_selective_repeat を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 輻輳ウィンドウの変化（TCP Reno / Tahoe の簡略モデル）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CongestionState:
    """あるイベントを処理した直後の状態（実装済み）。phase は下記の 3 つのいずれか。"""

    cwnd: int
    ssthresh: int
    phase: str


class RenoCongestionControl:
    """TCP Reno（variant="reno"）と Tahoe（variant="tahoe"）の輻輳制御の簡略モデル。

    cwnd（輻輳ウィンドウ）と ssthresh（スロースタートの閾値）は **セグメント数** で数えます。
    Linux のカーネルと同じく、輻輳回避での「1 RTT に 1 セグメント」の増加は、ACK を数える
    カウンタで整数のまま扱います。

    phase（状態）:
        "fast_recovery"          高速回復中（Reno のみ）
        "slow_start"             cwnd < ssthresh
        "congestion_avoidance"   cwnd >= ssthresh

    イベントと動作:
        on_ack()     新しいデータの ACK が 1 つ届いた（1 セグメント分の確認応答）。
            - 重複 ACK のカウンタを 0 に戻す。
            - 高速回復中なら: cwnd = ssthresh にして高速回復を抜ける（輻輳回避のカウンタも 0 に）。
            - スロースタートなら: cwnd += 1。
            - 輻輳回避なら: カウンタを 1 増やし、カウンタ >= cwnd になったら cwnd += 1、カウンタ = 0。
        on_dupack()  重複 ACK が 1 つ届いた（受信側に順番の飛んだデータが届いている＝どれかが失われた）。
            - 高速回復中なら: cwnd += 1（抜けたセグメントの分だけウィンドウを膨らませる）。
            - そうでなければ重複 ACK を数え、ちょうど 3 つ目で高速再送:
                ssthresh = max(cwnd // 2, 2)、輻輳回避のカウンタ = 0、そして
                Reno:  cwnd = ssthresh + 3 として高速回復に入る
                Tahoe: cwnd = 1（スロースタートからやり直す）
              4 つ目以降の重複 ACK（高速回復中でない場合）は何もしない。
        on_timeout() 再送タイムアウト。
            - ssthresh = max(cwnd // 2, 2)、cwnd = 1、高速回復を抜け、各カウンタを 0 に。

    簡略化: 本物の TCP は ssthresh を「送信済みで未確認のデータ量（FlightSize）の半分」から
    決めますが、ここでは cwnd の半分を使います。NewReno（RFC 6582）の部分 ACK の処理も省略します。

    >>> cc = RenoCongestionControl(initial_cwnd=10, initial_ssthresh=5)
    >>> for _ in range(3):
    ...     cc.on_dupack()
    >>> (cc.cwnd, cc.ssthresh, cc.phase)
    (8, 5, 'fast_recovery')
    """

    def __init__(self, *, initial_cwnd: int = 10, initial_ssthresh: int = 1 << 30, variant: str = "reno") -> None:
        """状態を初期化する（実装済み）。初期値は RFC 6928 の初期ウィンドウ 10 と「十分大きな」ssthresh。"""
        if initial_cwnd < 1 or initial_ssthresh < 2:
            raise ValueError("initial_cwnd は 1 以上、initial_ssthresh は 2 以上です")
        if variant not in ("reno", "tahoe"):
            raise ValueError(f"variant は 'reno' か 'tahoe' です: {variant!r}")
        self.cwnd = initial_cwnd
        self.ssthresh = initial_ssthresh
        self.variant = variant
        self.in_fast_recovery = False
        self._dupacks = 0  # 連続した重複 ACK の数
        self._ca_count = 0  # 輻輳回避で「cwnd 個の ACK ごとに +1」を数えるカウンタ

    @property
    def phase(self) -> str:
        """現在の状態（"fast_recovery" / "slow_start" / "congestion_avoidance"）。"""
        raise NotImplementedError("演習3: RenoCongestionControl.phase を実装してください")

    def on_ack(self) -> None:
        raise NotImplementedError("演習3: RenoCongestionControl.on_ack を実装してください")

    def on_dupack(self) -> None:
        raise NotImplementedError("演習3: RenoCongestionControl.on_dupack を実装してください")

    def on_timeout(self) -> None:
        raise NotImplementedError("演習3: RenoCongestionControl.on_timeout を実装してください")

    def state(self) -> CongestionState:
        """現在の状態のスナップショット（実装済み）。"""
        return CongestionState(self.cwnd, self.ssthresh, self.phase)


def cwnd_trace(
    events: Iterable[str],
    *,
    initial_cwnd: int = 10,
    initial_ssthresh: int = 1 << 30,
    variant: str = "reno",
) -> list[CongestionState]:
    """イベント列（"ack" / "dupack" / "timeout"）を順に処理し、各イベントの直後の状態のリストを返す。

    - RenoCongestionControl を作って、イベントごとに on_ack / on_dupack / on_timeout を呼ぶ。
    - 未知のイベントは ValueError。

    >>> [s.cwnd for s in cwnd_trace(["ack"] * 4, initial_cwnd=1, initial_ssthresh=4)]
    [2, 3, 4, 4]
    """
    raise NotImplementedError("演習3: cwnd_trace を実装してください")
