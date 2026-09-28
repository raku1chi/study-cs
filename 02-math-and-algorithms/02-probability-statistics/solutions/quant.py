"""2.2 確率・統計と定量的思考 — 解答例

演習の仕様は exercises/quant.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import heapq
import math
import random
from dataclasses import dataclass
from statistics import NormalDist
from typing import Sequence

_STD_NORMAL = NormalDist()  # 標準正規分布 N(0, 1)


def _check_probability(name: str, p: float) -> None:
    if not 0.0 <= p <= 1.0:
        raise ValueError(f"{name} は 0〜1 の確率で指定してください: {p}")


# ---------------------------------------------------------------------------
# 演習1: 記述統計
# ---------------------------------------------------------------------------

def mean(xs: Sequence[float]) -> float:
    if len(xs) == 0:
        raise ValueError("空のデータの平均は定義されません")
    return math.fsum(xs) / len(xs)  # fsum は丸め誤差を補正した合計


def median(xs: Sequence[float]) -> float:
    if len(xs) == 0:
        raise ValueError("空のデータの中央値は定義されません")
    s = sorted(xs)
    mid = len(s) // 2
    if len(s) % 2 == 1:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2


def percentile(xs: Sequence[float], p: float) -> float:
    if len(xs) == 0:
        raise ValueError("空のデータのパーセンタイルは定義されません")
    if not 0 <= p <= 100:
        raise ValueError(f"p は 0〜100 で指定してください: {p}")
    s = sorted(xs)
    # 並べた値の「0 始まりの位置」h を実数で求め、両隣の値を線形補間する
    # （NumPy の既定 method="linear"、Hyndman & Fan の type 7 と同じ定義）
    h = (len(s) - 1) * p / 100
    lo = math.floor(h)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (h - lo) * (s[hi] - s[lo])


def variance(xs: Sequence[float], sample: bool = True) -> float:
    n = len(xs)
    if sample and n < 2:
        raise ValueError("標本分散には 2 個以上のデータが必要です")
    if n == 0:
        raise ValueError("空のデータの分散は定義されません")
    m = mean(xs)
    # 2 パス法: 先に平均を求め、偏差の 2 乗を足す。
    # 「2 乗の平均 − 平均の 2 乗」は、値が大きく分散が小さいと桁落ちで壊れる
    ss = math.fsum((x - m) ** 2 for x in xs)
    # 標本分散は n-1 で割る（ベッセルの補正）。標本平均は母平均よりデータに「寄っている」ため、
    # n で割ると母分散を系統的に小さく見積もってしまう
    return ss / (n - 1 if sample else n)


def stdev(xs: Sequence[float], sample: bool = True) -> float:
    return math.sqrt(variance(xs, sample))


# ---------------------------------------------------------------------------
# 演習2: テールレイテンシの増幅と衝突確率
# ---------------------------------------------------------------------------

def prob_at_least_one(p: float, n: int) -> float:
    _check_probability("p", p)
    if n < 0:
        raise ValueError(f"n は 0 以上: {n}")
    if n == 0:
        return 0.0
    if p == 1.0:
        return 1.0
    # 1 - (1-p)^n をそのまま計算すると、p が極端に小さいとき (1-p) が 1.0 に丸められて 0 になる。
    # (1-p)^n = exp(n * log(1-p)) とし、log1p・expm1 で 1 に近い値の丸めを避ける
    return -math.expm1(n * math.log1p(-p))


def per_call_budget(target: float, n: int) -> float:
    _check_probability("target", target)
    if n < 1:
        raise ValueError(f"n は 1 以上: {n}")
    if target == 1.0:
        return 1.0
    # 1 - (1-q)^n = target を q について解く: q = 1 - (1-target)^(1/n)
    return -math.expm1(math.log1p(-target) / n)


def _check_birthday_args(n: int, m: int) -> None:
    if n < 0:
        raise ValueError(f"n は 0 以上: {n}")
    if m < 1:
        raise ValueError(f"m は 1 以上: {m}")


def birthday_collision_exact(n: int, m: int) -> float:
    _check_birthday_args(n, m)
    if n > m:
        return 1.0  # 鳩の巣原理
    # P(衝突なし) = Π_{i=0}^{n-1} (m-i)/m。積を直接とると 1 に近い値の積で精度が落ちるので、
    # 対数の和 Σ log1p(-i/m) として計算する
    log_no_collision = math.fsum(math.log1p(-i / m) for i in range(1, n))
    return -math.expm1(log_no_collision)


def birthday_collision_approx(n: int, m: int) -> float:
    _check_birthday_args(n, m)
    # 1 - exp(-n(n-1)/(2m))。n*(n-1) は int のまま計算し、最後に 1 回だけ割る
    return -math.expm1(-(n * (n - 1)) / (2 * m))


def items_for_collision_probability(p: float, m: int) -> int:
    if not 0.0 < p < 1.0:
        raise ValueError(f"p は 0 < p < 1 で指定してください: {p}")
    if m < 1:
        raise ValueError(f"m は 1 以上: {m}")
    # 1 - exp(-n(n-1)/(2m)) >= p  ⇔  n(n-1) >= 2m·ln(1/(1-p))。n の 2 次不等式を解く
    target = 2 * m * -math.log1p(-p)
    n = max(1, math.ceil((1 + math.sqrt(1 + 4 * target)) / 2))
    # 浮動小数点の誤差で 1 つずれることがあるので、定義（近似式の値が p 以上となる最小の n）で調整する
    while n > 1 and birthday_collision_approx(n - 1, m) >= p:
        n -= 1
    while birthday_collision_approx(n, m) < p:
        n += 1
    return n


# ---------------------------------------------------------------------------
# 演習3: ベイズの定理とアラートの適合率
# ---------------------------------------------------------------------------

def bayes_posterior(prior: float, sensitivity: float, false_positive_rate: float) -> float:
    for name, value in (("prior", prior), ("sensitivity", sensitivity),
                        ("false_positive_rate", false_positive_rate)):
        _check_probability(name, value)
    # P(E) = P(E|H)P(H) + P(E|¬H)P(¬H)（全確率の公式）
    evidence = sensitivity * prior + false_positive_rate * (1 - prior)
    if evidence == 0:
        raise ValueError("P(E) = 0 のため事後確率は定義されません（アラートが決して鳴らない）")
    return sensitivity * prior / evidence


@dataclass(frozen=True)
class AlertStats:
    true_positives: float
    false_positives: float
    false_negatives: float
    true_negatives: float
    precision: float


def alert_confusion(n_events: int, base_rate: float, sensitivity: float,
                    false_positive_rate: float) -> AlertStats:
    if n_events < 0:
        raise ValueError(f"n_events は 0 以上: {n_events}")
    for name, value in (("base_rate", base_rate), ("sensitivity", sensitivity),
                        ("false_positive_rate", false_positive_rate)):
        _check_probability(name, value)
    # 「自然頻度」で考える: n 件のうち本物は何件で、そのうち何件が鳴るか
    positives = n_events * base_rate
    negatives = n_events - positives
    tp = positives * sensitivity
    fn = positives - tp
    fp = negatives * false_positive_rate
    tn = negatives - fp
    precision = tp / (tp + fp) if tp + fp > 0 else math.nan
    return AlertStats(tp, fp, fn, tn, precision)


# ---------------------------------------------------------------------------
# 演習4: A/B テスト
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ABTestResult:
    rate_a: float
    rate_b: float
    diff: float
    z: float
    p_value: float
    ci_low: float
    ci_high: float


def _check_counts(conv: int, n: int, label: str) -> None:
    if n <= 0:
        raise ValueError(f"{label} のユーザー数は 1 以上: {n}")
    if not 0 <= conv <= n:
        raise ValueError(f"{label} のコンバージョン数は 0〜{n}: {conv}")


def two_proportion_ztest(conv_a: int, n_a: int, conv_b: int, n_b: int,
                         alpha: float = 0.05) -> ABTestResult:
    _check_counts(conv_a, n_a, "A")
    _check_counts(conv_b, n_b, "B")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha は 0 < alpha < 1: {alpha}")
    rate_a, rate_b = conv_a / n_a, conv_b / n_b
    diff = rate_b - rate_a
    # 検定: 帰無仮説「A と B の率は等しい」のもとでは共通の率 pooled を推定し、それで標準誤差を計算する
    pooled = (conv_a + conv_b) / (n_a + n_b)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    if se_pooled == 0:
        raise ValueError("両群とも率が 0 または 1 のため検定できません")
    z = diff / se_pooled
    p_value = 2 * (1 - _STD_NORMAL.cdf(abs(z)))  # 両側検定
    # 信頼区間: 差の推定なので、帰無仮説を仮定せず各群の率で標準誤差を計算する（Wald 区間）
    se = math.sqrt(rate_a * (1 - rate_a) / n_a + rate_b * (1 - rate_b) / n_b)
    z_crit = _STD_NORMAL.inv_cdf(1 - alpha / 2)
    return ABTestResult(rate_a, rate_b, diff, z, p_value, diff - z_crit * se, diff + z_crit * se)


def sample_size_per_group(baseline: float, mde: float, alpha: float = 0.05,
                          power: float = 0.8) -> int:
    p1, p2 = baseline, baseline + mde
    if not (0 < p1 < 1 and 0 < p2 < 1):
        raise ValueError(f"baseline と baseline + mde は 0〜1 の間: {p1}, {p2}")
    if mde == 0:
        raise ValueError("mde = 0 は検出できません")
    if not 0 < alpha < 1 or not 0 < power < 1:
        raise ValueError(f"alpha と power は 0〜1 の間: alpha={alpha}, power={power}")
    z_alpha = _STD_NORMAL.inv_cdf(1 - alpha / 2)
    z_beta = _STD_NORMAL.inv_cdf(power)
    p_bar = (p1 + p2) / 2
    # 帰無仮説のもとでの標準偏差（共通の率 p_bar）と、対立仮説のもとでの標準偏差を使う
    numerator = (z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
                 + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(numerator / mde**2)


def srm_p_value(n_a: int, n_b: int, expected_share_a: float = 0.5) -> float:
    if n_a < 0 or n_b < 0 or n_a + n_b == 0:
        raise ValueError(f"件数が不正です: n_a={n_a}, n_b={n_b}")
    if not 0 < expected_share_a < 1:
        raise ValueError(f"expected_share_a は 0 < x < 1: {expected_share_a}")
    n = n_a + n_b
    e_a, e_b = n * expected_share_a, n * (1 - expected_share_a)
    chi2 = (n_a - e_a) ** 2 / e_a + (n_b - e_b) ** 2 / e_b
    # 自由度 1 のカイ二乗分布は標準正規分布の 2 乗の分布なので、P(χ² ≥ c) = 2(1 - Φ(√c))
    return 2 * (1 - _STD_NORMAL.cdf(math.sqrt(chi2)))


# ---------------------------------------------------------------------------
# 演習5: 待ち行列（M/M/1）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MM1Metrics:
    utilization: float
    mean_in_system: float
    mean_in_queue: float
    mean_sojourn: float
    mean_wait: float


def _check_rates(arrival_rate: float, service_rate: float) -> None:
    if arrival_rate <= 0 or service_rate <= 0:
        raise ValueError(f"到着率と処理率は正の数: λ={arrival_rate}, μ={service_rate}")


def mm1_metrics(arrival_rate: float, service_rate: float) -> MM1Metrics:
    _check_rates(arrival_rate, service_rate)
    if arrival_rate >= service_rate:
        raise ValueError(f"λ >= μ では待ち行列が無限に伸びます（ρ = {arrival_rate / service_rate:.3f}）")
    rho = arrival_rate / service_rate
    w = 1 / (service_rate - arrival_rate)  # 平均滞在時間 W = 1/(μ-λ)
    wq = rho * w                           # 平均待ち時間 Wq = W - 1/μ = ρ/(μ-λ)
    # L と Lq はリトルの法則 L = λW から
    return MM1Metrics(rho, arrival_rate * w, arrival_rate * wq, w, wq)


def max_arrival_rate_for_latency(service_rate: float, target_sojourn: float) -> float:
    if service_rate <= 0 or target_sojourn <= 0:
        raise ValueError("service_rate と target_sojourn は正の数")
    if target_sojourn <= 1 / service_rate:
        raise ValueError(
            f"目標 {target_sojourn} は平均処理時間 {1 / service_rate} 以下なので、どんな負荷でも達成できません"
        )
    # 1/(μ-λ) <= target ⇔ λ <= μ - 1/target
    return service_rate - 1 / target_sojourn


@dataclass(frozen=True)
class QueueSimResult:
    num_customers: int
    duration: float
    mean_wait: float
    mean_sojourn: float
    mean_in_system: float
    utilization: float
    max_in_system: int


_ARRIVAL, _DEPARTURE = 1, 0  # 同時刻なら退去（0）を先に処理する


def simulate_mm1(arrival_rate: float, service_rate: float, num_customers: int,
                 seed: int) -> QueueSimResult:
    _check_rates(arrival_rate, service_rate)
    if num_customers < 1:
        raise ValueError(f"num_customers は 1 以上: {num_customers}")
    rng = random.Random(seed)

    # 乱数を引く順序を仕様どおりに固定する（到着間隔 → 処理時間、を客ごとに交互に）
    arrivals: list[float] = []
    services: list[float] = []
    t = 0.0
    for _ in range(num_customers):
        t += rng.expovariate(arrival_rate)
        arrivals.append(t)
        services.append(rng.expovariate(service_rate))

    # 離散事象シミュレーション: 「次に起きる事象」を優先度付きキュー（時刻順）から取り出して処理する
    events: list[tuple[float, int, int]] = [(arrivals[0], _ARRIVAL, 0)]
    waiting: list[int] = []      # 待っている客（FIFO。先頭を指す添字で管理）
    head = 0
    in_service: int | None = None
    in_system = max_in_system = 0
    last_time = area = busy = 0.0  # area = ∫ N(t) dt、busy = サーバーが処理中だった時間の合計
    total_wait = total_sojourn = 0.0

    def start_service(i: int, now: float) -> None:
        nonlocal in_service, total_wait
        in_service = i
        total_wait += now - arrivals[i]
        heapq.heappush(events, (now + services[i], _DEPARTURE, i))

    while events:
        now, kind, i = heapq.heappop(events)
        # 前の事象から今までの間、系内人数は一定だったので、面積と稼働時間を積み上げる
        area += in_system * (now - last_time)
        if in_service is not None:
            busy += now - last_time
        last_time = now

        if kind == _ARRIVAL:
            in_system += 1
            max_in_system = max(max_in_system, in_system)
            if i + 1 < num_customers:  # 次の客の到着を予約する
                heapq.heappush(events, (arrivals[i + 1], _ARRIVAL, i + 1))
            if in_service is None:
                start_service(i, now)
            else:
                waiting.append(i)
        else:  # 退去
            in_system -= 1
            total_sojourn += now - arrivals[i]
            in_service = None
            if head < len(waiting):
                start_service(waiting[head], now)
                head += 1

    duration = last_time  # 最後の客が退去した時刻
    return QueueSimResult(
        num_customers=num_customers,
        duration=duration,
        mean_wait=total_wait / num_customers,
        mean_sojourn=total_sojourn / num_customers,
        mean_in_system=area / duration,
        utilization=busy / duration,
        max_in_system=max_in_system,
    )
