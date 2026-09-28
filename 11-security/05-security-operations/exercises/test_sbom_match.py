"""11.5 SBOM と脆弱性の突き合わせ（sbom_match）— テスト

実行: python3 tools/check.py 11.5   （またはこのディレクトリで python3 -m unittest -v）

脆弱性の情報はテスト用に単純化した例です（実際の CVE の影響範囲とは異なります）。
"""
import unittest
from pathlib import Path

from sbom_match import (
    Advisory,
    Component,
    Finding,
    compare_versions,
    load_advisories,
    match,
    parse_cyclonedx,
    parse_version,
    satisfies,
    scan_sbom_file,
)

DATA = Path(__file__).parent / "data"

# 簡略化した脆弱性フィード。log4shell（CVE-2021-44228）は log4j-core 2.15.0 未満が対象、など
ADVISORY_ROWS = [
    {"id": "CVE-2021-44228", "package": "log4j-core", "affected": "<2.15.0", "fixed": "2.15.0", "severity": "critical"},
    {"id": "CVE-2021-45046", "package": "log4j-core", "affected": ">=2.0.0,<2.16.0", "fixed": "2.16.0", "severity": "critical"},
    {"id": "CVE-2099-0001", "package": "openssl", "affected": ">=3.0.0,<3.0.7", "fixed": "3.0.7", "severity": "high"},
    {"id": "CVE-2099-9999", "package": "not-installed", "affected": "<9.9.9", "fixed": "9.9.9", "severity": "low"},
]


class TestExercise1Versions(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("1.2.3")[:3], (1, 2, 3))
        self.assertEqual(parse_version("v2")[:3], (2, 0, 0))
        self.assertEqual(parse_version("1.2")[:3], (1, 2, 0))
        with self.assertRaises(ValueError):
            parse_version("not-a-version")

    def test_compare(self):
        self.assertEqual(compare_versions("1.0.0", "1.0.1"), -1)
        self.assertEqual(compare_versions("2.0.0", "1.9.9"), 1)
        self.assertEqual(compare_versions("1.2", "1.2.0"), 0)
        self.assertEqual(compare_versions("1.10.0", "1.9.0"), 1, "数値として比較（文字列順ではない）")
        self.assertEqual(compare_versions("v1.2.3", "1.2.3"), 0)

    def test_prereleases(self):
        self.assertEqual(compare_versions("1.0.0-rc1", "1.0.0"), -1, "rc は正式版より前")
        self.assertEqual(compare_versions("1.0.0-alpha", "1.0.0-beta"), -1)
        self.assertEqual(compare_versions("1.0.0-rc.1", "1.0.0-rc.2"), -1)

    def test_satisfies(self):
        self.assertTrue(satisfies("2.14.1", "<2.15.0"))
        self.assertFalse(satisfies("2.17.1", "<2.15.0"))
        self.assertTrue(satisfies("2.14.1", ">=2.0.0,<2.16.0"))
        self.assertFalse(satisfies("2.16.0", ">=2.0.0,<2.16.0"), "上限は含まない")
        self.assertTrue(satisfies("3.0.6", ">=3.0.0,<3.0.7"))
        self.assertTrue(satisfies("1.2.3", ""), "空の制約はすべてに一致")
        self.assertTrue(satisfies("2.0.0", "==2.0.0"))
        self.assertTrue(satisfies("2.0.1", "!=2.0.0"))
        with self.assertRaises(ValueError):
            satisfies("1.0.0", "~>1.0")


class TestExercise2Sbom(unittest.TestCase):
    def test_parse_cyclonedx(self):
        comps = parse_cyclonedx((DATA / "sbom.cdx.json").read_text(encoding="utf-8"))
        self.assertEqual(len(comps), 6)
        self.assertIn(Component("requests", "2.31.0", "pkg:pypi/requests@2.31.0"), comps)
        self.assertTrue(all(isinstance(c, Component) for c in comps))

    def test_parse_rejects_non_cyclonedx(self):
        with self.assertRaises(ValueError):
            parse_cyclonedx('{"bomFormat": "SPDX", "components": []}')
        with self.assertRaises(ValueError):
            parse_cyclonedx('{"bomFormat": "CycloneDX", "components": [{"name": "x"}]}')

    def test_match_finds_vulnerable_versions(self):
        advisories = load_advisories(ADVISORY_ROWS)
        comps = parse_cyclonedx((DATA / "sbom.cdx.json").read_text(encoding="utf-8"))
        findings = match(comps, advisories)
        # log4j 2.14.1 は両方の CVE に該当、2.17.1 はどちらにも該当しない。openssl 3.0.6 は該当
        self.assertEqual(
            findings,
            [
                Finding("log4j-core", "2.14.1", "CVE-2021-44228", "critical", "2.15.0"),
                Finding("log4j-core", "2.14.1", "CVE-2021-45046", "critical", "2.16.0"),
                Finding("openssl", "3.0.6", "CVE-2099-0001", "high", "3.0.7"),
            ],
        )

    def test_patched_versions_are_not_flagged(self):
        advisories = load_advisories(ADVISORY_ROWS)
        findings = match([Component("log4j-core", "2.17.1")], advisories)
        self.assertEqual(findings, [], "修正版にアップグレード済みなら検出されない")

    def test_uninstalled_package_not_reported(self):
        advisories = load_advisories(ADVISORY_ROWS)
        findings = match([Component("requests", "2.31.0")], advisories)
        self.assertEqual(findings, [], "SBOM に無いパッケージの脆弱性は報告しない")

    def test_scan_sbom_file(self):
        findings = scan_sbom_file(DATA / "sbom.cdx.json", load_advisories(ADVISORY_ROWS))
        self.assertEqual({f.advisory_id for f in findings}, {"CVE-2021-44228", "CVE-2021-45046", "CVE-2099-0001"})


if __name__ == "__main__":
    unittest.main()
