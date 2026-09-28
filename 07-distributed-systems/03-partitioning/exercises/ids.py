"""7.3 パーティショニング — 演習: 分散 ID 生成（Snowflake と UUIDv7）

データを複数のノードに分けると、「1 台のデータベースの自動採番」に頼れなくなります。
各ノードが調整なしに、重複せず、しかも時刻順に並ぶ ID を作る代表的な方法が次の 2 つです。

    演習4: Snowflake 形式の 64 ビット ID（Twitter が 2010 年に公開した方式に基づく）
        ┌─┬──────────────────────────────┬────────────┬──────────────┐
        │0│ タイムスタンプ（41 ビット）    │ ワーカー ID │ シーケンス    │
        │ │ エポックからのミリ秒           │ （10 ビット）│ （12 ビット） │
        └─┴──────────────────────────────┴────────────┴──────────────┘
        最上位ビットは 0（符号付き 64 ビット整数として正の値になるように）。

    演習5: UUIDv7（RFC 9562, 2024 年）
        128 ビット = unix_ts_ms（48）| ver = 0111（4）| rand_a（12）| var = 10（2）| rand_b（62）
        先頭がミリ秒の UNIX 時間なので、生成順に並び、B 木インデックスの末尾に追記されやすい。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.3
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_ids

制約: 演習5では、Python 3.14 以降の uuid.uuid7() などの既製の実装は使わず、ビット演算で組み立ててください
（uuid.UUID(int=...) で UUID オブジェクトを作るのは構いません）。
"""
from __future__ import annotations

import secrets
import time
import uuid  # noqa: F401  演習5で使います（uuid.UUID(int=...)）
from typing import Callable, NamedTuple

# ---------------------------------------------------------------------------
# 演習4（★★☆）: Snowflake 形式の 64 ビット ID
# ---------------------------------------------------------------------------

DEFAULT_EPOCH_MS = 1_577_836_800_000  # この演習の既定のエポック: 2020-01-01T00:00:00Z（UNIX 時間のミリ秒）
TIMESTAMP_BITS = 41
WORKER_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_BITS) - 1  # 1023
SEQUENCE_MASK = (1 << SEQUENCE_BITS) - 1  # 4095


class ClockMovedBackwardsError(RuntimeError):
    """時計が許容範囲（max_backward_ms）を超えて戻ったため、ID を発行できない。"""


class SnowflakeParts(NamedTuple):
    timestamp_ms: int  # UNIX 時間のミリ秒（エポックを足し戻した値）
    worker_id: int
    sequence: int


def _wall_clock_ms() -> int:
    return time.time_ns() // 1_000_000


def _sleep_ms(ms: int) -> None:
    time.sleep(ms / 1000)


class SnowflakeGenerator:
    """1 つのワーカー（プロセス）が使う Snowflake ID の生成器。

    ID = ((ts - epoch_ms) << 22) | (worker_id << 12) | sequence

    next_id() の規則:
        1. ts = clock_ms() を読む。
        2. ts が前回のタイムスタンプより小さい（時計が戻った）とき:
             - 戻り幅が max_backward_ms を超えるなら ClockMovedBackwardsError（状態は変えない）。
             - そうでなければ、sleep_ms(前回 - ts) を呼んで clock_ms() を読み直すことを、
               ts が前回以上になるまで繰り返す（小さな巻き戻りは待ってやり過ごす）。
        3. ts - epoch_ms < 0 なら ValueError、>= 2^41 なら OverflowError。
        4. ts が前回と同じミリ秒なら sequence を 1 増やす。4095 を超えて 0 に戻ったら（使い切ったら）、
           sleep_ms(1) と clock_ms() の読み直しを ts が前回より大きくなるまで繰り返し、sequence は 0 のまま。
           ts が前回より大きければ sequence = 0。
        5. 前回のタイムスタンプを ts にして、ID を組み立てて返す。

    こうすると、1 つの生成器が返す ID は重複せず、狭義単調増加になる。

    検証（ValueError）: worker_id が 0〜1023 の範囲外、max_backward_ms < 0。
    clock_ms と sleep_ms は注入できる（テストでは偽の時計を渡す）。

    考えてみよう: なぜ時計は壁時計（UNIX 時間）なのに、戻ったときの対処が必要なのか（7.1 章）。
    ワーカー ID の重複（同じ ID の 2 プロセス）を防ぐには、運用上どうすればよいか。
    """

    def __init__(
        self,
        worker_id: int,
        *,
        epoch_ms: int = DEFAULT_EPOCH_MS,
        clock_ms: Callable[[], int] = _wall_clock_ms,
        sleep_ms: Callable[[int], None] = _sleep_ms,
        max_backward_ms: int = 10,
    ) -> None:
        raise NotImplementedError("演習4: SnowflakeGenerator.__init__ を実装してください")

    def next_id(self) -> int:
        raise NotImplementedError("演習4: SnowflakeGenerator.next_id を実装してください")


