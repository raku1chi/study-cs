"""12.5 AIシステムの本番運用 — 演習1: データドリフトの検出（★★☆）

本番のモデルに入ってくるデータの分布が、学習したときの分布（基準）からずれていないかを監視します。

    - PSI（Population Stability Index）: 分布のずれの「大きさ」を 1 つの数で表す。与信モデルの監視で
      広く使われ、経験則として 0.1 未満は安定、0.1〜0.25 はやや変化、0.25 以上は大きな変化とされる。
    - 2 標本 KS 統計量: 数値の特徴量の累積分布の最大の差。p 値で「偶然の差か」を判断する。
    - カイ二乗検定: カテゴリの特徴量の割合が変わったかを判断する。
    - 判定: 効果の大きさ（PSI）と統計的な有意さ（p 値）の両方を見て、ok / warn / alert に振り分ける。
      欠損率の急増（上流のパイプラインの障害でよく起きる）も検出する。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.5
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_drift

p 値の計算（chi2_sf と ks_p_value）は数値計算の部品なので実装済みです。
"""
from __future__ import annotations

import bisect  # noqa: F401  bin_proportions で使えます（bisect_left）
import math
from collections import Counter  # noqa: F401
from dataclasses import dataclass
from typing import Hashable, Sequence

# ---------------------------------------------------------------------------
# 実装済み: p 値の計算（数値計算の部品）
# ---------------------------------------------------------------------------


def _lower_gamma_series(a: float, x: float) -> float:
    """正則化された下側不完全ガンマ関数 P(a, x) を級数で求める（x < a + 1 で速く収束する）。"""
    term = total = 1.0 / a
    ap = a
    for _ in range(10_000):
        ap += 1.0
        term *= x / ap
        total += term
        if abs(term) < abs(total) * 1e-15:
            break
    return total * math.exp(-x + a * math.log(x) - math.lgamma(a))


def _upper_gamma_cf(a: float, x: float) -> float:
    """正則化された上側不完全ガンマ関数 Q(a, x) を連分数（Lentz 法）で求める（x >= a + 1 用）。"""
    tiny = 1e-300
    b = x + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < tiny:
            d = tiny
        c = b + an / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return math.exp(-x + a * math.log(x) - math.lgamma(a)) * h


def chi2_sf(x: float, dof: int) -> float:
    """自由度 dof のカイ二乗分布の上側確率 P(X >= x)（= カイ二乗検定の p 値）。実装済み。"""
    if dof < 1:
        raise ValueError("自由度は 1 以上")
    if x <= 0:
        return 1.0
    a, y = dof / 2.0, x / 2.0
    if y < a + 1.0:
        return max(0.0, 1.0 - _lower_gamma_series(a, y))
    return min(1.0, _upper_gamma_cf(a, y))


def ks_p_value(d: float, n1: int, n2: int) -> float:
    """2 標本 KS 検定の p 値の漸近近似（Kolmogorov 分布。Numerical Recipes の方法）。実装済み。"""
    if n1 < 1 or n2 < 1:
        raise ValueError("標本の大きさは 1 以上")
    en = math.sqrt(n1 * n2 / (n1 + n2))
    lam = (en + 0.12 + 0.11 / en) * d
    total = 0.0
    sign = 1.0
    for j in range(1, 101):
        term = sign * 2.0 * math.exp(-2.0 * j * j * lam * lam)
        total += term
        if abs(term) <= 1e-10 * abs(total) or abs(term) < 1e-300:
            return min(1.0, max(0.0, total))
        sign = -sign
    return 1.0  # λ が小さく級数が収束しない = 分布の差はほぼない


# ---------------------------------------------------------------------------
# 演習1a（★☆☆〜★★☆）: PSI（Population Stability Index）
# ---------------------------------------------------------------------------

def quantile_edges(reference: Sequence[float], n_bins: int = 10) -> list[float]:
    """基準データの分位点から、ビンの内側の境界（最大 n_bins - 1 個）を作る。

    - 基準データを昇順に並べたものを s（長さ n）として、i = 1, …, n_bins - 1 について s[(i × n) // n_bins]。
    - 同じ値が多いと境界が重なるので、直前の境界より大きいものだけを残す（結果は狭義の昇順）。
    - n_bins < 2、または reference が空なら ValueError。

    >>> quantile_edges(list(range(1, 11)), 4)
    [3, 6, 8]
    """
    raise NotImplementedError("演習1a: quantile_edges を実装してください")


def bin_proportions(values: Sequence[float], edges: Sequence[float]) -> list[float]:
    """各ビンに入る値の割合（長さ len(edges) + 1、合計 1）。

    ビンは (-∞, e₀], (e₀, e₁], …, (e_last, +∞)。つまり境界と等しい値は下側のビンに入る。
    ヒント: bisect.bisect_left(edges, v) がそのままビンの番号になる。values が空なら ValueError。

    >>> bin_proportions([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [3, 6, 8])
    [0.3, 0.3, 0.2, 0.2]
    """
    raise NotImplementedError("演習1a: bin_proportions を実装してください")


def psi_from_proportions(expected: Sequence[float], actual: Sequence[float], eps: float = 1e-4) -> float:
    """PSI = Σ (a_i - e_i) × ln(a_i / e_i)（e: 基準の割合、a: 現在の割合）。

    - 割合が 0 のビンは log(0) になるので、e_i と a_i をそれぞれ max(値, eps) に置き換えてから計算する。
    - 長さが違う、または空なら ValueError。
    """
    raise NotImplementedError("演習1a: psi_from_proportions を実装してください")


