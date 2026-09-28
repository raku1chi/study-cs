"""5.3 DNS・HTTP・TLS — テスト（http_cache）

実行: python3 tools/check.py 5.3   （またはこのディレクトリで python3 -m unittest -v）

時刻はすべて引数で与える（テストの中で現在時刻は使わない）ので、結果は毎回同じです。
"""
import os
import time
import unittest
from email.utils import formatdate

from http_cache import cache_status, current_age, freshness_lifetime, parse_cache_control, parse_http_date

T0 = 1_750_000_000.0  # 基準時刻（UNIX 時間）


def http_date(t: float) -> str:
    return formatdate(t, usegmt=True)


class TestParseCacheControl(unittest.TestCase):
    def test_examples(self):
        self.assertEqual(parse_cache_control("max-age=60, public"), {"max-age": "60", "public": None})
        self.assertEqual(parse_cache_control("No-Cache, MAX-AGE=0"), {"no-cache": None, "max-age": "0"},
                         "ディレクティブ名は大文字小文字を区別しない")
        self.assertEqual(parse_cache_control(" , ,no-store,, "), {"no-store": None})
        self.assertEqual(parse_cache_control(""), {})
        self.assertEqual(parse_cache_control(None), {})

    def test_quoted_strings(self):
        self.assertEqual(parse_cache_control('private="Set-Cookie, X-Token", max-age=10'),
                         {"private": "Set-Cookie, X-Token", "max-age": "10"}, "引用符の中のカンマは区切りではない")
        self.assertEqual(parse_cache_control('max-age="30"'), {"max-age": "30"})
        self.assertEqual(parse_cache_control(r'x-ext="a\"b", public'), {"x-ext": 'a"b', "public": None})

    def test_duplicates_keep_first(self):
        self.assertEqual(parse_cache_control("max-age=10, max-age=20")["max-age"], "10")


class TestParseHttpDate(unittest.TestCase):
    def test_three_formats(self):
        # RFC 9110 は、受信側に 3 つの形式すべてを受け付けるよう求めている
        for text in ("Sun, 06 Nov 1994 08:49:37 GMT",     # IMF-fixdate（推奨）
                     "Sunday, 06-Nov-94 08:49:37 GMT",    # 廃止された RFC 850 形式
                     "Sun Nov  6 08:49:37 1994"):         # C の asctime() 形式
            self.assertEqual(parse_http_date(text), 784111777.0, text)

    def test_invalid(self):
        for text in ("0", "", "garbage", "Sun, 32 Nov 1994 08:49:37 GMT", None):
            self.assertIsNone(parse_http_date(text), repr(text))

    @unittest.skipUnless(hasattr(time, "tzset"), "time.tzset が必要（Unix 系 OS）")
    def test_asctime_is_utc_regardless_of_local_timezone(self):
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Asia/Tokyo"
        time.tzset()
        try:
            self.assertEqual(parse_http_date("Sun Nov  6 08:49:37 1994"), 784111777.0,
                             "タイムゾーンのない日時を、実行環境のローカル時刻として解釈してはいけない")
        finally:
            if old is None:
                del os.environ["TZ"]
            else:
                os.environ["TZ"] = old
            time.tzset()


class TestFreshnessLifetime(unittest.TestCase):
    def life(self, headers, shared=False, response_time=T0):
        return freshness_lifetime(headers, shared=shared, response_time=response_time)

    def test_max_age(self):
        self.assertEqual(self.life({"Cache-Control": "max-age=600"}), 600)

    def test_s_maxage_only_for_shared_caches(self):
        h = {"Cache-Control": "max-age=600, s-maxage=60"}
        self.assertEqual(self.life(h, shared=True), 60, "共有キャッシュ（CDN など）は s-maxage を優先")
        self.assertEqual(self.life(h, shared=False), 600, "ブラウザ（プライベートキャッシュ）は s-maxage を無視")

    def test_expires(self):
        self.assertEqual(self.life({"Date": http_date(T0), "Expires": http_date(T0 + 3600)}), 3600)
        self.assertEqual(self.life({"Expires": http_date(T0 + 120)}, response_time=T0), 120,
                         "Date がなければ受信時刻を使う")
        self.assertEqual(self.life({"Date": http_date(T0), "Expires": http_date(T0 - 60)}), 0)
        self.assertEqual(self.life({"Date": http_date(T0), "Expires": "0"}), 0, "不正な Expires は期限切れ")

    def test_max_age_beats_expires(self):
        h = {"Cache-Control": "max-age=10", "Date": http_date(T0), "Expires": http_date(T0 + 3600)}
        self.assertEqual(self.life(h), 10)

    def test_invalid_max_age_means_stale(self):
        for value in ("abc", "-1", "1.5", ""):
            self.assertEqual(self.life({"Cache-Control": f"max-age={value}"}), 0, value)

    def test_huge_max_age_is_capped(self):
        self.assertEqual(self.life({"Cache-Control": "max-age=99999999999999999999"}), 2**31)

    def test_heuristic_freshness(self):
        h = {"Date": http_date(T0), "Last-Modified": http_date(T0 - 10 * 86400)}
        self.assertAlmostEqual(self.life(h), 86400, msg="最終更新からの経過時間の 10%")
        self.assertEqual(self.life({}), 0, "手がかりがなければ 0")

    def test_header_names_are_case_insensitive(self):
        self.assertEqual(self.life({"cache-control": "max-age=5"}), 5)


