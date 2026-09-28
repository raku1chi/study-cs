"""10.1 ミニ terraform plan / apply — テスト

実行: python3 tools/check.py 10.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import copy
import unittest

from iac_plan import (
    UNKNOWN,
    Change,
    CloudError,
    CycleError,
    FakeCloud,
    Plan,
    apply,
    build_graph,
    find_refs,
    plan,
    refresh,
    resolve,
    topo_sort,
)

SCHEMA = {
    "aws_vpc": {"cidr_block"},
    "aws_subnet": {"vpc_id", "cidr_block", "availability_zone"},
    "aws_security_group": {"vpc_id", "name"},
    "aws_instance": {"ami", "subnet_id"},
}

VPC, SUBNET, SG, WEB = "aws_vpc.main", "aws_subnet.a", "aws_security_group.web", "aws_instance.web"


def base_config():
    return {
        VPC: {"attrs": {"cidr_block": "10.0.0.0/16", "tags": {"Name": "main"}}},
        SUBNET: {"attrs": {"vpc_id": "${aws_vpc.main.id}", "cidr_block": "10.0.1.0/24",
                           "availability_zone": "ap-northeast-1a"}},
        SG: {"attrs": {"vpc_id": "${aws_vpc.main.id}", "name": "web", "ingress": [443]}},
        WEB: {"attrs": {"ami": "ami-111", "instance_type": "t3.small", "subnet_id": "${aws_subnet.a.id}",
                        "security_groups": ["${aws_security_group.web.id}"]}},
    }


def deployed():
    """base_config を空の環境に apply した直後の (config, state, cloud)。"""
    config, state, cloud = base_config(), {}, FakeCloud()
    apply(plan(config, state, SCHEMA), config, state, cloud)
    return config, state, cloud


class TestExercise3Graph(unittest.TestCase):
    def test_find_refs(self):
        self.assertEqual(find_refs("${aws_vpc.main.id}"), {"aws_vpc.main"})
        self.assertEqual(find_refs({"a": ["x", {"b": "${aws_subnet.a.id}"}], "c": 3, "d": None}), {"aws_subnet.a"})
        self.assertEqual(find_refs("arn:${aws_s3_bucket.logs.id}/${aws_s3_bucket.logs.id}/*"), {"aws_s3_bucket.logs"})
        self.assertEqual(find_refs(["plain", 42, True]), set())
        with self.assertRaises(ValueError, msg=".id 以外の属性は参照できない"):
            find_refs("${aws_vpc.main.cidr_block}")
        with self.assertRaises(ValueError):
            find_refs("${var.region}")

    def test_resolve(self):
        ids = {"aws_vpc.main": "r-0001", "aws_subnet.a": "r-0002"}
        self.assertEqual(resolve("${aws_vpc.main.id}", ids.__getitem__), "r-0001")
        self.assertEqual(resolve({"x": ["${aws_subnet.a.id}", 1]}, ids.__getitem__), {"x": ["r-0002", 1]})
        self.assertEqual(resolve("arn:${aws_vpc.main.id}/*", ids.__getitem__), "arn:r-0001/*")
        lookup = lambda ref: UNKNOWN if ref == "aws_subnet.a" else ids[ref]  # noqa: E731
        self.assertIs(resolve(["${aws_vpc.main.id}", "${aws_subnet.a.id}"], lookup), UNKNOWN,
                      "1 つでも未確定の参照があれば値全体が未確定")
        original = {"tags": {"Name": "x"}}
        resolved = resolve(original, ids.__getitem__)
        self.assertEqual(resolved, original)
        resolved["tags"]["Name"] = "changed"
        self.assertEqual(original["tags"]["Name"], "x", "resolve は入れ物をコピーする（元の設定を共有しない）")

    def test_build_graph(self):
        config = base_config()
        config["aws_s3_bucket.logs"] = {"attrs": {}, "depends_on": [VPC]}
        graph = build_graph(config)
        self.assertEqual(graph[VPC], set())
        self.assertEqual(graph[SUBNET], {VPC})
        self.assertEqual(graph[WEB], {SUBNET, SG})
        self.assertEqual(graph["aws_s3_bucket.logs"], {VPC}, "depends_on も依存に含める")

    def test_build_graph_rejects_unknown_reference(self):
        config = base_config()
        del config[SG]
        with self.assertRaises(ValueError):
            build_graph(config)
        with self.assertRaises(ValueError):
            build_graph({"no_dot": {"attrs": {}}})

    def test_topo_sort_is_deterministic(self):
        graph = {"d": {"b", "c"}, "b": {"a"}, "c": {"a"}, "a": set(), "e": set()}
        self.assertEqual(topo_sort(graph), ["a", "b", "c", "d", "e"])
        self.assertEqual(topo_sort(graph, key=lambda n: -ord(n)), ["e", "a", "c", "b", "d"])
        self.assertEqual(topo_sort({}), [])

    def test_topo_sort_respects_all_edges(self):
        graph = {f"n{i}": {f"n{j}" for j in range(i) if (i * j) % 3 == 1} for i in range(30)}
        order = topo_sort(graph)
        pos = {n: i for i, n in enumerate(order)}
        self.assertEqual(sorted(order), sorted(graph))
        for n, deps in graph.items():
            for d in deps:
                self.assertLess(pos[d], pos[n], f"{d} は {n} より先")

    def assert_is_cycle(self, graph, cycle):
        self.assertGreaterEqual(len(cycle), 2)
        self.assertEqual(cycle[0], cycle[-1], "cycle は始点に戻る形 [a, ..., a]")
        for a, b in zip(cycle, cycle[1:]):
            self.assertIn(b, graph[a], f"{a} は {b} に依存していない")

    def test_cycle_detection(self):
        graph = {"a": {"c"}, "b": {"a"}, "c": {"b"}, "x": set(), "y": {"x", "a"}}
        with self.assertRaises(CycleError) as cm:
            topo_sort(graph)
        self.assert_is_cycle(graph, cm.exception.cycle)
        self.assertEqual(set(cm.exception.cycle), {"a", "b", "c"})
        self.assertIsInstance(cm.exception, ValueError)

    def test_self_loop(self):
        with self.assertRaises(CycleError) as cm:
            topo_sort({"a": {"a"}})
        self.assertEqual(cm.exception.cycle, ["a", "a"])

    def test_topo_sort_rejects_unknown_node(self):
        with self.assertRaises(ValueError):
            topo_sort({"a": {"zzz"}})


class TestExercise4Plan(unittest.TestCase):
    def test_initial_plan_creates_in_dependency_order(self):
        p = plan(base_config(), {}, SCHEMA)
        self.assertEqual(p.changes[WEB], Change(WEB, "create"))
        self.assertEqual(p.steps, [("create", VPC), ("create", SG), ("create", SUBNET), ("create", WEB)])
        self.assertEqual(p.summary(), "Plan: 4 to add, 0 to change, 0 to destroy.")

    def test_no_changes_after_apply(self):
        config, state, _ = deployed()
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes, {})
        self.assertEqual(p.steps, [])
        self.assertEqual(p.summary(), "No changes. Your infrastructure matches the configuration.")

    def test_mutable_change_is_in_place_update(self):
        config, state, _ = deployed()
        config[WEB]["attrs"]["instance_type"] = "t3.large"
        config[VPC]["attrs"]["tags"] = {"Name": "main", "env": "prod"}
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes, {WEB: Change(WEB, "update", ("instance_type",)),
                                     VPC: Change(VPC, "update", ("tags",))})
        # 2 つの更新の間には依存する操作がない（サブネットは変わらない）ので、アドレス順
        self.assertEqual(p.steps, [("update", WEB), ("update", VPC)])
        self.assertEqual(p.summary(), "Plan: 0 to add, 2 to change, 0 to destroy.")

    def test_added_and_removed_attributes_are_changes(self):
        config, state, _ = deployed()
        del config[VPC]["attrs"]["tags"]
        config[SG]["attrs"]["description"] = "web tier"
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes[VPC], Change(VPC, "update", ("tags",)))
        self.assertEqual(p.changes[SG], Change(SG, "update", ("description",)))

    def test_force_new_change_cascades(self):
        config, state, _ = deployed()
        config[VPC]["attrs"]["cidr_block"] = "10.1.0.0/16"
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes[VPC], Change(VPC, "replace", ("cidr_block",), ("cidr_block",)))
        self.assertEqual(p.changes[SUBNET], Change(SUBNET, "replace", ("vpc_id",), ("vpc_id",)),
                         "VPC の id が変わるので、vpc_id（置き換えが必要な属性）が未確定になる")
        self.assertEqual(p.changes[WEB], Change(WEB, "replace", ("security_groups", "subnet_id"), ("subnet_id",)))
        self.assertEqual(p.steps, [
            ("destroy", WEB), ("destroy", SG), ("destroy", SUBNET), ("destroy", VPC),
            ("create", VPC), ("create", SG), ("create", SUBNET), ("create", WEB),
        ])
        self.assertEqual(p.summary(), "Plan: 4 to add, 0 to change, 4 to destroy.")

    def test_removed_resources_are_destroyed_dependents_first(self):
        config, state, _ = deployed()
        del config[WEB], config[SG]
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes, {WEB: Change(WEB, "delete"), SG: Change(SG, "delete")})
        self.assertEqual(p.steps, [("destroy", WEB), ("destroy", SG)])

    def test_dependent_update_happens_before_delete(self):
        config, state, _ = deployed()
        del config[SG]
        config[WEB]["attrs"]["security_groups"] = []
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes[WEB].action, "update")
        self.assertEqual(p.changes[SG].action, "delete")
        self.assertEqual(p.steps, [("update", WEB), ("destroy", SG)],
                         "参照を外す更新が先。逆だと削除が DependencyViolation になる")

    def test_replace_without_cbd_is_destroy_then_create(self):
        config, state, _ = deployed()
        config[SG]["attrs"]["name"] = "web-v2"
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes[SG], Change(SG, "replace", ("name",), ("name",)))
        self.assertEqual(p.changes[WEB], Change(WEB, "update", ("security_groups",)))
        self.assertEqual(p.steps, [("destroy", SG), ("create", SG), ("update", WEB)])

    def test_create_before_destroy(self):
        config, state, _ = deployed()
        config[SG]["attrs"]["name"] = "web-v2"
        config[SG]["create_before_destroy"] = True
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes[SG], Change(SG, "replace", ("name",), ("name",), True))
        self.assertEqual(p.steps, [("create", SG), ("update", WEB), ("destroy", SG)])

    def test_cbd_propagates_to_dependencies(self):
        config, state, _ = deployed()
        config[VPC]["attrs"]["cidr_block"] = "10.1.0.0/16"
        config[WEB]["create_before_destroy"] = True
        p = plan(config, state, SCHEMA)
        for address in (VPC, SUBNET, SG, WEB):
            self.assertTrue(p.changes[address].create_before_destroy, f"{address} にも伝播する")
        self.assertEqual(p.steps, [
            ("create", VPC), ("create", SG), ("create", SUBNET), ("create", WEB),
            ("destroy", WEB), ("destroy", SG), ("destroy", SUBNET), ("destroy", VPC),
        ])

    def test_cbd_does_not_propagate_to_dependents(self):
        config, state, _ = deployed()
        config[VPC]["attrs"]["cidr_block"] = "10.1.0.0/16"
        config[VPC]["create_before_destroy"] = True
        p = plan(config, state, SCHEMA)
        self.assertTrue(p.changes[VPC].create_before_destroy)
        self.assertFalse(p.changes[SUBNET].create_before_destroy)
        pos = {step: i for i, step in enumerate(p.steps)}
        self.assertLess(pos[("create", VPC)], pos[("create", SUBNET)])
        self.assertLess(pos[("destroy", SUBNET)], pos[("create", SUBNET)])
        self.assertLess(pos[("destroy", SUBNET)], pos[("destroy", VPC)])
        self.assertLess(pos[("create", VPC)], pos[("destroy", VPC)])

    def test_plan_does_not_modify_inputs(self):
        config, state, _ = deployed()
        config[VPC]["attrs"]["cidr_block"] = "10.1.0.0/16"
        config_before, state_before = copy.deepcopy(config), copy.deepcopy(state)
        plan(config, state, SCHEMA)
        self.assertEqual(config, config_before)
        self.assertEqual(state, state_before)

    def test_plan_rejects_cycles(self):
        config = {
            "aws_security_group.a": {"attrs": {"peer": "${aws_security_group.b.id}"}},
            "aws_security_group.b": {"attrs": {"peer": "${aws_security_group.a.id}"}},
        }
        with self.assertRaises(CycleError):
            plan(config, {}, SCHEMA)


class TestExercise5Apply(unittest.TestCase):
    def test_apply_creates_resources_with_resolved_references(self):
        config, state, cloud = deployed()
        self.assertEqual(len(cloud.resources), 4)
        vpc_id, subnet_id, sg_id = state[VPC]["id"], state[SUBNET]["id"], state[SG]["id"]
        self.assertEqual(cloud.read(subnet_id)["vpc_id"], vpc_id)
        self.assertEqual(cloud.read(state[WEB]["id"])["security_groups"], [sg_id])
        self.assertEqual(state[WEB]["deps"], [SG, SUBNET], "state に依存関係を記録する（削除順の決定に使う）")
        self.assertEqual(state[SUBNET]["attrs"]["vpc_id"], vpc_id, "state には解決済みの値を記録する")

    def test_cascade_replacement_applies_cleanly(self):
        config, state, cloud = deployed()
        old_ids = {a: state[a]["id"] for a in state}
        config[VPC]["attrs"]["cidr_block"] = "10.1.0.0/16"
        apply(plan(config, state, SCHEMA), config, state, cloud)
        self.assertEqual(len(cloud.resources), 4)
        for address, old in old_ids.items():
            self.assertNotEqual(state[address]["id"], old, f"{address} は作り直されている")
            self.assertIsNone(cloud.read(old))
        self.assertEqual(plan(config, state, SCHEMA).changes, {}, "apply の後は差分がない（収束する）")

    def test_replace_without_cbd_hits_dependency_violation(self):
        config, state, cloud = deployed()
        config[SG]["attrs"]["name"] = "web-v2"
        before = copy.deepcopy(state)
        with self.assertRaises(CloudError) as cm:
            apply(plan(config, state, SCHEMA), config, state, cloud)
        self.assertIn("DependencyViolation", str(cm.exception))
        self.assertEqual(state, before, "失敗した操作は state に反映しない")

    def test_create_before_destroy_succeeds(self):
        config, state, cloud = deployed()
        old_sg = state[SG]["id"]
        config[SG]["attrs"]["name"] = "web-v2"
        config[SG]["create_before_destroy"] = True
        apply(plan(config, state, SCHEMA), config, state, cloud)
        self.assertIsNone(cloud.read(old_sg), "古いセキュリティグループは最後に削除される")
        self.assertNotIn("deposed", state[SG])
        self.assertEqual(cloud.read(state[WEB]["id"])["security_groups"], [state[SG]["id"]])
        self.assertEqual(len(cloud.resources), 4)
        self.assertEqual(plan(config, state, SCHEMA).changes, {})

    def test_cbd_keeps_deposed_object_until_destroy(self):
        config, state, cloud = deployed()
        old_sg = state[SG]["id"]
        config[SG]["attrs"]["name"] = "web-v2"
        config[SG]["create_before_destroy"] = True
        p = plan(config, state, SCHEMA)
        # 最後の destroy だけを残して実行し、途中の state を観察する
        apply(Plan(p.changes, p.steps[:-1]), config, state, cloud)
        self.assertEqual(state[SG]["deposed"], old_sg)
        self.assertIsNotNone(cloud.read(old_sg))
        apply(Plan(p.changes, p.steps[-1:]), config, state, cloud)
        self.assertNotIn("deposed", state[SG])
        self.assertIsNone(cloud.read(old_sg))

    def test_delete_with_dependent_update(self):
        config, state, cloud = deployed()
        del config[SG]
        config[WEB]["attrs"]["security_groups"] = []
        apply(plan(config, state, SCHEMA), config, state, cloud)
        self.assertNotIn(SG, state)
        self.assertEqual(len(cloud.resources), 3)
        self.assertEqual(state[WEB]["deps"], [SUBNET], "依存関係の記録も更新する")

    def test_refresh_detects_drift_and_plan_reverts_it(self):
        config, state, cloud = deployed()
        web_id = state[WEB]["id"]
        cloud.resources[web_id]["attrs"]["instance_type"] = "t3.2xlarge"  # 誰かがコンソールで変更した
        drift = refresh(state, cloud)
        self.assertEqual(drift, {WEB: ["instance_type"]})
        self.assertEqual(state[WEB]["attrs"]["instance_type"], "t3.2xlarge")
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes, {WEB: Change(WEB, "update", ("instance_type",))})
        apply(p, config, state, cloud)
        self.assertEqual(cloud.read(web_id)["instance_type"], "t3.small", "設定の値に戻る")
        self.assertEqual(refresh(state, cloud), {})

    def test_refresh_detects_deleted_resource(self):
        config, state, cloud = deployed()
        cloud.delete(state[WEB]["id"])  # 誰かがコンソールで削除した
        self.assertEqual(refresh(state, cloud), {WEB: ["(deleted)"]})
        self.assertNotIn(WEB, state)
        p = plan(config, state, SCHEMA)
        self.assertEqual(p.changes, {WEB: Change(WEB, "create")})
        apply(p, config, state, cloud)
        self.assertEqual(len(cloud.resources), 4)

    def test_full_lifecycle_never_violates_cloud_constraints(self):
        config, state, cloud = deployed()
        edits = [
            lambda c: c[SUBNET]["attrs"].update(availability_zone="ap-northeast-1c"),
            lambda c: c.update({"aws_instance.batch": {"attrs": {
                "ami": "ami-222", "instance_type": "c7g.large", "subnet_id": "${aws_subnet.a.id}",
                "security_groups": []}}}),
            lambda c: c[WEB]["attrs"].update(ami="ami-333"),
            lambda c: c.pop("aws_instance.batch"),
            lambda c: c[VPC]["attrs"].update(cidr_block="10.9.0.0/16"),
        ]
        for edit in edits:
            edit(config)
            apply(plan(config, state, SCHEMA), config, state, cloud)
            self.assertEqual(plan(config, state, SCHEMA).changes, {})
            self.assertEqual(sorted(cloud.resources), sorted(e["id"] for e in state.values()))


if __name__ == "__main__":
    unittest.main()
