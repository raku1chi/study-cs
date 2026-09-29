"""9.6 システム設計ケーススタディ — 演習1・2 のテスト（URL 短縮）

実行: python3 tools/check.py 9.6   （またはこのディレクトリで python3 -m unittest -v）
"""
import math
import random
import threading
import unittest

from shortener import (
    ALPHABET,
    AliasTakenError,
    CodeGenerator,
    Shortener,
    base62_decode,
    base62_encode,
    default_multiplier,
    validate_alias,
    validate_url,
)


class TestExercise1Base62(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(base62_encode(0), "0")
        self.assertEqual(base62_encode(9), "9")
        self.assertEqual(base62_encode(10), "a")
        self.assertEqual(base62_encode(36), "A")
        self.assertEqual(base62_encode(61), "Z")
        self.assertEqual(base62_encode(62), "10")
        self.assertEqual(base62_encode(62 ** 7 - 1), "ZZZZZZZ")
        self.assertEqual(base62_decode("ZZZZZZZ"), 62 ** 7 - 1)
        self.assertEqual(base62_decode("a"), 10)
        self.assertNotEqual(base62_decode("a"), base62_decode("A"), "大文字と小文字は別の数字")

    def test_width(self):
        self.assertEqual(base62_encode(125, width=4), "0021")
        self.assertEqual(base62_decode("0021"), 125)
        self.assertEqual(base62_encode(0, width=3), "000")
        with self.assertRaises(ValueError):
            base62_encode(62 ** 3, width=3)

    def test_round_trip(self):
        rng = random.Random(62)
        for _ in range(500):
            n = rng.randrange(0, 2 ** 64)
            self.assertEqual(base62_decode(base62_encode(n)), n)

    def test_invalid(self):
        for bad in (-1, 1.5, True, "12"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                base62_encode(bad)
        for bad in ("", "abc-", "日本", "a b", "+1"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                base62_decode(bad)


class TestExercise2CodeGenerator(unittest.TestCase):
    def test_bijection_on_small_space(self):
        gen = CodeGenerator(length=2, offset=17)
        codes = [gen.code_for(n) for n in range(gen.capacity)]
        self.assertEqual(gen.capacity, 62 ** 2)
        self.assertEqual(len(set(codes)), gen.capacity, "異なる番号は必ず異なるコードになる（衝突しない）")
        self.assertTrue(all(len(c) == 2 and set(c) <= set(ALPHABET) for c in codes))
        self.assertEqual([gen.counter_for(c) for c in codes], list(range(gen.capacity)))

    def test_default_generator(self):
        gen = CodeGenerator()
        self.assertEqual(gen.capacity, 62 ** 7)
        codes = [gen.code_for(n) for n in range(1, 11)]
        self.assertTrue(all(len(c) == 7 for c in codes))
        self.assertNotEqual(codes, sorted(codes), "連番がそのまま並んで見えない")
        self.assertEqual(gen.counter_for(gen.code_for(123_456_789)), 123_456_789)
        self.assertEqual(gen.code_for(gen.capacity - 1), gen.code_for(gen.capacity - 1))

    def test_default_multiplier_is_coprime(self):
        for length in range(1, 10):
            m = default_multiplier(length)
            self.assertEqual(math.gcd(m, 62), 1)
            self.assertTrue(0 < m < 62 ** length)

    def test_custom_parameters(self):
        gen = CodeGenerator(length=3, multiplier=1, offset=0)
        self.assertEqual(gen.code_for(125), "021", "乗数 1・オフセット 0 ならただの 62 進数")
        for bad in ({"multiplier": 2}, {"multiplier": 31}, {"multiplier": 62}, {"multiplier": 0},
                    {"multiplier": 62 ** 3 + 1}, {"offset": -1}, {"offset": 62 ** 3}, {"length": 0}):
            kwargs = {"length": 3, **bad}
            with self.assertRaises(ValueError, msg=str(bad)):
                CodeGenerator(**kwargs)

    def test_out_of_range(self):
        gen = CodeGenerator(length=2)
        for bad in (-1, 62 ** 2, 1.0, True):
            with self.assertRaises(ValueError, msg=repr(bad)):
                gen.code_for(bad)
        for bad in ("a", "abc", "a-", ""):
            with self.assertRaises(ValueError, msg=repr(bad)):
                gen.counter_for(bad)


class TestExercise2Validation(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(validate_alias("summer-sale"), "summer-sale")
        self.assertEqual(validate_alias("abc"), "abc")
        self.assertEqual(validate_alias("abcdefgh"), "abcdefgh", "8 文字なら 7 文字のコードとは衝突しない")
        self.assertEqual(validate_alias("my_link"), "my_link", "記号を含めば 7 文字でも衝突しない")
        invalid = ["ab", "a" * 31, "has space", "日本語", "a/b", "abcdefg", "Admin", "api", "LOGIN"]
        for alias in invalid:
            with self.assertRaises(ValueError, msg=repr(alias)):
                validate_alias(alias)
        self.assertEqual(validate_alias("abcdefg", code_length=6), "abcdefg")

    def test_urls(self):
        for url in ("https://example.com/path?q=1#frag", "http://localhost:8080/", "https://例え.jp/"):
            self.assertEqual(validate_url(url), url)
        invalid = ["", "example.com", "ftp://example.com/", "javascript:alert(1)",
                   "data:text/html,hi", "https://", "https://exa mple.com/", "https://example.com/\n",
                   "https://example.com/" + "a" * 2048]
        for url in invalid:
            with self.assertRaises(ValueError, msg=repr(url)):
                validate_url(url)


class TestExercise2Shortener(unittest.TestCase):
    def test_shorten_and_resolve(self):
        s = Shortener(CodeGenerator(length=4))
        c1 = s.shorten("https://example.com/a")
        c2 = s.shorten("https://example.com/a")
        self.assertNotEqual(c1, c2, "同じ URL でも別のコードを発行してよい")
        self.assertEqual(len(c1), 4)
        self.assertEqual(s.resolve(c1), "https://example.com/a")
        with self.assertRaises(KeyError):
            s.resolve("nope")
        with self.assertRaises(ValueError):
            s.shorten("javascript:alert(1)")

    def test_codes_follow_the_generator_counter(self):
        gen = CodeGenerator(length=4, offset=5)
        s = Shortener(gen)
        codes = [s.shorten(f"https://example.com/{i}") for i in range(5)]
        self.assertEqual([gen.counter_for(c) for c in codes], [0, 1, 2, 3, 4])

    def test_aliases(self):
        s = Shortener()
        self.assertEqual(s.shorten("https://example.com/sale", alias="summer-sale"), "summer-sale")
        self.assertEqual(s.resolve("summer-sale"), "https://example.com/sale")
        with self.assertRaises(AliasTakenError):
            s.shorten("https://example.com/other", alias="summer-sale")
        with self.assertRaises(ValueError):
            s.shorten("https://example.com/x", alias="admin")

    def test_capacity_exhaustion(self):
        s = Shortener(CodeGenerator(length=1))
        for i in range(62):
            s.shorten(f"https://example.com/{i}")
        with self.assertRaises(OverflowError):
            s.shorten("https://example.com/overflow")

    def test_concurrent_shorten_never_reuses_codes(self):
        s = Shortener(CodeGenerator(length=5))
        results = []
        lock = threading.Lock()

        def worker(n):
            mine = [s.shorten(f"https://example.com/{n}/{i}") for i in range(200)]
            with lock:
                results.extend(mine)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(5)
        self.assertEqual(len(results), 1600)
        self.assertEqual(len(set(results)), 1600, "同時に呼ばれても同じコードを 2 回発行しない")


if __name__ == "__main__":
    unittest.main()
