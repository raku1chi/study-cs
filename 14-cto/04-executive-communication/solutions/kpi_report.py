"""14.4 経営陣・取締役会・投資家とのコミュニケーション — 解答例（kpi_report.py）

指標ごとの実績・目標・向き・黄の幅から信号（赤・黄・緑）と傾向を判定し、
「例外（赤・黄）を先に」並べた 1 ページの経営向けサマリーを Markdown で出力します。
演習の仕様は exercises/kpi_report.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

STATUS_LABEL = {"red": "赤", "amber": "黄", "green": "緑"}
TREND_LABEL = {"improving": "改善", "worsening": "悪化", "flat": "横ばい", "n/a": "—"}


@dataclass(frozen=True)
class Metric:
    name: str
    value: float
    target: float
    higher_is_better: bool = True
    amber_band: float = 0.0          # 目標からこの幅までの未達は「黄」（指標の単位で）
    previous: float | None = None    # 前期の値
    unit: str = ""
    category: str = ""
    noise: float = 0.0               # この幅以内の変化は「横ばい」とみなす（指標の単位で）


def rag_status(metric: Metric) -> str:
    if metric.amber_band < 0:
        raise ValueError(f"amber_band は 0 以上です: {metric.name}")
    if metric.higher_is_better:
        # 大きいほど良い指標: 目標以上で緑、目標 − 幅 以上で黄
        if metric.value >= metric.target:
            return "green"
        if metric.value >= metric.target - metric.amber_band:
            return "amber"
        return "red"
    # 小さいほど良い指標: 目標以下で緑、目標 + 幅 以下で黄
    if metric.value <= metric.target:
        return "green"
    if metric.value <= metric.target + metric.amber_band:
        return "amber"
    return "red"


def trend(metric: Metric) -> str:
    if metric.noise < 0:
        raise ValueError(f"noise は 0 以上です: {metric.name}")
    if metric.previous is None:
        return "n/a"
    delta = metric.value - metric.previous
    if abs(delta) <= metric.noise:
        return "flat"
    # 「増えた」ことが良いかどうかは指標の向きで決まる
    better = delta > 0 if metric.higher_is_better else delta < 0
    return "improving" if better else "worsening"


def overall_status(metrics: Sequence[Metric]) -> str:
    if not metrics:
        raise ValueError("指標がありません")
    statuses = {rag_status(m) for m in metrics}
    # 最も悪い信号が全体の信号（1 つでも赤があれば全体は赤）
    for status in ("red", "amber"):
        if status in statuses:
            return status
    return "green"


def format_value(value: float, unit: str = "") -> str:
    if float(value).is_integer():
        text = f"{value:,.0f}"
    else:
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def _trend_text(metric: Metric) -> str:
    t = trend(metric)
    if t == "n/a":
        return TREND_LABEL[t]
    return f"{TREND_LABEL[t]}（前期 {format_value(metric.previous, metric.unit)}）"


def render_report(title: str, period: str, metrics: Sequence[Metric]) -> str:
    overall = overall_status(metrics)
    statuses = [rag_status(m) for m in metrics]
    counts = {s: statuses.count(s) for s in ("red", "amber", "green")}
    lines = [
        f"# {title}（{period}）",
        "",
        f"**総合: {STATUS_LABEL[overall]}**（赤 {counts['red']} / 黄 {counts['amber']} / 緑 {counts['green']}）",
        "",
        "## 要対応・要注意（赤・黄）",
        "",
    ]
    # 例外を先に: 赤 → 黄の順。同じ信号の中では入力の順を保つ
    exceptions = [m for s in ("red", "amber") for m, st in zip(metrics, statuses) if st == s]
    if exceptions:
        lines.append("| 状態 | 区分 | 指標 | 実績 | 目標 | 傾向 |")
        lines.append("|---|---|---|---|---|---|")
        for m in exceptions:
            lines.append(
                f"| {STATUS_LABEL[rag_status(m)]} | {m.category} | {m.name} | "
                f"{format_value(m.value, m.unit)} | {format_value(m.target, m.unit)} | {_trend_text(m)} |"
            )
    else:
        lines.append("赤・黄の指標はありません。")
    lines += ["", "## 全指標", "", "| 区分 | 指標 | 状態 | 実績 | 目標 | 傾向 |", "|---|---|---|---|---|---|"]
    for m, st in zip(metrics, statuses):
        lines.append(
            f"| {m.category} | {m.name} | {STATUS_LABEL[st]} | "
            f"{format_value(m.value, m.unit)} | {format_value(m.target, m.unit)} | {_trend_text(m)} |"
        )
    return "\n".join(lines) + "\n"


def sample_metrics() -> list[Metric]:
    """本文 3.4 節の例。"""
    return [
        Metric("変更のリードタイム（中央値）", 30, 24, False, 6, 36, "時間", "デリバリー", 1),
        Metric("ロードマップ達成率", 70, 80, True, 5, 78, "%", "デリバリー", 2),
        Metric("可用性（主要 API）", 99.95, 99.9, True, 0.05, 99.82, "%", "信頼性", 0.01),
        Metric("重大インシデント", 3, 2, False, 1, 5, "件", "信頼性"),
        Metric("重大な脆弱性の修正日数（中央値）", 9, 14, False, 3, 12, "日", "セキュリティ", 1),
        Metric("多要素認証の適用率", 100, 100, True, 1, 97, "%", "セキュリティ"),
        Metric("採用計画の達成率", 60, 90, True, 10, 70, "%", "人と組織", 5),
        Metric("惜しまれる離職（年率）", 6, 8, False, 2, 7, "%", "人と組織", 0.5),
        Metric("売上に対するクラウド費用", 13.5, 12, False, 2, 12.8, "%", "コスト", 0.2),
    ]


if __name__ == "__main__":
    print(render_report("技術 KPI サマリー", "2026 年度 第 2 四半期", sample_metrics()), end="")
