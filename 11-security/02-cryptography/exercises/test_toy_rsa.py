"""11.2 教科書的 RSA（toy_rsa）— テスト

【教育目的・本番では使わない】
実行: python3 tools/check.py 11.2   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import unittest

from toy_rsa import (
    PrivateKey,
    PublicKey,
    decrypt,
    egcd,
    encrypt,
    forge_signature,
    generate_keypair,
    generate_prime,
    is_probable_prime,
    malleate_ciphertext,
    modinv,
    sign,
    verify,
)


def is_prime_reference(n: int) -> bool:
    """テスト用の確実な判定（試し割り）。小さな n 専用。"""
    if n < 2:
        return False
    return all(n % p for p in range(2, math.isqrt(n) + 1))


def deterministic_mr(n: int) -> bool:
    """n < 3.3 × 10^24 で確実に正しい Miller–Rabin（底を固定）。テストの答え合わせ用。"""
    if n < 2:
        return False
    bases = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41)
    for p in bases:
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in bases:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


class TestExercise1ModularArithmetic(unittest.TestCase):
    def test_egcd_examples(self):
        g, x, y = egcd(240, 46)
        self.assertEqual(g, 2)
        self.assertEqual(240 * x + 46 * y, 2)
        self.assertEqual(egcd(17, 0)[0], 17)

    def test_egcd_bezout_identity(self):
        rng = random.Random(1)
        for _ in range(500):
            a, b = rng.randrange(0, 10**12), rng.randrange(1, 10**12)
            g, x, y = egcd(a, b)
            self.assertEqual(g, math.gcd(a, b), (a, b))
            self.assertEqual(a * x + b * y, g, (a, b))

    def test_modinv(self):
        self.assertEqual(modinv(3, 11), 4)
        self.assertEqual(modinv(17, 3120), 2753)  # 教科書によく出る RSA の例（p=61, q=53）
        self.assertEqual(modinv(-3, 11), modinv(8, 11))
        rng = random.Random(2)
        for _ in range(300):
            m = rng.randrange(2, 10**9)
            a = rng.randrange(1, m)
            if math.gcd(a, m) == 1:
                self.assertEqual(a * modinv(a, m) % m, 1, (a, m))

    def test_modinv_errors(self):
        with self.assertRaises(ValueError):
            modinv(10, 20)  # gcd = 10
        with self.assertRaises(ValueError):
            modinv(0, 7)
        with self.assertRaises(ValueError):
            modinv(3, 1)


class TestExercise2MillerRabin(unittest.TestCase):
    def test_small_numbers_match_trial_division(self):
        rng = random.Random(3)
        for n in range(-5, 3000):
            self.assertEqual(is_probable_prime(n, rng=rng), is_prime_reference(n), n)

    def test_known_primes(self):
        for p in (2, 3, 97, 7919, 2**31 - 1, 2**61 - 1, 2**89 - 1, 2**127 - 1):
            self.assertTrue(is_probable_prime(p, rng=random.Random(4)), p)

    def test_carmichael_numbers_are_composite(self):
        # フェルマーテストを「すり抜ける」合成数。Miller–Rabin は見抜ける
        for c in (561, 1105, 1729, 2465, 2821, 6601, 8911, 41041, 825265, 321197185, 5394826801):
            self.assertFalse(is_probable_prime(c, rng=random.Random(5)), c)

    def test_strong_pseudoprimes(self):
        # 底 2 の強擬素数（底 2 だけを試すと素数と誤判定される）
        for c in (2047, 3277, 4033, 4681, 8321):
            self.assertFalse(is_probable_prime(c, rng=random.Random(6)), c)
        # 底 2〜31 の素数すべてに対する強擬素数。底を固定した判定は騙されるが、ランダムな底なら見抜ける
        self.assertFalse(is_probable_prime(3825123056546413051, rng=random.Random(7)))

    def test_large_composites(self):
        self.assertFalse(is_probable_prime((2**61 - 1) * (2**89 - 1), rng=random.Random(8)))
        self.assertFalse(is_probable_prime(2**128 + 1, rng=random.Random(9)))  # フェルマー数 F7（合成数）

    def test_generate_prime(self):
        rng = random.Random(10)
        for bits in (8, 16, 64, 128):
            p = generate_prime(bits, rng)
            self.assertEqual(p.bit_length(), bits, "ちょうど bits ビットの素数を返すこと")
            self.assertTrue(deterministic_mr(p), p)

    def test_generate_prime_is_deterministic_with_seed(self):
        self.assertEqual(generate_prime(64, random.Random(11)), generate_prime(64, random.Random(11)))

    def test_generate_prime_rejects_tiny_bits(self):
        with self.assertRaises(ValueError):
            generate_prime(4, random.Random(0))


class TestExercise3Rsa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pub, cls.priv = generate_keypair(512, random.Random(2026))

    def test_key_structure(self):
        pub, priv = self.pub, self.priv
        self.assertIsInstance(pub, PublicKey)
        self.assertIsInstance(priv, PrivateKey)
        self.assertEqual(pub.n.bit_length(), 512)
        self.assertEqual(pub.e, 65537)
        self.assertEqual(priv.p * priv.q, pub.n)
        self.assertNotEqual(priv.p, priv.q)
        self.assertTrue(deterministic_mr(priv.p) and deterministic_mr(priv.q))
        lam = math.lcm(priv.p - 1, priv.q - 1)
        self.assertEqual(pub.e * priv.d % lam, 1, "d は e の λ(n) を法とする逆元")

    def test_keygen_deterministic_and_validated(self):
        self.assertEqual(generate_keypair(128, random.Random(5)), generate_keypair(128, random.Random(5)))
        with self.assertRaises(ValueError):
            generate_keypair(127, random.Random(0))

    def test_encrypt_decrypt_round_trip(self):
        rng = random.Random(12)
        for _ in range(50):
            m = rng.randrange(0, self.pub.n)
            c = encrypt(self.pub, m)
            self.assertEqual(decrypt(self.priv, c), m)
        msg = int.from_bytes("こんにちは".encode("utf-8"), "big")
        self.assertEqual(decrypt(self.priv, encrypt(self.pub, msg)), msg)

    def test_textbook_example(self):
        # p=61, q=53, n=3233, e=17, d=2753 の古典的な例（λ ではなく φ で d を作った鍵でも動く）
        pub, priv = PublicKey(3233, 17), PrivateKey(3233, 2753, 61, 53)
        self.assertEqual(encrypt(pub, 65), 2790)
        self.assertEqual(decrypt(priv, 2790), 65)

    def test_range_errors(self):
        with self.assertRaises(ValueError):
            encrypt(self.pub, self.pub.n)
        with self.assertRaises(ValueError):
            encrypt(self.pub, -1)
        with self.assertRaises(ValueError):
            decrypt(self.priv, self.pub.n + 5)

    def test_sign_verify(self):
        m = 123456789
        s = sign(self.priv, m)
        self.assertTrue(verify(self.pub, m, s))
        self.assertFalse(verify(self.pub, m + 1, s))
        self.assertFalse(verify(self.pub, m, (s + 1) % self.pub.n))
        self.assertFalse(verify(self.pub, m, self.pub.n + 1), "範囲外の署名は例外ではなく False")


class TestExercise4Malleability(unittest.TestCase):
    """教科書的 RSA の弱点を「攻撃者の立場で」確かめる。だから本番では OAEP / PSS を使う。"""

    @classmethod
    def setUpClass(cls):
        cls.pub, cls.priv = generate_keypair(512, random.Random(7))

    def test_attacker_doubles_amount_without_knowing_it(self):
        amount = 10_000  # 「1 万円を送金」という平文（攻撃者は知らない）
        c = encrypt(self.pub, amount)
        forged = malleate_ciphertext(self.pub, c, 2)  # 公開鍵だけで細工する
        self.assertNotEqual(forged, c)
        self.assertEqual(decrypt(self.priv, forged), 20_000, "復号すると 2 倍の金額になってしまう")

    def test_deterministic_encryption_allows_guessing(self):
        # 同じ平文は必ず同じ暗号文になる → 候補が少なければ総当たりで平文が分かる
        secret_vote = 1
        c = encrypt(self.pub, secret_vote)
        guesses = {encrypt(self.pub, g): g for g in (0, 1, 2)}
        self.assertEqual(guesses[c], secret_vote)

    def test_signature_forgery_by_multiplication(self):
        m1, m2 = 1234, 5678
        s1, s2 = sign(self.priv, m1), sign(self.priv, m2)
        m3, s3 = forge_signature(self.pub, m1, s1, m2, s2)
        self.assertEqual(m3, m1 * m2 % self.pub.n)
        self.assertTrue(verify(self.pub, m3, s3), "署名者が一度も署名していない m1*m2 に有効な署名ができてしまう")


if __name__ == "__main__":
    unittest.main()
