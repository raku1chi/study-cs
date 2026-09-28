"""6.3 演習3（在庫の引き当て）のテスト

実行: python3 tools/check.py 6.3   （またはこのディレクトリで python3 -m unittest -v test_inventory）

同じデータベースファイルに複数の接続を開き、処理の割り込みを再現します。
一部のテストはスレッドで本当に同時に実行します（タイムアウト付き）。
"""
import os
import tempfile
import threading
import unittest

import inventory as inv


class InventoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "shop.db")
        inv.setup(self.path, {1: 10, 2: 5, 3: 0})
        self.a = inv.connect(self.path)
        self.b = inv.connect(self.path)

    def tearDown(self):
        self.a.close()
        self.b.close()
        self.tmp.cleanup()

    def version(self, product_id):
        return self.a.execute("SELECT version FROM products WHERE id = ?", (product_id,)).fetchone()[0]

    def count(self, table):
        return self.a.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def run_threads(self, target, n):
        """n 個のスレッドで target(i) を同時に実行し、結果のリストを返す（例外は送り直す）。"""
        barrier = threading.Barrier(n)
        results, errors = [None] * n, []

        def worker(i):
            try:
                barrier.wait(timeout=10)
                results[i] = target(i)
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertFalse(any(t.is_alive() for t in threads), "スレッドが終わりません（ロックの解放漏れ？）")
        if errors:
            raise errors[0]
        return results


class TestNaive(InventoryTestCase):
    def test_naive_read_modify_write_loses_update(self):
        # A が在庫 10 を読んだ後、書く前に B が 2 個引き当てる。A は古い値 10 から 7 を書き込む
        ok_a = inv.reserve_naive(self.a, 1, 3, between=lambda: inv.reserve_naive(self.b, 1, 2))
        self.assertTrue(ok_a)
        self.assertEqual(inv.get_stock(self.a, 1), 7, "本来は 10 - 3 - 2 = 5。B の引き当てが失われた（ロストアップデート）")


class TestAtomic(InventoryTestCase):
    def test_reserve_and_insufficient(self):
        self.assertTrue(inv.reserve_atomic(self.a, 1, 3))
        self.assertEqual(inv.get_stock(self.a, 1), 7)
        self.assertFalse(inv.reserve_atomic(self.a, 1, 8), "在庫 7 に 8 個は引き当てられない")
        self.assertEqual(inv.get_stock(self.a, 1), 7, "失敗したら在庫は変わらない")
        self.assertTrue(inv.reserve_atomic(self.b, 1, 7))
        self.assertEqual(inv.get_stock(self.a, 1), 0)
        self.assertFalse(inv.reserve_atomic(self.a, 1, 1))
        self.assertFalse(inv.reserve_atomic(self.a, 3, 1), "在庫 0 の商品")

    def test_increments_version(self):
        inv.reserve_atomic(self.a, 1, 1)
        inv.reserve_atomic(self.a, 1, 1)
        self.assertEqual(self.version(1), 2, "在庫を変えたら version も増やす（楽観的並行制御との併用のため）")
        inv.reserve_atomic(self.a, 1, 100)
        self.assertEqual(self.version(1), 2, "失敗した引き当ては何も変えない")

    def test_errors(self):
        with self.assertRaises(ValueError):
            inv.reserve_atomic(self.a, 1, 0)
        with self.assertRaises(ValueError):
            inv.reserve_atomic(self.a, 1, -1)
        with self.assertRaises(KeyError):
            inv.reserve_atomic(self.a, 999, 1)

    def test_concurrent_threads_never_oversell(self):
        conn_setup = inv.connect(self.path)
        conn_setup.execute("UPDATE products SET stock = 100 WHERE id = 1")
        conn_setup.close()

        def worker(i):
            conn = inv.connect(self.path)
            try:
                return sum(inv.reserve_atomic(conn, 1, 1) for _ in range(40))
            finally:
                conn.close()

        successes = self.run_threads(worker, 4)  # 4 スレッド × 40 回 = 160 回の要求に対して在庫 100
        self.assertEqual(sum(successes), 100, "ちょうど在庫の数だけ成功する")
        self.assertEqual(inv.get_stock(self.a, 1), 0)


