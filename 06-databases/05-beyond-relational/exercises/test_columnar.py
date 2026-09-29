"""6.5 演習3（行指向と列指向、圧縮と読み取りコスト）のテスト

実行: python3 tools/check.py 6.5   （またはこのディレクトリで python3 -m unittest -v test_columnar）
"""
import math
import random
import unittest

from columnar import (
    bytes_read_column_store,
    bytes_read_row_store,
    column_size,
    dict_decode,
    dict_encode,
    rle_decode,
    rle_encode,
    row_store_size,
    sales_by_region,
    sales_by_region_encoded,
    sum_rle,
    to_columns,
    to_rows,
    value_size,
)

REGIONS = ["北海道", "東北", "関東", "中部", "近畿", "中国", "四国", "九州"]
COLUMNS = ["order_id", "region", "product", "year", "amount", "note"]


def make_sales(n=5000, seed=65):
    rng = random.Random(seed)
    return [
        {
            "order_id": i,
            "region": rng.choice(REGIONS),
            "product": f"product-{rng.randrange(500):03d}",
            "year": rng.choice([2023, 2024, 2025]),
            "amount": rng.randrange(100, 100_000),
            "note": rng.choice(["", "ギフト包装", "配送日指定あり", "領収書希望"]),
        }
        for i in range(1, n + 1)
    ]


def ref_size(values, encoding):
    """テスト用の参照実装（仕様の式どおり）。"""
    if encoding == "plain":
        return sum(value_size(v) for v in values)
    if encoding == "rle":
        runs = 0
        total = 0
        for i, v in enumerate(values):
            if i == 0 or values[i - 1] != v:
                runs += 1
                total += value_size(v) + 4
        return total
    distinct = sorted(set(values))
    if not distinct:
        return 0
    bits = max(1, math.ceil(math.log2(len(distinct))))
    return sum(value_size(v) for v in distinct) + math.ceil(len(values) * bits / 8)


class TestLayouts(unittest.TestCase):
    def test_provided_value_size(self):
        self.assertEqual((value_size(1), value_size("ab"), value_size("関東"), value_size(None)), (8, 6, 10, 1))
        with self.assertRaises(TypeError):
            value_size(1.5)

    def test_to_columns_and_back(self):
        rows = make_sales(50)
        table = to_columns(rows, COLUMNS)
        self.assertEqual(list(table), COLUMNS)
        self.assertEqual(table["order_id"][:3], [1, 2, 3])
        self.assertEqual(to_rows(table), rows)

    def test_column_subset(self):
        rows = [{"a": 1, "b": 2, "c": 3}]
        self.assertEqual(to_columns(rows, ["c", "a"]), {"c": [3], "a": [1]})
        with self.assertRaises(KeyError):
            to_columns(rows, ["z"])

    def test_to_rows_errors_and_empty(self):
        with self.assertRaises(ValueError):
            to_rows({"a": [1, 2], "b": [1]})
        self.assertEqual(to_rows({}), [])
        self.assertEqual(to_rows({"a": []}), [])


class TestEncodings(unittest.TestCase):
    def test_rle(self):
        self.assertEqual(rle_encode(["a", "a", "b", "a"]), [("a", 2), ("b", 1), ("a", 1)])
        self.assertEqual(rle_encode([]), [])
        self.assertEqual(rle_encode([7] * 1000), [(7, 1000)])
        self.assertEqual(rle_decode([("x", 3), ("y", 1)]), ["x", "x", "x", "y"])
        with self.assertRaises(ValueError):
            rle_decode([("x", 0)])

    def test_rle_round_trip(self):
        rng = random.Random(1)
        for _ in range(50):
            values = [rng.choice("abc") for _ in range(rng.randrange(0, 40))]
            self.assertEqual(rle_decode(rle_encode(values)), values)

    def test_dictionary_is_sorted_and_order_preserving(self):
        dictionary, codes = dict_encode(["tokyo", "osaka", "tokyo", "nagoya"])
        self.assertEqual((dictionary, codes), (["nagoya", "osaka", "tokyo"], [2, 1, 2, 0]))
        values = [30, 10, 20, 10, 40]
        d, c = dict_encode(values)
        for i in range(len(values)):
            for j in range(len(values)):
                self.assertEqual(values[i] < values[j], c[i] < c[j], "符号の大小 = 値の大小")
        self.assertEqual(dict_decode(d, c), values)
        self.assertEqual(dict_encode([]), ([], []))


