"""6.1 演習1（関係代数）のテスト

実行: python3 tools/check.py 6.1   （またはこのディレクトリで python3 -m unittest -v test_relalg）
"""
import random
import sqlite3
import unittest
from pathlib import Path

from relalg import (
    Relation,
    cross,
    customers_who_bought,
    difference,
    group_by,
    intersection,
    natural_join,
    project,
    rename,
    select,
    theta_join,
    union,
)

DATA = Path(__file__).parent / "data" / "ecommerce.sql"

EMP = Relation.from_tuples(
    ["emp_id", "name", "dept_id", "boss_id", "salary"],
    [
        (1, "Alice", 10, None, 900),
        (2, "Bob", 10, 1, 500),
        (3, "Carol", 20, 1, 700),
        (4, "Dave", 20, 3, 500),
        (5, "Eve", None, 3, 400),
    ],
)
DEPT = Relation.from_tuples(["dept_id", "dept_name"], [(10, "Sales"), (20, "Dev"), (30, "HR")])


def load_ecommerce() -> dict[str, Relation]:
    conn = sqlite3.connect(":memory:")
    conn.executescript(DATA.read_text(encoding="utf-8"))
    db = {}
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        cur = conn.execute(f"SELECT * FROM {table}")
        attrs = [d[0] for d in cur.description]
        db[table] = Relation.from_tuples(attrs, cur.fetchall())
    conn.close()
    return db


class TestProvidedRelation(unittest.TestCase):
    """提供済みの Relation クラスの動作確認（学習者が変更しなくても通る）。"""

    def test_schema_validation(self):
        with self.assertRaises(ValueError):
            Relation(["a", "a"])
        with self.assertRaises(ValueError):
            Relation(["a", "b"], [{"a": 1}])

    def test_equality_ignores_order(self):
        r1 = Relation.from_tuples(["a", "b"], [(1, 2), (3, 4)])
        r2 = Relation.from_tuples(["b", "a"], [(4, 3), (2, 1)])
        self.assertEqual(r1, r2)


class TestSelectProjectRename(unittest.TestCase):
    def test_select(self):
        r = select(EMP, lambda row: row["salary"] >= 700)
        self.assertEqual(r.attributes, EMP.attributes)
        self.assertEqual(r.tuples(["name"]), [("Alice",), ("Carol",)])

    def test_select_does_not_modify_input(self):
        before = EMP.tuples()
        select(EMP, lambda row: False)
        self.assertEqual(EMP.tuples(), before)

    def test_select_empty_result_keeps_schema(self):
        r = select(EMP, lambda row: row["salary"] > 10_000)
        self.assertEqual(len(r), 0)
        self.assertEqual(r.attributes, EMP.attributes)

    def test_project_removes_duplicates(self):
        r = project(EMP, ["salary"])
        self.assertEqual(r.attributes, ("salary",))
        self.assertEqual(r.tuples(), [(400,), (500,), (700,), (900,)], "射影は重複行を取り除くこと（集合）")

    def test_project_keeps_requested_order(self):
        r = project(EMP, ["salary", "name"])
        self.assertEqual(r.attributes, ("salary", "name"))
        self.assertEqual(len(r), 5)

    def test_project_null_values_are_kept_and_deduplicated(self):
        r = Relation.from_tuples(["a", "b"], [(1, None), (2, None), (3, 5)])
        self.assertEqual(project(r, ["b"]).tuples(), [(5,), (None,)])

    def test_project_errors(self):
        for bad in ([], ["nope"], ["name", "name"]):
            with self.assertRaises(ValueError, msg=str(bad)):
                project(EMP, bad)

    def test_rename(self):
        r = rename(EMP, {"emp_id": "id", "name": "emp_name"})
        self.assertEqual(r.attributes, ("id", "emp_name", "dept_id", "boss_id", "salary"))
        self.assertEqual(r.tuples(["emp_name"])[0], ("Alice",))

    def test_rename_errors(self):
        with self.assertRaises(ValueError):
            rename(EMP, {"nope": "x"})
        with self.assertRaises(ValueError, msg="名前の変更後に属性名が重複するなら ValueError"):
            rename(EMP, {"name": "salary"})


