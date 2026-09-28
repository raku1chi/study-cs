"""11.1 セキュリティの基本原則と脅威モデリング — 演習（risk_register）

組織のリスク登録簿（リスクレジスター）を扱う小さなライブラリを作ります。
- 演習1: 定量的リスク評価（SLE・ALE と、対策の純便益）
- 演習2: 固有リスク（対策前）と残存リスク（対策後）
- 演習3: ヒートマップと、経営に報告するトップリスクの表

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.1
    python3 tools/check.py -v 11.1

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_risk_register

モデルの前提（教材用に単純化しています）:
    - 発生可能性（likelihood）と影響度（impact）は 1〜5 の 5 段階。スコア = 発生可能性 × 影響度。
    - 対策（Control）の effectiveness（0〜1）は「その対策で発生可能性が何割減るか」。
      現実には、バックアップのように「影響度を下げる」対策もありますが、ここでは扱いません。
    - 順序尺度（1〜5 の段階）を掛け算するのは数学的には乱暴です。README の
      「リスクで考える」で、この単純化の限界と使いどころを説明しています。
"""
from __future__ import annotations

import math  # noqa: F401  演習2で使えます（math.ceil など）
from dataclasses import dataclass


@dataclass(frozen=True)
class Control:
    """リスクに対する対策（管理策）。"""

    name: str
    effectiveness: float  # 0.0〜1.0


@dataclass(frozen=True)
class Risk:
    """リスク登録簿の 1 行。"""

    id: str
    title: str
    owner: str  # リスクオーナー（リスクの受容・対応を決める責任者）
    likelihood: int  # 1〜5
    impact: int  # 1〜5
    controls: tuple[Control, ...] = ()


@dataclass(frozen=True)
class Assessment:
    """1 件のリスクの評価結果。"""

    risk_id: str
    title: str
    owner: str
    inherent_score: int  # 固有リスクのスコア（対策前）
    residual_likelihood: int  # 対策後の発生可能性
    residual_score: int  # 残存リスクのスコア（対策後）
    level: str  # 残存スコアのレベル（risk_level）
    needs_treatment: bool  # 残存スコアがリスク許容水準（appetite）を超えているか


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 定量的リスク評価（ALE）
# ---------------------------------------------------------------------------

def single_loss_expectancy(asset_value: float, exposure_factor: float) -> float:
    """単一損失予想額 SLE = 資産価値 AV × 暴露係数 EF を返す。

    - exposure_factor は「1 回の事象で資産価値の何割を失うか」（0〜1）。範囲外は ValueError。
    - asset_value が負なら ValueError。

    >>> single_loss_expectancy(50_000_000, 0.4)
    20000000.0
    """
    raise NotImplementedError("演習1: single_loss_expectancy を実装してください")


def annualized_loss_expectancy(sle: float, aro: float) -> float:
    """年間予想損失額 ALE = SLE × 年間発生率 ARO を返す（どちらかが負なら ValueError）。

    ARO は「1 年に何回起きるか」の期待値。4 年に 1 回なら 0.25。
    """
    raise NotImplementedError("演習1: annualized_loss_expectancy を実装してください")


def control_net_benefit(ale_before: float, ale_after: float, annual_cost: float) -> float:
    """対策の年間の純便益 =（対策前の ALE − 対策後の ALE）− 対策の年間コスト を返す。

    正なら「コストに見合う」、負なら「この対策単体では割に合わない」ことを示す。
    """
    raise NotImplementedError("演習1: control_net_benefit を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 固有リスクと残存リスク
# ---------------------------------------------------------------------------

def combined_effectiveness(controls: tuple[Control, ...] | list[Control]) -> float:
    """複数の対策を重ねたときの合計の効果を返す。

    対策が互いに独立に働くと仮定すると、攻撃が「すべての対策をすり抜ける」確率は
    (1 − e1) × (1 − e2) × … なので、合計の効果は 1 − (1 − e1)(1 − e2)… になる。
    - 対策がなければ 0.0。
    - effectiveness が 0〜1 の範囲外の対策があれば ValueError。

    >>> combined_effectiveness((Control("MFA", 0.5), Control("パッチ", 0.4)))  # doctest: +SKIP
    0.7
    """
    raise NotImplementedError("演習2: combined_effectiveness を実装してください")


def inherent_score(risk: Risk) -> int:
    """固有リスクのスコア（likelihood × impact）を返す。

    likelihood・impact が 1〜5 の int でなければ ValueError（bool も不可）。
    """
    raise NotImplementedError("演習2: inherent_score を実装してください")


def residual_likelihood(risk: Risk) -> int:
    """対策後の発生可能性を返す。

    likelihood × (1 − combined_effectiveness(controls)) を **切り上げた** 整数（最小 1）。
    切り上げるのは、リスクを楽観的に見積もらないため（保守的な丸め）。

    注意: 浮動小数点の誤差に気をつけること。例えば効果 0.2 と 0.25 の対策を重ねた
    5 × (1 − 0.4) は数学的には 3 だが、素朴に計算すると 3.0000000000000004 になり、
    切り上げると 4 になってしまう。round(x, 9) してから切り上げるとよい。
    """
    raise NotImplementedError("演習2: residual_likelihood を実装してください")


def risk_level(score: int) -> str:
    """スコア（1〜25）をヒートマップのレベルに分類する。

    | スコア  | レベル |
    |---------|--------|
    | 1〜4    | "低"   |
    | 5〜9    | "中"   |
    | 10〜16  | "高"   |
    | 17〜25  | "重大" |

    1〜25 の int 以外は ValueError（bool も不可）。
    """
    raise NotImplementedError("演習2: risk_level を実装してください")


def assess(risk: Risk, appetite: int = 9) -> Assessment:
    """リスクを評価して Assessment を返す。

    - residual_score = residual_likelihood(risk) × risk.impact
    - level = risk_level(residual_score)
    - needs_treatment = residual_score > appetite
      （appetite はリスク許容水準。これを超える残存リスクは追加の対応が必要）
    """
    raise NotImplementedError("演習2: assess を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: ヒートマップとトップリスク報告
# ---------------------------------------------------------------------------

def heat_map(risks: list[Risk], residual: bool = True) -> dict[tuple[int, int], list[str]]:
    """(発生可能性, 影響度) のマスごとに、そこに入るリスク ID の昇順リストを返す。

    residual=True なら発生可能性に residual_likelihood を、False なら対策前の
    likelihood を使う。リスクが 1 件もないマスはキーを作らない。

    >>> heat_map([Risk("R-1", "t", "o", 3, 4)], residual=False)
    {(3, 4): ['R-1']}
    """
    raise NotImplementedError("演習3: heat_map を実装してください")


def top_risks(risks: list[Risk], n: int = 5, appetite: int = 9) -> list[Assessment]:
    """評価結果を「残存スコアの降順 → 固有スコアの降順 → ID の昇順」に並べ、先頭 n 件を返す。"""
    raise NotImplementedError("演習3: top_risks を実装してください")


def render_report(risks: list[Risk], n: int = 5, appetite: int = 9) -> str:
    """トップリスクを Markdown の表にして返す（経営会議の資料に貼る想定）。

    形式（各行の末尾に改行。最後の行にも改行を付ける）:
        | ID | リスク | オーナー | 固有 | 残存 | レベル | 対応 |
        |---|---|---|---|---|---|---|
        | R-01 | ランサムウェアで基幹業務が停止する | CIO | 20 | 10 | 高 | 要対応 |

    「対応」列は needs_treatment が True なら "要対応"、False なら "受容可"。
    """
    raise NotImplementedError("演習3: render_report を実装してください")
