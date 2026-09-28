"""8.1 演習1・2 — 価格計算エンジンのテスト

実行: python3 tools/check.py 8.1   （またはこのディレクトリで python3 -m unittest -v test_pricing）

テストは 2 種類あります。
  - TestCharacterization...: 既存コード（v1）の「現在の振る舞い」を固定する特性テスト。
    最初から通ります。リファクタリング中は常に緑に保ってください。
  - TestNewFeature...: 新しい要件（v2）のテスト。最初は失敗します（演習2）。

特性テストは、時計を注入できるようになった後も「キャンペーン期間外の固定時刻」で実行します。
テストを実行する日によって結果が変わらないようにするためです（本文の「テスト容易性」を参照）。
"""
import inspect
import json
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pricing

JST = timezone(timedelta(hours=9))
UTC = timezone.utc
# キャンペーン期間外の固定時刻（特性テスト用）
OUTSIDE_CAMPAIGN = datetime(2026, 1, 15, 12, 0, tzinfo=JST)
GOLDEN_FILE = Path(__file__).parent / "data" / "pricing_golden.json"


def accepts_clock() -> bool:
    try:
        return "clock" in inspect.signature(pricing.calculate_total).parameters
    except (TypeError, ValueError):
        return False


def quote(cart, tier, coupon=None, at=OUTSIDE_CAMPAIGN):
    """clock を受け取れる実装なら固定時刻を注入し、受け取れない実装（v1）ならそのまま呼ぶ。"""
    if accepts_clock():
        return pricing.calculate_total(cart, {"tier": tier}, coupon, clock=lambda: at)
    return pricing.calculate_total(cart, {"tier": tier}, coupon)


def item(category, unit_price, qty=1, sku=None):
    return {"sku": sku or f"{category[:1].upper()}-001", "category": category, "unit_price": unit_price, "qty": qty}


def expected(subtotal, discount, shipping, tax8, tax10):
    return {
        "subtotal": subtotal,
        "discount": discount,
        "shipping": shipping,
        "tax": tax8 + tax10,
        "tax_by_rate": {8: tax8, 10: tax10},
        "total": subtotal - discount + shipping + tax8 + tax10,
    }


# ---------------------------------------------------------------------------
# 特性テスト（最初から通る。リファクタリング中も緑に保つ）
# ---------------------------------------------------------------------------

class TestCharacterizationExamples(unittest.TestCase):
    def test_regular_customer_pays_shipping_and_tax(self):
        self.assertEqual(quote([item("goods", 1200, 2)], "regular"), expected(2400, 0, 500, 0, 290))

    def test_result_keys(self):
        result = quote([item("goods", 100)], "regular")
        self.assertEqual(set(result), {"subtotal", "discount", "shipping", "tax", "tax_by_rate", "total"})

    def test_books_are_never_discounted(self):
        self.assertEqual(quote([item("book", 1500, 2)], "gold"), expected(3000, 0, 0, 0, 300))

    def test_member_discount_is_floored_per_line(self):
        # 999 × 5% = 49.95 → 49、1999 × 5% = 99.95 → 99
        cart = [item("food", 999), item("goods", 1999)]
        self.assertEqual(quote(cart, "silver"), expected(2998, 148, 500, 76, 240))

    def test_tax_is_rounded_once_per_rate(self):
        # 明細ごとに切り捨てると 8 × 3 = 24 円だが、税率ごとにまとめて 315 × 8% = 25.2 → 25 円
        cart = [item("food", 105, sku="F-1"), item("food", 105, sku="F-2"), item("food", 105, sku="F-3")]
        self.assertEqual(quote(cart, "regular"), expected(315, 0, 500, 25, 50))

    def test_free_shipping_threshold_uses_discounted_amount(self):
        self.assertEqual(quote([item("goods", 5000)], "regular")["shipping"], 0)
        self.assertEqual(quote([item("goods", 4999)], "regular")["shipping"], 500)
        # 5263 - 263（5%）= 5000 → 無料
        self.assertEqual(quote([item("goods", 5263)], "silver")["shipping"], 0)
        # 5262 - 263 = 4999 → 有料
        self.assertEqual(quote([item("goods", 5262)], "silver")["shipping"], 500)

    def test_gold_members_always_get_free_shipping(self):
        self.assertEqual(quote([item("food", 100)], "gold"), expected(100, 10, 0, 7, 0))

    def test_welcome10_for_regular_customer(self):
        cart = [item("goods", 2000), item("book", 1000)]
        self.assertEqual(quote(cart, "regular", "WELCOME10"), expected(3000, 200, 500, 0, 330))

    def test_welcome10_is_rejected_for_other_tiers(self):
        for tier in ("silver", "gold"):
            with self.assertRaises(ValueError, msg=tier):
                quote([item("goods", 1000)], tier, "WELCOME10")

    def test_quirk_welcome10_is_not_checked_for_books_only_cart(self):
        # 仕様書には書かれていない「癖」: 割引対象の明細がないと、利用資格の検査が行われない。
        try:
            result = quote([item("book", 1000)], "silver", "WELCOME10")
        except ValueError:
            self.fail(
                "既存の振る舞いが変わりました: 書籍だけのカートでは、silver 会員の WELCOME10 は"
                "エラーにならずに無視されていました。振る舞いを変えるなら、リファクタリングとは"
                "別の変更として関係者と合意してから行ってください（特性テストは現在の振る舞いを固定します）"
            )
        self.assertEqual(result, expected(1000, 0, 500, 0, 150))

    def test_goods500_applies_after_member_discount(self):
        # 3334 - 333（10%）= 3001 ≥ 3000 → 500 円引き
        self.assertEqual(quote([item("goods", 3334)], "gold", "GOODS500"), expected(3334, 833, 0, 0, 250))

    def test_goods500_threshold_boundary(self):
        # silver: 3157 - 157 = 3000 → 使える / 3156 - 157 = 2999 → 使えない
        self.assertEqual(quote([item("goods", 3157)], "silver", "GOODS500")["discount"], 657)
        with self.assertRaises(ValueError):
            quote([item("goods", 3156)], "silver", "GOODS500")

    def test_goods500_reduces_the_10_percent_tax_base(self):
        cart = [item("goods", 3000), item("food", 2000)]
        self.assertEqual(quote(cart, "regular", "GOODS500"), expected(5000, 500, 500, 160, 300))

    def test_invalid_inputs_raise_value_error(self):
        cases = {
            "空のカート": ([], "regular", None),
            "数量 0": ([item("goods", 100, 0)], "regular", None),
            "数量が小数": ([item("goods", 100, 1.5)], "regular", None),
            "単価が負": ([item("goods", -1)], "regular", None),
            "単価が文字列": ([item("goods", "100")], "regular", None),
            "未知のカテゴリ": ([item("toys", 100)], "regular", None),
            "未知の会員ランク": ([item("goods", 100)], "diamond", None),
            "未知のクーポン": ([item("goods", 100)], "regular", "SAVE99"),
        }
        for label, (cart, tier, coupon) in cases.items():
            with self.assertRaises(ValueError, msg=label):
                quote(cart, tier, coupon)

    def test_missing_tier_raises_value_error(self):
        with self.assertRaises(ValueError):
            if accepts_clock():
                pricing.calculate_total([item("goods", 100)], {}, clock=lambda: OUTSIDE_CAMPAIGN)
            else:
                pricing.calculate_total([item("goods", 100)], {})


