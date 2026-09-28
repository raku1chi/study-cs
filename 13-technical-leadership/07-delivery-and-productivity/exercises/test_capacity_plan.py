"""13.7 デリバリーと生産性 — テスト（四半期のキャパシティ計画）

実行: python3 tools/check.py 13.7   （またはこのディレクトリで python3 -m unittest -v test_capacity_plan）
"""
import unittest
from datetime import date

from capacity_plan import Member, allocate, business_days, member_capacity, team_capacity

# 本文の例: 2026 年 10〜12 月（日本の祝日と年末の休業日）
Q4_HOLIDAYS = {date(2026, 10, 12), date(2026, 11, 3), date(2026, 11, 23),
               date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31)}
BOOK_TEAM = [
    Member("A", leave_days=3, oncall_weeks=3),
    Member("B", leave_days=5, oncall_weeks=3),
    Member("C", leave_days=2, oncall_weeks=3),
    Member("D", fte=0.8, leave_days=2, oncall_weeks=2),
    Member("E", leave_days=10, oncall_weeks=2),
    Member("F", fte=0.5),
]


class TestExercise5BusinessDays(unittest.TestCase):
    def test_book_quarter(self):
        self.assertEqual(business_days(date(2026, 10, 1), date(2026, 12, 31), Q4_HOLIDAYS), 60)
        self.assertEqual(business_days(date(2026, 10, 1), date(2026, 12, 31)), 66)

    def test_docstring_example(self):
        self.assertEqual(business_days(date(2026, 10, 5), date(2026, 10, 18), {date(2026, 10, 12)}), 9)

    def test_weekend_and_single_day(self):
        self.assertEqual(business_days(date(2026, 10, 3), date(2026, 10, 4)), 0, "土日")
        self.assertEqual(business_days(date(2026, 10, 5), date(2026, 10, 5)), 1, "両端を含む")
        self.assertEqual(business_days(date(2026, 10, 3), date(2026, 10, 4), [date(2026, 10, 3)]), 0,
                         "土曜の祝日を二重に引かない")

    def test_invalid_range(self):
        with self.assertRaises(ValueError):
            business_days(date(2026, 10, 5), date(2026, 10, 4))


class TestExercise5Capacity(unittest.TestCase):
    def test_book_members(self):
        got = [member_capacity(m, 60) for m in BOOK_TEAM]
        for g, e in zip(got, [39.6, 38.0, 40.4, 33.12, 36.0, 24.0]):
            self.assertAlmostEqual(g, e)
        self.assertAlmostEqual(team_capacity(BOOK_TEAM, 60), 211.12)

    def test_parameters(self):
        m = Member("X", fte=1.0, leave_days=0, oncall_weeks=1)
        self.assertAlmostEqual(member_capacity(m, 10, overhead_ratio=0.0, oncall_cost_days=0.0), 10.0)
        self.assertAlmostEqual(member_capacity(m, 10, overhead_ratio=0.5, oncall_cost_days=1.0), 4.0)

    def test_never_negative(self):
        self.assertEqual(member_capacity(Member("X", leave_days=30), 20), 0.0)
        self.assertEqual(member_capacity(Member("X", oncall_weeks=13), 10), 0.0)

    def test_invalid_members(self):
        for m in (Member("X", fte=0), Member("X", fte=1.5), Member("X", leave_days=-1),
                  Member("X", oncall_weeks=-1)):
            with self.assertRaises(ValueError, msg=str(m)):
                member_capacity(m, 10)
        with self.assertRaises(ValueError):
            member_capacity(Member("X"), 10, overhead_ratio=1.0)
        with self.assertRaises(ValueError):
            member_capacity(Member("X"), 10, oncall_cost_days=-1)
        with self.assertRaises(ValueError):
            member_capacity(Member("X"), -1)

    def test_team_capacity_empty(self):
        self.assertEqual(team_capacity([], 60), 0.0)


class TestExercise5Allocate(unittest.TestCase):
    def test_docstring_examples(self):
        self.assertEqual(allocate(10, {"新機能": 0.6, "技術的負債": 0.2, "運用": 0.2}),
                         {"新機能": 6.0, "技術的負債": 2.0, "運用": 2.0})
        self.assertEqual(allocate(10.8, {"a": 1 / 3, "b": 1 / 3, "c": 1 / 3}), {"a": 3.5, "b": 3.5, "c": 3.5})

    def test_book_example(self):
        got = allocate(211.12, {"新機能": 0.6, "技術的負債": 0.2, "運用・保守（KTLO）": 0.2})
        self.assertEqual(got, {"新機能": 126.5, "技術的負債": 42.5, "運用・保守（KTLO）": 42.0})
        self.assertEqual(list(got), ["新機能", "技術的負債", "運用・保守（KTLO）"])

    def test_largest_remainder(self):
        # 11 単位を 0.45 / 0.35 / 0.2 で配る: 4.95, 3.85, 2.2 → 4, 3, 2 + 余り 2 → a, b に 1 ずつ
        self.assertEqual(allocate(11, {"a": 0.45, "b": 0.35, "c": 0.2}, step=1), {"a": 5, "b": 4, "c": 2})

    def test_sum_matches_units(self):
        for total in (0, 0.4, 7.3, 99.99, 211.12):
            got = allocate(total, {"x": 0.5, "y": 0.3, "z": 0.2})
            self.assertAlmostEqual(sum(got.values()), int(total / 0.5 + 1e-9) * 0.5, msg=str(total))

    def test_float_noise_does_not_lose_a_unit(self):
        # 0.3 / 0.1 は 2.9999999999999996 になる。誤差で 1 単位（0.1 人日）を失わないこと
        self.assertAlmostEqual(allocate(0.3, {"a": 1.0}, step=0.1)["a"], 0.3)
        self.assertAlmostEqual(allocate(0.1 + 0.2, {"a": 1.0}, step=0.1)["a"], 0.3)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            allocate(-1, {"a": 1.0})
        with self.assertRaises(ValueError):
            allocate(10, {"a": 1.0}, step=0)
        with self.assertRaises(ValueError):
            allocate(10, {})
        with self.assertRaises(ValueError):
            allocate(10, {"a": 0.5, "b": 0.4})
        with self.assertRaises(ValueError):
            allocate(10, {"a": 1.2, "b": -0.2})


if __name__ == "__main__":
    unittest.main()