class TestCurrentAge(unittest.TestCase):
    def age(self, headers, now=T0 + 62):
        return current_age(headers, request_time=T0, response_time=T0 + 2, now=now)

    def test_basic(self):
        # 見かけの経過 = (T0+2) - (T0+1) = 1、応答の遅れ = 2 → 初期の経過 max(1, 2) = 2、保存後 60 秒
        self.assertEqual(self.age({"Date": http_date(T0 + 1)}), 62)

    def test_age_header_from_upstream_cache(self):
        self.assertEqual(self.age({"Date": http_date(T0 + 1), "Age": "100"}), 162, "100 + 応答の遅れ 2 + 60")

    def test_server_clock_ahead(self):
        self.assertEqual(self.age({"Date": http_date(T0 + 100)}), 62, "未来の Date でも経過時間は負にならない")

    def test_server_clock_behind(self):
        self.assertEqual(self.age({"Date": http_date(T0 - 300)}), 362, "Date が古ければ、見かけの経過を採る")

    def test_missing_or_invalid_headers(self):
        self.assertEqual(self.age({}), 62, "Date がなければ受信時刻、Age がなければ 0")
        self.assertEqual(self.age({"Date": "garbage", "Age": "-5"}), 62)


class TestCacheStatus(unittest.TestCase):
    def status(self, headers, shared=False, now=T0 + 62):
        headers = {"Date": http_date(T0 + 1), **headers}
        return cache_status(headers, request_time=T0, response_time=T0 + 2, now=now, shared=shared)

    def test_fresh_and_stale(self):
        self.assertEqual(self.status({"Cache-Control": "max-age=600"}), "fresh")
        self.assertEqual(self.status({"Cache-Control": "max-age=60"}), "stale")
        self.assertEqual(self.status({"Cache-Control": "max-age=62"}), "stale", "寿命 > 経過 のときだけ新鮮")
        self.assertEqual(self.status({"Cache-Control": "max-age=63"}), "fresh")

    def test_no_store_and_private(self):
        self.assertEqual(self.status({"Cache-Control": "no-store, max-age=600"}), "no-store")
        self.assertEqual(self.status({"Cache-Control": "private, max-age=600"}, shared=True), "no-store",
                         "共有キャッシュは private な応答を保存してはいけない")
        self.assertEqual(self.status({"Cache-Control": "private, max-age=600"}, shared=False), "fresh")

    def test_no_cache_requires_validation(self):
        self.assertEqual(self.status({"Cache-Control": "no-cache, max-age=600"}), "must-revalidate",
                         "no-cache は「保存するな」ではなく「使う前に必ず確認せよ」")

    def test_must_revalidate(self):
        self.assertEqual(self.status({"Cache-Control": "max-age=10, must-revalidate"}), "must-revalidate")
        self.assertEqual(self.status({"Cache-Control": "max-age=600, must-revalidate"}), "fresh")

    def test_shared_cache_revalidation_rules(self):
        self.assertEqual(self.status({"Cache-Control": "s-maxage=10"}, shared=True), "must-revalidate",
                         "s-maxage は共有キャッシュに対して proxy-revalidate の意味も持つ")
        self.assertEqual(self.status({"Cache-Control": "max-age=10, proxy-revalidate"}, shared=True), "must-revalidate")
        self.assertEqual(self.status({"Cache-Control": "max-age=10, proxy-revalidate"}, shared=False), "stale")

    def test_expires_and_heuristics(self):
        self.assertEqual(self.status({"Expires": http_date(T0 + 3600)}), "fresh")
        self.assertEqual(self.status({"Expires": "0"}), "stale")
        self.assertEqual(self.status({"Last-Modified": http_date(T0 - 30 * 86400)}), "fresh")
        self.assertEqual(self.status({}), "stale")


if __name__ == "__main__":
    unittest.main()
