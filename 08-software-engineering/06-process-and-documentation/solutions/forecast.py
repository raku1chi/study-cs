"""8.6 開発プロセスとドキュメンテーション — 解答例: モンテカルロ法による完了日の予測

仕様は exercises/forecast.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta
from typing import Sequence


def percentile(values: Sequence[float], p: float) -> float:
    if not values:
        raise ValueError("値が 1 つもありません")
    if not 0 < p <= 100:
        raise ValueError(f"p は 0 より大きく 100 以下にしてください: {p}")
    ordered = sorted(values)
    return ordered[math.ceil(p / 100 * len(ordered)) - 1]


def _validate_history(history: Sequence[int]) -> None:
    if not history:
        raise ValueError("過去のスループットが空です")
    if any(x < 0 for x in history):
        raise ValueError("スループットに負の値があります")


def simulate_weeks(
    history: Sequence[int], backlog: int, *, runs: int = 10_000, seed: int = 0, max_weeks: int = 520
) -> list[int]:
    _validate_history(history)
    if backlog < 0 or runs < 1:
        raise ValueError(f"backlog は 0 以上、runs は 1 以上にしてください: {backlog}, {runs}")
    if backlog > 0 and not any(history):
        raise ValueError("過去のスループットがすべて 0 なので、終わる日を予測できません")
    rng = random.Random(seed)
    results = []
    for _ in range(runs):
        done = weeks = 0
        while done < backlog:
            done += rng.choice(history)  # 過去の 1 週間を、未来の 1 週間に見立てる（復元抽出）
            weeks += 1
            if weeks > max_weeks:
                raise ValueError(f"{max_weeks} 週を超えても終わらない試行があります")
        results.append(weeks)
    return results


def forecast_completion(
    history: Sequence[int],
    backlog: int,
    start: date,
    *,
    runs: int = 10_000,
    seed: int = 0,
    confidences: Sequence[int] = (50, 85, 95),
) -> dict[int, date]:
    weeks = simulate_weeks(history, backlog, runs=runs, seed=seed)
    return {c: start + timedelta(weeks=int(percentile(weeks, c))) for c in confidences}


def forecast_items(
    history: Sequence[int],
    weeks: int,
    *,
    runs: int = 10_000,
    seed: int = 0,
    confidences: Sequence[int] = (50, 85, 95),
) -> dict[int, int]:
    _validate_history(history)
    if weeks < 0 or runs < 1:
        raise ValueError(f"weeks は 0 以上、runs は 1 以上にしてください: {weeks}, {runs}")
    rng = random.Random(seed)
    totals = [sum(rng.choice(history) for _ in range(weeks)) for _ in range(runs)]
    # 「c% の確率で少なくとも X 件」→ 分布の下側（100 - c パーセンタイル）を見る
    return {c: min(totals) if c >= 100 else int(percentile(totals, 100 - c)) for c in confidences}
