"""4.4 並行処理と同期 — sync_lab のテスト

実行: python3 tools/check.py 4.4   （またはこのディレクトリで python3 -m unittest -v test_sync_lab）

スレッドを使うテストには、すべてタイムアウトを付けています。デッドロックするとテストが
「止まる」のではなく「失敗する」ようにするためです。
"""
import asyncio
import random
import threading
import time
import unittest

from sync_lab import (
    Account,
    BoundedBlockingQueue,
    InsufficientFunds,
    QueueClosed,
    ReadWriteLock,
    build_wait_for_graph,
    find_deadlock,
    gather_with_concurrency_limit,
    transfer,
)

TIMEOUT = 10.0


def start(target, *args):
    t = threading.Thread(target=target, args=args, daemon=True)
    t.start()
    return t


class TestExercise1BlockingQueue(unittest.TestCase):
    def test_fifo(self):
        q = BoundedBlockingQueue(3)
        for x in "abc":
            q.put(x)
        self.assertEqual(len(q), 3)
        self.assertEqual([q.get(), q.get(), q.get()], ["a", "b", "c"])

    def test_put_blocks_while_full(self):
        q = BoundedBlockingQueue(1)
        q.put(1)
        done = threading.Event()

        def producer():
            q.put(2)
            done.set()

        t = start(producer)
        self.assertFalse(done.wait(0.2), "満杯の間、put は待たされること")
        self.assertEqual(q.get(timeout=TIMEOUT), 1)
        self.assertTrue(done.wait(TIMEOUT), "空きができたら put が完了すること")
        self.assertEqual(q.get(timeout=TIMEOUT), 2)
        t.join(TIMEOUT)

    def test_get_blocks_while_empty(self):
        q = BoundedBlockingQueue(2)
        got = []
        t = start(lambda: got.append(q.get()))
        time.sleep(0.2)
        self.assertEqual(got, [], "空の間、get は待たされること")
        q.put("x")
        t.join(TIMEOUT)
        self.assertEqual(got, ["x"])

    def test_timeouts(self):
        q = BoundedBlockingQueue(1)
        t0 = time.monotonic()
        with self.assertRaises(TimeoutError):
            q.get(timeout=0.1)
        self.assertGreaterEqual(time.monotonic() - t0, 0.09)
        with self.assertRaises(TimeoutError):
            q.get(timeout=0)
        q.put("a")
        with self.assertRaises(TimeoutError):
            q.put("b", timeout=0.05)
        self.assertEqual(len(q), 1)

    def test_close_wakes_waiters_and_allows_draining(self):
        q = BoundedBlockingQueue(2)
        errors = []

        def waiter():
            try:
                q.get()
            except QueueClosed as e:
                errors.append(e)

        waiters = [start(waiter) for _ in range(3)]
        time.sleep(0.1)
        q.close()
        for t in waiters:
            t.join(TIMEOUT)
            self.assertFalse(t.is_alive(), "close() は待っているスレッドを起こすこと")
        self.assertEqual(len(errors), 3)
        self.assertTrue(q.closed)
        with self.assertRaises(QueueClosed):
            q.put("late")

    def test_items_put_before_close_can_still_be_taken(self):
        q = BoundedBlockingQueue(5)
        q.put(1)
        q.put(2)
        q.close()
        self.assertEqual([q.get(), q.get()], [1, 2])
        with self.assertRaises(QueueClosed):
            q.get()

    def test_blocked_put_fails_when_closed(self):
        q = BoundedBlockingQueue(1)
        q.put(0)
        errors = []

        def producer():
            try:
                q.put(1)
            except QueueClosed as e:
                errors.append(e)

        t = start(producer)
        time.sleep(0.1)
        q.close()
        t.join(TIMEOUT)
        self.assertEqual(len(errors), 1)

    def test_many_producers_and_consumers(self):
        q = BoundedBlockingQueue(8)
        received = []
        lock = threading.Lock()

        def producer(base):
            for i in range(1000):
                q.put(base + i, timeout=TIMEOUT)

        def consumer():
            while True:
                try:
                    item = q.get(timeout=TIMEOUT)
                except QueueClosed:
                    return
                with lock:
                    received.append(item)

        consumers = [start(consumer) for _ in range(4)]
        producers = [start(producer, k * 10000) for k in range(4)]
        for t in producers:
            t.join(TIMEOUT)
        q.close()
        for t in consumers:
            t.join(TIMEOUT)
            self.assertFalse(t.is_alive())
        self.assertEqual(sorted(received), sorted(k * 10000 + i for k in range(4) for i in range(1000)))

    def test_invalid_capacity(self):
        with self.assertRaises(ValueError):
            BoundedBlockingQueue(0)


