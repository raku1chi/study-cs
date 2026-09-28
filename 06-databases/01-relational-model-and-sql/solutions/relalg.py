"""6.1 リレーショナルモデルとSQL — 演習1 解答例: 関係代数

演習の仕様は exercises/relalg.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any

Row = dict[str, Any]


# ---------------------------------------------------------------------------
# 提供済み: リレーションを表すクラス（スタブと同じ）
# ---------------------------------------------------------------------------

def _sort_key(values: tuple) -> tuple:
    # None（NULL）や型の混在があっても並べられるようにするためのキー
    return tuple((v is None, type(v).__name__, v if v is not None else 0) for v in values)


class Relation:
    def __init__(self, attributes: Sequence[str], rows: Iterable[Mapping[str, Any]] = ()) -> None:
        attrs = tuple(attributes)
        if len(set(attrs)) != len(attrs):
            raise ValueError(f"属性名が重複しています: {attrs}")
        self.attributes: tuple[str, ...] = attrs
        self.rows: list[Row] = []
        expected = set(attrs)
        for row in rows:
            if set(row) != expected:
                raise ValueError(f"行の属性 {sorted(row)} がスキーマ {list(attrs)} と一致しません")
            self.rows.append(dict(row))

    @classmethod
    def from_tuples(cls, attributes: Sequence[str], tuples: Iterable[Sequence[Any]]) -> Relation:
        attrs = tuple(attributes)
        return cls(attrs, (dict(zip(attrs, t, strict=True)) for t in tuples))

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows)

    def tuples(self, attributes: Sequence[str] | None = None) -> list[tuple]:
        order = tuple(attributes) if attributes is not None else self.attributes
        return sorted((tuple(r[a] for a in order) for r in self.rows), key=_sort_key)

    def as_set(self) -> frozenset[tuple]:
        order = sorted(self.attributes)
        return frozenset(tuple(r[a] for a in order) for r in self.rows)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Relation):
            return NotImplemented
        return set(self.attributes) == set(other.attributes) and self.as_set() == other.as_set()

    def __repr__(self) -> str:
        body = ", ".join(repr(t) for t in self.tuples()[:5])
        more = ", ..." if len(self.rows) > 5 else ""
        return f"Relation({list(self.attributes)}, [{body}{more}])"


# ---------------------------------------------------------------------------
# 演習1-1: 選択・射影・名前の変更
# ---------------------------------------------------------------------------

def _check_attributes(r: Relation, attributes: Iterable[str]) -> None:
    unknown = [a for a in attributes if a not in r.attributes]
    if unknown:
        raise ValueError(f"存在しない属性です: {unknown}（スキーマ: {list(r.attributes)}）")


def _dedupe(attributes: Sequence[str], rows: Iterable[Row]) -> Relation:
    """行の重複を取り除いて Relation を作る（出現順を保つ）。"""
    seen: set[tuple] = set()
    out: list[Row] = []
    for row in rows:
        key = tuple(row[a] for a in attributes)
        if key not in seen:
            seen.add(key)
            out.append(row)
    return Relation(attributes, out)


def select(r: Relation, predicate: Callable[[Row], bool]) -> Relation:
    # σ: 行を絞り込むだけ。スキーマは変わらない
    return Relation(r.attributes, (row for row in r.rows if predicate(row)))


def project(r: Relation, attributes: Sequence[str]) -> Relation:
    attrs = tuple(attributes)
    if not attrs:
        raise ValueError("射影する属性を 1 つ以上指定してください")
    if len(set(attrs)) != len(attrs):
        raise ValueError(f"属性名が重複しています: {attrs}")
    _check_attributes(r, attrs)
    # π: 列を絞ると重複した行が生まれうる。リレーションは集合なので重複を除く
    #    （SQL の SELECT は既定では重複を除かない。SELECT DISTINCT が π に相当する）
    return _dedupe(attrs, ({a: row[a] for a in attrs} for row in r.rows))


def rename(r: Relation, mapping: Mapping[str, str]) -> Relation:
    _check_attributes(r, mapping)
    new_attrs = tuple(mapping.get(a, a) for a in r.attributes)
    if len(set(new_attrs)) != len(new_attrs):
        raise ValueError(f"名前の変更後に属性名が重複します: {new_attrs}")
    return Relation(new_attrs, ({mapping.get(a, a): v for a, v in row.items()} for row in r.rows))


# ---------------------------------------------------------------------------
# 演習1-2: 直積・自然結合・θ結合
# ---------------------------------------------------------------------------

def cross(r: Relation, s: Relation) -> Relation:
    common = set(r.attributes) & set(s.attributes)
    if common:
        raise ValueError(f"直積では属性名が重複してはいけません（rename を使う）: {sorted(common)}")
    attrs = r.attributes + s.attributes
    return Relation(attrs, ({**a, **b} for a in r.rows for b in s.rows))


def natural_join(r: Relation, s: Relation) -> Relation:
    common = tuple(a for a in r.attributes if a in s.attributes)
    if not common:
        return cross(r, s)  # 共通の属性がなければ直積になる
    extra = tuple(a for a in s.attributes if a not in common)
    # ハッシュ結合: s を「共通属性の値 → 行のリスト」の辞書にしておき、r の各行で引く。
    # 入れ子ループ（|r|×|s| 回の比較）ではなく、|r| + |s| に比例する手間で済む（6.2 章）。
    table: dict[tuple, list[Row]] = {}
    for row in s.rows:
        key = tuple(row[a] for a in common)
        if any(v is None for v in key):
            continue  # NULL は何とも等しくない（SQL と同じ）ので、結合相手にならない
        table.setdefault(key, []).append(row)
    out: list[Row] = []
    for row in r.rows:
        key = tuple(row[a] for a in common)
        for match in table.get(key, ()):
            out.append({**row, **{a: match[a] for a in extra}})
    return Relation(r.attributes + extra, out)


def theta_join(r: Relation, s: Relation, predicate: Callable[[Row], bool]) -> Relation:
    # θ結合の定義そのもの: R ⋈θ S = σθ(R × S)
    return select(cross(r, s), predicate)


# ---------------------------------------------------------------------------
# 演習1-3: 集合演算
# ---------------------------------------------------------------------------

def _check_compatible(r: Relation, s: Relation) -> None:
    if set(r.attributes) != set(s.attributes):
        raise ValueError(
            f"和両立（union-compatible）ではありません: {list(r.attributes)} と {list(s.attributes)}"
        )


def union(r: Relation, s: Relation) -> Relation:
    _check_compatible(r, s)
    return _dedupe(r.attributes, [*r.rows, *s.rows])


def difference(r: Relation, s: Relation) -> Relation:
    _check_compatible(r, s)
    exclude = {tuple(row[a] for a in r.attributes) for row in s.rows}
    return _dedupe(r.attributes, (row for row in r.rows if tuple(row[a] for a in r.attributes) not in exclude))


def intersection(r: Relation, s: Relation) -> Relation:
    _check_compatible(r, s)
    keep = {tuple(row[a] for a in r.attributes) for row in s.rows}
    return _dedupe(r.attributes, (row for row in r.rows if tuple(row[a] for a in r.attributes) in keep))


# ---------------------------------------------------------------------------
# 演習1-4: グループ化と集約
# ---------------------------------------------------------------------------

AGGREGATE_FUNCTIONS = ("count", "sum", "avg", "min", "max")


def _aggregate(func: str, attr: str | None, rows: list[Row]) -> Any:
    if func == "count":
        if attr is None:
            return len(rows)  # COUNT(*): 行数
        return sum(1 for row in rows if row[attr] is not None)  # COUNT(列): NULL 以外の数
    values = [row[attr] for row in rows if row[attr] is not None]  # 集約関数は NULL を無視する
    if not values:
        return None  # SUM/AVG/MIN/MAX は対象が 0 件なら NULL（0 ではない）
    if func == "sum":
        return sum(values)
    if func == "avg":
        return sum(values) / len(values)
    if func == "min":
        return min(values)
    return max(values)


def group_by(
    r: Relation,
    keys: Sequence[str],
    aggregates: Mapping[str, tuple[str, str | None]],
) -> Relation:
    keys = tuple(keys)
    _check_attributes(r, keys)
    for name, (func, attr) in aggregates.items():
        if func not in AGGREGATE_FUNCTIONS:
            raise ValueError(f"未対応の集約関数です: {func}")
        if attr is None and func != "count":
            raise ValueError(f"{func} には属性の指定が必要です")
        if attr is not None:
            _check_attributes(r, [attr])
    out_attrs = keys + tuple(aggregates)
    if len(set(out_attrs)) != len(out_attrs):
        raise ValueError(f"出力の属性名が重複しています: {out_attrs}")

    # グループキーの値ごとに行をまとめる（dict は挿入順を保つので結果も出現順になる）
    groups: dict[tuple, list[Row]] = {}
    for row in r.rows:
        groups.setdefault(tuple(row[k] for k in keys), []).append(row)
    if not keys and not groups:
        # GROUP BY なしの集約は、入力が 0 行でも必ず 1 行を返す（SQL と同じ）
        groups[()] = []

    out: list[Row] = []
    for key, rows in groups.items():
        row = dict(zip(keys, key))
        for name, (func, attr) in aggregates.items():
            row[name] = _aggregate(func, attr, rows)
        out.append(row)
    return Relation(out_attrs, out)


# ---------------------------------------------------------------------------
# 演習1-5: 演算を組み合わせて問い合わせを書く
# ---------------------------------------------------------------------------

def customers_who_bought(db: Mapping[str, Relation], category_id: int) -> Relation:
    # 関係代数で書くと:
    #   π_name( π_product_id(σ_category_id=c(products))
    #           ⋈ π_order_id,product_id(order_items)
    #           ⋈ π_order_id,customer_id(σ_status≠'cancelled'(orders))
    #           ⋈ π_customer_id,name(customers) )
    # products と customers はどちらも name 属性を持つので、射影せずに自然結合すると
    # 「商品名 = 顧客名」という意図しない条件まで結合条件に入ってしまう。
    products = project(select(db["products"], lambda p: p["category_id"] == category_id), ["product_id"])
    items = project(db["order_items"], ["order_id", "product_id"])
    orders = project(select(db["orders"], lambda o: o["status"] != "cancelled"), ["order_id", "customer_id"])
    customers = project(db["customers"], ["customer_id", "name"])
    joined = natural_join(natural_join(natural_join(products, items), orders), customers)
    return project(joined, ["name"])
