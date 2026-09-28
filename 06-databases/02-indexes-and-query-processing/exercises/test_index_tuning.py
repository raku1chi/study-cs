"""6.2 演習3（インデックス設計とキーセットページネーション）のテスト

実行: python3 tools/check.py 6.2   （またはこのディレクトリで python3 -m unittest -v test_index_tuning）

実行計画の文字列は SQLite のバージョンで少し変わる（3.36 より前は "SCAN TABLE orders"）ため、
正規表現でどちらにも一致するように確かめています。
"""
import re
import sqlite3
import unittest

import index_tuning as it


def plan_text(lines):
    return "\n".join("    " + line for line in lines)


class IndexDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plain = it.create_database()     # インデックスなし（結果の比較用）
        cls.conn = it.create_database()      # 学習者のインデックスを作る DB
        cls.setup_error = None
        try:
            cls.statements = it.index_statements()
            it.apply_indexes(cls.conn, cls.statements)
        except Exception as e:  # noqa: BLE001  各テストで報告する
            cls.setup_error = e

    @classmethod
    def tearDownClass(cls):
        cls.plain.close()
        cls.conn.close()

    def setUp(self):
        if self.setup_error is not None:
            raise self.setup_error

    def plan(self, name):
        return it.explain(self.conn, it.QUERIES[name], it.SAMPLE_PARAMS[name])

    def assert_line(self, lines, pattern, message):
        if not any(re.fullmatch(pattern, line) for line in lines):
            self.fail(f"{message}\n実際の実行計画:\n{plan_text(lines)}")

    def assert_no_table_scan(self, lines, table):
        for line in lines:
            if re.fullmatch(rf"SCAN (TABLE )?{table}", line):
                self.fail(f"{table} を全件走査しています\n実際の実行計画:\n{plan_text(lines)}")

    def assert_no_temp_sort(self, lines, allow_group_by=False):
        for line in lines:
            if "TEMP B-TREE" in line and not (allow_group_by and "GROUP BY" in line):
                self.fail(f"一時的な並べ替え（{line}）が発生しています\n実際の実行計画:\n{plan_text(lines)}")

    # --- 文の形式と個数 -------------------------------------------------------

    def test_statements_are_create_index_within_budget(self):
        self.assertIsInstance(self.statements, list)
        self.assertLessEqual(len(self.statements), it.INDEX_BUDGET, f"インデックスは {it.INDEX_BUDGET} 個まで")
        for stmt in self.statements:
            self.assertRegex(stmt, re.compile(r"^\s*CREATE\s+(UNIQUE\s+)?INDEX\s", re.I), "CREATE INDEX 文だけを返すこと")

    # --- 各問い合わせの実行計画 -------------------------------------------------

    def test_orders_of_customer(self):
        lines = self.plan("orders_of_customer")
        self.assert_line(lines, r"SEARCH (TABLE )?orders USING (COVERING )?INDEX \S+ \(customer_id=\?.*\)",
                         "customer_id の等価条件でインデックスを使うこと")
        self.assert_no_temp_sort(lines)

    def test_recent_order_count_is_covered(self):
        lines = self.plan("recent_order_count")
        self.assert_line(lines, r"SEARCH (TABLE )?orders USING COVERING INDEX \S+ \(customer_id=\? AND created_at>\?\)",
                         "customer_id と created_at の両方をインデックスで使い、インデックスだけで数えること")

    def test_customer_by_email(self):
        lines = self.plan("customer_by_email")
        self.assert_no_table_scan(lines, "customers")
        self.assert_line(lines, r"SEARCH (TABLE )?customers USING (COVERING )?INDEX .*", "インデックスで探すこと")

    def test_pending_orders(self):
        lines = self.plan("pending_orders")
        self.assert_no_table_scan(lines, "orders")
        self.assert_no_temp_sort(lines)
        self.assert_line(lines, r"(SEARCH|SCAN) (TABLE )?orders USING (COVERING )?INDEX .*", "インデックスを使うこと")

    def test_daily_sales_is_covered(self):
        lines = self.plan("daily_sales")
        self.assert_line(lines, r"SEARCH (TABLE )?orders USING COVERING INDEX \S+ \(created_at>\? AND created_at<\?\)",
                         "created_at の範囲をインデックスで絞り、インデックスだけで集計すること")
        self.assert_no_temp_sort(lines, allow_group_by=True)

    def test_paid_by_customer_is_covered_without_sort(self):
        lines = self.plan("paid_by_customer")
        self.assert_line(lines, r"SEARCH (TABLE )?orders USING COVERING INDEX \S+ \(status=\?\)",
                         "status の等価条件で絞り、インデックスだけで集計すること")
        self.assert_no_temp_sort(lines)

    def test_keyset_query_uses_index_without_sort(self):
        sql = it.keyset_page_sql()
        params = {"last_created_at": "2025-06-15 12:00:00", "last_id": 25_000, "page_size": 20}
        lines = it.explain(self.conn, sql, params)
        self.assert_no_table_scan(lines, "orders")
        self.assert_no_temp_sort(lines)
        self.assert_line(lines, r"(SEARCH|SCAN) (TABLE )?orders USING (COVERING )?INDEX .*",
                         "キーセットページネーションもインデックスで並べ替えなしに実行できること")

    # --- インデックスは結果を変えない ---------------------------------------------

    def test_results_are_unchanged_by_indexes(self):
        for name in ("recent_order_count", "customer_by_email", "daily_sales", "paid_by_customer"):
            sql, params = it.QUERIES[name], it.SAMPLE_PARAMS[name]
            self.assertEqual(
                sorted(self.conn.execute(sql, params).fetchall()),
                sorted(self.plain.execute(sql, params).fetchall()),
                name,
            )
        # LIMIT 付きの問い合わせは、同時刻の行の選ばれ方が計画で変わりうるので、並びの値だけを比べる
        for name, col in (("orders_of_customer", 1), ("pending_orders", 2)):
            sql, params = it.QUERIES[name], it.SAMPLE_PARAMS[name]
            got = [row[col] for row in self.conn.execute(sql, params)]
            expected = [row[col] for row in self.plain.execute(sql, params)]
            self.assertEqual(got, expected, name)


