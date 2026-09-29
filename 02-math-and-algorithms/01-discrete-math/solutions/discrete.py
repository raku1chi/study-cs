"""2.1 計算機科学のための離散数学 — 解答例

演習の仕様は exercises/discrete.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import math
from itertools import product
from typing import Callable, NamedTuple, Sequence, TypeVar

T = TypeVar("T")
BoolFunc = Callable[..., object]


# ---------------------------------------------------------------------------
# 演習1: 真理値表と恒真式・同値の判定
# ---------------------------------------------------------------------------

def _rows(n: int):
    if n < 0:
        raise ValueError(f"変数の数 n は 0 以上: {n}")
    # (False, True) の順に並べた直積 = 「False を 0、True を 1 とした 2 進数の数え上げ順」
    return product((False, True), repeat=n)


def truth_table(f: BoolFunc, n: int) -> list[tuple[tuple[bool, ...], bool]]:
    return [(row, bool(f(*row))) for row in _rows(n)]


def is_tautology(f: BoolFunc, n: int) -> bool:
    # ∀row f(row): all() は偽の行を見つけた時点で打ち切る
    return all(f(*row) for row in _rows(n))


def is_satisfiable(f: BoolFunc, n: int) -> bool:
    # ∃row f(row)。「充足可能でない」⇔「¬f が恒真」
    return any(f(*row) for row in _rows(n))


def find_counterexample(f: BoolFunc, g: BoolFunc, n: int) -> tuple[bool, ...] | None:
    for row in _rows(n):
        if bool(f(*row)) != bool(g(*row)):
            return row
    return None


def are_equivalent(f: BoolFunc, g: BoolFunc, n: int) -> bool:
    # f ≡ g ⇔ (f ↔ g) が恒真 ⇔ 反例が存在しない
    return find_counterexample(f, g, n) is None


# ---------------------------------------------------------------------------
# 演習2: エラトステネスの篩と素因数分解
# ---------------------------------------------------------------------------

def primes_up_to(n: int) -> list[int]:
    if n < 2:
        return []
    # is_prime[i] == 1 なら i はまだ「素数候補」。bytearray は bool のリストより省メモリで速い
    is_prime = bytearray([1]) * (n + 1)
    is_prime[0] = is_prime[1] = 0
    for p in range(2, math.isqrt(n) + 1):
        if is_prime[p]:
            # p の倍数を消す。p*k（k < p）はすでに k の素因数で消えているので p*p から始めればよい
            start = p * p
            is_prime[start::p] = bytes(len(range(start, n + 1, p)))
    return [i for i, flag in enumerate(is_prime) if flag]


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    # n = a × b（a ≤ b）なら a ≤ √n。だから √n までの奇数で割り切れなければ素数
    for d in range(3, math.isqrt(n) + 1, 2):
        if n % d == 0:
            return False
    return True


def factorize(n: int) -> list[tuple[int, int]]:
    if n < 1:
        raise ValueError(f"1 以上の整数を指定してください: {n}")
    factors: list[tuple[int, int]] = []
    d = 2
    # 小さい約数から割れるだけ割る。割れた d は必ず素数
    # （d より小さい素因数はすべて取り除き済みなので、合成数の d では割り切れない）
    while d * d <= n:
        if n % d == 0:
            count = 0
            while n % d == 0:
                n //= d
                count += 1
            factors.append((d, count))
        d += 1 if d == 2 else 2
    if n > 1:  # 残った n は √(元の n) より大きい素因数（高々 1 つ）
        factors.append((n, 1))
    return factors


# ---------------------------------------------------------------------------
# 演習3: ユークリッドの互除法・モジュラ逆数・高速べき乗
# ---------------------------------------------------------------------------

def gcd(a: int, b: int) -> int:
    a, b = abs(a), abs(b)
    # gcd(a, b) = gcd(b, a mod b)。b が 0 になったときの a が答え
    while b:
        a, b = b, a % b
    return a


def extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    # 不変条件: old_r = a*old_x + b*old_y かつ r = a*x + b*y
    # （r の列はユークリッドの互除法と同じ。係数も同じ漸化式で更新すれば等式が保たれる）
    old_r, r = a, b
    old_x, x = 1, 0
    old_y, y = 0, 1
    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_x, x = x, old_x - q * x
        old_y, y = y, old_y - q * y
    if old_r < 0:  # 負の入力のときは符号をそろえて gcd を非負にする
        old_r, old_x, old_y = -old_r, -old_x, -old_y
    return old_r, old_x, old_y


def mod_inverse(a: int, m: int) -> int:
    if m < 2:
        raise ValueError(f"法 m は 2 以上: {m}")
    g, x, _ = extended_gcd(a % m, m)
    # a*x + m*y = 1 なら a*x ≡ 1 (mod m)。g != 1 なら逆元は存在しない
    if g != 1:
        raise ValueError(f"{a} は法 {m} で逆元を持ちません（gcd = {g}）")
    return x % m


def mod_pow(base: int, exp: int, mod: int) -> int:
    if exp < 0:
        raise ValueError(f"指数は 0 以上: {exp}")
    if mod < 1:
        raise ValueError(f"法は 1 以上: {mod}")
    result = 1 % mod           # mod == 1 なら答えは常に 0
    base %= mod                # 負の base もここで 0〜mod-1 に正規化される
    # 不変条件: result * base^exp ≡ (元の base)^(元の exp)  (mod mod)
    while exp > 0:
        if exp & 1:            # 指数の最下位ビットが 1 なら、いまの base を結果に掛ける
            result = result * base % mod
        base = base * base % mod  # base を 2 乗し、指数を半分にする（不変条件は保たれる）
        exp >>= 1
    return result


# ---------------------------------------------------------------------------
# 演習4: 数え上げ
# ---------------------------------------------------------------------------

def n_choose_k(n: int, k: int) -> int:
    if n < 0 or k < 0:
        raise ValueError(f"n と k は 0 以上: n={n}, k={k}")
    if k > n:
        return 0
    k = min(k, n - k)  # C(n, k) = C(n, n-k)。掛け算の回数を減らす
    result = 1
    for i in range(k):
        # ここで result == C(n, i)。C(n, i+1) = C(n, i) * (n-i) / (i+1) は必ず整数なので、
        # 先に掛けてから割れば、途中で小数（float）を一切使わずに正確に計算できる
        result = result * (n - i) // (i + 1)
    return result


def power_set(items: Sequence[T]) -> list[list[T]]:
    n = len(items)
    # 部分集合 ↔ n ビットの整数（ビット i が 1 なら items[i] を含む）という全単射を使う
    return [[items[i] for i in range(n) if mask >> i & 1] for mask in range(1 << n)]


def count_surjections(n: int, k: int) -> int:
    if n < 0 or k < 0:
        raise ValueError(f"n と k は 0 以上: n={n}, k={k}")
    # 包除原理: 全射 = 全体 − 「少なくとも 1 つの値に写らない」写像
    #   = Σ_{i=0}^{k} (-1)^i C(k, i) (k-i)^n
    # （i 個の値を「使わない」と決めた写像は (k-i)^n 通り）
    return sum((-1) ** i * n_choose_k(k, i) * (k - i) ** n for i in range(k + 1))


def min_items_for_collision(space_size: int, k: int = 2) -> int:
    if space_size < 1 or k < 1:
        raise ValueError(f"space_size と k は 1 以上: space_size={space_size}, k={k}")
    # 一般化された鳩の巣原理: 各箱に k-1 個ずつ入れると space_size*(k-1) 個までは
    # 「どの箱も k 個未満」にできる。あと 1 個入れると、どこかの箱が k 個になる
    return space_size * (k - 1) + 1


def min_code_length(n_ids: int, alphabet_size: int) -> int:
    if n_ids < 1:
        raise ValueError(f"n_ids は 1 以上: {n_ids}")
    if alphabet_size < 2:
        raise ValueError(f"alphabet_size は 2 以上: {alphabet_size}")
    # alphabet_size^L >= n_ids となる最小の L。math.log を使うと浮動小数点の誤差で
    # 境界（ちょうど 62^6 など）を間違えるので、整数の掛け算だけで求める
    length, capacity = 0, 1
    while capacity < n_ids:
        capacity *= alphabet_size
        length += 1
    return length


# ---------------------------------------------------------------------------
# 演習5: ループ不変条件（整数平方根）
# ---------------------------------------------------------------------------

def isqrt_trace(n: int) -> tuple[int, list[tuple[int, int]]]:
    if n < 0:
        raise ValueError(f"負の数の平方根は扱いません: {n}")
    lo, hi = 0, n + 1
    # 初期化: 0*0 <= n < (n+1)*(n+1) なので不変条件 lo^2 <= n < hi^2 は成り立つ
    states = [(lo, hi)]
    while hi - lo > 1:
        mid = (lo + hi) // 2      # lo < mid < hi（hi - lo >= 2 なので）
        if mid * mid <= n:
            lo = mid              # lo^2 <= n は mid で保たれる
        else:
            hi = mid              # n < hi^2 は mid で保たれる
        # 維持: 不変条件は保たれ、hi - lo（変量）は真に減る
        states.append((lo, hi))
    # 終了: hi == lo + 1 かつ lo^2 <= n < (lo+1)^2。これは lo == ⌊√n⌋ の定義そのもの
    return lo, states


def isqrt(n: int) -> int:
    return isqrt_trace(n)[0]


# ---------------------------------------------------------------------------
# 演習6: 中国剰余定理と RSA（教育用の玩具）
# ---------------------------------------------------------------------------

class RSAKey(NamedTuple):
    n: int
    e: int
    d: int
    p: int
    q: int


def crt(residues: Sequence[int], moduli: Sequence[int]) -> int:
    if len(residues) != len(moduli):
        raise ValueError("residues と moduli の長さが違います")
    x, m = 0, 1  # 不変条件: x は「これまでの連立合同式」の 0 <= x < m となる唯一の解
    for r, mi in zip(residues, moduli):
        if mi < 1:
            raise ValueError(f"法は 1 以上: {mi}")
        if gcd(m, mi) != 1:
            raise ValueError(f"法が互いに素ではありません: {mi}")
        # x + m*t ≡ r (mod mi) を t について解く: t ≡ (r - x) * m^{-1} (mod mi)
        t = (r - x) * mod_inverse(m, mi) % mi if mi > 1 else 0
        x += m * t
        m *= mi
    return x % m


def rsa_generate(p: int, q: int, e: int = 65537) -> RSAKey:
    if p == q:
        raise ValueError("p と q は異なる素数にしてください")
    # p = 2 だと d mod (p-1) = 0 となり、CRT による復号で c^0 = 1 になって誤るので除外する
    if not (p > 2 and q > 2 and is_prime(p) and is_prime(q)):
        raise ValueError(f"p と q は 3 以上の素数にしてください: p={p}, q={q}")
    phi = (p - 1) * (q - 1)
    if not 1 < e < phi:
        raise ValueError(f"e は 1 < e < φ(n) = {phi} の範囲で指定してください: {e}")
    if gcd(e, phi) != 1:
        raise ValueError(f"e と φ(n) が互いに素ではありません: e={e}, φ(n)={phi}")
    d = mod_inverse(e, phi)  # e*d ≡ 1 (mod φ(n))
    return RSAKey(n=p * q, e=e, d=d, p=p, q=q)


def _check_message(x: int, key: RSAKey) -> None:
    if not 0 <= x < key.n:
        raise ValueError(f"0 <= x < n = {key.n} の整数を指定してください: {x}")


def rsa_encrypt(m: int, key: RSAKey) -> int:
    _check_message(m, key)
    return mod_pow(m, key.e, key.n)


def rsa_decrypt(c: int, key: RSAKey) -> int:
    _check_message(c, key)
    return mod_pow(c, key.d, key.n)


def rsa_decrypt_crt(c: int, key: RSAKey) -> int:
    _check_message(c, key)
    # フェルマーの小定理より、法 p では指数を p-1 で割った余りに縮められる
    dp = key.d % (key.p - 1)
    dq = key.d % (key.q - 1)
    # 半分の桁数の法で 2 回べき乗し（大きな鍵ではこちらが数倍速い）、CRT で 1 つにまとめる
    m1 = mod_pow(c, dp, key.p)
    m2 = mod_pow(c, dq, key.q)
    return crt([m1, m2], [key.p, key.q])
