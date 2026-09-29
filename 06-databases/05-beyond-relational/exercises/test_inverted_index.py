"""6.5 演習1（転置インデックスと BM25）のテスト

実行: python3 tools/check.py 6.5   （またはこのディレクトリで python3 -m unittest -v test_inverted_index）
"""
import math
import unittest
from collections import Counter

from inverted_index import InvertedIndex, tokenize

DOCS = {
    1: "PostgreSQL is a relational database. PostgreSQL supports SQL.",
    2: "Redis is an in-memory key-value store.",
    3: "Elasticsearch is a search engine built on Lucene. It uses an inverted index.",
    4: "東京都の天気予報",
    5: "京都の観光ガイド",
    6: "データベースの索引（インデックス）の仕組み",
    7: "全文検索エンジンと転置インデックス",
    8: "SQL と NoSQL のデータベース",
}


def build(docs=DOCS, **kwargs):
    index = InvertedIndex(**kwargs)
    for doc_id, text in docs.items():
        index.add(doc_id, text)
    return index


def reference_bm25(docs, query, k1=1.2, b=0.75):
    """BM25 の定義どおりの参照実装（テスト用）。"""
    tokenized = {d: tokenize(t) for d, t in docs.items()}
    n_docs = len(docs)
    avgdl = sum(len(t) for t in tokenized.values()) / n_docs
    terms = list(dict.fromkeys(tokenize(query)))
    scores = {}
    for d, toks in tokenized.items():
        counts = Counter(toks)
        s, hit = 0.0, False
        for t in terms:
            tf = counts[t]
            if tf == 0:
                continue
            hit = True
            n_t = sum(1 for other in tokenized.values() if t in other)
            idf = math.log(1 + (n_docs - n_t + 0.5) / (n_t + 0.5))
            s += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(toks) / avgdl))
        if hit:
            scores[d] = s
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))


class TestTokenize(unittest.TestCase):
    def test_english_words_are_lowercased(self):
        self.assertEqual(tokenize("Hello, World!"), ["hello", "world"])
        self.assertEqual(tokenize("key-value store"), ["key", "value", "store"])

    def test_japanese_bigrams(self):
        self.assertEqual(tokenize("東京都の天気"), ["東京", "京都", "都の", "の天", "天気"])
        self.assertEqual(tokenize("本"), ["本"], "1 文字だけのランはそのまま")

    def test_mixed_scripts_and_numbers(self):
        self.assertEqual(tokenize("PostgreSQL 16で全文検索"), ["postgresql", "16", "で全", "全文", "文検", "検索"])
        self.assertEqual(tokenize("SQL入門"), ["sql", "入門"])

    def test_nfkc_normalization(self):
        self.assertEqual(tokenize("ＳＱＬ入門"), ["sql", "入門"], "全角英字 → 半角")
        self.assertEqual(tokenize("ﾃﾞｰﾀﾍﾞｰｽ"), tokenize("データベース"), "半角カナ → 全角")
        self.assertEqual(tokenize("データベース"), ["デー", "ータ", "タベ", "ベー", "ース"], "長音記号も文字の一部")

    def test_separators(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize("!!! ... ---"), [])
        self.assertEqual(tokenize("データ・ベース"), ["デー", "ータ", "ベー", "ース"], "中黒は区切り")
        self.assertEqual(tokenize("索引（インデックス）"), ["索引", "イン", "ンデ", "デッ", "ック", "クス"])


class TestIndexBuilding(unittest.TestCase):
    def test_postings_with_term_frequencies(self):
        index = build()
        self.assertEqual(index.postings("postgresql"), [(1, 2)])
        self.assertEqual(index.postings("sql"), [(1, 1), (8, 1)])
        self.assertEqual(index.postings("デー"), [(6, 1), (8, 1)])
        self.assertEqual(index.postings("mysql"), [])

    def test_document_statistics(self):
        index = build()
        self.assertEqual(index.doc_count, 8)
        self.assertEqual(index.doc_length(4), 7, "東京都の天気予報 → 7 つの bi-gram")
        total = sum(len(tokenize(t)) for t in DOCS.values())
        self.assertAlmostEqual(index.avgdl, total / 8)

    def test_empty_index_and_empty_document(self):
        index = InvertedIndex()
        self.assertEqual(index.doc_count, 0)
        self.assertEqual(index.avgdl, 0.0)
        index.add(1, "!!!")
        self.assertEqual(index.doc_length(1), 0)

    def test_duplicate_document_id(self):
        index = build()
        with self.assertRaises(ValueError):
            index.add(1, "again")


