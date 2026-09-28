"""13.5 育成・評価・キャリアラダー — 演習: 評価のキャリブレーション（評価者による偏りの検出）

評価会議（キャリブレーション）の前に、評価者（マネージャー）ごとの評価の偏りを
データで確認するツールを作ります。評価者ごとの統計、分布のずれ、寛大化・厳格化の検出、
そして「評価者ごとに標準化すると何が起きるか」を実装して確かめます。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.5          # この章の 2 つの演習（calibration, comp_bands）をテスト
    python3 tools/check.py -v 13.5       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_calibration

共通の約束:
    - 標準偏差は母標準偏差（偏差の 2 乗の平均の平方根。n で割る）を使う。
    - 同じ社員（employee）の評価が 2 件以上ある、または評価が 0 件 → ValueError。

制約:
    - 標準ライブラリのみを使ってください（statistics モジュールは使ってかまいません）。
"""
from __future__ import annotations

import math  # noqa: F401  演習2で使います
from dataclasses import dataclass


@dataclass(frozen=True)
class Rating:
    """1 人の社員に対する評価。score は評価の段階（例: 1〜5）。"""

    employee: str
    manager: str
    score: float


@dataclass(frozen=True)
class ManagerStats:
    """評価者ごとの統計。n: 評価した人数、mean: 平均、sd: 母標準偏差。"""

    n: int
    mean: float
    sd: float


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 評価者ごとの統計と分布の比較
# ---------------------------------------------------------------------------

def manager_stats(ratings: list[Rating]) -> dict[str, ManagerStats]:
    """評価者ごとの人数・平均・母標準偏差を返す（キーは評価者名の昇順）。

    >>> rs = [Rating("a", "M1", 4), Rating("b", "M1", 2), Rating("c", "M2", 3)]
    >>> manager_stats(rs)
    {'M1': ManagerStats(n=2, mean=3.0, sd=1.0), 'M2': ManagerStats(n=1, mean=3.0, sd=0.0)}
    """
    raise NotImplementedError("演習1: manager_stats を実装してください")


def distribution_distance(ratings: list[Rating], scale: list[float]) -> dict[str, float]:
    """評価者ごとに、自分の評価の分布と「他の評価者全員」の評価の分布の全変動距離を返す。

    全変動距離 = 0.5 × Σ_k |p(k) − q(k)|
        p(k): その評価者の評価のうち、段階 k の割合
        q(k): 他の評価者全員の評価のうち、段階 k の割合（その評価者自身は含めない）
    0 なら分布が同じ、1 なら 2 つの分布がまったく重ならない。キーは評価者名の昇順。

    - 評価者が 1 人しかいない → ValueError（比べる相手がいない）
    - scale にない評価がある → ValueError

    >>> rs = [Rating("a", "M1", 5), Rating("b", "M1", 5), Rating("c", "M2", 3), Rating("d", "M2", 5)]
    >>> distribution_distance(rs, scale=[1, 2, 3, 4, 5])
    {'M1': 0.5, 'M2': 0.5}
    """
    raise NotImplementedError("演習1: distribution_distance を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 寛大化・厳格化の検出
# ---------------------------------------------------------------------------

def leniency_flags(ratings: list[Rating], z_threshold: float = 2.0) -> dict[str, tuple[float, str]]:
    """評価者ごとに (z, 判定) を返す（キーは評価者名の昇順）。

    z は「その評価者の平均が、他の評価者全員の評価から無作為に同じ人数を選んだ場合の
    平均と比べて、標準誤差いくつ分ずれているか」を表す:
        z = (その評価者の平均 − 他の評価者全員の平均) / (他の評価者全員の母標準偏差 / √n)
        n はその評価者が評価した人数
    他の評価者全員の標準偏差が 0 のときは、平均の差が 0 なら z = 0.0、
    正なら +math.inf、負なら -math.inf とする。

    判定: z >= z_threshold なら "lenient"（寛大）、z <= -z_threshold なら "severe"（厳格）、
          それ以外は "ok"

    - 評価者が 1 人しかいない、z_threshold が 0 以下 → ValueError

    ヒント: 平均の差をそのまま比べず標準誤差で割るのは、評価した人数が少ない評価者の平均は
    偶然でも大きく揺れるから。同じ 0.5 の差でも、3 人と 30 人では意味が違う。
    """
    raise NotImplementedError("演習2: leniency_flags を実装してください")


# ---------------------------------------------------------------------------
# 演習2（続き）: 評価者ごとの標準化と、その影響
# ---------------------------------------------------------------------------

def normalize_within_manager(ratings: list[Rating]) -> dict[str, float]:
    """評価者ごとに z スコアへ標準化し、全体の尺度に戻した値を社員ごとに返す。

    標準化後の値 = 全体の平均 + z × 全体の母標準偏差
        z = (その人の評価 − その評価者の平均) / その評価者の母標準偏差
        その評価者の標準偏差が 0（全員同じ評価）のときは z = 0
    「全体」は全評価者の全評価。

    >>> rs = [Rating("a", "M1", 5), Rating("b", "M1", 3), Rating("c", "M2", 3), Rating("d", "M2", 1)]
    >>> {e: round(v, 3) for e, v in normalize_within_manager(rs).items()}
    {'a': 4.414, 'b': 1.586, 'c': 4.414, 'd': 1.586}

    （M1 は全体に比べて寛大、M2 は厳格だが、標準化すると両者の違いは消える）
    """
    raise NotImplementedError("演習2: normalize_within_manager を実装してください")


def rank_changes(ratings: list[Rating]) -> dict[str, tuple[int, int]]:
    """社員ごとに (元の評価での順位, 標準化後の順位) を返す（キーは社員名の昇順）。

    順位は 1 始まりで、値の大きい順。値が同じなら社員名の昇順で先の人を上位とする。
    標準化後の値は normalize_within_manager の結果を使う。

    >>> rs = [Rating("a", "M1", 5), Rating("b", "M1", 3), Rating("c", "M2", 3), Rating("d", "M2", 1)]
    >>> rank_changes(rs)
    {'a': (1, 1), 'b': (2, 3), 'c': (3, 2), 'd': (4, 4)}
    """
    raise NotImplementedError("演習2: rank_changes を実装してください")
