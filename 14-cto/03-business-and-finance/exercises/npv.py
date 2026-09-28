"""14.3 事業と財務のリテラシー — 演習1（npv.py）

技術投資（例: クラウド費用を削減する移行プロジェクト）を、NPV（正味現在価値）・
IRR（内部収益率）・回収期間で評価する関数を作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.3          # この章の全演習（npv / saas_metrics / budget_model）
    python3 tools/check.py -v 14.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_npv

キャッシュフローの約束:
    cashflows[0] は「今」（t = 0）、cashflows[t] は t 期末のキャッシュフロー。
    投資（支出）は負、効果（収入・削減額）は正で表す。期は年でも月でもよい（割引率と揃える）。

制約（学びのための縛り）:
    - IRR は二分法で実装し、外部ライブラリ（numpy-financial など）は使わないこと。
"""
from __future__ import annotations

from typing import Sequence


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """割引率 rate でのキャッシュフローの正味現在価値（NPV）を返す。

    NPV = Σ_{t=0..n} cashflows[t] / (1 + rate) ** t

    - rate <= -1 のときは ValueError。
    - cashflows が空のときは ValueError。

    >>> npv(0.0, [-100, 60, 60])
    20.0
    >>> abs(npv(0.10, [-100, 110])) < 1e-9     # 浮動小数点の誤差があるので許容誤差で比べる
    True
    """
    raise NotImplementedError("演習1: npv を実装してください")


def irr(
    cashflows: Sequence[float],
    lo: float = -0.99,
    hi: float = 10.0,
    tol: float = 1e-10,
    max_iter: int = 500,
) -> float:
    """NPV が 0 になる割引率（IRR, 内部収益率）を二分法で求める。

    - cashflows が 2 期未満、または正と負のキャッシュフローが両方含まれない場合は ValueError。
    - npv(lo) と npv(hi) の符号が同じ（範囲内に根がない）場合は ValueError。
      どちらかがちょうど 0 ならその端の値を返してよい。
    - 区間の幅の半分が tol 未満になるか、max_iter 回繰り返したら、区間の中点を返す。

    >>> round(irr([-100, 110]), 6)
    0.1

    注意: 符号が何度も変わるキャッシュフロー（途中で大きな追加投資があるなど）では
    IRR が複数存在しうる。その場合、この関数は [lo, hi] 内の根の 1 つを返すだけである。

    ヒント: 通常の投資（最初に支出、後で収入）では、割引率を上げるほど NPV は小さくなる。
    npv(mid) の符号が npv(lo) と同じなら根は mid より右にある。
    """
    raise NotImplementedError("演習1: irr を実装してください")


def payback_period(cashflows: Sequence[float]) -> float | None:
    """累積キャッシュフローが初めて 0 以上になる時点（回収期間）を返す。

    - cashflows[0] >= 0 なら 0.0。
    - t 期（t >= 1）の途中で累積が 0 を超える場合、その期のキャッシュフローは期中に均等に
      入ると仮定して線形補間する: (t - 1) + (t - 1 期末までの不足額) / cashflows[t]
    - 最後まで回収できなければ None。
    - cashflows が空なら ValueError。

    >>> payback_period([-300, 100, 100, 100, 100])
    3.0
    >>> payback_period([-300, 120, 120, 120])
    2.5
    >>> payback_period([-300, 100]) is None
    True
    """
    raise NotImplementedError("演習1: payback_period を実装してください")


def discounted_payback_period(rate: float, cashflows: Sequence[float]) -> float | None:
    """各期のキャッシュフローを割引率 rate で現在価値に直してから、回収期間を求める。

    計算方法は payback_period と同じ（割り引いたキャッシュフローに対して適用する）。
    rate <= -1 のときは ValueError。割引するぶん、payback_period 以上の値になる（rate > 0 のとき）。
    """
    raise NotImplementedError("演習1: discounted_payback_period を実装してください")
