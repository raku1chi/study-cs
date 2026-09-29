"""13.4 採用 — 演習: 採用ファネルの計算

採用計画を「数字」で立てるための小さな計算ツールを作ります。
目標の採用数から逆算した必要な母集団、充足までの期間、面接官の負荷、採用単価を計算します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.4          # 合格数を表示
    python3 tools/check.py -v 13.4       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

モデルの前提（簡略化しています）:
    - 各段階の通過率は、その段階に入った候補者のうち次の段階に進む割合。
      最後の段階（オファー）の通過率は、オファーの承諾率を表す。
    - 金額の単位は呼び出し側で統一する（本文の例では「万円」）。

制約:
    - 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

import math  # noqa: F401  演習1・4で使います
from dataclasses import dataclass

EPS = 1e-9  # 浮動小数点の誤差の許容幅


@dataclass(frozen=True)
class Stage:
    """選考の 1 段階。

    name           : 段階の名前（例: "技術面接"）。段階どうしで重複しないこと
    pass_rate      : 通過率（0 < pass_rate <= 1）
    duration_days  : 候補者がこの段階に入ってから次の段階に入るまでの平均日数（0 以上）
    interview_hours: この段階で候補者 1 人あたりに面接官が使う時間の合計
                     （準備・評価の記入・すり合わせを含む。0 以上）
    """

    name: str
    pass_rate: float
    duration_days: float = 0.0
    interview_hours: float = 0.0


@dataclass(frozen=True)
class Channel:
    """採用チャネル（候補者の獲得経路）。

    name        : チャネル名（例: "リファラル"）。"合計" は使えない
    share       : 採用数に占めるこのチャネルの割合（全チャネルの合計が 1）
    fee_rate    : 1 人採用するごとに払う手数料の、年収に対する割合（人材紹介なら 0.35 など）
    fee_per_hire: 1 人採用するごとに払う定額（リファラルの紹介ボーナスなど）
    fixed_cost  : 採用数によらず、その期間に払う固定費（スカウト媒体の年間利用料など）
    """

    name: str
    share: float
    fee_rate: float = 0.0
    fee_per_hire: float = 0.0
    fixed_cost: float = 0.0


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 必要な母集団
# ---------------------------------------------------------------------------

def required_pipeline(target_hires: int, stages: list[Stage]) -> list[int]:
    """目標の採用数を達成するために、各段階に入る必要がある候補者数を返す。

    最後の段階から逆算する:
        最後の段階に入る必要がある人数 = ceil(target_hires / 最後の段階の通過率)
        その 1 つ前の段階に入る必要がある人数 = ceil(上の人数 / その段階の通過率)
        ……を先頭の段階まで繰り返す。
    人数は整数なので、各段階で切り上げる。ただし 3 / 0.3 = 10.000000000000002 のような
    浮動小数点の誤差で 11 にならないよう、割り算の結果から EPS を引いてから切り上げること。

    - target_hires が 1 未満 → ValueError
    - stages が空、段階の名前が重複、通過率が (0, 1] の範囲外、日数・時間が負 → ValueError

    >>> stages = [Stage("書類選考", 0.3), Stage("面接", 0.4), Stage("オファー", 0.7)]
    >>> required_pipeline(5, stages)
    [67, 20, 8]
    """
    raise NotImplementedError("演習1: required_pipeline を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 充足までの期間
# ---------------------------------------------------------------------------

def expected_time_to_fill(target_hires: int, stages: list[Stage], weekly_applicants: float) -> float:
    """目標の人数を採用し終えるまでの日数の目安を返す（簡略化したモデル）。

    日数 = 必要な応募者（先頭の段階に入る人数）がそろうまでの日数
           + 全段階の duration_days の合計（最後の応募者が選考を通過するまでの日数）
    応募者は毎週 weekly_applicants 人のペースで一定に集まるものとする（1 週 = 7 日）。

    - weekly_applicants が 0 以下 → ValueError
    - 段階の検証は required_pipeline と同じ

    >>> stages = [Stage("書類選考", 0.5, duration_days=3), Stage("オファー", 0.5, duration_days=7)]
    >>> expected_time_to_fill(2, stages, weekly_applicants=4)
    24.0
    """
    raise NotImplementedError("演習2: expected_time_to_fill を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 面接官の負荷
# ---------------------------------------------------------------------------

def interviewer_load(
    target_hires: int, stages: list[Stage], weeks: float, interviewers: dict[str, int]
) -> dict[str, float]:
    """段階ごとの「面接官 1 人あたりの週の負荷（時間）」を返す（キーは段階の名前で、stages の順）。

    負荷 = その段階に入る候補者数 × interview_hours ÷ weeks ÷ その段階を担当する面接官の人数
    （候補者数は required_pipeline の結果。面接は担当者で均等に分担できると仮定）

    - interview_hours が 0 の段階は結果に含めない
    - interview_hours が正の段階について、interviewers に名前がない、または人数が 1 未満 → ValueError
    - weeks が 0 以下 → ValueError

    >>> stages = [Stage("書類選考", 0.5, interview_hours=0.5), Stage("面接", 0.5, interview_hours=2)]
    >>> interviewer_load(2, stages, weeks=4, interviewers={"書類選考": 1, "面接": 2})
    {'書類選考': 1.0, '面接': 1.0}
    """
    raise NotImplementedError("演習3: interviewer_load を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 採用単価
# ---------------------------------------------------------------------------

def cost_per_hire(
    channels: list[Channel], hires: int, annual_salary: float, internal_cost: float = 0.0
) -> dict[str, float]:
    """チャネルごとの採用単価と、全体の採用単価を返す。

    - チャネルの採用数 = hires × share（小数になってもよい。期待値として扱う）
    - チャネルの 1 人あたりの変動費 = fee_rate × annual_salary + fee_per_hire
    - チャネルの採用単価 = 変動費 + fixed_cost ÷ チャネルの採用数
        チャネルの採用数が 0 のとき: fixed_cost > 0 なら math.inf（払っているのに採れていない）、
        そうでなければ変動費
    - "合計" = (全チャネルの費用の合計 + internal_cost) ÷ hires
        チャネルの費用 = 変動費 × チャネルの採用数 + fixed_cost
        internal_cost は面接官の人件費や採用担当者の費用など、社内でかかる費用の合計

    戻り値: {チャネル名: 採用単価, ..., "合計": 全体の採用単価}（チャネルは入力の順）

    - hires が 1 未満、annual_salary や internal_cost が負、チャネルが空、
      チャネルの数値に負の値がある、share の合計が 1 から EPS より大きくずれる、
      チャネル名に "合計" がある → ValueError

    >>> chs = [Channel("紹介", 0.5, fee_rate=0.3), Channel("リファラル", 0.5, fee_per_hire=20)]
    >>> cost_per_hire(chs, hires=4, annual_salary=1000, internal_cost=40)
    {'紹介': 300.0, 'リファラル': 20.0, '合計': 170.0}
    """
    raise NotImplementedError("演習4: cost_per_hire を実装してください")