class TestExercise2ReadWriteLock(unittest.TestCase):
    def test_readers_share(self):
        rw = ReadWriteLock()
        barrier = threading.Barrier(3, timeout=TIMEOUT)
        errors = []

        def reader():
            with rw.read_locked():
                try:
                    barrier.wait()  # 3 人が同時に読み取り中でなければ、ここを通過できない
                except threading.BrokenBarrierError as e:
                    errors.append(e)

        threads = [start(reader) for _ in range(3)]
        for t in threads:
            t.join(TIMEOUT)
        self.assertEqual(errors, [], "複数の読み手は同時にロックを持てること")

    def test_writer_excludes_everyone(self):
        rw = ReadWriteLock()
        self.assertTrue(rw.acquire_write())
        self.assertFalse(rw.acquire_read(timeout=0.05))
        self.assertFalse(rw.acquire_write(timeout=0.05))
        rw.release_write()
        self.assertTrue(rw.acquire_read(timeout=0))
        self.assertFalse(rw.acquire_write(timeout=0.05), "読み手がいる間は書けない")
        rw.release_read()
        self.assertTrue(rw.acquire_write(timeout=0))
        rw.release_write()

    def test_waiting_writer_blocks_new_readers(self):
        rw = ReadWriteLock()
        events = []
        rw.acquire_read()  # 読み手 R1 が保持中
        writer_waiting = threading.Event()

        def writer():
            writer_waiting.set()
            with rw.write_locked():
                events.append("writer")

        def late_reader():
            with rw.read_locked():
                events.append("late reader")

        w = start(writer)
        writer_waiting.wait(TIMEOUT)
        time.sleep(0.1)  # 書き手が確実に待ち状態に入るまで待つ
        r = start(late_reader)
        time.sleep(0.1)
        self.assertEqual(events, [], "書き手が待っている間、新しい読み手は入れない（書き込み優先）")
        rw.release_read()
        w.join(TIMEOUT)
        r.join(TIMEOUT)
        self.assertEqual(events, ["writer", "late reader"])

    def test_timed_out_writer_does_not_block_readers(self):
        rw = ReadWriteLock()
        rw.acquire_read()
        self.assertFalse(rw.acquire_write(timeout=0.1))
        self.assertTrue(rw.acquire_read(timeout=0.5),
                        "タイムアウトで諦めた書き手が「待っている」扱いのまま残ってはいけない")
        rw.release_read()
        rw.release_read()

    def test_release_without_acquire(self):
        rw = ReadWriteLock()
        with self.assertRaises(RuntimeError):
            rw.release_read()
        with self.assertRaises(RuntimeError):
            rw.release_write()

    def test_invariants_under_stress(self):
        rw = ReadWriteLock()
        state = {"a": 0, "b": 0}
        violations = []

        def writer(n):
            for _ in range(n):
                with rw.write_locked():
                    state["a"] += 1
                    time.sleep(0)  # 書き込みの途中で他のスレッドに切り替わる機会を作る
                    state["b"] += 1

        def reader(n):
            for _ in range(n):
                with rw.read_locked():
                    if state["a"] != state["b"]:
                        violations.append(dict(state))

        threads = [start(writer, 300) for _ in range(3)] + [start(reader, 500) for _ in range(5)]
        for t in threads:
            t.join(TIMEOUT)
            self.assertFalse(t.is_alive(), "デッドロックしていないこと")
        self.assertEqual(violations, [], "読み手が書きかけの状態を見てはいけない")
        self.assertEqual(state, {"a": 900, "b": 900})