class TestBooleanSearch(unittest.TestCase):
    def setUp(self):
        self.index = build()

    def test_must_is_and(self):
        self.assertEqual(self.index.search_boolean(must="sql"), [1, 8])
        self.assertEqual(self.index.search_boolean(must="relational database"), [1])
        self.assertEqual(self.index.search_boolean(must="sql mysql"), [], "含まない語があれば 0 件")

    def test_should_is_or(self):
        self.assertEqual(self.index.search_boolean(should="redis lucene"), [2, 3])

    def test_must_and_should(self):
        self.assertEqual(self.index.search_boolean(must="is", should="redis lucene"), [2, 3])
        self.assertEqual(self.index.search_boolean(must="is", should="redis nothing"), [2])

    def test_must_not(self):
        self.assertEqual(self.index.search_boolean(must="データベース"), [6, 8])
        self.assertEqual(self.index.search_boolean(must="データベース", must_not="sql"), [6])
        self.assertEqual(self.index.search_boolean(should="インデックス index", must_not="全文"), [3, 6])

    def test_japanese_ngram_false_positive(self):
        # bi-gram では「京都」が「東京都」にも一致してしまう（n-gram 方式の典型的な誤り）
        self.assertEqual(self.index.search_boolean(must="京都"), [4, 5])
        self.assertEqual(self.index.search_boolean(must="京都", must_not="東京"), [5])

    def test_requires_positive_terms(self):
        with self.assertRaises(ValueError):
            self.index.search_boolean(must_not="sql")
        with self.assertRaises(ValueError):
            self.index.search_boolean(must="!!!")


class TestBM25(unittest.TestCase):
    def test_idf(self):
        index = build()
        self.assertAlmostEqual(index.idf("postgresql"), math.log(1 + (8 - 1 + 0.5) / (1 + 0.5)))
        self.assertGreater(index.idf("redis"), index.idf("is"), "まれな語ほど IDF が大きい")
        self.assertGreater(index.idf("is"), 0, "多くの文書に現れる語でも負にならない")
        self.assertAlmostEqual(index.idf("unknown"), math.log(1 + 8.5 / 0.5))

    def test_matches_reference_implementation(self):
        index = build()
        for query in ("PostgreSQL SQL", "inverted index search", "データベース", "インデックス 検索", "is an", "京都"):
            got = index.search(query, k=100)
            expected = reference_bm25(DOCS, query)
            self.assertEqual([d for d, _ in got], [d for d, _ in expected], query)
            for (_, s1), (_, s2) in zip(got, expected):
                self.assertAlmostEqual(s1, s2, places=9, msg=query)

    def test_parameters_are_used(self):
        index = build(k1=2.0, b=0.3)
        got = index.search("sql database", k=100)
        expected = reference_bm25(DOCS, "sql database", k1=2.0, b=0.3)
        self.assertEqual([round(s, 9) for _, s in got], [round(s, 9) for _, s in expected])

    def test_repeated_query_terms_count_once(self):
        index = build()
        self.assertAlmostEqual(index.score("sql sql sql", 1), index.score("sql", 1))

    def test_term_frequency_saturates(self):
        docs = {
            1: "a " + "b " * 9,      # tf(a) = 1、長さ 10
            2: "a " * 5 + "b " * 5,  # tf(a) = 5
            3: "a " * 10,            # tf(a) = 10
            4: "c " * 10,            # a を含まない（IDF を正にするため）
            5: "d " * 10,
        }
        index = build(docs)
        s1, s5, s10 = (index.score("a", d) for d in (1, 2, 3))
        self.assertLess(s1, s5)
        self.assertLess(s5, s10)
        self.assertLess(s10 / s1, index.k1 + 1, "tf が 10 倍になってもスコアは k1 + 1 倍未満で頭打ち")

    def test_longer_documents_are_penalized(self):
        docs = {1: "cat dog", 2: "cat dog bird fish lion bear", 3: "zebra"}
        index = build(docs)
        self.assertGreater(index.score("cat", 1), index.score("cat", 2), "同じ tf なら短い文書の方が高い")
        flat = build(docs, b=0.0)
        self.assertAlmostEqual(flat.score("cat", 1), flat.score("cat", 2), msg="b = 0 なら長さで補正しない")

    def test_search_ordering_and_k(self):
        index = build()
        results = index.search("PostgreSQL SQL", k=10)
        self.assertEqual(results[0][0], 1)
        self.assertEqual([d for d, _ in results], [1, 8])
        self.assertEqual(len(index.search("is an", k=2)), 2)
        self.assertEqual(index.search("nothing here"), [])
        with self.assertRaises(ValueError):
            index.search("sql", k=0)

    def test_ties_are_broken_by_doc_id(self):
        index = build({3: "same text", 1: "same text", 2: "other"})
        self.assertEqual([d for d, _ in index.search("same")], [1, 3])


if __name__ == "__main__":
    unittest.main()
