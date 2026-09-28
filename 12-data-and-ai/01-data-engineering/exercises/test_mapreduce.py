"""12.1 演習1: MapReduce — テスト

実行: python3 tools/check.py 12.1   （またはこのディレクトリで python3 -m unittest -v test_mapreduce）
"""
import collections
import os
import random
import subprocess
import sys
import unittest
from pathlib import Path

from mapreduce import (
    JobResult,
    hash_partitioner,
    inverted_index,
    reduce_side_join,
    run_mapreduce,
    split_input,
    tokenize,
    word_count,
)

HERE = Path(__file__).resolve().parent

LINES = [
    "the quick brown fox jumps over the lazy dog",
    "The dog barks. The fox runs!",
    "a quick movement of the enemy will jeopardize six gunboats",
    "the the the the",
    "",
    "Dog and fox and dog",
]


def identity_mapper(record):
    yield record


def collect_reducer(key, values):
    yield key, list(values)


class TestPartitionerAndSplits(unittest.TestCase):
    def test_partition_in_range(self):
        for n in (1, 2, 3, 7, 16):
            for key in ["apple", "りんご", 42, ("a", 1), 3.5, ""]:
                p = hash_partitioner(key, n)
                self.assertIsInstance(p, int)
                self.assertTrue(0 <= p < n, (key, n, p))

    def test_partition_is_deterministic(self):
        self.assertEqual(hash_partitioner("apple", 8), hash_partitioner("apple", 8))

    def test_partition_stable_across_processes(self):
        # 組み込みの hash() は PYTHONHASHSEED によって変わる。パーティショナは変わってはいけない
        code = (
            "from mapreduce import hash_partitioner\n"
            "print([hash_partitioner(k, 97) for k in ['apple', 'banana', 'cherry', 'データ', 'x' * 50]])"
        )
        outputs = set()
        for seed in ("1", "2", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONDONTWRITEBYTECODE="1")
            proc = subprocess.run(
                [sys.executable, "-c", code], cwd=HERE, env=env,
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            outputs.add(proc.stdout.strip())
        self.assertEqual(len(outputs), 1, f"プロセスごとに結果が変わっています: {outputs}")

    def test_partition_spreads_keys(self):
        counts = collections.Counter(hash_partitioner(f"user-{i}", 4) for i in range(2000))
        self.assertEqual(set(counts), {0, 1, 2, 3})
        for p, c in counts.items():
            self.assertTrue(350 <= c <= 650, f"パーティション {p} に偏りすぎ: {counts}")

    def test_partition_rejects_bad_n(self):
        with self.assertRaises(ValueError):
            hash_partitioner("a", 0)

    def test_split_input_sizes_and_order(self):
        records = list(range(10))
        splits = split_input(records, 3)
        self.assertEqual(splits, [[0, 1, 2, 3], [4, 5, 6], [7, 8, 9]])
        self.assertEqual(split_input([1, 2], 4), [[1], [2], [], []])
        self.assertEqual(split_input([], 2), [[], []])
        with self.assertRaises(ValueError):
            split_input(records, 0)


class TestEngine(unittest.TestCase):
    def test_groups_values_and_sorts_keys_within_partition(self):
        records = [("b", 1), ("a", 2), ("b", 3), ("c", 4), ("a", 5)]
        result = run_mapreduce(records, identity_mapper, collect_reducer, num_partitions=1, num_map_tasks=2)
        self.assertIsInstance(result, JobResult)
        self.assertEqual(result.partitions, [[("a", [2, 5]), ("b", [1, 3]), ("c", [4])]])

    def test_keys_are_sorted_in_every_partition(self):
        rng = random.Random(1)
        records = [(rng.randrange(100), i) for i in range(500)]
        result = run_mapreduce(records, identity_mapper, collect_reducer, num_partitions=5, num_map_tasks=3)
        self.assertEqual(len(result.partitions), 5)
        for part in result.partitions:
            keys = [k for k, _ in part]
            self.assertEqual(keys, sorted(keys))
            self.assertEqual(len(keys), len(set(keys)), "Reducer は 1 つのキーにつき 1 回だけ呼ばれるべき")
        self.assertEqual(sorted(k for k, _ in result.records()), sorted({k for k, _ in records}))

    def test_same_key_goes_to_one_partition(self):
        records = [("hot", i) for i in range(20)] + [("cold", 1)]
        result = run_mapreduce(records, identity_mapper, collect_reducer, num_partitions=4, num_map_tasks=4)
        found = [i for i, part in enumerate(result.partitions) for k, _ in part if k == "hot"]
        self.assertEqual(len(found), 1)
        self.assertEqual(result.as_dict()["hot"], list(range(20)), "値は Map タスク順・出力順に並ぶ")

    def test_counters(self):
        result = word_count(LINES, num_partitions=3, num_map_tasks=2, use_combiner=False)
        c = result.counters
        n_words = sum(len(tokenize(line)) for line in LINES)
        self.assertEqual(c["map_input_records"], len(LINES))
        self.assertEqual(c["map_output_records"], n_words)
        self.assertEqual(c["combine_output_records"], 0)
        self.assertEqual(c["shuffle_records"], n_words, "Combiner なしでは Map 出力がすべてシャッフルされる")
        self.assertEqual(sum(result.shuffle_sizes), c["shuffle_records"])
        distinct = len({w for line in LINES for w in tokenize(line)})
        self.assertEqual(c["reduce_input_groups"], distinct)
        self.assertEqual(c["reduce_output_records"], distinct)

    def test_custom_partitioner_causes_skew(self):
        result = run_mapreduce(
            [("k%d" % i, i) for i in range(30)], identity_mapper, collect_reducer,
            num_partitions=3, num_map_tasks=2, partitioner=lambda key, n: 0,
        )
        self.assertEqual(result.shuffle_sizes, [30, 0, 0])
        self.assertEqual(result.partitions[1], [])

    def test_bad_partitioner_and_arguments(self):
        with self.assertRaises(ValueError):
            run_mapreduce([("a", 1)], identity_mapper, collect_reducer, partitioner=lambda k, n: n)
        with self.assertRaises(ValueError):
            run_mapreduce([("a", 1)], identity_mapper, collect_reducer, num_partitions=0)
        with self.assertRaises(ValueError):
            run_mapreduce([("a", 1)], identity_mapper, collect_reducer, num_map_tasks=0)

    def test_empty_input(self):
        result = run_mapreduce([], identity_mapper, collect_reducer, num_partitions=2)
        self.assertEqual(result.partitions, [[], []])
        self.assertEqual(result.counters["map_input_records"], 0)


class TestWordCount(unittest.TestCase):
    def expected(self):
        return collections.Counter(w for line in LINES for w in tokenize(line))

    def test_word_count(self):
        result = word_count(LINES)
        self.assertEqual(result.as_dict(), dict(self.expected()))
        self.assertEqual(result.as_dict()["the"], 9)

    def test_result_independent_of_parallelism(self):
        expected = dict(self.expected())
        for parts in (1, 2, 5):
            for tasks in (1, 3, 8):
                for comb in (True, False):
                    got = word_count(LINES, num_partitions=parts, num_map_tasks=tasks, use_combiner=comb)
                    self.assertEqual(got.as_dict(), expected, (parts, tasks, comb))

    def test_combiner_reduces_shuffle(self):
        lines = ["the cat and the hat and the bat"] * 50
        without = word_count(lines, num_map_tasks=4, use_combiner=False)
        with_c = word_count(lines, num_map_tasks=4, use_combiner=True)
        self.assertEqual(without.as_dict(), with_c.as_dict())
        self.assertEqual(without.counters["shuffle_records"], 400)
        # 各 Map タスク内で 5 種類の単語に集約されるので 4 タスク × 5 語 = 20 件
        self.assertEqual(with_c.counters["combine_output_records"], 20)
        self.assertEqual(with_c.counters["shuffle_records"], 20)


class TestInvertedIndex(unittest.TestCase):
    DOCS = {
        "d1": "Spark and Hadoop process big data",
        "d2": "Hadoop MapReduce writes to disk; Spark keeps data in memory",
        "d3": "data data data",
        "d4": "",
    }

    def test_postings(self):
        index = inverted_index(self.DOCS, num_partitions=3, num_map_tasks=2).as_dict()
        self.assertEqual(index["data"], ["d1", "d2", "d3"])
        self.assertEqual(index["hadoop"], ["d1", "d2"])
        self.assertEqual(index["memory"], ["d2"])
        self.assertNotIn("", index)
        vocab = {w for text in self.DOCS.values() for w in tokenize(text)}
        self.assertEqual(set(index), vocab)

    def test_mapper_deduplicates_within_document(self):
        result = inverted_index({"d3": "data data data"})
        self.assertEqual(result.counters["map_output_records"], 1)


class TestReduceSideJoin(unittest.TestCase):
    ORDERS = [
        {"order_id": 1, "customer_id": 10, "amount": 1200},
        {"order_id": 2, "customer_id": 20, "amount": 800},
        {"order_id": 3, "customer_id": 10, "amount": 500},
        {"order_id": 4, "customer_id": 99, "amount": 300},  # 顧客マスタにない
        {"order_id": 5, "customer_id": None, "amount": 100},  # キーが NULL
    ]
    CUSTOMERS = [
        {"id": 10, "name": "佐藤", "region": "関東"},
        {"id": 20, "name": "鈴木", "region": "関西"},
        {"id": 30, "name": "高橋", "region": "九州"},  # 注文がない
    ]

    def test_inner_join(self):
        result = reduce_side_join(self.ORDERS, self.CUSTOMERS, left_key="customer_id", right_key="id")
        rows = sorted((row for _, row in result.records()), key=lambda r: r["order_id"])
        self.assertEqual([r["order_id"] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0], {"order_id": 1, "customer_id": 10, "amount": 1200,
                                   "id": 10, "name": "佐藤", "region": "関東"})
        self.assertEqual(rows[1]["region"], "関西")
        self.assertTrue(all(k == row["customer_id"] for k, row in result.records()))

    def test_many_to_many(self):
        left = [{"k": "x", "l": i} for i in range(3)]
        right = [{"k": "x", "r": j} for j in range(4)] + [{"k": "y", "r": 9}]
        result = reduce_side_join(left, right, left_key="k", right_key="k", num_partitions=2)
        pairs = sorted((row["l"], row["r"]) for _, row in result.records())
        self.assertEqual(pairs, [(i, j) for i in range(3) for j in range(4)])

    def test_null_keys_never_match(self):
        left = [{"k": None, "v": 1}]
        right = [{"k": None, "w": 2}]
        result = reduce_side_join(left, right, left_key="k", right_key="k")
        self.assertEqual(result.records(), [])
        self.assertEqual(result.counters["map_output_records"], 0)


if __name__ == "__main__":
    unittest.main()
