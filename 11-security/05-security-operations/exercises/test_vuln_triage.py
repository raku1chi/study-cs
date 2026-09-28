"""11.5 脆弱性トリアージ（vuln_triage）— テスト

実行: python3 tools/check.py 11.5   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from vuln_triage import (
    SLA_DAYS,
    Finding,
    Triage,
    prioritize,
    severity_band,
    summarize,
    triage_all,
)


class TestExercise1Severity(unittest.TestCase):
    def test_bands(self):
        cases = {0.0: "none", 3.9: "low", 4.0: "medium", 6.9: "medium",
                 7.0: "high", 8.9: "high", 9.0: "critical", 10.0: "critical", 0.1: "low"}
        for cvss, band in cases.items():
            self.assertEqual(severity_band(cvss), band, cvss)

    def test_out_of_range(self):
        for bad in (-0.1, 10.1):
            with self.assertRaises(ValueError):
                severity_band(bad)


class TestExercise2Prioritize(unittest.TestCase):
    def base(self, **kw):
        args = dict(id="CVE-x", cvss=5.0, epss=0.01, kev=False, internet_facing=False, asset_criticality=3)
        args.update(kw)
        return Finding(**args)

    def test_kev_is_p1(self):
        t = prioritize(self.base(cvss=6.0, kev=True))
        self.assertEqual(t.priority, "P1")
        self.assertEqual(t.due_days, SLA_DAYS["P1"])
        self.assertIn("KEV（悪用が確認済み）", t.rationale)

    def test_critical_internet_facing_is_p1(self):
        self.assertEqual(prioritize(self.base(cvss=9.5, internet_facing=True)).priority, "P1")
        self.assertEqual(prioritize(self.base(cvss=9.5, internet_facing=False)).priority, "P3",
                         "同じ深刻度でも露出していなければ下がる")

    def test_high_epss_is_p2(self):
        self.assertEqual(prioritize(self.base(cvss=5.0, epss=0.6)).priority, "P2")

    def test_high_and_internet_facing_is_p2(self):
        self.assertEqual(prioritize(self.base(cvss=7.5, internet_facing=True)).priority, "P2")

    def test_p3_and_p4(self):
        self.assertEqual(prioritize(self.base(cvss=7.5)).priority, "P3")
        self.assertEqual(prioritize(self.base(cvss=5.0, epss=0.2)).priority, "P3")
        self.assertEqual(prioritize(self.base(cvss=3.0, epss=0.01)).priority, "P4")
        self.assertEqual(prioritize(self.base(cvss=3.0)).due_days, SLA_DAYS["P4"])

    def test_critical_asset_escalation(self):
        # 重要資産（5）は 1 段階引き上げる
        self.assertEqual(prioritize(self.base(cvss=3.0, asset_criticality=5)).priority, "P3")
        self.assertEqual(prioritize(self.base(cvss=7.5, asset_criticality=5)).priority, "P2")
        # P1・P2 はそれ以上上げない
        self.assertEqual(prioritize(self.base(cvss=5.0, epss=0.6, asset_criticality=5)).priority, "P2")
        self.assertEqual(prioritize(self.base(kev=True, asset_criticality=5)).priority, "P1")

    def test_severity_recorded(self):
        t = prioritize(self.base(cvss=9.1, internet_facing=True))
        self.assertEqual(t.severity, "critical")
        self.assertIsInstance(t, Triage)

    def test_validation(self):
        for bad in [dict(cvss=11.0), dict(epss=1.5), dict(epss=-0.1), dict(asset_criticality=0),
                    dict(asset_criticality=6), dict(asset_criticality=True)]:
            with self.assertRaises(ValueError, msg=str(bad)):
                prioritize(self.base(**bad))


class TestExercise3Reports(unittest.TestCase):
    def findings(self):
        return [
            Finding("CVE-A", 9.8, 0.90, True, True, 5),   # P1
            Finding("CVE-B", 5.0, 0.10, True, False, 2),  # P1（KEV）
            Finding("CVE-C", 7.5, 0.30, False, True, 3),  # P2
            Finding("CVE-D", 8.1, 0.05, False, False, 1), # P3
            Finding("CVE-E", 2.0, 0.01, False, False, 1), # P4
        ]

    def test_triage_all_order(self):
        order = [t.id for t in triage_all(self.findings())]
        # P1 が先。P1 内はスコア降順（CVE-A の方が高い）
        self.assertEqual(order[:2], ["CVE-A", "CVE-B"])
        self.assertEqual(order, ["CVE-A", "CVE-B", "CVE-C", "CVE-D", "CVE-E"])
        priorities = [t.priority for t in triage_all(self.findings())]
        self.assertEqual(priorities, ["P1", "P1", "P2", "P3", "P4"])

    def test_tie_break_by_id(self):
        f = [
            Finding("CVE-002", 5.0, 0.01, False, False, 1),
            Finding("CVE-001", 5.0, 0.01, False, False, 1),
        ]
        self.assertEqual([t.id for t in triage_all(f)], ["CVE-001", "CVE-002"], "同スコアは ID 昇順")

    def test_summarize(self):
        self.assertEqual(summarize(self.findings()), {"P1": 2, "P2": 1, "P3": 1, "P4": 1})
        self.assertEqual(summarize([]), {"P1": 0, "P2": 0, "P3": 0, "P4": 0})


if __name__ == "__main__":
    unittest.main()
