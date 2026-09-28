"""6.1 リレーショナルモデルとSQL — 演習1: 関係代数を実装する

SQL の裏にある「関係代数（relational algebra）」の演算を、Python の dict のリストで実装します。
各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.1          # この章の全演習の合格数を表示
    python3 tools/check.py -v 6.1       # 各テストの結果を詳しく表示

このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_relalg

約束ごと:
    - リレーションは `Relation`（下で提供済み）で表す。属性名の並び（スキーマ）と、行（dict）のリスト。
    - 値 None は SQL の NULL とみなす。
    - 演算は入力を書き換えず、新しい Relation を返す。
    - リレーションは本来「集合」なので、射影（project）と集合演算は結果から重複行を取り除く。
      それ以外の演算は、入力に重複がなければ結果にも重複は生じない。
    - 結果の行の順序は問わない（テストは集合として比較する）。
"""
from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import Any

Row = dict[str, Any]


# ---------------------------------------------------------------------------
# 提供済み: リレーションを表すクラス（このクラスは変更しなくてよい）
# ---------------------------------------------------------------------------

def _sort_key(values: tuple) -> tuple:
    # None（NULL）や型の混在があっても並べられるようにするためのキー
    return tuple((v is None, type(v).__name__, v if v is not None else 0) for v in values)


class Relation:
    """リレーション（関係）。

    - attributes: 属性名のタプル（スキーマ）。重複した属性名は ValueError。
    - rows: 行のリスト。各行は「ちょうどスキーマの属性をキーに持つ dict」（過不足があれば ValueError）。

    コンストラクタは行の重複を取り除かない（SQL のテーブルと同じ「バッグ」）。
    2 つの Relation の `==` は、属性名の集合と行の集合が等しいかで判定する（属性や行の順序は無視）。

    >>> r = Relation.from_tuples(["id", "name"], [(1, "Alice"), (2, "Bob")])
    >>> r.attributes
    ('id', 'name')
    >>> r.rows[0]
    {'id': 1, 'name': 'Alice'}
    >>> r.tuples(["name"])
    [('Alice',), ('Bob',)]
    """

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
        """属性名の並びと、値のタプルの列から Relation を作る。"""
        attrs = tuple(attributes)
        return cls(attrs, (dict(zip(attrs, t, strict=True)) for t in tuples))

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self.rows)

    def tuples(self, attributes: Sequence[str] | None = None) -> list[tuple]:
        """行を（指定した属性の順の）タプルにし、ソートしたリストで返す。表示や比較に便利。"""
        order = tuple(attributes) if attributes is not None else self.attributes
        return sorted((tuple(r[a] for a in order) for r in self.rows), key=_sort_key)

    def as_set(self) -> frozenset[tuple]:
        """行を「属性名のアルファベット順に並べた値のタプル」の集合にする。"""
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
# 演習1-1（★☆☆）: 選択・射影・名前の変更
# ---------------------------------------------------------------------------

def select(r: Relation, predicate: Callable[[Row], bool]) -> Relation:
    """選択 σ: predicate(row) が True になる行だけを残す。スキーマは変わらない。

    SQL の WHERE 句に相当する。

    >>> r = Relation.from_tuples(["id", "age"], [(1, 20), (2, 35)])
    >>> select(r, lambda row: row["age"] >= 30).tuples()
    [(2, 35)]
    """
    raise NotImplementedError("演習1-1: select を実装してください")


def project(r: Relation, attributes: Sequence[str]) -> Relation:
    """射影 π: 指定した属性だけを、指定した順に残し、重複した行を取り除く。

    SQL の SELECT DISTINCT 列, ... に相当する（DISTINCT を付けない SELECT は重複を残す）。

    - attributes が空、属性名が重複している、存在しない属性を含む場合は ValueError。

    >>> r = Relation.from_tuples(["id", "city"], [(1, "Tokyo"), (2, "Osaka"), (3, "Tokyo")])
    >>> project(r, ["city"]).tuples()
    [('Osaka',), ('Tokyo',)]
    """
    raise NotImplementedError("演習1-1: project を実装してください")