def decode_snowflake(snowflake_id: int, epoch_ms: int = DEFAULT_EPOCH_MS) -> SnowflakeParts:
    """ID を (UNIX 時間のミリ秒, ワーカー ID, シーケンス) に分解する。

    snowflake_id が 0〜2^63-1 の範囲外なら ValueError。

    >>> decode_snowflake((1000 << 22) | (5 << 12) | 7, epoch_ms=0)
    SnowflakeParts(timestamp_ms=1000, worker_id=5, sequence=7)
    """
    raise NotImplementedError("演習4: decode_snowflake を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: UUIDv7（RFC 9562）
# ---------------------------------------------------------------------------

RAND_BITS = 74  # rand_a（12 ビット）+ rand_b（62 ビット）


def uuid7_from_parts(unix_ts_ms: int, rand_a: int, rand_b: int) -> uuid.UUID:
    """RFC 9562 のレイアウトで UUIDv7 を組み立てる。

    128 ビットの整数を、上位から次の順に詰める:
        unix_ts_ms（48 ビット）, version = 0b0111（4 ビット）, rand_a（12 ビット）,
        variant = 0b10（2 ビット）, rand_b（62 ビット）
    それぞれの値が範囲外（負、またはビット数を超える）なら ValueError。

    >>> str(uuid7_from_parts(0x017F22E279B0, 0xCC3, 0x18C4DC0C0C07398F))
    '017f22e2-79b0-7cc3-98c4-dc0c0c07398f'
    """
    raise NotImplementedError("演習5: uuid7_from_parts を実装してください")


def uuid7_timestamp_ms(u: uuid.UUID) -> int:
    """UUIDv7 から unix_ts_ms（上位 48 ビット）を取り出す。version が 7 でなければ ValueError。"""
    raise NotImplementedError("演習5: uuid7_timestamp_ms を実装してください")


class UUIDv7Generator:
    """同じプロセス内で、生成順に厳密に増加する UUIDv7 を作る生成器。

    状態: 最後に使ったタイムスタンプ last_ts（初期値 -1）と、74 ビットの乱数部 r（上位 12 ビットが rand_a、
    下位 62 ビットが rand_b）。

    new() の規則:
        1. ts = clock_ms()。0〜2^48-1 の範囲外なら ValueError。
        2. ts > last_ts なら: last_ts = ts、r = randbits(74)（新しいミリ秒では乱数を引き直す）。
        3. そうでない（同じミリ秒、または時計が戻った）なら: last_ts はそのまま、r を 1 増やす。
           r が 2^74 に達したら（あふれたら）、last_ts を 1 増やし（実時刻より先に進める）、r = randbits(74)。
        4. uuid7_from_parts(last_ts, r の上位 12 ビット, r の下位 62 ビット) を返す。

    RFC 9562 は同じミリ秒の中で順序を保つ方法をいくつか挙げており、乱数部をカウンタとして増やすのは
    その一つです（本文 8.3 節）。この演習では増分を 1 にした簡略版を実装します。
    randbits はテストで注入できる（既定は secrets.randbits）。
    """

    def __init__(
        self,
        clock_ms: Callable[[], int] = _wall_clock_ms,
        randbits: Callable[[int], int] = secrets.randbits,
    ) -> None:
        raise NotImplementedError("演習5: UUIDv7Generator.__init__ を実装してください")

    def new(self) -> uuid.UUID:
        raise NotImplementedError("演習5: UUIDv7Generator.new を実装してください")
