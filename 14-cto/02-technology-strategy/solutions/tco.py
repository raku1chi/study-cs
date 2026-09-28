"""14.2 技術戦略の立て方 — 解答例（tco.py）

Build / Buy / Partner の複数年 TCO（総保有コスト）を、割引率を使った現在価値で比較し、
「どの入力が判断を左右するか」をトルネード型の感度分析で調べます。

演習の仕様は exercises/tco.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import dataclasses
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
    wage_growth: float = 0.0        # 人件費の年上昇率
    license: float = 0.0            # 1 年目のライセンス料・利用料・委託費
    license_escalator: float = 0.0  # ライセンス料等の年上昇率（値上げ・従量増）
    infra: float = 0.0              # 年間インフラ費（一定）
    other: float = 0.0              # その他の年間費用（一定）
    exit_cost: float = 0.0          # 最終年に計上する撤退・乗り換え費用（ロックインの大きさ）


# ---------------------------------------------------------------------------
# 演習1: 現在価値と年次コスト
# ---------------------------------------------------------------------------

def present_value(amount: float, rate: float, year: int) -> float:
    if rate <= -1:
        raise ValueError(f"割引率は -1 より大きくしてください: {rate}")
    if year < 0:
        raise ValueError(f"年は 0 以上です: {year}")
    # t 年後の金額は (1 + r)^t で割ると「今の価値」になる
    return amount / (1 + rate) ** year


def annual_costs(option: Option, years: int) -> list[float]:
    if years < 1:
        raise ValueError(f"期間は 1 年以上です: {years}")
    costs = [option.upfront]  # 0 年目は一時費用だけ
    for t in range(1, years + 1):
        # 上昇率は「1 年目の水準」から複利で効く。t 年目は (t - 1) 回上昇している
        people = option.fte * option.cost_per_fte * (1 + option.wage_growth) ** (t - 1)
        license_fee = option.license * (1 + option.license_escalator) ** (t - 1)
        cost = people + license_fee + option.infra + option.other
        if t == years:
            # 期間の終わりに乗り換える前提で、撤退コストを最終年に計上する
            cost += option.exit_cost
        costs.append(cost)
    return costs


# ---------------------------------------------------------------------------
# 演習2: TCO の比較
# ---------------------------------------------------------------------------

def total_cost_of_ownership(option: Option, years: int, discount_rate: float) -> float:
    return sum(
        present_value(cost, discount_rate, t)
        for t, cost in enumerate(annual_costs(option, years))
    )


def rank_options(
    options: Sequence[Option], years: int, discount_rate: float
) -> list[tuple[str, float]]:
    if not options:
        raise ValueError("選択肢が空です")
    names = [o.name for o in options]
    if len(set(names)) != len(names):
        raise ValueError(f"選択肢の名前が重複しています: {names}")
    scored = [(o.name, total_cost_of_ownership(o, years, discount_rate)) for o in options]
    # 同額のときは名前順にして、結果を決定的にする
    return sorted(scored, key=lambda item: (item[1], item[0]))


# ---------------------------------------------------------------------------
# 演習3: トルネード型の感度分析と損益分岐点
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SensitivityRow:
    """1 つの入力を low / high に振ったときの結果。"""

    parameter: str
    low: float
    high: float
    margin_low: float    # 他案の最小 TCO − 基準ケースの最良案の TCO（負なら判断が逆転）
    margin_high: float
    winner_low: str      # その入力値で最も TCO が小さい案
    winner_high: str

    @property
    def swing(self) -> float:
        return abs(self.margin_high - self.margin_low)

    @property
    def flips(self) -> bool:
        return min(self.margin_low, self.margin_high) < 0


def _apply(
    options: Sequence[Option], discount_rate: float, parameter: str, value: float
) -> tuple[list[Option], float]:
    """parameter を value に置き換えた (選択肢のリスト, 割引率) を返す。元の値は変更しない。"""
    if parameter == "discount_rate":
        return list(options), value
    name, sep, field = parameter.partition(".")
    if not sep or field not in NUMERIC_FIELDS:
        raise ValueError(f"不正なパラメータ名です: {parameter!r}（例: 'Build.fte', 'discount_rate'）")
    if name not in {o.name for o in options}:
        raise ValueError(f"選択肢 {name!r} がありません")
    # frozen な dataclass は dataclasses.replace で「一部だけ違うコピー」を作る
    replaced = [
        dataclasses.replace(o, **{field: value}) if o.name == name else o for o in options
    ]
    return replaced, discount_rate


def _margin(
    options: Sequence[Option], years: int, discount_rate: float, baseline_best: str
) -> tuple[float, str]:
    """(他案の最小 TCO − baseline_best の TCO, 現在の最良案) を返す。"""
    ranking = rank_options(options, years, discount_rate)
    costs = dict(ranking)
    best_other = min(cost for name, cost in ranking if name != baseline_best)
    return best_other - costs[baseline_best], ranking[0][0]


def tornado(
    options: Sequence[Option],
    years: int,
    discount_rate: float,
    ranges: Mapping[str, tuple[float, float]],
) -> list[SensitivityRow]:
    if len(options) < 2:
        raise ValueError("比較には 2 つ以上の選択肢が必要です")
    # 基準ケースの最良案を固定し、「その案の優位（マージン）」がどれだけ動くかを見る
    baseline_best = rank_options(options, years, discount_rate)[0][0]
    rows = []
    for parameter, (low, high) in ranges.items():
        opts_low, rate_low = _apply(options, discount_rate, parameter, low)
        opts_high, rate_high = _apply(options, discount_rate, parameter, high)
        margin_low, winner_low = _margin(opts_low, years, rate_low, baseline_best)
        margin_high, winner_high = _margin(opts_high, years, rate_high, baseline_best)
        rows.append(
            SensitivityRow(parameter, low, high, margin_low, margin_high, winner_low, winner_high)
        )
    # 影響の大きい順（トルネードの形）。同じ幅なら名前順
    rows.sort(key=lambda r: (-r.swing, r.parameter))
    return rows


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
    if len(options) < 2:
        raise ValueError("比較には 2 つ以上の選択肢が必要です")
    baseline_best = rank_options(options, years, discount_rate)[0][0]

    def margin_at(value: float) -> float:
        opts, rate = _apply(options, discount_rate, parameter, value)
        return _margin(opts, years, rate, baseline_best)[0]

    f_lo, f_hi = margin_at(lo), margin_at(hi)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError(f"{parameter} を {lo}〜{hi} で動かしても判断は逆転しません")
    # 二分法: 符号が変わる区間を半分ずつ狭めていく（14.3 の IRR と同じ考え方）
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        f_mid = margin_at(mid)
        if f_mid == 0 or abs(hi - lo) / 2 < tol:  # lo > hi で呼ばれても動くように abs
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2


def format_tornado(rows: Sequence[SensitivityRow], width: int = 30) -> str:
    """トルネード図を ASCII で描く（本文の出力例を作るための補助関数。演習の対象外）。"""
    if not rows:
        return ""
    scale = max(r.swing for r in rows) or 1.0
    lines = []
    for r in rows:
        bar = "#" * max(1, round(width * r.swing / scale))
        flag = "  <- 逆転あり" if r.flips else ""
        lines.append(
            f"{r.parameter:24s} {r.low:>8g} .. {r.high:<8g} {bar:<{width}s} "
            f"マージン {r.margin_low:>8.0f} .. {r.margin_high:<8.0f}{flag}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    # 本文 5.4 節の例: 請求・課金基盤の Build / Buy / Partner（単位: 万円、5 年、割引率 8%）
    build = Option("Build", upfront=5000, fte=1.5, cost_per_fte=1200, wage_growth=0.03,
                   infra=150, exit_cost=1000)
    buy = Option("Buy", upfront=1500, fte=0.5, cost_per_fte=1200, wage_growth=0.03,
                 license=1300, license_escalator=0.20, exit_cost=2500)
    partner = Option("Partner", upfront=3500, fte=0.5, cost_per_fte=1200, wage_growth=0.03,
                     license=1800, license_escalator=0.03, exit_cost=2000)
    options = [build, buy, partner]
    for o in options:
        costs = annual_costs(o, 5)
        print(f"{o.name:8s} 年次コスト {[round(c) for c in costs]}  単純合計 {sum(costs):,.0f}")
    print()
    for name, cost in rank_options(options, 5, 0.08):
        print(f"{name:8s} TCO（現在価値） {cost:,.0f}")
    print()
    ranges = {
        "Build.fte": (1.0, 2.5),
        "Buy.license_escalator": (0.05, 0.35),
        "Build.upfront": (3500, 8000),
        "Buy.exit_cost": (1000, 5000),
        "discount_rate": (0.04, 0.12),
        "Partner.license": (1400, 2200),
    }
    print(format_tornado(tornado(options, 5, 0.08, ranges)))
    print()
    x = break_even(options, 5, 0.08, "Buy.license_escalator", 0.0, 0.5)
    print(f"Buy のライセンス料の年上昇率が {x:.1%} を超えると Buy は最良でなくなる")
    y = break_even(options, 5, 0.08, "Build.fte", 0.5, 3.0)
    print(f"Build の運用人員が {y:.2f} 人年/年 を下回ると Build が最良になる")
