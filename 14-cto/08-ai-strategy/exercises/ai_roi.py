"""14.8 AI戦略とAIガバナンス — 演習: AI機能のROIモデル

「この AI 機能に投資すべきか」を議論するとき、トークンの単価だけを見ていると判断を誤ります。
多くの業務機能では、人のレビュー時間、すり抜けた誤りのコスト、評価・運用の固定費、
そして「実際にどれだけ使われるか（利用率）」と「どれだけ正しいか（精度）」が損益を決めます。
この演習では、簡単な月次の損益モデルを作り、シナリオ比較・損益分岐点・回収期間・
感度分析（トルネード図のデータ）を計算します。

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 14.8          # 合格数を表示
    python3 tools/check.py -v 14.8       # 各テストの結果を詳しく表示

モデルの前提（本文 9 節。教材用に単純化している）:
    handled      = eligible_requests × adoption                     AI で処理する件数/月
    model_cost   = handled × cost_per_request                        モデル利用料
    review_cost  = handled × review_rate × review_minutes × 時給/60   人のレビュー
    errors       = handled × (1 − accuracy)                          誤った結果
    escaped      = errors × (1 − review_rate)                        レビューをすり抜けた誤り
    error_cost   = escaped × error_cost（1件あたり）                  顧客対応・補償など
    savings      = handled × accuracy × minutes_saved × 時給/60      正しい結果が節約する人手
    revenue      = handled × accuracy × revenue_per_success          追加収益
    net          = savings + revenue − (model_cost + review_cost + error_cost + fixed_monthly)
    - レビューは誤りを必ず見つける、レビュー対象は誤りと無関係に選ばれる、と仮定する。
    - 金額の単位は円。単価（price_*_per_mtok）は 100 万トークンあたりの円。

制約: 標準ライブラリのみ。dataclasses.replace() を使うとパラメータを 1 つだけ変えた
モデルを簡単に作れます。
"""
from __future__ import annotations

from dataclasses import dataclass, fields, replace  # noqa: F401  replace と fields は実装で使えます
from typing import Iterable, Mapping

# 0〜1 の割合を表すパラメータ（感度分析で 1 を超えないように頭打ちにする）
RATE_FIELDS = ("adoption", "accuracy", "review_rate")
TOKENS_PER_UNIT = 1_000_000


@dataclass(frozen=True)
class AIFeatureModel:
    """AI 機能の月次モデルのパラメータ。すべて 0 以上の数値。RATE_FIELDS は 0〜1。"""

    eligible_requests: float    # AI の対象になりうる件数/月
    adoption: float             # そのうち実際に AI で処理する割合
    input_tokens: float         # 1 回の呼び出しの入力トークン（検索した文書などを含む）
    output_tokens: float        # 1 回の呼び出しの出力トークン
    price_in_per_mtok: float    # 入力 100 万トークンあたりの単価（円）
    price_out_per_mtok: float   # 出力 100 万トークンあたりの単価（円）
    accuracy: float             # AI の結果がそのまま使える割合
    review_rate: float          # 人がレビューする割合
    review_minutes: float       # レビュー 1 件あたりの時間（分）
    minutes_saved: float        # 正しい結果 1 件あたりに節約できる人手（分）
    hourly_cost: float          # 人件費（円/時。社会保険料などを含む）
    calls_per_request: float = 1.0      # 1 件あたりのモデル呼び出し回数（エージェント・再試行）
    revenue_per_success: float = 0.0    # 正しい結果 1 件あたりの追加収益（円）
    error_cost: float = 0.0             # 顧客に届いた誤り 1 件あたりのコスト（円）
    fixed_monthly: float = 0.0          # 評価・監視・基盤・運用人員などの固定費（円/月）
    build_cost: float = 0.0             # 初期開発費（円）


@dataclass(frozen=True)
class MonthlyResult:
    """月次の損益の内訳（円）。"""

    handled: float
    model_cost: float
    review_cost: float
    error_cost: float
    fixed_cost: float
    savings: float
    revenue: float

    @property
    def total_cost(self) -> float:
        return self.model_cost + self.review_cost + self.error_cost + self.fixed_cost

    @property
    def total_value(self) -> float:
        return self.savings + self.revenue

    @property
    def net(self) -> float:
        return self.total_value - self.total_cost


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 1件あたりのモデル利用料と月次の損益
# ---------------------------------------------------------------------------

