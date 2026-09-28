"""6.3 演習1（MVCC）のテスト

実行: python3 tools/check.py 6.3   （またはこのディレクトリで python3 -m unittest -v test_mvcc）
発展課題（serializable=True）を実装していない場合、そのテストはスキップされます。
"""
import unittest

from mvcc import MVCCStore, SerializationError, TransactionError


def setup_store(data, **kwargs):
    store = MVCCStore(**kwargs)
    t = store.begin()
    for k, v in data.items():
        t.put(k, v)
    t.commit()
    return store


def run_with_retry(store, work, max_attempts=5):
    """SerializationError なら最初からやり直す（アプリケーションの定番の書き方）。"""
    for attempt in range(1, max_attempts + 1):
        txn = store.begin()
        work(txn)
        try:
            txn.commit()
            return attempt
        except SerializationError:
            continue
    raise AssertionError("再試行しても成功しなかった")


class TestSnapshotIsolation(unittest.TestCase):
    def test_commit_makes_writes_visible(self):
        store = MVCCStore()
        t1 = store.begin()
        t1.put("x", 1)
        self.assertEqual(t1.commit(), 1, "最初のコミットの commit_ts は 1")
        self.assertEqual(t1.status, "committed")
        t2 = store.begin()
        self.assertEqual(t2.start_ts, 1)
        self.assertEqual(t2.get("x"), 1)

    def test_uncommitted_writes_are_invisible(self):
        store = setup_store({"x": 1})
        writer = store.begin()
        writer.put("x", 2)
        reader = store.begin()
        self.assertEqual(reader.get("x"), 1, "コミット前の書き込みは見えない（ダーティリードが起きない）")

    def test_read_your_own_writes(self):
        store = setup_store({"x": 1, "y": 2})
        t = store.begin()
        t.put("x", 10)
        self.assertEqual(t.get("x"), 10)
        t.delete("y")
        self.assertIsNone(t.get("y"))
        self.assertEqual(t.get("y", "none"), "none")
        t.put("y", 20)
        self.assertEqual(t.get("y"), 20)
        self.assertIsNone(t.get("missing"))

    def test_snapshot_is_stable(self):
        store = setup_store({"x": 1})
        t1 = store.begin()
        self.assertEqual(t1.get("x"), 1)
        t2 = store.begin()
        t2.put("x", 2)
        t2.commit()
        self.assertEqual(t1.get("x"), 1, "同じトランザクションでは同じ値が読める（反復不能読み取りが起きない）")
        self.assertEqual(store.begin().get("x"), 2, "後から始めたトランザクションには新しい値が見える")

    def test_snapshot_taken_at_begin(self):
        store = setup_store({"x": 1})
        t1 = store.begin()          # まだ何も読んでいない
        t2 = store.begin()
        t2.put("x", 2)
        t2.commit()
        self.assertEqual(t1.get("x"), 1, "スナップショットは begin() の時点で決まる")

    def test_scan_has_no_phantoms(self):
        store = setup_store({"order:1": "a", "order:2": "b", "user:1": "u"})
        t1 = store.begin()
        first = t1.scan("order:")
        self.assertEqual(first, {"order:1": "a", "order:2": "b"})
        t2 = store.begin()
        t2.put("order:3", "c")
        t2.delete("order:1")
        t2.commit()
        self.assertEqual(t1.scan("order:"), first, "同じ条件の読み取りで行が増減しない（ファントムが起きない）")
        self.assertEqual(store.begin().scan("order:"), {"order:2": "b", "order:3": "c"})

    def test_scan_includes_own_writes_sorted(self):
        store = setup_store({"k:b": 2, "k:a": 1})
        t = store.begin()
        t.put("k:c", 3)
        t.delete("k:a")
        t.put("other", 0)
        result = t.scan("k:")
        self.assertEqual(result, {"k:b": 2, "k:c": 3})
        self.assertEqual(list(result), ["k:b", "k:c"], "キーの昇順")
        self.assertEqual(set(t.scan()), {"k:b", "k:c", "other"})

    def test_abort_discards_writes(self):
        store = setup_store({"x": 1})
        t = store.begin()
        t.put("x", 99)
        t.put("new", 1)
        t.abort()
        self.assertEqual(t.status, "aborted")
        after = store.begin()
        self.assertEqual((after.get("x"), after.get("new")), (1, None))

    def test_finished_transactions_reject_operations(self):
        store = MVCCStore()
        t = store.begin()
        t.commit()
        for op in (lambda: t.get("x"), lambda: t.put("x", 1), lambda: t.delete("x"),
                   lambda: t.scan(), t.commit, t.abort):
            with self.assertRaises(TransactionError):
                op()
        a = store.begin()
        a.abort()
        with self.assertRaises(TransactionError):
            a.commit()

    def test_delete_and_reinsert_across_transactions(self):
        store = setup_store({"x": 1})
        t = store.begin()
        t.delete("x")
        t.commit()
        self.assertIsNone(store.begin().get("x"))
        t = store.begin()
        t.put("x", 3)
        t.commit()
        self.assertEqual(store.begin().get("x"), 3)