class TestJoins(unittest.TestCase):
    def test_cross_product(self):
        r = cross(project(EMP, ["name"]), DEPT)
        self.assertEqual(r.attributes, ("name", "dept_id", "dept_name"))
        self.assertEqual(len(r), 5 * 3)

    def test_cross_requires_distinct_attribute_names(self):
        with self.assertRaises(ValueError):
            cross(EMP, DEPT)  # dept_id が重複

    def test_natural_join(self):
        r = natural_join(EMP, DEPT)
        self.assertEqual(r.attributes, EMP.attributes + ("dept_name",))
        self.assertEqual(
            r.tuples(["name", "dept_name"]),
            [("Alice", "Sales"), ("Bob", "Sales"), ("Carol", "Dev"), ("Dave", "Dev")],
            "dept_id が NULL の Eve は結合されず、社員のいない HR も現れないこと",
        )

    def test_natural_join_on_multiple_attributes(self):
        r = Relation.from_tuples(["a", "b", "x"], [(1, 1, "p"), (1, 2, "q"), (2, 2, "r")])
        s = Relation.from_tuples(["b", "a", "y"], [(1, 1, "P"), (2, 1, "Q"), (2, 3, "R")])
        j = natural_join(r, s)
        self.assertEqual(j.attributes, ("a", "b", "x", "y"))
        self.assertEqual(j.tuples(), [(1, 1, "p", "P"), (1, 2, "q", "Q")])

    def test_natural_join_null_never_matches(self):
        r = Relation.from_tuples(["k", "x"], [(None, 1), (1, 2)])
        s = Relation.from_tuples(["k", "y"], [(None, 3), (1, 4)])
        self.assertEqual(natural_join(r, s).tuples(), [(1, 2, 4)])

    def test_natural_join_without_common_attributes_is_cross(self):
        a = Relation.from_tuples(["x"], [(1,), (2,)])
        b = Relation.from_tuples(["y"], [("a",), ("b",), ("c",)])
        self.assertEqual(natural_join(a, b), cross(a, b))

    def test_natural_join_one_to_many_and_many_to_many(self):
        r = Relation.from_tuples(["k", "x"], [(1, "a"), (1, "b"), (2, "c")])
        s = Relation.from_tuples(["k", "y"], [(1, "A"), (1, "B"), (3, "C")])
        self.assertEqual(len(natural_join(r, s)), 4, "k=1 は 2 行 × 2 行 = 4 行になる")

    def test_natural_join_matches_bruteforce_on_random_data(self):
        rng = random.Random(61)
        for _ in range(30):
            r = Relation.from_tuples(
                ["k", "x"], {(rng.choice([None, 1, 2, 3, 4]), rng.randrange(100)) for _ in range(rng.randrange(0, 15))}
            )
            s = Relation.from_tuples(
                ["y", "k"], {(rng.randrange(100), rng.choice([None, 1, 2, 3, 5])) for _ in range(rng.randrange(0, 15))}
            )
            expected = {
                (a["k"], a["x"], b["y"])
                for a in r
                for b in s
                if a["k"] is not None and a["k"] == b["k"]
            }
            self.assertEqual(set(natural_join(r, s).tuples(["k", "x", "y"])), expected)

    def test_theta_join_self_join_with_rename(self):
        # 自己結合: 社員とその上司の名前（SQL の FROM emp AS e JOIN emp AS b ON e.boss_id = b.emp_id）
        e = project(EMP, ["name", "boss_id"])
        b = rename(project(EMP, ["emp_id", "name"]), {"emp_id": "b_id", "name": "boss_name"})
        r = theta_join(e, b, lambda row: row["boss_id"] == row["b_id"])
        self.assertEqual(
            r.tuples(["name", "boss_name"]),
            [("Bob", "Alice"), ("Carol", "Alice"), ("Dave", "Carol"), ("Eve", "Carol")],
        )

    def test_theta_join_non_equi(self):
        a = Relation.from_tuples(["x"], [(1,), (5,), (9,)])
        b = Relation.from_tuples(["lo", "hi"], [(0, 4), (4, 8)])
        r = theta_join(a, b, lambda row: row["lo"] <= row["x"] < row["hi"])
        self.assertEqual(r.tuples(), [(1, 0, 4), (5, 4, 8)])

    def test_theta_join_requires_rename(self):
        with self.assertRaises(ValueError):
            theta_join(EMP, EMP, lambda row: True)


class TestSetOperations(unittest.TestCase):
    A = Relation.from_tuples(["id", "name"], [(1, "Alice"), (2, "Bob"), (3, "Carol")])
    B = Relation.from_tuples(["name", "id"], [("Bob", 2), ("Dave", 4), ("Bob", 2)])

    def test_union_deduplicates(self):
        r = union(self.A, self.B)
        self.assertEqual(r.attributes, ("id", "name"), "結果の属性の順序は左側に合わせる")
        self.assertEqual(r.tuples(), [(1, "Alice"), (2, "Bob"), (3, "Carol"), (4, "Dave")])

    def test_difference(self):
        self.assertEqual(difference(self.A, self.B).tuples(), [(1, "Alice"), (3, "Carol")])
        self.assertEqual(difference(self.B, self.A).tuples(["id", "name"]), [(4, "Dave")])
        self.assertEqual(len(difference(self.A, self.A)), 0)

    def test_intersection(self):
        self.assertEqual(intersection(self.A, self.B).tuples(), [(2, "Bob")])

    def test_operations_with_empty_relation(self):
        empty = Relation(["id", "name"])
        self.assertEqual(union(self.A, empty), self.A)
        self.assertEqual(difference(self.A, empty), self.A)
        self.assertEqual(len(intersection(self.A, empty)), 0)

    def test_schema_must_match(self):
        other = Relation.from_tuples(["id"], [(1,)])
        for op in (union, difference, intersection):
            with self.assertRaises(ValueError, msg=op.__name__):
                op(self.A, other)