class TestExercise3Deadlock(unittest.TestCase):
    def assert_cycle(self, graph, cycle):
        self.assertIsNotNone(cycle, graph)
        self.assertTrue(cycle, "空でない循環を返すこと")
        self.assertEqual(len(set(cycle)), len(cycle), "同じノードを 2 回含めない")
        for a, b in zip(cycle, cycle[1:] + cycle[:1]):
            self.assertIn(b, graph.get(a, ()), f"{a} → {b} という辺がありません: {cycle}")

    def test_build_wait_for_graph(self):
        holders = {"L1": "T1", "L2": "T2", "L3": "T3"}
        waiting = {"T1": "L2", "T2": "L3", "T4": "L9"}  # L9 は誰も持っていない
        self.assertEqual(build_wait_for_graph(holders, waiting), {"T1": {"T2"}, "T2": {"T3"}})

    def test_self_deadlock_on_non_reentrant_lock(self):
        graph = build_wait_for_graph({"L": "T1"}, {"T1": "L"})
        self.assertEqual(graph, {"T1": {"T1"}})
        self.assertEqual(find_deadlock(graph), ["T1"])

    def test_no_cycle(self):
        self.assertIsNone(find_deadlock({}))
        self.assertIsNone(find_deadlock({"A": ["B"], "B": ["C"], "D": ["B"]}))
        self.assertIsNone(find_deadlock({"A": ["B", "C"], "B": ["D"], "C": ["D"]}), "合流は循環ではない")

    def test_two_and_three_cycles(self):
        g = {"A": ["B"], "B": ["A"]}
        self.assert_cycle(g, find_deadlock(g))
        g = {"T1": ["T2"], "T2": ["T3"], "T3": ["T1"], "T4": ["T1"], "T5": []}
        cycle = find_deadlock(g)
        self.assert_cycle(g, cycle)
        self.assertEqual(set(cycle), {"T1", "T2", "T3"})

    def test_from_lock_tables(self):
        # 典型的なデッドロック: T1 は A を持って B を待ち、T2 は B を持って A を待つ
        graph = build_wait_for_graph({"A": "T1", "B": "T2"}, {"T1": "B", "T2": "A"})
        self.assertEqual(set(find_deadlock(graph)), {"T1", "T2"})

    def test_random_graphs(self):
        rng = random.Random(41)
        for _ in range(300):
            n = rng.randrange(1, 9)
            g = {i: [j for j in range(n) if rng.random() < 0.2] for i in range(n)}
            cycle = find_deadlock(g)
            if cycle is None:
                self.assertFalse(has_cycle_bruteforce(g), g)
            else:
                self.assert_cycle(g, cycle)

    def test_long_chain_without_recursion_limit(self):
        n = 20000
        chain = {i: [i + 1] for i in range(n)}
        self.assertIsNone(find_deadlock(chain))
        chain[n] = [0]
        self.assertEqual(len(find_deadlock(chain)), n + 1)


def has_cycle_bruteforce(g):
    """各ノードから到達できるノードを求め、自分に戻れるかを調べる（小さなグラフ用）。"""
    for start_node in g:
        seen, stack = set(), list(g[start_node])
        while stack:
            v = stack.pop()
            if v == start_node:
                return True
            if v not in seen:
                seen.add(v)
                stack.extend(g.get(v, ()))
    return False


class SpyLock:
    """取得の順序を記録するロック。"""

    def __init__(self, account_id, log):
        self._lock = threading.Lock()
        self._id = account_id
        self._log = log

    def acquire(self, *args, **kwargs):
        ok = self._lock.acquire(*args, **kwargs)
        if ok:
            self._log.append(self._id)
        return ok

    def release(self):
        self._lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()


class TestExercise3Transfer(unittest.TestCase):
    def test_basic_transfer(self):
        a, b = Account(1, 100), Account(2, 50)
        transfer(a, b, 30)
        self.assertEqual((a.balance, b.balance), (70, 80))
        with self.assertRaises(InsufficientFunds):
            transfer(b, a, 81)
        self.assertEqual((a.balance, b.balance), (70, 80), "失敗した送金は残高を変えない")

    def test_invalid_transfers(self):
        a, b = Account(1, 100), Account(2, 0)
        for amount in (0, -5):
            with self.assertRaises(ValueError):
                transfer(a, b, amount)
        with self.assertRaises(ValueError):
            transfer(a, a, 10)  # 同じ口座（再入不可のロックを 2 回取ろうとしてはいけない）

    def test_locks_are_taken_in_id_order(self):
        log = []
        a, b = Account(1, 100), Account(2, 100)
        a.lock, b.lock = SpyLock(1, log), SpyLock(2, log)
        transfer(b, a, 10)
        transfer(a, b, 10)
        self.assertEqual(log, [1, 2, 1, 2], "どちら向きの送金でも、ID の小さい口座のロックから取ること")

    def test_many_threads_no_deadlock_and_money_is_conserved(self):
        rng = random.Random(42)
        accounts = [Account(i, 1000) for i in range(10)]
        plans = [[(rng.randrange(10), rng.randrange(10), rng.randrange(1, 50)) for _ in range(2000)]
                 for _ in range(8)]

        errors = []
        succeeded = []

        def worker(plan):
            ok = 0
            try:
                for s, d, amount in plan:
                    if s == d:
                        continue
                    try:
                        transfer(accounts[s], accounts[d], amount)
                        ok += 1
                    except InsufficientFunds:
                        pass
            except BaseException as e:  # スレッド内の例外は、そのままでは誰にも気づかれない
                errors.append(e)
            succeeded.append(ok)

        threads = [start(worker, p) for p in plans]
        for t in threads:
            t.join(TIMEOUT)
            self.assertFalse(t.is_alive(), "デッドロックしていないこと（時間内に終わること）")
        self.assertEqual(errors, [], "送金中に予期しない例外が起きてはいけない")
        self.assertGreater(sum(succeeded), 1000, "送金の多くは成功するはず")
        self.assertEqual(sum(a.balance for a in accounts), 10 * 1000, "お金の総額は変わらない")
        self.assertTrue(all(a.balance >= 0 for a in accounts))