class TestConflicts(unittest.TestCase):
    def test_lost_update_is_prevented(self):
        store = setup_store({"counter": 0})
        t1, t2 = store.begin(), store.begin()
        t1.put("counter", t1.get("counter") + 1)
        t2.put("counter", t2.get("counter") + 1)
        t1.commit()
        with self.assertRaises(SerializationError):
            t2.commit()
        self.assertEqual(t2.status, "aborted")
        self.assertEqual(store.begin().get("counter"), 1, "t2 の書き込みは反映されない")

    def test_retry_makes_both_increments_count(self):
        store = setup_store({"counter": 0})
        t1 = store.begin()
        t1.put("counter", t1.get("counter") + 1)
        # t1 のコミット前に、別のトランザクションが同じカウンタを増やしてコミットする
        attempts = run_with_retry(store, lambda t: t.put("counter", t.get("counter") + 1))
        self.assertEqual(attempts, 1)
        with self.assertRaises(SerializationError):
            t1.commit()
        attempts = run_with_retry(store, lambda t: t.put("counter", t.get("counter") + 1))
        self.assertEqual(store.begin().get("counter"), 2, "中断されたら再試行する。そうすれば更新は失われない")

    def test_blind_writes_also_conflict(self):
        store = MVCCStore()
        t1, t2 = store.begin(), store.begin()
        t1.put("x", "a")
        t2.put("x", "b")
        t2.commit()
        with self.assertRaises(SerializationError, msg="読んでいなくても、同じキーへの並行した書き込みは衝突"):
            t1.commit()

    def test_disjoint_writes_do_not_conflict(self):
        store = setup_store({"x": 0, "y": 0})
        t1, t2 = store.begin(), store.begin()
        t1.put("x", 1)
        t2.put("y", 1)
        t1.commit()
        t2.commit()
        t3 = store.begin()
        self.assertEqual((t3.get("x"), t3.get("y")), (1, 1))

    def test_no_conflict_with_earlier_commits(self):
        store = setup_store({"x": 0})
        t1 = store.begin()
        t1.put("x", 1)
        t1.commit()
        t2 = store.begin()  # t1 のコミットの後に開始
        t2.put("x", 2)
        t2.commit()
        self.assertEqual(store.begin().get("x"), 2)

    def test_delete_conflicts_with_update(self):
        store = setup_store({"x": 1})
        t1, t2 = store.begin(), store.begin()
        t1.delete("x")
        t2.put("x", 2)
        t1.commit()
        with self.assertRaises(SerializationError):
            t2.commit()

    def test_write_skew_is_allowed_under_snapshot_isolation(self):
        # 当直の医師は常に 1 人以上必要。2 人が同時に「もう 1 人いるから」と当直を外れる
        store = setup_store({"oncall:alice": True, "oncall:bob": True})
        t1, t2 = store.begin(), store.begin()
        for t, me in ((t1, "alice"), (t2, "bob")):
            on_call = sum(1 for v in t.scan("oncall:").values() if v)
            self.assertEqual(on_call, 2)
            if on_call >= 2:
                t.put(f"oncall:{me}", False)
        t1.commit()
        t2.commit()  # 書いたキーが異なるので first-committer-wins では検出されない
        final = store.begin().scan("oncall:")
        self.assertEqual(sum(final.values()), 0, "スナップショット分離では書き込みスキューが起きる")


class TestVacuum(unittest.TestCase):
    def test_versions_accumulate_and_vacuum_removes_old_ones(self):
        store = MVCCStore()
        for i in range(5):
            t = store.begin()
            t.put("x", i)
            t.commit()
        self.assertEqual(store.version_count(), 5, "更新のたびに新しいバージョンが増える")
        self.assertEqual(store.vacuum(), 4)
        self.assertEqual(store.version_count(), 1)
        self.assertEqual(store.begin().get("x"), 4)

    def test_long_running_transaction_blocks_vacuum(self):
        store = setup_store({"x": 0})
        old = store.begin()  # 長く実行中のトランザクション
        self.assertEqual(old.get("x"), 0)
        for i in range(1, 4):
            t = store.begin()
            t.put("x", i)
            t.commit()
        self.assertEqual(store.vacuum(), 0, "old のスナップショットが x=0 を必要としているので回収できない")
        self.assertEqual(old.get("x"), 0)
        self.assertEqual(store.version_count(), 4)
        old.commit()
        self.assertEqual(store.vacuum(), 3, "old が終われば回収できる")
        self.assertEqual(store.version_count(), 1)

    def test_vacuum_keeps_versions_needed_by_active_snapshots(self):
        store = setup_store({"x": 0})
        t = store.begin()
        t.put("x", 1)
        t.commit()
        reader = store.begin()  # x=1 を見るスナップショット
        t = store.begin()
        t.put("x", 2)
        t.commit()
        self.assertEqual(store.vacuum(), 1, "x=0 だけが回収できる")
        self.assertEqual(reader.get("x"), 1)
        self.assertEqual(store.begin().get("x"), 2)

    def test_tombstones_are_removed(self):
        store = setup_store({"x": 1, "y": 1})
        t = store.begin()
        t.delete("x")
        t.commit()
        self.assertEqual(store.version_count(), 3, "削除も（墓標という）新しいバージョン")
        self.assertEqual(store.vacuum(), 2)
        self.assertEqual(store.version_count(), 1)
        self.assertEqual(store.begin().scan(), {"y": 1})

    def test_vacuum_with_no_versions(self):
        self.assertEqual(MVCCStore().vacuum(), 0)
        self.assertEqual(MVCCStore().version_count(), 0)


