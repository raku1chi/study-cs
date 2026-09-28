"""8.2 演習3 — テストダブルのテスト

実行: python3 tools/check.py 8.2   （またはこのディレクトリで python3 -m unittest -v test_fakes）

構成:
  - RepositoryContract: リポジトリの「契約テスト」。本物（SQLite）と偽物（あなたの実装）の両方で実行する。
  - TestFakeClock / TestRecordingPaymentGateway: テスト用の時計・決済ゲートウェイの単体テスト。
  - TestSubscriptionService...: あなたの偽物を使って、SubscriptionService の更新・失効を検証する。
"""
import unittest
from datetime import datetime, timedelta, timezone

from fakes import Charge, FakeClock, InMemorySubscriptionRepository, RecordingPaymentGateway
from subscriptions import (
    ACTIVE,
    CANCELED,
    EXPIRED,
    PAST_DUE,
    DuplicateSubscriptionError,
    PaymentFailedError,
    SqliteSubscriptionRepository,
    Subscription,
    SubscriptionNotFoundError,
    SubscriptionService,
)

UTC = timezone.utc
JST = timezone(timedelta(hours=9))
T0 = datetime(2026, 4, 1, 9, 0, tzinfo=UTC)
DAY = timedelta(days=1)


def sub(sub_id, period_end, status=ACTIVE, user_id=None, plan="monthly", auto_renew=True, failed=0):
    return Subscription(sub_id, user_id or f"user-{sub_id}", plan, status, period_end, auto_renew, failed)


# ---------------------------------------------------------------------------
# 契約テスト: 本物と偽物で同じテストを実行する
# ---------------------------------------------------------------------------

class RepositoryContract:
    """make_repo() をサブクラスで定義すると、そのリポジトリに対して契約テストを実行する。"""

    def make_repo(self):
        raise NotImplementedError

    def setUp(self):
        self.repo = self.make_repo()

    def test_get_returns_what_was_added(self):
        s = sub("s1", T0, failed=2, auto_renew=False)
        self.repo.add(s)
        self.assertEqual(self.repo.get("s1"), s)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(self.repo.get("nope"))

    def test_add_duplicate_raises(self):
        self.repo.add(sub("s1", T0))
        with self.assertRaises(DuplicateSubscriptionError):
            self.repo.add(sub("s1", T0 + DAY))
        self.assertEqual(self.repo.get("s1").current_period_end, T0, "失敗した add は既存の値を変えない")

    def test_update_replaces_value(self):
        self.repo.add(sub("s1", T0))
        self.repo.update(sub("s1", T0 + 30 * DAY, status=PAST_DUE, failed=1))
        stored = self.repo.get("s1")
        self.assertEqual((stored.status, stored.current_period_end, stored.failed_attempts), (PAST_DUE, T0 + 30 * DAY, 1))

    def test_update_unknown_raises(self):
        with self.assertRaises(SubscriptionNotFoundError):
            self.repo.update(sub("ghost", T0))

    def test_stored_value_is_isolated_from_callers(self):
        original = sub("s1", T0)
        self.repo.add(original)
        original.status = CANCELED  # add に渡したオブジェクトを後から変更
        fetched = self.repo.get("s1")
        fetched.failed_attempts = 99  # get で受け取ったオブジェクトを変更
        stored = self.repo.get("s1")
        self.assertEqual(
            (stored.status, stored.failed_attempts), (ACTIVE, 0),
            "保存内容が呼び出し側の変更の影響を受けています（参照ではなくコピーを保存・返却すること）",
        )

    def test_list_due_filters_and_orders(self):
        self.repo.add(sub("b", T0 - DAY))
        self.repo.add(sub("a", T0 - DAY))  # b と同時刻 → id の昇順で a が先
        self.repo.add(sub("c", T0 - 2 * DAY, status=PAST_DUE))
        self.repo.add(sub("d", T0))  # ちょうど now → 含む
        self.repo.add(sub("e", T0 + timedelta(microseconds=1)))  # now より後 → 含まない
        self.repo.add(sub("f", T0 - DAY, status=EXPIRED))
        self.repo.add(sub("g", T0 - DAY, status=CANCELED))
        self.assertEqual([s.id for s in self.repo.list_due(T0)], ["c", "a", "b", "d"])

    def test_list_due_returns_copies(self):
        self.repo.add(sub("s1", T0))
        self.repo.list_due(T0)[0].status = EXPIRED
        self.assertEqual(self.repo.get("s1").status, ACTIVE)

    def test_naive_datetimes_are_rejected(self):
        naive = datetime(2026, 4, 1, 9, 0)
        with self.assertRaises(ValueError):
            self.repo.add(sub("s1", naive))
        self.repo.add(sub("s2", T0))
        with self.assertRaises(ValueError):
            self.repo.update(sub("s2", naive))
        with self.assertRaises(ValueError):
            self.repo.list_due(naive)

    def test_time_zones_are_compared_as_instants(self):
        in_jst = datetime(2026, 4, 1, 18, 0, tzinfo=JST)  # = 09:00 UTC = T0
        self.repo.add(sub("s1", in_jst))
        self.assertEqual(self.repo.get("s1").current_period_end, T0)
        self.assertEqual([s.id for s in self.repo.list_due(T0)], ["s1"])
        self.assertEqual(self.repo.list_due(T0 - timedelta(microseconds=1)), [])


