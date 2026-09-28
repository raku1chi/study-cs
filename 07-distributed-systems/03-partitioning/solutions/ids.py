"""7.3 パーティショニング — 演習: 分散 ID 生成（Snowflake と UUIDv7）（解答例）

演習の仕様は exercises/ids.py の docstring を参照してください。
"""
from __future__ import annotations

import secrets
import time
import uuid
from typing import Callable, NamedTuple

# ---------------------------------------------------------------------------
# 演習4: Snowflake 形式の 64 ビット ID
# ---------------------------------------------------------------------------

DEFAULT_EPOCH_MS = 1_577_836_800_000  # 2020-01-01T00:00:00Z
TIMESTAMP_BITS = 41
WORKER_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_BITS) - 1  # 1023
SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1  # 4095


class ClockMovedBackwardsError(RuntimeError):
    pass


class SnowflakeParts(NamedTuple):
    timestamp_ms: int
    worker_id: int
    sequence: int


def _wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def _sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000)


class SnowflakeGenerator:
    def __init__(
        self,
        worker_id: int,
        *,
        epoch_ms: int = DEFAULT_EPOCH_MS,
        clock_ms: Callable[[], int] = _wall_clock_ms,
        sleep_ms: Callable[[int], None] = _sleep_ms,
        max_backward_ms: int = 10,
    ) -> None:
        if not 0 <= worker_id <= MAX_WORKER_ID:
            raise ValueError(f"worker_id は 0〜{MAX_WORKER_ID} です: {worker_id}")
        if max_backward_ms < 0:
            raise ValueError(f"max_backward_ms は 0 以上です: {max_backward_ms}")
        self.worker_id = worker_id
        self.epoch_ms = epoch_ms
        self.clock_ms = clock_ms
        self.sleep_ms = sleep_ms
        self.max_backward_ms = max_backward_ms
        self._last_ts = -1
        self._sequence = 0

    def next_id(self) -> int:
        ts = self.clock_ms()
        if ts < self._last_ts:
            behind = self._last_ts - ts
            if behind > self.max_backward_ms:
                # 大きく戻った時計を待つと、その間 ID を出せない。黙って続けると重複する。止めて知らせる
                raise ClockMovedBackwardsError(f"時計が {behind} ms 戻りました")
            while ts < self._last_ts:  # 小さな巻き戻りは、追いつくまで待つ
                self.sleep_ms(self._last_ts - ts)
                ts = self.clock_ms()
        if ts - self.epoch_ms < 0:
            raise ValueError("時計がエポックより前を指しています")
        if ts - self.epoch_ms >= 1 << TIMESTAMP_BITS:
            raise OverflowError("41 ビットのタイムスタンプを使い切りました")
        if ts == self._last_ts:
            self._sequence = (self._sequence + 1) & SEQUENCE_MASK
            if self._sequence == 0:
                # 同じミリ秒で 4096 個を使い切った。次のミリ秒まで待つ
                while ts <= self._last_ts:
                    self.sleep_ms(1)
                    ts = self.clock_ms()
        else:
            self._sequence = 0
        self._last_ts = ts
        return ((ts - self.epoch_ms) << (WORKER_BITS + SEQUENCE_BITS)) | (
            self.worker_id << SEQUENCE_BITS
        ) | self._sequence


def decode_snowflake(snowflake_id: int, epoch_ms: int = DEFAULT_EPOCH_MS) -> SnowflakeParts:
    if not 0 <= snowflake_id < 1 << 63:
        raise ValueError(f"63 ビットの非負整数ではありません: {snowflake_id}")
    return SnowflakeParts(
        timestamp_ms=(snowflake_id >> (WORKER_BITS + SEQUENCE_BITS)) + epoch_ms,
        worker_id=(snowflake_id >> SEQUENCE_BITS) & MAX_WORKER_ID,
        sequence=snowflake_id & SEQUENCE_MASK,
    )


# ---------------------------------------------------------------------------
# 演習5: UUIDv7（RFC 9562）
# ---------------------------------------------------------------------------

RAND_BITS = 74  # rand_a (12) + rand_b (62)


def uuid7_from_parts(unix_ts_ms: int, rand_a: int, rand_b: int) -> uuid.UUID:
    if not 0 <= unix_ts_ms < 1 << 48:
        raise ValueError(f"unix_ts_ms は 48 ビットです: {unix_ts_ms}")
    if not 0 <= rand_a < 1 << 12:
        raise ValueError(f"rand_a は 12 ビットです: {rand_a}")
    if not 0 <= rand_b < 1 << 62:
        raise ValueError(f"rand_b は 62 ビットです: {rand_b}")
    value = (
        (unix_ts_ms << 80)  # 上位 48 ビット: ミリ秒の UNIX 時間（ビッグエンディアン → 時刻順に並ぶ）
        | (0x7 << 76)  # version = 7
        | (rand_a << 64)
        | (0b10 << 62)  # variant = RFC 9562（RFC 4122 と同じ 10xx）
        | rand_b
    )
    return uuid.UUID(int=value)


def uuid7_timestamp_ms(u: uuid.UUID) -> int:
    if u.version != 7:
        raise ValueError(f"UUIDv7 ではありません（version={u.version}）")
    return u.int >> 80


class UUIDv7Generator:
    def __init__(
        self,
        clock_ms: Callable[[], int] = _wall_clock_ms,
        randbits: Callable[[int], int] = secrets.randbits,
    ) -> None:
        self.clock_ms = clock_ms
        self.randbits = randbits
        self._last_ts = -1
        self._rand = 0

    def new(self) -> uuid.UUID:
        ts = self.clock_ms()
        if not 0 <= ts < 1 << 48:
            raise ValueError(f"時計の値が範囲外です: {ts}")
        if ts > self._last_ts:
            self._last_ts = ts
            self._rand = self.randbits(RAND_BITS)
        else:
            # 同じミリ秒、または時計が戻った: 最後のタイムスタンプを使い続け、乱数部をカウンタとして 1 増やす
            self._rand += 1
            if self._rand >= 1 << RAND_BITS:
                # あふれたらタイムスタンプを実時刻より先に 1 ms 進め、乱数部を引き直す
                self._last_ts += 1
                self._rand = self.randbits(RAND_BITS)
        return uuid7_from_parts(self._last_ts, self._rand >> 62, self._rand & ((1 << 62) - 1))
