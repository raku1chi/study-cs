"""8.1 良いコードと設計原則 — 解答例: 価格計算エンジン（リファクタリング後 + v2 の新機能）

仕様は exercises/pricing.py の docstring を参照してください。
ここに至るまでの手順の一例は、章の README の「演習」の解説を見てください。

設計の要点:
  1. 境界（calculate_total）で入力を検証して型のついた値に変換し、内側では検証済みの値だけを扱う。
  2. ビジネスが変えたくなる値（割引率・送料・税率・キャンペーン期間）を、表として 1 か所に集める。
  3. 計算を「明細の割引率 → 明細の割引額 → 注文全体の割引 → 送料 → 税」という段階に分ける。
  4. 現在時刻は clock から一度だけ読み、計算の中心（_quote）は純粋関数にする
     （functional core, imperative shell）。テストでは時計を差し替えられる。
  5. 既存コードの「癖」は、意図をコメントに書いたうえで明示的に保存する。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Mapping, Optional, Protocol, Sequence

JST = timezone(timedelta(hours=9), "JST")
Clock = Callable[[], datetime]

# ---------------------------------------------------------------------------
# ビジネスルール（変更が予想される値はここに集める）
# ---------------------------------------------------------------------------

TIER_DISCOUNT_PERCENT: Mapping[str, int] = {
    "regular": 0,
    "silver": 5,
    "gold": 10,
    "platinum": 15,
}
FREE_SHIPPING_TIERS = frozenset({"gold", "platinum"})
SHIPPING_FEE = 500
FREE_SHIPPING_THRESHOLD = 5_000

# 書籍は定価販売（この店のルール）なので、割引の対象は食品と雑貨だけ
DISCOUNTABLE_CATEGORIES = frozenset({"food", "goods"})
TAX_RATE_PERCENT: Mapping[str, int] = {"book": 10, "food": 8, "goods": 10}
SHIPPING_TAX_RATE_PERCENT = 10


@dataclass(frozen=True)
class Campaign:
    """期間限定で、特定カテゴリの割引率を上乗せする。期間は [start, end)（end は含まない）。"""

    name: str
    category: str
    extra_percent: int
    start: datetime
    end: datetime

    def is_active(self, now: datetime) -> bool:
        # timezone 付きの datetime どうしは、タイムゾーンが違っても正しく比較できる
        return self.start <= now < self.end


CAMPAIGNS: tuple[Campaign, ...] = (
    Campaign(
        name="秋の食品フェア",
        category="food",
        extra_percent=5,
        start=datetime(2026, 10, 1, tzinfo=JST),
        end=datetime(2026, 11, 1, tzinfo=JST),
    ),
)


# ---------------------------------------------------------------------------
# ドメインの値
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Line:
    """検証済みの明細。amount は単価 × 数量（税抜）。"""

    category: str
    amount: int

    @property
    def discountable(self) -> bool:
        return self.category in DISCOUNTABLE_CATEGORIES

    @property
    def tax_rate(self) -> int:
        return TAX_RATE_PERCENT[self.category]


@dataclass(frozen=True)
class OrderDiscount:
    """注文全体に対する定額の割引と、それを差し引く課税区分（税率）。"""

    amount: int
    tax_rate: int


# ---------------------------------------------------------------------------
# クーポン（Strategy パターン: 種類ごとに振る舞いを差し替える）
# ---------------------------------------------------------------------------

class Coupon(Protocol):
    code: str

    def validate(self, tier: str, lines: Sequence[Line]) -> None: ...

    def line_percent(self, line: Line) -> int: ...

    def order_discount(self, lines: Sequence[Line], net_amounts: Sequence[int]) -> Optional[OrderDiscount]: ...


@dataclass(frozen=True)
class PercentOffCoupon:
    """割引対象の明細に、割引率を上乗せするクーポン（例: WELCOME10）。"""

    code: str
    percent: int
    allowed_tiers: frozenset

    def validate(self, tier: str, lines: Sequence[Line]) -> None:
        # 既存の振る舞いを保存している: 割引対象の明細がないカート（書籍だけ）では、
        # 利用資格を検査しない。旧コードは割引対象の明細を処理する途中でしか
        # 検査していなかったため。仕様として正しいかは要確認 —— 変えるなら
        # リファクタリングとは別の変更として、関係者と合意してから変える。
        if tier not in self.allowed_tiers and any(line.discountable for line in lines):
            allowed = "・".join(sorted(self.allowed_tiers))
            raise ValueError(f"{self.code} は {allowed} 会員のみ使えます（現在: {tier}）")

    def line_percent(self, line: Line) -> int:
        return self.percent if line.discountable else 0

    def order_discount(self, lines: Sequence[Line], net_amounts: Sequence[int]) -> Optional[OrderDiscount]:
        return None


@dataclass(frozen=True)
class AmountOffCoupon:
    """特定カテゴリの割引後合計が条件を満たすと、注文から定額を引くクーポン（例: GOODS500）。"""

    code: str
    amount: int
    category: str
    minimum: int

    def validate(self, tier: str, lines: Sequence[Line]) -> None:
        return None  # 会員ランクの制限はない

    def line_percent(self, line: Line) -> int:
        return 0

    def order_discount(self, lines: Sequence[Line], net_amounts: Sequence[int]) -> Optional[OrderDiscount]:
        eligible = sum(net for line, net in zip(lines, net_amounts) if line.category == self.category)
        if eligible < self.minimum:
            raise ValueError(
                f"{self.code} は {self.category} の割引後の合計が {self.minimum:,} 円以上のときに使えます"
                f"（現在: {eligible:,} 円）"
            )
        return OrderDiscount(self.amount, TAX_RATE_PERCENT[self.category])


COUPONS: Mapping[str, Coupon] = {
    "WELCOME10": PercentOffCoupon("WELCOME10", 10, frozenset({"regular"})),
    "GOODS500": AmountOffCoupon("GOODS500", 500, "goods", 3_000),
}


# ---------------------------------------------------------------------------
# 公開インターフェース（imperative shell: 入力の検証と、時計の読み取り）
# ---------------------------------------------------------------------------

def calculate_total(cart, customer, coupon_code=None, *, clock: Optional[Clock] = None) -> dict:
    lines = _parse_cart(cart)
    tier = _parse_tier(customer)
    coupon = _parse_coupon(coupon_code)
    now = (clock or _system_clock)()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(f"clock は timezone 付きの datetime を返してください: {now!r}")
    return _quote(lines, tier, coupon, now)


def _system_clock() -> datetime:
    return datetime.now(timezone.utc)


def _parse_cart(cart) -> list[Line]:
    if not cart:
        raise ValueError("カートが空です")
    lines = []
    for item in cart:
        category = item.get("category")
        unit_price = item.get("unit_price")
        qty = item.get("qty")
        if not isinstance(unit_price, int) or unit_price < 0:
            raise ValueError(f"単価が不正です: {item!r}")
        if not isinstance(qty, int) or qty < 1:
            raise ValueError(f"数量が不正です: {item!r}")
        if category not in TAX_RATE_PERCENT:
            raise ValueError(f"不明なカテゴリです: {category!r}")
        lines.append(Line(category, unit_price * qty))
    return lines


def _parse_tier(customer) -> str:
    tier = customer.get("tier")
    if tier not in TIER_DISCOUNT_PERCENT:
        raise ValueError(f"不明な会員ランクです: {tier!r}")
    return tier


def _parse_coupon(code) -> Optional[Coupon]:
    if code is None:
        return None
    try:
        return COUPONS[code]
    except KeyError:
        raise ValueError(f"不明なクーポンです: {code!r}") from None


# ---------------------------------------------------------------------------
# 計算の中心（functional core: 入力だけから結果が決まる純粋関数）
# ---------------------------------------------------------------------------

def _quote(lines: Sequence[Line], tier: str, coupon: Optional[Coupon], now: datetime) -> dict:
    if coupon is not None:
        coupon.validate(tier, lines)
    campaigns = [c for c in CAMPAIGNS if c.is_active(now)]

    # 1. 明細ごとの割引: 割引率を合計してから掛け、1 回だけ切り捨てる
    line_discounts = [line.amount * _line_percent(line, tier, coupon, campaigns) // 100 for line in lines]
    net_amounts = [line.amount - d for line, d in zip(lines, line_discounts)]

    # 2. 注文全体の割引（定額クーポン）
    order_discount = coupon.order_discount(lines, net_amounts) if coupon is not None else None

    # 3. 送料（割引後の商品合計で判定する）
    subtotal = sum(line.amount for line in lines)
    discount = sum(line_discounts) + (order_discount.amount if order_discount else 0)
    shipping = _shipping_fee(tier, merchandise_total=subtotal - discount)

    # 4. 消費税
    tax_by_rate = _tax_by_rate(lines, net_amounts, order_discount, shipping)
    tax = sum(tax_by_rate.values())
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "tax": tax,
        "tax_by_rate": tax_by_rate,
        "total": subtotal - discount + shipping + tax,
    }


def _line_percent(line: Line, tier: str, coupon: Optional[Coupon], campaigns: Sequence[Campaign]) -> int:
    if not line.discountable:
        return 0
    percent = TIER_DISCOUNT_PERCENT[tier]
    if coupon is not None:
        percent += coupon.line_percent(line)
    percent += sum(c.extra_percent for c in campaigns if c.category == line.category)
    return percent


def _shipping_fee(tier: str, merchandise_total: int) -> int:
    if tier in FREE_SHIPPING_TIERS or merchandise_total >= FREE_SHIPPING_THRESHOLD:
        return 0
    return SHIPPING_FEE


def _tax_by_rate(
    lines: Sequence[Line], net_amounts: Sequence[int], order_discount: Optional[OrderDiscount], shipping: int
) -> dict[int, int]:
    """税率ごとに課税対象額を合計してから、1 回だけ切り捨てる。"""
    taxable = {8: 0, 10: 0}
    for line, net in zip(lines, net_amounts):
        taxable[line.tax_rate] += net
    if order_discount is not None:
        taxable[order_discount.tax_rate] -= order_discount.amount
    taxable[SHIPPING_TAX_RATE_PERCENT] += shipping
    return {rate: amount * rate // 100 for rate, amount in taxable.items()}