class TestSqliteRepositoryContract(RepositoryContract, unittest.TestCase):
    def make_repo(self):
        repo = SqliteSubscriptionRepository(":memory:")
        self.addCleanup(repo.close)
        return repo


class TestInMemoryRepositoryContract(RepositoryContract, unittest.TestCase):
    def make_repo(self):
        return InMemorySubscriptionRepository()


# ---------------------------------------------------------------------------
# 時計と決済ゲートウェイ
# ---------------------------------------------------------------------------

class TestFakeClock(unittest.TestCase):
    def test_now_advance_and_set(self):
        clock = FakeClock(T0)
        self.assertEqual(clock.now(), T0)
        clock.advance(timedelta(days=30, seconds=5))
        self.assertEqual(clock.now(), T0 + timedelta(days=30, seconds=5))
        clock.set(T0 - DAY)
        self.assertEqual(clock.now(), T0 - DAY)
        clock.advance(timedelta(0))
        self.assertEqual(clock.now(), T0 - DAY)

    def test_rejects_naive_datetimes_and_going_backwards(self):
        with self.assertRaises(ValueError):
            FakeClock(datetime(2026, 4, 1))
        clock = FakeClock(T0)
        with self.assertRaises(ValueError):
            clock.set(datetime(2026, 4, 1))
        with self.assertRaises(ValueError):
            clock.advance(-DAY)
        self.assertEqual(clock.now(), T0)


class TestRecordingPaymentGateway(unittest.TestCase):
    def test_records_calls_and_returns_configured_results(self):
        gateway = RecordingPaymentGateway(declined_users=["bob"])
        self.assertTrue(gateway.charge("alice", 980, "k1"))
        self.assertFalse(gateway.charge("bob", 980, "k2"))
        self.assertEqual(gateway.charges, [Charge("alice", 980, "k1"), Charge("bob", 980, "k2")])

    def test_declined_users_can_change_during_a_test(self):
        gateway = RecordingPaymentGateway(declined_users={"bob"})
        self.assertFalse(gateway.charge("bob", 980, "k1"))
        gateway.declined_users.discard("bob")  # カードを更新した
        self.assertTrue(gateway.charge("bob", 980, "k2"))
        self.assertEqual(len(gateway.charges), 2)


# ---------------------------------------------------------------------------
# 偽物を使った SubscriptionService のテスト
# ---------------------------------------------------------------------------

class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(T0)
        self.repo = InMemorySubscriptionRepository()
        self.payments = RecordingPaymentGateway()
        self.service = SubscriptionService(self.repo, self.payments, self.clock)