class TestCharacterizationGoldenMaster(unittest.TestCase):
    """レガシー版の出力を記録したゴールデンマスター（120 ケース）と照合する。"""

    def test_matches_recorded_outputs(self):
        cases = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))["cases"]
        mismatches = []
        for index, case in enumerate(cases):
            try:
                actual = quote(case["cart"], case["customer"]["tier"], case["coupon"])
                actual = dict(actual, tax_by_rate={str(k): v for k, v in actual["tax_by_rate"].items()})
            except ValueError:
                actual = "ValueError"
            if actual != case["expected"]:
                mismatches.append(
                    f"  ケース {index}: tier={case['customer']['tier']} coupon={case['coupon']}\n"
                    f"    cart     = {case['cart']}\n"
                    f"    期待     = {case['expected']}\n"
                    f"    実際     = {actual}"
                )
        if mismatches:
            shown = "\n".join(mismatches[:3])
            self.fail(f"記録された振る舞いと {len(mismatches)}/{len(cases)} ケースが一致しません（先頭 3 件）:\n{shown}")


# ---------------------------------------------------------------------------
# 新機能テスト（演習2。最初は失敗する）
# ---------------------------------------------------------------------------

class FeatureTestCase(unittest.TestCase):
    def quote_or_fail(self, cart, tier, coupon=None, at=OUTSIDE_CAMPAIGN):
        """正しい入力で ValueError が出たら、未実装として分かりやすいメッセージで失敗させる。"""
        try:
            return quote(cart, tier, coupon, at)
        except ValueError as exc:
            if tier != "platinum":
                raise
            message = f"演習2（N1）: platinum ランクが未対応です（{type(exc).__name__}: {exc}）"
        self.fail(message)

    def quote_at(self, when, cart, tier, coupon=None):
        if not accepts_clock():
            self.fail(
                "演習2（N2）: calculate_total にキーワード専用引数 clock を追加してください"
                "（引数なしで呼ぶと現在時刻を返す関数を注入できるように）"
            )
        return self.quote_or_fail(cart, tier, coupon, at=when)


