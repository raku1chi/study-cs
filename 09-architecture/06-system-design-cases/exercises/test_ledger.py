"""9.6 システム設計ケーススタディ — 演習4 のテスト（複式簿記の元帳）

プリペイドのウォレットを題材にします。

    psp_cash        決済代行に預けてあるお金（資産）
    wallet:alice    alice に対する支払い義務＝alice のウォレット残高（負債。マイナス不可）
    payable:shop1   加盟店 shop1 への未払い金（負債）
    revenue:fees    手数料収入（収益）

実行: python3 tools/check.py 9.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import threading
import unittest
from datetime import datetime, timedelta, timezone

from ledger import (
    AccountType,
    AlreadyReversedError,
    CurrencyMismatchError,
    IdempotencyConflictError,
    InsufficientBalanceError,
    InvalidPostingError,
    Ledger,
    LedgerError,
    OutOfOrderError,
    Posting,
    UnbalancedEntryError,
    UnknownAccountError,
    UnknownEntryError,
)

JST = timezone(timedelta(hours=9))


def t(day, hour=12):
    return datetime(2026, 4, day, hour, 0, tzinfo=JST)


def make_ledger():
    ledger = Ledger()
    ledger.open_account("psp_cash", AccountType.ASSET)
    ledger.open_account("wallet:alice", AccountType.LIABILITY, allow_negative=False)
    ledger.open_account("payable:shop1", AccountType.LIABILITY)
    ledger.open_account("revenue:fees", AccountType.REVENUE)
    return ledger


def top_up(ledger, amount, external_id="psp_evt_1", at=None):
    return ledger.post(external_id, [Posting("psp_cash", debit=amount), Posting("wallet:alice", credit=amount)],
                       at or t(1), "チャージ")


def purchase(ledger, amount, fee, external_id="order_1", at=None):
    return ledger.post(external_id, [
        Posting("wallet:alice", debit=amount),
        Posting("payable:shop1", credit=amount - fee),
        Posting("revenue:fees", credit=fee),
    ], at or t(2), "shop1 での支払い")


class TestExercise4Postings(unittest.TestCase):
    def test_posting_validation(self):
        self.assertEqual(Posting("a", debit=100).credit, 0)
        for kwargs in ({"debit": 0, "credit": 0}, {"debit": 100, "credit": 100}, {"debit": -1},
                       {"credit": 1.5}, {"debit": True}):
            with self.assertRaises(InvalidPostingError, msg=str(kwargs)):
                Posting("a", **kwargs)

    def test_accounts(self):
        ledger = make_ledger()
        self.assertEqual(ledger.account("psp_cash").normal_side, "debit")
        self.assertEqual(ledger.account("wallet:alice").normal_side, "credit")
        with self.assertRaises(LedgerError):
            ledger.open_account("psp_cash", AccountType.ASSET)
        with self.assertRaises(UnknownAccountError):
            ledger.account("nope")


class TestExercise4Posting(unittest.TestCase):
    def setUp(self):
        self.ledger = make_ledger()

    def test_balances_follow_the_normal_side(self):
        r = top_up(self.ledger, 10_000)
        self.assertFalse(r.duplicate)
        self.assertEqual(r.entry.entry_id, "je_000001")
        purchase(self.ledger, 3_000, 90)
        self.assertEqual(self.ledger.balance("psp_cash"), 10_000)       # 資産: 借方 − 貸方
        self.assertEqual(self.ledger.balance("wallet:alice"), 7_000)    # 負債: 貸方 − 借方
        self.assertEqual(self.ledger.balance("payable:shop1"), 2_910)
        self.assertEqual(self.ledger.balance("revenue:fees"), 90)
        debits, credits = self.ledger.trial_balance()
        self.assertEqual(debits, credits)
        self.assertEqual(debits, 13_000)

    def test_unbalanced_entry_is_rejected(self):
        with self.assertRaises(UnbalancedEntryError):
            self.ledger.post("x1", [Posting("psp_cash", debit=1_000), Posting("wallet:alice", credit=999)], t(1))
        self.assertEqual(self.ledger.balance("psp_cash"), 0, "失敗した記帳は何も変更しない")
        self.assertEqual(self.ledger.trial_balance(), (0, 0))

    def test_structural_errors(self):
        with self.assertRaises(InvalidPostingError, msg="1 行だけ"):
            self.ledger.post("x1", [Posting("psp_cash", debit=1)], t(1))
        with self.assertRaises(InvalidPostingError, msg="外部 ID なし"):
            self.ledger.post("", [Posting("psp_cash", debit=1), Posting("wallet:alice", credit=1)], t(1))
        with self.assertRaises(UnknownAccountError):
            self.ledger.post("x2", [Posting("psp_cash", debit=1), Posting("ghost", credit=1)], t(1))
        with self.assertRaises(InvalidPostingError, msg="タイムゾーンなし"):
            self.ledger.post("x3", [Posting("psp_cash", debit=1), Posting("wallet:alice", credit=1)],
                             datetime(2026, 4, 1, 12, 0))
        self.ledger.open_account("usd_cash", AccountType.ASSET, currency="USD")
        with self.assertRaises(CurrencyMismatchError):
            self.ledger.post("x4", [Posting("usd_cash", debit=1), Posting("wallet:alice", credit=1)], t(1))

    def test_no_negative_balance_for_designated_accounts(self):
        top_up(self.ledger, 10_000)
        purchase(self.ledger, 3_000, 90)
        with self.assertRaises(InsufficientBalanceError):
            purchase(self.ledger, 8_000, 240, external_id="order_2")
        self.assertEqual(self.ledger.balance("wallet:alice"), 7_000)
        self.assertEqual(self.ledger.balance("payable:shop1"), 2_910, "一部の口座だけが更新されてはいけない")
        purchase(self.ledger, 7_000, 210, external_id="order_3")
        self.assertEqual(self.ledger.balance("wallet:alice"), 0, "ちょうど 0 はよい")
        # 通常の口座（資産）はマイナスになってもよい（例: 立替）
        self.ledger.post("x5", [Posting("payable:shop1", debit=5_000), Posting("psp_cash", credit=15_000),
                                Posting("revenue:fees", debit=10_000)], t(3))
        self.assertEqual(self.ledger.balance("psp_cash"), -5_000)

    def test_idempotent_posting(self):
        first = top_up(self.ledger, 10_000)
        again = top_up(self.ledger, 10_000)
        self.assertTrue(again.duplicate)
        self.assertEqual(again.entry, first.entry)
        self.assertEqual(self.ledger.balance("wallet:alice"), 10_000, "決済代行の通知が 2 回届いても 1 回分")
        reordered = self.ledger.post("psp_evt_1", [Posting("wallet:alice", credit=10_000),
                                                   Posting("psp_cash", debit=10_000)], t(1), "チャージ")
        self.assertTrue(reordered.duplicate, "行の順序は問わない")
        with self.assertRaises(IdempotencyConflictError):
            top_up(self.ledger, 20_000)
        with self.assertRaises(IdempotencyConflictError):
            top_up(self.ledger, 10_000, at=t(1, 13))

    def test_append_only_in_time_order(self):
        top_up(self.ledger, 1_000, at=t(5))
        top_up(self.ledger, 1_000, external_id="same-time", at=t(5))  # 同時刻は可
        with self.assertRaises(OutOfOrderError):
            top_up(self.ledger, 1_000, external_id="late", at=t(4))


class TestExercise4ReversalAndHistory(unittest.TestCase):
    def setUp(self):
        self.ledger = make_ledger()
        top_up(self.ledger, 10_000, at=t(1))
        self.purchase = purchase(self.ledger, 3_000, 90, at=t(2)).entry

    def test_reverse(self):
        r = self.ledger.reverse(self.purchase.entry_id, "refund_1", t(3))
        self.assertFalse(r.duplicate)
        self.assertEqual(r.entry.reverses, self.purchase.entry_id)
        self.assertEqual(r.entry.description, "取消: shop1 での支払い")
        self.assertEqual(self.ledger.balance("wallet:alice"), 10_000)
        self.assertEqual(self.ledger.balance("payable:shop1"), 0)
        self.assertEqual(self.ledger.balance("revenue:fees"), 0)
        self.assertEqual(self.ledger.entry(self.purchase.entry_id), self.purchase, "元の仕訳は消えない")
        self.assertTrue(self.ledger.reverse(self.purchase.entry_id, "refund_1", t(4)).duplicate)
        with self.assertRaises(AlreadyReversedError):
            self.ledger.reverse(self.purchase.entry_id, "refund_2", t(4))
        with self.assertRaises(InvalidPostingError):
            self.ledger.reverse(r.entry.entry_id, "refund_3", t(4))
        with self.assertRaises(UnknownEntryError):
            self.ledger.reverse("je_999999", "refund_4", t(4))
        with self.assertRaises(IdempotencyConflictError):
            self.ledger.reverse("je_000001", "refund_1", t(4))

    def test_reversal_respects_negative_balance_rule(self):
        # チャージ 10,000 のうち 3,000 は使用済み。チャージそのものを取り消すと残高が負になる
        with self.assertRaises(InsufficientBalanceError):
            self.ledger.reverse("je_000001", "chargeback_1", t(3))
        self.assertEqual(self.ledger.balance("wallet:alice"), 7_000)

    def test_balance_as_of(self):
        self.ledger.reverse(self.purchase.entry_id, "refund_1", t(3))
        self.assertEqual(self.ledger.balance("wallet:alice", as_of=t(1, 11)), 0)
        self.assertEqual(self.ledger.balance("wallet:alice", as_of=t(1)), 10_000, "同時刻を含む")
        self.assertEqual(self.ledger.balance("wallet:alice", as_of=t(2, 18)), 7_000)
        self.assertEqual(self.ledger.balance("wallet:alice", as_of=t(30)), 10_000)
        self.assertEqual(self.ledger.balance("revenue:fees", as_of=t(2)), 90)

    def test_statement(self):
        self.ledger.post("combined", [Posting("wallet:alice", debit=500), Posting("wallet:alice", debit=500),
                                      Posting("payable:shop1", credit=1_000)], t(3))
        rows = self.ledger.statement("wallet:alice")
        self.assertEqual([(eid, delta, bal) for eid, _, delta, bal in rows], [
            ("je_000001", 10_000, 10_000),
            ("je_000002", -3_000, 7_000),
            ("je_000003", -1_000, 6_000),   # 同じ口座の 2 行は 1 件にまとめる
        ])
        self.assertEqual(rows[0][1], t(1))

    def test_concurrent_postings_keep_the_books_balanced(self):
        ledger = make_ledger()
        top_up(ledger, 100_000)
        errors = []

        def spend(n):
            def run():
                for i in range(50):
                    try:
                        purchase(ledger, 300, 9, external_id=f"order-{n}-{i}", at=t(2))
                    except InsufficientBalanceError:
                        pass
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)
            return run

        threads = [threading.Thread(target=spend(n)) for n in range(8)]
        for th in threads:
            th.start()
        for th in threads:
            th.join(10)
        self.assertEqual(errors, [])
        # 400 回 × 300 円 = 120,000 円 > 100,000 円: 残高を超えた分は拒否され、残高は負にならない
        self.assertEqual(ledger.balance("wallet:alice"), 100_000 - 300 * 333)
        self.assertEqual(ledger.balance("payable:shop1") + ledger.balance("revenue:fees"), 300 * 333)
        debits, credits = ledger.trial_balance()
        self.assertEqual(debits, credits)


if __name__ == "__main__":
    unittest.main()
