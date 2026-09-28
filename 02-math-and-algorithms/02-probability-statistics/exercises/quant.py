"""2.2 確率・統計と定量的思考 — 演習

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 2.2          # 合格数を表示
    python3 tools/check.py -v 2.2       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

演習の一覧:
    演習1（★☆☆）平均・中央値・パーセンタイル・分散（標本と母集団）
    演習2（★☆☆）ファンアウトによるテールの増幅と、誕生日のパラドックス（衝突確率）
    演習3（★☆☆）ベイズの定理とアラートの適合率
    演習4（★★☆）A/B テストの検定・信頼区間・必要サンプルサイズ・SRM チェック
    演習5（★★★）M/M/1 待ち行列の公式と、離散事象シミュレーション

制約（学びのための縛り）:
    - 演習1 では statistics モジュールの mean・median・quantiles・variance などを使わないでください
      （テストでは答え合わせに使っています）。math.fsum は使って構いません。
    - 演習4 では、正規分布の累積分布関数と逆関数に statistics.NormalDist を使ってください
      （NormalDist().cdf(z)、NormalDist().inv_cdf(q)）。
    - 乱数は必ず引数の seed から作った random.Random を使い、グローバルな random.random() は
      使わないでください（テストが再現できなくなります）。
"""
from __future__ import annotations

import heapq  # noqa: F401  演習5で使えます
import math  # noqa: F401
import random  # noqa: F401  演習5で使えます
from dataclasses import dataclass
from statistics import NormalDist  # noqa: F401  演習4で使えます
from typing import Sequence


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 記述統計
# ---------------------------------------------------------------------------

def mean(xs: Sequence[float]) -> float:
    """算術平均を返す。空なら ValueError。

    >>> mean([1, 2, 3, 4])
    2.5
    """
    raise NotImplementedError("演習1: mean を実装してください")


def median(xs: Sequence[float]) -> float:
    """中央値を返す（個数が偶数なら中央の 2 つの平均）。空なら ValueError。入力を変更しないこと。

    >>> median([3, 1, 2])
    2.0
    >>> median([4, 1, 3, 2])
    2.5
    """
    raise NotImplementedError("演習1: median を実装してください")


def percentile(xs: Sequence[float], p: float) -> float:
    """p パーセンタイル（0 <= p <= 100）を、次の「線形補間」の定義で返す。

    昇順に並べた値を s[0], ..., s[n-1] とし、h = (n - 1) * p / 100 とする。
    lo = ⌊h⌋ として、結果は s[lo] + (h - lo) * (s[lo+1] - s[lo])（h が整数なら s[h]）。
    これは NumPy の既定（method="linear"）や Excel の PERCENTILE.INC と同じ定義。
    Python の statistics.quantiles の既定（method="exclusive"）とは異なるので注意（本文 3.1 節）。

    - 空なら ValueError。p が 0〜100 の範囲外なら ValueError。
    - p = 0 は最小値、p = 100 は最大値、p = 50 は中央値と一致する。

    >>> percentile([12, 15, 11, 14, 13, 250, 12, 16, 13, 14], 50)
    13.5
    >>> round(percentile([12, 15, 11, 14, 13, 250, 12, 16, 13, 14], 90), 6)
    39.4
    """
    raise NotImplementedError("演習1: percentile を実装してください")


def variance(xs: Sequence[float], sample: bool = True) -> float:
    """分散を返す。sample=True なら標本分散（n-1 で割る）、False なら母分散（n で割る）。

    - sample=True でデータが 2 個未満、sample=False で空なら ValueError。
    - 数値的に安定な方法で計算すること。「2 乗の平均 − 平均の 2 乗」は、
      [1e9 + 4, 1e9 + 7, 1e9 + 13, 1e9 + 16] のように値が大きく分散が小さいデータで
      桁落ちして大きく間違える（テストで確かめます）。
      先に平均を求めてから偏差の 2 乗を足す「2 パス法」なら安定です。

    >>> variance([4, 7, 13, 16])
    30.0
    >>> variance([4, 7, 13, 16], sample=False)
    22.5
    """
    raise NotImplementedError("演習1: variance を実装してください")


