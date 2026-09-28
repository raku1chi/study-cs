"""7.4 合意と協調 — リースとフェンシングトークンのテスト

実行: python3 tools/check.py 7.4   （またはこのディレクトリで python3 -m unittest -v test_fencing）
"""
import random
import unittest

from fencing import FencedStorage, LockService, StaleTokenError, UnfencedStorage


class FakeClock:
    def __init__(self, now: int = 0) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


class TestExercise6LockService(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock(1_000)
        self.locks = LockService(lease_ms=10_000, clock=self.clock)

    def test_acquire_and_exclusion(self):
        t1 = self.locks.acquire("orders", "A")
        self.assertEqual(t1, 1)
        self.assertIsNone(self.locks.acquire("orders", "B"), "有効なリースがある間は他人は取れない")
        self.assertEqual(self.locks.holder("orders"), ("A", 1))
        self.assertEqual(self.locks.acquire("invoices", "B"), 2, "トークンはロックをまたいで単調増加")

    def test_reacquire_by_holder_extends_with_same_token(self):
        t = self.locks.acquire("orders", "A")
        self.clock.now += 9_000
        self.assertEqual(self.locks.acquire("orders", "A"), t)
        self.clock.now += 9_000
        self.assertEqual(self.locks.holder("orders"), ("A", t), "延長されたので、まだ有効")

    def test_lease_expires(self):
        self.locks.acquire("orders", "A")
        self.clock.now += 9_999
        self.assertEqual(self.locks.holder("orders"), ("A", 1))
        self.clock.now += 1
        self.assertIsNone(self.locks.holder("orders"), "expires_at ちょうどで失効する")
        self.assertEqual(self.locks.acquire("orders", "B"), 2, "失効後は別のクライアントが新しいトークンで取れる")

    def test_renew(self):
        t = self.locks.acquire("orders", "A")
        self.clock.now += 5_000
        self.assertTrue(self.locks.renew("orders", "A", t))
        self.clock.now += 9_000
        self.assertEqual(self.locks.holder("orders"), ("A", t))
        self.assertFalse(self.locks.renew("orders", "B", t), "保持者以外は延長できない")
        self.assertFalse(self.locks.renew("orders", "A", t + 1), "トークンが違えば延長できない")
        self.clock.now += 20_000
        self.assertFalse(self.locks.renew("orders", "A", t), "一度失効したら延長できない")

    def test_release(self):
        t = self.locks.acquire("orders", "A")
        self.assertFalse(self.locks.release("orders", "B", t))
        self.assertTrue(self.locks.release("orders", "A", t))
        self.assertIsNone(self.locks.holder("orders"))
        self.assertFalse(self.locks.release("orders", "A", t), "解放済みのロックは解放できない")
        self.assertEqual(self.locks.acquire("orders", "B"), t + 1)

    def test_new_tokens_strictly_increase(self):
        rng = random.Random(3)
        last_new_token = 0
        new_tokens = 0
        for _ in range(500):
            name = rng.choice(["x", "y", "z"])
            client = rng.choice(["A", "B", "C"])
            op = rng.random()
            if op < 0.5:
                before = self.locks.holder(name)
                t = self.locks.acquire(name, client)
                if before is not None and before[0] == client:
                    self.assertEqual(t, before[1], "保持者の再取得は同じトークン")
                elif before is not None:
                    self.assertIsNone(t)
                else:
                    self.assertGreater(t, last_new_token, "新しく発行するトークンは必ずそれまでより大きい")
                    last_new_token = t
                    new_tokens += 1
            elif op < 0.7:
                h = self.locks.holder(name)
                if h:
                    self.assertTrue(self.locks.release(name, h[0], h[1]))
            else:
                self.clock.now += rng.randrange(0, 15_000)
        self.assertGreater(new_tokens, 50)

    def test_invalid_lease(self):
        with self.assertRaises(ValueError):
            LockService(lease_ms=0, clock=self.clock)


class TestExercise6FencedStorage(unittest.TestCase):
    def test_accepts_equal_or_newer_tokens(self):
        s = FencedStorage()
        s.write("k", "v1", token=3)
        s.write("k", "v2", token=3)
        s.write("k", "v3", token=5)
        self.assertEqual(s.read("k"), "v3")
        with self.assertRaises(StaleTokenError):
            s.write("k", "stale", token=4)
        self.assertEqual(s.read("k"), "v3", "拒否された書き込みは反映されない")
        s.write("other", "ok", token=1)
        self.assertEqual(s.read("other"), "ok", "トークンの検査はキーごと")
        self.assertIsNone(s.read("missing"))


class TestExercise6PausedClientScenario(unittest.TestCase):
    """Kleppmann（2016）が示した筋書き: リースを持つクライアントが GC で止まっている間に、リースが失効する。"""

    def run_scenario(self, storage):
        clock = FakeClock(0)
        locks = LockService(lease_ms=10_000, clock=clock)
        token_a = locks.acquire("file", "A")
        # A は「自分がロックを持っているか」を確認してから書き込もうとする……
        self.assertEqual(locks.holder("file"), ("A", token_a))
        clock.now += 15_000  # ……その直前に、GC の一時停止で 15 秒止まる。リースは失効する
        token_b = locks.acquire("file", "B")
        self.assertIsNotNone(token_b, "失効したので B がロックを取る")
        storage.write("file", "B の内容", token_b)
        # A が目を覚ます。A は自分がまだロックを持っていると思い込んでいる
        try:
            storage.write("file", "A の古い内容", token_a)
        except StaleTokenError:
            return "rejected"
        return "accepted"

    def test_fencing_token_rejects_the_paused_client(self):
        storage = FencedStorage()
        self.assertEqual(self.run_scenario(storage), "rejected")
        self.assertEqual(storage.read("file"), "B の内容")

    def test_without_fencing_data_is_corrupted(self):
        storage = UnfencedStorage()
        self.assertEqual(self.run_scenario(storage), "accepted")
        self.assertEqual(storage.read("file"), "A の古い内容", "B の書き込みが古い内容で上書きされた")


if __name__ == "__main__":
    unittest.main()
