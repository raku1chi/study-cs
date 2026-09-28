"""6.1 演習2（SQL の問い合わせ）のテスト

各 SQL を、元のデータと「データを追加・変更したデータ」の両方で実行し、
Python で計算した正解（参照実装）と比べます。

実行: python3 tools/check.py 6.1   （またはこのディレクトリで python3 -m unittest -v test_sql_practice）
"""
import sqlite3
import unittest
from collections import defaultdict

import sql_practice as sp

# 追加データ: 新しい顧客・カテゴリ・商品・注文（7 月）を足す
VARIANT_SQL = """
INSERT INTO customers VALUES (11, '松本 葵', 'aoi@example.com', '京都府', '2025-06-20');
INSERT INTO categories VALUES (11, 'NoSQL', 3);
INSERT INTO products VALUES (13, 'NoSQL 入門', 11, 2600);
INSERT INTO orders VALUES
  (21, 11, '2025-07-01 09:00:00', 'paid'),
  (22, 11, '2025-07-15 18:00:00', 'paid'),
  (23, 7,  '2025-07-20 12:00:00', 'cancelled'),
  (24, 10, '2025-08-02 08:00:00', 'cancelled');
INSERT INTO order_items VALUES
  (21, 13, 1, 2600), (22, 12, 2, 4200), (23, 1, 1, 3200), (24, 5, 1, 1500);
UPDATE orders SET status = 'cancelled' WHERE order_id = 19;
"""

EMPTY_ORDERS_SQL = "DELETE FROM order_items; DELETE FROM orders;"


def load_tables(conn: sqlite3.Connection) -> dict:
    out = {}
    for table in ("customers", "categories", "products", "orders", "order_items"):
        cur = conn.execute(f"SELECT * FROM {table}")
        cols = [d[0] for d in cur.description]
        out[table] = [dict(zip(cols, row)) for row in cur.fetchall()]
    return out


# ---------------------------------------------------------------------------
# 参照実装（SQL を使わずに Python で正解を計算する）
# ---------------------------------------------------------------------------

def valid_orders(t):
    return {o["order_id"]: o for o in t["orders"] if o["status"] != "cancelled"}


