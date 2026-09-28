"""3.2 型システム — 通貨と物理量の型（解答例）

演習の仕様は exercises/units.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# 演習1: Money
# ---------------------------------------------------------------------------

MINOR_UNITS: dict[str, int] = {"JPY": 0, "USD": 2, "EUR": 2, "KWD": 3}


class CurrencyMismatchError(TypeError):
    """異なる通貨の金額を足したり比べたりしようとした。"""


_DECIMAL_RE = re.compile(r"[+-]?[0-9]+(?:\.[0-9]+)?")  # \d だと全角数字にも一致するので使わない


@dataclass(frozen=True)
class Money:
    amount: int
    currency: str

    def __post_init__(self) -> None:
        # bool は int のサブクラスなので、type(...) is int で厳密に判定する
        if type(self.amount) is not int:
            raise TypeError(f"amount は最小単位の整数で指定してください: {self.amount!r}")
        if self.currency not in MINOR_UNITS:
            raise ValueError(f"未対応の通貨コードです: {self.currency!r}")

    @classmethod
    def parse(cls, text: str, currency: str) -> Money:
        if currency not in MINOR_UNITS:
            raise ValueError(f"未対応の通貨コードです: {currency!r}")
        s = text.strip()
        if not _DECIMAL_RE.fullmatch(s):
            raise ValueError(f"金額の形式が不正です: {text!r}")
        digits = MINOR_UNITS[currency]
        sign = -1 if s.startswith("-") else 1
        s = s.lstrip("+-")
        whole, _, frac = s.partition(".")
        if len(frac) > digits:
            raise ValueError(f"{currency} の小数部は {digits} 桁までです: {text!r}")
        # float を経由せず、文字列から整数演算だけで最小単位に変換する（誤差が入らない）
        minor = int(whole) * 10**digits + int(frac.ljust(digits, "0") or "0")
        return cls(sign * minor, currency)

    def _check_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(f"通貨が異なります: {self.currency} と {other.currency}")

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.amount, self.currency)

    def __mul__(self, k: object) -> Money:
        # 整数倍だけを許す。小数倍（税率など）は丸め方の決定が必要なので、別の操作にする
        if type(k) is not int:
            return NotImplemented
        return Money(self.amount * k, self.currency)

    __rmul__ = __mul__

    def _compare_key(self, other: object) -> int:
        if not isinstance(other, Money):
            raise TypeError(f"Money と {type(other).__name__} は比較できません")
        self._check_same_currency(other)
        return other.amount

    def __lt__(self, other: object) -> bool:
        return self.amount < self._compare_key(other)

    def __le__(self, other: object) -> bool:
        return self.amount <= self._compare_key(other)

    def __gt__(self, other: object) -> bool:
        return self.amount > self._compare_key(other)

    def __ge__(self, other: object) -> bool:
        return self.amount >= self._compare_key(other)

    def allocate(self, ratios: Sequence[int]) -> list[Money]:
        if not ratios or any(type(r) is not int or r < 0 for r in ratios) or sum(ratios) == 0:
            raise ValueError(f"比率は 0 以上の整数で、合計が正である必要があります: {ratios!r}")
        total = sum(ratios)
        # まず切り捨てで配り、残った端数を比率が正の項目に先頭から 1 単位ずつ配る
        shares = [self.amount * r // total for r in ratios]
        remainder = self.amount - sum(shares)  # 切り捨てなので 0 以上
        for i, r in enumerate(ratios):
            if remainder == 0:
                break
            if r > 0:
                shares[i] += 1
                remainder -= 1
        return [Money(s, self.currency) for s in shares]

    def __str__(self) -> str:
        digits = MINOR_UNITS[self.currency]
        sign = "-" if self.amount < 0 else ""
        whole, frac = divmod(abs(self.amount), 10**digits)
        text = f"{whole:,}"
        if digits:
            text += "." + str(frac).zfill(digits)
        return f"{self.currency} {sign}{text}"


# ---------------------------------------------------------------------------
# 演習2: Quantity（次元付きの物理量）
# ---------------------------------------------------------------------------

BASE_UNITS: tuple[str, ...] = ("kg", "m", "s", "A", "K", "mol", "cd")


class DimensionError(TypeError):
    """次元の異なる量を足したり比べたりしようとした。"""


def _normalize_dims(dims: Mapping[str, int] | Iterable[tuple[str, int]]) -> tuple[tuple[str, int], ...]:
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
    def part(unit: str, exp: int) -> str:
        return unit if exp == 1 else f"{unit}^{exp}"

    num = [part(u, e) for u, e in dims if e > 0]
    den = [part(u, -e) for u, e in dims if e < 0]
    if not den:
        return "·".join(num)
    return f"{'·'.join(num) or '1'}/{'·'.join(den)}"


@dataclass(frozen=True)
class Quantity:
    value: float
    dims: tuple[tuple[str, int], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
            raise TypeError(f"value は数値で指定してください: {self.value!r}")
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "dims", _normalize_dims(self.dims))

    @staticmethod
    def _coerce(other: object) -> Quantity | None:
        if isinstance(other, Quantity):
            return other
        if isinstance(other, (int, float)) and not isinstance(other, bool):
            return Quantity(other)  # ただの数値は「無次元量」として扱う
        return None

    def _same_dims(self, other: Quantity, op: str) -> None:
        if self.dims != other.dims:
            raise DimensionError(
                f"{op}: 次元が一致しません（{format_dims(self.dims) or '無次元'} と "
                f"{format_dims(other.dims) or '無次元'}）"
            )

    def __add__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        self._same_dims(o, "+")
        return Quantity(self.value + o.value, self.dims)

    def __radd__(self, other: object) -> Quantity:
        return self.__add__(other)

    def __sub__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        self._same_dims(o, "-")
        return Quantity(self.value - o.value, self.dims)

    def __rsub__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        return o.__sub__(self)

    def __neg__(self) -> Quantity:
        return Quantity(-self.value, self.dims)

    def __mul__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        # 掛け算では指数を足す（m × m = m^2、m/s × s = m）
        return Quantity(self.value * o.value, self.dims + o.dims)

    def __rmul__(self, other: object) -> Quantity:
        return self.__mul__(other)

    def __truediv__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        # 割り算では指数を引く
        return Quantity(self.value / o.value, self.dims + tuple((u, -e) for u, e in o.dims))

    def __rtruediv__(self, other: object) -> Quantity:
        o = self._coerce(other)
        if o is None:
            return NotImplemented
        return o.__truediv__(self)

    def __pow__(self, n: object) -> Quantity:
        if type(n) is not int:
            return NotImplemented
        return Quantity(self.value**n, tuple((u, e * n) for u, e in self.dims))

    def _compare(self, other: object, op: str) -> float:
        o = self._coerce(other)
        if o is None:
            raise TypeError(f"Quantity と {type(other).__name__} は比較できません")
        self._same_dims(o, op)
        return o.value

    def __lt__(self, other: object) -> bool:
        return self.value < self._compare(other, "<")

    def __le__(self, other: object) -> bool:
        return self.value <= self._compare(other, "<=")

    def __gt__(self, other: object) -> bool:
        return self.value > self._compare(other, ">")

    def __ge__(self, other: object) -> bool:
        return self.value >= self._compare(other, ">=")

    def to(self, unit: Quantity) -> float:
        self._same_dims(unit, "to")
        return self.value / unit.value

    def unit_str(self) -> str:
        return format_dims(self.dims)

    def __str__(self) -> str:
        unit = self.unit_str()
        return f"{self.value} {unit}" if unit else f"{self.value}"


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