def rename(r: Relation, mapping: Mapping[str, str]) -> Relation:
    """名前の変更 ρ: mapping（旧名 → 新名）に従って属性名を変える。値は変わらない。

    SQL の AS（列の別名・テーブルの別名）に相当する。自己結合の前に使う。

    - mapping に存在しない属性名があれば ValueError。
    - 変更後の属性名が重複する場合も ValueError。
    - 属性の並び順は元のまま（名前だけ変わる）。

    >>> r = Relation.from_tuples(["id", "boss"], [(2, 1)])
    >>> rename(r, {"id": "emp_id"}).attributes
    ('emp_id', 'boss')
    """
    raise NotImplementedError("演習1-1: rename を実装してください")


# ---------------------------------------------------------------------------
# 演習1-2（★★☆）: 直積・自然結合・θ結合
# ---------------------------------------------------------------------------

def cross(r: Relation, s: Relation) -> Relation:
    """直積 ×: r のすべての行と s のすべての行の組み合わせ。

    - 結果のスキーマは r の属性の後に s の属性を並べたもの。
    - r と s に同じ名前の属性があれば ValueError（先に rename で名前を変えること）。
    - 結果の行数は len(r) * len(s)。SQL の CROSS JOIN に相当する。
    """
    raise NotImplementedError("演習1-2: cross を実装してください")


def natural_join(r: Relation, s: Relation) -> Relation:
    """自然結合 ⋈: 同じ名前の属性（共通属性）の値がすべて等しい行どうしを結合する。

    - 結果のスキーマは「r の属性」の後に「s の属性のうち共通でないもの」を s の順に並べたもの。
    - 共通属性が 1 つもなければ、直積 cross(r, s) と同じ結果になる。
    - 共通属性の値に None（NULL）を含む行は、どの行とも一致しない（SQL の NULL = NULL が
      真にならないのと同じ）。

    >>> emp = Relation.from_tuples(["name", "dept_id"], [("Alice", 1), ("Bob", 2), ("Carol", None)])
    >>> dept = Relation.from_tuples(["dept_id", "dept"], [(1, "Sales"), (2, "Dev")])
    >>> natural_join(emp, dept).tuples()
    [('Alice', 1, 'Sales'), ('Bob', 2, 'Dev')]

    ヒント: s の行を「共通属性の値のタプル → 行のリスト」の dict にしてから r の各行で引くと、
    |r|×|s| 回の比較をせずに済む（ハッシュ結合。6.2 章で詳しく扱う）。
    """
    raise NotImplementedError("演習1-2: natural_join を実装してください")


def theta_join(r: Relation, s: Relation, predicate: Callable[[Row], bool]) -> Relation:
    """θ結合: 直積の各行（r の行と s の行をつないだ dict）のうち、predicate が True のものを残す。

    定義は R ⋈θ S = σθ(R × S)。SQL の JOIN ... ON 条件 に相当する。
    属性名の重複は cross と同じく ValueError（自己結合では先に rename する）。

    >>> a = Relation.from_tuples(["x"], [(1,), (5,)])
    >>> b = Relation.from_tuples(["y"], [(3,)])
    >>> theta_join(a, b, lambda row: row["x"] < row["y"]).tuples()
    [(1, 3)]
    """
    raise NotImplementedError("演習1-2: theta_join を実装してください")


# ---------------------------------------------------------------------------
# 演習1-3（★☆☆）: 集合演算（和・差・共通部分）
# ---------------------------------------------------------------------------

def union(r: Relation, s: Relation) -> Relation:
    """和 ∪: r と s のどちらかに含まれる行。重複は取り除く（SQL の UNION。UNION ALL ではない）。

    - r と s の属性名の集合が異なる（和両立でない）場合は ValueError。
      属性の並び順が違うだけなら許し、結果は r の並び順にする。
    """
    raise NotImplementedError("演習1-3: union を実装してください")