class TestNewFeaturePlatinum(FeatureTestCase):
    def test_platinum_gets_15_percent_on_non_book_lines(self):
        cart = [item("goods", 2000), item("food", 1000), item("book", 1000)]
        self.assertEqual(
            self.quote_or_fail(cart, "platinum"), expected(4000, 450, 0, 68, 270),
            "platinum: 食品・雑貨に 15% 引き、書籍は定価、送料無料",
        )

    def test_platinum_always_gets_free_shipping(self):
        self.assertEqual(self.quote_or_fail([item("food", 100)], "platinum"), expected(100, 15, 0, 6, 0))

    def test_platinum_cannot_use_welcome10(self):
        self.quote_or_fail([item("goods", 1000)], "platinum")  # 未対応ならここで分かりやすく失敗する
        with self.assertRaises(ValueError, msg="WELCOME10 は regular 専用"):
            quote([item("goods", 1000)], "platinum", "WELCOME10")

    def test_platinum_with_goods500(self):
        # 3530 - 529（15%）= 3001 ≥ 3000 → 500 円引き
        self.assertEqual(
            self.quote_or_fail([item("goods", 3530)], "platinum", "GOODS500"), expected(3530, 1029, 0, 0, 250)
        )


class TestNewFeatureAutumnFoodFair(FeatureTestCase):
    IN_CAMPAIGN = datetime(2026, 10, 15, 12, 0, tzinfo=JST)
    NO_DISCOUNT = expected(1000, 0, 500, 80, 50)
    WITH_DISCOUNT = expected(1000, 50, 500, 76, 50)

    def test_food_gets_extra_5_percent_during_campaign(self):
        self.assertEqual(
            self.quote_at(self.IN_CAMPAIGN, [item("food", 1000)], "regular"), self.WITH_DISCOUNT,
            "キャンペーン期間中は食品に 5% 引きが追加される",
        )

    def test_campaign_starts_at_midnight_jst(self):
        just_before = datetime(2026, 9, 30, 23, 59, 59, tzinfo=JST)
        start_in_utc = datetime(2026, 9, 30, 15, 0, 0, tzinfo=UTC)  # = 2026-10-01 00:00 JST
        self.assertEqual(self.quote_at(just_before, [item("food", 1000)], "regular"), self.NO_DISCOUNT)
        self.assertEqual(
            self.quote_at(start_in_utc, [item("food", 1000)], "regular"), self.WITH_DISCOUNT,
            "UTC で表した 2026-09-30T15:00Z は日本時間の 10/1 0:00 なので期間内",
        )

    def test_campaign_end_is_exclusive(self):
        last_moment = datetime(2026, 10, 31, 23, 59, 59, 999999, tzinfo=JST)
        end = datetime(2026, 11, 1, 0, 0, tzinfo=JST)
        self.assertEqual(self.quote_at(last_moment, [item("food", 1000)], "regular"), self.WITH_DISCOUNT)
        self.assertEqual(self.quote_at(end, [item("food", 1000)], "regular"), self.NO_DISCOUNT)

    def test_other_time_zones_are_compared_correctly(self):
        # ニューヨーク（UTC-5）の 10/31 10:00 は、日本時間の 11/1 0:00 → 期間外
        new_york = timezone(timedelta(hours=-5))
        when = datetime(2026, 10, 31, 10, 0, tzinfo=new_york)
        self.assertEqual(self.quote_at(when, [item("food", 1000)], "regular"), self.NO_DISCOUNT)

    def test_rates_are_added_then_floored_once(self):
        # gold の食品 999 円: 10% + 5% = 15% → 149.85 → 149 円（別々に切り捨てると 99 + 49 = 148 円）
        self.assertEqual(
            self.quote_at(self.IN_CAMPAIGN, [item("food", 999)], "gold"), expected(999, 149, 0, 68, 0),
            "複数の割引率は合計してから 1 回だけ切り捨てる",
        )

    def test_campaign_does_not_apply_to_goods_or_books(self):
        cart = [item("goods", 1000), item("book", 1000)]
        self.assertEqual(self.quote_at(self.IN_CAMPAIGN, cart, "regular"), expected(2000, 0, 500, 0, 250))

    def test_campaign_stacks_with_platinum(self):
        self.assertEqual(
            self.quote_at(self.IN_CAMPAIGN, [item("food", 2000)], "platinum"), expected(2000, 400, 0, 128, 0)
        )

    def test_campaign_stacks_with_welcome10(self):
        self.assertEqual(
            self.quote_at(self.IN_CAMPAIGN, [item("food", 1000)], "regular", "WELCOME10"),
            expected(1000, 150, 500, 68, 50),
        )

    def test_clock_is_actually_used(self):
        calls = []

        def clock():
            calls.append(1)
            return self.IN_CAMPAIGN

        if not accepts_clock():
            self.quote_at(self.IN_CAMPAIGN, [item("food", 1000)], "regular")  # 分かりやすく失敗させる
        pricing.calculate_total([item("food", 1000)], {"tier": "regular"}, clock=clock)
        self.assertGreaterEqual(len(calls), 1, "注入された clock が呼ばれていません（システム時計を直接読んでいませんか）")

    def test_naive_datetime_is_rejected(self):
        if not accepts_clock():
            self.quote_at(self.IN_CAMPAIGN, [item("food", 1000)], "regular")
        with self.assertRaises(ValueError, msg="timezone のない datetime は日本時間か UTC か判断できない"):
            pricing.calculate_total([item("food", 1000)], {"tier": "regular"}, clock=lambda: datetime(2026, 10, 15))


if __name__ == "__main__":
    unittest.main()
