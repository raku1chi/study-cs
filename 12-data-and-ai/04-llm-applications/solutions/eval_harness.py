"""12.4 LLMアプリケーション開発 — 演習3: LLM の評価ハーネス（解答例）

演習の仕様は exercises/eval_harness.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import random
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence


@dataclass(frozen=True)
class EvalItem:
    id: str
    question: str
    references: tuple[str, ...]


# ---------------------------------------------------------------------------
# 演習3a: 自動採点の指標
# ---------------------------------------------------------------------------

def normalize_answer(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    # 句読点・記号的な区切り（P*）と空白（Z* や改行・タブ）を取り除く
    return "".join(
        ch for ch in text
        if not (unicodedata.category(ch).startswith(("P", "Z")) or ch.isspace())
    )


def _as_refs(references: str | Sequence[str]) -> list[str]:
    refs = [references] if isinstance(references, str) else list(references)
    if not refs:
        raise ValueError("参照解答が空です")
    return refs


def exact_match(prediction: str, references: str | Sequence[str]) -> float:
    pred = normalize_answer(prediction)
    return 1.0 if any(pred == normalize_answer(r) for r in _as_refs(references)) else 0.0


def _f1(pred_units: Sequence[str], ref_units: Sequence[str]) -> float:
    if not pred_units and not ref_units:
        return 1.0
    if not pred_units or not ref_units:
        return 0.0
    common = sum((Counter(pred_units) & Counter(ref_units)).values())  # 多重集合の共通部分
    if common == 0:
        return 0.0
    precision = common / len(pred_units)
    recall = common / len(ref_units)
    return 2 * precision * recall / (precision + recall)


def char_f1(prediction: str, references: str | Sequence[str]) -> float:
    # 日本語は単語の区切りがないので、文字単位で重なりを数える
    pred = list(normalize_answer(prediction))
    return max(_f1(pred, list(normalize_answer(r))) for r in _as_refs(references))


def token_f1(prediction: str, references: str | Sequence[str]) -> float:
    def tokens(s: str) -> list[str]:
        return [t for t in (normalize_answer(w) for w in s.split()) if t]

    pred = tokens(prediction)
    return max(_f1(pred, tokens(r)) for r in _as_refs(references))


# ---------------------------------------------------------------------------
# 演習3b: 対応のあるブートストラップ
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BootstrapResult:
    mean_a: float
    mean_b: float
    diff: float
    ci_low: float
    ci_high: float
    p_b_better: float


def paired_bootstrap(
    scores_a: Sequence[float],
    scores_b: Sequence[float],
    *,
    n_resamples: int = 2000,
    seed: int = 0,
    confidence: float = 0.95,
) -> BootstrapResult:
    n = len(scores_a)
    if n == 0 or n != len(scores_b):
        raise ValueError("スコアの列が空か、長さが違います")
    if n_resamples < 1 or not 0 < confidence < 1:
        raise ValueError("n_resamples >= 1, 0 < confidence < 1")
    rng = random.Random(seed)
    # 同じ問題に対する 2 つのスコアの差を単位に再標本化する（問題の難易度のばらつきが打ち消し合う）
    deltas = [b - a for a, b in zip(scores_a, scores_b)]
    diffs = []
    for _ in range(n_resamples):
        total = 0.0
        for _ in range(n):
            total += deltas[rng.randrange(n)]
        diffs.append(total / n)
    diffs.sort()
    lo_index = math.floor((1 - confidence) / 2 * n_resamples)
    hi_index = min(n_resamples - 1, math.ceil((1 + confidence) / 2 * n_resamples) - 1)
    mean_a = sum(scores_a) / n
    mean_b = sum(scores_b) / n
    return BootstrapResult(
        mean_a=mean_a,
        mean_b=mean_b,
        diff=mean_b - mean_a,
        ci_low=diffs[lo_index],
        ci_high=diffs[hi_index],
        p_b_better=sum(d > 0 for d in diffs) / n_resamples,
    )


# ---------------------------------------------------------------------------
# 演習3c: LLM-as-a-judge のインターフェース
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class JudgeVerdict:
    score: int
    reason: str


class OverlapJudge:
    """LLM の審査員の代わりに使う、決定的なスタブ。"""

    def __call__(self, question: str, answer: str, reference: str) -> JudgeVerdict:
        f1 = char_f1(answer, reference)
        score = 1 + round(4 * f1)
        return JudgeVerdict(score, f"参照解答との文字 F1 = {f1:.2f}")


def pairwise_preference(
    judge: Callable[[str, str, str], str], question: str, answer_a: str, answer_b: str
) -> str:
    # 順番を入れ替えて 2 回聞き、両方で同じ側が選ばれたときだけ勝ちとする（位置バイアスへの対策）
    first = judge(question, answer_a, answer_b)
    second = judge(question, answer_b, answer_a)
    for verdict in (first, second):
        if verdict not in ("first", "second", "tie"):
            raise ValueError(f"審査結果は first / second / tie のどれか: {verdict!r}")
    if first == "first" and second == "second":
        return "A"
    if first == "second" and second == "first":
        return "B"
    return "tie"


# ---------------------------------------------------------------------------
# 演習3d: プロンプトの 2 つの版を比べる
# ---------------------------------------------------------------------------

@dataclass
class ComparisonReport:
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
    if not items:
        raise ValueError("評価データが空です")
    scores_a, scores_b, regressions, improvements = [], [], [], []
    for item in items:
        a = metric(run_a(item.question), item.references)
        b = metric(run_b(item.question), item.references)
        scores_a.append(a)
        scores_b.append(b)
        if b < a - 1e-9:
            regressions.append(item.id)  # 平均が上がっても、個別に悪化した問題は必ず確認する
        elif b > a + 1e-9:
            improvements.append(item.id)
    boot = paired_bootstrap(scores_a, scores_b, n_resamples=n_resamples, seed=seed)
    return ComparisonReport(scores_a, scores_b, boot, regressions, improvements)


def should_block_release(report: ComparisonReport, *, tolerance: float = 0.0) -> bool:
    b = report.bootstrap
    # 統計的にはっきり悪化している、または平均の悪化が許容幅を超えたら止める
    return b.ci_high < 0 or b.diff < -tolerance
