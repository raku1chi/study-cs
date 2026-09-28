"""3.2 型システム — 演習1・2: 型で間違いを防ぐ（通貨と物理量）

「ただの int / float」を、意味を持つ型で包むことで、単位や通貨の取り違えを
実行時に（そして型検査器があれば実行前に）検出できるようにします。

    演習1（★☆☆）: Money    — 通貨付きの金額。異なる通貨の加算はエラー
    演習2（★★☆）: Quantity — 次元付きの物理量。長さ＋時間はエラー、掛け算・割り算で次元が変わる

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.2

このディレクトリで演習ごとに実行することもできます:
    python3 -m unittest -v test_units.TestExercise1Money
    python3 -m unittest -v test_units.TestExercise2Quantity

制約: Money の計算では float を使わないでください（金額は最小単位の整数で扱う。1.1 章を参照）。
"""
from __future__ import annotations

import re  # noqa: F401  演習1で使えます
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 演習1（★☆☆）: Money — 通貨付きの金額
# ---------------------------------------------------------------------------

# 通貨ごとの小数部の桁数（ISO 4217 の minor unit。与えられたもの）
MINOR_UNITS: dict[str, int] = {"JPY": 0, "USD": 2, "EUR": 2, "KWD": 3}


class CurrencyMismatchError(TypeError):
    """異なる通貨の金額を足したり比べたりしようとした（与えられたもの）。"""