class TestSizes(unittest.TestCase):
    def test_small_example(self):
        v = ["関東"] * 6 + ["近畿"] * 2
        self.assertEqual(column_size(v, "plain"), 80)
        self.assertEqual(column_size(v, "rle"), 28)
        self.assertEqual(column_size(v, "dict"), 21)
        self.assertEqual(column_size(v), 80, "既定は plain")
        with self.assertRaises(ValueError):
            column_size(v, "zstd")

    def test_edge_cases(self):
        for enc in ("plain", "rle", "dict"):
            self.assertEqual(column_size([], enc), 0, enc)
        self.assertEqual(column_size([5, 5, 5], "dict"), 8 + 1, "1 種類でも符号は 1 ビット")

    def test_sizes_match_formula_on_generated_data(self):
        table = to_columns(make_sales(), COLUMNS)
        for col in COLUMNS:
            for enc in ("plain", "rle", "dict"):
                self.assertEqual(column_size(table[col], enc), ref_size(table[col], enc), f"{col} / {enc}")

    def test_row_store_reads_everything(self):
        rows = make_sales(100)
        expected = sum(value_size(r[c]) for r in rows for c in COLUMNS)
        self.assertEqual(row_store_size(rows, COLUMNS), expected)
        self.assertEqual(bytes_read_row_store(rows, COLUMNS), expected)

    def test_column_store_reads_only_needed_columns(self):
        rows = make_sales()
        table = to_columns(rows, COLUMNS)
        needed = ["region", "year", "amount"]
        plain = bytes_read_column_store(table, needed)
        self.assertEqual(plain, sum(ref_size(table[c], "plain") for c in needed))
        self.assertLess(plain * 2, bytes_read_row_store(rows, COLUMNS), "6 列中 3 列だけを読む")
        encoded = bytes_read_column_store(table, needed, {"region": "dict", "year": "dict"})
        self.assertEqual(encoded, ref_size(table["region"], "dict") + ref_size(table["year"], "dict")
                         + ref_size(table["amount"], "plain"))

    def test_sorting_makes_rle_effective(self):
        rows = make_sales()
        unsorted = to_columns(rows, COLUMNS)
        sorted_table = to_columns(sorted(rows, key=lambda r: (r["year"], r["region"])), COLUMNS)
        self.assertGreater(column_size(unsorted["region"], "rle"), column_size(unsorted["region"], "plain"),
                           "並んでいないデータに RLE を使うと、かえって大きくなる")
        self.assertLess(column_size(sorted_table["region"], "rle") * 100, column_size(unsorted["region"], "rle"),
                        "(year, region) の順に並べると、region の連続が長くなり RLE がよく効く")
        self.assertEqual(len(rle_encode(sorted_table["year"])), 3)
        self.assertEqual(len(rle_encode(sorted_table["region"])), 3 * len(REGIONS))


class TestAggregation(unittest.TestCase):
    def naive(self, rows, year):
        totals = {}
        for r in rows:
            if r["year"] == year:
                totals[r["region"]] = totals.get(r["region"], 0) + r["amount"]
        return dict(sorted(totals.items()))

    def test_sum_rle(self):
        self.assertEqual(sum_rle([(10, 3), (5, 2)]), 40)
        self.assertEqual(sum_rle([]), 0)

    def test_sales_by_region(self):
        rows = make_sales()
        table = to_columns(rows, COLUMNS)
        for year in (2023, 2024, 2025, 1999):
            got = sales_by_region(table, year)
            self.assertEqual(got, self.naive(rows, year), year)
            self.assertEqual(list(got), sorted(got), "地域名の昇順")

    def test_reads_only_needed_columns(self):
        rows = make_sales(200)
        table = to_columns(rows, ["region", "year", "amount"])  # 他の列は渡さない
        self.assertEqual(sales_by_region(table, 2024), self.naive(rows, 2024))

    def test_encoded_aggregation(self):
        rows = sorted(make_sales(), key=lambda r: (r["year"], r["region"]))
        table = to_columns(rows, COLUMNS)
        year_runs = rle_encode(table["year"])
        dictionary, codes = dict_encode(table["region"])
        for year in (2023, 2024, 2025, 1999):
            got = sales_by_region_encoded(year_runs, dictionary, codes, table["amount"], year)
            self.assertEqual(got, self.naive(rows, year), year)
            self.assertEqual(list(got), sorted(got))

    def test_encoded_aggregation_on_unsorted_data(self):
        rows = make_sales(300, seed=9)
        table = to_columns(rows, COLUMNS)
        got = sales_by_region_encoded(rle_encode(table["year"]), *dict_encode(table["region"]), table["amount"], 2025)
        self.assertEqual(got, self.naive(rows, 2025))


if __name__ == "__main__":
    unittest.main()