class TestExercise4AsyncLimit(unittest.TestCase):
    def test_results_keep_input_order(self):
        async def job(i, delay):
            await asyncio.sleep(delay)
            return i

        async def main():
            delays = [0.05, 0.01, 0.03, 0.0, 0.02]
            return await gather_with_concurrency_limit([job(i, d) for i, d in enumerate(delays)], 2)

        self.assertEqual(asyncio.run(main()), [0, 1, 2, 3, 4])

    def test_concurrency_never_exceeds_limit_but_reaches_it(self):
        state = {"now": 0, "max": 0}

        async def job(i):
            state["now"] += 1
            state["max"] = max(state["max"], state["now"])
            await asyncio.sleep(0.01)
            state["now"] -= 1
            return i * i

        async def main():
            return await gather_with_concurrency_limit((job(i) for i in range(20)), 3)

        self.assertEqual(asyncio.run(main()), [i * i for i in range(20)])
        self.assertEqual(state["max"], 3)

    def test_runs_in_parallel(self):
        async def main():
            t0 = time.monotonic()
            await gather_with_concurrency_limit([asyncio.sleep(0.1) for _ in range(10)], 10)
            return time.monotonic() - t0

        self.assertLess(asyncio.run(main()), 0.5, "10 個を同時に待てば 0.1 秒程度で終わる")

    def test_per_task_timeout_with_return_exceptions(self):
        async def slow():
            await asyncio.sleep(5)

        async def fast():
            await asyncio.sleep(0.01)
            return "ok"

        async def main():
            t0 = time.monotonic()
            res = await gather_with_concurrency_limit([fast(), slow(), fast()], 2, timeout=0.1,
                                                      return_exceptions=True)
            return res, time.monotonic() - t0

        res, elapsed = asyncio.run(main())
        self.assertEqual(res[0], "ok")
        self.assertIsInstance(res[1], asyncio.TimeoutError)
        self.assertEqual(res[2], "ok")
        self.assertLess(elapsed, 1.0)

    def test_exceptions_are_collected_or_raised(self):
        async def boom():
            await asyncio.sleep(0)
            raise ValueError("boom")

        async def ok():
            return 1

        async def collect():
            return await gather_with_concurrency_limit([ok(), boom(), ok()], 2, return_exceptions=True)

        res = asyncio.run(collect())
        self.assertEqual(res[0], 1)
        self.assertIsInstance(res[1], ValueError)
        self.assertEqual(res[2], 1)

    def test_first_error_cancels_the_rest(self):
        log = []

        async def boom():
            await asyncio.sleep(0.01)
            raise ValueError("boom")

        async def long_job():
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                log.append("cancelled")
                raise

        async def never_started():
            log.append("started")  # 並行数 2 なので、エラーの時点ではまだ始まっていないはず

        async def main():
            t0 = time.monotonic()
            with self.assertRaises(ValueError):
                await gather_with_concurrency_limit([long_job(), boom(), never_started()], 2)
            return time.monotonic() - t0

        elapsed = asyncio.run(main())
        self.assertLess(elapsed, 1.0, "エラーが起きたら、残りの仕事の完了を待たずに戻ること")
        self.assertEqual(log, ["cancelled"], "実行中の仕事はキャンセルし、未着手の仕事は始めない")

    def test_empty_and_invalid(self):
        self.assertEqual(asyncio.run(gather_with_concurrency_limit([], 3)), [])

        async def main():
            with self.assertRaises(ValueError):
                await gather_with_concurrency_limit([], 0)

        asyncio.run(main())


if __name__ == "__main__":
    unittest.main()
