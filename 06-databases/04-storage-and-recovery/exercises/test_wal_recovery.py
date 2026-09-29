"""6.4 演習3（WAL による障害回復）のテスト

実行: python3 tools/check.py 6.4   （またはこのディレクトリで python3 -m unittest -v test_wal_recovery）
"""
import random
import unittest

from wal_recovery import Analysis, LogRecord, Page, analyze, recover, redo, undo


def U(lsn, txn, page, before, after):
    return LogRecord(lsn, "update", txn=txn, page=page, before=before, after=after)


def C(lsn, txn):
    return LogRecord(lsn, "commit", txn=txn)


def CLR(lsn, txn, page, after, undoes):
    return LogRecord(lsn, "clr", txn=txn, page=page, after=after, undoes=undoes)


def values(pages, names):
    return {n: pages.get(n, Page()).value for n in names}


# シナリオ A: チェックポイントなし。T2 のコミット前の変更を含む P1 がディスクに書かれていた（STEAL）
LOG_A = [
    U(1, 1, "P1", None, 10),
    U(2, 2, "P2", None, 20),
    C(3, 1),
    U(4, 2, "P1", 10, 11),
    U(5, 3, "P3", None, 30),
    C(6, 3),
]
DISK_A = {"P1": Page(11, 4)}

# シナリオ B: チェックポイントあり。A と C はチェックポイントの前にディスクへ書かれている
LOG_B = [
    U(1, 1, "A", None, 1),
    C(2, 1),
    U(3, 2, "B", None, 5),          # T2 の最初の変更はチェックポイントより前
    U(4, 5, "C", None, "c"),
    C(5, 5),
    LogRecord(6, "checkpoint", active=(2,), dirty=(("B", 3),)),
    U(7, 2, "A", 1, 2),
    U(8, 3, "D", None, 7),
    C(9, 3),
    U(10, 4, "B", 5, 6),
]
DISK_B = {"A": Page(1, 1), "C": Page("c", 4)}
EXPECTED_B = {"A": 1, "B": None, "C": "c", "D": 7}

# シナリオ D: 取り消しの途中でクラッシュした（abort と CLR 1 つ、end なし）
LOG_D = [
    U(1, 1, "A", None, 1),
    U(2, 1, "B", None, 2),
    U(3, 1, "C", None, 3),
    LogRecord(4, "abort", txn=1),
    CLR(5, 1, "C", None, 3),
]
DISK_D = {"A": Page(1, 1), "B": Page(2, 2), "C": Page(3, 3)}


class TestAnalysis(unittest.TestCase):
    def test_without_checkpoint(self):
        self.assertEqual(analyze(LOG_A), Analysis(frozenset({1, 3}), frozenset({2}), 1))

    def test_with_checkpoint(self):
        a = analyze(LOG_B)
        self.assertEqual(a.winners, frozenset({3}))
        self.assertEqual(a.losers, frozenset({2, 4}), "チェックポイントの active（T2）と、その後に現れた T4")
        self.assertEqual(a.redo_lsn, 3, "チェックポイントと dirty の recLSN の最小値")

    def test_ended_transactions_are_not_losers(self):
        log = [U(1, 1, "A", None, 1), LogRecord(2, "abort", txn=1), CLR(3, 1, "A", None, 1), LogRecord(4, "end", txn=1)]
        self.assertEqual(analyze(log).losers, frozenset())
        self.assertEqual(analyze(LOG_D).losers, frozenset({1}), "abort はしたが end がない → 取り消しを続ける")

    def test_empty_log(self):
        self.assertEqual(analyze([]), Analysis(frozenset(), frozenset(), 1))

    def test_validation(self):
        with self.assertRaises(ValueError):
            analyze([U(2, 1, "A", None, 1), U(2, 1, "A", 1, 2)])
        with self.assertRaises(ValueError):
            analyze([LogRecord(1, "bogus")])


class TestRedo(unittest.TestCase):
    def test_repeats_history_and_skips_applied_changes(self):
        pages = {"P1": Page(11, 4)}
        applied = redo(LOG_A, pages, 1)
        self.assertEqual(applied, [2, 5], "LSN 1 と 4 は P1 に反映済み（page_lsn = 4）なので飛ばす")
        self.assertEqual(values(pages, ["P1", "P2", "P3"]), {"P1": 11, "P2": 20, "P3": 30},
                         "敗者 T2 の変更（P2 = 20）も、いったん再実行する")
        self.assertEqual(pages["P2"].page_lsn, 2)

    def test_redo_starts_at_redo_lsn(self):
        pages = {"A": Page(1, 1), "C": Page("c", 4)}
        applied = redo(LOG_B, pages, 3)
        self.assertEqual(applied, [3, 7, 8, 10], "チェックポイントのおかげで LSN 1 は調べない")

    def test_redo_is_idempotent(self):
        pages = {"P1": Page(11, 4)}
        redo(LOG_A, pages, 1)
        self.assertEqual(redo(LOG_A, pages, 1), [], "2 回目は何も適用しない")

    def test_clrs_are_redone(self):
        pages = {"A": Page(1, 1), "B": Page(2, 2), "C": Page(3, 3)}  # CLR 5 はディスクに未反映
        self.assertEqual(redo(LOG_D, pages, 1), [5], "CLR も update と同じく再実行する")
        self.assertIsNone(pages["C"].value)


