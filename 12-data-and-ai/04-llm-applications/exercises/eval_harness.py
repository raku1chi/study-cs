"""12.4 LLMアプリケーション開発 — 演習3: LLM の評価ハーネス（★★☆）

プロンプトやモデルを変えたとき、「良くなったのか、たまたまなのか、どこかが悪化していないか」を
数字で判断するための小さな評価の仕組みを作ります。

    - 自動採点: 完全一致（EM）と、日本語向けの文字単位 F1、英語向けのトークン単位 F1
    - 2 つの版の比較: 同じ問題セットでの差を、対応のあるブートストラップで信頼区間つきで見積もる
    - LLM-as-a-judge のインターフェース: 本物の LLM の代わりに決定的なスタブの審査員を使う。
      順番を入れ替えて 2 回聞き、位置の偏り（先に見せた方を選びがち）を打ち消す
    - リリース判定: 統計的に悪化している、または許容幅を超えて悪化したら止める（CI に組み込む想定）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.4
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_eval_harness
"""
from __future__ import annotations

import math  # noqa: F401
import random  # noqa: F401
import unicodedata  # noqa: F401
from collections import Counter  # noqa: F401
from dataclasses import dataclass, field
from typing import Callable, Sequence


@dataclass(frozen=True)
class EvalItem:
    """評価データの 1 問（実装済み）。references は許容する正解の候補（1 つ以上）。"""

    id: str
    question: str
    references: tuple[str, ...]


# ---------------------------------------------------------------------------
# 演習3a（★☆☆）: 自動採点の指標
# ---------------------------------------------------------------------------
# references には文字列 1 つ、または文字列のリスト・タプルを渡せる。複数あれば最もよく一致したものの値を返す。
# references が空なら ValueError。

def normalize_answer(text: str) -> str:
    """採点のための正規化: NFKC → 小文字 → 句読点・かっこ（category が "P" で始まる文字）と
    空白（category が "Z" で始まる文字、および str.isspace() が真の文字）を取り除く。

    >>> normalize_answer("  １泊　12,000円。 ")
    '1泊12000円'
    """
    raise NotImplementedError("演習3a: normalize_answer を実装してください")


def exact_match(prediction: str, references: str | Sequence[str]) -> float:
    """正規化した予測が、正規化したいずれかの参照解答と完全に一致すれば 1.0、しなければ 0.0。"""
    raise NotImplementedError("演習3a: exact_match を実装してください")


def char_f1(prediction: str, references: str | Sequence[str]) -> float:
    """文字単位の F1（日本語の抽出型 QA でよく使われる）。

    正規化した文字列を文字の多重集合とみなし、共通部分の大きさ c から
    適合率 = c / 予測の文字数、再現率 = c / 参照の文字数、F1 = 2PR / (P + R)。
    両方が空なら 1.0、片方だけが空なら 0.0、c = 0 なら 0.0。

    >>> char_f1("3日です", "週3日まで")    # 共通は「3」「日」「で」
    0.666...
    """
    raise NotImplementedError("演習3a: char_f1 を実装してください")


def token_f1(prediction: str, references: str | Sequence[str]) -> float:
    """トークン単位の F1（英語向け）。空白で分割し、各トークンを normalize_answer して空になったものを除く。
    F1 の計算は char_f1 と同じ（多重集合の共通部分）。"""
    raise NotImplementedError("演習3a: token_f1 を実装してください")


# ---------------------------------------------------------------------------
# 演習3b（★★☆）: 対応のあるブートストラップ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BootstrapResult:
    """比較の結果（実装済み）。diff は B − A の平均（正なら B が良い）。"""

    mean_a: float
    mean_b: float
    diff: float
    ci_low: float
    ci_high: float
    p_b_better: float  # 再標本化した差のうち 0 より大きいものの割合


