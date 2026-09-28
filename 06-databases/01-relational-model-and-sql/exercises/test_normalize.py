"""6.1 演習3（関数従属性と正規化）のテスト

実行: python3 tools/check.py 6.1   （またはこのディレクトリで python3 -m unittest -v test_normalize）
"""
import random
import unittest
from itertools import combinations

from normalize import (
    bcnf_decompose,
    bcnf_violations,
    candidate_keys,
    closure,
    format_fd,
    is_superkey,
    parse_fds,
    third_nf_violations,
)

ORDER_LINES = ["注文ID", "注文日時", "顧客ID", "顧客名", "商品ID", "商品名", "定価", "数量", "購入単価"]
ORDER_LINES_FDS = parse_fds(
    "注文ID -> 注文日時, 顧客ID; 顧客ID -> 顧客名; 商品ID -> 商品名, 定価; 注文ID 商品ID -> 数量, 購入単価"
)
CLASS = ["学生", "科目", "教員"]
CLASS_FDS = parse_fds("学生 科目 -> 教員; 教員 -> 科目")


def fs(*names):
    return frozenset(names)


# ---------------------------------------------------------------------------
# テスト用の参照実装（学習者のコードとは独立に計算する）
# ---------------------------------------------------------------------------

def ref_closure(x, fds):
    result = set(x)
    while True:
        added = {a for lhs, rhs in fds if lhs <= result for a in rhs} - result
        if not added:
            return frozenset(result)
        result |= added


def brute_force_keys(schema, fds):
    attrs = sorted(set(schema))
    supers = [
        frozenset(c)
        for n in range(1, len(attrs) + 1)
        for c in combinations(attrs, n)
        if ref_closure(c, fds) >= set(attrs)
    ]
    keys = [k for k in supers if not any(o < k for o in supers)]
    return sorted(keys, key=lambda k: (len(k), sorted(k)))


def is_bcnf_fragment(fragment, fds):
    """F⁺ を fragment に射影した従属性で、BCNF 違反がないか。"""
    items = sorted(fragment)
    for n in range(1, len(items)):
        for c in combinations(items, n):
            implied = ref_closure(c, fds) & fragment
            if implied != frozenset(c) and implied != fragment:
                return False
    return True


def is_lossless(schema, fragments, fds):
    """チェイス（chase）で、分解が無損失かどうかを判定する。"""
    attrs = sorted(set(schema))
    # 表（tableau）: 行 = 断片、列 = 属性。断片に含まれる属性は区別された記号 "a"
    table = [{a: ("a" if a in frag else ("b", i)) for a in attrs} for i, frag in enumerate(fragments)]
    changed = True
    while changed:
        changed = False
        for lhs, rhs in fds:
            for r1 in table:
                for r2 in table:
                    if r1 is r2 or any(r1[a] != r2[a] for a in lhs):
                        continue
                    for a in rhs:
                        if r1[a] != r2[a]:
                            # 同じ値にそろえる（"a" があれば "a" を優先）
                            new = "a" if "a" in (r1[a], r2[a]) else min(r1[a], r2[a])
                            old = {r1[a], r2[a]}
                            for row in table:
                                if row[a] in old:
                                    row[a] = new
                            changed = True
    return any(all(v == "a" for v in row.values()) for row in table)


def random_fds(rng, attrs):
    fds = []
    for _ in range(rng.randrange(1, 6)):
        lhs = frozenset(rng.sample(attrs, rng.choice([1, 1, 2])))
        rhs = frozenset(rng.sample(attrs, 1))
        fds.append((lhs, rhs))
    return fds


# ---------------------------------------------------------------------------
# テスト
# ---------------------------------------------------------------------------

class TestProvidedParser(unittest.TestCase):
    def test_parse_fds(self):
        self.assertEqual(parse_fds("A, B -> C\nC -> D E"), [(fs("A", "B"), fs("C")), (fs("C"), fs("D", "E"))])
        for bad in ("A B C", "A -> B -> C", "-> A", "A ->"):
            with self.assertRaises(ValueError, msg=bad):
                parse_fds(bad)


