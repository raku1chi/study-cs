"""12.1 演習2: 増分・冪等な ETL と SCD Type 2 — テスト

実行: python3 tools/check.py 12.1   （またはこのディレクトリで python3 -m unittest -v test_scd_etl）
"""
import datetime as dt
import random
import sqlite3
import unittest

from scd_etl import (
    INFERRED,
    MIN_TIME,
    apply_customer_change,
    create_source,
    create_warehouse,
    dump_warehouse,
    extract_changed,
    get_watermark,
    lookup_customer_sk,
    run_etl,
)


class Source:
    """テスト用の業務 DB（ソース）。updated_at は呼び出し側が明示する。"""

    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        create_source(self.conn)

    def add_customer(self, cid, name, prefecture, tier, at):
        self.conn.execute("INSERT INTO customers VALUES (?, ?, ?, ?, ?)", (cid, name, prefecture, tier, at))
        self.conn.commit()

    def update_customer(self, cid, at, **changes):
        sets = ", ".join(f"{k} = ?" for k in changes)
        self.conn.execute(f"UPDATE customers SET {sets}, updated_at = ? WHERE customer_id = ?",
                          (*changes.values(), at, cid))
        self.conn.commit()

    def add_order(self, oid, cid, ordered_at, amount, at=None):
        self.conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", (oid, cid, ordered_at, amount, at or ordered_at))
        self.conn.commit()

    def update_order(self, oid, at, **changes):
        sets = ", ".join(f"{k} = ?" for k in changes)
        self.conn.execute(f"UPDATE orders SET {sets}, updated_at = ? WHERE order_id = ?", (*changes.values(), at, oid))
        self.conn.commit()


def versions(dw, cid):
    return dw.execute(
        "SELECT customer_sk, name, prefecture, tier, valid_from, valid_to, is_current, is_inferred"
        " FROM dim_customer WHERE customer_id = ? ORDER BY valid_from", (cid,)).fetchall()


def fact(dw, oid):
    return dw.execute("SELECT customer_sk, date_key, ordered_at, amount FROM fact_orders WHERE order_id = ?",
                      (oid,)).fetchone()


class ScdEtlTestCase(unittest.TestCase):
    def setUp(self):
        self.src = Source()
        self.dw = sqlite3.connect(":memory:")
        create_warehouse(self.dw)
        s = self.src
        s.add_customer(1, "佐藤", "東京都", "regular", "2026-04-01T09:00:00")
        s.add_customer(2, "鈴木", "大阪府", "gold", "2026-04-01T09:05:00")
        s.add_customer(3, "高橋", "福岡県", "regular", "2026-04-01T09:10:00")
        s.add_order(101, 1, "2026-04-01T10:00:00", 3000)
        s.add_order(102, 2, "2026-04-02T11:00:00", 5000)
        s.add_order(103, 1, "2026-04-04T12:00:00", 1200)

    def tearDown(self):
        self.src.conn.close()
        self.dw.close()

    def sk(self, cid, current=True):
        row = self.dw.execute("SELECT customer_sk FROM dim_customer WHERE customer_id = ? AND is_current = ?",
                              (cid, int(current))).fetchone()
        return row[0]


class TestExtract(ScdEtlTestCase):
    def test_full_and_incremental_extract(self):
        rows = extract_changed(self.src.conn, "customers", None)
        self.assertEqual([r["customer_id"] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0], {"customer_id": 1, "name": "佐藤", "prefecture": "東京都",
                                   "tier": "regular", "updated_at": "2026-04-01T09:00:00"})
        # ウォーターマークと同じ時刻の行は含めない（厳密に「より後」）
        rows = extract_changed(self.src.conn, "customers", "2026-04-01T09:05:00")
        self.assertEqual([r["customer_id"] for r in rows], [3])

    def test_extract_orders_by_updated_at(self):
        self.src.update_order(101, "2026-04-05T00:00:00", amount=3100)
        rows = extract_changed(self.src.conn, "orders", "2026-04-01T10:00:00")
        self.assertEqual([r["order_id"] for r in rows], [102, 103, 101])

    def test_rejects_unknown_table(self):
        with self.assertRaises(ValueError):
            extract_changed(self.src.conn, "customers; DROP TABLE orders", None)


