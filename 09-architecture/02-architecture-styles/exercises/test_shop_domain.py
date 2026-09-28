"""9.2 アーキテクチャスタイル — 演習1 のテスト（ドメインモデル）と、依存方向の検査

実行: python3 tools/check.py 9.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import ast
import dataclasses
import unittest
from datetime import datetime, timezone
from pathlib import Path

from shop_domain import (
    MAX_LINES,
    InvalidOrderError,
    InvalidStateError,
    Order,
    OrderLine,
    OrderStatus,
)

T0 = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)


def two_lines():
    return [OrderLine("BOOK", 2, 1500), OrderLine("PEN", 3, 200)]


class TestExercise1OrderLine(unittest.TestCase):
    def test_valid_line_and_subtotal(self):
        line = OrderLine("BOOK", 2, 1500)
        self.assertEqual(line.subtotal, 3000)
        self.assertEqual(OrderLine("FREE", 1, 0).subtotal, 0)

    def test_value_object_semantics(self):
        self.assertEqual(OrderLine("BOOK", 2, 1500), OrderLine("BOOK", 2, 1500))
        self.assertEqual(len({OrderLine("BOOK", 2, 1500), OrderLine("BOOK", 2, 1500)}), 1)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            OrderLine("BOOK", 2, 1500).quantity = 3

    def test_invalid_lines(self):
        for args in [("", 1, 100), ("   ", 1, 100), ("A", 0, 100), ("A", 100, 100), ("A", -1, 100), ("A", 1, -1)]:
            with self.assertRaises(InvalidOrderError, msg=str(args)):
                OrderLine(*args)
        self.assertEqual(OrderLine("A", 99, 1).quantity, 99)


class TestExercise1Order(unittest.TestCase):
    def test_place_creates_pending_order(self):
        lines = two_lines()
        order = Order.place("ord_1", "c1", "req_1", lines, T0)
        self.assertEqual(order.status, OrderStatus.PENDING_PAYMENT)
        self.assertEqual(order.total, 3600)
        self.assertEqual(order.version, 0)
        self.assertEqual(order.created_at, T0)
        self.assertIsInstance(order.lines, tuple, "明細はタプルで保持する")
        lines.append(OrderLine("X", 1, 1))
        self.assertEqual(len(order.lines), 2, "渡したリストを後から変更しても影響を受けない")

    def test_place_validation(self):
        with self.assertRaises(InvalidOrderError):
            Order.place("o", "c1", "r", [], T0)
        with self.assertRaises(InvalidOrderError):
            Order.place("o", "c1", "r", [OrderLine(f"S{i}", 1, 10) for i in range(MAX_LINES + 1)], T0)
        self.assertEqual(
            len(Order.place("o", "c1", "r", [OrderLine(f"S{i}", 1, 10) for i in range(MAX_LINES)], T0).lines),
            MAX_LINES,
        )
        with self.assertRaises(InvalidOrderError, msg="同じ SKU の明細が 2 行"):
            Order.place("o", "c1", "r", [OrderLine("A", 1, 10), OrderLine("A", 2, 10)], T0)
        with self.assertRaises(InvalidOrderError, msg="顧客 ID が空"):
            Order.place("o", "", "r", two_lines(), T0)
        with self.assertRaises(InvalidOrderError, msg="合計 0 円"):
            Order.place("o", "c1", "r", [OrderLine("FREE", 1, 0)], T0)

    def test_payment_transitions(self):
        order = Order.place("o", "c1", "r", two_lines(), T0)
        order.mark_paid("pay_1")
        self.assertEqual((order.status, order.payment_id), (OrderStatus.PAID, "pay_1"))
        with self.assertRaises(InvalidStateError):
            order.mark_paid("pay_2")
        with self.assertRaises(InvalidStateError):
            order.mark_payment_failed("late")
        with self.assertRaises(InvalidStateError, msg="支払い済みは取り消せない"):
            order.cancel()
        self.assertEqual(order.payment_id, "pay_1", "失敗した操作は状態を変えない")

    def test_failure_and_cancel_transitions(self):
        order = Order.place("o", "c1", "r", two_lines(), T0)
        order.mark_payment_failed("カードが利用できません")
        self.assertEqual(order.status, OrderStatus.PAYMENT_FAILED)
        self.assertEqual(order.failure_reason, "カードが利用できません")
        with self.assertRaises(InvalidStateError):
            order.mark_paid("pay_1")
        order.cancel()
        self.assertEqual(order.status, OrderStatus.CANCELLED)
        with self.assertRaises(InvalidStateError):
            order.cancel()

        pending = Order.place("o2", "c1", "r2", two_lines(), T0)
        pending.cancel()
        self.assertEqual(pending.status, OrderStatus.CANCELLED)


class TestArchitectureRule(unittest.TestCase):
    """9.1 の適応度関数: 内側（shop_domain）は外側やインフラに依存してはいけない。"""

    FORBIDDEN = {"sqlite3", "shop_adapters", "json", "socket", "http", "urllib", "requests"}

    def test_domain_does_not_depend_on_adapters_or_infrastructure(self):
        source = (Path(__file__).parent / "shop_domain.py").read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported & self.FORBIDDEN, set(),
                         "shop_domain.py が外側（アダプタ・インフラ）を import しています")


if __name__ == "__main__":
    unittest.main()