class TestOptimistic(InventoryTestCase):
    def test_success_increments_version(self):
        self.assertTrue(inv.reserve_optimistic(self.a, 1, 4))
        self.assertEqual(inv.get_stock(self.a, 1), 6)
        self.assertEqual(self.version(1), 1)

    def test_conflict_is_detected_and_retried(self):
        attempts = []

        def interfere(attempt):
            attempts.append(attempt)
            if attempt == 0:  # 最初の試行でだけ、B が割り込んで引き当てる
                self.assertTrue(inv.reserve_optimistic(self.b, 1, 2))

        self.assertTrue(inv.reserve_optimistic(self.a, 1, 3, on_read=interfere))
        self.assertEqual(attempts, [0, 1], "1 回目は競合で失敗し、2 回目で成功する")
        self.assertEqual(inv.get_stock(self.a, 1), 5, "10 - 2 - 3 = 5。更新は失われない")
        self.assertEqual(self.version(1), 2)

    def test_mixing_with_atomic_update_is_still_safe(self):
        def interfere(attempt):
            if attempt == 0:
                self.assertTrue(inv.reserve_atomic(self.b, 1, 2))  # version を増やす更新

        self.assertTrue(inv.reserve_optimistic(self.a, 1, 3, on_read=interfere))
        self.assertEqual(inv.get_stock(self.a, 1), 5)

    def test_gives_up_after_max_retries(self):
        attempts = []

        def always_interfere(attempt):
            attempts.append(attempt)
            self.assertTrue(inv.reserve_optimistic(self.b, 1, 1))

        with self.assertRaises(inv.ConflictError):
            inv.reserve_optimistic(self.a, 1, 1, max_retries=2, on_read=always_interfere)
        self.assertEqual(attempts, [0, 1, 2], "最初の試行 + 再試行 2 回")
        self.assertEqual(inv.get_stock(self.a, 1), 7, "割り込んだ 3 回分だけが反映される")

    def test_insufficient_stock_is_not_retried(self):
        calls = []
        self.assertFalse(inv.reserve_optimistic(self.a, 2, 6, on_read=calls.append))
        self.assertEqual(calls, [], "在庫が足りなければ、書き込みを試みずに False")
        self.assertEqual((inv.get_stock(self.a, 2), self.version(2)), (5, 0))

    def test_errors(self):
        with self.assertRaises(ValueError):
            inv.reserve_optimistic(self.a, 1, 0)
        with self.assertRaises(KeyError):
            inv.reserve_optimistic(self.a, 999, 1)


class TestPlaceOrder(InventoryTestCase):
    def test_created(self):
        self.assertEqual(inv.place_order(self.a, "req-1", {1: 2, 2: 1}), "created")
        self.assertEqual((inv.get_stock(self.a, 1), inv.get_stock(self.a, 2)), (8, 4))
        self.assertEqual(self.count("orders"), 1)
        items = self.a.execute("SELECT product_id, quantity FROM order_items ORDER BY product_id").fetchall()
        self.assertEqual(items, [(1, 2), (2, 1)])
        self.assertFalse(self.a.in_transaction, "トランザクションを開いたままにしない")

    def test_all_or_nothing(self):
        self.assertEqual(inv.place_order(self.a, "req-1", {1: 2, 2: 6}), "insufficient_stock")
        self.assertEqual(inv.get_stock(self.a, 1), 10, "商品 1 を減らした後で商品 2 が足りなかった → 商品 1 も元に戻る")
        self.assertEqual((self.count("orders"), self.count("order_items")), (0, 0))
        self.assertFalse(self.a.in_transaction)

    def test_duplicate_request_is_applied_once(self):
        self.assertEqual(inv.place_order(self.a, "req-1", {1: 2}), "created")
        self.assertEqual(inv.place_order(self.a, "req-1", {1: 2}), "duplicate")
        self.assertEqual(inv.place_order(self.b, "req-1", {1: 2}), "duplicate", "別の接続からの再送も検出する")
        self.assertEqual(inv.get_stock(self.a, 1), 8, "在庫は 1 回分だけ減る")
        self.assertEqual(self.count("orders"), 1)
        self.assertFalse(self.a.in_transaction or self.b.in_transaction)

    def test_failed_request_can_be_retried(self):
        self.assertEqual(inv.place_order(self.a, "req-9", {3: 1}), "insufficient_stock")
        self.a.execute("UPDATE products SET stock = 5 WHERE id = 3")  # 入荷
        self.assertEqual(inv.place_order(self.a, "req-9", {3: 1}), "created")

    def test_unknown_product_rolls_back(self):
        with self.assertRaises(KeyError):
            inv.place_order(self.a, "req-1", {1: 1, 999: 1})
        self.assertEqual(inv.get_stock(self.a, 1), 10)
        self.assertEqual(self.count("orders"), 0)
        self.assertFalse(self.a.in_transaction)

    def test_validation(self):
        with self.assertRaises(ValueError):
            inv.place_order(self.a, "req-1", {})
        with self.assertRaises(ValueError):
            inv.place_order(self.a, "req-1", {1: 0})
        self.assertFalse(self.a.in_transaction)

    def test_concurrent_duplicates_create_exactly_one_order(self):
        def worker(i):
            conn = inv.connect(self.path)
            try:
                return inv.place_order(conn, "same-request", {1: 3})
            finally:
                conn.close()

        results = self.run_threads(worker, 4)  # 同じ要求が 4 回同時に届く
        self.assertEqual(sorted(results), ["created", "duplicate", "duplicate", "duplicate"])
        self.assertEqual(inv.get_stock(self.a, 1), 7)

    def test_concurrent_orders_do_not_oversell(self):
        def worker(i):
            conn = inv.connect(self.path)
            try:
                return [inv.place_order(conn, f"req-{i}-{k}", {1: 1, 2: 1}) for k in range(3)]
            finally:
                conn.close()

        results = [r for rs in self.run_threads(worker, 4) for r in rs]  # 12 件の注文、商品 2 は在庫 5
        self.assertEqual(results.count("created"), 5)
        self.assertEqual(results.count("insufficient_stock"), 7)
        self.assertEqual((inv.get_stock(self.a, 1), inv.get_stock(self.a, 2)), (5, 0))
        self.assertEqual(self.count("orders"), 5)


if __name__ == "__main__":
    unittest.main()
