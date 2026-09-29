"""2.1 計算機科学のための離散数学 — テスト

実行: python3 tools/check.py 2.1   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import unittest
from itertools import product

from discrete import (
    RSAKey,
    are_equivalent,
    count_surjections,
    crt,
    extended_gcd,
    factorize,
    find_counterexample,
    gcd,
    is_prime,
    is_satisfiable,
    is_tautology,
    isqrt,
    isqrt_trace,
    min_code_length,
    min_items_for_collision,
    mod_inverse,
    mod_pow,
    n_choose_k,
    power_set,
    primes_up_to,
    rsa_decrypt,
    rsa_decrypt_crt,
    rsa_encrypt,
    rsa_generate,
    truth_table,
)


def implies(p, q):
    return (not p) or q


F, T = False, True


# ---------------------------------------------------------------------------
# 演習1
# ---------------------------------------------------------------------------

class TestExercise1Logic(unittest.TestCase):
    def test_truth_table_and(self):
        self.assertEqual(
            truth_table(lambda p, q: p and q, 2),
            [((F, F), F), ((F, T), F), ((T, F), F), ((T, T), T)],
        )

    def test_truth_table_order_and_size(self):
        table = truth_table(lambda a, b, c: a, 3)
        self.assertEqual(len(table), 8)
        self.assertEqual([row for row, _ in table], list(product((F, T), repeat=3)))
        self.assertEqual([out for _, out in table], [F, F, F, F, T, T, T, T])

    def test_truth_table_zero_variables(self):
        self.assertEqual(truth_table(lambda: True, 0), [((), True)])
        self.assertEqual(truth_table(lambda: 0, 0), [((), False)])

    def test_truth_table_normalizes_to_bool(self):
        table = truth_table(lambda p: 1 if p else 0, 1)
        self.assertEqual(table, [((F,), F), ((T,), T)])
        for _, out in table:
            self.assertIs(type(out), bool, "出力は bool() で変換して格納すること")

    def test_tautologies(self):
        self.assertTrue(is_tautology(lambda p: p or not p, 1), "排中律")
        self.assertTrue(is_tautology(lambda p, q: implies(implies(p, q) and p, q), 2), "モーダスポネンス")
        self.assertTrue(is_tautology(lambda p, q: implies(implies(implies(p, q), p), p), 2), "パースの法則")
        self.assertFalse(is_tautology(implies, 2))
        self.assertFalse(is_tautology(lambda p, q, r: p or q or r, 3))
        self.assertTrue(is_tautology(lambda: True, 0))

    def test_satisfiable(self):
        self.assertFalse(is_satisfiable(lambda p: p and not p, 1), "矛盾式は充足不能")
        self.assertTrue(is_satisfiable(lambda p, q, r: p and not q and r, 3))
        self.assertFalse(is_satisfiable(lambda: False, 0))
        # 「f が恒真」⇔「¬f が充足不能」
        f = lambda p, q: implies(p, q) or implies(q, p)  # noqa: E731
        self.assertEqual(is_tautology(f, 2), not is_satisfiable(lambda p, q: not f(p, q), 2))

    def test_equivalences(self):
        self.assertTrue(are_equivalent(lambda a, b: not (a and b), lambda a, b: (not a) or (not b), 2))
        self.assertTrue(are_equivalent(lambda a, b: not (a or b), lambda a, b: (not a) and (not b), 2))
        self.assertTrue(are_equivalent(lambda a, b, c: a and (b or c), lambda a, b, c: (a and b) or (a and c), 3))
        self.assertTrue(are_equivalent(implies, lambda p, q: implies(not q, not p), 2), "対偶は同値")
        self.assertFalse(are_equivalent(implies, lambda p, q: implies(q, p), 2), "逆は同値ではない")
        self.assertFalse(
            are_equivalent(lambda a, b: not (a and b), lambda a, b: (not a) and (not b), 2),
            "よくある書き換えミス: not (a and b) を not a and not b にしてはいけない",
        )

    def test_counterexample(self):
        self.assertEqual(find_counterexample(implies, lambda p, q: implies(q, p), 2), (F, T))
        self.assertIsNone(find_counterexample(implies, lambda p, q: (not p) or q, 2))
        self.assertEqual(find_counterexample(lambda a, b, c: a, lambda a, b, c: a and c, 3), (T, F, F))
        # 1/0 を返す関数も真偽値として比較する
        self.assertIsNone(find_counterexample(lambda p: p, lambda p: 1 if p else 0, 1))

    def test_negative_n(self):
        for func in (truth_table, is_tautology, is_satisfiable):
            with self.assertRaises(ValueError, msg=func.__name__):
                func(lambda: True, -1)
        with self.assertRaises(ValueError):
            are_equivalent(lambda: True, lambda: True, -1)


# ---------------------------------------------------------------------------
# 演習2
# ---------------------------------------------------------------------------

class TestExercise2Primes(unittest.TestCase):
    def test_small(self):
        self.assertEqual(primes_up_to(30), [2, 3, 5, 7, 11, 13, 17, 19, 23, 29])
        self.assertEqual(primes_up_to(2), [2])
        self.assertEqual(primes_up_to(13), [2, 3, 5, 7, 11, 13], "n 自身が素数なら含める")
        for n in (1, 0, -10):
            self.assertEqual(primes_up_to(n), [], n)

    def test_prime_counting_function(self):
        # π(10^5) = 9592, π(10^6) = 78498
        self.assertEqual(len(primes_up_to(10**5)), 9592)
        primes = primes_up_to(10**6)
        self.assertEqual(len(primes), 78498)
        self.assertEqual(primes[-1], 999983)

    def test_sieve_agrees_with_is_prime(self):
        primes = set(primes_up_to(2000))
        for n in range(-5, 2001):
            self.assertEqual(is_prime(n), n in primes, n)

    def test_is_prime_known_values(self):
        for p in (2, 3, 97, 7919, 2_147_483_647, 1_000_000_007):
            self.assertTrue(is_prime(p), p)
        for c in (0, 1, 4, 561, 1105, 7917, 2_147_483_649, 1_000_000_007 * 3):
            self.assertFalse(is_prime(c), f"{c} は素数ではない（561 と 1105 はカーマイケル数）")

    def test_factorize_examples(self):
        self.assertEqual(factorize(360), [(2, 3), (3, 2), (5, 1)])
        self.assertEqual(factorize(1), [])
        self.assertEqual(factorize(97), [(97, 1)])
        self.assertEqual(factorize(2**20), [(2, 20)])
        self.assertEqual(factorize(2_147_483_647), [(2_147_483_647, 1)])
        self.assertEqual(factorize(600851475143), [(71, 1), (839, 1), (1471, 1), (6857, 1)])

    def test_factorize_reconstructs(self):
        rng = random.Random(21)
        for _ in range(300):
            n = rng.randrange(1, 10**7)
            factors = factorize(n)
            product_ = 1
            for p, k in factors:
                self.assertTrue(is_prime(p), (n, p))
                self.assertGreaterEqual(k, 1)
                product_ *= p**k
            self.assertEqual(product_, n, n)
            ps = [p for p, _ in factors]
            self.assertEqual(ps, sorted(set(ps)), "素数は小さい順に、重複なく並べる")

    def test_factorize_invalid(self):
        for n in (0, -1, -360):
            with self.assertRaises(ValueError, msg=n):
                factorize(n)


# ---------------------------------------------------------------------------
# 演習3
# ---------------------------------------------------------------------------

class CountingModulus(int):
    """`x % m` が何回計算されたかを数える int。

    x が int で m がこのクラスのとき、Python は m.__rmod__(x) を先に呼ぶ
    （右オペランドが左オペランドの型のサブクラスで、反射メソッドを上書きしているため）。
    """

    def __new__(cls, value):
        obj = super().__new__(cls, value)
        obj.count = 0
        return obj

    def __rmod__(self, other):
        self.count += 1
        return int.__rmod__(self, other)

    def __rdivmod__(self, other):
        self.count += 1
        return int.__rdivmod__(self, other)


def require_fast_mod_pow(testcase: unittest.TestCase) -> None:
    """大きな指数を使うテストの前に、mod_pow が繰り返し二乗法になっているかを素早く確かめる。

    指数に比例する回数の乗算をする実装だと、指数が 10^9 を超えるテストが終わらなくなるため、
    ここで即座に失敗させる（NotImplementedError はそのまま伝わる）。
    """
    mod = CountingModulus(1_000_003)
    mod_pow(3, 5000, mod)
    if mod.count > 3 * (5000).bit_length() + 5:
        testcase.fail(
            "mod_pow が指数に比例する回数の剰余演算をしています。このテストは巨大な指数を使うので、"
            "先に演習3の mod_pow を繰り返し二乗法（O(log exp)）で完成させてください"
        )


class TestExercise3NumberTheory(unittest.TestCase):
    def test_gcd_examples(self):
        self.assertEqual(gcd(1071, 462), 21)
        self.assertEqual(gcd(462, 1071), 21)
        self.assertEqual(gcd(0, 0), 0)
        self.assertEqual(gcd(0, 5), 5)
        self.assertEqual(gcd(-12, 18), 6)
        self.assertEqual(gcd(-12, -18), 6)
        self.assertEqual(gcd(17, 3120), 1)

    def test_gcd_random(self):
        rng = random.Random(31)
        for _ in range(500):
            a, b = rng.randrange(-10**12, 10**12), rng.randrange(-10**12, 10**12)
            self.assertEqual(gcd(a, b), math.gcd(a, b), (a, b))

    def test_extended_gcd(self):
        g, x, y = extended_gcd(240, 46)
        self.assertEqual((g, 240 * x + 46 * y), (2, 2))
        rng = random.Random(32)
        cases = [(0, 0), (0, 7), (7, 0), (-7, 0), (1, 1), (-240, 46), (240, -46)]
        cases += [(rng.randrange(-10**9, 10**9), rng.randrange(-10**9, 10**9)) for _ in range(500)]
        for a, b in cases:
            g, x, y = extended_gcd(a, b)
            self.assertEqual(g, math.gcd(a, b), (a, b))
            self.assertEqual(a * x + b * y, g, (a, b, x, y))

    def test_mod_inverse_examples(self):
        self.assertEqual(mod_inverse(3, 11), 4)
        self.assertEqual(mod_inverse(17, 3120), 2753)
        self.assertEqual(mod_inverse(-3, 11), 7, "負の a は法で割った余りとして扱う")
        self.assertEqual(mod_inverse(14, 11), 4, "a >= m でもよい")

    def test_mod_inverse_random(self):
        rng = random.Random(33)
        for _ in range(500):
            m = rng.randrange(2, 10**9)
            a = rng.randrange(-10**9, 10**9)
            if math.gcd(a, m) != 1:
                with self.assertRaises(ValueError, msg=(a, m)):
                    mod_inverse(a, m)
                continue
            inv = mod_inverse(a, m)
            self.assertTrue(0 <= inv < m, (a, m, inv))
            self.assertEqual(a * inv % m, 1, (a, m, inv))

    def test_mod_inverse_invalid(self):
        with self.assertRaises(ValueError):
            mod_inverse(6, 9)  # gcd = 3
        with self.assertRaises(ValueError):
            mod_inverse(0, 7)
        for m in (1, 0, -5):
            with self.assertRaises(ValueError, msg=m):
                mod_inverse(3, m)

    def test_mod_pow_examples(self):
        self.assertEqual(mod_pow(3, 13, 1000), 323)
        self.assertEqual(mod_pow(2, 10, 1000), 24)
        self.assertEqual(mod_pow(5, 0, 7), 1)
        self.assertEqual(mod_pow(5, 0, 1), 0, "mod == 1 なら常に 0")
        self.assertEqual(mod_pow(123, 456, 1), 0)
        self.assertEqual(mod_pow(-2, 3, 5), (-8) % 5, "負の base")
        self.assertEqual(mod_pow(0, 0, 5), 1)

    def test_mod_pow_random(self):
        rng = random.Random(34)
        for _ in range(500):
            b = rng.randrange(-10**6, 10**6)
            e = rng.randrange(0, 10**4)
            m = rng.randrange(1, 10**9)
            self.assertEqual(mod_pow(b, e, m), pow(b, e, m), (b, e, m))

    def test_mod_pow_fermat(self):
        require_fast_mod_pow(self)
        # フェルマーの小定理: p が素数で a が p の倍数でなければ a^(p-1) ≡ 1 (mod p)
        p = 1_000_000_007
        for a in (2, 3, 10, 123456789):
            self.assertEqual(mod_pow(a, p - 1, p), 1, a)

    def test_mod_pow_uses_logarithmic_number_of_reductions(self):
        exp = 10**6 + 1
        mod = CountingModulus(1_000_000_007)
        result = mod_pow(7, exp, mod)
        self.assertEqual(result, pow(7, exp, 1_000_000_007))
        limit = 3 * exp.bit_length() + 5
        self.assertLessEqual(
            mod.count, limit,
            f"剰余演算が {mod.count} 回行われました（上限 {limit} 回）。"
            "指数を 1 ずつ減らすのではなく、指数を半分にする繰り返し二乗法で実装してください",
        )
        self.assertGreater(mod.count, 0, "掛けるたびに mod で割った余りをとってください")

    def test_mod_pow_invalid(self):
        with self.assertRaises(ValueError):
            mod_pow(2, -1, 7)
        for m in (0, -7):
            with self.assertRaises(ValueError, msg=m):
                mod_pow(2, 3, m)


# ---------------------------------------------------------------------------
# 演習4
# ---------------------------------------------------------------------------

class TestExercise4Counting(unittest.TestCase):
    def test_n_choose_k_small(self):
        self.assertEqual(n_choose_k(5, 2), 10)
        self.assertEqual(n_choose_k(50, 2), 1225)
        self.assertEqual(n_choose_k(0, 0), 1)
        self.assertEqual(n_choose_k(7, 0), 1)
        self.assertEqual(n_choose_k(7, 7), 1)
        self.assertEqual(n_choose_k(3, 5), 0, "k > n なら 0")

    def test_n_choose_k_pascal(self):
        for n in range(1, 40):
            for k in range(1, n):
                self.assertEqual(n_choose_k(n, k), n_choose_k(n - 1, k - 1) + n_choose_k(n - 1, k), (n, k))

    def test_n_choose_k_big_exact(self):
        for n, k in [(100, 50), (1000, 500), (1000, 3), (2000, 1000)]:
            value = n_choose_k(n, k)
            self.assertIs(type(value), int, "float ではなく int を返すこと")
            self.assertEqual(value, math.comb(n, k), (n, k))

    def test_n_choose_k_invalid(self):
        for n, k in [(-1, 0), (5, -1), (-3, -3)]:
            with self.assertRaises(ValueError, msg=(n, k)):
                n_choose_k(n, k)

    def test_power_set(self):
        self.assertEqual(power_set([]), [[]])
        self.assertEqual(power_set(["x"]), [[], ["x"]])
        self.assertEqual(
            power_set(["a", "b", "c"]),
            [[], ["a"], ["b"], ["a", "b"], ["c"], ["a", "c"], ["b", "c"], ["a", "b", "c"]],
        )
        self.assertEqual(power_set("ab"), [[], ["a"], ["b"], ["a", "b"]], "文字列も Sequence として扱える")

    def test_power_set_size_and_positional_elements(self):
        items = list(range(10))
        subsets = power_set(items)
        self.assertEqual(len(subsets), 2**10)
        self.assertEqual(len({tuple(s) for s in subsets}), 2**10)
        self.assertEqual(sum(len(s) for s in subsets), 10 * 2**9, "各要素はちょうど半分の部分集合に含まれる")
        self.assertEqual(power_set([1, 1]), [[], [1], [1], [1, 1]], "要素は位置で区別する")

    def test_count_surjections_brute_force(self):
        for n in range(0, 7):
            for k in range(0, 6):
                expected = sum(1 for f in product(range(k), repeat=n) if len(set(f)) == k)
                self.assertEqual(count_surjections(n, k), expected, (n, k))

    def test_count_surjections_identity(self):
        # すべての写像 k^n 個を「像がちょうど j 個の値からなるもの」に分類すると
        # Σ_j C(k, j) × (j 個の値への全射の数) = k^n
        n, k = 12, 7
        total = sum(math.comb(k, j) * count_surjections(n, j) for j in range(k + 1))
        self.assertEqual(total, k**n)
        self.assertEqual(count_surjections(5, 3), 150)
        self.assertEqual(count_surjections(20, 20), math.factorial(20), "n == k なら全単射の数 n!")

    def test_count_surjections_invalid(self):
        with self.assertRaises(ValueError):
            count_surjections(-1, 2)
        with self.assertRaises(ValueError):
            count_surjections(2, -1)

    def test_pigeonhole(self):
        self.assertEqual(min_items_for_collision(365), 366)
        self.assertEqual(min_items_for_collision(10**4), 10001)
        self.assertEqual(min_items_for_collision(10, k=3), 21)
        self.assertEqual(min_items_for_collision(1), 2)
        self.assertEqual(min_items_for_collision(7, k=1), 1)
        self.assertEqual(min_items_for_collision(2**32), 2**32 + 1)
        for args in [(0,), (-1,), (10, 0)]:
            with self.assertRaises(ValueError, msg=args):
                min_items_for_collision(*args)

    def test_pigeonhole_is_tight(self):
        # 箱 m 個に (k-1)*m 個までなら「どの箱も k 個未満」の入れ方が存在する（=上限はこれ以上下げられない）
        for m in range(1, 6):
            for k in range(1, 5):
                n = min_items_for_collision(m, k)
                counts = [0] * m
                for i in range(n - 1):
                    counts[i % m] += 1  # できるだけ均等に入れる
                self.assertLess(max(counts, default=0), k, (m, k))

    def test_min_code_length(self):
        self.assertEqual(min_code_length(62**6, 62), 6)
        self.assertEqual(min_code_length(62**6 + 1, 62), 7)
        self.assertEqual(min_code_length(1000, 10), 3)
        self.assertEqual(min_code_length(1001, 10), 4)
        self.assertEqual(min_code_length(1, 2), 0)
        self.assertEqual(min_code_length(2, 2), 1)
        self.assertEqual(min_code_length(3, 2), 2)
        for e in (15, 100, 308):
            self.assertEqual(min_code_length(10**e, 10), e, f"10^{e}: 浮動小数点の log では誤差が出やすい境界")
            self.assertEqual(min_code_length(10**e + 1, 10), e + 1)

    def test_min_code_length_invalid(self):
        for args in [(0, 10), (-5, 10), (10, 1), (10, 0)]:
            with self.assertRaises(ValueError, msg=args):
                min_code_length(*args)


# ---------------------------------------------------------------------------
# 演習5
# ---------------------------------------------------------------------------

class TestExercise5LoopInvariant(unittest.TestCase):
    def test_example_trace(self):
        self.assertEqual(isqrt_trace(10), (3, [(0, 11), (0, 5), (2, 5), (3, 5), (3, 4)]))
        self.assertEqual(isqrt_trace(0), (0, [(0, 1)]))

    def test_matches_math_isqrt(self):
        for n in range(0, 3000):
            self.assertEqual(isqrt(n), math.isqrt(n), n)
        rng = random.Random(51)
        for _ in range(200):
            n = rng.randrange(0, 10**rng.randrange(1, 120))
            self.assertEqual(isqrt(n), math.isqrt(n), n)
        self.assertEqual(isqrt(10**100), 10**50)
        self.assertEqual(isqrt(10**100 - 1), 10**50 - 1)

    def check_trace(self, n):
        result, states = isqrt_trace(n)
        self.assertEqual(states[0], (0, n + 1), "初期状態は (0, n+1)")
        for lo, hi in states:
            self.assertTrue(lo * lo <= n < hi * hi, f"不変条件 lo^2 <= n < hi^2 が破れている: n={n}, (lo, hi)={(lo, hi)}")
        for (lo1, hi1), (lo2, hi2) in zip(states, states[1:]):
            self.assertLess(hi2 - lo2, hi1 - lo1, f"変量 hi - lo が減少していない: n={n}")
            self.assertTrue(lo1 <= lo2 and hi2 <= hi1, f"区間が縮んでいない: n={n}")
        lo, hi = states[-1]
        self.assertEqual(hi - lo, 1, "終了時は hi == lo + 1")
        self.assertEqual(result, lo)
        self.assertLessEqual(len(states), n.bit_length() + 1, f"反復回数が O(log n) を超えている: n={n}")

    def test_invariant_variant_and_efficiency(self):
        for n in list(range(0, 600)) + [2**61 - 1, 2**64, 10**30 + 12345]:
            self.check_trace(n)

    def test_negative(self):
        with self.assertRaises(ValueError):
            isqrt(-1)
        with self.assertRaises(ValueError):
            isqrt_trace(-4)


# ---------------------------------------------------------------------------
# 演習6
# ---------------------------------------------------------------------------

class TestExercise6CrtAndRsa(unittest.TestCase):
    def test_crt_examples(self):
        self.assertEqual(crt([2, 3, 2], [3, 5, 7]), 23)
        self.assertEqual(crt([], []), 0)
        self.assertEqual(crt([5], [7]), 5)
        self.assertEqual(crt([12], [7]), 5, "法以上の余りは正規化する")
        self.assertEqual(crt([-1, -1], [4, 9]), 35, "負の余りは正規化する")
        self.assertEqual(crt([0, 3], [1, 5]), 3, "法 1 の条件は常に満たされる")

    def test_crt_random_against_brute_force(self):
        rng = random.Random(61)
        moduli_choices = [2, 3, 5, 7, 11, 13, 4, 9, 25, 49]
        for _ in range(300):
            moduli = []
            for m in rng.sample(moduli_choices, rng.randrange(1, 4)):
                if all(math.gcd(m, x) == 1 for x in moduli):
                    moduli.append(m)
            residues = [rng.randrange(-50, 50) for _ in moduli]
            big_m = math.prod(moduli)
            expected = next(x for x in range(big_m) if all((x - r) % m == 0 for r, m in zip(residues, moduli)))
            self.assertEqual(crt(residues, moduli), expected, (residues, moduli))

    def test_crt_invalid(self):
        with self.assertRaises(ValueError):
            crt([1, 2], [4, 6])  # gcd(4, 6) = 2
        with self.assertRaises(ValueError):
            crt([1, 2], [3])
        with self.assertRaises(ValueError):
            crt([1], [0])

    def test_generate_textbook_example(self):
        key = rsa_generate(61, 53, 17)
        self.assertEqual(key, RSAKey(n=3233, e=17, d=2753, p=61, q=53))
        self.assertEqual(rsa_encrypt(65, key), 2790)
        self.assertEqual(rsa_decrypt(2790, key), 65)

    def test_generate_default_exponent(self):
        key = rsa_generate(1_000_003, 999_983)
        self.assertEqual(key.e, 65537)
        self.assertEqual(key.n, 1_000_003 * 999_983)
        phi = (1_000_003 - 1) * (999_983 - 1)
        self.assertEqual(key.e * key.d % phi, 1)
        self.assertTrue(0 < key.d < phi)

    def test_generate_invalid(self):
        cases = {
            "p == q": (61, 61, 17),
            "p が素数でない": (60, 53, 17),
            "q が素数でない": (61, 51, 17),
            "p = 2（奇素数でない）": (2, 5, 3),
            "q = 2（奇素数でない）": (5, 2, 3),
            "gcd(e, φ) != 1（φ = 3120 は 3 の倍数）": (61, 53, 3),
            "e = 1": (61, 53, 1),
            "e >= φ": (61, 53, 3121),
        }
        for label, args in cases.items():
            with self.assertRaises(ValueError, msg=label):
                rsa_generate(*args)

    def test_round_trip_all_messages(self):
        key = rsa_generate(61, 53, 17)
        for m in range(key.n):
            c = rsa_encrypt(m, key)
            self.assertTrue(0 <= c < key.n)
            self.assertEqual(rsa_decrypt(c, key), m, m)

    def test_crt_decryption_agrees(self):
        require_fast_mod_pow(self)
        rng = random.Random(62)
        for p, q, e in [(61, 53, 17), (1_000_003, 999_983, 65537), (2_147_483_647, 1_000_000_007, 65537)]:
            key = rsa_generate(p, q, e)
            for _ in range(200):
                m = rng.randrange(key.n)
                c = rsa_encrypt(m, key)
                self.assertEqual(rsa_decrypt_crt(c, key), m, (p, q, m))
                self.assertEqual(rsa_decrypt_crt(c, key), rsa_decrypt(c, key))

    def test_message_range_is_checked(self):
        key = rsa_generate(61, 53, 17)
        for bad in (-1, key.n, key.n + 5):
            with self.assertRaises(ValueError, msg=bad):
                rsa_encrypt(bad, key)
            with self.assertRaises(ValueError, msg=bad):
                rsa_decrypt(bad, key)
            with self.assertRaises(ValueError, msg=bad):
                rsa_decrypt_crt(bad, key)

    def test_textbook_rsa_is_malleable(self):
        # 教科書的な RSA の弱点: E(m1) × E(m2) ≡ E(m1 × m2)。
        # 攻撃者は平文を知らなくても、暗号文から「別の平文の暗号文」を作れてしまう。
        # 実務の RSA がパディング（OAEP など）を必須とする理由の 1 つ。
        require_fast_mod_pow(self)
        key = rsa_generate(1_000_003, 999_983)
        m1, m2 = 1234, 5678
        forged = rsa_encrypt(m1, key) * rsa_encrypt(m2, key) % key.n
        self.assertEqual(rsa_decrypt(forged, key), m1 * m2)


if __name__ == "__main__":
    unittest.main()
