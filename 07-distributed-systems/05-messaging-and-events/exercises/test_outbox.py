"""7.5 メッセージングとイベント駆動 — Transactional Outbox と冪等なコンシューマのテスト

実行: python3 tools/check.py 7.5   （またはこのディレクトリで python3 -m unittest -v test_outbox）

データベースは一時ディレクトリの SQLite ファイルを使います。接続を開き直すことで、プロセスの再起動を模擬します。
"""
import json
import os
import random
import sqlite3
import tempfile
import unittest

from outbox import (
    FakeBroker,
    IdempotentConsumer,
    OutboxRelay,
    SimulatedCrash,
    init_consumer_db,
    init_producer_db,
    place_order,
    place_order_dual_write,
)


class DbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.producer_path = os.path.join(self.tmp.name, "orders.db")
        self.consumer_path = os.path.join(self.tmp.name, "billing.db")
        self.conns = []
        self.db = self.connect(self.producer_path)
        init_producer_db(self.db)
        self.consumer_db = self.connect(self.consumer_path)
        init_consumer_db(self.consumer_db)
        self.broker = FakeBroker()

    def connect(self, path):
        conn = sqlite3.connect(path)
        self.conns.append(conn)
        return conn

    def tearDown(self):
        for conn in self.conns:
            conn.close()
        self.tmp.cleanup()

    def count(self, conn, sql):
        return conn.execute(sql).fetchone()[0]


class TestExercise4PlaceOrder(DbTestCase):
    def test_order_and_event_are_written_together(self):
        event_id = place_order(self.db, "o-1", "alice", 1200)
        self.assertEqual(self.db.execute("SELECT id, customer, amount FROM orders").fetchall(), [("o-1", "alice", 1200)])
        row = self.db.execute("SELECT event_id, event_type, aggregate_id, payload, published_at FROM outbox").fetchone()
        self.assertEqual(row[:3], (event_id, "OrderPlaced", "o-1"))
        self.assertEqual(json.loads(row[3]), {"order_id": "o-1", "customer": "alice", "amount": 1200})
        self.assertIsNone(row[4], "まだ送信していない")
        self.assertEqual(len(event_id), 36, "既定のイベント ID は UUID の文字列")

    def test_explicit_event_id(self):
        self.assertEqual(place_order(self.db, "o-1", "alice", 100, event_id="evt-1"), "evt-1")

    def test_failure_after_order_insert_rolls_back_everything(self):
        place_order(self.db, "o-1", "alice", 100, event_id="evt-1")
        with self.assertRaises(sqlite3.IntegrityError):
            place_order(self.db, "o-2", "bob", 200, event_id="evt-1")  # outbox の INSERT で失敗する
        self.assertEqual(self.count(self.db, "SELECT COUNT(*) FROM orders WHERE id = 'o-2'"), 0, "注文も残らない")
        self.assertEqual(self.count(self.db, "SELECT COUNT(*) FROM outbox"), 1)

    def test_invalid_order_writes_nothing(self):
        for args in (("o-1", "alice", 0), ("o-1", "alice", -5)):
            with self.assertRaises(sqlite3.IntegrityError):
                place_order(self.db, *args)
        place_order(self.db, "o-1", "alice", 100)
        with self.assertRaises(sqlite3.IntegrityError):
            place_order(self.db, "o-1", "alice", 100)  # 同じ注文 ID
        self.assertEqual(self.count(self.db, "SELECT COUNT(*) FROM outbox"), 1)

    def test_dual_write_can_lose_events(self):
        # 比較用の悪い例（実装済み）: コミットの後、送信の前に落ちると、イベントが失われる
        with self.assertRaises(SimulatedCrash):
            place_order_dual_write(self.db, self.broker, "o-1", "alice", 100, crash_before_publish=True)
        self.assertEqual(self.count(self.db, "SELECT COUNT(*) FROM orders"), 1)
        self.assertEqual(self.broker.messages, [], "注文はあるのに、誰にも知らされない")


