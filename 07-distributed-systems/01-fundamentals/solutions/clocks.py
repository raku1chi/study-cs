"""7.1 分散システムの本質 — 演習: 論理時計（解答例）

演習の仕様は exercises/clocks.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 演習1: Lamport 時計
# ---------------------------------------------------------------------------


class LamportClock:
    def __init__(self) -> None:
        self._time = 0

    @property
    def time(self) -> int:
        return self._time

    def tick(self) -> int:
        # ローカルイベント（送信を含む）の前に必ず 1 進める
        self._time += 1
        return self._time

    def send(self) -> int:
        # 送信もイベントの一種。進めた値をメッセージに添える
        return self.tick()

    def receive(self, remote_time: int) -> int:
        if remote_time < 0:
            raise ValueError(f"タイムスタンプは 0 以上です: {remote_time}")
        # 「相手が知っている時刻」と「自分の時刻」の大きい方より、さらに後ろに置く
        self._time = max(self._time, remote_time) + 1
        return self._time


# ---------------------------------------------------------------------------
# 演習2: ベクトル時計
# ---------------------------------------------------------------------------


class Ordering(Enum):
    BEFORE = "before"
    AFTER = "after"
    CONCURRENT = "concurrent"
    EQUAL = "equal"


class VectorClock:
    """不変（immutable）なベクトル時計。0 の要素は持たない形に正規化する。"""

    __slots__ = ("_entries",)

    def __init__(self, entries: Mapping[str, int] | None = None) -> None:
        cleaned: dict[str, int] = {}
        for node, count in (entries or {}).items():
            if not isinstance(count, int) or count < 0:
                raise ValueError(f"カウンタは 0 以上の整数です: {node}={count!r}")
            if count:
                cleaned[node] = count
        self._entries = cleaned

    def get(self, node: str) -> int:
        return self._entries.get(node, 0)

    def increment(self, node: str) -> VectorClock:
        entries = dict(self._entries)
        entries[node] = entries.get(node, 0) + 1
        return VectorClock(entries)

    def merge(self, other: VectorClock) -> VectorClock:
        # 要素ごとの最大値 = 「どちらかが知っていたことを、すべて知っている」状態
        nodes = self._entries.keys() | other._entries.keys()
        return VectorClock({n: max(self.get(n), other.get(n)) for n in nodes})

    def compare(self, other: VectorClock) -> Ordering:
        nodes = self._entries.keys() | other._entries.keys()
        le = all(self.get(n) <= other.get(n) for n in nodes)
        ge = all(self.get(n) >= other.get(n) for n in nodes)
        if le and ge:
            return Ordering.EQUAL
        if le:
            return Ordering.BEFORE  # self → other（self が因果的に先）
        if ge:
            return Ordering.AFTER
        # どちらの方向にも「全要素が以下」が成り立たない = 互いに知らない = 並行
        return Ordering.CONCURRENT

    def to_dict(self) -> dict[str, int]:
        return dict(sorted(self._entries.items()))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VectorClock):
            return NotImplemented
        return self._entries == other._entries

    def __hash__(self) -> int:
        return hash(frozenset(self._entries.items()))

    def __repr__(self) -> str:
        return f"VectorClock({self.to_dict()})"


# ---------------------------------------------------------------------------
# 演習3: トレースの解析
# ---------------------------------------------------------------------------

KINDS = ("local", "send", "recv")


@dataclass(frozen=True)
class Event:
    name: str
    node: str
    kind: str = "local"
    msg: str | None = None


def _validate(trace: Sequence[Event]) -> None:
    names: set[str] = set()
    sent: set[str] = set()
    received: set[str] = set()
    for ev in trace:
        if ev.name in names:
            raise ValueError(f"イベント名が重複しています: {ev.name}")
        names.add(ev.name)
        if ev.kind not in KINDS:
            raise ValueError(f"不明な種類です: {ev.kind!r}（{ev.name}）")
        if ev.kind == "local":
            if ev.msg is not None:
                raise ValueError(f"local イベントに msg は指定できません: {ev.name}")
            continue
        if ev.msg is None:
            raise ValueError(f"{ev.kind} イベントには msg が必要です: {ev.name}")
        if ev.kind == "send":
            if ev.msg in sent:
                raise ValueError(f"メッセージ {ev.msg} が 2 回送信されています")
            sent.add(ev.msg)
        else:
            if ev.msg not in sent:
                raise ValueError(f"未送信のメッセージ {ev.msg} を受信しています: {ev.name}")
            if ev.msg in received:
                raise ValueError(f"メッセージ {ev.msg} が 2 回受信されています")
            received.add(ev.msg)


def lamport_timestamps(trace: Sequence[Event]) -> dict[str, int]:
    _validate(trace)
    clocks: dict[str, LamportClock] = {}
    msg_time: dict[str, int] = {}
    result: dict[str, int] = {}
    for ev in trace:
        clock = clocks.setdefault(ev.node, LamportClock())
        if ev.kind == "recv":
            result[ev.name] = clock.receive(msg_time[ev.msg])  # type: ignore[index]
        else:
            result[ev.name] = clock.tick()
            if ev.kind == "send":
                msg_time[ev.msg] = result[ev.name]  # type: ignore[index]
    return result


def vector_timestamps(trace: Sequence[Event]) -> dict[str, VectorClock]:
    _validate(trace)
    current: dict[str, VectorClock] = {}
    msg_clock: dict[str, VectorClock] = {}
    result: dict[str, VectorClock] = {}
    for ev in trace:
        vc = current.get(ev.node, VectorClock())
        if ev.kind == "recv":
            # 受信: 送信側の知識を取り込んでから、自分の要素を進める
            vc = vc.merge(msg_clock[ev.msg])  # type: ignore[index]
        vc = vc.increment(ev.node)
        if ev.kind == "send":
            msg_clock[ev.msg] = vc  # type: ignore[index]
        current[ev.node] = vc
        result[ev.name] = vc
    return result


def lamport_total_order(trace: Sequence[Event]) -> list[str]:
    stamps = lamport_timestamps(trace)
    node_of = {ev.name: ev.node for ev in trace}
    # (Lamport 時刻, ノード名) は一意なので、全順序になる
    return sorted(stamps, key=lambda name: (stamps[name], node_of[name]))


def concurrent_pairs(
    trace: Sequence[Event], names: Iterable[str] | None = None
) -> list[tuple[str, str]]:
    stamps = vector_timestamps(trace)
    position = {ev.name: i for i, ev in enumerate(trace)}
    if names is None:
        targets = [ev.name for ev in trace]
    else:
        targets = list(dict.fromkeys(names))
        for name in targets:
            if name not in stamps:
                raise KeyError(name)
    targets.sort(key=position.__getitem__)
    pairs: list[tuple[str, str]] = []
    for i, a in enumerate(targets):
        for b in targets[i + 1 :]:
            if stamps[a].compare(stamps[b]) is Ordering.CONCURRENT:
                pairs.append((a, b))
    return pairs
