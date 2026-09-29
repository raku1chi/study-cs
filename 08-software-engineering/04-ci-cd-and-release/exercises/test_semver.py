"""8.4 演習4 — セマンティックバージョニング（SemVer 2.0.0）のテスト

実行: python3 tools/check.py 8.4   （またはこのディレクトリで python3 -m unittest -v test_semver）

範囲指定の判定の期待値は、この演習で扱う部分集合について npm の node-semver の振る舞いに合わせています
（node-semver が受け付ける "1.x"・"^1.2"・"v1.2.3"・"~>1.2.3" などの形は、この演習では ValueError にします）。
"""
import functools
import random
import unittest

from semver import Version, compare, max_satisfying, parse, satisfies


class TestParse(unittest.TestCase):
    def test_valid_versions(self):
        self.assertEqual(parse("1.2.3"), Version(1, 2, 3))
        self.assertEqual(parse("0.0.0"), Version(0, 0, 0))
        self.assertEqual(parse("1.2.3-beta.11+build.5"), Version(1, 2, 3, ("beta", 11), ("build", "5")))
        self.assertEqual(parse("1.0.0-x-y-z.--").prerelease, ("x-y-z", "--"))
        self.assertEqual(parse("1.0.0-alpha.0valid").prerelease, ("alpha", "0valid"), "英字を含むなら先頭の 0 は可")
        self.assertEqual(parse("1.0.0+0.build.1-rc.10000aaa-kk-0.1").build, ("0", "build", "1-rc", "10000aaa-kk-0", "1"))
        self.assertEqual(parse("1.2.3----RC-SNAPSHOT.12.9.1--.12+788").prerelease, ("---RC-SNAPSHOT", 12, 9, "1--", 12))
        big = parse("99999999999999999999999.999999999999999999.99999999999999999")
        self.assertEqual(big.major, 99999999999999999999999)

    def test_numeric_prerelease_identifiers_are_ints(self):
        v = parse("2.0.0-rc.1.alpha.0")
        self.assertEqual(v.prerelease, ("rc", 1, "alpha", 0))
        self.assertIsInstance(v.prerelease[1], int)

    def test_round_trip_to_string(self):
        for text in ["1.2.3", "1.2.3-alpha.1", "1.2.3+build.7", "10.20.30-rc.1+exp.sha.5114f85"]:
            self.assertEqual(str(parse(text)), text)

    def test_invalid_versions(self):
        invalid = [
            "", "1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "v1.2.3", "1.2.3-", "1.2.3+",
            "1.2.3-01", "1.2.3-alpha..1", "1.2.3-alpha_1", " 1.2.3", "1.2.3 ", "1.2.3\n", "-1.2.3",
            "1.2.3-+", "1.2.3+build..1", "１.2.3", "1.2.٣", "a.b.c", "1.2.3-alpha+beta+gamma",
        ]
        for text in invalid:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse(text)


SPEC_ORDER = [
    "1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta", "1.0.0-beta.2",
    "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0", "1.0.1", "1.1.0", "1.10.0", "2.0.0-0", "2.0.0",
]


class TestCompare(unittest.TestCase):
    def test_spec_example_order(self):
        for lower, higher in zip(SPEC_ORDER, SPEC_ORDER[1:]):
            self.assertEqual(compare(lower, higher), -1, (lower, higher))
            self.assertEqual(compare(higher, lower), 1, (higher, lower))

    def test_sorting_shuffled_versions(self):
        shuffled = SPEC_ORDER[:]
        random.Random(84).shuffle(shuffled)
        self.assertEqual(sorted(shuffled, key=functools.cmp_to_key(compare)), SPEC_ORDER)

    def test_numbers_compare_numerically(self):
        self.assertEqual(compare("1.10.0", "1.9.0"), 1, "文字列としてではなく数値として比べる")
        self.assertEqual(compare("1.0.0-beta.11", "1.0.0-beta.2"), 1)

    def test_build_metadata_is_ignored(self):
        self.assertEqual(compare("1.0.0+a", "1.0.0+b"), 0)
        self.assertEqual(compare("1.0.0-rc.1+x", "1.0.0-rc.1"), 0)

    def test_accepts_version_objects(self):
        self.assertEqual(compare(Version(1, 0, 0), "1.0.0-rc.1"), 1)


