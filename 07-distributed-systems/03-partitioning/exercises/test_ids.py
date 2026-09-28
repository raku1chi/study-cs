"""7.3 パーティショニング — 分散 ID 生成のテスト

実行: python3 tools/check.py 7.3   （またはこのディレクトリで python3 -m unittest -v test_ids）

時計と sleep を注入するので、テストは実時間を待ちません。
"""
import random
import unittest
import uuid

from ids import (
    DEFAULT_EPOCH_MS,
    ClockMovedBackwardsError,
    SnowflakeGenerator,
    SnowflakeParts,
    UUIDv7Generator,
    decode_snowflake,
    uuid7_from_parts,
    uuid7_timestamp_ms,
)


class FakeClock:
    """ミリ秒の整数を返す偽の時計。sleep(ms) で時計が ms だけ進む。"""

    def __init__(self, now_ms: int) -> None:
        self.now = now_ms
        self.sleeps: list[int] = []

    def __call__(self) -> int:
        return self.now

    def sleep(self, ms: int) -> None:
        self.sleeps.append(ms)
        self.now += ms


def make_gen(worker_id: int = 5, start_offset: int = 1000, **kwargs):
    clock = FakeClock(DEFAULT_EPOCH_MS + start_offset)
    gen = SnowflakeGenerator(worker_id, clock_ms=clock, sleep_ms=clock.sleep, **kwargs)
    return gen, clock


class TestExercise4Snowflake(unittest.TestCase):
    def test_bit_layout(self):
        gen, _ = make_gen(worker_id=5, start_offset=1000)
        first = gen.next_id()
        self.assertEqual(first, (1000 << 22) | (5 << 12) | 0)
        self.assertEqual(gen.next_id(), (1000 << 22) | (5 << 12) | 1, "同じミリ秒ではシーケンスが増える")
        self.assertEqual(decode_snowflake(first), SnowflakeParts(DEFAULT_EPOCH_MS + 1000, 5, 0))

    def test_sequence_resets_each_millisecond(self):
        gen, clock = make_gen()
        gen.next_id()
        gen.next_id()
        clock.now += 1
        self.assertEqual(decode_snowflake(gen.next_id()).sequence, 0)

    def test_sequence_exhaustion_waits_for_next_millisecond(self):
        gen, clock = make_gen()
        start = clock.now
        ids = [gen.next_id() for _ in range(4097)]
        self.assertEqual(len(set(ids)), 4097)
        self.assertEqual(ids, sorted(ids))
        last = decode_snowflake(ids[-1])
        self.assertEqual((last.timestamp_ms, last.sequence), (start + 1, 0), "4097 個目は次のミリ秒")
        self.assertEqual(decode_snowflake(ids[-2]).sequence, 4095)
        self.assertTrue(clock.sleeps, "使い切ったら sleep で次のミリ秒を待つ")

    def test_monotonic_under_irregular_clock(self):
        gen, clock = make_gen(max_backward_ms=10)
        rng = random.Random(1)
        ids = []
        for _ in range(10_000):
            r = rng.random()
            if r < 0.3:
                clock.now += rng.randrange(1, 4)
            elif r < 0.33:
                clock.now -= rng.randrange(1, 6)  # NTP の補正などで少しだけ戻る
            ids.append(gen.next_id())
        self.assertEqual(len(set(ids)), len(ids), "重複しない")
        self.assertTrue(all(a < b for a, b in zip(ids, ids[1:])), "狭義単調増加")

    def test_small_backward_step_waits(self):
        gen, clock = make_gen(max_backward_ms=10)
        a = gen.next_id()
        clock.now -= 3
        b = gen.next_id()
        self.assertGreater(b, a)
        self.assertIn(3, clock.sleeps, "戻った分だけ待つ")

    def test_large_backward_jump_raises_and_recovers(self):
        gen, clock = make_gen(max_backward_ms=10)
        a = gen.next_id()
        clock.now -= 1000
        with self.assertRaises(ClockMovedBackwardsError):
            gen.next_id()
        clock.now += 1001
        self.assertGreater(gen.next_id(), a, "時計が追いつけば、また単調に発行できる")
        self.assertTrue(issubclass(ClockMovedBackwardsError, RuntimeError))

    def test_workers_do_not_collide(self):
        g1, _ = make_gen(worker_id=1)
        g2, _ = make_gen(worker_id=2)
        ids1 = {g1.next_id() for _ in range(100)}
        ids2 = {g2.next_id() for _ in range(100)}
        self.assertFalse(ids1 & ids2)
        self.assertEqual({decode_snowflake(i).worker_id for i in ids2}, {2})

    def test_validation(self):
        for worker in (-1, 1024):
            with self.assertRaises(ValueError):
                SnowflakeGenerator(worker)
        with self.assertRaises(ValueError):
            make_gen(max_backward_ms=-1)
        gen, _ = make_gen(start_offset=-1)
        with self.assertRaises(ValueError, msg="エポックより前の時刻"):
            gen.next_id()
        gen, _ = make_gen(start_offset=1 << 41)
        with self.assertRaises(OverflowError):
            gen.next_id()
        gen, _ = make_gen(start_offset=(1 << 41) - 1, worker_id=1023)
        self.assertLess(gen.next_id(), 1 << 63, "符号付き 64 ビット整数に収まる")
        for bad in (-1, 1 << 63):
            with self.assertRaises(ValueError):
                decode_snowflake(bad)

    def test_custom_epoch(self):
        clock = FakeClock(1_000_000_000_500)
        gen = SnowflakeGenerator(3, epoch_ms=1_000_000_000_000, clock_ms=clock, sleep_ms=clock.sleep)
        sid = gen.next_id()
        self.assertEqual(sid >> 22, 500)
        self.assertEqual(decode_snowflake(sid, epoch_ms=1_000_000_000_000).timestamp_ms, 1_000_000_000_500)


