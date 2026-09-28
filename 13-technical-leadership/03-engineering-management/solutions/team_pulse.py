"""13.3 エンジニアリングマネジメントの基礎 — 解答例: チームのサーベイ結果の分析

演習の仕様は exercises/team_pulse.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

ENTIRE_ORG = "全体"


@dataclass(frozen=True)
class Response:
    team: str
    period: str
    enps: int | None = None
    items: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class TeamSummary:
    n: int
    enps: float | None
    item_means: dict[str, float]


# ---------------------------------------------------------------------------
# 演習1: eNPS と好意的回答率
# ---------------------------------------------------------------------------

def _check_scale(scores: list[int], lo: int, hi: int) -> None:
    if not scores:
        raise ValueError("回答が 0 件です")
    for s in scores:
        # bool は int のサブクラスなので明示的に除く
        if isinstance(s, bool) or not isinstance(s, int) or not lo <= s <= hi:
            raise ValueError(f"{lo}〜{hi} の整数ではありません: {s!r}")


def enps(scores: list[int]) -> float:
    _check_scale(scores, 0, 10)
    promoters = sum(1 for s in scores if s >= 9)   # 推奨者: 9〜10
    detractors = sum(1 for s in scores if s <= 6)  # 批判者: 0〜6（7〜8 は中立で、どちらにも数えない）
    # 割合の差を先に計算すると 0.3 * 100 = 30.000000000000004 のような誤差が出るので、
    # 人数の差を先に取ってから割る
    return (promoters - detractors) * 100 / len(scores)


def favorability(scores: list[int]) -> float:
    _check_scale(scores, 1, 5)
    return sum(1 for s in scores if s >= 4) * 100 / len(scores)


# ---------------------------------------------------------------------------
# 演習2: 設問ごとの平均・低スコアの設問・期ごとの推移
# ---------------------------------------------------------------------------

def item_means(responses: list[Response]) -> dict[str, float]:
    totals: dict[str, int] = {}
    counts: dict[str, int] = {}
    for r in responses:
        for item, score in r.items.items():
            _check_scale([score], 1, 5)
            totals[item] = totals.get(item, 0) + score
            counts[item] = counts.get(item, 0) + 1
    return {item: totals[item] / counts[item] for item in sorted(totals)}


def low_scoring_items(responses: list[Response], threshold: float = 3.5) -> list[tuple[str, float]]:
    means = item_means(responses)
    low = [(item, m) for item, m in means.items() if m < threshold]
    return sorted(low, key=lambda x: (x[1], x[0]))


def period_trend(responses: list[Response], metric: str = "enps") -> list[tuple[str, float, float | None]]:
    by_period: dict[str, list[int]] = {}
    for r in responses:
        if metric == "enps":
            if r.enps is not None:
                by_period.setdefault(r.period, []).append(r.enps)
        elif metric in r.items:
            by_period.setdefault(r.period, []).append(r.items[metric])

    result: list[tuple[str, float, float | None]] = []
    previous: float | None = None
    for period in sorted(by_period):
        values = by_period[period]
        value = enps(values) if metric == "enps" else sum(values) / len(values)
        change = None if previous is None else value - previous
        result.append((period, value, change))
        previous = value
    return result


# ---------------------------------------------------------------------------
# 演習3: 匿名性を守る集計（小さなグループの秘匿と二次秘匿）
# ---------------------------------------------------------------------------

def suppress_small_groups(counts: dict[str, int], min_responses: int = 5) -> set[str]:
    if min_responses < 1:
        raise ValueError("min_responses は 1 以上にしてください")
    for name, n in counts.items():
        if n < 0:
            raise ValueError(f"回答数が負です: {name}={n}")

    # 一次秘匿: 回答数がしきい値未満のグループ（0 件のグループは出す情報がないので対象外）
    suppressed = {name for name, n in counts.items() if 0 < n < min_responses}
    # 二次秘匿: 全体の数値が公開されていると「全体 − 公開したグループ」で秘匿した部分が逆算できる。
    # 逆算できる部分（秘匿したグループの合計）もしきい値以上になるまで、小さいグループから追加する
    remaining = sorted((n, name) for name, n in counts.items() if n > 0 and name not in suppressed)
    while suppressed and sum(counts[name] for name in suppressed) < min_responses and remaining:
        _, name = remaining.pop(0)
        suppressed.add(name)
    return suppressed


def _summarize(responses: list[Response]) -> TeamSummary:
    enps_scores = [r.enps for r in responses if r.enps is not None]
    return TeamSummary(
        n=len(responses),
        enps=enps(enps_scores) if enps_scores else None,
        item_means=item_means(responses),
    )


def team_report(
    responses: list[Response], period: str, min_responses: int = 5
) -> dict[str, TeamSummary | None]:
    in_period = [r for r in responses if r.period == period]
    by_team: dict[str, list[Response]] = {}
    for r in in_period:
        by_team.setdefault(r.team, []).append(r)
    if ENTIRE_ORG in by_team:
        raise ValueError(f"チーム名に {ENTIRE_ORG!r} は使えません")

    hidden = suppress_small_groups({t: len(rs) for t, rs in by_team.items()}, min_responses)
    report: dict[str, TeamSummary | None] = {}
    for team in sorted(by_team):
        report[team] = None if team in hidden else _summarize(by_team[team])
    report[ENTIRE_ORG] = _summarize(in_period) if len(in_period) >= min_responses else None
    return report
