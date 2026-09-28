"""14.2 技術戦略の立て方 — 演習（tco.py）

Build（自社開発）/ Buy（製品・SaaS の購入）/ Partner（開発・運用の委託）の複数年の
TCO（総保有コスト）を、割引率を使った現在価値で比較し、どの入力が判断を左右するかを
トルネード型の感度分析で調べるツールを作ります。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.2          # 合格数を表示
    python3 tools/check.py -v 14.2       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_tco

モデルの前提（簡略化しています。本文 5 節を参照）:
    - 0 年目に一時費用（upfront）が発生し、1〜N 年目の年末に年次コストが発生する。
    - 人件費とライセンス料は「1 年目の水準」から毎年一定率で上昇する（複利）。
    - 撤退・乗り換え費用（exit_cost）は最終年（N 年目）に計上する。
    - 税・減価償却・インフレ（割引率に含める）・残存価値は考えない。
    - 金額の単位は任意（本文では万円）。
"""
from __future__ import annotations

import dataclasses  # noqa: F401  演習3で dataclasses.replace が使えます
from dataclasses import dataclass
from typing import Mapping, Sequence

# 感度分析で動かせる Option のフィールド（name 以外の数値フィールド）
NUMERIC_FIELDS = (
    "upfront",
    "fte",
    "cost_per_fte",
    "wage_growth",
    "license",
    "license_escalator",
    "infra",
    "other",
    "exit_cost",
)


@dataclass(frozen=True)
class Option:
    """1 つの選択肢のコスト構造。金額の単位は任意（本文では万円）。"""

    name: str
    upfront: float = 0.0            # 0 年目の一時費用（開発・導入・データ移行）
    fte: float = 0.0                # 1 年目以降に必要な社内人員（人年/年）
    cost_per_fte: float = 0.0       # 1 人年あたりのフルロードコスト（1 年目の水準）
    wage_growth: float = 0.0        # 人件費の年上昇率（例: 0.03 = 3%）
    license: float = 0.0            # 1 年目のライセンス料・利用料・委託費
    license_escalator: float = 0.0  # ライセンス料等の年上昇率（値上げ・従量増）
    infra: float = 0.0              # 年間インフラ費（一定）
    other: float = 0.0              # その他の年間費用（一定）
    exit_cost: float = 0.0          # 最終年に計上する撤退・乗り換え費用（ロックインの大きさ）


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 現在価値と年次コスト
# ---------------------------------------------------------------------------

def present_value(amount: float, rate: float, year: int) -> float:
    """year 年後の金額 amount を、割引率 rate で現在価値に割り引く。

    現在価値 = amount / (1 + rate) ** year

    - rate <= -1 のときは ValueError（(1 + rate) が 0 以下になり意味をなさない）。
    - year < 0 のときは ValueError。

    >>> present_value(125.0, 0.25, 1)
    100.0
    >>> present_value(100.0, 0.10, 0)
    100.0
    >>> round(present_value(110.0, 0.10, 1), 6)   # 浮動小数点の誤差があるので丸めて比較
    100.0
    """
    raise NotImplementedError("演習1: present_value を実装してください")