def stdev(xs: Sequence[float], sample: bool = True) -> float:
    """標準偏差（variance の平方根）を返す。条件は variance と同じ。"""
    raise NotImplementedError("演習1: stdev を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: テールレイテンシの増幅と衝突確率
# ---------------------------------------------------------------------------
# 確率が極端に小さい（1e-15 など）とき、1 - (1 - p)**n は (1 - p) が 1.0 に丸められて
# 0 になってしまいます。math.log1p(x) = log(1 + x) と math.expm1(x) = exp(x) - 1 は、
# x が 0 に近くても精度を失わないので、これらを使って計算してください。
#     1 - (1 - p)**n  =  -expm1(n * log1p(-p))

def prob_at_least_one(p: float, n: int) -> float:
    """確率 p で起きる事象を独立に n 回試したとき、少なくとも 1 回起きる確率 1 - (1-p)^n を返す。

    例: 1 台のバックエンドが 1% の確率で遅いとき、100 台に並列に問い合わせる（ファンアウト）と、
    少なくとも 1 台が遅い確率は 63%。
    - p が 0〜1 の範囲外、または n < 0 なら ValueError。n == 0 なら 0.0。
    - p が 1e-18 のように極端に小さくても精度を失わないこと（上の注意を参照）。

    >>> round(prob_at_least_one(0.01, 100), 4)
    0.634
    """
    raise NotImplementedError("演習2: prob_at_least_one を実装してください")


def per_call_budget(target: float, n: int) -> float:
    """ファンアウト n のとき、全体で「少なくとも 1 回遅い」確率を target 以下にするために、
    1 回の呼び出しが遅くてよい確率の上限 q（1 - (1-q)^n = target の解）を返す。

    - target が 0〜1 の範囲外、または n < 1 なら ValueError。

    >>> round(per_call_budget(0.01, 100), 8)     # 各サーバーは p99.99 で目標を満たす必要がある
    0.0001005
    """
    raise NotImplementedError("演習2: per_call_budget を実装してください")


def birthday_collision_exact(n: int, m: int) -> float:
    """m 通りの値から一様ランダムに n 個選んだとき、少なくとも 1 組が一致する確率を厳密に返す。

    P(衝突なし) = (m/m) × ((m-1)/m) × … × ((m-n+1)/m)、答えは 1 - P(衝突なし)。
    - n > m なら 1.0（鳩の巣原理）。n <= 1 なら 0.0。
    - n < 0 または m < 1 なら ValueError。
    - 積を直接とると 1 に近い数の積で精度が落ちるので、log1p の和として計算するとよい。
    - ループで計算するので n は 10**7 程度までを想定（それ以上は近似式を使う）。

    >>> round(birthday_collision_exact(23, 365), 4)
    0.5073
    """
    raise NotImplementedError("演習2: birthday_collision_exact を実装してください")


def birthday_collision_approx(n: int, m: int) -> float:
    """誕生日のパラドックスの近似式 1 - exp(-n(n-1) / (2m)) を返す。

    UUIDv4（ランダムな 122 ビット、m = 2**122）のように m が巨大でも使える。
    - n < 0 または m < 1 なら ValueError。
    - 確率が 1e-20 のように小さくても 0 にならないこと（expm1 を使う）。

    >>> f"{birthday_collision_approx(10**12, 2**122):.2e}"   # UUIDv4 を 1 兆個作ったとき
    '9.40e-14'
    """
    raise NotImplementedError("演習2: birthday_collision_approx を実装してください")


def items_for_collision_probability(p: float, m: int) -> int:
    """birthday_collision_approx(n, m) >= p となる最小の整数 n を返す。

    - p は 0 < p < 1。m >= 1。それ以外は ValueError。

    ヒント: 1 - exp(-n(n-1)/(2m)) >= p ⇔ n(n-1) >= 2m·ln(1/(1-p)) なので、
    n の 2 次不等式を解けばよい。浮動小数点の誤差で 1 ずれることがあるので、
    求めた n の前後を birthday_collision_approx で確かめて調整すると確実です。

    >>> items_for_collision_probability(0.5, 365)
    23
    >>> items_for_collision_probability(0.5, 2**32)    # 32 ビットのハッシュ値
    77164
    """
    raise NotImplementedError("演習2: items_for_collision_probability を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: ベイズの定理とアラートの適合率
# ---------------------------------------------------------------------------

def bayes_posterior(prior: float, sensitivity: float, false_positive_rate: float) -> float:
    """ベイズの定理で P(H | E)（アラート E が鳴ったとき、本当に障害 H である確率）を返す。

        prior               = P(H)       基準率（事前確率）
        sensitivity         = P(E | H)   感度（検出率、再現率）
        false_positive_rate = P(E | ¬H)  偽陽性率

    - どれかが 0〜1 の範囲外なら ValueError。P(E) = 0 なら ValueError。

    >>> round(bayes_posterior(0.001, 0.99, 0.01), 3)     # 本文 1.3 節の例: 精度 99% でも 9%
    0.09
    """
    raise NotImplementedError("演習3: bayes_posterior を実装してください")


@dataclass(frozen=True)
class AlertStats:
    """n_events 件を判定したときの、混同行列の各マスの期待件数と適合率。"""

    true_positives: float    # 本物の異常で、アラートが鳴った
    false_positives: float   # 正常なのに、アラートが鳴った（誤報）
    false_negatives: float   # 本物の異常なのに、鳴らなかった（見逃し）
    true_negatives: float    # 正常で、鳴らなかった
    precision: float         # 適合率 = TP / (TP + FP)。アラートが 1 件も鳴らないなら math.nan


def alert_confusion(n_events: int, base_rate: float, sensitivity: float,
                    false_positive_rate: float) -> AlertStats:
    """n_events 件の事象（5 分間の監視窓、ログイン試行など）を判定したときの期待件数を返す。

    「確率」ではなく「100 万件のうち何件か」という自然頻度で考えると、基準率の誤りに気づきやすい。
    - n_events < 0、または確率が 0〜1 の範囲外なら ValueError。

    >>> s = alert_confusion(1_000_000, 0.00001, 0.99, 0.001)   # 不正ログイン検知の例
    >>> round(s.true_positives, 1), round(s.false_positives, 2), round(s.precision, 4)
    (9.9, 999.99, 0.0098)
    """
    raise NotImplementedError("演習3: alert_confusion を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: A/B テスト
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ABTestResult:
    rate_a: float     # A のコンバージョン率
    rate_b: float     # B のコンバージョン率
    diff: float       # rate_b - rate_a
    z: float          # 検定統計量
    p_value: float    # 両側 p 値
    ci_low: float     # 差 diff の信頼区間の下限
    ci_high: float    # 差 diff の信頼区間の上限


def two_proportion_ztest(conv_a: int, n_a: int, conv_b: int, n_b: int,
                         alpha: float = 0.05) -> ABTestResult:
    """2 群の比率の差の z 検定（両側）と、差の信頼区間（信頼水準 1 - alpha）を返す。

    検定（帰無仮説: 両群の率は等しい）:
        pooled = (conv_a + conv_b) / (n_a + n_b)
        se0    = sqrt(pooled * (1 - pooled) * (1/n_a + 1/n_b))
        z      = (rate_b - rate_a) / se0
        p 値   = 2 * (1 - Φ(|z|))                     Φ は標準正規分布の累積分布関数
    信頼区間（Wald 区間。帰無仮説を仮定しない標準誤差を使う）:
        se     = sqrt(rate_a(1-rate_a)/n_a + rate_b(1-rate_b)/n_b)
        diff ± z_{1-alpha/2} * se                     z_{1-alpha/2} = Φ^{-1}(1 - alpha/2)

    - n_a, n_b が 1 未満、conv が 0〜n の範囲外、alpha が 0 < alpha < 1 でなければ ValueError。
    - se0 == 0（両群とも率が 0、または両群とも 1）なら ValueError。

    >>> r = two_proportion_ztest(1000, 10_000, 1100, 10_000)
    >>> round(r.z, 3), round(r.p_value, 4), round(r.ci_low, 4), round(r.ci_high, 4)
    (2.307, 0.0211, 0.0015, 0.0185)
    """
    raise NotImplementedError("演習4: two_proportion_ztest を実装してください")


def sample_size_per_group(baseline: float, mde: float, alpha: float = 0.05,
                          power: float = 0.8) -> int:
    """両側検定で、差 mde（絶対値。例: 0.10 → 0.11 なら 0.01）を検出力 power で検出するのに
    必要な 1 群あたりのサンプルサイズを、次の式で求めて切り上げた整数で返す。

        p1 = baseline、p2 = baseline + mde、p̄ = (p1 + p2) / 2
        n = ( z_{1-alpha/2} * sqrt(2 p̄ (1-p̄)) + z_{power} * sqrt(p1(1-p1) + p2(1-p2)) )^2 / mde^2

    - p1, p2 が 0 < p < 1 でない、mde == 0、alpha・power が 0〜1 の間にないなら ValueError。

    >>> sample_size_per_group(0.10, 0.01)
    14751
    """
    raise NotImplementedError("演習4: sample_size_per_group を実装してください")


def srm_p_value(n_a: int, n_b: int, expected_share_a: float = 0.5) -> float:
    """サンプル比率のずれ（SRM: sample ratio mismatch）を検出するカイ二乗検定の p 値を返す。

    A に expected_share_a、B に残りを割り当てる設計なのに、実際の件数が n_a, n_b だったとき:
        期待値 e_a = n * share, e_b = n * (1 - share)（n = n_a + n_b）
        χ² = (n_a - e_a)^2 / e_a + (n_b - e_b)^2 / e_b
        p 値 = 2 * (1 - Φ(sqrt(χ²)))       （自由度 1 のカイ二乗分布 = 標準正規分布の 2 乗の分布）
    p 値が非常に小さい（例: 0.001 未満）なら、割り当てかログ収集が壊れている疑いが強く、
    その実験の結果は信用できない。
    - 件数が負、合計が 0、expected_share_a が 0 < x < 1 でなければ ValueError。

    >>> round(srm_p_value(50_000, 49_000), 4)
    0.0015
    """
    raise NotImplementedError("演習4: srm_p_value を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: 待ち行列（M/M/1）の公式と離散事象シミュレーション
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MM1Metrics:
    utilization: float      # ρ = λ/μ
    mean_in_system: float   # L  = 系内（待ち＋処理中）の平均人数 = ρ/(1-ρ)
    mean_in_queue: float    # Lq = 待ち行列の平均人数 = ρ^2/(1-ρ)
    mean_sojourn: float     # W  = 平均滞在時間（待ち＋処理） = 1/(μ-λ)
    mean_wait: float        # Wq = 平均待ち時間 = ρ/(μ-λ)


def mm1_metrics(arrival_rate: float, service_rate: float) -> MM1Metrics:
    """M/M/1 待ち行列（ポアソン到着 λ、指数分布の処理時間 平均 1/μ、窓口 1 つ）の定常状態の指標を返す。

    - λ <= 0 または μ <= 0 なら ValueError。λ >= μ（ρ >= 1）なら定常状態がないので ValueError。
    - L = λW、Lq = λWq（リトルの法則）が成り立つことを確かめよう。

    >>> m = mm1_metrics(80, 100)       # 1 秒に 80 件到着、処理能力 100 件/秒
    >>> round(m.utilization, 2), round(m.mean_sojourn * 1000, 1)   # 利用率 80%、平均 50 ms
    (0.8, 50.0)
    """
    raise NotImplementedError("演習5: mm1_metrics を実装してください")


def max_arrival_rate_for_latency(service_rate: float, target_sojourn: float) -> float:
    """M/M/1 で平均滞在時間を target_sojourn 以下に保てる最大の到着率 λ を返す。

    - service_rate <= 0 または target_sojourn <= 0 なら ValueError。
    - target_sojourn <= 1/μ（平均処理時間以下）はどんな負荷でも達成できないので ValueError。

    >>> max_arrival_rate_for_latency(100, 0.05)   # 処理 10 ms のサーバーで平均 50 ms 以内 → 80 件/秒
    80.0
    """
    raise NotImplementedError("演習5: max_arrival_rate_for_latency を実装してください")


@dataclass(frozen=True)
class QueueSimResult:
    num_customers: int      # シミュレーションした客の数
    duration: float         # 観測期間の長さ = 最後の客が退去した時刻（開始は時刻 0）
    mean_wait: float        # 待ち時間（処理開始 − 到着）の客ごとの平均
    mean_sojourn: float     # 滞在時間（退去 − 到着）の客ごとの平均
    mean_in_system: float   # 系内人数 N(t) の時間平均 = (1/duration) ∫ N(t) dt
    utilization: float      # サーバーが処理中だった時間の割合
    max_in_system: int      # 系内人数の最大値（処理中の 1 人を含む）


def simulate_mm1(arrival_rate: float, service_rate: float, num_customers: int,
                 seed: int) -> QueueSimResult:
    """M/M/1 待ち行列を離散事象シミュレーションし、観測した指標を返す。

    モデル:
        - 時刻 0 に系は空。窓口は 1 つで、到着順（FIFO）に処理する。
        - rng = random.Random(seed) を作り、客ごとに次の順で乱数を引く:
              gap     = rng.expovariate(arrival_rate)   # 前の客（最初の客は時刻 0）からの到着間隔
              service = rng.expovariate(service_rate)   # この客の処理時間
          （すべての客の到着時刻と処理時間を先に生成してからシミュレーションしてよい）
        - num_customers 人が到着し、全員が退去した時点で終了する。
    観測する指標は QueueSimResult の各フィールドのコメントを参照。

    - arrival_rate <= 0、service_rate <= 0、num_customers < 1 なら ValueError。
    - λ >= μ でもシミュレーション自体は行える（待ち行列が伸び続ける様子が観察できる）。

    ヒント（離散事象シミュレーション）:
        「到着」と「退去」という事象を時刻順に処理する。heapq を優先度付きキューとして使い、
        取り出した事象の時刻まで時計を進め、その間の N(t) × 経過時間 を面積に足してから
        状態（系内人数・待ち行列・処理中の客）を更新し、新しく決まった事象（次の到着・処理中の客の退去）を
        キューに入れる。

    テストは、①仕様どおりの乱数の順序なら参照実装と一致すること、②同じ seed で結果が再現すること、
    ③観測値でリトルの法則 L = λW が（観測期間の到着率で）成り立つこと、④長いシミュレーションで
    理論値に近づくこと、を確かめます。
    """
    raise NotImplementedError("演習5: simulate_mm1 を実装してください")