class TestGroupBy(unittest.TestCase):
    def test_group_by_with_all_functions(self):
        r = group_by(
            EMP,
            ["dept_id"],
            {
                "n": ("count", None),
                "total": ("sum", "salary"),
                "avg": ("avg", "salary"),
                "lo": ("min", "salary"),
                "hi": ("max", "salary"),
            },
        )
        self.assertEqual(r.attributes, ("dept_id", "n", "total", "avg", "lo", "hi"))
        self.assertEqual(
            r.tuples(),
            [(10, 2, 1400, 700.0, 500, 900), (20, 2, 1200, 600.0, 500, 700), (None, 1, 400, 400.0, 400, 400)],
            "dept_id が NULL の行も 1 つのグループになる（SQL の GROUP BY と同じ）",
        )

    def test_count_star_vs_count_column(self):
        r = group_by(EMP, [], {"all_rows": ("count", None), "has_boss": ("count", "boss_id")})
        self.assertEqual(r.tuples(), [(5, 4)], "COUNT(*) は 5、COUNT(boss_id) は NULL を除いて 4")

    def test_aggregates_ignore_null(self):
        r = Relation.from_tuples(["g", "v"], [("a", None), ("a", 10), ("b", None)])
        out = group_by(r, ["g"], {"s": ("sum", "v"), "avg": ("avg", "v"), "c": ("count", "v")})
        self.assertEqual(out.tuples(), [("a", 10, 10.0, 1), ("b", None, None, 0)])

    def test_empty_input_without_keys_returns_one_row(self):
        empty = Relation(["g", "v"])
        out = group_by(empty, [], {"n": ("count", None), "s": ("sum", "v"), "m": ("max", "v")})
        self.assertEqual(out.tuples(), [(0, None, None)], "GROUP BY なしの集約は 0 行の入力でも 1 行返す")

    def test_empty_input_with_keys_returns_no_rows(self):
        empty = Relation(["g", "v"])
        out = group_by(empty, ["g"], {"n": ("count", None)})
        self.assertEqual(len(out), 0)
        self.assertEqual(out.attributes, ("g", "n"))

    def test_multiple_keys(self):
        r = Relation.from_tuples(
            ["y", "m", "v"], [(2025, 1, 10), (2025, 1, 5), (2025, 2, 7), (2024, 1, 1)]
        )
        out = group_by(r, ["y", "m"], {"s": ("sum", "v")})
        self.assertEqual(out.tuples(), [(2024, 1, 1), (2025, 1, 15), (2025, 2, 7)])

    def test_errors(self):
        with self.assertRaises(ValueError):
            group_by(EMP, ["nope"], {"n": ("count", None)})
        with self.assertRaises(ValueError):
            group_by(EMP, ["dept_id"], {"x": ("median", "salary")})
        with self.assertRaises(ValueError):
            group_by(EMP, ["dept_id"], {"x": ("sum", "nope")})
        with self.assertRaises(ValueError):
            group_by(EMP, ["dept_id"], {"x": ("sum", None)})
        with self.assertRaises(ValueError):
            group_by(EMP, ["dept_id"], {"dept_id": ("count", None)})


class TestComposedQuery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = load_ecommerce()
        cls.conn = sqlite3.connect(":memory:")
        cls.conn.executescript(DATA.read_text(encoding="utf-8"))

    @classmethod
    def tearDownClass(cls):
        cls.conn.close()

    def expected(self, category_id):
        rows = self.conn.execute(
            """
            SELECT DISTINCT c.name
            FROM products AS p
            JOIN order_items AS oi ON oi.product_id = p.product_id
            JOIN orders AS o       ON o.order_id = oi.order_id
            JOIN customers AS c    ON c.customer_id = o.customer_id
            WHERE p.category_id = ? AND o.status <> 'cancelled'
            """,
            (category_id,),
        ).fetchall()
        return sorted(rows)

    def test_database_books(self):
        r = customers_who_bought(self.db, 3)
        self.assertEqual(r.attributes, ("name",))
        self.assertEqual(r.tuples(), [("佐藤 花子",), ("小林 陽菜",), ("田中 健太",), ("高橋 美咲",)])

    def test_cancelled_orders_are_excluded(self):
        # ヘッドホン（カテゴリ 8）: 中村 翔の注文はキャンセルされている
        names = [n for (n,) in customers_who_bought(self.db, 8).tuples()]
        self.assertNotIn("中村 翔", names)
        self.assertEqual(sorted(names), sorted(["鈴木 一郎", "渡辺 大輔", "伊藤 さくら"]))

    def test_matches_sql_for_every_category(self):
        for category_id in range(1, 12):
            self.assertEqual(
                customers_who_bought(self.db, category_id).tuples(),
                self.expected(category_id),
                f"category_id={category_id}",
            )


if __name__ == "__main__":
    unittest.main()