def ref_top_customers(t, n):
    names = {c["customer_id"]: c["name"] for c in t["customers"]}
    orders = valid_orders(t)
    revenue = defaultdict(int)
    for item in t["order_items"]:
        order = orders.get(item["order_id"])
        if order:
            revenue[order["customer_id"]] += item["quantity"] * item["unit_price"]
    ranked = sorted(revenue.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return [(cid, names[cid], rev) for cid, rev in ranked]


def ref_order_counts(t):
    counts = defaultdict(int)
    for o in valid_orders(t).values():
        counts[o["customer_id"]] += 1
    return [(c["customer_id"], c["name"], counts[c["customer_id"]]) for c in sorted(t["customers"], key=lambda c: c["customer_id"])]


def ref_customers_without_orders(t):
    ordered = {o["customer_id"] for o in t["orders"]}
    return [(c["customer_id"], c["name"]) for c in sorted(t["customers"], key=lambda c: c["customer_id"]) if c["customer_id"] not in ordered]


def ref_leaf_categories(t):
    parents = {c["parent_id"] for c in t["categories"] if c["parent_id"] is not None}
    return [(c["category_id"], c["name"]) for c in sorted(t["categories"], key=lambda c: c["category_id"]) if c["category_id"] not in parents]


def ref_monthly_revenue(t):
    orders = valid_orders(t)
    monthly = defaultdict(int)
    for item in t["order_items"]:
        order = orders.get(item["order_id"])
        if order:
            monthly[order["ordered_at"][:7]] += item["quantity"] * item["unit_price"]
    out, total = [], 0
    for month in sorted(monthly):
        total += monthly[month]
        out.append((month, monthly[month], total))
    return out


def ref_rank_within_category(t):
    orders = valid_orders(t)
    revenue = defaultdict(int)
    for item in t["order_items"]:
        if item["order_id"] in orders:
            revenue[item["product_id"]] += item["quantity"] * item["unit_price"]
    by_category = defaultdict(list)
    for p in t["products"]:
        by_category[p["category_id"]].append((p["product_id"], revenue[p["product_id"]]))
    out = []
    for cat in sorted(by_category):
        products = by_category[cat]
        for pid, rev in products:
            rank = 1 + sum(1 for _, other in products if other > rev)  # RANK の定義そのもの
            out.append((cat, pid, rev, rank))
    return sorted(out, key=lambda r: (r[0], r[3], r[1]))


def ref_category_paths(t):
    by_id = {c["category_id"]: c for c in t["categories"]}
    out = []
    for cid in sorted(by_id):
        names, node = [], by_id[cid]
        while node is not None:
            names.append(node["name"])
            node = by_id.get(node["parent_id"]) if node["parent_id"] is not None else None
        out.append((cid, " > ".join(reversed(names)), len(names)))
    return out


def ref_repeat_rate(t):
    counts = defaultdict(int)
    for o in valid_orders(t).values():
        counts[o["customer_id"]] += 1
    if not counts:
        return None
    return round(sum(1 for n in counts.values() if n >= 2) / len(counts), 4)


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

class SQLTestCase(unittest.TestCase):
    def setUp(self):
        self.base = sp.connect()
        self.variant = sp.connect(VARIANT_SQL)

    def tearDown(self):
        self.base.close()
        self.variant.close()

    def run_sql(self, conn, sql, params=()):
        self.assertIsInstance(sql, str, "SQL の文字列を返してください")
        try:
            cur = conn.execute(sql, params)
        except sqlite3.Error as e:
            self.fail(f"SQL の実行に失敗しました: {type(e).__name__}: {e}\n--- SQL ---\n{sql}")
        return [d[0] for d in cur.description], cur.fetchall()

    def check(self, sql, columns, reference, params=(), conns=None):
        for label, conn in conns or (("元のデータ", self.base), ("追加データ", self.variant)):
            cols, rows = self.run_sql(conn, sql, params)
            self.assertEqual(cols, columns, f"[{label}] 列の名前と順序")
            self.assertEqual(rows, reference(load_tables(conn)), f"[{label}] 結果（行の並び順も含む）")


class TestTopCustomers(SQLTestCase):
    def test_top3(self):
        _, rows = self.run_sql(self.base, sp.top_customers_sql(), {"n": 3})
        self.assertEqual(rows, [(2, "鈴木 一郎", 39900), (5, "伊藤 さくら", 20300), (3, "高橋 美咲", 20100)])

    def test_against_reference(self):
        for n in (1, 5, 100):
            self.check(sp.top_customers_sql(), ["customer_id", "name", "revenue"], lambda t, n=n: ref_top_customers(t, n), {"n": n})

    def test_tie_is_broken_by_customer_id(self):
        # 田中 健太（id=4, 5600）と同額になるよう、渡辺 大輔（id=6, 8800）の売上を 5600 にする
        self.base.execute("UPDATE order_items SET unit_price = 5600 WHERE order_id = 9")
        _, rows = self.run_sql(self.base, sp.top_customers_sql(), {"n": 10})
        self.assertEqual([r[0] for r in rows[-2:]], [4, 6], "同額なら customer_id の昇順")


class TestOrderCounts(SQLTestCase):
    def test_includes_customers_without_valid_orders(self):
        _, rows = self.run_sql(self.base, sp.order_counts_sql())
        counts = {cid: n for cid, _, n in rows}
        self.assertEqual(len(rows), 10, "全顧客（10 人）を返すこと。LEFT JOIN の後に WHERE で絞っていないか")
        self.assertEqual(counts[7], 0, "注文のない顧客は 0（COUNT(*) だと 1 になる）")
        self.assertEqual(counts[8], 0, "キャンセルした注文しかない顧客も 0")
        self.assertEqual(counts[1], 4)

    def test_against_reference(self):
        self.check(sp.order_counts_sql(), ["customer_id", "name", "orders"], ref_order_counts)


class TestCustomersWithoutOrders(SQLTestCase):
    def test_base(self):
        _, rows = self.run_sql(self.base, sp.customers_without_orders_sql())
        self.assertEqual(rows, [(7, "山本 結衣"), (10, "加藤 蓮")])

    def test_against_reference(self):
        self.check(sp.customers_without_orders_sql(), ["customer_id", "name"], ref_customers_without_orders)


class TestLeafCategories(SQLTestCase):
    def test_not_in_with_null_trap(self):
        _, rows = self.run_sql(self.base, sp.leaf_categories_sql())
        self.assertNotEqual(
            rows, [],
            "0 行になりました。NOT IN (SELECT parent_id ...) の結果に NULL が含まれると、"
            "x NOT IN (...) は決して真にならないためです。NOT EXISTS を使いましょう",
        )
        self.assertEqual([r[0] for r in rows], [3, 4, 5, 8, 9, 10])

    def test_against_reference(self):
        self.check(sp.leaf_categories_sql(), ["category_id", "name"], ref_leaf_categories)


class TestMonthlyRevenue(SQLTestCase):
    def test_base(self):
        _, rows = self.run_sql(self.base, sp.monthly_revenue_sql())
        self.assertEqual(rows[0], ("2025-01", 24400, 24400))
        self.assertEqual(rows[-1], ("2025-06", 12500, 133400))

    def test_against_reference(self):
        # 追加データでは 8 月の注文はキャンセルのみ → 8 月は結果に現れない
        self.check(sp.monthly_revenue_sql(), ["month", "revenue", "running_total"], ref_monthly_revenue)


class TestRankWithinCategory(SQLTestCase):
    def test_ties_and_unsold_products(self):
        _, rows = self.run_sql(self.base, sp.rank_within_category_sql())
        self.assertEqual(len(rows), 12, "一度も売れていない商品も含めること")
        category3 = [r for r in rows if r[0] == 3]
        self.assertEqual(
            category3,
            [(3, 1, 12800, 1), (3, 2, 12800, 1), (3, 12, 0, 3)],
            "同額は同順位、次は 3 位（RANK）。売れていない商品の revenue は 0",
        )

    def test_against_reference(self):
        self.check(
            sp.rank_within_category_sql(), ["category_id", "product_id", "revenue", "category_rank"], ref_rank_within_category
        )


class TestCategoryPaths(SQLTestCase):
    def test_base(self):
        _, rows = self.run_sql(self.base, sp.category_paths_sql())
        self.assertEqual(rows[2], (3, "本 > コンピュータ > データベース", 3))
        self.assertEqual(rows[9], (10, "ギフトカード", 1))

    def test_against_reference(self):
        # 追加データでは深さ 4 のカテゴリ（NoSQL）が増える
        self.check(sp.category_paths_sql(), ["category_id", "path", "depth"], ref_category_paths)


class TestRepeatPurchaseRate(SQLTestCase):
    def test_base(self):
        cols, rows = self.run_sql(self.base, sp.repeat_purchase_rate_sql())
        self.assertEqual(cols, ["rate"])
        self.assertEqual(len(rows), 1)
        self.assertNotEqual(rows[0][0], 0, "0 になりました。整数どうしの割り算は切り捨てられます")
        self.assertAlmostEqual(rows[0][0], 0.7143, places=4)

    def test_against_reference(self):
        for label, conn in (("元のデータ", self.base), ("追加データ", self.variant)):
            _, rows = self.run_sql(conn, sp.repeat_purchase_rate_sql())
            self.assertAlmostEqual(rows[0][0], ref_repeat_rate(load_tables(conn)), places=4, msg=label)

    def test_no_purchasers_gives_null(self):
        conn = sp.connect(EMPTY_ORDERS_SQL)
        try:
            _, rows = self.run_sql(conn, sp.repeat_purchase_rate_sql())
        finally:
            conn.close()
        self.assertEqual(rows, [(None,)], "購入者が 0 人なら NULL（ゼロ除算を避ける）")


if __name__ == "__main__":
    unittest.main()