def paired_bootstrap(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    *,
    n_resamples: int = 2000,
    seed: int = 0,
    confidence: float = 0.95,
) -> BootstrapResult:
    """同じ n 問に対する 2 つの版のスコアの差を、対応のあるブートストラップで見積もる。

    アルゴリズム（テストは結果の値まで確かめるので、この通りに書くこと）:
    1. deltas[i] = scores_b[i] - scores_a[i]
    2. rng = random.Random(seed)。n_resamples 回、「rng.randrange(n) を n 回呼んで選んだ添字の
       deltas の平均」を計算し、リストに入れる（1 回の反復の中で randrange を n 回、順に呼ぶ）。
    3. そのリストを昇順に並べ、R = n_resamples として
       ci_low  = リスト[floor((1 - confidence) / 2 × R)]
       ci_high = リスト[min(R - 1, ceil((1 + confidence) / 2 × R) - 1)]
    4. p_b_better = リストのうち 0 より大きいものの割合。mean_a, mean_b, diff は元のデータから計算する。

    空、長さが違う、n_resamples < 1、confidence が (0, 1) の外なら ValueError。

    なぜ「対応のある」か: 問題ごとの難易度の差は大きいので、A と B を別々に再標本化すると区間が
    無駄に広がる。同じ問題の差を単位にすると、難易度のばらつきが打ち消し合う。
    """
    raise NotImplementedError("演習3b: paired_bootstrap を実装してください")


# ---------------------------------------------------------------------------
# 演習3c（★★☆）: LLM-as-a-judge のインターフェース
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JudgeVerdict:
    """審査員の判定（実装済み）。score は 1〜5。"""

    score: int
    reason: str


class OverlapJudge:
    """LLM の審査員の代わりに使う、決定的なスタブ。

    本物の LLM-as-a-judge は「質問・回答・参照解答」をプロンプトにして LLM に 1〜5 点で採点させるが、
    テストでは決定的に動くよう、文字 F1 で代用する: score = 1 + round(4 × char_f1(回答, 参照解答))。
    reason には F1 の値を含む短い説明を入れる。
    """

    def __call__(self, question: str, answer: str, reference: str) -> JudgeVerdict:
        raise NotImplementedError("演習3c: OverlapJudge.__call__ を実装してください")


def pairwise_preference(
    judge: Callable[[str, str, str], str], question: str, answer_a: str, answer_b: str
) -> str:
    """2 つの回答のどちらが良いかを、審査員 judge(質問, 1 つ目, 2 つ目) に聞く。

    judge は "first" / "second" / "tie" のどれかを返す（それ以外なら ValueError）。
    LLM の審査員には「先に見せた方を選びやすい」などの位置の偏りがあるので、
    (A, B) の順と (B, A) の順の 2 回聞き、両方で A が選ばれたら "A"、両方で B なら "B"、
    それ以外（判定が食い違う・引き分け）は "tie" を返す。
    """
    raise NotImplementedError("演習3c: pairwise_preference を実装してください")


# ---------------------------------------------------------------------------
# 演習3d（★★☆）: プロンプトの 2 つの版を比べる
# ---------------------------------------------------------------------------

@dataclass
class ComparisonReport:
    """比較のレポート（実装済み）。regressions / improvements は問題 ID のリスト（評価データの順）。"""

    scores_a: list[float]
    scores_b: list[float]
    bootstrap: BootstrapResult
    regressions: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)


def compare_versions(
    items: Sequence[EvalItem],
    run_a: Callable[[str], str],
    run_b: Callable[[str], str],
    *,
    metric: Callable[[str, Sequence[str]], float] = char_f1,
    n_resamples: int = 2000,
    seed: int = 0,
) -> ComparisonReport:
    """各問題で run_a(質問)・run_b(質問) の回答を metric(回答, 参照解答) で採点し、レポートを作る。

    - B のスコアが A より 1e-9 を超えて低い問題を regressions、高い問題を improvements に入れる。
    - bootstrap は paired_bootstrap(scores_a, scores_b, n_resamples=…, seed=…)。
    - items が空なら ValueError。

    run_a / run_b は「プロンプトの版 A / B で LLM に答えさせる関数」を想定している（テストでは辞書の .get）。
    """
    raise NotImplementedError("演習3d: compare_versions を実装してください")


def should_block_release(report: ComparisonReport, *, tolerance: float = 0.0) -> bool:
    """リリースを止めるべきなら True: 信頼区間の上限が 0 未満（はっきり悪化）、または diff < -tolerance。"""
    raise NotImplementedError("演習3d: should_block_release を実装してください")
