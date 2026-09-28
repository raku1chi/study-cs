"""10.4 構造化ログから RED メトリクス — テスト

データ: data/access.jsonl（2026-09-01 10:00〜10:09 UTC の架空のアクセスログ）
実行: python3 tools/check.py 10.4   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest
from datetime import datetime, timezone
from pathlib import Path

from logstats import (
    EndpointStats,
    LogRecord,
    endpoint_of,
    normalize_path,
    parse_line,
    parse_logs,
    per_minute,
    percentile,
    red_by_endpoint,
    slowest,
    top_offenders,
)

DATA = Path(__file__).parent / "data" / "access.jsonl"


def load():
    return parse_logs(DATA.read_text(encoding="utf-8").splitlines())


class TestExercise3Parse(unittest.TestCase):
    def test_parse_valid_line(self):
        line = ('{"ts":"2026-09-01T10:00:00.228Z","method":"POST","path":"/api/checkout","status":201,'
                '"duration_ms":155.3,"client_ip":"203.0.113.15","trace_id":"6733688b87dfe06b67131b0db95f935d"}')
        r = parse_line(line)
        self.assertEqual(r, LogRecord(datetime(2026, 9, 1, 10, 0, 0, 228000, tzinfo=timezone.utc), "POST",
                                      "/api/checkout", 201, 155.3, "203.0.113.15", "6733688b87dfe06b67131b0db95f935d"))

    def test_offsets_are_converted_to_utc(self):
        r = parse_line('{"ts":"2026-09-01T19:00:00+09:00","method":"GET","path":"/","status":200,"duration_ms":1}')
        self.assertEqual(r.ts, datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc))
        self.assertEqual((r.client_ip, r.trace_id), ("", ""), "任意のフィールドは空文字列")
        self.assertIsInstance(r.duration_ms, float)

    def test_invalid_lines(self):
        bad = [
            "not json",
            "[1, 2, 3]",
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"/","status":200}',                       # 欠落
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"/","status":"200","duration_ms":1}',     # 型
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"/","status":true,"duration_ms":1}',      # bool
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"/","status":200,"duration_ms":-1}',      # 負
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"/","status":999,"duration_ms":1}',       # 範囲外
            '{"ts":"2026-09-01T10:00:00","method":"GET","path":"/","status":200,"duration_ms":1}',        # TZ なし
            '{"ts":"yesterday","method":"GET","path":"/","status":200,"duration_ms":1}',
            '{"ts":"2026-09-01T10:00:00Z","method":"GET","path":"api","status":200,"duration_ms":1}',     # / なし
            '{"ts":"2026-09-01T10:00:00Z","method":"","path":"/","status":200,"duration_ms":1}',
        ]
        for line in bad:
            self.assertIsNone(parse_line(line), line)

    def test_parse_fixture(self):
        records, errors = load()
        self.assertEqual((len(records), errors), (1006, 6), "壊れた 6 行は数えて読み飛ばす")
        self.assertEqual(parse_logs(["", "  "]), ([], 0), "空行はエラーに数えない")

    def test_normalize_path(self):
        cases = {
            "/api/items/123": "/api/items/{id}",
            "/api/items/123?ref=home": "/api/items/{id}",
            "/api/search?q=shoes": "/api/search",
            "/api/orders/3f0c2a8e-9d1b-4c6e-8f7a-1b2c3d4e5f60": "/api/orders/{uuid}",
            "/api/users/42/orders/7": "/api/users/{id}/orders/{id}",
            "/api/items/": "/api/items",
            "/": "/",
            "/api/v2/items": "/api/v2/items",
            "/healthz#x": "/healthz",
        }
        for raw, expected in cases.items():
            self.assertEqual(normalize_path(raw), expected, raw)

    def test_normalization_bounds_cardinality(self):
        records, _ = load()
        raw_paths = {r.path for r in records}
        endpoints = {endpoint_of(r) for r in records}
        self.assertGreater(len(raw_paths), 500, "生のパスをラベルにすると系列が爆発する")
        self.assertEqual(endpoints, {"GET /api/items/{id}", "GET /api/orders/{uuid}", "GET /api/search",
                                     "GET /healthz", "POST /api/checkout"})


class TestExercise4Red(unittest.TestCase):
    def test_percentile_nearest_rank(self):
        values = [15, 20, 35, 40, 50]
        self.assertEqual(percentile(values, 30), 20)
        self.assertEqual(percentile(values, 40), 20)
        self.assertEqual(percentile(values, 50), 35)
        self.assertEqual(percentile(values, 100), 50)
        self.assertEqual(percentile([7], 99), 7)
        with self.assertRaises(ValueError):
            percentile([], 50)
        with self.assertRaises(ValueError):
            percentile([1], 0)

    def test_red_by_endpoint(self):
        records, _ = load()
        stats = red_by_endpoint(records, window_seconds=600)
        self.assertEqual(list(stats), sorted(stats), "エンドポイント名の順")
        checkout = stats["POST /api/checkout"]
        self.assertIsInstance(checkout, EndpointStats)
        self.assertEqual((checkout.count, checkout.errors), (96, 8))
        self.assertAlmostEqual(checkout.error_ratio, 8 / 96)
        self.assertAlmostEqual(checkout.rate_per_sec, 96 / 600)
        self.assertEqual((checkout.p50, checkout.p95, checkout.p99), (219.8, 2320.9, 2908.3))
        items = stats["GET /api/items/{id}"]
        self.assertEqual((items.count, items.errors, items.p95), (408, 0, 47.9), "404 はサーバーのエラーではない")
        search = stats["GET /api/search"]
        self.assertEqual((search.count, search.errors, search.p99), (374, 1, 166.7))
        with self.assertRaises(ValueError):
            red_by_endpoint(records, 0)

    def test_per_minute_shows_the_incident(self):
        records, _ = load()
        minutes = per_minute(records)
        self.assertEqual(list(minutes)[0], "2026-09-01T10:00Z")
        self.assertEqual(len(minutes), 10)
        errors = [minutes[m]["POST /api/checkout"].errors for m in minutes]
        self.assertEqual(errors, [0, 0, 0, 0, 3, 1, 4, 0, 0, 0], "10:04〜10:06 に決済のエラーが集中している")
        p95 = minutes["2026-09-01T10:06Z"]["POST /api/checkout"].p95
        self.assertEqual(p95, 2908.3)
        self.assertAlmostEqual(minutes["2026-09-01T10:00Z"]["GET /healthz"].rate_per_sec, 6 / 60)

    def test_top_offenders(self):
        records, _ = load()
        self.assertEqual(top_offenders(records, "client_ip", "requests", 2), [("198.51.100.23", 180), ("10.0.0.2", 60)])
        self.assertEqual(top_offenders(records, "client_ip", "client_errors", 1), [("198.51.100.23", 118)],
                         "スクレイパーが大量の 429 を受けている")
        self.assertEqual(top_offenders(records, "endpoint", "errors"), [("POST /api/checkout", 8), ("GET /api/search", 1)],
                         "値が 0 のものは含めない")
        (top, total), = top_offenders(records, "endpoint", "time", 1)
        self.assertEqual(top, "POST /api/checkout", "件数は少ないが、サーバーの時間を最も使っている")
        self.assertAlmostEqual(total, 54277.9, places=3)
        with self.assertRaises(ValueError):
            top_offenders(records, "user", "requests")
        with self.assertRaises(ValueError):
            top_offenders(records, "endpoint", "latency")

    def test_slowest_gives_trace_ids(self):
        records, _ = load()
        self.assertEqual(slowest(records, 2), [
            (2908.3, "POST /api/checkout", "20d5f9613304bb84b9b4e8d8da0e395a"),
            (2629.9, "POST /api/checkout", "fdf8672121d889daa0478dfe2b41a63f"),
        ])


if __name__ == "__main__":
    unittest.main()
