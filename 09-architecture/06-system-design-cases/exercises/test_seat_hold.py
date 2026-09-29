"""9.6 システム設計ケーススタディ — 演習3 のテスト（座席の仮押さえと確定）

実行: python3 tools/check.py 9.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import random
import threading
import unittest

from seat_hold import (
    HoldExpiredError,
    HoldLimitError,
    HoldNotFoundError,
    InvalidHoldStateError,
    SeatInventory,
    SeatUnavailableError,
    UnknownSeatError,
)

SEATS = [f"A{i}" for i in range(1, 11)]


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class TestExercise3Basics(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.inv = SeatInventory(SEATS, hold_ttl=600, max_seats_per_user=4, clock=self.clock)

    def test_hold_and_confirm(self):
        hold = self.inv.hold("u1", ["A3", "A2"])
        self.assertEqual((hold.hold_id, hold.user_id, hold.seat_ids, hold.expires_at),
                         ("hold-000001", "u1", ("A2", "A3"), 600.0))
        self.assertEqual(self.inv.seat_state("A2"), "held")
        self.assertNotIn("A2", self.inv.available())
        booking = self.inv.confirm(hold.hold_id, "pay_1")
        self.assertEqual((booking.booking_id, booking.seat_ids, booking.payment_ref),
                         ("bk-000001", ("A2", "A3"), "pay_1"))
        self.assertEqual(self.inv.seat_state("A3"), "booked")
        self.assertEqual(len(self.inv.available()), 8)

    def test_all_or_nothing(self):
        self.inv.hold("u1", ["A1"])
        with self.assertRaises(SeatUnavailableError) as cm:
            self.inv.hold("u2", ["A2", "A1", "A3"])
        self.assertEqual(cm.exception.seats, ("A1",))
        self.assertEqual(self.inv.seat_state("A2"), "available", "1 席でも取れなければ何も押さえない")
        self.assertEqual(self.inv.seat_state("A3"), "available")

    def test_expired_holds_are_released(self):
        hold = self.inv.hold("u1", ["A1"])
        self.clock.now = 599.9
        self.assertEqual(self.inv.seat_state("A1"), "held")
        self.clock.now = 600.0
        self.assertEqual(self.inv.seat_state("A1"), "available", "期限ちょうどで解放")
        other = self.inv.hold("u2", ["A1"])
        with self.assertRaises(HoldExpiredError):
            self.inv.confirm(hold.hold_id, "pay_late")
        self.assertEqual(self.inv.confirm(other.hold_id, "pay_2").user_id, "u2")

    def test_confirm_after_expiry(self):
        hold = self.inv.hold("u1", ["A1", "A2"])
        self.clock.now = 601
        with self.assertRaises(HoldExpiredError):
            self.inv.confirm(hold.hold_id, "pay_1")
        with self.assertRaises(HoldExpiredError, msg="2 回目も期限切れとして答える"):
            self.inv.confirm(hold.hold_id, "pay_1")
        self.assertEqual(self.inv.available(), set(SEATS))

    def test_expire_holds_sweeper(self):
        self.inv.hold("u1", ["A1"])
        self.inv.hold("u2", ["A2"])
        self.clock.now = 300
        self.inv.hold("u3", ["A3"])
        self.clock.now = 650
        self.assertEqual(self.inv.expire_holds(), 2)
        self.assertEqual(self.inv.expire_holds(), 0)
        self.assertEqual(self.inv.seat_state("A3"), "held")

    def test_confirm_is_idempotent(self):
        hold = self.inv.hold("u1", ["A5"])
        first = self.inv.confirm(hold.hold_id, "pay_1")
        self.assertEqual(self.inv.confirm(hold.hold_id, "pay_1"), first, "決済通知の重複には同じ結果")
        with self.assertRaises(InvalidHoldStateError):
            self.inv.confirm(hold.hold_id, "pay_other")
        self.clock.now = 10_000
        self.assertEqual(self.inv.confirm(hold.hold_id, "pay_1"), first, "確定済みは期限に関係ない")
        self.assertEqual(self.inv.seat_state("A5"), "booked")

    def test_release(self):
        hold = self.inv.hold("u1", ["A1", "A2"])
        self.inv.release(hold.hold_id)
        self.assertEqual(self.inv.available(), set(SEATS))
        with self.assertRaises(HoldNotFoundError):
            self.inv.release(hold.hold_id)
        with self.assertRaises(HoldNotFoundError):
            self.inv.confirm(hold.hold_id, "pay_1")
        expired = self.inv.hold("u1", ["A3"])
        self.clock.now = 601
        self.inv.release(expired.hold_id)  # 期限切れは何もしない
        booked = self.inv.hold("u1", ["A4"])
        self.inv.confirm(booked.hold_id, "pay")
        with self.assertRaises(InvalidHoldStateError):
            self.inv.release(booked.hold_id)
        with self.assertRaises(HoldNotFoundError):
            self.inv.release("hold-999999")

    def test_per_user_limit(self):
        self.inv.hold("u1", ["A1", "A2"])
        b = self.inv.hold("u1", ["A3"])
        self.inv.confirm(b.hold_id, "pay")
        with self.assertRaises(HoldLimitError):
            self.inv.hold("u1", ["A4", "A5"])   # 仮押さえ 2 + 確定 1 + 今回 2 = 5 > 4
        self.inv.hold("u1", ["A4"])             # 合計 4 席まではよい
        self.inv.hold("u2", ["A5", "A6", "A7", "A8"])

    def test_validation(self):
        with self.assertRaises(UnknownSeatError):
            self.inv.hold("u1", ["Z9"])
        with self.assertRaises(ValueError):
            self.inv.hold("u1", [])
        with self.assertRaises(ValueError):
            self.inv.hold("u1", ["A1", "A1"])
        with self.assertRaises(UnknownSeatError):
            self.inv.seat_state("Z9")
        with self.assertRaises(ValueError):
            SeatInventory(["A1", "A1"])
        with self.assertRaises(ValueError):
            SeatInventory([])
        with self.assertRaises(HoldNotFoundError):
            self.inv.confirm("hold-404", "pay")


class TestExercise3Concurrency(unittest.TestCase):
    def run_threads(self, targets):
        threads = [threading.Thread(target=t) for t in targets]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)
            self.assertFalse(t.is_alive(), "スレッドが終わらない（デッドロック？）")

    def test_one_seat_many_buyers(self):
        inv = SeatInventory(["X1"], max_seats_per_user=1)
        start = threading.Barrier(30)
        winners, losers = [], []
        lock = threading.Lock()

        def buyer(n):
            def run():
                start.wait(5)
                try:
                    hold = inv.hold(f"user{n}", ["X1"])
                except SeatUnavailableError:
                    with lock:
                        losers.append(n)
                    return
                inv.confirm(hold.hold_id, f"pay{n}")
                with lock:
                    winners.append(n)
            return run

        self.run_threads([buyer(n) for n in range(30)])
        self.assertEqual(len(winners), 1, "同じ座席を買えるのは 1 人だけ")
        self.assertEqual(len(losers), 29)
        self.assertEqual(inv.seat_state("X1"), "booked")

    def test_no_overselling_under_contention(self):
        seats = [f"S{i:02d}" for i in range(20)]
        inv = SeatInventory(seats, max_seats_per_user=2)
        bookings = []
        lock = threading.Lock()

        def buyer(n):
            def run():
                rng = random.Random(n)
                for _ in range(20):
                    wanted = rng.sample(seats, 2)
                    try:
                        hold = inv.hold(f"user{n}", wanted)
                    except (SeatUnavailableError, HoldLimitError):
                        continue
                    if rng.random() < 0.3:
                        inv.release(hold.hold_id)      # 決済をやめる人もいる
                        continue
                    booking = inv.confirm(hold.hold_id, f"pay-{n}-{hold.hold_id}")
                    with lock:
                        bookings.append(booking)
            return run

        self.run_threads([buyer(n) for n in range(24)])
        sold = [seat for b in bookings for seat in b.seat_ids]
        self.assertEqual(len(sold), len(set(sold)), "同じ座席が 2 回売れてはいけない")
        self.assertEqual(set(sold), {s for s in seats if inv.seat_state(s) == "booked"})
        per_user = {}
        for b in bookings:
            per_user[b.user_id] = per_user.get(b.user_id, 0) + len(b.seat_ids)
        self.assertTrue(all(n <= 2 for n in per_user.values()), per_user)


if __name__ == "__main__":
    unittest.main()
