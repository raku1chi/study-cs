"""13.5 育成・評価・キャリアラダー — 解答例: 給与レンジ（バンド）の設計と昇給予算

演習の仕様は exercises/comp_bands.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Band:
    level: str
    minimum: float
    midpoint: float
    maximum: float


@dataclass(frozen=True)
class Employee:
    name: str
    level: str
    salary: float
    rating: str


@dataclass(frozen=True)
class Adjustment:
    name: str
    old_salary: float
    merit: float
    catch_up: float
    lump_sum: float
    new_salary: float


# ---------------------------------------------------------------------------
# 演習3: バンドの設計
# ---------------------------------------------------------------------------

def _per_level(value: float | list[float], count: int, what: str) -> list[float]:
    values = [value] * count if isinstance(value, (int, float)) else list(value)
    if len(values) != count:
        raise ValueError(f"{what} の個数が合いません: {len(values)} != {count}")
    return [float(v) for v in values]


def build_bands(
    base_midpoint: float,
    levels: list[str],
    progression: float | list[float],
    spread: float | list[float],
) -> list[Band]:
    if base_midpoint <= 0:
        raise ValueError("base_midpoint は正の値にしてください")
    if not levels or len(set(levels)) != len(levels):
        raise ValueError("levels は空でない、重複のないリストにしてください")
    progressions = _per_level(progression, len(levels) - 1, "progression")
    spreads = _per_level(spread, len(levels), "spread")
    if any(p <= 0 for p in progressions) or any(s < 0 for s in spreads):
        raise ValueError("progression は正、spread は 0 以上にしてください")

    bands = []
    mid = float(base_midpoint)
    for i, level in enumerate(levels):
        if i > 0:
            mid *= 1 + progressions[i - 1]  # 中央値の等級間の上昇率
        s = spreads[i]
        # レンジの幅 spread = (max - min) / min、中央値 = (min + max) / 2 から
        # min = 2 * mid / (2 + spread)、max = min * (1 + spread)
        minimum = 2 * mid / (2 + s)
        bands.append(Band(level, minimum, mid, minimum * (1 + s)))
    return bands


def band_overlap(lower: Band, upper: Band) -> float:
    width = lower.maximum - lower.minimum
    if width <= 0:
        raise ValueError("下位のバンドの幅が 0 です")
    return max(0.0, lower.maximum - upper.minimum) / width


# ---------------------------------------------------------------------------
# 演習3（続き）: 個人の位置づけ
# ---------------------------------------------------------------------------

def compa_ratio(salary: float, band: Band) -> float:
    return salary / band.midpoint


def range_penetration(salary: float, band: Band) -> float:
    width = band.maximum - band.minimum
    if width <= 0:
        raise ValueError("バンドの幅が 0 です")
    return (salary - band.minimum) / width


def _band_map(bands: list[Band]) -> dict[str, Band]:
    return {b.level: b for b in bands}


def out_of_band(employees: list[Employee], bands: list[Band]) -> list[tuple[str, str, float]]:
    by_level = _band_map(bands)
    result = []
    for e in employees:
        if e.level not in by_level:
            raise ValueError(f"{e.name}: 等級 {e.level} のバンドがありません")
        band = by_level[e.level]
        if e.salary < band.minimum:
            result.append((e.name, "below", band.minimum - e.salary))
        elif e.salary > band.maximum:
            result.append((e.name, "above", e.salary - band.maximum))
    return result


# ---------------------------------------------------------------------------
# 演習4: メリットマトリクスによる昇給と予算
# ---------------------------------------------------------------------------

def _zone(cr: float, edges: list[float]) -> int:
    # edges = [0.9, 1.1] なら、0.9 未満 → 0、0.9 以上 1.1 未満 → 1、1.1 以上 → 2
    zone = 0
    for edge in edges:
        if cr >= edge:
            zone += 1
    return zone


def merit_adjustments(
    employees: list[Employee],
    bands: list[Band],
    matrix: dict[str, list[float]],
    zone_edges: list[float] | None = None,
) -> list[Adjustment]:
    edges = [0.9, 1.1] if zone_edges is None else list(zone_edges)
    if edges != sorted(edges) or len(set(edges)) != len(edges):
        raise ValueError("zone_edges は狭義の昇順にしてください")
    by_level = _band_map(bands)
    result = []
    for e in employees:
        if e.level not in by_level:
            raise ValueError(f"{e.name}: 等級 {e.level} のバンドがありません")
        if e.rating not in matrix:
            raise ValueError(f"{e.name}: 評価 {e.rating} がマトリクスにありません")
        row = matrix[e.rating]
        if len(row) != len(edges) + 1:
            raise ValueError(f"評価 {e.rating} の昇給率の個数がゾーンの数と合いません")
        band = by_level[e.level]
        # 同じ評価でも、レンジの中で低い位置にいる人ほど昇給率を高くする（市場との差を縮める）
        merit = e.salary * row[_zone(compa_ratio(e.salary, band), edges)]
        tentative = e.salary + merit
        catch_up = lump_sum = 0.0
        if tentative < band.minimum:
            # 昇給後もレンジの下限に届かなければ、下限まで引き上げる
            catch_up = band.minimum - tentative
            new_salary = band.minimum
        else:
            cap = max(band.maximum, e.salary)  # すでに上限を超えている人の基本給は下げない
            if tentative > cap:
                # 上限を超える分は基本給に入れず、一時金として支払う
                lump_sum = tentative - cap
                new_salary = cap
            else:
                new_salary = tentative
        result.append(Adjustment(e.name, e.salary, merit, catch_up, lump_sum, new_salary))
    return result


def budget_summary(adjustments: list[Adjustment]) -> dict[str, float]:
    payroll = sum(a.old_salary for a in adjustments)
    if payroll <= 0:
        raise ValueError("給与の合計が 0 です")
    base_increase = sum(a.new_salary - a.old_salary for a in adjustments)
    lump = sum(a.lump_sum for a in adjustments)
    return {
        "payroll": payroll,
        "base_increase": base_increase,
        "lump_sum": lump,
        "total_cost": base_increase + lump,
        "increase_rate": base_increase / payroll,
    }
