"""9.2 アーキテクチャスタイル — 演習3 のテスト（アプリケーションサービス）

アプリケーションサービスを、インメモリのアダプタ（演習2）と組み合わせてテストします。
DB も決済代行も本物は使いませんが、ポートを通しているので、本番とまったく同じコードが動きます。

実行: python3 tools/check.py 9.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from datetime import datetime, timezone

from shop_adapters import (
    FakePaymentGateway,
    FixedClock,
    InMemoryCatalog,
    InMemoryEventPublisher,
    InMemoryOrderRepository,
    SequentialIds,
)
from shop_domain import (
    InvalidOrderError,
    InvalidStateError,
    Order,
    OrderLine,
    OrderNotFoundError,
    OrderPlaced,
    OrderService,
    OrderStatus,
    OrderSummary,
    PlaceOrderCommand,
)

T0 = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)


def cmd(request_id="req_1", customer="c1", items=(("BOOK", 2), ("PEN", 3))):
    return PlaceOrderCommand(request_id, customer, tuple(items))


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = InMemoryOrderRepository()
        self.catalog = InMemoryCatalog({"BOOK": 1500, "PEN": 200, "FREE": 0})
        self.gateway = FakePaymentGateway()
        self.clock = FixedClock(T0)
        self.events = InMemoryEventPublisher()
        self.service = OrderService(self.repo, self.catalog, self.gateway, self.clock, self.events, SequentialIds())


class TestExercise3PlaceOrder(ServiceTestCase):
    def test_happy_path(self):
        summary = self.service.place_order(cmd())
        self.assertEqual(summary, OrderSummary("ord_0001", "paid", 3600, "pay_0001", None))
        self.assertEqual([(c.idempotency_key, c.customer_id, c.amount) for c in self.gateway.charges],
                         [("ord_0001", "c1", 3600)], "冪等キーには注文 ID を使う")
        self.assertEqual(self.events.events, [OrderPlaced("ord_0001", "c1", 3600, T0)])
        stored = self.repo.get("ord_0001")
        self.assertEqual(stored.status, OrderStatus.PAID)
        self.assertEqual(stored.version, 2, "add で 1、支払い結果の save で 2")

    def test_prices_come_from_the_catalog(self):
        with self.assertRaises(InvalidOrderError):
            self.service.place_order(cmd(items=(("BOOK", 1), ("UNKNOWN", 1))))
        with self.assertRaises(InvalidOrderError):
            self.service.place_order(cmd(request_id="req_2", items=(("FREE", 1),)))
        self.assertEqual(self.repo.list_by_customer("c1"), [], "不正な注文は保存しない")
        self.assertEqual(self.gateway.calls, 0, "不正な注文では課金しない")

    def test_declined_payment_is_recorded_not_raised(self):
        self.gateway.declined_customers.add("c1")
        summary = self.service.place_order(cmd())
        self.assertEqual(summary.status, "payment_failed")
        self.assertTrue(summary.failure_reason)
        self.assertEqual(self.repo.get(summary.order_id).status, OrderStatus.PAYMENT_FAILED)
        self.assertEqual(self.events.events, [], "失敗した注文ではイベントを出さない")

    def test_retry_with_same_request_id_is_idempotent(self):
        first = self.service.place_order(cmd())
        again = self.service.place_order(cmd())
        self.assertEqual(first, again)
        self.assertEqual(self.gateway.calls, 1, "再送では課金を呼ばない")
        self.assertEqual(len(self.events.events), 1)
        self.assertEqual(len(self.repo.list_by_customer("c1")), 1)

        self.gateway.declined_customers.add("c2")
        failed = self.service.place_order(cmd(request_id="req_x", customer="c2"))
        self.assertEqual(self.service.place_order(cmd(request_id="req_x", customer="c2")), failed,
                         "失敗した結果も、同じ request_id なら同じ結果を返す")

    def test_resume_after_timeout_does_not_double_charge(self):
        # 決済代行では課金されたのに、応答がタイムアウトで届かなかった
        self.gateway.fail_after_charge_once = True
        with self.assertRaises(TimeoutError):
            self.service.place_order(cmd())
        self.assertEqual(self.repo.get("ord_0001").status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(self.events.events, [])

        # クライアントが同じ request_id で再送 → 同じ冪等キーで課金をやり直し、完了させる
        summary = self.service.place_order(cmd())
        self.assertEqual((summary.order_id, summary.status, summary.payment_id), ("ord_0001", "paid", "pay_0001"))
        self.assertEqual(len(self.gateway.charges), 1, "決済代行側の課金は 1 回だけ")
        self.assertEqual(self.gateway.calls, 2)
        self.assertEqual(len(self.events.events), 1)

    def test_concurrent_duplicate_joins_the_winner(self):
        class RacyRepository(InMemoryOrderRepository):
            """最初の find_by_request_id の直後に、別のリクエストが同じ request_id で保存した状況を再現する。"""

            def __init__(self):
                super().__init__()
                self.first_lookup = True

            def find_by_request_id(self, request_id):
                if self.first_lookup:
                    self.first_lookup = False
                    winner = Order.place("ord_winner", "c1", request_id, [OrderLine("BOOK", 1, 1500)], T0)
                    winner.mark_paid("pay_winner")
                    super().add(winner)
                    return None
                return super().find_by_request_id(request_id)

        repo = RacyRepository()
        service = OrderService(repo, self.catalog, self.gateway, self.clock, self.events, SequentialIds())
        summary = service.place_order(cmd())
        self.assertEqual((summary.order_id, summary.status), ("ord_winner", "paid"))
        self.assertEqual(self.gateway.calls, 0, "先に処理した側の結果に合流し、課金しない")
        self.assertEqual(len(repo.list_by_customer("c1")), 1)

    def test_uses_clock_for_created_at(self):
        self.clock.advance(3600)
        summary = self.service.place_order(cmd())
        self.assertEqual(self.repo.get(summary.order_id).created_at, datetime(2026, 4, 1, 10, 0, tzinfo=timezone.utc))


class TestExercise3CancelOrder(ServiceTestCase):
    def test_cancel_failed_order(self):
        self.gateway.declined_customers.add("c1")
        summary = self.service.place_order(cmd())
        cancelled = self.service.cancel_order(summary.order_id)
        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(self.repo.get(summary.order_id).status, OrderStatus.CANCELLED)

    def test_cannot_cancel_paid_or_unknown(self):
        summary = self.service.place_order(cmd())
        with self.assertRaises(InvalidStateError):
            self.service.cancel_order(summary.order_id)
        self.assertEqual(self.repo.get(summary.order_id).status, OrderStatus.PAID)
        with self.assertRaises(OrderNotFoundError):
            self.service.cancel_order("nope")


if __name__ == "__main__":
    unittest.main()