class TestClosure(unittest.TestCase):
    FDS = parse_fds("A -> B; B -> C; C D -> E")

    def test_examples(self):
        self.assertEqual(closure({"A"}, self.FDS), fs("A", "B", "C"))
        self.assertEqual(closure({"A", "D"}, self.FDS), fs("A", "B", "C", "D", "E"))
        self.assertEqual(closure({"D"}, self.FDS), fs("D"))
        self.assertEqual(closure(set(), self.FDS), frozenset())

    def test_needs_repeated_passes(self):
        # 後ろの FD が先に使えるようになるので、1 回走査するだけでは足りない
        fds = parse_fds("C -> D; B -> C; A -> B")
        self.assertEqual(closure({"A"}, fds), fs("A", "B", "C", "D"))

    def test_japanese_attribute_names(self):
        self.assertEqual(
            closure({"注文ID"}, ORDER_LINES_FDS), fs("注文ID", "注文日時", "顧客ID", "顧客名")
        )

    def test_random_against_reference(self):
        rng = random.Random(613)
        attrs = list("ABCDEF")
        for _ in range(200):
            fds = random_fds(rng, attrs)
            x = set(rng.sample(attrs, rng.randrange(0, 4)))
            self.assertEqual(closure(x, fds), ref_closure(x, fds), f"X={sorted(x)} F={[format_fd(f) for f in fds]}")

    def test_is_superkey(self):
        self.assertTrue(is_superkey({"A", "D"}, "ABCDE", self.FDS))
        self.assertTrue(is_superkey({"A", "C", "D"}, "ABCDE", self.FDS))
        self.assertFalse(is_superkey({"A"}, "ABCDE", self.FDS))
        with self.assertRaises(ValueError):
            is_superkey({"Z"}, "ABCDE", self.FDS)
        with self.assertRaises(ValueError):
            is_superkey({"A"}, "ABC", self.FDS)  # FD にスキーマ外の属性（D, E）


class TestCandidateKeys(unittest.TestCase):
    def test_single_key(self):
        self.assertEqual(candidate_keys("ABCDE", parse_fds("A -> B; B -> C; C D -> E")), [fs("A", "D")])

    def test_cycle_gives_multiple_keys(self):
        self.assertEqual(
            candidate_keys("ABCD", parse_fds("A -> B; B -> C; C -> A")),
            [fs("A", "D"), fs("B", "D"), fs("C", "D")],
        )

    def test_order_lines(self):
        self.assertEqual(candidate_keys(ORDER_LINES, ORDER_LINES_FDS), [fs("注文ID", "商品ID")])

    def test_overlapping_keys(self):
        self.assertEqual(candidate_keys(CLASS, CLASS_FDS), sorted([fs("学生", "科目"), fs("学生", "教員")], key=sorted))

    def test_no_fds(self):
        self.assertEqual(candidate_keys("ABC", []), [fs("A", "B", "C")])

    def test_random_against_brute_force(self):
        rng = random.Random(614)
        attrs = list("ABCDEF")
        for _ in range(150):
            fds = random_fds(rng, attrs)
            self.assertEqual(candidate_keys(attrs, fds), brute_force_keys(attrs, fds), [format_fd(f) for f in fds])

    def test_errors(self):
        with self.assertRaises(ValueError):
            candidate_keys("", [])
        with self.assertRaises(ValueError):
            candidate_keys("AB", parse_fds("A -> C"))