class TestInitialLoad(ScdEtlTestCase):
    def test_initial_load(self):
        stats = run_etl(self.src.conn, self.dw)
        self.assertEqual(stats, {"customers.inserted": 3, "orders.inserted": 3})
        for cid in (1, 2, 3):
            v = versions(self.dw, cid)
            self.assertEqual(len(v), 1)
            self.assertEqual(v[0][4:], (MIN_TIME, None, 1, 0), "初回のバージョンは過去全体に有効で現行")
        self.assertEqual(fact(self.dw, 101), (self.sk(1), 20260401, "2026-04-01T10:00:00", 3000))
        self.assertEqual(fact(self.dw, 102)[0], self.sk(2))
        self.assertEqual(get_watermark(self.dw, "customers"), "2026-04-01T09:10:00")
        self.assertEqual(get_watermark(self.dw, "orders"), "2026-04-04T12:00:00")

    def test_date_dimension(self):
        run_etl(self.src.conn, self.dw)
        rows = self.dw.execute("SELECT * FROM dim_date ORDER BY date_key").fetchall()
        self.assertEqual(rows, [
            (20260401, "2026-04-01", 2026, 4, 1, 2, 0),  # 水曜日
            (20260402, "2026-04-02", 2026, 4, 2, 3, 0),
            (20260404, "2026-04-04", 2026, 4, 4, 5, 1),  # 土曜日
        ])

    def test_rerun_is_noop(self):
        run_etl(self.src.conn, self.dw)
        before = dump_warehouse(self.dw)
        self.assertEqual(run_etl(self.src.conn, self.dw), {})
        self.assertEqual(dump_warehouse(self.dw), before)


