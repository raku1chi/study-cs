"""2.1 計算機科学のための離散数学 — 演習

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.1          # 合格数を表示
    python3 tools/check.py -v 2.1       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

演習の一覧:
    演習1（★☆☆）真理値表と、恒真式・充足可能性・同値の判定
    演習2（★☆☆）エラトステネスの篩・素数判定・素因数分解
    演習3（★★☆）ユークリッドの互除法・拡張ユークリッド・モジュラ逆数・高速べき乗
    演習4（★★☆）数え上げ（二項係数・冪集合・全射の個数・鳩の巣原理）
    演習5（★★☆）ループ不変条件を明示した整数平方根
    演習6（★★★）中国剰余定理と、教育用の玩具 RSA

制約（学びのための縛り）:
    - math.gcd・math.lcm・math.comb・math.perm・math.factorial、3 引数の pow()、
      pow(a, -1, m) は使わないでください（それ自体を実装する演習です）。
    - 演習5 では math.isqrt を使わないでください（演習2 では使って構いません）。
    - 演習6 の RSA は仕組みを学ぶための玩具です。本物の暗号には絶対に使わないでください
      （本文 6.8 節と 11.2 章を参照）。
    - テストの中では答え合わせのために標準ライブラリの関数を使っています。
"""
from __future__ import annotations

import math  # noqa: F401  演習2で math.isqrt を使えます
from itertools import product  # noqa: F401  演習1で使えます
from typing import Callable, NamedTuple, Sequence, TypeVar

T = TypeVar("T")
BoolFunc = Callable[..., object]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 真理値表と恒真式・同値の判定
# ---------------------------------------------------------------------------
# 論理関数は「n 個の bool を位置引数で受け取り、真偽値を返す Python の関数」で表します。
#     implies = lambda p, q: (not p) or q        # P → Q
# 行の順序はすべての関数で共通です: itertools.product((False, True), repeat=n) の順
# （False を 0、True を 1 とみなした 2 進数の数え上げ順。最初の変数が最上位の桁）。
# n = 0 のときは、引数なしの行 () が 1 行だけあります。n < 0 なら ValueError。

def truth_table(f: BoolFunc, n: int) -> list[tuple[tuple[bool, ...], bool]]:
    """n 変数の論理関数 f の真理値表を、(入力のタプル, 出力) のリストで返す。

    - 出力は bool(f(*入力)) に変換して格納する（f が 1/0 を返しても True/False になる）。

    >>> truth_table(lambda p, q: p and q, 2)
    [((False, False), False), ((False, True), False), ((True, False), False), ((True, True), True)]
    >>> truth_table(lambda: True, 0)
    [((), True)]
    """
    raise NotImplementedError("演習1: truth_table を実装してください")


def is_tautology(f: BoolFunc, n: int) -> bool:
    """f がすべての入力で真になる（恒真式、トートロジーである）かを返す。

    >>> is_tautology(lambda p: p or not p, 1)             # 排中律
    True
    >>> is_tautology(lambda p, q: (not p) or q, 2)        # P → Q は恒真ではない
    False
    """
    raise NotImplementedError("演習1: is_tautology を実装してください")


def is_satisfiable(f: BoolFunc, n: int) -> bool:
    """f を真にする入力が少なくとも 1 つ存在する（充足可能である）かを返す。

    >>> is_satisfiable(lambda p: p and not p, 1)          # 矛盾式
    False
    """
    raise NotImplementedError("演習1: is_satisfiable を実装してください")


def find_counterexample(f: BoolFunc, g: BoolFunc, n: int) -> tuple[bool, ...] | None:
    """bool(f(*v)) != bool(g(*v)) となる入力 v を、行の順序で最初のものを返す。なければ None。

    「2 つの条件式は同じ意味か」を確かめ、違うなら違いが出る具体的な入力（テストケース）を得る。

    >>> implies = lambda p, q: (not p) or q
    >>> find_counterexample(implies, lambda p, q: implies(q, p), 2)   # P→Q と逆 Q→P
    (False, True)
    """
    raise NotImplementedError("演習1: find_counterexample を実装してください")