class TestSubscriptionServiceSubscribe(ServiceTestCase):
    def test_subscribe_charges_first_period_and_stores_active(self):
        s = self.service.subscribe("s1", "alice", "monthly")
        self.assertEqual(self.payments.charges, [Charge("alice", 980, "s1:initial")])
        self.assertEqual(self.repo.get("s1"), s)
        self.assertEqual((s.status, s.current_period_end), (ACTIVE, T0 + 30 * DAY))

    def test_declined_card_stores_nothing(self):
        self.payments.declined_users.add("alice")
        with self.assertRaises(PaymentFailedError):
            self.service.subscribe("s1", "alice", "monthly")
        self.assertIsNone(self.repo.get("s1"))

    def test_yearly_plan(self):
        s = self.service.subscribe("s1", "alice", "yearly")
        self.assertEqual(self.payments.charges[0].amount, 9800)
        self.assertEqual(s.current_period_end, T0 + 365 * DAY)


class TestSubscriptionServiceRenewal(ServiceTestCase):
    def setUp(self):
        super().setUp()
        self.service.subscribe("s1", "alice", "monthly")
        self.end = T0 + 30 * DAY

    def test_nothing_happens_before_period_end(self):
        self.clock.set(self.end - timedelta(seconds=1))
        self.assertEqual(self.service.process_due(), [])
        self.assertEqual(len(self.payments.charges), 1)

    def test_renews_exactly_at_period_end(self):
        self.clock.set(self.end)
        self.assertEqual(self.service.process_due(), [("s1", "renewed")])
        renewal = self.payments.charges[-1]
        self.assertEqual((renewal.user_id, renewal.amount), ("alice", 980))
        self.assertTrue(renewal.idempotency_key.startswith("s1:"))
        self.assertEqual(self.repo.get("s1").current_period_end, self.end + 30 * DAY)

    def test_canceled_subscription_expires_without_charging(self):
        self.service.cancel("s1")
        self.clock.set(self.end)
        self.assertEqual(self.service.process_due(), [("s1", "expired")])
        self.assertEqual(len(self.payments.charges), 1, "解約予約済みなら更新の課金はしない")
        self.assertEqual(self.repo.get("s1").status, EXPIRED)

    def test_recovers_after_failed_payment_without_free_days(self):
        self.payments.declined_users.add("alice")
        self.clock.set(self.end)
        self.assertEqual(self.service.process_due(), [("s1", "payment_failed")])
        self.assertEqual(self.repo.get("s1").status, PAST_DUE)
        self.payments.declined_users.clear()
        self.clock.advance(DAY)
        self.assertEqual(self.service.process_due(), [("s1", "renewed")])
        renewed = self.repo.get("s1")
        self.assertEqual(renewed.status, ACTIVE)
        self.assertEqual(renewed.failed_attempts, 0)
        self.assertEqual(renewed.current_period_end, self.end + 30 * DAY, "次の期間は、支払った日ではなく元の期限から数える")

    def test_expires_after_max_failed_attempts(self):
        self.payments.declined_users.add("alice")
        events = []
        for day in range(3):
            self.clock.set(self.end + day * DAY)
            events += self.service.process_due()
        self.assertEqual(events, [("s1", "payment_failed"), ("s1", "payment_failed"), ("s1", "expired")])
        self.clock.advance(DAY)
        self.assertEqual(self.service.process_due(), [], "失効したものは処理しない")

    def test_expires_when_grace_period_is_over(self):
        self.payments.declined_users.add("alice")
        self.clock.set(self.end)
        self.service.process_due()
        self.clock.set(self.end + 3 * DAY)  # 猶予期間（3 日）が終わった後の最初の実行
        self.assertEqual(self.service.process_due(), [("s1", "expired")])

    def test_processes_multiple_subscriptions_in_due_order(self):
        self.clock.set(T0 + DAY)
        self.service.subscribe("s0", "bob", "monthly")  # s1 より 1 日遅い期限
        self.clock.set(self.end + 5 * DAY)
        self.assertEqual(self.service.process_due(), [("s1", "renewed"), ("s0", "renewed")])


if __name__ == "__main__":
    unittest.main()
