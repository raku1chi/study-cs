"""10.6 タグの監査と未配賦の費用 — テスト

実行: python3 tools/check.py 10.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from tag_audit import EXAMPLE_POLICY, UNALLOCATED, Resource, TagPolicy, audit, check_resource, cost_report

GOOD = {"team": "payments", "env": "prod", "cost-center": "CC-100"}

INVENTORY = [
    Resource("i-001", "vm", 120_000, dict(GOOD)),
    Resource("i-002", "vm", 80_000, {"team": "search", "env": "prod", "cost-center": "CC-200"}),
    Resource("db-01", "rds", 300_000, {"Team": "payments", "env": "prod", "cost-center": "CC-100"}),
    Resource("i-003", "vm", 40_000, {"team": "search", "env": "Prod", "cost-center": "CC-200"}),
    Resource("nat-1", "nat", 150_000, {}),
    Resource("s3-logs", "s3", 60_000, {"team": "platform", "env": "prod", "cost-center": "CC-999"}),
    Resource("i-004", "vm", 50_000, {"team": " ", "env": "dev", "cost-center": "CC-300"}),
    Resource("i-005", "vm", 30_000, {"team": "search", "env": "dev", "cost-center": "CC-200"}),
]


class TestExercise7Audit(unittest.TestCase):
    def test_compliant(self):
        self.assertEqual(check_resource(INVENTORY[0], EXAMPLE_POLICY), [])

    def test_missing_with_case_hint(self):
        self.assertEqual(check_resource(INVENTORY[2], EXAMPLE_POLICY), ["missing:team (found Team)"],
                         "タグのキーは大文字・小文字を区別する")

    def test_invalid_values(self):
        self.assertEqual(check_resource(INVENTORY[3], EXAMPLE_POLICY), ["invalid:env=Prod"])
        self.assertEqual(check_resource(INVENTORY[5], EXAMPLE_POLICY), ["invalid:cost-center=CC-999"])

    def test_blank_value_is_missing(self):
        self.assertEqual(check_resource(INVENTORY[6], EXAMPLE_POLICY), ["missing:team"])

    def test_all_missing_sorted_by_key(self):
        self.assertEqual(check_resource(INVENTORY[4], EXAMPLE_POLICY),
                         ["missing:cost-center", "missing:env", "missing:team"])

    def test_audit(self):
        report = audit(INVENTORY, EXAMPLE_POLICY)
        self.assertEqual(sorted(report), ["db-01", "i-003", "i-004", "nat-1", "s3-logs"])
        self.assertNotIn("i-001", report, "問題のないリソースは含めない")

    def test_extra_tags_are_fine(self):
        r = Resource("x", "vm", 1, dict(GOOD, owner="alice"))
        self.assertEqual(check_resource(r, EXAMPLE_POLICY), [])


class TestExercise7CostReport(unittest.TestCase):
    def test_report(self):
        report = cost_report(INVENTORY, EXAMPLE_POLICY)
        self.assertEqual(report["total"], 830_000)
        self.assertEqual(report["compliant_cost"], 230_000)
        self.assertAlmostEqual(report["compliance_by_count"], 3 / 8)
        self.assertAlmostEqual(report["compliance_by_cost"], 230_000 / 830_000)
        self.assertEqual(report["by_group"], {UNALLOCATED: 600_000, "payments": 120_000, "search": 110_000})
        self.assertEqual(list(report["by_group"]), [UNALLOCATED, "payments", "search"], "金額の大きい順")

    def test_count_and_cost_compliance_differ(self):
        report = cost_report(INVENTORY, EXAMPLE_POLICY)
        self.assertLess(report["compliance_by_cost"], report["compliance_by_count"],
                        "高価なリソース（DB・NAT）ほどタグが漏れていると、金額ベースの準拠率は低くなる")

    def test_group_by_other_key(self):
        report = cost_report(INVENTORY, EXAMPLE_POLICY, group_by="env")
        self.assertEqual(report["by_group"], {UNALLOCATED: 600_000, "prod": 200_000, "dev": 30_000})
        with self.assertRaises(ValueError):
            cost_report(INVENTORY, EXAMPLE_POLICY, group_by="owner")

    def test_empty_inventory(self):
        report = cost_report([], EXAMPLE_POLICY)
        self.assertEqual((report["total"], report["compliance_by_cost"], report["by_group"]), (0, 1.0, {}))

    def test_custom_policy(self):
        policy = TagPolicy({"owner": None})
        report = cost_report(INVENTORY, policy, group_by="owner")
        self.assertEqual(report["by_group"], {UNALLOCATED: 830_000})


if __name__ == "__main__":
    unittest.main()
