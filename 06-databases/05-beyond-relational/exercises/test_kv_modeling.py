"""6.5 演習2（アクセスパターンから設計する KV のデータモデル）のテスト

実行: python3 tools/check.py 6.5   （またはこのディレクトリで python3 -m unittest -v test_kv_modeling）
"""
import unittest
from collections import Counter

import kv_modeling as kv
from kv_modeling import Table


class TestTable(unittest.TestCase):
    def test_put_get_overwrite_delete(self):
        t = Table()
        t.put_item({"PK": "A", "SK": "1", "v": 1})
        t.put_item({"PK": "A", "SK": "1", "v": 2})
        self.assertEqual(t.get_item("A", "1"), {"PK": "A", "SK": "1", "v": 2})
        self.assertIsNone(t.get_item("A", "2"))
        t.delete_item("A", "1")
        t.delete_item("A", "1")  # なければ何もしない
        self.assertIsNone(t.get_item("A", "1"))
        self.assertEqual(t.query("A"), [])

    def test_items_are_copied(self):
        t = Table()
        item = {"PK": "A", "SK": "1", "tags": ["x"]}
        t.put_item(item)
        item["tags"].append("changed-after-put")
        got = t.get_item("A", "1")
        got["tags"].append("changed-after-get")
        self.assertEqual(t.get_item("A", "1")["tags"], ["x"])

    def test_query_order_and_conditions(self):
        t = Table()
        for sk in ["ORDER#2025-03", "PROFILE", "ORDER#2025-01", "ORDER#2025-02", "ADDR#home"]:
            t.put_item({"PK": "U#1", "SK": sk})
        t.put_item({"PK": "U#2", "SK": "ORDER#2025-01"})
        sks = lambda items: [i["SK"] for i in items]  # noqa: E731
        self.assertEqual(sks(t.query("U#1")), ["ADDR#home", "ORDER#2025-01", "ORDER#2025-02", "ORDER#2025-03", "PROFILE"])
        self.assertEqual(sks(t.query("U#1", begins_with="ORDER#")), ["ORDER#2025-01", "ORDER#2025-02", "ORDER#2025-03"])
        self.assertEqual(sks(t.query("U#1", between=("ORDER#2025-02", "ORDER#2025-03"))), ["ORDER#2025-02", "ORDER#2025-03"],
                         "between は両端を含む")
        self.assertEqual(sks(t.query("U#1", begins_with="ORDER#", reverse=True, limit=2)), ["ORDER#2025-03", "ORDER#2025-02"])
        self.assertEqual(t.query("nobody"), [])

    def test_query_argument_errors(self):
        t = Table()
        with self.assertRaises(ValueError):
            t.query("A", begins_with="x", between=("a", "b"))
        with self.assertRaises(ValueError):
            t.query("A", limit=0)
        with self.assertRaises(ValueError):
            t.query("A", index="NO_SUCH_INDEX")

    def test_key_validation(self):
        t = Table(gsis={"G": ("gpk", "gsk")})
        for bad in ({"SK": "1"}, {"PK": "A"}, {"PK": "", "SK": "1"}, {"PK": 1, "SK": "1"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                t.put_item(bad)
        with self.assertRaises(ValueError):
            t.put_item({"PK": "A", "SK": "1", "gpk": 5, "gsk": "x"})
        self.assertIsNone(t.get_item("A", "1"), "検査に失敗した項目は保存しない")

    def test_sparse_gsi(self):
        t = Table(gsis={"ByEmail": ("email", "SK")})
        t.put_item({"PK": "U#1", "SK": "PROFILE", "email": "a@example.com"})
        t.put_item({"PK": "U#1", "SK": "ORDER#1"})                     # email がない → GSI に入らない
        t.put_item({"PK": "U#2", "SK": "PROFILE", "email": "a@example.com"})
        got = t.query("a@example.com", index="ByEmail")
        self.assertEqual([(i["PK"], i["SK"]) for i in got], [("U#1", "PROFILE"), ("U#2", "PROFILE")],
                         "同じ GSI のソートキーなら (PK, SK) の順")

    def test_gsi_follows_overwrite_and_delete(self):
        t = Table(gsis={"G": ("gpk", "gsk")})
        t.put_item({"PK": "A", "SK": "1", "gpk": "old", "gsk": "x"})
        t.put_item({"PK": "A", "SK": "1", "gpk": "new", "gsk": "x"})
        self.assertEqual(t.query("old", index="G"), [], "上書きしたら古い GSI のエントリは消える")
        self.assertEqual(len(t.query("new", index="G")), 1)
        t.delete_item("A", "1")
        self.assertEqual(t.query("new", index="G"), [])

    def test_gsi_range_conditions(self):
        t = Table(gsis={"G": ("gpk", "gsk")})
        for i, day in enumerate(["2025-01-03", "2025-01-01", "2025-01-02"]):
            t.put_item({"PK": f"P{i}", "SK": "S", "gpk": "all", "gsk": day})
        self.assertEqual([i["gsk"] for i in t.query("all", index="G", between=("2025-01-02", "2025-12-31"))],
                         ["2025-01-02", "2025-01-03"])

    def test_scan_and_call_counters(self):
        t = Table()
        t.put_item({"PK": "B", "SK": "1"})
        t.put_item({"PK": "A", "SK": "2"})
        t.put_item({"PK": "A", "SK": "1"})
        self.assertEqual([(i["PK"], i["SK"]) for i in t.scan()], [("A", "1"), ("A", "2"), ("B", "1")])
        t.get_item("A", "1")
        t.query("A")
        self.assertEqual((t.calls["put_item"], t.calls["scan"], t.calls["get_item"], t.calls["query"]), (3, 1, 1, 1))


CUSTOMERS = [
    {"customer_id": "c1", "name": "佐藤", "email": "sato@example.com"},
    {"customer_id": "c2", "name": "鈴木", "email": "suzuki@example.com"},
    {"customer_id": "c10", "name": "高橋", "email": "takahashi@example.com"},
]


def order(oid, cid, at, status, *items):
    return {
        "order_id": oid, "customer_id": cid, "ordered_at": at, "status": status,
        "items": [{"product_id": p, "quantity": q, "unit_price": u} for p, q, u in items],
    }


ORDERS = [
    order("o1001", "c1", "2025-05-30T23:59:00Z", "shipped", ("p2", 1, 3200), ("p1", 2, 1200)),
    order("o1002", "c1", "2025-06-01T00:00:00Z", "paid", ("p3", 1, 800)),
    order("o1003", "c2", "2025-06-01T09:00:00Z", "paid", ("p1", 1, 1200)),
    order("o1004", "c1", "2025-06-15T12:00:00Z", "cancelled", ("p9", 3, 500)),
    order("o1005", "c1", "2025-07-01T00:00:00Z", "paid", ("p1", 1, 1100), ("p4", 1, 4000), ("p10", 5, 100)),
    order("o1006", "c10", "2025-06-20T08:00:00Z", "shipped", ("p5", 1, 9800)),
    order("o1007", "c1", "2025-06-15T12:00:00Z", "paid", ("p6", 1, 700)),   # o1004 と同時刻
]


def header(o):
    return {k: o[k] for k in ("order_id", "customer_id", "ordered_at", "status")}


class TestAccessPatterns(unittest.TestCase):
    def setUp(self):
        self.t = kv.make_table()
        self.assertIsInstance(self.t, Table)
        for c in CUSTOMERS:
            kv.put_customer(self.t, c)
        for o in ORDERS:
            kv.put_order(self.t, o)

    def read(self, fn, *args, **kwargs):
        """読み取りの関数を呼び、query / get_item をちょうど 1 回だけ使ったことを確かめる。"""
        before = Counter(self.t.calls)
        result = fn(self.t, *args, **kwargs)
        used = Counter(self.t.calls)
        used.subtract(before)
        self.assertEqual(used["scan"], 0, f"{fn.__name__}: scan を使わないこと")
        self.assertEqual(used["query"] + used["get_item"], 1,
                         f"{fn.__name__}: query か get_item をちょうど 1 回だけ使うこと（実際: {dict(+used)}）")
        return result

    def test_get_customer(self):
        self.assertEqual(self.read(kv.get_customer, "c2"), CUSTOMERS[1])
        self.assertIsNone(self.read(kv.get_customer, "nobody"))

    def test_get_order_header(self):
        self.assertEqual(self.read(kv.get_order, "o1005"), header(ORDERS[4]))
        self.assertIsNone(self.read(kv.get_order, "o9999"))

    def test_get_order_items(self):
        self.assertEqual(
            self.read(kv.get_order_items, "o1005"),
            [{"product_id": "p1", "quantity": 1, "unit_price": 1100},
             {"product_id": "p10", "quantity": 5, "unit_price": 100},
             {"product_id": "p4", "quantity": 1, "unit_price": 4000}],
            "product_id の（文字列としての）昇順",
        )
        self.assertEqual(self.read(kv.get_order_items, "o9999"), [])

    def test_orders_for_customer_newest_first(self):
        got = self.read(kv.get_orders_for_customer, "c1")
        self.assertEqual([o["order_id"] for o in got], ["o1005", "o1007", "o1004", "o1002", "o1001"],
                         "新しい順。同時刻は order_id の降順")
        self.assertEqual(got[0], header(ORDERS[4]))

    def test_orders_for_customer_are_isolated(self):
        self.assertEqual([o["order_id"] for o in self.read(kv.get_orders_for_customer, "c10")], ["o1006"])
        self.assertEqual(self.read(kv.get_orders_for_customer, "nobody"), [])

    def test_orders_for_customer_period(self):
        june = self.read(kv.get_orders_for_customer, "c1", since="2025-06-01", until="2025-07-01")
        self.assertEqual([o["order_id"] for o in june], ["o1007", "o1004", "o1002"],
                         "since は含み、until は含まない（7/1 0:00 の o1005 は除く）")
        exact = self.read(kv.get_orders_for_customer, "c1", since="2025-06-01T00:00:00Z", until="2025-06-15T12:00:00Z")
        self.assertEqual([o["order_id"] for o in exact], ["o1002"])
        after = self.read(kv.get_orders_for_customer, "c1", since="2025-06-15T12:00:00Z", newest_first=False)
        self.assertEqual([o["order_id"] for o in after], ["o1004", "o1007", "o1005"])
        before = self.read(kv.get_orders_for_customer, "c1", until="2025-06-01")
        self.assertEqual([o["order_id"] for o in before], ["o1001"])

    def test_orders_for_customer_limit(self):
        got = self.read(kv.get_orders_for_customer, "c1", limit=2)
        self.assertEqual([o["order_id"] for o in got], ["o1005", "o1007"])

    def test_orders_by_status_oldest_first(self):
        paid = self.read(kv.get_orders_by_status, "paid")
        self.assertEqual([o["order_id"] for o in paid], ["o1002", "o1003", "o1007", "o1005"])
        self.assertEqual(paid[1], header(ORDERS[2]))
        self.assertEqual([o["order_id"] for o in self.read(kv.get_orders_by_status, "paid", limit=1)], ["o1002"])
        self.assertEqual(self.read(kv.get_orders_by_status, "returned"), [])

    def test_update_status_moves_order_between_lists(self):
        kv.update_order_status(self.t, "o1003", "shipped")
        self.assertEqual(self.read(kv.get_order, "o1003")["status"], "shipped")
        self.assertNotIn("o1003", [o["order_id"] for o in self.read(kv.get_orders_by_status, "paid")])
        self.assertEqual([o["order_id"] for o in self.read(kv.get_orders_by_status, "shipped")], ["o1001", "o1003", "o1006"])
        self.assertEqual(self.read(kv.get_orders_for_customer, "c2")[0]["status"], "shipped",
                         "注文履歴に表示するステータスも更新される")
        with self.assertRaises(KeyError):
            kv.update_order_status(self.t, "o9999", "paid")

    def test_no_scan_anywhere(self):
        kv.get_orders_for_customer(self.t, "c1")
        kv.get_orders_by_status(self.t, "paid")
        kv.get_order_items(self.t, "o1001")
        self.assertEqual(self.t.calls["scan"], 0)


if __name__ == "__main__":
    unittest.main()