class TestNormalFormViolations(unittest.TestCase):
    def test_bcnf_violations_order_lines(self):
        got = [format_fd(v) for v in bcnf_violations(ORDER_LINES, ORDER_LINES_FDS)]
        self.assertEqual(got, ["注文ID -> 注文日時 顧客ID", "顧客ID -> 顧客名", "商品ID -> 商品名 定価"])

    def test_bcnf_ok(self):
        self.assertEqual(bcnf_violations("ABC", parse_fds("A -> B C")), [])
        self.assertEqual(bcnf_violations("AB", []), [])

    def test_trivial_part_is_removed(self):
        self.assertEqual(bcnf_violations("ABCD", parse_fds("A B -> A C; D -> A")), [
            (fs("A", "B"), fs("C")), (fs("D"), fs("A"))
        ])

    def test_trivial_fd_is_not_a_violation(self):
        self.assertEqual(bcnf_violations("ABC", parse_fds("A B -> A")), [])

    def test_3nf_but_not_bcnf(self):
        self.assertEqual([format_fd(v) for v in bcnf_violations(CLASS, CLASS_FDS)], ["教員 -> 科目"])
        self.assertEqual(third_nf_violations(CLASS, CLASS_FDS), [], "科目はキー属性なので 3NF は満たす")

    def test_3nf_violations_partial_and_transitive(self):
        # 部分従属（注文ID → 注文日時 など）も推移従属（顧客ID → 顧客名）も 3NF 違反
        got = [format_fd(v) for v in third_nf_violations(ORDER_LINES, ORDER_LINES_FDS)]
        self.assertEqual(got, ["注文ID -> 注文日時 顧客ID", "顧客ID -> 顧客名", "商品ID -> 商品名 定価"])

    def test_3nf_excludes_prime_attributes_from_rhs(self):
        # 候補キーは {A, B} と {C, B}。C -> A の A はキー属性なので 3NF 違反ではないが、C -> D は違反
        fds = parse_fds("A B -> C D; C -> A D")
        self.assertEqual(third_nf_violations("ABCD", fds), [(fs("C"), fs("D"))])
        self.assertEqual(bcnf_violations("ABCD", fds), [(fs("C"), fs("A", "D"))])


class TestBCNFDecomposition(unittest.TestCase):
    def check_properties(self, schema, fds, fragments):
        attrs = frozenset(schema)
        self.assertTrue(fragments, "結果が空です")
        self.assertEqual(frozenset().union(*fragments), attrs, "すべての属性がどこかの断片に含まれること")
        for f in fragments:
            self.assertTrue(is_bcnf_fragment(f, fds), f"断片 {sorted(f)} が BCNF ではありません")
            self.assertFalse(any(f < g for g in fragments), f"断片 {sorted(f)} は他の断片に含まれています")
        self.assertTrue(is_lossless(schema, fragments, fds), "無損失分解になっていません")
        self.assertEqual(fragments, sorted(fragments, key=sorted), "sorted(断片) の辞書順に並べること")

    def test_order_lines(self):
        got = bcnf_decompose(ORDER_LINES, ORDER_LINES_FDS)
        self.assertEqual(
            set(got),
            {
                fs("注文ID", "注文日時", "顧客ID"),
                fs("顧客ID", "顧客名"),
                fs("商品ID", "商品名", "定価"),
                fs("注文ID", "商品ID", "数量", "購入単価"),
            },
        )
        self.check_properties(ORDER_LINES, ORDER_LINES_FDS, got)

    def test_dependency_is_lost(self):
        got = bcnf_decompose(CLASS, CLASS_FDS)
        self.assertEqual(got, [fs("学生", "教員"), fs("教員", "科目")])
        # 学生 科目 -> 教員 は、どちらの断片の中でも確かめられない（従属性が保存されない）
        self.assertFalse(any(fs("学生", "科目", "教員") <= f for f in got))

    def test_already_bcnf(self):
        self.assertEqual(bcnf_decompose("ABC", parse_fds("A -> B C")), [fs("A", "B", "C")])

    def test_random_properties(self):
        rng = random.Random(615)
        attrs = list("ABCDEF")
        for _ in range(60):
            fds = random_fds(rng, attrs)
            self.check_properties(attrs, fds, bcnf_decompose(attrs, fds))


if __name__ == "__main__":
    unittest.main()
