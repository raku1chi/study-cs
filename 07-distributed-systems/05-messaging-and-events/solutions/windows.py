"""7.5 メッセージングとイベント駆動 — 演習: イベント時刻のウィンドウ集計とウォーターマーク（解答例）

演習の仕様は exercises/windows.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Event:
    key: str
    value: float
    event_time: int


@dataclass(frozen=True)
class WindowResult:
    key: str
    start: int
    end: int
    count: int
    total: float
    is_update: bool = False


class WindowedAggregator:
    def __init__(
        self,
        size: int,
        slide: int | None = None,
        *,
        allowed_lateness: int = 0,
        max_out_of_orderness: int = 0,
    ) -> None:
        slide = size if slide is None else slide
        if size <= 0 or slide <= 0 or slide > size:
            raise ValueError(f"0 < slide <= size で指定してください: size={size}, slide={slide}")
        if allowed_lateness < 0 or max_out_of_orderness < 0:
            raise ValueError("allowed_lateness と max_out_of_orderness は 0 以上です")
        self.size = size
        self.slide = slide
        self.allowed_lateness = allowed_lateness
        self.max_out_of_orderness = max_out_of_orderness
        self.watermark: int | None = None
        self.late_events: list[Event] = []
        self._state: dict[tuple[str, int], list] = {}  # (key, start) → [count, total]
        self._fired: set[tuple[str, int]] = set()
        self._max_event_time: int | None = None

    def windows_for(self, event_time: int) -> list[int]:
        # event_time を含むウィンドウ [start, start + size) の start を列挙する（start は slide の倍数）
        last = event_time - event_time % self.slide
        starts = []
        start = last
        while start > event_time - self.size:
            starts.append(start)
            start -= self.slide
        return sorted(starts)

    def _result(self, key: str, start: int, is_update: bool = False) -> WindowResult:
        count, total = self._state[(key, start)]
        return WindowResult(key, start, start + self.size, count, total, is_update)

    def process(self, event: Event) -> list[WindowResult]:
        if event.event_time < 0:
            raise ValueError(f"event_time は 0 以上です: {event.event_time}")
        results: list[WindowResult] = []
        accepted = False
        for start in self.windows_for(event.event_time):
            end = start + self.size
            if self.watermark is not None and end + self.allowed_lateness <= self.watermark:
                continue  # このウィンドウは許容遅延を過ぎて閉じられ、状態も捨てた
            accepted = True
            state = self._state.setdefault((event.key, start), [0, 0.0])
            state[0] += 1
            state[1] += event.value
            if (event.key, start) in self._fired:
                # 発火済みのウィンドウへの遅れたイベント: 更新した結果をもう一度出す（遅延発火）
                results.append(self._result(event.key, start, is_update=True))
        if not accepted:
            self.late_events.append(event)  # どのウィンドウにも入れられない = 遅すぎる。サイド出力へ
        # ウォーターマーク = これまでに見た最大のイベント時刻 - 想定する乱れの幅。決して戻らない
        if self._max_event_time is None or event.event_time > self._max_event_time:
            self._max_event_time = event.event_time
        new_watermark = self._max_event_time - self.max_out_of_orderness
        if self.watermark is None or new_watermark > self.watermark:
            self.watermark = new_watermark
            results.extend(self._advance())
        return results

    def _advance(self) -> list[WindowResult]:
        assert self.watermark is not None
        ready = [
            ks for ks in self._state if ks not in self._fired and ks[1] + self.size <= self.watermark
        ]
        ready.sort(key=lambda ks: (ks[1] + self.size, ks[0], ks[1]))
        results = []
        for ks in ready:
            self._fired.add(ks)
            results.append(self._result(*ks))
        for ks in list(self._state):
            if ks[1] + self.size + self.allowed_lateness <= self.watermark:
                del self._state[ks]  # もう遅延イベントも受け付けない。状態を捨ててメモリを解放する
                self._fired.discard(ks)
        return results

    def flush(self) -> list[WindowResult]:
        # ストリームの終わり: 未発火のウィンドウをすべて発火させ、状態を空にする
        pending = sorted(
            (ks for ks in self._state if ks not in self._fired),
            key=lambda ks: (ks[1] + self.size, ks[0], ks[1]),
        )
        results = [self._result(*ks) for ks in pending]
        self._state.clear()
        self._fired.clear()
        return results
