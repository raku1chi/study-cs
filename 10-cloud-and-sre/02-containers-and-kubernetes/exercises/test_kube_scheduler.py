"""10.2 ミニ・スケジューラ — テスト

実行: python3 tools/check.py 10.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from collections import Counter

from kube_scheduler import (
    Node,
    PodSpec,
    Taint,
    Toleration,
    filter_node,
    parse_cpu,
    parse_memory,
    preempt,
    schedule,
    score_node,
    tolerates,
)

GPU_TAINT = Taint("dedicated", "gpu", "NoSchedule")


def cluster():
    return [
        Node("node-a", cpu="4", memory="8Gi", labels={"zone": "a", "disk": "ssd"}),
        Node("node-b", cpu="4", memory="8Gi", labels={"zone": "b"},
             pods=[PodSpec("existing", cpu="2", memory="2Gi")]),
        Node("node-c", cpu="2", memory="4Gi", labels={"zone": "c", "gpu": "true"}, taints=[GPU_TAINT]),
    ]


class TestExercise1Quantities(unittest.TestCase):
    def test_cpu(self):
        cases = {"250m": 250, "1": 1000, "0.5": 500, "2.25": 2250, ".5": 500, "1500m": 1500, "0": 0, " 2 ": 2000}
        for q, expected in cases.items():
            self.assertEqual(parse_cpu(q), expected, q)

    def test_cpu_invalid(self):
        for q in ["", "abc", "-1", "1.5m", "0.0001", "1k", "1 m", "m", "1e3"]:
            with self.assertRaises(ValueError, msg=q):
                parse_cpu(q)

    def test_memory(self):
        cases = {
            "128Mi": 128 * 2**20, "1Gi": 2**30, "1G": 10**9, "1.5Gi": 1610612736, "129M": 129 * 10**6,
            "128974848": 128974848, "1k": 1000, "1Ki": 1024, "2Ti": 2 * 2**40, "0.5": 1, "0": 0,
        }
        for q, expected in cases.items():
            self.assertEqual(parse_memory(q), expected, q)

    def test_si_and_binary_units_differ(self):
        # 1.1 章の KB と KiB の違い: 1Gi は 1G より約 7% 大きい
        self.assertAlmostEqual(parse_memory("1Gi") / parse_memory("1G"), 1.073741824)

    def test_memory_milli_suffix_is_rejected(self):
        with self.assertRaises(ValueError) as cm:
            parse_memory("400m")
        self.assertIn("Mi", str(cm.exception), "書き間違いの可能性をメッセージで伝える")

    def test_memory_invalid(self):
        for q in ["", "1K", "1gb", "-1Mi", "Mi", "1.2.3Gi", "1e9"]:
            with self.assertRaises(ValueError, msg=q):
                parse_memory(q)


class TestExercise2Filter(unittest.TestCase):
    def test_tolerations(self):
        self.assertTrue(tolerates([Toleration("dedicated", "Equal", "gpu", "NoSchedule")], GPU_TAINT))
        self.assertTrue(tolerates([Toleration("dedicated", "Equal", "gpu")], GPU_TAINT), "effect が空なら全 effect")
        self.assertTrue(tolerates([Toleration("dedicated", "Exists")], GPU_TAINT))
        self.assertTrue(tolerates([Toleration(operator="Exists")], GPU_TAINT), "キーなしの Exists は全部許容")
        self.assertFalse(tolerates([Toleration("dedicated", "Equal", "tpu")], GPU_TAINT))
        self.assertFalse(tolerates([Toleration("dedicated", "Exists", effect="NoExecute")], GPU_TAINT))
        self.assertFalse(tolerates([], GPU_TAINT))
        with self.assertRaises(ValueError):
            tolerates([Toleration("dedicated", "In", "gpu")], GPU_TAINT)

    def test_filter_reasons(self):
        a, b, c = cluster()
        pod = PodSpec("api", cpu="500m", memory="1Gi")
        self.assertEqual(filter_node(pod, a), [])
        self.assertEqual(filter_node(pod, c), ["node(s) had untolerated taint {dedicated: gpu}"])
        tolerant = PodSpec("trainer", cpu="500m", memory="1Gi",
                           tolerations=[Toleration("dedicated", "Equal", "gpu", "NoSchedule")])
        self.assertEqual(filter_node(tolerant, c), [])
        ssd = PodSpec("db", cpu="500m", memory="1Gi", node_selector={"disk": "ssd"})
        self.assertEqual(filter_node(ssd, a), [])
        self.assertEqual(filter_node(ssd, b), ["node(s) didn't match Pod's node affinity/selector"])
        big = PodSpec("big", cpu="2500m", memory="7Gi")
        self.assertEqual(filter_node(big, b), ["Insufficient cpu", "Insufficient memory"],
                         "requests の合計で判定する（既存 2 CPU + 2.5 CPU > 4 CPU）")

    def test_prefer_no_schedule_does_not_filter(self):
        node = Node("soft", cpu="2", memory="2Gi", taints=[Taint("spot", "true", "PreferNoSchedule")])
        self.assertEqual(filter_node(PodSpec("p", cpu="1", memory="1Gi"), node), [])

    def test_no_execute_filters(self):
        node = Node("draining", cpu="2", memory="2Gi", taints=[Taint("node.kubernetes.io/unreachable", "", "NoExecute")])
        self.assertEqual(filter_node(PodSpec("p"), node),
                         ["node(s) had untolerated taint {node.kubernetes.io/unreachable: }"])


class TestExercise2Score(unittest.TestCase):
    def test_scores(self):
        a, b, _ = cluster()
        pod = PodSpec("api", cpu="500m", memory="1Gi")
        # node-a: CPU 0.5/4 = 12.5%, メモリ 1/8 = 12.5%
        self.assertEqual(score_node(pod, a, "LeastAllocated"), 87)
        self.assertEqual(score_node(pod, a, "MostAllocated"), 12)
        self.assertEqual(score_node(pod, a, "BalancedAllocation"), 100)
        # node-b: CPU 2.5/4 = 62.5%, メモリ 3/8 = 37.5%
        self.assertEqual(score_node(pod, b, "LeastAllocated"), 50)
        self.assertEqual(score_node(pod, b, "MostAllocated"), 50)
        self.assertEqual(score_node(pod, b, "BalancedAllocation"), 87)
        self.assertEqual(score_node(pod, a), 87, "既定は LeastAllocated")
        with self.assertRaises(ValueError):
            score_node(pod, a, "Random")

    def test_exact_arithmetic(self):
        node = Node("n", cpu="1", memory="100")
        pod = PodSpec("p", cpu="290m", memory="29")
        # 0.29 * 100 を浮動小数点で計算すると 28.999... になり、切り捨てで 28 になってしまう
        self.assertEqual(score_node(pod, node, "MostAllocated"), 29)


class TestExercise2Schedule(unittest.TestCase):
    def test_binds_to_best_node(self):
        nodes = cluster()
        result = schedule(PodSpec("api", cpu="500m", memory="1Gi"), nodes)
        self.assertEqual(result.node, "node-a")
        self.assertEqual(result.message, "Successfully assigned api to node-a")
        self.assertEqual([p.name for p in nodes[0].pods], ["api"], "選んだノードにバインドする")

    def test_ties_break_by_name(self):
        nodes = [Node("n2", cpu="2", memory="2Gi"), Node("n1", cpu="2", memory="2Gi")]
        self.assertEqual(schedule(PodSpec("p", cpu="1", memory="1Gi"), nodes).node, "n1")

    def test_unschedulable_message(self):
        nodes = cluster()
        result = schedule(PodSpec("sel", cpu="1", memory="1Gi", node_selector={"disk": "nvme"}), nodes)
        self.assertIsNone(result.node)
        self.assertEqual(
            result.message,
            "0/3 nodes are available: 2 node(s) didn't match Pod's node affinity/selector, "
            "1 node(s) had untolerated taint {dedicated: gpu}.",
        )
        result = schedule(PodSpec("huge", cpu="2500m", memory="9Gi"), nodes)
        # node-a はメモリ不足、node-b は CPU とメモリの両方が不足（1 ノードが 2 つの理由を持つ）
        self.assertEqual(
            result.message,
            "0/3 nodes are available: 1 Insufficient cpu, 2 Insufficient memory, "
            "1 node(s) had untolerated taint {dedicated: gpu}.",
        )
        self.assertTrue(all(p.name != "huge" for n in nodes for p in n.pods), "失敗したらバインドしない")

    def test_spread_vs_bin_packing(self):
        def run(strategy):
            nodes = [Node(f"n{i}", cpu="4", memory="8Gi") for i in range(3)]
            for i in range(6):
                self.assertIsNotNone(schedule(PodSpec(f"p{i}", cpu="1", memory="1Gi"), nodes, strategy).node)
            return Counter({n.name: len(n.pods) for n in nodes})

        self.assertEqual(run("LeastAllocated"), Counter({"n0": 2, "n1": 2, "n2": 2}), "分散配置")
        self.assertEqual(run("MostAllocated"), Counter({"n0": 4, "n1": 2, "n2": 0}), "詰め込み（ビンパッキング）")

    def test_prefer_no_schedule_is_avoided_but_usable(self):
        spot = Node("spot", cpu="8", memory="16Gi", taints=[Taint("spot", "true", "PreferNoSchedule")])
        small = Node("small", cpu="2", memory="4Gi")
        self.assertEqual(schedule(PodSpec("p1", cpu="1", memory="1Gi"), [spot, small]).node, "small",
                         "空きは spot の方が多いが、PreferNoSchedule で減点される")
        self.assertEqual(schedule(PodSpec("p2", cpu="1500m", memory="1Gi"), [spot, small]).node, "spot",
                         "他に置き場がなければ PreferNoSchedule のノードにも置く")
        tolerant = PodSpec("p3", cpu="1", memory="1Gi", tolerations=[Toleration("spot", "Exists")])
        self.assertEqual(schedule(tolerant, [spot, small]).node, "spot")


class TestExercise3Preemption(unittest.TestCase):
    def nodes(self):
        return [
            Node("n1", cpu="4", memory="8Gi", pods=[
                PodSpec("batch-1", cpu="2", memory="1Gi", priority=0),
                PodSpec("batch-2", cpu="1", memory="1Gi", priority=0),
                PodSpec("web-1", cpu="1", memory="1Gi", priority=100),
            ]),
            Node("n2", cpu="4", memory="8Gi", pods=[
                PodSpec("etl-1", cpu="2", memory="1Gi", priority=50),
                PodSpec("etl-2", cpu="2", memory="1Gi", priority=50),
            ]),
        ]

    def test_minimal_victims_on_best_node(self):
        nodes = self.nodes()
        pod = PodSpec("critical", cpu="2", memory="1Gi", priority=1000)
        self.assertIsNone(schedule(pod, nodes).node, "まず通常のスケジュールは失敗する")
        node, victims = preempt(pod, nodes)
        self.assertEqual(node, "n1", "犠牲の最高優先度が低い（0 < 50）ノードを選ぶ")
        self.assertEqual(victims, ["batch-1"], "2 CPU 空けば足りる: batch-1 だけで済む")
        self.assertEqual(sorted(p.name for p in nodes[0].pods), ["batch-2", "web-1"])
        self.assertEqual(schedule(pod, nodes).node, "n1")

    def test_reprieve_keeps_as_many_as_possible(self):
        nodes = [Node("n", cpu="4", memory="8Gi", pods=[
            PodSpec("low-a", cpu="1", memory="1Gi", priority=1),
            PodSpec("low-b", cpu="1", memory="1Gi", priority=2),
            PodSpec("low-c", cpu="1", memory="1Gi", priority=3),
            PodSpec("low-d", cpu="1", memory="1Gi", priority=4),
        ])]
        node, victims = preempt(PodSpec("vip", cpu="2", memory="1Gi", priority=10), nodes)
        self.assertEqual((node, victims), ("n", ["low-a", "low-b"]), "優先度の高いものから戻し、低いものを犠牲にする")

    def test_never_preempts_equal_or_higher_priority(self):
        nodes = [Node("n", cpu="2", memory="2Gi", pods=[PodSpec("peer", cpu="2", memory="1Gi", priority=100)])]
        self.assertIsNone(preempt(PodSpec("p", cpu="1", memory="1Gi", priority=100), nodes))
        self.assertEqual(len(nodes[0].pods), 1)

    def test_preemption_cannot_fix_selector_or_taint(self):
        nodes = [
            Node("gpu", cpu="2", memory="2Gi", taints=[GPU_TAINT],
                 pods=[PodSpec("low", cpu="2", memory="1Gi", priority=0)]),
            Node("hdd", cpu="2", memory="2Gi", labels={"disk": "hdd"},
                 pods=[PodSpec("low2", cpu="2", memory="1Gi", priority=0)]),
        ]
        pod = PodSpec("p", cpu="1", memory="1Gi", priority=1000, node_selector={"disk": "hdd"})
        self.assertEqual(preempt(pod, nodes), ("hdd", ["low2"]))
        pod2 = PodSpec("q", cpu="1", memory="1Gi", priority=1000, node_selector={"disk": "ssd"})
        self.assertIsNone(preempt(pod2, nodes))

    def test_not_enough_even_after_evicting_all_lower(self):
        nodes = [Node("n", cpu="4", memory="8Gi", pods=[
            PodSpec("high", cpu="3", memory="1Gi", priority=500),
            PodSpec("low", cpu="1", memory="1Gi", priority=0),
        ])]
        self.assertIsNone(preempt(PodSpec("p", cpu="2", memory="1Gi", priority=100), nodes))


if __name__ == "__main__":
    unittest.main()