class TestUndo(unittest.TestCase):
    def test_undo_in_reverse_order_with_clrs(self):
        pages = {"P1": Page(11, 4), "P2": Page(20, 2), "P3": Page(30, 5)}
        new = undo(LOG_A, pages, frozenset({2}))
        self.assertEqual(new, [
            CLR(7, 2, "P1", 10, 4),
            CLR(8, 2, "P2", None, 2),
            LogRecord(9, "end", txn=2),
        ])
        self.assertEqual((pages["P1"].value, pages["P1"].page_lsn), (10, 7))
        self.assertEqual((pages["P2"].value, pages["P2"].page_lsn), (None, 8))

    def test_undo_reaches_before_checkpoint(self):
        pages = {"A": Page(2, 7), "B": Page(6, 10), "C": Page("c", 4), "D": Page(7, 8)}
        new = undo(LOG_B, pages, frozenset({2, 4}))
        self.assertEqual([(r.kind, r.undoes, r.after) for r in new[:3]], [("clr", 10, 5), ("clr", 7, 1), ("clr", 3, None)])
        self.assertEqual([(r.lsn, r.kind, r.txn) for r in new[3:]], [(14, "end", 2), (15, "end", 4)])

    def test_already_compensated_updates_are_skipped(self):
        pages = {"A": Page(1, 1), "B": Page(2, 2), "C": Page(None, 5)}
        new = undo(LOG_D, pages, frozenset({1}))
        self.assertEqual([r.undoes for r in new if r.kind == "clr"], [2, 1], "LSN 3 は CLR 5 で取り消し済み")
        self.assertEqual(new[-1], LogRecord(8, "end", txn=1))


class TestRecover(unittest.TestCase):
    def test_scenario_a(self):
        disk = {"P1": Page(11, 4)}
        pages, new = recover(LOG_A, disk)
        self.assertEqual(values(pages, ["P1", "P2", "P3"]), {"P1": 10, "P2": None, "P3": 30})
        self.assertEqual(disk, {"P1": Page(11, 4)}, "入力の disk_pages を書き換えない")
        self.assertEqual(len(new), 3)

    def test_scenario_b(self):
        pages, _ = recover(LOG_B, DISK_B)
        self.assertEqual(values(pages, EXPECTED_B), EXPECTED_B)

    def test_completed_abort(self):
        log = [U(1, 1, "A", None, 1), LogRecord(2, "abort", txn=1), CLR(3, 1, "A", None, 1), LogRecord(4, "end", txn=1)]
        pages, new = recover(log, {"A": Page(1, 1)})
        self.assertIsNone(pages["A"].value, "CLR を再実行して、取り消し後の状態に戻す")
        self.assertEqual(new, [], "敗者がいなければ、何も追記しない")

    def test_partial_abort(self):
        pages, new = recover(LOG_D, DISK_D)
        self.assertEqual(values(pages, "ABC"), {"A": None, "B": None, "C": None})
        self.assertEqual([r.undoes for r in new if r.kind == "clr"], [2, 1])

    def test_wal_rule_violation_is_detected(self):
        with self.assertRaises(ValueError, msg="ログにない変更（LSN 99）を含むページ"):
            recover(LOG_A, {"P1": Page(99, 99)})

    def test_crash_during_recovery_is_idempotent(self):
        for log, disk in ((LOG_A, DISK_A), (LOG_B, DISK_B), (LOG_D, DISK_D)):
            check_crash_during_recovery(self, log, disk, random.Random(len(log)))


class TestRandomHistories(unittest.TestCase):
    def test_random_crashes(self):
        for seed in range(150):
            log, disk, expected = simulate(seed)
            pages, new = recover(log, disk)
            self.assertEqual(values(pages, PAGES), expected, f"seed={seed}")
            if seed % 10 == 0:
                check_crash_during_recovery(self, log, disk, random.Random(seed))


# ---------------------------------------------------------------------------
# テスト用の道具
# ---------------------------------------------------------------------------

PAGES = ["P1", "P2", "P3", "P4"]


def history_state(log):
    """ログのすべての update / clr を順に適用した状態（「歴史の再現」の結果の参照値）。"""
    pages = {}
    for rec in log:
        if rec.kind in ("update", "clr"):
            pages[rec.page] = Page(rec.after, rec.lsn)
    return pages


