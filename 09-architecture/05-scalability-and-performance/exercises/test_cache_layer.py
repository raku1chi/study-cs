"""9.5 スケーラビリティとパフォーマンス — 演習5 のテスト（スタンピードに強いキャッシュ）

同時実行のテストでは、loader の中で threading.Event を待たせることで、
「読み込みの最中に同じキーの要求が殺到する」状況を決定的に作り出しています。

実行: python3 tools/check.py 9.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import threading
import time
import unittest

from cache_layer import CacheStats, CoalescingCache


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Origin:
    """遅いデータベースの代わり。呼ばれた回数を数え、版番号付きの値を返す。"""

    def __init__(self, block=None, fail=False):
        self.calls = 0
        self.version = 1
        self.block = block
        self.fail = fail
        self.entered = threading.Event()
        self.lock = threading.Lock()

    def __call__(self, key):
        with self.lock:
            self.calls += 1
            version = self.version
        self.entered.set()
        if self.block is not None:
            assert self.block.wait(5), "テストが loader を解放しなかった"
        if self.fail:
            raise ConnectionError("DB が過負荷です")
        return f"{key}:v{version}"


def wait_until(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.001)
    return False


class Worker(threading.Thread):
    def __init__(self, fn):
        super().__init__(daemon=True)
        self.fn, self.result, self.error = fn, None, None

    def run(self):
        try:
            self.result = self.fn()
        except BaseException as exc:  # noqa: BLE001
            self.error = exc


class TestExercise5Basics(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.origin = Origin()
        self.tasks = []
        self.cache = CoalescingCache(self.origin, ttl=10, stale_ttl=20, clock=self.clock, spawn=self.tasks.append)

    def test_hit_and_miss(self):
        self.assertEqual(self.cache.get("user:1"), "user:1:v1")
        self.assertEqual(self.cache.get("user:1"), "user:1:v1")
        self.assertEqual(self.origin.calls, 1)
        self.assertEqual(self.cache.stats, CacheStats(hits=1, misses=1, loads=1))

    def test_stale_while_revalidate(self):
        self.cache.get("k")
        self.origin.version = 2
        self.clock.now += 15                              # ttl は過ぎたが、猶予期間内
        self.assertEqual(self.cache.get("k"), "k:v1", "古い値をすぐ返す")
        self.assertEqual(len(self.tasks), 1, "裏での更新を 1 つ依頼する")
        self.assertEqual(self.cache.get("k"), "k:v1")
        self.assertEqual(len(self.tasks), 1, "更新の依頼は 1 キーにつき同時に 1 つまで")
        self.assertEqual(self.origin.calls, 1, "呼び出し元は loader を待たない")
        self.tasks.pop()()                               # 裏での更新を実行する
        self.assertEqual(self.cache.get("k"), "k:v2")
        self.assertEqual(self.cache.stats.stale_hits, 2)
        self.assertEqual(self.cache.stats.hits, 1)

    def test_expired_beyond_stale_window_loads_synchronously(self):
        self.cache.get("k")
        self.origin.version = 2
        self.clock.now += 30                              # ttl + stale_ttl ちょうど
        self.assertEqual(self.cache.get("k"), "k:v2")
        self.assertEqual(self.tasks, [])
        self.assertEqual(self.cache.stats.misses, 2)

    def test_refresh_failure_keeps_stale_value(self):
        self.cache.get("k")
        self.clock.now += 12
        self.cache.get("k")
        self.origin.fail = True
        self.tasks.pop()()
        self.assertEqual(self.cache.stats.refresh_errors, 1)
        self.assertEqual(self.cache.get("k"), "k:v1", "更新に失敗しても古い値を返し続ける")
        self.assertEqual(len(self.tasks), 1, "次の古い読み取りで、また更新を試みる")

    def test_load_errors_are_not_cached(self):
        self.origin.fail = True
        with self.assertRaises(ConnectionError):
            self.cache.get("k")
        self.origin.fail = False
        self.assertEqual(self.cache.get("k"), "k:v1")
        self.assertEqual(self.origin.calls, 2)

    def test_invalidate(self):
        self.cache.get("k")
        self.origin.version = 2
        self.cache.invalidate("k")
        self.assertEqual(self.cache.get("k"), "k:v2")
        self.cache.invalidate("never-loaded")  # 存在しないキーでもエラーにしない

    def test_invalidate_during_refresh_discards_result(self):
        self.cache.get("k")                               # v1 をキャッシュ
        self.clock.now += 15
        self.cache.get("k")                               # 裏での更新を依頼（まだ実行しない）
        self.cache.invalidate("k")                        # その間に DB が v2 に更新され、無効化された
        self.tasks.pop()()                                # 無効化の前に始まった更新が、古い v1 を読んで完了する
        self.origin.version = 2
        self.assertEqual(self.cache.get("k"), "k:v2",
                         "無効化より前に始まった更新の結果（古い v1）でキャッシュを上書きしない")

    def test_synchronous_spawn_does_not_deadlock(self):
        cache = CoalescingCache(self.origin, ttl=10, stale_ttl=20, clock=self.clock, spawn=lambda task: task())
        cache.get("k")
        self.origin.version = 2
        self.clock.now += 15
        done = Worker(lambda: cache.get("k"))
        done.start()
        done.join(5)
        self.assertFalse(done.is_alive(), "spawn をロックを持ったまま呼ぶとデッドロックする")
        self.assertIsNone(done.error)
        self.assertEqual(cache.get("k"), "k:v2")

    def test_validation(self):
        with self.assertRaises(ValueError):
            CoalescingCache(self.origin, ttl=0)
        with self.assertRaises(ValueError):
            CoalescingCache(self.origin, ttl=1, stale_ttl=-1)


class TestExercise5SingleFlight(unittest.TestCase):
    def start_leader(self, cache, origin, key="hot"):
        leader = Worker(lambda: cache.get(key))
        leader.start()
        wait_until(lambda: origin.entered.is_set() or not leader.is_alive())
        if not origin.entered.is_set():
            if leader.error is not None:
                raise leader.error
            self.fail("最初の読み込みが始まらない")
        return leader

    def test_concurrent_misses_call_loader_once(self):
        release = threading.Event()
        origin = Origin(block=release)
        cache = CoalescingCache(origin, ttl=60)
        leader = self.start_leader(cache, origin)
        followers = [Worker(lambda: cache.get("hot")) for _ in range(15)]
        for w in followers:
            w.start()
        self.assertTrue(wait_until(lambda: cache.waiting_count("hot") == 15), "後続の要求が待っていない")
        release.set()
        for w in [leader, *followers]:
            w.join(5)
            self.assertFalse(w.is_alive())
            self.assertIsNone(w.error)
            self.assertEqual(w.result, "hot:v1")
        self.assertEqual(origin.calls, 1, "16 件の同時の要求でも、オリジンへの読み込みは 1 回")
        stats = cache.stats
        self.assertEqual((stats.misses, stats.loads, stats.coalesced), (16, 1, 15))
        self.assertEqual(cache.waiting_count("hot"), 0)

    def test_waiters_share_the_error(self):
        release = threading.Event()
        origin = Origin(block=release, fail=True)
        cache = CoalescingCache(origin, ttl=60)
        leader = self.start_leader(cache, origin)
        followers = [Worker(lambda: cache.get("hot")) for _ in range(5)]
        for w in followers:
            w.start()
        self.assertTrue(wait_until(lambda: cache.waiting_count("hot") == 5))
        release.set()
        for w in [leader, *followers]:
            w.join(5)
            self.assertIsInstance(w.error, ConnectionError)
        self.assertEqual(origin.calls, 1)
        origin.fail, origin.block = False, None
        self.assertEqual(cache.get("hot"), "hot:v1", "失敗は保存されず、次の要求で読み込み直す")

    def test_invalidate_during_load_does_not_store_old_value(self):
        release = threading.Event()
        origin = Origin(block=release)
        cache = CoalescingCache(origin, ttl=60)
        leader = self.start_leader(cache, origin)        # v1 を読み込み中
        origin.version = 2
        cache.invalidate("hot")                           # 読み込みの途中で DB が更新され、無効化された
        release.set()
        leader.join(5)
        self.assertEqual(leader.result, "hot:v1", "待っていた呼び出しには、その読み込みの結果を返してよい")
        origin.block = None
        self.assertEqual(cache.get("hot"), "hot:v2", "無効化の前に始まった読み込みの結果は保存しない")

    def test_different_keys_do_not_block_each_other(self):
        release = threading.Event()
        slow = Origin(block=release)

        def loader(key):
            return slow(key) if key == "slow" else f"{key}:fast"

        cache = CoalescingCache(loader, ttl=60)
        leader = Worker(lambda: cache.get("slow"))
        leader.start()
        wait_until(lambda: slow.entered.is_set() or not leader.is_alive())
        if leader.error is not None:
            raise leader.error
        started = time.monotonic()
        self.assertEqual(cache.get("other"), "other:fast")
        self.assertLess(time.monotonic() - started, 1.0, "別のキーの読み込みを待たせてはいけない")
        release.set()
        leader.join(5)


if __name__ == "__main__":
    unittest.main()