def cost_per_request(m: AIFeatureModel) -> float:
    """1 件あたりのモデル利用料（円）を返す。

    calls_per_request × (input_tokens × price_in + output_tokens × price_out) ÷ 1,000,000

    パラメータの検証（monthly_result なども同じ検証を行う）:
        - 数値（int / float。bool は不可）でなければ TypeError
        - 負の値、または RATE_FIELDS が 1 を超える値なら ValueError

    例: 2 回 × (3,000 × 300 + 500 × 1,500) ÷ 1,000,000 = 3.3 円
    """
    raise NotImplementedError("演習2: cost_per_request を実装してください")


def monthly_result(m: AIFeatureModel) -> MonthlyResult:
    """モジュールの docstring の式に従って、月次の損益の内訳を返す。

    例（テストの BASE）: handled 12,000 件、model_cost 39,600 円、review_cost 480,000 円、
    error_cost 1,260,000 円、fixed_cost 800,000 円、savings 4,080,000 円 → net 1,500,400 円
    """
    raise NotImplementedError("演習2: monthly_result を実装してください")


def run_scenarios(base: AIFeatureModel, scenarios: Mapping[str, Mapping[str, float]]) -> dict[str, MonthlyResult]:
    """シナリオごとに base の一部のパラメータを上書きして、monthly_result を計算する。

    - scenarios は {シナリオ名: {パラメータ名: 値}}。戻り値は {シナリオ名: MonthlyResult}
      （scenarios と同じ順序）。
    - 上書きが空のシナリオは base そのもの。
    - 未知のパラメータ名は ValueError（打ち間違いを黙って無視しない）。
    """
    raise NotImplementedError("演習2: run_scenarios を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 損益分岐点と回収期間
# ---------------------------------------------------------------------------

def break_even(m: AIFeatureModel, field: str, lo: float, hi: float, tol: float = 1e-9) -> float | None:
    """パラメータ field だけを [lo, hi] の範囲で動かしたとき、net が 0 になる値を返す。

    - net は field について単調（増加または減少）と仮定し、二分法で求める。
    - net(lo) または net(hi) がちょうど 0 なら、その端点を返す。
    - net(lo) と net(hi) が同じ符号なら、範囲内に損益分岐点はないので None。
    - 区間の幅が tol 以下になったら、その中点を返す。
    - 未知の field、lo >= hi、tol <= 0 は ValueError。

    例: BASE の net は精度 a について 13,200,000 × a − 9,719,600 なので、
        break_even(BASE, "accuracy", 0, 1) ≒ 0.7363
    """
    raise NotImplementedError("演習3: break_even を実装してください")


def payback_month(m: AIFeatureModel, horizon_months: int, ramp_months: int = 0) -> int | None:
    """初期開発費 build_cost を回収できる月（1 始まり）を返す。回収できなければ None。

    - 累積損益は −build_cost から始まり、毎月の net を足していく。
      累積が 0 以上になった最初の月を返す。horizon_months 以内に回収できなければ None。
    - 利用率は ramp_months か月かけて直線的に立ち上がる:
        t 月目の adoption = m.adoption × min(1, t / ramp_months)
      ramp_months == 0 なら 1 か月目から m.adoption。
    - horizon_months <= 0、ramp_months < 0 は ValueError。

    例: BASE、ramp_months=3 → 1 か月目は利用率 0.2 で −33,200 円、2 か月目 +733,600 円、
        3 か月目以降 +1,500,400 円/月 → 6 か月目に回収
    """
    raise NotImplementedError("演習3: payback_month を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 感度分析（トルネード図のデータ）
# ---------------------------------------------------------------------------

def sensitivity(m: AIFeatureModel, field_names: Iterable[str], delta: float = 0.2) -> list[tuple[str, float, float]]:
    """各パラメータを ±delta（割合）動かしたときの net を返す。

    - 戻り値は (パラメータ名, 値を (1 − delta) 倍したときの net, (1 + delta) 倍したときの net)
      のリスト。
    - RATE_FIELDS のパラメータは 1 を超えないように頭打ちにする（0.85 × 1.2 → 1.0）。
    - 振れ幅 |net_high − net_low| の大きい順に並べる。同じならパラメータ名の昇順。
    - 0 < delta < 1 でなければ ValueError。未知のパラメータ名も ValueError。

    ヒント: 結果の先頭にあるパラメータほど、見積もりの精度を上げる（PoC で測る）価値が高い。
    """
    raise NotImplementedError("演習4: sensitivity を実装してください")