class TestScdType2(ScdEtlTestCase):
    def setUp(self):
        super().setUp()
        run_etl(self.src.conn, self.dw)
        self.old_sk = self.sk(1)
        self.src.update_customer(1, "2026-04-10T00:00:00", tier="gold")

    def test_type2_change_creates_new_version(self):
        stats = run_etl(self.src.conn, self.dw)
        self.assertEqual(stats, {"customers.new_version": 1})
        v = versions(self.dw, 1)
        self.assertEqual(len(v), 2)
        self.assertEqual(v[0][0], self.old_sk)
        self.assertEqual(v[0][3:7], ("regular", MIN_TIME, "2026-04-10T00:00:00", 0))
        self.assertEqual(v[1][3:7], ("gold", "2026-04-10T00:00:00", None, 1))
        self.assertNotEqual(v[1][0], self.old_sk, "新しいバージョンには新しいサロゲートキー")

    def test_facts_point_to_version_valid_at_order_time(self):
        self.src.add_order(104, 1, "2026-04-12T15:00:00", 8000)
        # 変更より前の時刻の注文が、変更と同じバッチで遅れて届くこともある
        self.src.add_order(105, 1, "2026-04-09T23:59:59", 700, at="2026-04-12T16:00:00")
        run_etl(self.src.conn, self.dw)
        new_sk = self.sk(1)
        self.assertEqual(fact(self.dw, 101)[0], self.old_sk, "過去の注文は過去のバージョンのまま")
        self.assertEqual(fact(self.dw, 103)[0], self.old_sk)
        self.assertEqual(fact(self.dw, 104)[0], new_sk)
        self.assertEqual(fact(self.dw, 105)[0], self.old_sk)

    def test_lookup_uses_half_open_interval(self):
        run_etl(self.src.conn, self.dw)
        new_sk = self.sk(1)
        self.assertEqual(lookup_customer_sk(self.dw, 1, "2026-04-09T23:59:59"), self.old_sk)
        self.assertEqual(lookup_customer_sk(self.dw, 1, "2026-04-10T00:00:00"), new_sk)
        self.assertEqual(lookup_customer_sk(self.dw, 1, "2030-01-01T00:00:00"), new_sk)
        self.assertIsNone(lookup_customer_sk(self.dw, 999, "2026-04-10T00:00:00"))

    def test_type1_change_overwrites_all_versions(self):
        run_etl(self.src.conn, self.dw)
        self.src.update_customer(1, "2026-04-11T00:00:00", name="佐藤 花子")
        self.assertEqual(run_etl(self.src.conn, self.dw), {"customers.type1_updated": 1})
        v = versions(self.dw, 1)
        self.assertEqual(len(v), 2, "Type 1 の変更ではバージョンを増やさない")
        self.assertEqual({row[1] for row in v}, {"佐藤 花子"}, "過去のバージョンの名前も上書きされる")

    def test_type1_and_type2_change_at_once(self):
        run_etl(self.src.conn, self.dw)
        self.src.update_customer(1, "2026-04-20T00:00:00", name="佐藤 花子", prefecture="神奈川県")
        self.assertEqual(run_etl(self.src.conn, self.dw), {"customers.new_version": 1})
        v = versions(self.dw, 1)
        self.assertEqual(len(v), 3)
        self.assertEqual([row[1] for row in v], ["佐藤 花子"] * 3)
        self.assertEqual([row[2] for row in v], ["東京都", "東京都", "神奈川県"])

    def test_stale_type2_change_is_rejected(self):
        run_etl(self.src.conn, self.dw)
        stale = {"customer_id": 1, "name": "佐藤", "prefecture": "東京都", "tier": "platinum",
                 "updated_at": "2026-04-05T00:00:00"}
        with self.assertRaises(ValueError):
            apply_customer_change(self.dw, stale)

    def test_history_cannot_be_rebuilt_from_current_snapshot(self):
        run_etl(self.src.conn, self.dw)
        fresh = sqlite3.connect(":memory:")
        create_warehouse(fresh)
        run_etl(self.src.conn, fresh)
        # ソースは現在の状態しか持たないので、あとから作り直した DW には履歴がない
        self.assertEqual(len(versions(self.dw, 1)), 2)
        self.assertEqual(len(versions(fresh, 1)), 1)
        fresh.close()