def annual_costs(option: Option, years: int) -> list[float]:
    """option の 0〜years 年目のコストを、長さ years + 1 のリストで返す。

    - 0 年目: upfront
    - t 年目（1 <= t <= years）:
        fte × cost_per_fte × (1 + wage_growth) ** (t - 1)
        + license × (1 + license_escalator) ** (t - 1)
        + infra + other
      さらに t == years（最終年）なら exit_cost を加える。
    - years < 1 のときは ValueError。

    >>> annual_costs(Option("x", upfront=100, license=10, license_escalator=0.5, exit_cost=7), 2)
    [100, 10.0, 22.0]

    ヒント: 上昇率は「1 年目の水準」から効くので、t 年目の指数は t - 1。
    """
    raise NotImplementedError("演習1: annual_costs を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: TCO の比較
# ---------------------------------------------------------------------------

def total_cost_of_ownership(option: Option, years: int, discount_rate: float) -> float:
    """annual_costs の各年のコストを現在価値に割り引いて合計した TCO を返す。

    TCO = Σ_{t=0..years} annual_costs(option, years)[t] / (1 + discount_rate) ** t

    discount_rate == 0 なら単純合計と一致する。
    """
    raise NotImplementedError("演習2: total_cost_of_ownership を実装してください")


def rank_options(
    options: Sequence[Option], years: int, discount_rate: float
) -> list[tuple[str, float]]:
    """各選択肢の (名前, TCO) を TCO の小さい順に並べて返す。

    - TCO が等しい場合は名前の辞書順に並べる（結果を決定的にするため）。
    - options が空、または名前が重複している場合は ValueError。
    """
    raise NotImplementedError("演習2: rank_options を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: トルネード型の感度分析と損益分岐点
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityRow:
    """1 つの入力を low / high に振ったときの結果（この型は完成しています）。"""

    parameter: str
    low: float
    high: float
    margin_low: float    # 他案の最小 TCO − 基準ケースの最良案の TCO（負なら判断が逆転）
    margin_high: float
    winner_low: str      # その入力値で最も TCO が小さい案
    winner_high: str

    @property
    def swing(self) -> float:
        """low と high でマージンがどれだけ動くか（トルネード図のバーの長さ）。"""
        return abs(self.margin_high - self.margin_low)

    @property
    def flips(self) -> bool:
        """low か high のどちらかで、基準ケースの最良案が最良でなくなるか。"""
        return min(self.margin_low, self.margin_high) < 0


def tornado(
    options: Sequence[Option],
    years: int,
    discount_rate: float,
    ranges: Mapping[str, tuple[float, float]],
) -> list[SensitivityRow]:
    """入力を 1 つずつ low / high に振り、判断がどれだけ揺れるかを調べる。

    手順:
    1. 基準ケース（引数そのまま）で TCO が最小の案を「基準の最良案」B とする。
    2. ranges の各項目 parameter: (low, high) について、その入力だけを low（次に high）に
       置き換え、他はすべて基準ケースのままで TCO を計算し直す。
       マージン = （B 以外の案の TCO の最小値）−（B の TCO）。
       マージンが負なら、その入力値では B よりも安い案がある（判断が逆転する）。
    3. SensitivityRow を swing（|margin_high − margin_low|）の大きい順に並べて返す。
       swing が同じなら parameter 名の辞書順。

    parameter の書き方:
    - "選択肢名.フィールド名"（例: "Build.fte", "Buy.license_escalator"）。
      フィールド名は NUMERIC_FIELDS のいずれか。
    - "discount_rate"（割引率そのもの）。

    エラー:
    - options が 2 つ未満なら ValueError。
    - parameter の書式が不正、存在しない選択肢名、NUMERIC_FIELDS にないフィールド名は ValueError。

    ヒント: Option は frozen な dataclass なので、dataclasses.replace(option, fte=2.0) で
    一部だけ値を変えたコピーを作る。元の options を書き換えてはいけない。
    """
    raise NotImplementedError("演習3: tornado を実装してください")


def break_even(
    options: Sequence[Option],
    years: int,
    discount_rate: float,
    parameter: str,
    lo: float,
    hi: float,
    tol: float = 1e-9,
    max_iter: int = 200,
) -> float:
    """parameter を lo〜hi の範囲で動かしたとき、判断が逆転する境界の値を二分法で求める。

    - 「判断」は tornado と同じ: 基準ケースの最良案 B のマージン
      （B 以外の案の TCO の最小値 − B の TCO）が 0 になる parameter の値を返す。
    - lo と hi でマージンの符号が同じ（範囲内で逆転しない）なら ValueError。
      どちらかでちょうど 0 ならその端の値を返してよい。
    - 区間の幅の半分が tol 未満になるか、max_iter 回繰り返したら打ち切る。
    - parameter の書式とエラーは tornado と同じ。

    例: 「Buy のライセンス料の年上昇率が何 % を超えたら Buy は最良でなくなるか」
        break_even(options, 5, 0.08, "Buy.license_escalator", 0.0, 0.5)

    ヒント: マージンは入力に対して連続なので、符号が変わる区間を半分ずつ狭めればよい。
    """
    raise NotImplementedError("演習3: break_even を実装してください")
