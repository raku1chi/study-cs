"""8.6 開発プロセスとドキュメンテーション — 演習2: カンバンのシミュレーター

「WIP（仕掛かり中の作業）を制限すると、なぜリードタイムが短くなるのか」を、
1 日単位の離散時間シミュレーションで確かめます。さらに、リトルの法則
（平均 WIP = スループット × 平均リードタイム）が成り立つことを、自分の手で検証します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.6

モデル:
    - ボードは工程（Stage）の列。例: 分析 → 開発 → テスト。
    - 各工程には作業者が workers 人いて、1 人が 1 日に 1 単位の作業を、1 つの項目に対して行う。
    - 各工程の WIP の上限（wip_limit）は、その工程にいる項目（作業中 ＋ 作業が終わって次の工程を
      待っているもの）の数の上限。None なら無制限。
    - 項目（Item）は arrival_day にバックログ（ボードの外の待ち行列）に入り、最初の工程に入った日が
      開始日（コミットメントポイント）、最後の工程を出た日が完了日。リードタイム = 完了日 − 開始日。
      バックログで待っている項目は WIP に数えない。

1 日（day = 0, 1, 2, …）の処理の順序（この順序は仕様の一部です）:
    1. 到着: arrival_day == day の項目を、items で与えられた順にバックログの末尾に入れる。
    2. 引き取り（下流の工程から順に）: 最後の工程から最初の工程へ向かって、各工程の項目を、
       その工程に入った順に見ていく。その工程の作業が残っていない項目は、
         - 最後の工程なら完了（完了日 = day）としてボードから取り除く。
         - そうでなければ、次の工程に空きがあれば（上限がないか、項目数 < 上限）次の工程の末尾へ移し、
           残りの作業量を work[次の工程] にする。空きがなければその工程に留まる。
       下流から処理するので、同じ日のうちに、下流に移った分の空きを上流が使える（引き取り型）。
    3. 開始: 最初の工程に空きがある間、バックログの先頭の項目を最初の工程の末尾へ入れる（開始日 = day）。
    4. 作業: 各工程で、その工程に入った順に、作業が残っている項目を最大 workers 個まで選び、
       それぞれの残りの作業量を 1 減らす。
    5. 記録: この時点でボードにいる項目の数（全工程の合計）を wip_by_day に追加する。

終了の条件:
    - days を指定したら、day = 0 〜 days - 1 の days 日分だけ実行する。
    - until_empty=True なら、すべての項目が完了するまで実行する（最後の項目が完了した日を含む）。
    - days と until_empty は、どちらか一方だけを指定する（両方・どちらもなしは ValueError）。

結果の指標:
    throughput        = 完了した項目の数 / 実行した日数
    average_wip       = wip_by_day の平均
    average_lead_time = 完了した項目のリードタイムの平均（完了が 0 件なら 0.0）
    until_empty で実行すると、ボードが空から始まり空で終わるので、リトルの法則
    average_wip == throughput × average_lead_time が（浮動小数点の誤差を除いて）厳密に成り立つ。
    なぜ厳密に成り立つのかは、README の「リトルの法則」を読んでから考えてみよう。
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class Stage:
    name: str
    workers: int  # 1 以上
    wip_limit: Optional[int] = None  # None なら無制限。指定するなら 1 以上


@dataclass(frozen=True)
class Item:
    id: str
    arrival_day: int  # 0 以上
    work: tuple[int, ...]  # 工程ごとの作業量（人日）。長さは工程の数、各要素は 1 以上


@dataclass(frozen=True)
class Completed:
    id: str
    start_day: int
    finish_day: int

    @property
    def lead_time(self) -> int:
        return self.finish_day - self.start_day


@dataclass(frozen=True)
class SimulationResult:
    days: int
    completed: tuple[Completed, ...]  # 完了した順（同じ日なら、ボードから取り除いた順）
    wip_by_day: tuple[int, ...]
    throughput: float
    average_wip: float
    average_lead_time: float


def generate_items(
    n: int, work_ranges: Sequence[tuple[int, int]], *, arrivals_per_day: int = 1, seed: int = 0
) -> list[Item]:
    """実験用の項目を作る補助関数（この関数は完成しています）。

    各工程の作業量を work_ranges[i] = (最小, 最大) から一様に選び、1 日に arrivals_per_day 件ずつ到着させる。
    """
    rng = random.Random(seed)
    return [
        Item(f"item-{i:04d}", i // arrivals_per_day, tuple(rng.randint(lo, hi) for lo, hi in work_ranges))
        for i in range(n)
    ]


def simulate(
    stages: Sequence[Stage],
    items: Sequence[Item],
    *,
    days: Optional[int] = None,
    until_empty: bool = False,
) -> SimulationResult:
    """カンバンのボードを 1 日ずつシミュレーションする（仕様はモジュールの docstring）。

    検証（ValueError）: 工程が空、workers < 1、wip_limit が 1 未満、項目の work の長さが工程の数と違う、
    work に 1 未満の値、arrival_day が負、id の重複、days と until_empty の指定の誤り、days < 1。

    ヒント: 工程ごとに「その工程に入った順の、(項目, 残りの作業量) のリスト」を持つとよい。
    """
    raise NotImplementedError("演習2: simulate を実装してください")