class TestSerializableBonus(unittest.TestCase):
    """発展課題: serializable=True（簡略化した SSI）。未実装ならスキップする。"""

    def make(self, data):
        try:
            return setup_store(data, serializable=True)
        except NotImplementedError:
            self.skipTest("発展課題（serializable モード）は未実装")

    def doctors(self, first_committer):
        store = self.make({"oncall:alice": True, "oncall:bob": True})
        t1, t2 = store.begin(), store.begin()
        for t, me in ((t1, "alice"), (t2, "bob")):
            if sum(1 for v in t.scan("oncall:").values() if v) >= 2:
                t.put(f"oncall:{me}", False)
        order = (t1, t2) if first_committer == 1 else (t2, t1)
        results = []
        for t in order:
            try:
                t.commit()
                results.append("ok")
            except SerializationError:
                results.append("aborted")
        return store, results

    def test_write_skew_is_prevented(self):
        for first in (1, 2):
            store, results = self.doctors(first)
            self.assertIn("aborted", results, f"first_committer={first}: どちらかは中断されるはず")
            on_call = sum(store.begin().scan("oncall:").values())
            self.assertGreaterEqual(on_call, 1, "当直の医師が 1 人以上残ること")

    def test_write_skew_detected_even_if_first_commits_before_second_reads(self):
        store = self.make({"oncall:alice": True, "oncall:bob": True})
        t1, t2 = store.begin(), store.begin()
        if sum(1 for v in t1.scan("oncall:").values() if v) >= 2:
            t1.put("oncall:alice", False)
        t1.commit()  # t2 はまだ何も読んでいない
        if sum(1 for v in t2.scan("oncall:").values() if v) >= 2:  # t2 のスナップショットでは 2 人
            t2.put("oncall:bob", False)
        with self.assertRaises(SerializationError):
            t2.commit()

    def test_phantom_based_write_skew_is_prevented(self):
        # 会議室の予約: 同じ時間帯の予約がなければ予約する（存在しない行を読む → 挿入する）
        store = self.make({"room:1:10:00": "carol"})
        t1, t2 = store.begin(), store.begin()
        for t, who in ((t1, "dave"), (t2, "erin")):
            if not t.scan("room:2:"):
                t.put(f"room:2:11:00:{who}", who)
        results = []
        for t in (t1, t2):
            try:
                t.commit()
                results.append("ok")
            except SerializationError:
                results.append("aborted")
        self.assertIn("aborted", results, "書いたキーは別でも、読んだ範囲（接頭辞）に相手が書いているので危険")
        self.assertEqual(len(store.begin().scan("room:2:")), 1, "会議室 2 の予約は 1 件だけになること")

    def test_disjoint_transactions_still_commit(self):
        store = self.make({"a": 1, "b": 1})
        t1, t2 = store.begin(), store.begin()
        t1.put("a", t1.get("a") + 1)
        t2.put("b", t2.get("b") + 1)
        t1.commit()
        t2.commit()
        self.assertEqual(store.begin().scan(), {"a": 2, "b": 2})

    def test_read_only_transactions_commit(self):
        store = self.make({"x": 1, "y": 1})
        reader = store.begin()
        writer = store.begin()
        reader.get("x")
        writer.put("x", 2)
        writer.commit()
        reader.get("y")
        reader.commit()  # 読み取り専用は中断されない
        self.assertEqual(reader.status, "committed")

    def test_sequential_transactions_do_not_conflict(self):
        store = self.make({"oncall:alice": True, "oncall:bob": True})
        for me in ("alice", "bob"):
            t = store.begin()
            if sum(1 for v in t.scan("oncall:").values() if v) >= 2:
                t.put(f"oncall:{me}", False)
            t.commit()  # 並行していないので、どちらも中断されない
        self.assertEqual(store.begin().scan("oncall:"), {"oncall:alice": False, "oncall:bob": True})


if __name__ == "__main__":
    unittest.main()