@dataclass(frozen=True)
class Money:
    """通貨付きの金額（不変）。amount は最小単位の整数（JPY なら円、USD ならセント）。

    実装するもの:
    - __post_init__: amount が int でなければ TypeError（float や bool も拒否する。
      bool は int のサブクラスなので type(x) is int で判定する）。
      currency が MINOR_UNITS にない（小文字も不可）なら ValueError。
    - parse(text, currency): "12.34" のような 10 進表記の文字列から作る（下記）。
    - +, -: 同じ通貨どうしだけ。通貨が違えば CurrencyMismatchError。
      Money 以外（int など）との演算は NotImplemented を返す（結果として TypeError になる）。
    - 単項 -: 符号を反転する。
    - *: int との掛け算だけを許す（Money * 3 と 3 * Money）。float や Money との掛け算は
      NotImplemented を返す（丸め方を決めずに小数倍することを型で禁止する）。
    - <, <=, >, >=: 同じ通貨どうしだけ。通貨が違えば CurrencyMismatchError、
      Money 以外との比較は TypeError。
      （== と hash はデータクラスが生成する。通貨が違えば等しくない）
    - allocate(ratios): 比率に従って分配する（下記）。
    - __str__: "JPY 1,234"、"USD 1,234.56"、"USD -0.05"、"KWD 1.234" の形式。
      通貨コード、半角スペース、符号、3 桁区切りの整数部、（桁数が 1 以上なら）"." と小数部。

    >>> Money(1000, "JPY") + Money(500, "JPY")
    Money(amount=1500, currency='JPY')
    >>> str(Money(123456, "USD"))
    'USD 1,234.56'
    """

    amount: int
    currency: str

    def __post_init__(self) -> None:
        raise NotImplementedError("演習1: Money.__post_init__ を実装してください")

    @classmethod
    def parse(cls, text: str, currency: str) -> Money:
        """10 進表記の文字列から Money を作る。float を経由してはいけない。

        - 形式: 前後の空白を除いて、[+-]? 数字 1 個以上、任意で "." と数字 1 個以上。
          数字は ASCII の 0〜9 のみ。3 桁区切りのカンマや指数表記（1e3）は受け付けない。
        - 小数部の桁数が通貨の桁数（MINOR_UNITS）より多ければ ValueError（勝手に丸めない）。
          少なければ 0 で補う。
        - 形式が不正、または currency が未対応なら ValueError。

        >>> Money.parse("12.3", "USD")
        Money(amount=1230, currency='USD')
        >>> Money.parse("0.1", "USD").amount    # float なら 0.1 は正確に表せないが、ここでは誤差なし
        10
        """
        raise NotImplementedError("演習1: Money.parse を実装してください")

    def __add__(self, other: object) -> Money:
        raise NotImplementedError("演習1: Money.__add__ を実装してください")

    def __sub__(self, other: object) -> Money:
        raise NotImplementedError("演習1: Money.__sub__ を実装してください")

    def __neg__(self) -> Money:
        raise NotImplementedError("演習1: Money.__neg__ を実装してください")

    def __mul__(self, k: object) -> Money:
        raise NotImplementedError("演習1: Money.__mul__ を実装してください")

    def __rmul__(self, k: object) -> Money:
        raise NotImplementedError("演習1: Money.__rmul__ を実装してください")

    def __lt__(self, other: object) -> bool:
        raise NotImplementedError("演習1: Money.__lt__ を実装してください")

    def __le__(self, other: object) -> bool:
        raise NotImplementedError("演習1: Money.__le__ を実装してください")

    def __gt__(self, other: object) -> bool:
        raise NotImplementedError("演習1: Money.__gt__ を実装してください")

    def __ge__(self, other: object) -> bool:
        raise NotImplementedError("演習1: Money.__ge__ を実装してください")

    def allocate(self, ratios: Sequence[int]) -> list[Money]:
        """金額を整数の比率 ratios に従って分配し、合計が元の金額と一致するリストを返す。

        - まず各項目に amount × r ÷ 合計 を切り捨てて配り、残った端数（最小単位）を、
          比率が 0 より大きい項目に先頭から 1 単位ずつ配る。
        - 比率が空、負の数や int 以外を含む、合計が 0 のときは ValueError。

        >>> [m.amount for m in Money(100, "JPY").allocate([1, 1, 1])]
        [34, 33, 33]
        >>> [m.amount for m in Money(11, "JPY").allocate([0, 1, 1])]
        [0, 6, 5]

        「100 円を 3 人で割ると 33.33… 円」を float で計算して丸めると、合計が 99 円や
        101 円になりかねない。分配の後も合計が変わらないことを保証するのがこの操作の目的。
        """
        raise NotImplementedError("演習1: Money.allocate を実装してください")

    def __str__(self) -> str:
        raise NotImplementedError("演習1: Money.__str__ を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: Quantity — 次元付きの物理量
# ---------------------------------------------------------------------------

# SI 基本単位（与えられたもの）。次元はこの順に並べて表す
BASE_UNITS: tuple[str, ...] = ("kg", "m", "s", "A", "K", "mol", "cd")


class DimensionError(TypeError):
    """次元の異なる量を足したり比べたりしようとした（与えられたもの）。"""


def _normalize_dims(dims: Mapping[str, int] | Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
    """次元を正規形（BASE_UNITS の順に並べ、指数 0 を除いたタプル）にする（与えられたもの）。

    同じ単位が複数回現れたら指数を足し合わせる。

    >>> _normalize_dims({"s": -2, "m": 1, "kg": 1})
    (('kg', 1), ('m', 1), ('s', -2))
    >>> _normalize_dims([("m", 1), ("s", -1), ("s", 1)])
    (('m', 1),)
    """
    items = dims.items() if isinstance(dims, Mapping) else dims
    exps: dict[str, int] = {}
    for unit, exp in items:
        if unit not in BASE_UNITS:
            raise ValueError(f"未知の基本単位です: {unit!r}（{', '.join(BASE_UNITS)} のいずれか）")
        if type(exp) is not int:
            raise TypeError(f"指数は整数で指定してください: {unit}^{exp!r}")
        exps[unit] = exps.get(unit, 0) + exp
    return tuple((u, exps[u]) for u in BASE_UNITS if exps.get(u, 0) != 0)


def format_dims(dims: tuple[tuple[str, int], ...]) -> str:
    """正規形の次元を "kg·m/s^2" のような文字列にする（与えられたもの）。

    正の指数の単位を "·" でつなぎ、負の指数があれば "/" の後に絶対値で並べる。
    指数が 1 なら省略する。分子がなければ "1/s"、無次元なら ""。

    >>> format_dims((("kg", 1), ("m", 1), ("s", -2)))
    'kg·m/s^2'
    """

    def part(unit: str, exp: int) -> str:
        return unit if exp == 1 else f"{unit}^{exp}"

    num = [part(u, e) for u, e in dims if e > 0]
    den = [part(u, -e) for u, e in dims if e < 0]
    if not den:
        return "·".join(num)
    return f"{'·'.join(num) or '1'}/{'·'.join(den)}"


@dataclass(frozen=True)
class Quantity:
    """次元付きの物理量（不変）。value は SI 基本単位で表した大きさ。

    Quantity(3.0, {"m": 1, "s": -1}) は 3 m/s を表す。dims は __post_init__（与えられたもの）で
    正規形のタプルに変換される。== と hash はデータクラスが生成する（value と dims を比較）。

    実装するもの:
    - +, -（逆向きの __radd__, __rsub__ も）: 次元が同じ量どうしだけ。違えば DimensionError。
      int / float（bool は除く）は「無次元量」として扱う。
      つまり 無次元量 + 1 は OK、長さ + 1 は DimensionError。それ以外の型は NotImplemented。
    - 単項 -
    - *, /（逆向きの __rmul__, __rtruediv__ も）: 値を掛け算・割り算し、次元の指数を足す・引く。
      数値との演算も可（2 * METER、1 / SECOND）。
    - **: int の指数だけを許す（それ以外は NotImplemented）。次元の指数を n 倍する。
    - <, <=, >, >=: 次元が同じなら値を比較。違えば DimensionError。数値や Quantity 以外は TypeError。
    - to(unit): unit を単位としたときの数値（self.value / unit.value）。次元が違えば DimensionError。
    - unit_str(): format_dims(self.dims)
    - __str__: "3.0 m/s" のように f"{value} {unit_str()}"。無次元なら f"{value}" だけ。

    >>> v = Quantity(10.0, {"m": 1}) / Quantity(2.0, {"s": 1})
    >>> str(v)
    '5.0 m/s'
    """

    value: float
    dims: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        """値を float に、次元を正規形にする（与えられたもの）。"""
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError(f"value は数値で指定してください: {self.value!r}")
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "dims", _normalize_dims(self.dims))

    def __add__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__add__ を実装してください")

    def __radd__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__radd__ を実装してください")

    def __sub__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__sub__ を実装してください")

    def __rsub__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__rsub__ を実装してください")

    def __neg__(self) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__neg__ を実装してください")

    def __mul__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__mul__ を実装してください")

    def __rmul__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__rmul__ を実装してください")

    def __truediv__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__truediv__ を実装してください")

    def __rtruediv__(self, other: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__rtruediv__ を実装してください")

    def __pow__(self, n: object) -> Quantity:
        raise NotImplementedError("演習2: Quantity.__pow__ を実装してください")

    def __lt__(self, other: object) -> bool:
        raise NotImplementedError("演習2: Quantity.__lt__ を実装してください")

    def __le__(self, other: object) -> bool:
        raise NotImplementedError("演習2: Quantity.__le__ を実装してください")

    def __gt__(self, other: object) -> bool:
        raise NotImplementedError("演習2: Quantity.__gt__ を実装してください")

    def __ge__(self, other: object) -> bool:
        raise NotImplementedError("演習2: Quantity.__ge__ を実装してください")

    def to(self, unit: Quantity) -> float:
        """unit を単位として表した数値を返す。

        >>> (Quantity(90_000.0, {"m": 1}) / Quantity(3600.0, {"s": 1})).to(Quantity(1.0, {"m": 1, "s": -1}))
        25.0
        """
        raise NotImplementedError("演習2: Quantity.to を実装してください")

    def unit_str(self) -> str:
        """次元を文字列で返す（format_dims を使う）。"""
        raise NotImplementedError("演習2: Quantity.unit_str を実装してください")

    def __str__(self) -> str:
        raise NotImplementedError("演習2: Quantity.__str__ を実装してください")


# よく使う単位（与えられたもの）。値はすべて SI 基本単位で表した大きさ
KILOGRAM = Quantity(1.0, {"kg": 1})
METER = Quantity(1.0, {"m": 1})
SECOND = Quantity(1.0, {"s": 1})
KILOMETER = Quantity(1000.0, {"m": 1})
HOUR = Quantity(3600.0, {"s": 1})
NEWTON = Quantity(1.0, {"kg": 1, "m": 1, "s": -2})
JOULE = Quantity(1.0, {"kg": 1, "m": 2, "s": -2})
# 1 ポンド重 = 0.45359237 kg × 9.80665 m/s^2 = 4.4482216152605 N（定義値）
POUND_FORCE = Quantity(4.4482216152605, {"kg": 1, "m": 1, "s": -2})