class TestIdempotencyAndRecovery(ScdEtlTestCase):
    def test_full_refresh_after_incremental_changes_nothing(self):
        run_etl(self.src.conn, self.dw)
        self.src.update_customer(2, "2026-04-05T00:00:00", tier="platinum")
        self.src.add_order(104, 2, "2026-04-06T09:00:00", 9900)
        run_etl(self.src.conn, self.dw)
        self.src.update_order(102, "2026-04-07T00:00:00", amount=5500)
        run_etl(self.src.conn, self.dw)
        before = dump_warehouse(self.dw)
        stats = run_etl(self.src.conn, self.dw, full_refresh=True)
        self.assertEqual(stats, {"customers.unchanged": 3, "orders.unchanged": 4})
        self.assertEqual(dump_warehouse(self.dw), before)

    def test_order_update_is_upsert(self):
        run_etl(self.src.conn, self.dw)
        self.src.update_order(102, "2026-04-07T00:00:00", amount=5500)
        self.assertEqual(run_etl(self.src.conn, self.dw), {"orders.updated": 1})
        self.assertEqual(fact(self.dw, 102)[3], 5500)
        self.assertEqual(self.dw.execute("SELECT COUNT(*) FROM fact_orders").fetchone()[0], 3)

    def test_late_arriving_customer_uses_inferred_member(self):
        run_etl(self.src.conn, self.dw)
        self.src.add_order(201, 9, "2026-04-08T10:00:00", 4000)
        self.assertEqual(run_etl(self.src.conn, self.dw), {"orders.inserted": 1})
        v = versions(self.dw, 9)
        self.assertEqual(len(v), 1)
        placeholder_sk = v[0][0]
        self.assertEqual(v[0][1:], (INFERRED, INFERRED, INFERRED, MIN_TIME, None, 1, 1))
        self.assertEqual(fact(self.dw, 201)[0], placeholder_sk)

        self.src.add_customer(9, "伊藤", "北海道", "regular", "2026-04-08T12:00:00")
        self.assertEqual(run_etl(self.src.conn, self.dw), {"customers.inferred_resolved": 1})
        v = versions(self.dw, 9)
        self.assertEqual(len(v), 1, "推定メンバーは新しいバージョンを作らずに埋める")
        self.assertEqual(v[0], (placeholder_sk, "伊藤", "北海道", "regular", MIN_TIME, None, 1, 0))
        self.assertEqual(fact(self.dw, 201)[0], placeholder_sk, "事実を直す必要がない")

    def test_failed_run_rolls_back_everything(self):
        run_etl(self.src.conn, self.dw)
        before = dump_warehouse(self.dw)
        self.src.update_customer(2, "2026-04-05T00:00:00", tier="platinum")  # 正常な変更
        self.src.add_order(104, 2, "2026-04-06T09:00:00", None)  # 不正なデータ
        with self.assertRaises(ValueError):
            run_etl(self.src.conn, self.dw)
        self.assertEqual(dump_warehouse(self.dw), before, "途中までの書き込みも残してはいけない")

        self.src.update_order(104, "2026-04-06T10:00:00", amount=100)  # ソースを直して再実行
        stats = run_etl(self.src.conn, self.dw)
        self.assertEqual(stats, {"customers.new_version": 1, "orders.inserted": 1})

    def test_invariants_under_random_changes(self):
        rng = random.Random(42)
        clock = dt.datetime(2026, 5, 1)
        next_order = 1000
        prefectures = ["東京都", "大阪府", "愛知県", "福岡県"]
        tiers = ["regular", "gold", "platinum"]

        def tick():
            nonlocal clock
            clock += dt.timedelta(minutes=rng.randrange(1, 180))
            return clock.isoformat(timespec="seconds")

        for step in range(60):
            r = rng.random()
            cid = rng.choice([1, 2, 3, 4])
            if r < 0.3:
                at = tick()
                if cid == 4 and not self.src.conn.execute("SELECT 1 FROM customers WHERE customer_id = 4").fetchone():
                    self.src.add_customer(4, "渡辺", rng.choice(prefectures), rng.choice(tiers), at)
                else:
                    self.src.update_customer(cid, at, prefecture=rng.choice(prefectures), tier=rng.choice(tiers))
            elif r < 0.4:
                self.src.update_customer(rng.choice([1, 2, 3]), tick(), name=f"顧客{step}")
            else:
                at = tick()
                self.src.add_order(next_order, cid, at, rng.randrange(100, 10000))
                next_order += 1
            if rng.random() < 0.3:
                run_etl(self.src.conn, self.dw)
        run_etl(self.src.conn, self.dw)

        for cid in (1, 2, 3, 4):
            v = versions(self.dw, cid)
            self.assertEqual(sum(row[6] for row in v), 1, f"顧客 {cid} の現行バージョンは 1 つ")
            self.assertEqual(v[0][4], MIN_TIME)
            for older, newer in zip(v, v[1:]):
                self.assertEqual(older[5], newer[4], "期間は隙間なく連続する")
            self.assertIsNone(v[-1][5])
        # すべての事実が「注文時点で有効だったバージョン」を指している
        rows = self.dw.execute(
            "SELECT f.order_id, f.ordered_at, d.valid_from, d.valid_to FROM fact_orders f"
            " JOIN dim_customer d USING (customer_sk)").fetchall()
        self.assertEqual(len(rows), next_order - 1000 + 3)
        for oid, at, vf, vt in rows:
            self.assertTrue(vf <= at and (vt is None or at < vt), (oid, at, vf, vt))
        before = dump_warehouse(self.dw)
        run_etl(self.src.conn, self.dw, full_refresh=True)
        self.assertEqual(dump_warehouse(self.dw), before)


if __name__ == "__main__":
    unittest.main()