class TestSatisfies(unittest.TestCase):
    def check(self, cases):
        for version, range_expr, expected in cases:
            self.assertEqual(satisfies(version, range_expr), expected, f"satisfies({version!r}, {range_expr!r})")

    def test_exact_and_comparators(self):
        self.check([
            ("1.2.3", "1.2.3", True), ("1.2.3", "=1.2.3", True), ("1.2.4", "1.2.3", False),
            ("1.2.3+build.5", "1.2.3", True),
            ("1.3.5", ">=1.2.0 <1.4.0", True), ("1.4.0", ">=1.2.0 <1.4.0", False),
            ("1.2.0", ">1.2.0", False), ("1.2.1", ">1.2.0", True), ("1.2.0", "<=1.2.0", True),
        ])

    def test_caret(self):
        self.check([
            ("1.2.3", "^1.2.3", True), ("1.9.9", "^1.2.3", True), ("2.0.0", "^1.2.3", False),
            ("1.2.2", "^1.2.3", False),
            ("0.2.5", "^0.2.3", True), ("0.3.0", "^0.2.3", False), ("0.2.2", "^0.2.3", False),
            ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
        ])

    def test_tilde(self):
        self.check([("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.2.2", "~1.2.3", False)])

    def test_or_and_star(self):
        self.check([
            ("1.5.0", "^1.0.0 || ^2.0.0", True), ("2.1.0", "^1.0.0 || ^2.0.0", True),
            ("3.0.0", "^1.0.0 || ^2.0.0", False), ("0.9.0", "<1.0.0 || >=3.0.0", True),
            ("5.0.0", "*", True), ("0.0.0", "*", True),
        ])

    def test_prerelease_rules(self):
        self.check([
            ("1.3.0-beta.1", "^1.2.0", False),            # 安定版の範囲に、別の版のプレリリースは入らない
            ("2.0.0-rc.1", "^1.0.0", False),              # 上限の 2.0.0-0 がこれを除外する
            ("2.0.0-rc.1", "<2.0.0", False),              # 同じ 2.0.0 でも、比較子にプレリリースがなければ不可
            ("1.2.3-beta.2", ">=1.2.3-beta.1 <2.0.0", True),
            ("1.2.4-beta.1", ">=1.2.3-beta.1", False),    # MAJOR.MINOR.PATCH が違う
            ("1.2.3-rc.1", "^1.2.3-alpha", True),
            ("1.2.3-alpha", "^1.2.3-beta", False),        # 下限より前
            ("5.0.0-beta", "*", False),
            ("1.2.3", "^1.2.3-beta", True),               # 安定版は普通に比べる
        ])

    def test_invalid_ranges(self):
        for bad in ["", "   ", "^", ">=1.2", "1.2.3 ||", "|| 1.2.3", "~>1.2.3", ">>1.0.0", "^v1.2.3", "1.x", "=> 1.0.0"]:
            with self.assertRaises(ValueError, msg=repr(bad)):
                satisfies("1.2.3", bad)

    def test_invalid_version(self):
        with self.assertRaises(ValueError):
            satisfies("1.2", "^1.0.0")


class TestMaxSatisfying(unittest.TestCase):
    VERSIONS = ["1.2.0", "1.10.1", "1.9.3", "2.0.0-rc.1", "2.0.0", "2.1.0-beta.1", "1.11.0-beta.1", "0.9.9"]

    def test_picks_highest_by_precedence(self):
        self.assertEqual(max_satisfying(self.VERSIONS, "^1.2.0"), "1.10.1")
        self.assertEqual(max_satisfying(self.VERSIONS, "~1.9.0"), "1.9.3")
        self.assertEqual(max_satisfying(self.VERSIONS, ">=1.0.0"), "2.0.0")
        self.assertEqual(max_satisfying(self.VERSIONS, ">=2.1.0-beta.0"), "2.1.0-beta.1")

    def test_none_when_nothing_matches(self):
        self.assertIsNone(max_satisfying(self.VERSIONS, "^3.0.0"))
        self.assertIsNone(max_satisfying([], "*"))

    def test_returns_original_string(self):
        self.assertEqual(max_satisfying(["1.0.0+build.9", "0.1.0"], "^1.0.0"), "1.0.0+build.9")


if __name__ == "__main__":
    unittest.main()
