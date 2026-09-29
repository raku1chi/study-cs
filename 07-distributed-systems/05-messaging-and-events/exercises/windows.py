"""7.5 メッセージングとイベント駆動 — 演習: イベント時刻のウィンドウ集計とウォーターマーク

ストリーム処理では「10 秒ごとの売上」「5 分間のアクセス数」のように、時間で区切った窓（ウィンドウ）で集計します。
ところが、イベントは発生した順に届くとは限りません（スマートフォンの再接続、ネットワークの遅延、再送）。
そこで、イベントに付いている **発生時刻**（event time）で窓に振り分け、「この時刻までのイベントは
もう来ないだろう」という推定＝**ウォーターマーク**（watermark）が窓の終わりを越えたら結果を出します。

この演習の約束（Apache Flink などの考え方を簡略化したもの）:
    - ウィンドウは [start, start + size) の半開区間。start は slide の倍数（slide == size ならタンブリング）。
    - ウォーターマーク = これまでに見た最大の event_time - max_out_of_orderness（決して戻らない）。
      最初のイベントまでは None。
    - ウィンドウは、ウォーターマークが end 以上になったら **発火**（結果を出す）する。
    - 発火後も、ウォーターマークが end + allowed_lateness に達するまでは状態を残し、遅れて届いたイベントを反映して
      **更新結果**（is_update=True）を出す。達したら状態を捨てる。
    - どのウィンドウにも入れられない（すべて捨てた後の）イベントは、late_events（サイド出力）に送る。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.5
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_windows
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    key: str  # 集計のキー（例: 店舗 ID）
    value: float  # 集計する値（例: 売上金額）
    event_time: int  # 発生時刻（0 以上の整数。単位は任意、例えば秒）


@dataclass(frozen=True)
class WindowResult:
    key: str
    start: int
    end: int  # start + size（この時刻は含まない）
    count: int  # ウィンドウ内のイベント数
    total: float  # value の合計
    is_update: bool = False  # 発火済みのウィンドウに遅れたイベントが来て、出し直した結果なら True


# ---------------------------------------------------------------------------
# 演習7（★★★）: ウォーターマークと許容遅延のあるウィンドウ集計
# ---------------------------------------------------------------------------


class WindowedAggregator:
    """キーごとに、イベント時刻のウィンドウで件数と合計を集計する。

    __init__(size, slide=None, *, allowed_lateness=0, max_out_of_orderness=0):
        slide が None なら size（タンブリング）。0 < slide <= size でなければ ValueError。
        allowed_lateness・max_out_of_orderness が負なら ValueError。
        属性 watermark（初期値 None）と late_events（初期値 []）を持つこと。

    windows_for(event_time) -> list[int]:
        event_time を含むウィンドウの start の昇順リスト。start は slide の倍数で、start <= event_time < start + size。
        例: size=10, slide=5 なら windows_for(7) == [0, 5]、windows_for(3) == [-5, 0]。

    process(event) -> list[WindowResult]:
        event_time < 0 なら ValueError。次の順に行い、出した結果のリストを返す。
        1. windows_for(event_time) の各ウィンドウについて:
             - ウォーターマークが None でなく、end + allowed_lateness <= ウォーターマーク なら、そのウィンドウは
               閉じている（状態も捨てた）ので飛ばす。
             - そうでなければ (key, start) の件数と合計に加える。そのウィンドウがすでに発火済みなら、
               更新後の値で WindowResult(..., is_update=True) を結果に加える。
           どのウィンドウにも加えられなかったら、event を late_events に追加する。
        2. ウォーターマークを max(これまでの最大の event_time, この event_time) - max_out_of_orderness に更新する
           （前より大きくなるときだけ。戻さない）。大きくなったら:
             - まだ発火していないウィンドウのうち end <= ウォーターマーク のものを発火させ、
               (end, key, start) の昇順に WindowResult を結果に加える。
             - end + allowed_lateness <= ウォーターマーク のウィンドウの状態を捨てる。
        イベントが 1 つもないウィンドウは結果に出さない。

    flush() -> list[WindowResult]:
        ストリームの終わり。まだ発火していないウィンドウをすべて (end, key, start) の昇順に出し、状態を空にする。

    >>> agg = WindowedAggregator(size=10)
    >>> agg.process(Event("k", 2.0, 1)), agg.process(Event("k", 3.0, 2))
    ([], [])
    >>> agg.process(Event("k", 1.0, 11))
    [WindowResult(key='k', start=0, end=10, count=2, total=5.0, is_update=False)]
    """

    def __init__(
        self,
        size: int,
        slide: int | None = None,
        *,
        allowed_lateness: int = 0,
        max_out_of_orderness: int = 0,
    ) -> None:
        raise NotImplementedError("演習7: WindowedAggregator.__init__ を実装してください")

    def windows_for(self, event_time: int) -> list[int]:
        raise NotImplementedError("演習7: WindowedAggregator.windows_for を実装してください")

    def process(self, event: Event) -> list[WindowResult]:
        raise NotImplementedError("演習7: WindowedAggregator.process を実装してください")

    def flush(self) -> list[WindowResult]:
        raise NotImplementedError("演習7: WindowedAggregator.flush を実装してください")
