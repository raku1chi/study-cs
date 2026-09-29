"""7.5 メッセージングとイベント駆動 — ログ型ブローカーのテスト

実行: python3 tools/check.py 7.5   （またはこのディレクトリで python3 -m unittest -v test_minilog）
"""
import random
import unittest
import zlib

from minilog import Broker, CommitFailedError, Consumer, Record, partition_for_key, range_assign


def make_broker(partitions: int = 4, topic: str = "orders") -> Broker:
    b = Broker()
    b.create_topic(topic, partitions)
    return b


def drain(consumer: Consumer, rounds: int = 20) -> list[Record]:
    out: list[Record] = []
    for _ in range(rounds):
        batch = consumer.poll(max_records=7)
        if not batch:
            break
        out.extend(batch)
    return out


class TestExercise1Partitioning(unittest.TestCase):
    def test_partition_for_key_is_stable(self):
        self.assertEqual(partition_for_key("user:1", 8), zlib.crc32(b"user:1") % 8)
        self.assertEqual(partition_for_key("ユーザー", 3), zlib.crc32("ユーザー".encode("utf-8")) % 3)
        with self.assertRaises(ValueError):
            partition_for_key("k", 0)

    def test_range_assign_examples(self):
        self.assertEqual(range_assign(["b", "a"], 5), {"a": [0, 1, 2], "b": [3, 4]})
        self.assertEqual(range_assign(["c1", "c2", "c3"], 7), {"c1": [0, 1, 2], "c2": [3, 4], "c3": [5, 6]})
        self.assertEqual(range_assign(["x", "y", "z"], 2), {"x": [0], "y": [1], "z": []}, "パーティションより多いメンバーは暇になる")
        self.assertEqual(range_assign([], 3), {})

    def test_range_assign_covers_all_partitions_exactly_once(self):
        rng = random.Random(1)
        for _ in range(50):
            members = [f"m{i}" for i in range(rng.randrange(1, 8))]
            n = rng.randrange(0, 20)
            assigned = [p for parts in range_assign(members, n).values() for p in parts]
            self.assertEqual(sorted(assigned), list(range(n)))


class TestExercise2Broker(unittest.TestCase):
    def test_keyed_records_go_to_the_same_partition_with_increasing_offsets(self):
        b = make_broker(4)
        results = [b.produce("orders", {"n": i}, key="customer-42") for i in range(5)]
        partition = partition_for_key("customer-42", 4)
        self.assertEqual(results, [(partition, i) for i in range(5)])
        self.assertEqual(b.end_offset("orders", partition), 5)
        records = b.fetch("orders", partition, 0)
        self.assertEqual([r.offset for r in records], [0, 1, 2, 3, 4])
        self.assertEqual(records[0], Record("orders", partition, 0, "customer-42", {"n": 0}))

    def test_keyless_records_are_spread_round_robin(self):
        b = make_broker(3)
        self.assertEqual([b.produce("orders", i)[0] for i in range(7)], [0, 1, 2, 0, 1, 2, 0])

    def test_fetch_from_offset_with_limit(self):
        b = make_broker(1)
        for i in range(10):
            b.produce("orders", i)
        self.assertEqual([r.value for r in b.fetch("orders", 0, 7)], [7, 8, 9])
        self.assertEqual([r.value for r in b.fetch("orders", 0, 2, max_records=3)], [2, 3, 4])
        self.assertEqual(b.fetch("orders", 0, 10), [], "末尾（end_offset）から読むと空")

    def test_errors(self):
        b = make_broker(2)
        with self.assertRaises(ValueError):
            b.create_topic("orders", 2)
        with self.assertRaises(ValueError):
            b.create_topic("empty", 0)
        with self.assertRaises(KeyError):
            b.produce("nope", 1)
        with self.assertRaises(KeyError):
            b.fetch("nope", 0, 0)
        with self.assertRaises(ValueError):
            b.fetch("orders", 5, 0)
        with self.assertRaises(ValueError):
            b.fetch("orders", 0, 1)  # まだ 0 件なので、オフセット 1 は範囲外
        with self.assertRaises(ValueError):
            b.fetch("orders", 0, 0, max_records=0)
        self.assertEqual(b.partitions("orders"), 2)


