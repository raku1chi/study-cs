"""4.5 仮想化とコンテナ — 解答例: CFS 帯域制御（CPU クォータ）のシミュレーション

演習の仕様は exercises/cfs_quota.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import NamedTuple, Sequence


class Burst(NamedTuple):
    name: str
    start: int  # 実行可能になる時刻（ミリ秒）
    work: int  # 必要な CPU 時間（ミリ秒）


class CfsResult(NamedTuple):
    finish: dict[str, int]  # バースト名 -> 完了時刻（ミリ秒）
    nr_periods: int  # 実行可能なバーストがいた周期の数
    nr_throttled: int  # クォータ不足で実行できないバーストが出た周期の数
    throttled_time: int  # 実行可能なバーストがいるのに、クォータが 0 で誰も動けなかった時間（ミリ秒）


def _validate(bursts: Sequence[Burst], quota: int | None, period: int, cpus: int) -> None:
    if period < 1 or cpus < 1:
        raise ValueError("period と cpus は 1 以上")
    if quota is not None and quota < 1:
        raise ValueError("quota は None（無制限）か 1 以上")
    names = [b.name for b in bursts]
    if len(set(names)) != len(names):
        raise ValueError("バーストの名前が重複しています")
    for b in bursts:
        if b.start < 0 or b.work < 1:
            raise ValueError(f"不正なバースト: {b}")


def _run(bursts: Sequence[Burst], quota: int | None, period: int, cpus: int) -> tuple[CfsResult, list[int]]:
    """シミュレーション本体。結果と、周期ごとに使った CPU 時間のリストを返す。"""
    _validate(bursts, quota, period, cpus)
    remaining = {b.name: b.work for b in bursts}
    received = {b.name: 0 for b in bursts}  # これまでに受け取った CPU 時間（公平性の基準）
    order = {b.name: i for i, b in enumerate(bursts)}
    finish: dict[str, int] = {}
    usage: list[int] = []
    nr_periods = nr_throttled = throttled_time = 0
    period_active = period_throttled = False
    runtime_left = 0
    t = 0
    while len(finish) < len(bursts):
        if t % period == 0:
            # 周期の境目: 前の周期を集計し、クォータを補充する
            nr_periods += period_active
            nr_throttled += period_throttled
            period_active = period_throttled = False
            runtime_left = quota if quota is not None else 0
            usage.append(0)
        runnable = [b for b in bursts if b.start <= t and remaining[b.name] > 0]
        if runnable:
            period_active = True
            want = min(len(runnable), cpus)  # CPU が足りる範囲で、同時に走りたい数
            if quota is None:
                slots = want
            else:
                slots = min(want, runtime_left)
                if slots < want:
                    period_throttled = True  # クォータ不足で走れないバーストが出た
                if runtime_left == 0:
                    throttled_time += 1  # グループ全体が止められている 1 ミリ秒
            # CFS のように、受け取った CPU 時間が少ないものを優先する（同点は開始時刻、入力の順）
            runnable.sort(key=lambda b: (received[b.name], b.start, order[b.name]))
            for b in runnable[:slots]:
                remaining[b.name] -= 1
                received[b.name] += 1
                usage[-1] += 1
                if quota is not None:
                    runtime_left -= 1
                if remaining[b.name] == 0:
                    finish[b.name] = t + 1
        t += 1
    # 最後の（途中までの）周期を集計する
    nr_periods += period_active
    nr_throttled += period_throttled
    return CfsResult(finish, nr_periods, nr_throttled, throttled_time), usage


# ---------------------------------------------------------------------------
# 演習2: CFS 帯域制御のシミュレーション
# ---------------------------------------------------------------------------

def simulate(bursts: Sequence[Burst], *, quota: int | None, period: int = 100, cpus: int = 4) -> CfsResult:
    return _run(bursts, quota, period, cpus)[0]


def latencies(bursts: Sequence[Burst], result: CfsResult) -> dict[str, int]:
    """各バーストの遅延（完了時刻 - 開始時刻）。"""
    return {b.name: result.finish[b.name] - b.start for b in bursts}


# ---------------------------------------------------------------------------
# 演習3: スロットリングを起こさない最小のクォータ
# ---------------------------------------------------------------------------

def min_quota_without_throttling(bursts: Sequence[Burst], *, period: int = 100, cpus: int = 4) -> int:
    if not bursts:
        raise ValueError("バーストがありません")
    # スロットリングが一度も起きないなら、スケジュールは「制限なし」のときと完全に同じになる。
    # したがって必要十分なクォータは、制限なしで動かしたときの「1 周期あたりの CPU 使用量の最大値」。
    # 平均の使用量ではなく、周期の中のピーク（並列度 × 時間）で決まるのが要点
    _, usage = _run(bursts, None, period, cpus)
    return max(usage)