def difference(r: Relation, s: Relation) -> Relation:
    """差 −: r に含まれ、s に含まれない行（SQL の EXCEPT）。和両立でなければ ValueError。"""
    raise NotImplementedError("演習1-3: difference を実装してください")


def intersection(r: Relation, s: Relation) -> Relation:
    """共通部分 ∩: r と s の両方に含まれる行（SQL の INTERSECT）。和両立でなければ ValueError。

    ちなみに r ∩ s = r − (r − s) なので、∩ は基本演算ではない。
    """
    raise NotImplementedError("演習1-3: intersection を実装してください")


# ---------------------------------------------------------------------------
# 演習1-4（★★☆）: グループ化と集約（拡張関係代数の γ）
# ---------------------------------------------------------------------------

AGGREGATE_FUNCTIONS = ("count", "sum", "avg", "min", "max")


def group_by(
    r: Relation,
    keys: Sequence[str],
    aggregates: Mapping[str, tuple[str, str | None]],
) -> Relation:
    """グループ化と集約 γ: keys の値ごとに行をまとめ、集約関数を計算する。

    aggregates は「出力する属性名 → (関数名, 対象の属性名)」の dict。関数名は
    "count" / "sum" / "avg" / "min" / "max" のいずれか。
    結果のスキーマは keys の後に aggregates のキーを（dict の順に）並べたもの。

    SQL と同じ NULL の扱いにすること:
    - ("count", None) は行数（COUNT(*)）。("count", "列") は None でない値の数（COUNT(列)）。
    - sum / avg / min / max は None を無視する。対象の値が 1 つもなければ結果は None。
    - keys が空（GROUP BY なし）のときは、r が 0 行でも必ず 1 行を返す
      （例: count は 0、sum は None）。keys が空でなく r が 0 行なら、結果も 0 行。

    エラー（ValueError）:
    - keys や対象の属性がスキーマにない
    - 未対応の関数名、count 以外で対象の属性が None
    - 出力の属性名が重複する（keys と aggregates のキーが衝突するなど）

    >>> sales = Relation.from_tuples(["shop", "amount"], [("A", 100), ("A", None), ("B", 50)])
    >>> group_by(sales, ["shop"], {"n": ("count", None), "n_amount": ("count", "amount"),
    ...                            "total": ("sum", "amount")}).tuples()
    [('A', 2, 1, 100), ('B', 1, 1, 50)]
    """
    raise NotImplementedError("演習1-4: group_by を実装してください")


# ---------------------------------------------------------------------------
# 演習1-5（★★☆）: 演算を組み合わせて問い合わせを書く
# ---------------------------------------------------------------------------

def customers_who_bought(db: Mapping[str, Relation], category_id: int) -> Relation:
    """カテゴリ category_id の商品を、キャンセルされていない注文で買った顧客の名前。

    db は EC サイトの各テーブルを Relation にした dict（キーは "customers", "orders",
    "order_items", "products" など。スキーマは data/ecommerce.sql と同じ）。
    結果は属性 ("name",) だけを持つ Relation（重複なし）。

    ここまでに実装した演算（select / project / natural_join など）を組み合わせて書くこと。
    SQL で書くと次の問い合わせに相当する:

        SELECT DISTINCT c.name
        FROM products AS p
        JOIN order_items AS oi ON oi.product_id = p.product_id
        JOIN orders AS o       ON o.order_id = oi.order_id
        JOIN customers AS c    ON c.customer_id = o.customer_id
        WHERE p.category_id = :category_id AND o.status <> 'cancelled';

    注意: products にも customers にも name 属性がある。そのまま自然結合すると何が起きるか？
    """
    raise NotImplementedError("演習1-5: customers_who_bought を実装してください")
