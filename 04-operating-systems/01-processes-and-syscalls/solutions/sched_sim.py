"""4.1 プロセス・スレッド・システムコール — 解答例: CPU スケジューリングシミュレータ

演習の仕様は exercises/sched_sim.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import heapq
from collections import deque
from typing import NamedTuple, Sequence

IDLE = None  # CPU が空いている区間の名前
SWITCH = "<cs>"  # コンテキストスイッチに使われた区間の名前


class Process(NamedTuple):
    name: str
    arrival: int  # 到着時刻（実行可能になった時刻）
    burst: int  # 必要な CPU 時間


class Slice(NamedTuple):
    start: int
    end: int
    name: str | None  # プロセス名、SWITCH、または IDLE(None)


class Metrics(NamedTuple):
    completion: int
    turnaround: int
    waiting: int
    response: int


class Averages(NamedTuple):
    turnaround: float
    waiting: float
    response: float


# ---------------------------------------------------------------------------
# 補助関数（スタブでも実装済みで提供）
# ---------------------------------------------------------------------------

def validate_processes(procs: Sequence[Process]) -> None:
    names = set()
    for p in procs:
        if not isinstance(p.name, str) or not p.name or p.name == SWITCH:
            raise ValueError(f"プロセス名が不正です: {p.name!r}")
        if p.name in names:
            raise ValueError(f"プロセス名が重複しています: {p.name!r}")
        names.add(p.name)
        if not isinstance(p.arrival, int) or p.arrival < 0:
            raise ValueError(f"{p.name}: arrival は 0 以上の整数: {p.arrival!r}")
        if not isinstance(p.burst, int) or p.burst < 1:
            raise ValueError(f"{p.name}: burst は 1 以上の整数: {p.burst!r}")


def add_slice(timeline: list[Slice], start: int, end: int, name: str | None) -> None:
    if end <= start:
        return
    if timeline and timeline[-1].name == name and timeline[-1].end == start:
        timeline[-1] = Slice(timeline[-1].start, end, name)
    else:
        timeline.append(Slice(start, end, name))


def format_gantt(timeline: Sequence[Slice]) -> str:
    if not timeline:
        return "(空)"
    total = timeline[-1].end
    rows: dict[str, list[str]] = {}
    for s in timeline:
        label = "idle" if s.name is IDLE else ("cs" if s.name == SWITCH else s.name)
        rows.setdefault(label, ["·"] * total)
        for t in range(s.start, s.end):
            rows[label][t] = "█"
    width = max(len(label) for label in rows)
    lines = [f"{label:<{width}} |{''.join(cells)}|" for label, cells in rows.items()]
    lines.append(f"{'':<{width}}  0〜{total}（1 文字 = 1 単位時間）")
    return "\n".join(lines)


def _arrival_order(procs: Sequence[Process]) -> list[int]:
    # 到着時刻の順。同時に到着したら入力の順（添字の小さい順）
    return sorted(range(len(procs)), key=lambda i: (procs[i].arrival, i))


# ---------------------------------------------------------------------------
# 演習1a: 評価指標の計算
# ---------------------------------------------------------------------------

def compute_metrics(procs: Sequence[Process], timeline: Sequence[Slice]) -> dict[str, Metrics]:
    validate_processes(procs)
    by_name = {p.name: p for p in procs}
    first_run: dict[str, int] = {}
    last_end: dict[str, int] = {}
    ran = {p.name: 0 for p in procs}
    prev_end = 0
    for s in timeline:
        if s.end <= s.start:
            raise ValueError(f"長さが 0 以下の区間があります: {s}")
        if s.start < prev_end:
            raise ValueError(f"区間が重なっているか、時刻順に並んでいません: {s}")
        prev_end = s.end
        if s.name is IDLE or s.name == SWITCH:
            continue
        p = by_name.get(s.name)
        if p is None:
            raise ValueError(f"未知のプロセスです: {s.name!r}")
        if s.start < p.arrival:
            raise ValueError(f"{p.name} が到着前（{p.arrival}）に実行されています: {s}")
        first_run.setdefault(p.name, s.start)
        last_end[p.name] = s.end
        ran[p.name] += s.end - s.start
    result: dict[str, Metrics] = {}
    for p in procs:
        if ran[p.name] != p.burst:
            raise ValueError(f"{p.name} の実行時間の合計 {ran[p.name]} が burst {p.burst} と一致しません")
        completion = last_end[p.name]
        turnaround = completion - p.arrival  # 到着から完了までの時間
        result[p.name] = Metrics(
            completion=completion,
            turnaround=turnaround,
            waiting=turnaround - p.burst,  # CPU を待っていた時間の合計
            response=first_run[p.name] - p.arrival,  # 初めて CPU をもらうまでの時間
        )
    return result


def average(metrics: dict[str, Metrics]) -> Averages:
    if not metrics:
        raise ValueError("プロセスがありません")
    n = len(metrics)
    return Averages(
        turnaround=sum(m.turnaround for m in metrics.values()) / n,
        waiting=sum(m.waiting for m in metrics.values()) / n,
        response=sum(m.response for m in metrics.values()) / n,
    )


# ---------------------------------------------------------------------------
# 演習1b: FIFO・SJF・SRTF
# ---------------------------------------------------------------------------

def fifo(procs: Sequence[Process]) -> list[Slice]:
    validate_processes(procs)
    timeline: list[Slice] = []
    t = 0
    for i in _arrival_order(procs):
        p = procs[i]
        if t < p.arrival:  # 誰も来ていなければ CPU は遊ぶ
            add_slice(timeline, t, p.arrival, IDLE)
            t = p.arrival
        add_slice(timeline, t, t + p.burst, p.name)  # 到着順に最後まで走らせる
        t += p.burst
    return timeline


def sjf(procs: Sequence[Process]) -> list[Slice]:
    validate_processes(procs)
    order = _arrival_order(procs)
    timeline: list[Slice] = []
    ready: list[tuple[int, int, int]] = []  # (burst, arrival, index) の最小ヒープ
    t = k = 0
    while k < len(order) or ready:
        while k < len(order) and procs[order[k]].arrival <= t:
            i = order[k]
            heapq.heappush(ready, (procs[i].burst, procs[i].arrival, i))
            k += 1
        if not ready:
            nxt = procs[order[k]].arrival
            add_slice(timeline, t, nxt, IDLE)
            t = nxt
            continue
        _, _, i = heapq.heappop(ready)  # 到着済みの中で最も短いものを選ぶ
        add_slice(timeline, t, t + procs[i].burst, procs[i].name)  # 非プリエンプティブ
        t += procs[i].burst
    return timeline


def srtf(procs: Sequence[Process]) -> list[Slice]:
    validate_processes(procs)
    order = _arrival_order(procs)
    remaining = [p.burst for p in procs]
    timeline: list[Slice] = []
    ready: list[tuple[int, int, int]] = []  # (残り時間, arrival, index) の最小ヒープ
    t = k = 0
    while k < len(order) or ready:
        while k < len(order) and procs[order[k]].arrival <= t:
            i = order[k]
            heapq.heappush(ready, (remaining[i], procs[i].arrival, i))
            k += 1
        if not ready:
            nxt = procs[order[k]].arrival
            add_slice(timeline, t, nxt, IDLE)
            t = nxt
            continue
        _, arrival, i = heapq.heappop(ready)
        # 判断をやり直す必要があるのは「次の到着」か「完了」のときだけ（イベント駆動）
        next_arrival = procs[order[k]].arrival if k < len(order) else None
        until = t + remaining[i]
        if next_arrival is not None and next_arrival < until:
            until = next_arrival
        add_slice(timeline, t, until, procs[i].name)  # 同じプロセスが続けば区間は結合される
        remaining[i] -= until - t
        t = until
        if remaining[i] > 0:
            # 残り時間が同じなら先に到着した方が優先されるので、同点では横取りされない
            heapq.heappush(ready, (remaining[i], arrival, i))
    return timeline


# ---------------------------------------------------------------------------
# 演習2: ラウンドロビン（コンテキストスイッチのコスト付き）
# ---------------------------------------------------------------------------

def round_robin(procs: Sequence[Process], quantum: int, switch_cost: int = 0) -> list[Slice]:
    validate_processes(procs)
    if not isinstance(quantum, int) or quantum < 1:
        raise ValueError(f"quantum は 1 以上の整数: {quantum!r}")
    if not isinstance(switch_cost, int) or switch_cost < 0:
        raise ValueError(f"switch_cost は 0 以上の整数: {switch_cost!r}")
    order = _arrival_order(procs)
    remaining = [p.burst for p in procs]
    queue: deque[int] = deque()
    timeline: list[Slice] = []
    t = k = 0
    last: int | None = None  # 直前に CPU を使っていたプロセス（アイドルを挟んだら None）

    def admit(upto: int) -> None:
        nonlocal k
        while k < len(order) and procs[order[k]].arrival <= upto:
            queue.append(order[k])
            k += 1

    admit(t)
    while queue or k < len(order):
        if not queue:
            nxt = procs[order[k]].arrival
            add_slice(timeline, t, nxt, IDLE)
            t, last = nxt, None
            admit(t)
            continue
        i = queue.popleft()
        if switch_cost and last is not None and last != i:
            # 別のプロセスへ切り替えるたびに、レジスタの退避・復元などのコストがかかる
            add_slice(timeline, t, t + switch_cost, SWITCH)
            t += switch_cost
            admit(t)
        run = min(quantum, remaining[i])
        add_slice(timeline, t, t + run, procs[i].name)
        t += run
        remaining[i] -= run
        # 規約: 同じ時刻に到着したプロセスは、横取りされたプロセスより先に並ぶ
        admit(t)
        if remaining[i] > 0:
            queue.append(i)
        last = i
    return timeline


# ---------------------------------------------------------------------------
# 演習3: 多段フィードバックキュー（MLFQ）
# ---------------------------------------------------------------------------

def mlfq(
    procs: Sequence[Process],
    quanta: Sequence[int] = (2, 4, 8),
    boost_interval: int | None = None,
) -> list[Slice]:
    validate_processes(procs)
    if not quanta or any(not isinstance(q, int) or q < 1 for q in quanta):
        raise ValueError(f"quanta は 1 以上の整数を 1 つ以上: {quanta!r}")
    if boost_interval is not None and (not isinstance(boost_interval, int) or boost_interval < 1):
        raise ValueError(f"boost_interval は None か 1 以上の整数: {boost_interval!r}")
    n, levels = len(procs), len(quanta)
    order = _arrival_order(procs)
    queues: list[deque[int]] = [deque() for _ in range(levels)]
    level = [0] * n  # 現在の優先度レベル（0 が最高）
    used = [0] * n  # 現在のレベルで使った CPU 時間（横取りされても引き継ぐ）
    remaining = [p.burst for p in procs]
    timeline: list[Slice] = []
    running: int | None = None
    t = k = finished = 0

    # 1 単位時間ずつ進める。本物のスケジューラはイベント駆動だが、規則を追いやすさを優先した
    while finished < n:
        # (1) この時刻に到着したプロセスは最高レベルの末尾へ
        while k < n and procs[order[k]].arrival <= t:
            queues[0].append(order[k])
            k += 1
        # (2) タイムスライス（割り当て）を使い切ったら 1 段下げる（最下段はそのまま）
        if running is not None and used[running] >= quanta[level[running]]:
            level[running] = min(level[running] + 1, levels - 1)
            used[running] = 0
            queues[level[running]].append(running)
            running = None
        # (3) 優先度ブースト: 飢餓（starvation）を防ぐため、定期的に全員を最高レベルへ戻す
        if boost_interval is not None and t > 0 and t % boost_interval == 0:
            moved = [i for q in queues for i in q]
            for q in queues:
                q.clear()
            for i in moved:
                level[i], used[i] = 0, 0
            queues[0].extend(moved)
            if running is not None:
                level[running], used[running] = 0, 0
        # (4) より高いレベルに実行可能なプロセスがいれば横取り（preempt）する
        if running is not None and any(queues[lv] for lv in range(level[running])):
            queues[level[running]].append(running)
            running = None
        # (5) 最も高いレベルの先頭を選ぶ
        if running is None:
            for q in queues:
                if q:
                    running = q.popleft()
                    break
        if running is None:  # 誰もいない: 次の到着まで時間を進める
            nxt = procs[order[k]].arrival
            add_slice(timeline, t, nxt, IDLE)
            t = nxt
            continue
        # (6) 1 単位時間だけ実行する
        add_slice(timeline, t, t + 1, procs[running].name)
        t += 1
        remaining[running] -= 1
        used[running] += 1
        if remaining[running] == 0:
            finished += 1
            running = None
    return timeline
