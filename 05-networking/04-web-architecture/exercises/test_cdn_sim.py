"""5.4 Webの仕組みとネットワーク構成 — テスト（cdn_sim）

実行: python3 tools/check.py 5.4   （またはこのディレクトリで python3 -m unittest -v）

時計は FakeClock、オリジンは呼び出しを記録する FakeOrigin で置き換えるので、結果は毎回同じです。
"""
import unittest

from cdn_sim import CDNCache, EdgeResponse, OriginResponse

URL_A = "https://example.com/a"


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class FakeOrigin:
    """呼ばれた回数を数え、version を上げると内容が変わるオリジン。"""

    def __init__(self, ttl=60.0, status=200, vary=(), swr=0.0):
        self.calls = []
        self.version = 1
        self.ttl, self.status, self.vary, self.swr = ttl, status, vary, swr

    def __call__(self, url, headers):
        self.calls.append(url)
        lang = next((v for k, v in headers.items() if k.lower() == "accept-language"), "-")
        return OriginResponse(self.status, f"{url} v{self.version} {lang}", self.ttl, self.vary, self.swr)


class TestBasicCaching(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.origin = FakeOrigin(ttl=60)
        self.cdn = CDNCache(self.origin, self.clock)

    def test_miss_then_hit(self):
        first = self.cdn.get(URL_A)
        self.assertEqual((first.status, first.cache, first.age), (200, "MISS", 0.0))
        self.clock.now = 10
        second = self.cdn.get(URL_A)
        self.assertEqual(second, EdgeResponse(200, first.body, "HIT", 10.0))
        self.assertEqual(len(self.origin.calls), 1, "2 回目はオリジンに行かない")

    def test_expiry(self):
        self.cdn.get(URL_A)
        self.clock.now = 59.9
        self.assertEqual(self.cdn.get(URL_A).cache, "HIT")
        self.origin.version = 2
        self.clock.now = 60.0
        resp = self.cdn.get(URL_A)
        self.assertEqual(resp.cache, "MISS", "経過時間が寿命に達したら新鮮ではない")
        self.assertIn("v2", resp.body)
        self.assertEqual(len(self.origin.calls), 2)

    def test_cache_key_normalization(self):
        self.assertEqual(self.cdn.cache_key("https://Example.COM/p?b=2&a=1&utm_source=mail"),
                         "https://example.com/p?a=1&b=2")
        self.assertEqual(self.cdn.cache_key("https://example.com"), "https://example.com/")
        self.cdn.get("https://example.com/p?b=2&a=1")
        self.assertEqual(self.cdn.get("https://example.com/p?a=1&b=2&utm_campaign=x&fbclid=y").cache, "HIT")
        self.assertEqual(self.cdn.get("https://example.com/p?a=1&b=3").cache, "MISS")
        self.assertEqual(self.cdn.get("https://example.com/P?a=1&b=2").cache, "MISS", "パスは大文字小文字を区別する")

    def test_stats(self):
        for t in (0, 1, 2):
            self.clock.now = t
            self.cdn.get(URL_A)
        self.cdn.get("https://example.com/b")
        self.cdn.get(URL_A, {"Authorization": "Bearer x"})
        s = self.cdn.stats
        self.assertEqual((s.requests, s.hits, s.stale_hits, s.misses, s.bypasses, s.origin_requests), (5, 2, 0, 2, 1, 3))
        self.assertAlmostEqual(s.hit_ratio, 2 / 5)


class TestWhatIsCacheable(unittest.TestCase):
    def test_zero_ttl_is_not_cached(self):
        origin = FakeOrigin(ttl=0)
        cdn = CDNCache(origin, FakeClock())
        self.assertEqual([cdn.get(URL_A).cache for _ in range(3)], ["MISS"] * 3)
        self.assertEqual(len(origin.calls), 3)

    def test_error_status_is_not_cached_but_404_is(self):
        origin = FakeOrigin(status=500)
        cdn = CDNCache(origin, FakeClock())
        self.assertEqual([cdn.get(URL_A).cache for _ in range(2)], ["MISS", "MISS"])
        origin.status = 404
        self.assertEqual([cdn.get("https://example.com/nope").cache for _ in range(2)], ["MISS", "HIT"],
                         "404 は（明示的な寿命があれば）キャッシュしてよい")

    def test_authorization_bypasses_cache(self):
        origin = FakeOrigin()
        cdn = CDNCache(origin, FakeClock())
        cdn.get(URL_A)  # 認証なしの応答をキャッシュしておく
        self.assertEqual(cdn.get(URL_A, {"authorization": "Bearer alice"}).cache, "BYPASS",
                         "認証付きのリクエストには、キャッシュした応答を返さない")
        cdn2 = CDNCache(origin, FakeClock())
        cdn2.get(URL_A, {"Authorization": "Bearer alice"})
        self.assertEqual(cdn2.get(URL_A).cache, "MISS", "認証付きの応答は保存しない")


class TestVary(unittest.TestCase):
    def test_vary_on_language(self):
        origin = FakeOrigin(vary=("Accept-Language",))
        cdn = CDNCache(origin, FakeClock())
        ja = cdn.get(URL_A, {"Accept-Language": "ja"})
        en = cdn.get(URL_A, {"Accept-Language": "en"})
        self.assertEqual((ja.cache, en.cache), ("MISS", "MISS"))
        self.assertIn("ja", cdn.get(URL_A, {"accept-language": "ja"}).body)
        self.assertEqual(cdn.get(URL_A, {"Accept-Language": "en"}).cache, "HIT")
        self.assertEqual(len(origin.calls), 2, "言語ごとに 1 回ずつ")

    def test_accept_encoding_is_normalized(self):
        origin = FakeOrigin(vary=("Accept-Encoding",))
        cdn = CDNCache(origin, FakeClock())
        self.assertEqual(cdn.get(URL_A, {"Accept-Encoding": "gzip, deflate, br"}).cache, "MISS")
        self.assertEqual(cdn.get(URL_A, {"Accept-Encoding": "br;q=1.0, gzip;q=0.8"}).cache, "HIT", "どちらも br")
        self.assertEqual(cdn.get(URL_A, {"Accept-Encoding": "gzip"}).cache, "MISS")
        self.assertEqual(cdn.get(URL_A, {"Accept-Encoding": "deflate, gzip"}).cache, "HIT", "どちらも gzip")
        self.assertEqual(cdn.get(URL_A).cache, "MISS", "指定なしは identity")

    def test_without_normalization_the_cache_fragments(self):
        origin = FakeOrigin(vary=("Accept-Encoding",))
        cdn = CDNCache(origin, FakeClock(), normalize_accept_encoding=False)
        cdn.get(URL_A, {"Accept-Encoding": "gzip, deflate, br"})
        self.assertEqual(cdn.get(URL_A, {"Accept-Encoding": "br;q=1.0, gzip;q=0.8"}).cache, "MISS")

    def test_vary_star_is_never_reused(self):
        origin = FakeOrigin(vary=("*",))
        cdn = CDNCache(origin, FakeClock())
        self.assertEqual([cdn.get(URL_A).cache for _ in range(2)], ["MISS", "MISS"])


class TestPurgeAndStale(unittest.TestCase):
    def test_purge(self):
        origin = FakeOrigin(vary=("Accept-Language",))
        cdn = CDNCache(origin, FakeClock())
        cdn.get(URL_A, {"Accept-Language": "ja"})
        cdn.get(URL_A, {"Accept-Language": "en"})
        self.assertEqual(cdn.purge(URL_A), 2, "同じ URL のすべての表現を消す")
        self.assertEqual(cdn.purge(URL_A), 0)
        self.assertEqual(cdn.get(URL_A, {"Accept-Language": "ja"}).cache, "MISS")

    def test_purge_prefix(self):
        cdn = CDNCache(FakeOrigin(), FakeClock())
        for path in ("/img/a.png", "/img/b.png", "/index.html"):
            cdn.get("https://example.com" + path)
        self.assertEqual(cdn.purge_prefix("https://example.com/img/"), 2)
        self.assertEqual(cdn.get("https://example.com/index.html").cache, "HIT")
        self.assertEqual(cdn.get("https://example.com/img/a.png").cache, "MISS")

    def test_stale_while_revalidate(self):
        clock = FakeClock()
        origin = FakeOrigin(ttl=10, swr=30)
        cdn = CDNCache(origin, clock)
        cdn.get(URL_A)  # 時刻 0 に v1 を保存。10 秒間は新鮮、40 秒までは古いものを返せる
        origin.version = 2
        clock.now = 15
        stale = cdn.get(URL_A)
        self.assertEqual((stale.cache, stale.age), ("STALE", 15.0))
        self.assertIn("v1", stale.body, "利用者は待たされずに古い内容を受け取る")
        self.assertEqual(len(origin.calls), 2, "裏でオリジンから新しい内容を取得している")
        clock.now = 16
        fresh = cdn.get(URL_A)
        self.assertEqual((fresh.cache, fresh.age), ("HIT", 1.0))
        self.assertIn("v2", fresh.body)
        clock.now = 60  # 15 秒に保存した v2 は 55 秒まで古いものとして使えるが、それも過ぎた
        self.assertEqual(cdn.get(URL_A).cache, "MISS")
        self.assertEqual(cdn.stats.stale_hits, 1)


class TestOriginShield(unittest.TestCase):
    def test_two_tier_cache(self):
        clock = FakeClock()
        origin = FakeOrigin(ttl=60)
        shield = CDNCache(origin, clock)  # オリジンの手前に置く中間のキャッシュ
        tokyo = CDNCache(shield.as_origin(), clock)
        osaka = CDNCache(shield.as_origin(), clock)
        self.assertEqual(tokyo.get(URL_A).cache, "MISS")
        clock.now = 5
        r = osaka.get(URL_A)
        self.assertEqual((r.cache, r.age), ("MISS", 5.0), "osaka には初めてだが、shield に残っていた（経過 5 秒）")
        self.assertEqual(len(origin.calls), 1, "オリジンへのリクエストは 1 回だけ")
        clock.now = 59
        self.assertEqual(osaka.get(URL_A).cache, "HIT")
        clock.now = 61
        self.assertEqual(osaka.get(URL_A).cache, "MISS",
                         "下流は上流での経過時間を引き継ぐので、shield と同じ時刻に期限が切れる")
        self.assertEqual(len(origin.calls), 2)

    def test_uncacheable_responses_are_not_cached_downstream(self):
        clock = FakeClock()
        origin = FakeOrigin(status=500)
        shield = CDNCache(origin, clock)
        edge = CDNCache(shield.as_origin(), clock)
        self.assertEqual([edge.get(URL_A).cache for _ in range(2)], ["MISS", "MISS"])
        self.assertEqual(len(origin.calls), 2)


if __name__ == "__main__":
    unittest.main()