def psi(reference: Sequence[float], current: Sequence[float], *, n_bins: int = 10, eps: float = 1e-4) -> float:
    """数値の特徴量の PSI。境界は **基準データだけ** で quantile_edges により決め、両方に同じ境界を使う。"""
    raise NotImplementedError("演習1a: psi を実装してください")


def categorical_psi(reference_counts: dict[Hashable, int], current_counts: dict[Hashable, int], *, eps: float = 1e-4) -> float:
    """カテゴリの特徴量の PSI。カテゴリは両方の和集合（片方にしかないカテゴリの割合は 0）。

    カテゴリの並び順は結果に影響しないが、決定的にするため str で並べるとよい。
    どちらかの件数の合計が 0 なら ValueError。
    """
    raise NotImplementedError("演習1a: categorical_psi を実装してください")


# ---------------------------------------------------------------------------
# 演習1b（★★☆）: 2 標本 KS 統計量とカイ二乗検定
# ---------------------------------------------------------------------------

def ks_statistic(reference: Sequence[float], current: Sequence[float]) -> float:
    """2 標本 KS 統計量 D = max_x |F_ref(x) - F_cur(x)|（F は経験累積分布関数）。

    両方を並べ替え、値の小さい順に「その値以下の割合」を比べる。**同じ値はまとめて** 進めてから
    差を測ること（[1, 1, 2] と [1, 2, 2] の D は 1/3。1 つずつ進めると途中で 2/3 と誤って測る）。
    どちらかが空なら ValueError。

    >>> ks_statistic([1, 2, 3], [2, 3, 4])
    0.333...
    """
    raise NotImplementedError("演習1b: ks_statistic を実装してください")


def chi_square_drift(reference_counts: dict[Hashable, int], current_counts: dict[Hashable, int]) -> tuple[float, int, float]:
    """カテゴリの割合が基準と現在で同じかを、2 × k の分割表のカイ二乗検定で調べ、(統計量, 自由度, p 値) を返す。

    - カテゴリは両方の和集合のうち、合計の件数が 0 より大きいもの（k 個）。
    - 期待度数 E = 行の合計 × 列の合計 ÷ 総数、統計量 = Σ (観測 - E)² / E（2 行 × k 列のすべてのセル）。
    - 自由度 = k - 1、p 値 = chi2_sf(統計量, 自由度)。
    - k < 2 なら検定できないので (0.0, 0, 1.0) を返す。どちらかの合計が 0 なら ValueError。

    >>> chi_square_drift({"a": 30, "b": 10}, {"a": 20, "b": 20})   # doctest: +SKIP
    (5.333..., 1, 0.0209...)
    """
    raise NotImplementedError("演習1b: chi_square_drift を実装してください")


# ---------------------------------------------------------------------------
# 演習1c（★★☆）: 特徴量ごとの判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftThresholds:
    """判定の閾値（実装済み）。"""

    psi_warn: float = 0.1
    psi_alert: float = 0.25
    p_value: float = 0.01
    missing_rate_increase: float = 0.05  # 欠損率がこれを超えて増えたら alert


@dataclass(frozen=True)
class FeatureDrift:
    """1 つの特徴量の判定結果（実装済み）。"""

    feature: str
    kind: str  # "numeric" / "categorical"
    psi: float
    statistic: float  # 数値は KS の D、カテゴリはカイ二乗統計量
    p_value: float
    missing_rate_reference: float
    missing_rate_current: float
    status: str  # "ok" / "warn" / "alert"
    reasons: tuple[str, ...] = ()


def evaluate_drift(
    reference: dict[str, Sequence],
    current: dict[str, Sequence],
    *,
    categorical: frozenset[str] | set[str] = frozenset(),
    n_bins: int = 10,
    thresholds: DriftThresholds = DriftThresholds(),
) -> list[FeatureDrift]:
    """基準データ reference と現在のデータ current（{特徴量名: 値のリスト}）を比べ、特徴量名の昇順に結果を返す。

    各特徴量について:
    1. current に特徴量がない、どちらかのリストが空、基準の値がすべて None なら ValueError。
    2. None を欠損として除き、欠損率（None の数 ÷ 全件数）を両方について求める。
    3. 現在の値がすべて欠損なら、psi=inf, statistic=inf, p_value=0.0, status="alert" の結果にする。
    4. categorical に含まれる特徴量は、Counter で数えて categorical_psi と chi_square_drift（p 値を使う）。
       それ以外は psi(n_bins=n_bins) と ks_statistic、p 値は ks_p_value(D, 基準の件数, 現在の件数)。
    5. 判定（上から順に。reasons に理由の文字列を追加する）:
       - p < thresholds.p_value かつ PSI >= psi_alert → "alert"（理由に "PSI" という語を含める）
       - p < thresholds.p_value かつ PSI >= psi_warn → "warn"（同上）
       - どちらでもなければ "ok"
       - さらに、(現在の欠損率 - 基準の欠損率) > missing_rate_increase なら "alert" にし、
         理由に「欠損」という語を含める
    効果の大きさ（PSI）と有意さ（p 値）の両方を要求するのは、小さな標本では PSI が偶然大きくなり、
    大きな標本では意味のない小さな差でも p 値が小さくなるからである（テストで両方を確かめる）。
    """
    raise NotImplementedError("演習1c: evaluate_drift を実装してください")
