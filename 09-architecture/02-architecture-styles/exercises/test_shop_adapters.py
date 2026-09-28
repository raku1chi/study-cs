"""9.2 アーキテクチャスタイル — 演習2・4 のテスト（アダプタと契約テスト）

OrderRepositoryContract は、OrderRepository ポートの「契約」をテストにしたものです。
同じテストを InMemoryOrderRepository（演習2）と SqliteOrderRepository（演習4）の両方に実行します。

実行: python3 tools/check.py 9.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from shop_adapters import (
    FakePaymentGateway,
    FixedClock,
    InMemoryCatalog,
    InMemoryEventPublisher,
    InMemoryOrderRepository,
    SequentialIds,
    SqliteOrderRepository,
)
from shop_domain import (
    ConcurrencyError,
    DuplicateOrderError,
    Order,
    OrderLine,
    OrderNotFoundError,
    OrderService,
    OrderStatus,
    PaymentDeclinedError,
    PlaceOrderCommand,
)

T0 = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
JST = timezone(timedelta(hours=9))


def make_order(n=1, customer="c1", request_id=None, at=T0):
    return Order.place(
        f"ord_{n:04d}", customer, request_id or f"req_{n}",
        [OrderLine("BOOK", 2, 1500), OrderLine("PEN", 3, 200)], at,
    )


class OrderRepositoryContract:
    """リポジトリの契約テスト。サブクラスで make_repo() を実装し、unittest.TestCase と組み合わせる。"""

    def make_repo(self):
        raise NotImplementedError

    def setUp(self):
        self.repo = self.make_repo()

    def test_add_then_get_round_trip(self):
        order = make_order()
        self.repo.add(order)
        self.assertEqual(order.version, 1, "add に成功したら version は 1")
        loaded = self.repo.get("ord_0001")
        self.assertEqual(loaded, order)
        self.assertIsNot(loaded, order)
        self.assertEqual(loaded.lines, (OrderLine("BOOK", 2, 1500), OrderLine("PEN", 3, 200)))
        self.assertEqual(loaded.created_at, T0)
        self.assertEqual(loaded.created_at.utcoffset(), timedelta(0), "タイムゾーンの情報を保つ")
        self.assertIs(loaded.status, OrderStatus.PENDING_PAYMENT)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(self.repo.get("missing"))
        self.assertIsNone(self.repo.find_by_request_id("missing"))

    def test_duplicate_order_id_or_request_id_is_rejected(self):
        self.repo.add(make_order(1))
        with self.assertRaises(DuplicateOrderError):
            self.repo.add(make_order(1, request_id="another_request"))
        with self.assertRaises(DuplicateOrderError):
            dup = make_order(2, request_id="req_1")
            self.repo.add(dup)
        self.assertEqual([o.order_id for o in self.repo.list_by_customer("c1")], ["ord_0001"],
                         "失敗した add は何も保存しない")
        self.assertIsNone(self.repo.get("ord_0002"))

    def test_returned_objects_are_independent_copies(self):
        order = make_order()
        self.repo.add(order)
        order.mark_paid("pay_x")  # add に渡したオブジェクトを変更しても…
        loaded = self.repo.get("ord_0001")
        self.assertIs(loaded.status, OrderStatus.PENDING_PAYMENT, "…保存済みの状態は変わらない")
        loaded.cancel()  # 取り出したオブジェクトを変更しても…
        self.assertIs(self.repo.get("ord_0001").status, OrderStatus.PENDING_PAYMENT, "…save するまで変わらない")

    def test_save_updates_state_and_version(self):
        self.repo.add(make_order())
        order = self.repo.get("ord_0001")
        order.mark_paid("pay_0001")
        self.repo.save(order)
        self.assertEqual(order.version, 2)
        loaded = self.repo.get("ord_0001")
        self.assertEqual((loaded.status, loaded.payment_id, loaded.version), (OrderStatus.PAID, "pay_0001", 2))

        failed = make_order(2)
        self.repo.add(failed)
        failed.mark_payment_failed("カードが利用できません")
        self.repo.save(failed)
        self.assertEqual(self.repo.get("ord_0002").failure_reason, "カードが利用できません")

    def test_save_unknown_order(self):
        with self.assertRaises(OrderNotFoundError):
            self.repo.save(make_order(9))

    def test_optimistic_locking(self):
        self.repo.add(make_order())
        a = self.repo.get("ord_0001")
        b = self.repo.get("ord_0001")
        a.mark_paid("pay_a")
        self.repo.save(a)            # 先に保存した方が勝つ
        b.cancel()
        with self.assertRaises(ConcurrencyError):
            self.repo.save(b)        # 古い版に基づく更新は拒否される
        loaded = self.repo.get("ord_0001")
        self.assertEqual((loaded.status, loaded.version), (OrderStatus.PAID, 2), "負けた側の変更は反映されない")
        self.assertEqual(b.version, 1, "失敗した save は version を変えない")

        # 最新の版を読み直せば、再び更新できる
        c = self.repo.get("ord_0001")
        self.repo.save(c)
        self.assertEqual(self.repo.get("ord_0001").version, 3)

    def test_find_by_request_id(self):
        self.repo.add(make_order(1, request_id="client-abc"))
        found = self.repo.find_by_request_id("client-abc")
        self.assertEqual(found.order_id, "ord_0001")

    def test_list_by_customer_is_filtered_and_ordered(self):
        self.repo.add(make_order(3, at=T0 + timedelta(minutes=5)))
        self.repo.add(make_order(1, at=T0 + timedelta(minutes=5)))
        self.repo.add(make_order(2, at=T0))
        self.repo.add(make_order(4, customer="other"))
        # 同じ時刻を別のタイムゾーンで表したもの（09:02 UTC = 18:02 JST）
        self.repo.add(make_order(5, at=datetime(2026, 4, 1, 18, 2, tzinfo=JST)))
        got = [o.order_id for o in self.repo.list_by_customer("c1")]
        self.assertEqual(got, ["ord_0002", "ord_0005", "ord_0001", "ord_0003"])
        self.assertEqual(self.repo.list_by_customer("nobody"), [])


class TestInMemoryOrderRepository(OrderRepositoryContract, unittest.TestCase):
    def make_repo(self):
        return InMemoryOrderRepository()


class TestSqliteOrderRepository(OrderRepositoryContract, unittest.TestCase):
    def make_repo(self):
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        return SqliteOrderRepository(self.conn)

    def test_failed_add_leaves_no_orphan_lines(self):
        self.repo.add(make_order(1))
        with self.assertRaises(DuplicateOrderError):
            self.repo.add(make_order(2, request_id="req_1"))
        (count,) = self.conn.execute("SELECT COUNT(*) FROM order_lines WHERE order_id = 'ord_0002'").fetchone()
        self.assertEqual(count, 0, "注文と明細は同じトランザクションで保存する")

    def test_data_survives_a_new_connection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shop.sqlite3"
            conn1 = sqlite3.connect(path)
            SqliteOrderRepository(conn1).add(make_order())
            conn1.close()
            conn2 = sqlite3.connect(path)
            try:
                self.assertEqual(SqliteOrderRepository(conn2).get("ord_0001").total, 3600)
            finally:
                conn2.close()

    def test_version_check_is_done_by_the_database(self):
        # 別の接続（別のプロセスのつもり）から更新されても、楽観的ロックが効くこと
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "shop.sqlite3"
            conn1, conn2 = sqlite3.connect(path), sqlite3.connect(path)
            try:
                repo1, repo2 = SqliteOrderRepository(conn1), SqliteOrderRepository(conn2)
                repo1.add(make_order())
                mine, theirs = repo1.get("ord_0001"), repo2.get("ord_0001")
                theirs.cancel()
                repo2.save(theirs)
                mine.mark_paid("pay_1")
                with self.assertRaises(ConcurrencyError):
                    repo1.save(mine)
                self.assertIs(repo1.get("ord_0001").status, OrderStatus.CANCELLED)
            finally:
                conn1.close()
                conn2.close()


class TestExercise2FakePaymentGateway(unittest.TestCase):
    def test_charges_are_recorded_with_sequential_ids(self):
        gw = FakePaymentGateway()
        self.assertEqual(gw.charge("c1", 1000, "k1"), "pay_0001")
        self.assertEqual(gw.charge("c2", 500, "k2"), "pay_0002")
        self.assertEqual([(c.idempotency_key, c.amount) for c in gw.charges], [("k1", 1000), ("k2", 500)])
        self.assertEqual(gw.calls, 2)

    def test_same_key_does_not_charge_twice(self):
        gw = FakePaymentGateway()
        first = gw.charge("c1", 1000, "k1")
        self.assertEqual(gw.charge("c1", 1000, "k1"), first)
        self.assertEqual(len(gw.charges), 1)
        self.assertEqual(gw.calls, 2)
        with self.assertRaises(ValueError, msg="同じキーで金額が違うのは誤用"):
            gw.charge("c1", 2000, "k1")

    def test_declines(self):
        gw = FakePaymentGateway(declined_customers={"bad"}, limit=10_000)
        with self.assertRaises(PaymentDeclinedError):
            gw.charge("bad", 100, "k1")
        with self.assertRaises(PaymentDeclinedError):
            gw.charge("c1", 10_001, "k2")
        self.assertEqual(gw.charge("c1", 10_000, "k3"), "pay_0001")
        self.assertEqual(len(gw.charges), 1, "拒否された課金は記録しない")

    def test_fail_after_charge_once(self):
        gw = FakePaymentGateway(fail_after_charge_once=True)
        with self.assertRaises(TimeoutError):
            gw.charge("c1", 1000, "k1")
        self.assertEqual(len(gw.charges), 1, "課金は記録されている（応答だけが失われた）")
        self.assertFalse(gw.fail_after_charge_once)
        self.assertEqual(gw.charge("c1", 1000, "k1"), "pay_0001")


class TestEndToEndWithSqlite(unittest.TestCase):
    """アダプタを差し替えるだけで、同じユースケースが SQLite の上で動くこと。"""

    def test_place_order_on_sqlite(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        repo = SqliteOrderRepository(conn)
        gateway = FakePaymentGateway(fail_after_charge_once=True)
        events = InMemoryEventPublisher()
        service = OrderService(repo, InMemoryCatalog({"BOOK": 1500}), gateway, FixedClock(T0), events,
                               SequentialIds())
        command = PlaceOrderCommand("req_1", "c1", (("BOOK", 2),))
        with self.assertRaises(TimeoutError):
            service.place_order(command)
        summary = service.place_order(command)
        self.assertEqual((summary.status, summary.total), ("paid", 3000))
        self.assertEqual(repo.get(summary.order_id).version, 2)
        self.assertEqual(len(gateway.charges), 1)
        self.assertEqual(len(events.events), 1)


if __name__ == "__main__":
    unittest.main()
