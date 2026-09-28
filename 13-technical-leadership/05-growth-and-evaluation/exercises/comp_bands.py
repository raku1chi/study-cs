"""13.5 育成・評価・キャリアラダー — 演習: 給与レンジ（バンド）の設計と昇給予算

等級ごとの給与レンジ（バンド）を設計し、個人の給与がレンジのどこにあるか
（コンパレシオ、レンジ内の位置）を計算し、メリットマトリクスによる昇給の予算を見積もります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 13.5          # この章の 2 つの演習（calibration, comp_bands）をテスト
    python3 tools/check.py -v 13.5

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_comp_bands

用語（本文の 5 節も参照）:
    - 中央値（midpoint）: レンジの真ん中。多くの場合、市場の水準を参考に決める
    - レンジの幅（range spread）: (上限 − 下限) ÷ 下限
    - 中央値の上昇率（midpoint progression）: 次の等級の中央値 ÷ この等級の中央値 − 1
    - コンパレシオ（compa-ratio）: 給与 ÷ 中央値
    - レンジ内の位置（range penetration）: (給与 − 下限) ÷ (上限 − 下限)

金額の単位は呼び出し側で統一してください（本文の例では「万円」）。
制約: 標準ライブラリのみを使ってください。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    """等級ごとの給与レンジ。minimum <= midpoint <= maximum。"""

    level: str
    minimum: float
    midpoint: float
    maximum: float


@dataclass(frozen=True)
class Employee:
    """社員。rating は評価の段階（メリットマトリクスのキー）。"""

    name: str
    level: str
    salary: float
    rating: str


@dataclass(frozen=True)
class Adjustment:
    """昇給の結果。

    merit     : メリットマトリクスによる昇給額（= old_salary × 昇給率）
    catch_up  : 昇給後もレンジの下限に届かない場合の、下限までの引き上げ額
    lump_sum  : 昇給後にレンジの上限を超える分を、基本給に入れず一時金として払う額
    new_salary: 新しい基本給
    """

    name: str
    old_salary: float
    merit: float
    catch_up: float
    lump_sum: float
    new_salary: float


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: バンドの設計
# ---------------------------------------------------------------------------

def build_bands(
    base_midpoint: float,
    levels: list[str],
    progression: float | list[float],
    spread: float | list[float],
) -> list[Band]:
    """等級ごとのバンドを作る。

    - 最初の等級の中央値は base_midpoint。
      以降は「前の等級の中央値 × (1 + progression)」
      progression はすべての等級間で共通の値か、等級間ごとの値のリスト（長さ = 等級数 − 1）
    - spread（レンジの幅）はすべての等級で共通の値か、等級ごとのリスト（長さ = 等級数）
    - 中央値が (下限 + 上限) / 2、レンジの幅が (上限 − 下限) / 下限 になるように:
        下限 = 2 × 中央値 / (2 + spread)、上限 = 下限 × (1 + spread)

    - base_midpoint が 0 以下、levels が空または重複あり、リストの長さが合わない、
      progression が 0 以下、spread が負 → ValueError

    >>> bands = build_bands(500, ["L1", "L2"], progression=0.2, spread=0.5)
    >>> [(b.level, round(b.minimum), round(b.midpoint), round(b.maximum)) for b in bands]
    [('L1', 400, 500, 600), ('L2', 480, 600, 720)]
    """
    raise NotImplementedError("演習3: build_bands を実装してください")


def band_overlap(lower: Band, upper: Band) -> float:
    """下位の等級のバンドのうち、上位の等級のバンドと重なっている割合を返す。

    重なり = max(0, 下位の上限 − 上位の下限) ÷ (下位の上限 − 下位の下限)
    （重なりの定義は組織によって異なる。ここでは下位のレンジの幅を分母にする）

    - 下位のバンドの幅が 0 以下 → ValueError

    >>> band_overlap(Band("L1", 400, 500, 600), Band("L2", 480, 600, 720))
    0.6
    """
    raise NotImplementedError("演習3: band_overlap を実装してください")


# ---------------------------------------------------------------------------
# 演習3（続き）: 個人の位置づけ
# ---------------------------------------------------------------------------

def compa_ratio(salary: float, band: Band) -> float:
    """コンパレシオ（給与 ÷ 中央値）を返す。

    >>> compa_ratio(540, Band("L2", 480, 600, 720))
    0.9
    """
    raise NotImplementedError("演習3: compa_ratio を実装してください")


def range_penetration(salary: float, band: Band) -> float:
    """レンジ内の位置 (給与 − 下限) ÷ (上限 − 下限) を返す。レンジ外なら 0 未満または 1 超になる。

    - バンドの幅が 0 以下 → ValueError

    >>> range_penetration(540, Band("L2", 480, 600, 720))
    0.25
    """
    raise NotImplementedError("演習3: range_penetration を実装してください")


def out_of_band(employees: list[Employee], bands: list[Band]) -> list[tuple[str, str, float]]:
    """レンジの外にいる社員を (名前, "below" または "above", 下限・上限との差額) で返す。

    - 入力の社員の順に並べる。下限ちょうど・上限ちょうどはレンジ内とみなす
    - 社員の等級のバンドがない → ValueError

    >>> bands = [Band("L2", 480, 600, 720)]
    >>> out_of_band([Employee("A", "L2", 450, "B"), Employee("B", "L2", 600, "B")], bands)
    [('A', 'below', 30)]
    """
    raise NotImplementedError("演習3: out_of_band を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: メリットマトリクスによる昇給と予算
# ---------------------------------------------------------------------------

def merit_adjustments(
    employees: list[Employee],
    bands: list[Band],
    matrix: dict[str, list[float]],
    zone_edges: list[float] | None = None,
) -> list[Adjustment]:
    """メリットマトリクス（評価 × レンジ内のゾーン → 昇給率）で昇給を計算する。

    1. 現在のコンパレシオでゾーンを決める。zone_edges（既定は [0.9, 1.1]）に対して
       0.9 未満 → ゾーン 0、0.9 以上 1.1 未満 → ゾーン 1、1.1 以上 → ゾーン 2
       （一般に、edges の値以上になるたびにゾーンが 1 つ上がる）
    2. 昇給額 merit = 給与 × matrix[評価][ゾーン]、仮の新給与 = 給与 + merit
    3. 仮の新給与がレンジの下限未満なら、下限まで引き上げる（catch_up = 下限 − 仮の新給与）
    4. 仮の新給与が「上限と現在の給与の大きい方」を超えるなら、基本給はその値で止め、
       超えた分を一時金にする（すでに上限を超えている人の基本給は下げない）
    5. 入力の社員の順に Adjustment を返す

    - 社員の等級のバンドがない、評価がマトリクスにない、昇給率の個数がゾーン数と合わない、
      zone_edges が狭義の昇順でない → ValueError

    ヒント: 同じ評価でもレンジの中で低い位置にいる人の昇給率を高くするのは、
    市場の水準（中央値）との差を時間をかけて縮めるため。
    """
    raise NotImplementedError("演習4: merit_adjustments を実装してください")


def budget_summary(adjustments: list[Adjustment]) -> dict[str, float]:
    """昇給の予算を集計する。

    戻り値のキー:
        "payroll"      : 昇給前の給与の合計
        "base_increase": 基本給の増加の合計（新給与 − 旧給与 の合計。catch_up を含む）
        "lump_sum"     : 一時金の合計
        "total_cost"   : base_increase + lump_sum
        "increase_rate": base_increase ÷ payroll

    - 給与の合計が 0 以下 → ValueError
    """
    raise NotImplementedError("演習4: budget_summary を実装してください")
