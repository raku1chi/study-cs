"""11.2 暗号技術の基礎 — 解答例（toy_rsa）

【教育目的・本番では使わない】教科書的 RSA（パディングなし）は安全ではありません。

演習の仕様は exercises/toy_rsa.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass

SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71, 73, 79, 83, 89, 97)


@dataclass(frozen=True)
class PublicKey:
    n: int
    e: int


@dataclass(frozen=True)
class PrivateKey:
    n: int
    d: int
    p: int
    q: int


# ---------------------------------------------------------------------------
# 演習1: 拡張ユークリッドの互除法とモジュラ逆元
# ---------------------------------------------------------------------------

def egcd(a: int, b: int) -> tuple[int, int, int]:
    # 不変条件: old_r = a*old_x + b*old_y、r = a*x + b*y を保ったまま互除法を進める
    old_r, r = a, b
    old_x, x = 1, 0
    old_y, y = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_x, x = x, old_x - q * x
        old_y, y = y, old_y - q * y
    return old_r, old_x, old_y


def modinv(a: int, m: int) -> int:
    if m <= 1:
        raise ValueError(f"法 m は 2 以上です: {m}")
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise ValueError(f"{a} は法 {m} で逆元を持ちません（gcd = {g}）")
    return x % m


# ---------------------------------------------------------------------------
# 演習2: Miller–Rabin 素数判定と素数生成
# ---------------------------------------------------------------------------

def is_probable_prime(n: int, rounds: int = 20, rng: random.Random | None = None) -> bool:
    if n < 2:
        return False
    for p in SMALL_PRIMES:  # 小さな素数での試し割りで大半の合成数を安く除外する
        if n == p:
            return True
        if n % p == 0:
            return False
    rng = rng if rng is not None else random.Random(0)
    # n - 1 = 2^s * d（d は奇数）に分解する
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(rounds):
        a = rng.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            # a^d, a^(2d), ..., a^(2^(s-1) d) のどれも -1 にならなかった
            # → a は「n が合成数である証人」。確実に合成数
            return False
    return True


def generate_prime(bits: int, rng: random.Random) -> int:
    if bits < 8:
        raise ValueError(f"bits は 8 以上にしてください: {bits}")
    while True:
        # 最上位ビットを立てて「ちょうど bits ビット」に、最下位ビットを立てて奇数にする
        candidate = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate, rng=rng):
            return candidate


# ---------------------------------------------------------------------------
# 演習3: 鍵生成・暗号化・復号・署名
# ---------------------------------------------------------------------------

def generate_keypair(bits: int, rng: random.Random, e: int = 65537) -> tuple[PublicKey, PrivateKey]:
    if bits < 16 or bits % 2:
        raise ValueError(f"bits は 16 以上の偶数にしてください: {bits}")
    half = bits // 2
    while True:
        p = generate_prime(half, rng)
        q = generate_prime(half, rng)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue  # 2 つの half ビット素数の積は bits-1 ビットになることがある
        lam = math.lcm(p - 1, q - 1)  # カーマイケル関数 λ(n)
        if math.gcd(e, lam) != 1:
            continue  # e が λ(n) と互いに素でないと d が存在しない
        d = modinv(e, lam)
        return PublicKey(n, e), PrivateKey(n, d, p, q)


def _check_range(value: int, n: int) -> None:
    if not 0 <= value < n:
        raise ValueError(f"値は 0 以上 n 未満でなければなりません: {value}")


def encrypt(pub: PublicKey, m: int) -> int:
    _check_range(m, pub.n)
    return pow(m, pub.e, pub.n)


def decrypt(priv: PrivateKey, c: int) -> int:
    _check_range(c, priv.n)
    return pow(c, priv.d, priv.n)


def sign(priv: PrivateKey, m: int) -> int:
    _check_range(m, priv.n)
    return pow(m, priv.d, priv.n)


def verify(pub: PublicKey, m: int, s: int) -> bool:
    if not (0 <= m < pub.n and 0 <= s < pub.n):
        return False
    return pow(s, pub.e, pub.n) == m


# ---------------------------------------------------------------------------
# 演習4: 教科書的 RSA の可鍛性（malleability）
# ---------------------------------------------------------------------------

def malleate_ciphertext(pub: PublicKey, c: int, k: int) -> int:
    # (m^e)(k^e) = (mk)^e なので、平文を知らないまま「k 倍した平文」の暗号文が作れる
    return (c * pow(k, pub.e, pub.n)) % pub.n


def forge_signature(pub: PublicKey, m1: int, s1: int, m2: int, s2: int) -> tuple[int, int]:
    # (m1^d)(m2^d) = (m1 m2)^d なので、2 つの正規の署名から第 3 のメッセージの署名が作れる
    return (m1 * m2) % pub.n, (s1 * s2) % pub.n
