"""9.3 ドメイン駆動設計とモジュール分割 — 演習1・2 のテスト

実行: python3 tools/check.py 9.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import dataclasses
import unittest
from datetime import date, datetime, timedelta, timezone

from reservation_domain import (
    BookingWindowError,
    CancellationPolicy,
    CapacityError,
    DoubleBookingError,
    DuplicateReservationError,
    GuestsSeated,
    InvalidTransitionError,
    InvalidValueError,
    Money,
    PartySize,
    ReservationBooked,
    ReservationCancelled,
    ReservationCompleted,
    ReservationMarkedNoShow,
    ReservationNotFoundError,
    ReservationRescheduled,
    ReservationStatus,
    Table,
    TableSchedule,
    TimeSlot,
    default_policy,
)

JST = timezone(timedelta(hours=9))
DAY = date(2026, 3, 15)


def at(hour, minute=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=JST)


def slot(hour, minute=0, minutes=90, day=DAY):
    return TimeSlot(at(hour, minute, day), minutes)


# ---------------------------------------------------------------------------
# 演習1: 値オブジェクト
# ---------------------------------------------------------------------------

class TestExercise1PartySize(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertEqual(PartySize(1).value, 1)
        self.assertEqual(PartySize(20).value, 20)
        for bad in (0, 21, -1, True, "4", 2.0, None):
            with self.assertRaises(InvalidValueError, msg=repr(bad)):
                PartySize(bad)

    def test_value_semantics(self):
        self.assertEqual(PartySize(4), PartySize(4))
        self.assertEqual(hash(PartySize(4)), hash(PartySize(4)))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            PartySize(4).value = 5

    def test_invalid_value_error_is_also_value_error(self):
        with self.assertRaises(ValueError):
            PartySize(0)


class TestExercise1TimeSlot(unittest.TestCase):
    def test_valid_slot_and_end(self):
        s = slot(18, 30, 90)
        self.assertEqual(s.end, at(20, 0))

    def test_rejects_naive_datetime(self):
        with self.assertRaises(InvalidValueError):
            TimeSlot(datetime(2026, 3, 15, 18, 0), 90)

    def test_rejects_unaligned_start_and_bad_duration(self):
        with self.assertRaises(InvalidValueError):
            TimeSlot(at(18, 10), 90)
        with self.assertRaises(InvalidValueError):
            TimeSlot(at(18, 0).replace(second=30), 90)
        for minutes in (15, 20, 100, 255, 0, True, 90.0):
            with self.assertRaises(InvalidValueError, msg=repr(minutes)):
                TimeSlot(at(18, 0), minutes)
        self.assertEqual(TimeSlot(at(18, 0), 30).minutes, 30)
        self.assertEqual(TimeSlot(at(18, 0), 240).minutes, 240)

    def test_overlaps_is_half_open(self):
        a = slot(18, 0, 90)             # 18:00〜19:30
        self.assertFalse(a.overlaps(slot(19, 30, 90)), "終わりと始まりが接しているだけなら重ならない")
        self.assertFalse(slot(19, 30, 90).overlaps(a))
        self.assertTrue(a.overlaps(slot(19, 15, 60)))
        self.assertTrue(a.overlaps(slot(17, 0, 75)))
        self.assertTrue(a.overlaps(slot(18, 30, 30)), "内側に含まれる")
        self.assertTrue(slot(17, 0, 240).overlaps(a), "外側から包む")
        self.assertFalse(a.overlaps(slot(16, 30, 90)))

    def test_same_instant_in_other_timezone_is_equal_time(self):
        utc_slot = TimeSlot(datetime(2026, 3, 15, 9, 0, tzinfo=timezone.utc), 90)  # = 18:00 JST
        self.assertTrue(utc_slot.overlaps(slot(19, 0, 60)))


class TestExercise1Money(unittest.TestCase):
    def test_arithmetic(self):
        self.assertEqual(Money(1000) + Money(500), Money(1500))
        self.assertEqual(Money(5500).times(4), Money(22000))
        self.assertEqual(Money(999).percent(50), Money(499), "端数は切り捨て")
        self.assertEqual(Money(10000).percent(0), Money(0))
        self.assertEqual(Money(10000).percent(100), Money(10000))
        self.assertEqual(Money(100, "USD").currency, "USD")

    def test_validation(self):
        for amount in (-1, 1.5, True, "100"):
            with self.assertRaises(InvalidValueError, msg=repr(amount)):
                Money(amount)
        for currency in ("jpy", "JP", "YEN!", "", "ＪＰＹ"):
            with self.assertRaises(InvalidValueError, msg=repr(currency)):
                Money(100, currency)
        with self.assertRaises(InvalidValueError):
            Money(100) + Money(100, "USD")
        with self.assertRaises(InvalidValueError):
            Money(100).times(-1)
        with self.assertRaises(InvalidValueError):
            Money(100).percent(101)


class TestExercise1CancellationPolicy(unittest.TestCase):
    def test_default_policy_tiers(self):
        p = default_policy()
        h = lambda x: timedelta(hours=x)  # noqa: E731
        self.assertEqual(p.fee_percent(h(48)), 0)
        self.assertEqual(p.fee_percent(h(24)), 0, "ちょうど 24 時間前は無料の段階")
        self.assertEqual(p.fee_percent(h(24) - timedelta(minutes=1)), 50)
        self.assertEqual(p.fee_percent(h(3)), 50)
        self.assertEqual(p.fee_percent(h(3) - timedelta(seconds=1)), 100)
        self.assertEqual(p.fee_percent(timedelta(0)), 100)
        self.assertEqual(p.fee_percent(-h(1)), 100, "開始後は最後の段階")
        self.assertEqual(p.fee(Money(22000), h(5)), Money(11000))

    def test_invalid_policies(self):
        h = lambda x: timedelta(hours=x)  # noqa: E731
        invalid = {
            "空": (),
            "時間が減少していない": ((h(3), 50), (h(24), 0), (h(0), 100)),
            "同じ時間の段階": ((h(24), 0), (h(24), 50), (h(0), 100)),
            "直前ほど安い": ((h(24), 50), (h(0), 10)),
            "最後が 0 時間でない": ((h(24), 0), (h(3), 100)),
            "料率が範囲外": ((h(24), 0), (h(0), 120)),
            "時間が負": ((h(24), 0), (-h(1), 100)),
        }
        for label, tiers in invalid.items():
            with self.assertRaises(InvalidValueError, msg=label):
                CancellationPolicy(tiers)


class TestExercise1Table(unittest.TestCase):
    def test_accepts(self):
        t = Table("T05", 2, 4)
        self.assertTrue(t.accepts(PartySize(2)))
        self.assertTrue(t.accepts(PartySize(4)))
        self.assertFalse(t.accepts(PartySize(1)))
        self.assertFalse(t.accepts(PartySize(5)))


# ---------------------------------------------------------------------------
# 演習2: 集約ルート TableSchedule
# ---------------------------------------------------------------------------

MORNING = at(10, 0)  # 予約を受け付ける「現在時刻」


def price():
    """1 名あたりのコース料金（値オブジェクトはモジュールの読み込み時ではなく、テストの中で作る）。"""
    return Money(5500)


class ScheduleTestCase(unittest.TestCase):
    def setUp(self):
        self.schedule = TableSchedule(Table("T05", 2, 4), DAY)

    def book(self, rid="r1", hour=18, minute=0, minutes=90, party=4, now=MORNING):
        return self.schedule.book(rid, "c-" + rid, PartySize(party), slot(hour, minute, minutes), price(), now)


class TestExercise2Booking(ScheduleTestCase):
    def test_book_records_reservation_and_event(self):
        r = self.book()
        self.assertEqual((r.reservation_id, r.status, r.fee), ("r1", ReservationStatus.BOOKED, None))
        self.assertEqual(self.schedule.pull_events(),
                         [ReservationBooked("r1", "T05", slot(18, 0, 90), PartySize(4))])
        self.assertEqual(self.schedule.pull_events(), [], "pull_events は取り出した後で空になる")

    def test_capacity(self):
        with self.assertRaises(CapacityError):
            self.book(party=5)
        with self.assertRaises(CapacityError):
            self.book(party=1)
        self.assertEqual(self.schedule.reservations(), [])

    def test_no_double_booking(self):
        self.book("r1", 18, 0)
        with self.assertRaises(DoubleBookingError):
            self.book("r2", 19, 0)
        with self.assertRaises(DoubleBookingError):
            self.book("r3", 17, 0)
        self.book("r4", 19, 30)  # 接しているだけなら予約できる
        self.book("r5", 16, 30)
        self.assertEqual([r.reservation_id for r in self.schedule.reservations()], ["r5", "r1", "r4"])
        self.assertEqual(len(self.schedule.pull_events()), 3, "失敗した予約ではイベントを出さない")

    def test_cancelled_reservation_frees_the_slot(self):
        self.book("r1", 18, 0)
        self.schedule.cancel("r1", MORNING)
        self.book("r2", 18, 0)
        self.assertEqual(self.schedule.reservation("r2").status, ReservationStatus.BOOKED)

    def test_booking_window(self):
        with self.assertRaises(BookingWindowError, msg="別の日の台帳には入れられない"):
            self.schedule.book("r1", "c", PartySize(2), slot(18, 0, day=date(2026, 3, 16)), price(), MORNING)
        with self.assertRaises(BookingWindowError, msg="過去の時刻"):
            self.book(hour=9)
        with self.assertRaises(BookingWindowError, msg="ちょうど現在時刻"):
            self.book(hour=10)

    def test_duplicate_id(self):
        self.book("r1", 18, 0)
        with self.assertRaises(DuplicateReservationError):
            self.book("r1", 12, 0)

    def test_reads_return_copies(self):
        self.book("r1")
        r = self.schedule.reservation("r1")
        r.status = ReservationStatus.CANCELLED
        self.assertEqual(self.schedule.reservation("r1").status, ReservationStatus.BOOKED,
                         "集約の外から内部の状態を書き換えられない")
        with self.assertRaises(ReservationNotFoundError):
            self.schedule.reservation("nope")


class TestExercise2Reschedule(ScheduleTestCase):
    def test_reschedule_into_own_slot_and_free_slot(self):
        self.book("r1", 18, 0)
        self.book("r2", 20, 0)
        self.schedule.pull_events()
        self.schedule.reschedule("r1", slot(18, 30, 90), MORNING)  # 元の自分の枠とは重なってよい
        self.assertEqual(self.schedule.reservation("r1").slot, slot(18, 30, 90))
        self.assertEqual(self.schedule.pull_events(),
                         [ReservationRescheduled("r1", "T05", slot(18, 0, 90), slot(18, 30, 90))])

    def test_reschedule_conflict_leaves_state_unchanged(self):
        self.book("r1", 18, 0)
        self.book("r2", 20, 0)
        with self.assertRaises(DoubleBookingError):
            self.schedule.reschedule("r1", slot(19, 30, 90), MORNING)
        self.assertEqual(self.schedule.reservation("r1").slot, slot(18, 0, 90))

    def test_only_booked_can_be_rescheduled(self):
        self.book("r1", 18, 0)
        self.schedule.cancel("r1", MORNING)
        with self.assertRaises(InvalidTransitionError):
            self.schedule.reschedule("r1", slot(12, 0), MORNING)
        with self.assertRaises(ReservationNotFoundError):
            self.schedule.reschedule("nope", slot(12, 0), MORNING)


class TestExercise2Cancellation(ScheduleTestCase):
    def test_fee_depends_on_lead_time(self):
        self.book("free", 18, 0)
        self.assertEqual(self.schedule.cancel("free", at(18, 0) - timedelta(hours=30)), Money(0))
        self.book("half", 18, 0)
        # 4 名 × 5,500 円 = 22,000 円の 50%
        self.assertEqual(self.schedule.cancel("half", at(13, 0)), Money(11000))
        self.book("full", 18, 0)
        self.assertEqual(self.schedule.cancel("full", at(17, 30)), Money(22000))
        r = self.schedule.reservation("half")
        self.assertEqual((r.status, r.fee), (ReservationStatus.CANCELLED, Money(11000)))
        events = [e for e in self.schedule.pull_events() if isinstance(e, ReservationCancelled)]
        self.assertEqual(events, [ReservationCancelled("free", "T05", Money(0)),
                                  ReservationCancelled("half", "T05", Money(11000)),
                                  ReservationCancelled("full", "T05", Money(22000))])

    def test_cannot_cancel_after_start_or_twice(self):
        self.book("r1", 18, 0)
        with self.assertRaises(InvalidTransitionError):
            self.schedule.cancel("r1", at(18, 0))
        self.schedule.cancel("r1", at(12, 0))
        with self.assertRaises(InvalidTransitionError):
            self.schedule.cancel("r1", at(12, 0))

    def test_custom_policy(self):
        policy = CancellationPolicy(((timedelta(hours=48), 0), (timedelta(0), 30)))
        schedule = TableSchedule(Table("T01", 1, 2), DAY, policy)
        schedule.book("r1", "c", PartySize(2), slot(19, 0), Money(10000), MORNING)
        self.assertEqual(schedule.cancel("r1", MORNING), Money(6000))


class TestExercise2Visit(ScheduleTestCase):
    def test_seat_window_and_completion(self):
        self.book("r1", 18, 0)
        self.schedule.pull_events()
        with self.assertRaises(InvalidTransitionError, msg="開始 20 分前は早すぎる"):
            self.schedule.seat("r1", at(17, 40))
        with self.assertRaises(InvalidTransitionError, msg="SEATED でないと complete できない"):
            self.schedule.complete("r1")
        self.schedule.seat("r1", at(17, 45))
        self.schedule.complete("r1")
        self.assertEqual(self.schedule.reservation("r1").status, ReservationStatus.COMPLETED)
        self.assertEqual(self.schedule.pull_events(),
                         [GuestsSeated("r1", "T05", at(17, 45)), ReservationCompleted("r1", "T05")])

    def test_cannot_seat_after_end(self):
        self.book("r1", 18, 0)
        with self.assertRaises(InvalidTransitionError):
            self.schedule.seat("r1", at(19, 30))
        self.schedule.seat("r1", at(19, 29))

    def test_no_show(self):
        self.book("r1", 18, 0)
        self.schedule.pull_events()
        with self.assertRaises(InvalidTransitionError, msg="猶予時間内はまだ無断キャンセルではない"):
            self.schedule.mark_no_show("r1", at(18, 14))
        self.assertEqual(self.schedule.mark_no_show("r1", at(18, 15)), Money(22000))
        r = self.schedule.reservation("r1")
        self.assertEqual((r.status, r.fee), (ReservationStatus.NO_SHOW, Money(22000)))
        self.assertEqual(self.schedule.pull_events(), [ReservationMarkedNoShow("r1", "T05", Money(22000))])
        with self.assertRaises(InvalidTransitionError):
            self.schedule.seat("r1", at(18, 20))

    def test_no_show_frees_the_table(self):
        self.book("r1", 18, 0)
        self.schedule.mark_no_show("r1", at(18, 15))
        self.book("walk-in", 18, 30, minutes=60, now=at(18, 20))
        self.assertEqual(self.schedule.reservation("walk-in").status, ReservationStatus.BOOKED)


if __name__ == "__main__":
    unittest.main()
