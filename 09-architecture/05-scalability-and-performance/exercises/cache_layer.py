"""9.5 スケーラビリティとパフォーマンス — 演習5（★★★）: スタンピードに強いキャッシュ

人気のキーのキャッシュが切れた瞬間、そのキーを求める大量のリクエストが一斉にデータベースへ向かう
「キャッシュスタンピード（thundering herd）」は、キャッシュに頼ったシステムの典型的な障害の引き金です。
この演習では、次の 2 つの対策を組み込んだ読み込み型のキャッシュ（read-through cache）を作ります。

    1. 単一飛行（single-flight, request coalescing）
       同じキーの読み込みが実行中なら、後から来た呼び出しは自分で読み込まず、その結果を待って共有する。
    2. stale-while-revalidate
       有効期限（ttl）を過ぎても、猶予期間（stale_ttl）の間は古い値をすぐ返し、裏で 1 回だけ更新する。

さらに、キャッシュとデータベースの不整合の古典的な原因である「無効化と読み込みの競合」を、
世代番号（generation）で防ぎます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.5

時間は clock（偽の時計を渡せる）で測ります。裏での更新は spawn（タスクを受け取って実行を開始する関数）に
依頼します。既定では新しいスレッドで実行しますが、テストではタスクをリストに溜めて手で実行します。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace  # noqa: F401
from typing import Callable, Generic, TypeVar

V = TypeVar("V")


@dataclass(frozen=True)
class CacheStats:
    """統計（読み取り専用のスナップショット）。

    - hits: 有効期限内の値を返した回数
    - stale_hits: 猶予期間内の古い値を返した回数
    - misses: 値がない、または猶予期間も過ぎていた回数（自分で読み込んだ場合も、待った場合も含む）
    - loads: 呼び出しの中で loader を実行した回数（裏での更新は含まない）
    - coalesced: 実行中の読み込みを待って結果を共有した回数
    - refresh_errors: 裏での更新が失敗した回数
    """

    hits: int = 0
    stale_hits: int = 0
    misses: int = 0
    loads: int = 0
    coalesced: int = 0
    refresh_errors: int = 0


def _start_thread(task: Callable[[], None]) -> None:
    threading.Thread(target=task, daemon=True).start()


class CoalescingCache(Generic[V]):
    """loader(key) で値を読み込むキャッシュ。

    get(key) の規則（age = 現在時刻 − その値を保存した時刻）:
    1. age < ttl: その値を返す（hits）。
    2. ttl <= age < ttl + stale_ttl: その値をすぐ返す（stale_hits）。そのキーの裏での更新が実行中でなければ、
       更新のタスクを spawn に渡す（実行中なら何もしない。更新は 1 キーにつき同時に 1 つまで）。
       更新が成功したら値と保存時刻を置き換える。失敗したら refresh_errors を数え、古い値はそのまま残す
       （次の古い読み取りで、また更新を試みる）。spawn はロックを放してから呼ぶこと
       （spawn がその場でタスクを実行する実装でも、デッドロックしないように）。
    3. 値がない、または age >= ttl + stale_ttl（misses）:
       - そのキーの読み込みが実行中なら、完了を待って同じ結果を返す（coalesced）。
         読み込みが例外で失敗したら、待っていた全員に同じ例外を送出する。
       - 実行中でなければ、自分が読み込む（loads）。loader はロックの外で呼ぶこと。
         成功したら保存して返す。例外なら保存せず（失敗はキャッシュしない）、そのまま送出する。
    invalidate(key): 値を消し、そのキーの世代番号を 1 進める。読み込み・更新は開始時の世代番号を覚えておき、
    完了時に世代番号が変わっていたら、結果を保存しない（読み込み中に DB が更新されて無効化された場合に、
    古い値でキャッシュを上書きしないため）。ただし、待っていた呼び出しにはその結果を返してよい。
    waiting_count(key): 実行中の読み込みを今待っている呼び出しの数（テスト・監視用）。
    ttl は正、stale_ttl は 0 以上（違反は ValueError）。
    """

    def __init__(
        self,
        loader: Callable[[str], V],
        *,
        ttl: float,
        stale_ttl: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] = _start_thread,
    ) -> None:
        raise NotImplementedError("演習5: CoalescingCache.__init__ を実装してください")

    @property
    def stats(self) -> CacheStats:
        raise NotImplementedError("演習5: CoalescingCache.stats を実装してください")

    def get(self, key: str) -> V:
        raise NotImplementedError("演習5: CoalescingCache.get を実装してください")

    def invalidate(self, key: str) -> None:
        raise NotImplementedError("演習5: CoalescingCache.invalidate を実装してください")

    def waiting_count(self, key: str) -> int:
        raise NotImplementedError("演習5: CoalescingCache.waiting_count を実装してください")
