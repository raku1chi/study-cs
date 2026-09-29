"""14.4 経営陣・取締役会・投資家とのコミュニケーション — 演習（kpi_report.py）

指標ごとの実績・目標・向き・黄の幅から信号（赤・黄・緑）と傾向を判定し、
「例外（赤・黄）を先に」並べた 1 ページの経営向けサマリーを Markdown で出力するツールを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.4          # 合格数を表示
    python3 tools/check.py -v 14.4       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_kpi_report

設計の考え方（本文 3.4 節）:
    - 信号の基準（目標と黄の幅）は、報告の前に指標ごとに決めておく。
      報告のたびに基準を変えると、信号は意味を失う。
    - 色だけに頼らず、「赤」「黄」「緑」の文字で状態を表す（色覚の多様性への配慮、白黒印刷）。
    - 読み手の時間は限られているので、例外（赤・黄）を先に、全体の一覧を後に置く。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

STATUS_LABEL = {"red": "赤", "amber": "黄", "green": "緑"}
TREND_LABEL = {"improving": "改善", "worsening": "悪化", "flat": "横ばい", "n/a": "—"}


@dataclass(frozen=True)
class Metric:
    """1 つの指標（この型は完成しています）。"""

    name: str
    value: float                     # 実績
    target: float                    # 目標
    higher_is_better: bool = True    # True: 大きいほど良い（達成率など）/ False: 小さいほど良い（障害件数など）
    amber_band: float = 0.0          # 目標からこの幅までの未達は「黄」（指標の単位で。0 なら未達はすべて赤）
    previous: float | None = None    # 前期の値（なければ None）
    unit: str = ""                   # 表示用の単位（"%", "件" など）
    category: str = ""               # 区分（"デリバリー", "信頼性" など）
    noise: float = 0.0               # 前期からの変化がこの幅以内なら「横ばい」（指標の単位で）


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 信号と傾向の判定
# ---------------------------------------------------------------------------

def rag_status(metric: Metric) -> str:
    """指標の信号を "green" / "amber" / "red" で返す。

    大きいほど良い指標（higher_is_better=True）:
        value >= target                       → "green"
        target - amber_band <= value < target → "amber"
        それ未満                               → "red"
    小さいほど良い指標（higher_is_better=False）:
        value <= target                       → "green"
        target < value <= target + amber_band → "amber"
        それより大きい                         → "red"

    - 境界ちょうど（value == target - amber_band など）は "amber"。
    - amber_band < 0 なら ValueError。

    >>> rag_status(Metric("達成率", 75, 80, amber_band=5))
    'amber'
    >>> rag_status(Metric("障害件数", 4, 2, higher_is_better=False, amber_band=1))
    'red'
    """
    raise NotImplementedError("演習1: rag_status を実装してください")


def trend(metric: Metric) -> str:
    """前期からの傾向を "improving" / "worsening" / "flat" / "n/a" で返す。

    - previous が None なら "n/a"。
    - |value − previous| <= noise なら "flat"。
    - それ以外は、指標の向きに照らして良くなったら "improving"、悪くなったら "worsening"。
      （小さいほど良い指標では、値が減ったら "improving"）
    - noise < 0 なら ValueError。

    >>> trend(Metric("障害件数", 3, 2, higher_is_better=False, previous=5))
    'improving'
    """
    raise NotImplementedError("演習1: trend を実装してください")


def overall_status(metrics: Sequence[Metric]) -> str:
    """全体の信号を返す。1 つでも "red" があれば "red"、なければ 1 つでも "amber" があれば
    "amber"、すべて "green" なら "green"。metrics が空なら ValueError。"""
    raise NotImplementedError("演習1: overall_status を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 1 ページのサマリーを出力する
# ---------------------------------------------------------------------------

def format_value(value: float, unit: str = "") -> str:
    """数値を表示用の文字列にする。

    - 整数値なら 3 桁区切りで小数点なし: 1234.0 → "1,234"
    - そうでなければ、3 桁区切りを付けて小数第 2 位までに丸め、末尾の 0 と小数点を取り除く:
      99.950 → "99.95"、13.5 → "13.5"、1234567.891 → "1,234,567.89"
    - 最後に unit をそのまま付ける: format_value(70, "%") → "70%"、format_value(-2.0, "件") → "-2件"

    >>> format_value(1234.0)
    '1,234'
    >>> format_value(99.95, "%")
    '99.95%'
    >>> format_value(1234567.891)
    '1,234,567.89'
    >>> format_value(0.125)   # 丸めは Python の書式指定（f"{x:,.2f}"）に従う
    '0.12'

    ヒント: f"{value:,.2f}" は 3 桁区切りと小数第 2 位までの丸めを同時に行う。
    """
    raise NotImplementedError("演習2: format_value を実装してください")


def render_report(title: str, period: str, metrics: Sequence[Metric]) -> str:
    """経営向けの 1 ページサマリーを Markdown で返す（末尾は改行 1 つ）。形式は次のとおり:

        # {title}（{period}）
        （空行）
        **総合: {赤/黄/緑}**（赤 {赤の数} / 黄 {黄の数} / 緑 {緑の数}）
        （空行）
        ## 要対応・要注意（赤・黄）
        （空行）
        | 状態 | 区分 | 指標 | 実績 | 目標 | 傾向 |
        |---|---|---|---|---|---|
        | 赤 | {category} | {name} | {実績} | {目標} | {傾向} |     ← 赤を先に、次に黄。
        ...                                                       同じ信号の中では入力の順
        （空行）
        ## 全指標
        （空行）
        | 区分 | 指標 | 状態 | 実績 | 目標 | 傾向 |
        |---|---|---|---|---|---|
        | {category} | {name} | {状態} | {実績} | {目標} | {傾向} |  ← 入力の順

    - 実績と目標は format_value(value, unit) で表示する。
    - 傾向は、"n/a" なら "—"、それ以外は「改善（前期 {format_value(previous, unit)}）」のように
      TREND_LABEL の文字と前期の値を表示する。
    - 赤・黄の指標が 1 つもなければ、「要対応・要注意」の表の代わりに
      「赤・黄の指標はありません。」という 1 行を置く。
    - metrics が空なら ValueError。

    出力例は本文 3.4 節（または solutions/kpi_report.py を実行）を参照。
    """
    raise NotImplementedError("演習2: render_report を実装してください")