class KeysetPaginationTest(unittest.TestCase):
    def setUp(self):
        self.conn = it.create_database(n_customers=200, n_orders=5000, seed=7)

    def tearDown(self):
        self.conn.close()

    def all_rows(self):
        return self.conn.execute(it.FIRST_PAGE_SQL.replace("LIMIT :page_size", "")).fetchall()

    def paginate(self, page_size):
        pages, after = [], None
        while True:
            page = it.fetch_page(self.conn, after, page_size)
            if not page:
                return pages
            self.assertLessEqual(len(page), page_size)
            pages.append(page)
            after = (page[-1][1], page[-1][0])
            self.assertLess(len(pages), 10_000, "ページングが終わりません")

    def test_sql_does_not_use_offset(self):
        self.assertNotIn("OFFSET", it.keyset_page_sql().upper())

    def test_pages_cover_all_rows_exactly_once(self):
        expected = self.all_rows()
        ties = len(expected) - len({row[1] for row in expected})
        self.assertGreater(ties, 10, "テストデータには同時刻の注文が含まれている")
        for page_size in (97, 500):
            rows = [row for page in self.paginate(page_size) for row in page]
            self.assertEqual(len(rows), len(expected), f"page_size={page_size}: 行数（取りこぼし・重複）")
            self.assertEqual(rows, expected, f"page_size={page_size}: 並び順")

    def test_ties_at_page_boundary(self):
        conn = it.create_database(n_customers=1, n_orders=0)
        same = "2025-05-05 05:05:00"
        conn.executemany(
            "INSERT INTO orders VALUES (?, 1, 'paid', ?, 100, NULL)",
            [(i, same) for i in range(1, 8)] + [(8, "2025-05-05 05:06:00"), (9, "2025-05-05 05:04:00")],
        )
        self.conn.close()
        self.conn = conn
        ids = [row[0] for page in self.paginate(2) for row in page]
        self.assertEqual(ids, [8, 7, 6, 5, 4, 3, 2, 1, 9],
                         "同時刻の行は id の降順。created_at だけで比べると境目の行を取りこぼす")

    def test_first_page_and_end(self):
        first = it.fetch_page(self.conn, None, 3)
        self.assertEqual(first, self.all_rows()[:3])
        oldest = self.all_rows()[-1]
        self.assertEqual(it.fetch_page(self.conn, (oldest[1], oldest[0]), 10), [])

    def test_invalid_page_size(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                it.fetch_page(self.conn, None, bad)


if __name__ == "__main__":
    unittest.main()
