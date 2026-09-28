"""7.2 レプリケーションと一貫性 — セッション保証のテスト

実行: python3 tools/check.py 7.2   （またはこのディレクトリで python3 -m unittest -v test_session_consistency）
"""
import unittest

from session_consistency import LEADER, ReplicatedStore, Session


class TestReplicatedStore(unittest.TestCase):
    def test_writes_get_increasing_lsns(self):
        store = ReplicatedStore(num_followers=2)
        self.assertEqual(store.leader_lsn, 0)
        self.assertEqual(store.write("x", 1), 1)
        self.assertEqual(store.write("y", 2), 2)
        self.assertEqual(store.write("x", 3), 3)
        self.assertEqual(store.leader_lsn, 3)
        self.assertEqual(store.num_followers, 2)

    def test_followers_lag_until_replicated(self):
        store = ReplicatedStore(num_followers=2)
        store.write("x", 1)
        self.assertEqual(store.read(LEADER, "x"), 1)
        self.assertIsNone(store.read(0, "x"), "複製するまでフォロワーには見えない")
        self.assertEqual(store.applied_lsn(0), 0)
        self.assertEqual(store.applied_lsn(LEADER), 1)
        store.replicate(0)
        self.assertEqual(store.read(0, "x"), 1)
        self.assertIsNone(store.read(1, "x"))

    def test_partial_replication_applies_log_in_order(self):
        store = ReplicatedStore(num_followers=1)
        for v in range(1, 6):
            store.write("x", v)
        store.replicate(0, up_to=2)
        self.assertEqual((store.applied_lsn(0), store.read(0, "x")), (2, 2))
        store.replicate(0, up_to=4)
        self.assertEqual((store.applied_lsn(0), store.read(0, "x")), (4, 4))
        store.replicate(0, up_to=1)
        self.assertEqual(store.applied_lsn(0), 4, "フォロワーが過去に戻ることはない")
        store.replicate(0, up_to=100)
        self.assertEqual(store.applied_lsn(0), 5, "リーダーの LSN を超えては進まない")

    def test_validation(self):
        with self.assertRaises(ValueError):
            ReplicatedStore(num_followers=0)
        store = ReplicatedStore(num_followers=2)
        with self.assertRaises(IndexError):
            store.replicate(2)
        with self.assertRaises(IndexError):
            store.read(-1, "x")
        with self.assertRaises(IndexError):
            store.applied_lsn(5)
        with self.assertRaises(ValueError):
            store.replicate(0, up_to=-1)


class TestSessionGuarantees(unittest.TestCase):
    def test_without_guarantees_you_may_not_see_your_own_write(self):
        store = ReplicatedStore(num_followers=2)
        s = Session(store, read_your_writes=False, monotonic_reads=False)
        s.write("profile", "新しい自己紹介")
        self.assertIsNone(s.read("profile", prefer=0), "保証がなければ、遅れたフォロワーから古い値が返る")
        self.assertEqual(s.last_served_by, 0)

    def test_read_your_writes_falls_back_to_leader(self):
        store = ReplicatedStore(num_followers=2)
        s = Session(store, monotonic_reads=False)
        lsn = s.write("profile", "新しい自己紹介")
        self.assertEqual(s.token, lsn)
        self.assertEqual(s.read("profile", prefer=0), "新しい自己紹介")
        self.assertEqual(s.last_served_by, LEADER)
        store.replicate(0)
        self.assertEqual(s.read("profile", prefer=0), "新しい自己紹介")
        self.assertEqual(s.last_served_by, 0, "フォロワーが追いついたら、フォロワーから読んでよい")

    def test_read_your_writes_by_waiting(self):
        store = ReplicatedStore(num_followers=2)
        writer = Session(store)
        s = Session(store, fallback="wait")
        s.write("x", "mine")  # LSN 1
        writer.write("y", "other")  # LSN 2
        self.assertEqual(s.read("x", prefer=1), "mine")
        self.assertEqual(s.last_served_by, 1)
        self.assertEqual(store.applied_lsn(1), 1, "必要な位置（LSN 1）まで追いつけば十分")

    def test_monotonic_reads_prevent_going_back_in_time(self):
        store = ReplicatedStore(num_followers=2)
        author = Session(store)
        author.write("comment", "v1")
        author.write("comment", "v2")
        store.replicate(0)  # フォロワー0 は最新（v2）
        store.replicate(1, up_to=1)  # フォロワー1 は遅れている（v1）

        careless = Session(store, monotonic_reads=False)
        self.assertEqual(careless.read("comment", prefer=0), "v2")
        self.assertEqual(careless.read("comment", prefer=1), "v1", "時間が巻き戻って見える")

        reader = Session(store)
        self.assertEqual(reader.read("comment", prefer=0), "v2")
        self.assertEqual(reader.read("comment", prefer=1), "v2", "一度見た状態より古い状態は見せない")
        self.assertEqual(reader.last_served_by, LEADER)

    def test_read_your_writes_alone_does_not_give_monotonic_reads(self):
        store = ReplicatedStore(num_followers=2)
        other = Session(store)
        other.write("x", "v1")
        other.write("x", "v2")
        store.replicate(0)
        store.replicate(1, up_to=1)
        s = Session(store, read_your_writes=True, monotonic_reads=False)
        self.assertEqual(s.read("x", prefer=0), "v2")
        self.assertEqual(s.read("x", prefer=1), "v1", "自分は何も書いていないので RYW では防げない")

    def test_tokens_carry_guarantees_across_devices(self):
        store = ReplicatedStore(num_followers=2)
        web = Session(store)
        web.write("address", "東京都…")
        phone_without_token = Session(store)
        self.assertIsNone(phone_without_token.read("address", prefer=0), "別の端末は自分の書き込みと認識できない")
        phone_with_token = Session(store, token=web.token)
        self.assertEqual(phone_with_token.read("address", prefer=0), "東京都…")

    def test_token_tracks_reads_too(self):
        store = ReplicatedStore(num_followers=1)
        Session(store).write("x", 1)
        s = Session(store)
        s.read("x", prefer=LEADER)
        self.assertEqual(s.token, 1, "読んだ状態の LSN もトークンに反映される")

    def test_validation(self):
        store = ReplicatedStore(num_followers=1)
        with self.assertRaises(ValueError):
            Session(store, fallback="retry")
        with self.assertRaises(ValueError):
            Session(store, token=-1)
        with self.assertRaises(IndexError):
            Session(store).read("x", prefer=3)


if __name__ == "__main__":
    unittest.main()