class SeqRand:
    """テスト用の randbits。与えた値を順に返す（尽きたら 0）。"""

    def __init__(self, values):
        self.values = list(values)
        self.calls: list[int] = []

    def __call__(self, bits: int) -> int:
        self.calls.append(bits)
        return self.values.pop(0) if self.values else 0


class TestExercise5UUIDv7(unittest.TestCase):
    def test_rfc9562_example_value(self):
        u = uuid7_from_parts(0x017F22E279B0, 0xCC3, 0x18C4DC0C0C07398F)
        self.assertEqual(u, uuid.UUID("017f22e2-79b0-7cc3-98c4-dc0c0c07398f"))
        self.assertEqual(u.version, 7)
        self.assertEqual(u.variant, uuid.RFC_4122)
        self.assertEqual(uuid7_timestamp_ms(u), 0x017F22E279B0)

    def test_field_boundaries(self):
        lo = uuid7_from_parts(0, 0, 0)
        hi = uuid7_from_parts((1 << 48) - 1, (1 << 12) - 1, (1 << 62) - 1)
        self.assertEqual(str(lo), "00000000-0000-7000-8000-000000000000")
        self.assertEqual(str(hi), "ffffffff-ffff-7fff-bfff-ffffffffffff")
        for args in [(-1, 0, 0), (1 << 48, 0, 0), (0, 1 << 12, 0), (0, -1, 0), (0, 0, 1 << 62), (0, 0, -1)]:
            with self.assertRaises(ValueError, msg=str(args)):
                uuid7_from_parts(*args)

    def test_timestamp_rejects_other_versions(self):
        with self.assertRaises(ValueError):
            uuid7_timestamp_ms(uuid.uuid4())

    def test_generator_sets_version_variant_and_time(self):
        clock = FakeClock(1_700_000_000_000)
        gen = UUIDv7Generator(clock_ms=clock, randbits=random.Random(1).getrandbits)
        for _ in range(100):
            clock.now += 1
            u = gen.new()
            self.assertEqual((u.version, u.variant), (7, uuid.RFC_4122))
            self.assertEqual(uuid7_timestamp_ms(u), clock.now)

    def test_uses_74_random_bits_on_new_millisecond(self):
        clock = FakeClock(1_700_000_000_000)
        rand = SeqRand([(0xABC << 62) | 12345])
        u = UUIDv7Generator(clock_ms=clock, randbits=rand).new()
        self.assertEqual(rand.calls, [74])
        self.assertEqual((u.int >> 64) & 0xFFF, 0xABC, "上位 12 ビットが rand_a")
        self.assertEqual(u.int & ((1 << 62) - 1), 12345, "下位 62 ビットが rand_b")

    def test_same_millisecond_increments_random_part(self):
        clock = FakeClock(1_700_000_000_000)
        rand = SeqRand([100])
        gen = UUIDv7Generator(clock_ms=clock, randbits=rand)
        a, b, c = gen.new(), gen.new(), gen.new()
        self.assertEqual((b.int - a.int, c.int - b.int), (1, 1))
        self.assertEqual(len(rand.calls), 1, "同じミリ秒では乱数を引き直さない")

    def test_counter_rollover_advances_timestamp(self):
        clock = FakeClock(1_700_000_000_000)
        rand = SeqRand([(1 << 74) - 1, 7])
        gen = UUIDv7Generator(clock_ms=clock, randbits=rand)
        a = gen.new()
        b = gen.new()  # 乱数部があふれる
        self.assertEqual(uuid7_timestamp_ms(b), clock.now + 1, "タイムスタンプを 1 ms 先に進める")
        self.assertGreater(b.int, a.int)
        c = gen.new()  # 時計はまだ元のミリ秒 → 進めたタイムスタンプを使い続ける
        self.assertEqual(c.int, b.int + 1)

    def test_monotonic_even_when_clock_goes_backwards(self):
        clock = FakeClock(1_700_000_000_000)
        rng = random.Random(2)
        gen = UUIDv7Generator(clock_ms=clock, randbits=rng.getrandbits)
        ids = []
        for _ in range(10_000):
            r = rng.random()
            if r < 0.3:
                clock.now += rng.randrange(1, 3)
            elif r < 0.35:
                clock.now -= rng.randrange(1, 50)
            ids.append(gen.new())
        ints = [u.int for u in ids]
        self.assertTrue(all(a < b for a, b in zip(ints, ints[1:])), "UUID は生成順に厳密に増加する")
        strs = [str(u) for u in ids]
        self.assertEqual(strs, sorted(strs), "文字列の辞書順も生成順と一致する（インデックスの局所性）")

    def test_default_generator_works_with_real_clock(self):
        gen = UUIDv7Generator()
        a, b = gen.new(), gen.new()
        self.assertLess(a.int, b.int)
        self.assertEqual(a.version, 7)


if __name__ == "__main__":
    unittest.main()