def are_equivalent(f: BoolFunc, g: BoolFunc, n: int) -> bool:
    """f と g が論理的に同値（すべての入力で出力の真偽が一致する）かを返す。

    >>> are_equivalent(lambda a, b: not (a and b), lambda a, b: (not a) or (not b), 2)  # ド・モルガン
    True
    """
    raise NotImplementedError("演習1: are_equivalent を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: エラトステネスの篩と素因数分解
# ---------------------------------------------------------------------------

def primes_up_to(n: int) -> list[int]:
    """n 以下の素数を小さい順に並べたリストを、エラトステネスの篩で求める。

    - n < 2 なら空リスト（負の数も含む）。
    - 10**6 程度までを 1 秒よりずっと短い時間で求められること（1 つずつ試し割りすると遅すぎる）。

    >>> primes_up_to(30)
    [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]

    ヒント: 長さ n+1 の「素数候補か」を表す配列（bytearray が速い）を用意し、
    素数 p が見つかるたびに p*p, p*p+p, p*p+2p, ... を候補から外す。
    p は √n まで調べれば十分。
    """
    raise NotImplementedError("演習2: primes_up_to を実装してください")


def is_prime(n: int) -> bool:
    """n が素数かを試し割りで判定する。n < 2 なら False。

    >>> [x for x in range(20) if is_prime(x)]
    [2, 3, 5, 7, 11, 13, 17, 19]

    ヒント: n = a × b（a ≤ b）と分解できるなら a ≤ √n。だから √n まで割ってみれば十分。
    """
    raise NotImplementedError("演習2: is_prime を実装してください")


def factorize(n: int) -> list[tuple[int, int]]:
    """正の整数 n を素因数分解し、(素数, 指数) のリストを素数の小さい順に返す。

    - factorize(1) は []。
    - n < 1 なら ValueError。

    >>> factorize(360)          # 360 = 2^3 × 3^2 × 5
    [(2, 3), (3, 2), (5, 1)]
    >>> factorize(97)
    [(97, 1)]
    """
    raise NotImplementedError("演習2: factorize を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: ユークリッドの互除法・モジュラ逆数・高速べき乗
# ---------------------------------------------------------------------------

def gcd(a: int, b: int) -> int:
    """a と b の最大公約数を、ユークリッドの互除法で求める（math.gcd は使わない）。

    - 結果は常に 0 以上。負の入力は絶対値で考える。gcd(0, 0) は 0。

    >>> gcd(1071, 462)
    21
    >>> gcd(-12, 18)
    6

    ヒント: gcd(a, b) = gcd(b, a mod b)。
    """
    raise NotImplementedError("演習3: gcd を実装してください")


def extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    """a*x + b*y == g（g = gcd(a, b) ≥ 0）を満たす (g, x, y) を返す（拡張ユークリッドの互除法）。

    x, y は条件を満たせばどれでもよい（テストは等式と g の値だけを確かめる）。

    >>> g, x, y = extended_gcd(240, 46)
    >>> g, 240 * x + 46 * y
    (2, 2)

    ヒント: 互除法で現れる余り r_i を、それぞれ a*x_i + b*y_i の形で持ち運ぶ。
    r_{i+1} = r_{i-1} - q_i * r_i なので、x と y も同じ式で更新できる。
    """
    raise NotImplementedError("演習3: extended_gcd を実装してください")


def mod_inverse(a: int, m: int) -> int:
    """a * x ≡ 1 (mod m) となる 0 ≤ x < m を返す（pow(a, -1, m) は使わない）。

    - m < 2 なら ValueError。
    - gcd(a, m) != 1 なら逆元は存在しないので ValueError。
    - 負の a も受け付ける（a を m で割った余りとして扱う）。

    >>> mod_inverse(3, 11)       # 3 × 4 = 12 ≡ 1 (mod 11)
    4
    >>> mod_inverse(17, 3120)
    2753
    """
    raise NotImplementedError("演習3: mod_inverse を実装してください")


def mod_pow(base: int, exp: int, mod: int) -> int:
    """base^exp mod mod を、繰り返し二乗法で O(log exp) 回の乗算で求める（3 引数の pow は使わない）。

    - exp < 0 なら ValueError。mod < 1 なら ValueError。
    - mod == 1 なら常に 0。exp == 0 なら 1 % mod。負の base も受け付ける。
    - 途中の値が大きくならないよう、掛けるたびに mod で割った余りをとること。
      （テストは剰余演算の回数を数え、指数に比例する回数の実装を不合格にします）

    >>> mod_pow(3, 13, 1000)     # 3^13 = 1594323
    323

    ヒント（不変条件）: result * base^exp ≡ 元の base^元の exp (mod mod) を保ったまま、
    exp の最下位ビットが 1 なら result に base を掛け、base を 2 乗して exp を半分にする。
    """
    raise NotImplementedError("演習3: mod_pow を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 数え上げ
# ---------------------------------------------------------------------------

def n_choose_k(n: int, k: int) -> int:
    """二項係数 C(n, k) を正確な整数で返す（math.comb・math.factorial・float は使わない）。

    - n < 0 または k < 0 なら ValueError。k > n なら 0。
    - n = 1000 程度でも正確に計算できること（float を経由すると桁が失われる）。

    >>> n_choose_k(5, 2)
    10
    >>> n_choose_k(50, 2)        # 50 人のチームの 1 対 1 のコミュニケーション経路
    1225

    ヒント: C(n, i+1) = C(n, i) × (n-i) / (i+1) で、右辺は必ず割り切れる。
    """
    raise NotImplementedError("演習4: n_choose_k を実装してください")


def power_set(items: Sequence[T]) -> list[list[T]]:
    """items の冪集合（すべての部分集合）をリストのリストで返す。

    - 並び順: 0 から 2^n - 1 までの整数 mask の順。mask のビット i が 1 なら items[i] を含む。
    - 各部分集合の中の要素は items での順序を保つ。
    - 要素は位置で区別する（同じ値が 2 回あれば、同じ内容の部分集合が複数現れてよい）。

    >>> power_set(["a", "b", "c"])
    [[], ['a'], ['b'], ['a', 'b'], ['c'], ['a', 'c'], ['b', 'c'], ['a', 'b', 'c']]
    """
    raise NotImplementedError("演習4: power_set を実装してください")


def count_surjections(n: int, k: int) -> int:
    """n 要素の集合から k 要素の集合への全射（どの値にも少なくとも 1 つ写る写像）の個数を返す。

    包除原理を使って計算すること（総当たりでは n が大きいと終わらない）。
    - n < 0 または k < 0 なら ValueError。
    - k > n なら 0。count_surjections(0, 0) は 1（空の写像は空集合への全射）。

    >>> count_surjections(5, 3)    # 5 つのジョブを 3 台に、どの台にも 1 つ以上割り当てる方法
    150

    ヒント: 「値 j に写らない写像の集合」を A_j とすると、全射の個数は
    k^n - |A_1 ∪ ... ∪ A_k|。i 個の値を使わない写像は (k-i)^n 通り。
    """
    raise NotImplementedError("演習4: count_surjections を実装してください")


def min_items_for_collision(space_size: int, k: int = 2) -> int:
    """space_size 個の箱に物を入れるとき、「どこかの箱に k 個以上入る」ことが
    どんな入れ方でも保証される最小の個数を返す（一般化された鳩の巣原理）。

    - space_size < 1 または k < 1 なら ValueError。

    >>> min_items_for_collision(365)           # 366 人いれば、誕生日が同じ 2 人が必ずいる
    366
    >>> min_items_for_collision(10**4)         # 4 桁の PIN を 10,001 人に配れば必ず重複する
    10001
    >>> min_items_for_collision(10, k=3)
    21
    """
    raise NotImplementedError("演習4: min_items_for_collision を実装してください")


def min_code_length(n_ids: int, alphabet_size: int) -> int:
    """alphabet_size 種類の文字で作る固定長のコードで、n_ids 個に重複なく割り当てるのに
    必要な最小の長さ L（alphabet_size ** L >= n_ids となる最小の L ≥ 0）を返す。

    - n_ids < 1 なら ValueError。alphabet_size < 2 なら ValueError。
    - 境界（n_ids がちょうど alphabet_size のべき乗）で間違えないこと。
      math.log を使うと浮動小数点の誤差で間違えることがあるので、整数だけで計算するとよい。

    >>> min_code_length(62 ** 6, 62)       # 英大小文字＋数字の 6 文字で ちょうど 62^6 個
    6
    >>> min_code_length(62 ** 6 + 1, 62)
    7
    """
    raise NotImplementedError("演習4: min_code_length を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★☆）: ループ不変条件（整数平方根）
# ---------------------------------------------------------------------------

def isqrt_trace(n: int) -> tuple[int, list[tuple[int, int]]]:
    """整数平方根 ⌊√n⌋ を二分探索で求め、(答え, 状態の列) を返す（math.isqrt は使わない）。

    アルゴリズムを次のように決めておきます。
        lo, hi = 0, n + 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            mid * mid <= n なら lo = mid、そうでなければ hi = mid
        答えは lo

    - 状態の列は、最初の (lo, hi) = (0, n+1) と、各反復の直後の (lo, hi) を順に並べたもの。
      したがって最後の状態は hi - lo == 1 を満たす。
    - n < 0 なら ValueError。

    テストは、すべての状態で次の性質が成り立つかを確かめます。
        不変条件（invariant）: lo*lo <= n < hi*hi
        変量（variant）      : hi - lo は反復ごとに真に減少する（だから必ず停止する）
        効率                 : 状態の数は n.bit_length() + 1 以下（O(log n) 回で終わる）

    >>> isqrt_trace(10)
    (3, [(0, 11), (0, 5), (2, 5), (3, 5), (3, 4)])

    考えてみよう: ループが終わったとき、不変条件と「hi == lo + 1」から、
    なぜ lo == ⌊√n⌋ だと言えるのか。
    """
    raise NotImplementedError("演習5: isqrt_trace を実装してください")


def isqrt(n: int) -> int:
    """⌊√n⌋ を返す（isqrt_trace を使ってよい）。n < 0 なら ValueError。

    float の math.sqrt と違い、10**100 のような巨大な整数でも正確に求められる。

    >>> isqrt(10**20 + 1)
    10000000000
    """
    raise NotImplementedError("演習5: isqrt を実装してください")


# ---------------------------------------------------------------------------
# 演習6（★★★）: 中国剰余定理と、教育用の玩具 RSA
# ---------------------------------------------------------------------------
# 警告: ここで作る「教科書的な RSA」は、パディングがないため決定的（同じ平文は同じ暗号文）で、
# 暗号文を改ざんすると平文も予測どおりに変わる（準同型性）など、安全ではありません。
# 数学の仕組みを確かめるためだけのものです。実務では検証済みの暗号ライブラリを使います。

class RSAKey(NamedTuple):
    """RSA の鍵。公開鍵は (n, e)、秘密にすべきものは d, p, q。"""

    n: int
    e: int
    d: int
    p: int
    q: int


def crt(residues: Sequence[int], moduli: Sequence[int]) -> int:
    """連立合同式 x ≡ residues[i] (mod moduli[i]) の、0 ≤ x < M（M = moduli の積）となる解を返す。

    - moduli はどの 2 つも互いに素であること。そうでなければ ValueError。
    - 法が 1 未満、または residues と moduli の長さが違えば ValueError。
    - residues は負の数や法以上の数でもよい（法で割った余りとして扱う）。
    - 空の連立式の解は 0（M = 1）。

    >>> crt([2, 3, 2], [3, 5, 7])     # 3 で割ると 2 余り、5 で割ると 3 余り、7 で割ると 2 余る数
    23

    ヒント: 解を 1 つずつ合成する。x ≡ a (mod m) の解 x に対して、x + m*t ≡ b (mod n) となる
    t を求めればよい。t ≡ (b - x) × m^{-1} (mod n)（演習3 の mod_inverse が使える）。
    """
    raise NotImplementedError("演習6: crt を実装してください")


def rsa_generate(p: int, q: int, e: int = 65537) -> RSAKey:
    """2 つの素数 p, q と公開指数 e から RSA の鍵を作る。

    - n = p*q、φ(n) = (p-1)(q-1)、d = e^{-1} mod φ(n)。
      （実際の規格では λ(n) = lcm(p-1, q-1) を使うことが多い。どちらでも正しく復号できるが、
       この演習では φ(n) を使うこと）
    - p == q、p または q が 3 以上の素数（奇素数）でない、1 < e < φ(n) でない、
      gcd(e, φ(n)) != 1 のいずれかなら ValueError。
      （p = 2 を許すと d mod (p-1) = 0 になり、rsa_decrypt_crt の手順が偶数の c で誤る。
       本物の RSA の p, q も巨大な奇素数である）

    >>> rsa_generate(61, 53, 17)
    RSAKey(n=3233, e=17, d=2753, p=61, q=53)
    """
    raise NotImplementedError("演習6: rsa_generate を実装してください")


def rsa_encrypt(m: int, key: RSAKey) -> int:
    """平文 m（0 ≤ m < n の整数）を c = m^e mod n で暗号化する。範囲外なら ValueError。

    >>> rsa_encrypt(65, rsa_generate(61, 53, 17))
    2790
    """
    raise NotImplementedError("演習6: rsa_encrypt を実装してください")


def rsa_decrypt(c: int, key: RSAKey) -> int:
    """暗号文 c（0 ≤ c < n）を m = c^d mod n で復号する。範囲外なら ValueError。

    >>> rsa_decrypt(2790, rsa_generate(61, 53, 17))
    65
    """
    raise NotImplementedError("演習6: rsa_decrypt を実装してください")


def rsa_decrypt_crt(c: int, key: RSAKey) -> int:
    """中国剰余定理を使って高速に復号する。結果は rsa_decrypt と一致すること。範囲外なら ValueError。

    手順:
        dp = d mod (p-1)、dq = d mod (q-1)
        m1 = c^dp mod p、m2 = c^dq mod q
        m ≡ m1 (mod p) かつ m ≡ m2 (mod q) となる 0 ≤ m < n を crt で求める
    法の桁数が半分になるため、実際の RSA 実装では復号がおよそ数倍速くなる。

    考えてみよう: なぜ指数 d を p-1 で割った余りに縮めてよいのか（フェルマーの小定理）。
    """
    raise NotImplementedError("演習6: rsa_decrypt_crt を実装してください")
