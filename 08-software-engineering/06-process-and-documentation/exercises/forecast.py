"""8.6 開発プロセスとドキュメンテーション — 演習1: モンテカルロ法による完了日の予測

「この 40 件のバックログは、いつ終わりますか？」という問いに、1 つの日付ではなく、
確率つきの範囲で答えるための道具を作ります。材料は、チームが過去に 1 週間あたりに
完了させた項目の数（スループット）の記録だけです。見積もりの会議は必要ありません。

    過去 10 週間のスループット: [3, 5, 2, 6, 4, 4, 0, 5, 3, 6]
    → 「50% の確率で 11 月 2 日までに、85% の確率で 11 月 16 日までに終わる」

考え方: 過去の 1 週間を無作為に選んで（復元抽出）未来の 1 週間に見立て、バックログが
尽きるまで繰り返す。これを何千回も試行すると、「何週間かかるか」の分布が得られる。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.6

乱数: random.Random(seed) を 1 つ作り、各試行の各週で rng.choice(history) を 1 回呼ぶこと。
      （同じ seed なら同じ結果になるように。グローバルな random は使わない）
"""
from __future__ import annotations

import random  # noqa: F401  実装で使います
from datetime import date, timedelta  # noqa: F401  実装で使います
from typing import Sequence


def percentile(values: Sequence[float], p: float) -> float:
    """最近傍順位法の p パーセンタイル（0 < p <= 100）。昇順に並べた ceil(p/100 × n) 番目の値。

    values が空、または p が範囲外なら ValueError。（8.4 の演習と同じ定義）
    """
    raise NotImplementedError("演習1: percentile を実装してください")


def simulate_weeks(
    history: Sequence[int], backlog: int, *, runs: int = 10_000, seed: int = 0, max_weeks: int = 520
) -> list[int]:
    """「backlog 件を終えるのに何週間かかるか」を runs 回シミュレーションし、各試行の週数のリストを返す。

    - 各試行: 完了数 0 から始め、完了数が backlog 以上になるまで、1 週間ごとに rng.choice(history)
      件を足していく。かかった週数を記録する（backlog が 0 なら 0 週）。
    - history が空、負の値を含む、backlog や runs が負（runs は 1 以上）なら ValueError。
    - backlog > 0 なのに history がすべて 0（決して終わらない）なら ValueError。
    - 1 つの試行が max_weeks 週を超えても終わらなければ ValueError（現実的でない予測を止める）。
    """
    raise NotImplementedError("演習1: simulate_weeks を実装してください")


def forecast_completion(
    history: Sequence[int],
    backlog: int,
    start: date,
    *,
    runs: int = 10_000,
    seed: int = 0,
    confidences: Sequence[int] = (50, 85, 95),
) -> dict[int, date]:
    """「c% の確率で、この日までに終わる」日付を、信頼度 c ごとに返す。

    週数の分布の c パーセンタイル w について、start + w 週（7 × w 日）の日付。
    例: {50: date(2026, 11, 2), 85: date(2026, 11, 16), 95: date(2026, 11, 23)}
    """
    raise NotImplementedError("演習1: forecast_completion を実装してください")


def forecast_items(
    history: Sequence[int],
    weeks: int,
    *,
    runs: int = 10_000,
    seed: int = 0,
    confidences: Sequence[int] = (50, 85, 95),
) -> dict[int, int]:
    """「c% の確率で、weeks 週間のうちに少なくとも何件終わるか」を、信頼度 c ごとに返す。

    - 各試行で rng.choice(history) を weeks 回引いて合計する（runs 回）。
    - 「c% の確率で少なくとも X 件」なので、合計の分布の **下側** を見る:
      X = (100 - c) パーセンタイル。ただし c == 100 のときは最小値。
      （高い信頼度ほど、少ない件数になる。85% の約束は 50% の約束より控えめ）
    - weeks が負なら ValueError。weeks == 0 なら、どの信頼度でも 0 件。history の検証は simulate_weeks と同じ。
    """
    raise NotImplementedError("演習1: forecast_items を実装してください")