def check_crash_during_recovery(test, log, disk, rng):
    full_pages, full_new = recover(log, disk)
    names = sorted(set(full_pages) | set(history_state(log)) | set(disk))
    expected = values(full_pages, names)
    for k in range(len(full_new) + 1):
        log2 = list(log) + full_new[:k]  # 回復中に k 件のログを書いたところでクラッシュ
        state_k = history_state(log2)
        variants = [
            dict(disk),                                   # 回復中のページは 1 枚もディスクに書かれていない
            {n: Page(p.value, p.page_lsn) for n, p in state_k.items()},  # すべて書かれた
        ]
        mixed = dict(disk)
        for n, p in state_k.items():                      # ページごとに書かれたかどうかがばらばら
            if rng.random() < 0.5:
                mixed[n] = Page(p.value, p.page_lsn)
        variants.append(mixed)
        for variant in variants:
            pages2, new2 = recover(log2, variant)
            test.assertEqual(values(pages2, names), expected, f"回復中のクラッシュ k={k}")
            combined = log2 + new2
            undone = [r.undoes for r in combined if r.kind == "clr"]
            test.assertEqual(len(undone), len(set(undone)), "同じ update を 2 回取り消してはいけない")
            clr_lsns = {r.lsn for r in combined if r.kind == "clr"}
            test.assertFalse(set(undone) & clr_lsns, "CLR を取り消してはいけない")


def simulate(seed, steps=60):
    """厳格なページ単位のロック・STEAL / NO-FORCE・ファジーチェックポイントのもとで実行し、途中でクラッシュさせる。

    戻り値: (ログ, クラッシュ時点のディスクのページ, 回復後にあるべき値)
    ログは常に永続化されている（WAL の規則は自動的に守られる）とする。
    """
    rng = random.Random(seed)
    log, mem, disk, rec_lsn = [], {}, {}, {}
    active, owner, committed = {}, {}, {}
    state = {"lsn": 0, "next_txn": 1}

    def append(**kw):
        state["lsn"] += 1
        rec = LogRecord(state["lsn"], **kw)
        log.append(rec)
        return rec

    def write_page(name, value, lsn):
        page = mem.setdefault(name, Page())
        rec_lsn.setdefault(name, lsn)  # ディスクとの差ができた最初の LSN
        page.value, page.page_lsn = value, lsn

    def release(txn):
        for name in [p for p, t in owner.items() if t == txn]:
            del owner[name]
        del active[txn]

    for step in range(steps):
        r = rng.random()
        if r < 0.15 and len(active) < 3:
            active[state["next_txn"]] = []
            state["next_txn"] += 1
        elif r < 0.55 and active:
            txn, name = rng.choice(sorted(active)), rng.choice(PAGES)
            if owner.get(name, txn) != txn:
                continue  # 他のトランザクションがロックしている
            rec = append(kind="update", txn=txn, page=name, before=mem.get(name, Page()).value, after=f"T{txn}-{step}")
            write_page(name, rec.after, rec.lsn)
            owner[name] = txn
            active[txn].append(rec)
        elif r < 0.68 and active:
            txn = rng.choice(sorted(active))
            append(kind="commit", txn=txn)
            for name in [p for p, t in owner.items() if t == txn]:
                committed[name] = mem[name].value
            release(txn)
        elif r < 0.76 and active:
            txn = rng.choice(sorted(active))
            append(kind="abort", txn=txn)
            for rec in reversed(active[txn]):
                clr = append(kind="clr", txn=txn, page=rec.page, after=rec.before, undoes=rec.lsn)
                write_page(rec.page, rec.before, clr.lsn)
            append(kind="end", txn=txn)
            release(txn)
        elif r < 0.9 and mem:
            name = rng.choice(sorted(mem))  # STEAL: コミット前の変更を含むページも書き出しうる
            disk[name] = Page(mem[name].value, mem[name].page_lsn)
            rec_lsn.pop(name, None)
        else:
            append(kind="checkpoint", active=tuple(sorted(active)), dirty=tuple(sorted(rec_lsn.items())))
    if active and rng.random() < 0.5:
        # 取り消しの途中でクラッシュする
        txn = rng.choice(sorted(active))
        append(kind="abort", txn=txn)
        records = list(reversed(active[txn]))
        for rec in records[: rng.randrange(len(records) + 1)]:
            clr = append(kind="clr", txn=txn, page=rec.page, after=rec.before, undoes=rec.lsn)
            write_page(rec.page, rec.before, clr.lsn)
            if rng.random() < 0.5:
                disk[rec.page] = Page(mem[rec.page].value, mem[rec.page].page_lsn)
    return log, disk, {name: committed.get(name) for name in PAGES}


if __name__ == "__main__":
    unittest.main()
