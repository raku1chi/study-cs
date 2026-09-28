"""11.2 暗号技術の基礎 — 演習（toy_rsa）

╔══════════════════════════════════════════════════════════════════════╗
║ 【教育目的・本番では使わない】                                          ║
║ ここで作るのは「教科書的 RSA」（パディングなし・小さな鍵）です。          ║
║ 決定的で可鍛的（malleable）なので、実際の暗号化・署名には絶対に使わず、   ║
║ 本番では検証済みのライブラリ（RSA-OAEP / RSA-PSS、または X25519・Ed25519）║
║ を使ってください。                                                      ║
╚══════════════════════════════════════════════════════════════════════╝

RSA の仕組みを、数論の部品（拡張ユークリッドの互除法・Miller–Rabin 素数判定）から
組み立て、最後に「なぜパディングなしの RSA は危険なのか」を攻撃者の立場で確かめます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.2
    python3 tools/check.py -v 11.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_toy_rsa

制約（学びのための縛り）:
    - modinv では pow(a, -1, m) を使わず、egcd で実装してください。
    - 乱数は引数の rng（random.Random）だけから取ってください。テストを決定的にするためです。
      ※本物の鍵生成では secrets（OS の CSPRNG）を使います。random は予測可能なので
        鍵生成に使ってはいけません（README の「乱数」の節を参照）。
    - pow(x, y, m)（べき剰余）と math.gcd・math.lcm は使って構いません。
"""
from __future__ import annotations

import math  # noqa: F401  math.gcd, math.lcm が使えます
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
# 演習1（★☆☆）: 拡張ユークリッドの互除法とモジュラ逆元
# ---------------------------------------------------------------------------

def egcd(a: int, b: int) -> tuple[int, int, int]:
    """(g, x, y) を返す。g = gcd(a, b) で、a*x + b*y == g を満たす（ベズーの等式）。

    >>> g, x, y = egcd(240, 46)
    >>> g, 240 * x + 46 * y
    (2, 2)

    ヒント: 互除法の各段階で「今の余り r が a と b の何倍の和で書けるか」を
    (x, y) として一緒に更新していく。
    """
    raise NotImplementedError("演習1: egcd を実装してください")


def modinv(a: int, m: int) -> int:
    """a の法 m での逆元（a*x ≡ 1 (mod m) となる 0 <= x < m）を返す。

    - m <= 1、または gcd(a, m) != 1（逆元が存在しない）なら ValueError。
    - a が負や m 以上でもよい（a % m として扱う）。

    >>> modinv(17, 3120)
    2753
    """
    raise NotImplementedError("演習1: modinv を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: Miller–Rabin 素数判定と素数生成
# ---------------------------------------------------------------------------

def is_probable_prime(n: int, rounds: int = 20, rng: random.Random | None = None) -> bool:
    """Miller–Rabin 法で n が（おそらく）素数なら True、確実に合成数なら False を返す。

    - n < 2 は False。
    - まず SMALL_PRIMES で試し割りする（n がその素数自身なら True、割り切れたら False）。
    - n - 1 = 2^s * d（d は奇数）と分解し、rounds 回、底 a を rng.randrange(2, n - 1) で選んで試す:
        x = a^d mod n が 1 か n-1 なら、この底では「素数らしい」
        そうでなければ x を 2 乗することを s-1 回まで繰り返し、途中で n-1 になれば「素数らしい」
        最後まで n-1 にならなければ n は **確実に合成数**（a は合成数の「証人」）
    - rng が None なら random.Random(0) を使う。

    合成数を素数と誤判定する確率は、1 ラウンドあたり 1/4 以下（20 ラウンドで 4^-20 以下）。
    フェルマーテスト（a^(n-1) ≡ 1 を見るだけ）はカーマイケル数（561 など）に騙されるが、
    Miller–Rabin は騙されない、という点がテストで確かめられます。
    """
    raise NotImplementedError("演習2: is_probable_prime を実装してください")


def generate_prime(bits: int, rng: random.Random) -> int:
    """ちょうど bits ビット（最上位ビットが 1）の素数を返す。bits < 8 なら ValueError。

    手順: rng.getrandbits(bits) で候補を作り、最上位ビットと最下位ビット（奇数にする）を
    立てて、is_probable_prime(candidate, rng=rng) が True になるまで繰り返す。
    """
    raise NotImplementedError("演習2: generate_prime を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 鍵生成・暗号化・復号・署名
# ---------------------------------------------------------------------------

def generate_keypair(bits: int, rng: random.Random, e: int = 65537) -> tuple[PublicKey, PrivateKey]:
    """bits ビットの法 n を持つ RSA の鍵ペアを返す。

    - bits が 16 未満または奇数なら ValueError。
    - p, q は generate_prime(bits // 2, rng) で作る（p == q なら作り直す）。
    - n = p * q が **ちょうど bits ビット** にならなければ作り直す
      （bits/2 ビットの素数 2 つの積は bits-1 ビットになることがある）。
    - λ(n) = lcm(p - 1, q - 1)（カーマイケル関数）。gcd(e, λ(n)) != 1 なら作り直す。
    - d = modinv(e, λ(n))。
    - 戻り値: (PublicKey(n, e), PrivateKey(n, d, p, q))

    補足: 教科書では φ(n) = (p-1)(q-1) を使うことも多く、その d でも正しく動きます。
    現代の規格（FIPS 186 など）は λ(n) を使います。
    """
    raise NotImplementedError("演習3: generate_keypair を実装してください")


def encrypt(pub: PublicKey, m: int) -> int:
    """c = m^e mod n を返す。0 <= m < n でなければ ValueError。"""
    raise NotImplementedError("演習3: encrypt を実装してください")


def decrypt(priv: PrivateKey, c: int) -> int:
    """m = c^d mod n を返す。0 <= c < n でなければ ValueError。"""
    raise NotImplementedError("演習3: decrypt を実装してください")


def sign(priv: PrivateKey, m: int) -> int:
    """教科書的署名 s = m^d mod n を返す。0 <= m < n でなければ ValueError。

    本物の署名はメッセージをハッシュし、PSS などのパディングを施してから計算します。
    """
    raise NotImplementedError("演習3: sign を実装してください")


def verify(pub: PublicKey, m: int, s: int) -> bool:
    """s^e mod n == m なら True。m や s が 0 以上 n 未満でなければ（例外ではなく）False。"""
    raise NotImplementedError("演習3: verify を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 教科書的 RSA の可鍛性（malleability）— 攻撃者の立場で
# ---------------------------------------------------------------------------

def malleate_ciphertext(pub: PublicKey, c: int, k: int) -> int:
    """暗号文 c（平文 m は未知）から、平文が m*k mod n になる暗号文を **公開鍵だけで** 作る。

    ヒント: (m^e)(k^e) ≡ (mk)^e (mod n)。
    """
    raise NotImplementedError("演習4: malleate_ciphertext を実装してください")


def forge_signature(pub: PublicKey, m1: int, s1: int, m2: int, s2: int) -> tuple[int, int]:
    """正規の署名 (m1, s1)・(m2, s2) から、署名者が署名していない (m3, s3) を作って返す。

    m3 = m1*m2 mod n、s3 = s1*s2 mod n。verify(pub, m3, s3) が True になってしまう。
    ハッシュとパディング（PSS）を使う本物の署名方式では、この攻撃は成り立ちません。
    """
    raise NotImplementedError("演習4: forge_signature を実装してください")