class TestExercise3ConsumerGroups(unittest.TestCase):
    def test_single_consumer_gets_everything(self):
        b = make_broker(3)
        for i in range(30):
            b.produce("orders", i, key=f"k{i % 5}")
        c = Consumer(b, "billing", "c1", ["orders"])
        self.assertEqual(c.assignment(), [("orders", 0), ("orders", 1), ("orders", 2)])
        self.assertEqual(sorted(r.value for r in drain(c)), list(range(30)))
        self.assertEqual(c.poll(), [])

    def test_per_key_order_is_preserved(self):
        b = make_broker(4)
        produced: dict[str, list[int]] = {}
        rng = random.Random(2)
        for i in range(200):
            key = f"customer-{rng.randrange(10)}"
            b.produce("orders", i, key=key)
            produced.setdefault(key, []).append(i)
        seen: dict[str, list[int]] = {}
        for r in drain(Consumer(b, "g", "c1", ["orders"]), rounds=100):
            seen.setdefault(r.key, []).append(r.value)
        self.assertEqual(seen, produced, "同じキーのレコードは、書いた順に読まれる")

    def test_committed_offsets_survive_consumer_restart(self):
        b = make_broker(2)
        for i in range(10):
            b.produce("orders", i)
        c1 = Consumer(b, "g", "c1", ["orders"])
        first = drain(c1)
        self.assertEqual(len(first), 10)
        c1.close()  # 正常終了: コミットしてから抜ける
        self.assertEqual(b.committed("g", "orders", 0), 5)
        for i in range(10, 14):
            b.produce("orders", i)
        c2 = Consumer(b, "g", "c2", ["orders"])
        self.assertEqual(sorted(r.value for r in drain(c2)), [10, 11, 12, 13], "コミット済みの位置から再開する")

    def test_rebalance_splits_partitions_between_members(self):
        b = make_broker(4)
        a = Consumer(b, "g", "a", ["orders"])
        self.assertEqual(len(a.assignment()), 4)
        gen = b.generation("g")
        bb = Consumer(b, "g", "b", ["orders"])
        self.assertGreater(b.generation("g"), gen, "メンバーが増えると世代が進む")
        self.assertEqual(a.assignment(), [("orders", 0), ("orders", 1)])
        self.assertEqual(bb.assignment(), [("orders", 2), ("orders", 3)])
        for i in range(40):
            b.produce("orders", i)
        got_a = {(r.partition, r.offset) for r in drain(a)}
        got_b = {(r.partition, r.offset) for r in drain(bb)}
        self.assertFalse(got_a & got_b, "1 つのパーティションはグループ内の 1 人だけが読む")
        self.assertEqual(len(got_a | got_b), 40)
        bb.close()
        self.assertEqual(len(a.assignment()), 4, "メンバーが抜けると残りが引き継ぐ")

    def test_crash_before_commit_causes_redelivery(self):
        b = make_broker(2)
        for i in range(20):
            b.produce("orders", {"order": i, "amount": 100})
        a = Consumer(b, "billing", "a", ["orders"])
        processed_by_a = drain(a)  # 処理した（課金した）が……
        self.assertEqual(len(processed_by_a), 20)
        a.crash()  # ……コミットする前に落ちた
        c = Consumer(b, "billing", "c", ["orders"])
        redelivered = drain(c)
        self.assertEqual(len(redelivered), 20, "コミットしていないので、次の担当者に再配送される（at-least-once）")
        # 冪等な処理（(トピック, パーティション, オフセット) で重複を除く）なら、結果は 1 回分
        charged = {(r.topic, r.partition, r.offset): r.value["amount"] for r in processed_by_a + redelivered}
        self.assertEqual(sum(charged.values()), 20 * 100)

    def test_commit_after_processing_prevents_redelivery(self):
        b = make_broker(2)
        for i in range(8):
            b.produce("orders", i)
        a = Consumer(b, "g", "a", ["orders"])
        drain(a)
        a.commit()
        a.crash()
        c = Consumer(b, "g", "c", ["orders"])
        self.assertEqual(drain(c), [])

    def test_zombie_commit_is_rejected(self):
        b = make_broker(2)
        for i in range(6):
            b.produce("orders", i)
        a = Consumer(b, "g", "a", ["orders"])
        drain(a)
        b.leave_group("g", "a")  # a は GC で長く止まり、セッションが切れてグループから外された
        c = Consumer(b, "g", "c", ["orders"])
        drain(c)
        c.commit()
        with self.assertRaises(CommitFailedError):
            a.commit()  # 目覚めたゾンビのコミットは拒否される
        self.assertEqual(b.committed("g", "orders", 0), 3, "c のコミットが残っている")
        self.assertEqual(a.poll(), [], "外されたメンバーには何も割り当てられていない")

    def test_stale_generation_commit_is_rejected_until_next_poll(self):
        b = make_broker(2)
        b.produce("orders", "x")
        a = Consumer(b, "g", "a", ["orders"])
        drain(a)
        Consumer(b, "g", "b", ["orders"])  # リバランスが起きた
        with self.assertRaises(CommitFailedError):
            a.commit()
        a.poll()  # 新しい世代に追従する（コミットしていない進捗は捨てる）
        a.commit()

    def test_commit_validation(self):
        b = make_broker(2)
        a = Consumer(b, "g", "a", ["orders"])
        Consumer(b, "g", "z", ["orders"])
        a.poll()
        with self.assertRaises(CommitFailedError):
            b.commit("g", "a", b.generation("g"), {("orders", 1): 0})  # a の担当ではない
        with self.assertRaises(ValueError):
            b.commit("g", "a", b.generation("g"), {("orders", 0): 5})  # まだ書かれていない位置

    def test_independent_groups_each_get_all_records(self):
        b = make_broker(3)
        for i in range(12):
            b.produce("orders", i)
        billing = Consumer(b, "billing", "b1", ["orders"])
        analytics = Consumer(b, "analytics", "a1", ["orders"])
        self.assertEqual(len(drain(billing)), 12)
        self.assertEqual(len(drain(analytics)), 12, "グループが違えば、それぞれが全件を読む（pub/sub）")

    def test_multiple_topics_are_assigned_per_topic(self):
        b = Broker()
        b.create_topic("orders", 2)
        b.create_topic("payments", 3)
        x = Consumer(b, "g", "x", ["orders", "payments"])
        y = Consumer(b, "g", "y", ["orders", "payments"])
        self.assertEqual(x.assignment(), [("orders", 0), ("payments", 0), ("payments", 1)])
        self.assertEqual(y.assignment(), [("orders", 1), ("payments", 2)])
        with self.assertRaises(KeyError):
            Consumer(b, "g", "w", ["unknown-topic"])


if __name__ == "__main__":
    unittest.main()