class TestExercise5Relay(DbTestCase):
    def test_publishes_in_order_and_marks_published(self):
        ids = [place_order(self.db, f"o-{i}", "alice", 100 + i) for i in range(5)]
        relay = OutboxRelay(self.db, self.broker, clock=lambda: 1234.5)
        self.assertEqual(relay.pending(), 5)
        self.assertEqual(relay.run_once(), 5)
        self.assertEqual([m["event_id"] for m in self.broker.messages], ids)
        self.assertEqual(
            self.broker.messages[0],
            {"event_id": ids[0], "event_type": "OrderPlaced", "aggregate_id": "o-0",
             "payload": {"order_id": "o-0", "customer": "alice", "amount": 100}},
        )
        self.assertEqual(relay.pending(), 0)
        self.assertEqual(self.count(self.db, "SELECT COUNT(*) FROM outbox WHERE published_at = 1234.5"), 5)
        self.assertEqual(relay.run_once(), 0, "送信済みは送らない")

    def test_batch_size(self):
        for i in range(5):
            place_order(self.db, f"o-{i}", "alice", 100)
        relay = OutboxRelay(self.db, self.broker)
        self.assertEqual(relay.run_once(batch_size=2), 2)
        self.assertEqual(relay.pending(), 3)

    def test_broker_failure_stops_and_retries_later_in_order(self):
        ids = [place_order(self.db, f"o-{i}", "alice", 100) for i in range(4)]
        relay = OutboxRelay(self.db, self.broker)
        self.broker.fail_next(1)
        self.assertEqual(relay.run_once(), 0, "最初の送信で失敗したら、そこで止める（順序を守る）")
        self.assertEqual(relay.pending(), 4)
        self.assertEqual(relay.run_once(), 4)
        self.assertEqual([m["event_id"] for m in self.broker.messages], ids)

    def test_crash_between_publish_and_mark_causes_duplicate(self):
        ids = [place_order(self.db, f"o-{i}", "alice", 100) for i in range(3)]
        crashing = OutboxRelay(self.db, self.broker, crash_after_publish=lambda eid: eid == ids[1])
        with self.assertRaises(SimulatedCrash):
            crashing.run_once()
        self.assertEqual([m["event_id"] for m in self.broker.messages], ids[:2])
        # プロセスを再起動した想定: 新しい接続と新しいリレー
        restarted = OutboxRelay(self.connect(self.producer_path), self.broker)
        self.assertEqual(restarted.pending(), 2, "ids[1] は送信したが、送信済みの記録はない")
        self.assertEqual(restarted.run_once(), 2)
        self.assertEqual([m["event_id"] for m in self.broker.messages], [ids[0], ids[1], ids[1], ids[2]])


class TestExercise6IdempotentConsumer(DbTestCase):
    def deliver_all(self, consumer):
        return [consumer.handle(m) for m in self.broker.messages]

    def test_duplicates_are_processed_once(self):
        ids = [place_order(self.db, f"o-{i}", "alice", 1000) for i in range(3)]
        relay = OutboxRelay(self.db, self.broker, crash_after_publish=lambda eid: eid == ids[0])
        with self.assertRaises(SimulatedCrash):
            relay.run_once()
        OutboxRelay(self.connect(self.producer_path), self.broker).run_once()
        consumer = IdempotentConsumer(self.consumer_db, clock=lambda: 1.0)
        self.assertEqual(self.deliver_all(consumer), [True, False, True, True])
        self.assertEqual(consumer.totals("alice"), (3000, 3), "重複した注文を二重に数えない")
        self.assertEqual(self.count(self.consumer_db, "SELECT COUNT(*) FROM processed_messages"), 3)
        self.assertIsNone(consumer.totals("nobody"))

    def test_failure_in_handler_rolls_back_and_can_be_retried(self):
        place_order(self.db, "o-1", "bob", 500)
        OutboxRelay(self.db, self.broker).run_once()
        message = self.broker.messages[0]

        def boom(msg):
            raise RuntimeError("処理の途中で落ちた")

        with self.assertRaises(RuntimeError):
            IdempotentConsumer(self.consumer_db, fail_hook=boom).handle(message)
        self.assertEqual(self.count(self.consumer_db, "SELECT COUNT(*) FROM processed_messages"), 0, "記録も取り消される")
        self.assertIsNone(IdempotentConsumer(self.consumer_db).totals("bob"), "効果も取り消される")
        consumer = IdempotentConsumer(self.consumer_db)
        self.assertTrue(consumer.handle(message), "再配送されれば、今度は処理される")
        self.assertEqual(consumer.totals("bob"), (500, 1))

    def test_unknown_event_types_are_recorded_but_have_no_effect(self):
        consumer = IdempotentConsumer(self.consumer_db)
        msg = {"event_id": "e-9", "event_type": "OrderShipped", "aggregate_id": "o-9", "payload": {}}
        self.assertTrue(consumer.handle(msg))
        self.assertFalse(consumer.handle(msg))
        self.assertEqual(self.count(self.consumer_db, "SELECT COUNT(*) FROM customer_totals"), 0)

    def test_end_to_end_effectively_once_under_random_failures(self):
        rng = random.Random(5)
        expected: dict[str, int] = {}
        conn = self.db
        for i in range(60):
            customer = rng.choice(["alice", "bob", "carol"])
            amount = rng.randrange(100, 1000)
            place_order(conn, f"o-{i}", customer, amount)
            expected[customer] = expected.get(customer, 0) + amount
            if rng.random() < 0.3:
                self.broker.fail_next(rng.randrange(1, 3))
            relay = OutboxRelay(conn, self.broker, crash_after_publish=lambda eid: rng.random() < 0.1)
            try:
                relay.run_once(batch_size=rng.randrange(1, 5))
            except SimulatedCrash:
                conn = self.connect(self.producer_path)  # 再起動
        while OutboxRelay(conn, self.broker).pending():
            OutboxRelay(conn, self.broker).run_once()
        consumer = IdempotentConsumer(self.consumer_db)
        deliveries = list(self.broker.messages)
        deliveries += rng.sample(deliveries, 20)  # ブローカー側の再配送も混ぜる
        rng.shuffle(deliveries)
        for m in deliveries:
            consumer.handle(m)
        self.assertGreater(len(self.broker.messages), 60, "リレーの再起動で重複が発生している")
        for customer, total in expected.items():
            self.assertEqual(consumer.totals(customer)[0], total, customer)
        self.assertEqual(sum(consumer.totals(c)[1] for c in expected), 60, "すべての注文をちょうど 1 回ずつ処理")


if __name__ == "__main__":
    unittest.main()
