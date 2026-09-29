"""4.4 並行処理と同期 — 演習: 同期プリミティブ・デッドロック・非同期の並行数制限

各関数・クラスの docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.4          # 合格数を表示（interleave.py の演習5も含む）
    python3 tools/check.py -v 4.4       # 各テストの結果を詳しく表示
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_sync_lab

演習の一覧:
    演習1（★★☆）: BoundedBlockingQueue — 条件変数による有界ブロッキングキュー
    演習2（★★★）: ReadWriteLock — 書き込み優先の読み書きロック
    演習3（★★☆）: build_wait_for_graph / find_deadlock / transfer — デッドロックの検出と回避
    演習4（★★☆）: gather_with_concurrency_limit — asyncio で並行数を制限する

制約（学びのための縛り）:
    - 演習1・2 では queue モジュールを使わないでください。threading.Lock と threading.Condition で作ります。
    - 演習4 では asyncio.Semaphore を使っても使わなくても構いません（解答例はワーカーを limit 個だけ作る方式）。

テストはスレッドにタイムアウトを付けているので、デッドロックしても止まらずに失敗として報告されます。
"""
from __future__ import annotations

import asyncio  # noqa: F401
import contextlib
import threading
import time  # noqa: F401  タイムアウトの計算に time.monotonic() を使います
from collections import deque  # noqa: F401
from typing import Any, Awaitable, Generic, Hashable, Iterable, Iterator, Mapping, TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 演習1（★★☆）: 有界ブロッキングキュー
# ---------------------------------------------------------------------------

class QueueClosed(Exception):
    """閉じられたキューに put した、または閉じられて空になったキューから get した。"""


class BoundedBlockingQueue(Generic[T]):
    """容量 capacity の FIFO キュー。生産者・消費者パターンの基本部品。

    - put(item, timeout=None): 満杯なら空きができるまで待ってから末尾に追加する。
        * timeout 秒以内に追加できなければ TimeoutError（timeout=0 なら待たずに判定）。
        * キューが閉じられていたら（待っている途中で閉じられた場合も）QueueClosed。
    - get(timeout=None): 空なら要素が来るまで待ってから先頭を取り出す。
        * timeout 秒以内に取り出せなければ TimeoutError。
        * 閉じられた後でも、残っている要素は取り出せる。閉じられていて空なら QueueClosed。
    - close(): キューを閉じ、待っているすべてのスレッドを起こす。
    - closed: 閉じられているか。len(q): 現在の要素数。
    - capacity < 1 なら ValueError。

    ヒント:
        - 1 つの threading.Lock を共有する 2 つの threading.Condition（「空でない」「満杯でない」）を使う。
        - 条件は **while ループで** 確かめ直すこと。wait() から戻っても、条件が満たされているとは限らない
          （他のスレッドに先を越された、あるいは見せかけの起床（spurious wakeup）がありうる）。
        - タイムアウトは「締め切り時刻 = time.monotonic() + timeout」を最初に計算し、
          wait() に残り時間を渡す。ループで何度も待つので、毎回 timeout を渡すと合計が長くなる。
    """

    def __init__(self, capacity: int) -> None:
        raise NotImplementedError("演習1: BoundedBlockingQueue.__init__ を実装してください")

    def put(self, item: T, timeout: float | None = None) -> None:
        raise NotImplementedError("演習1: put を実装してください")

    def get(self, timeout: float | None = None) -> T:
        raise NotImplementedError("演習1: get を実装してください")

    def close(self) -> None:
        raise NotImplementedError("演習1: close を実装してください")

    @property
    def closed(self) -> bool:
        raise NotImplementedError("演習1: closed を実装してください")

    def __len__(self) -> int:
        raise NotImplementedError("演習1: __len__ を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★★）: 書き込み優先の読み書きロック
# ---------------------------------------------------------------------------

class ReadWriteLock:
    """複数の読み手が同時に入れるが、書き手は 1 人だけで、書き手がいる間は誰も入れないロック。

    書き込み優先（writer-preferring）: 書き込みを **待っている** スレッドが 1 人でもいれば、
    新しい読み手は待たされる（すでに読み取り中の読み手はそのまま続ける）。こうしないと、
    読み手が途切れない限り書き手が永遠に入れない（飢餓）。

    - acquire_read(timeout=None) -> bool / acquire_write(timeout=None) -> bool:
        取得できたら True。timeout 秒以内に取得できなければ False（例外ではない）。
    - release_read() / release_write(): 解放する。保持していないのに呼ばれたら RuntimeError
      （読み取りは「読み取り中の数が 0 なのに解放」、書き込みは「書き手がいないのに解放」を検出すればよい）。
    - read_locked() / write_locked(): with 文で使うためのコンテキストマネージャ（実装済み）。
    - 再入（同じスレッドが保持中に再び取得すること）は考えなくてよい。

    注意: 書き手がタイムアウトで諦めたときは「待っている書き手」の数を必ず戻し、そのせいで
    待たされていた読み手を起こすこと（テストで確かめます）。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習2: ReadWriteLock.__init__ を実装してください")

    def acquire_read(self, timeout: float | None = None) -> bool:
        raise NotImplementedError("演習2: acquire_read を実装してください")

    def release_read(self) -> None:
        raise NotImplementedError("演習2: release_read を実装してください")

    def acquire_write(self, timeout: float | None = None) -> bool:
        raise NotImplementedError("演習2: acquire_write を実装してください")

    def release_write(self) -> None:
        raise NotImplementedError("演習2: release_write を実装してください")

    @contextlib.contextmanager
    def read_locked(self) -> Iterator[None]:
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextlib.contextmanager
    def write_locked(self) -> Iterator[None]:
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()


# ---------------------------------------------------------------------------
# 演習3（★★☆）: デッドロックの検出と回避
# ---------------------------------------------------------------------------

def build_wait_for_graph(
    holders: Mapping[Hashable, Hashable], waiting: Mapping[Hashable, Hashable]
) -> dict[Hashable, set[Hashable]]:
    """ロックの保持・待ちの状況から、待ちグラフ（wait-for graph）を作る。

    holders: ロック -> それを保持しているスレッド
    waiting: スレッド -> それが取得を待っているロック
    戻り値: スレッド -> そのスレッドが待っている相手（スレッド）の集合
            誰も保持していないロックを待っているスレッドは、辺を持たない（キーに含めない）。
            自分が保持しているロックを待っている場合は、自分への辺（自己ループ）になる。

    >>> build_wait_for_graph({"A": "T1", "B": "T2"}, {"T1": "B", "T2": "A"})
    {'T1': {'T2'}, 'T2': {'T1'}}
    """
    raise NotImplementedError("演習3: build_wait_for_graph を実装してください")


def find_deadlock(wait_for: Mapping[Hashable, Iterable[Hashable]]) -> list[Hashable] | None:
    """待ちグラフに循環があれば、その循環を 1 つ返す。なければ None。

    戻り値の [a, b, c] は a→b→c→a という循環を表す（同じノードは 1 回だけ含める）。
    どの循環を返してもよい。辺の先にだけ現れ、キーにないノードは「誰も待っていない」ノード。

    >>> find_deadlock({"T1": ["T2"], "T2": ["T3"], "T3": ["T1"]})
    ['T1', 'T2', 'T3']

    ヒント: 深さ優先探索で「今たどっている経路上」のノードに戻ってきたら循環。
    ノードを「未訪問・経路上・探索済み」の 3 色で管理する。2 万個のノードが一列に並んだ
    グラフでもエラーにならないよう、再帰ではなく自前のスタックで探索すること。
    """
    raise NotImplementedError("演習3: find_deadlock を実装してください")


class InsufficientFunds(Exception):
    pass


class Account:
    """口座。id は口座ごとに一意な整数。lock はこの口座の残高を守るロック（実装済み）。"""

    def __init__(self, account_id: int, balance: int = 0) -> None:
        self.id = account_id
        self.balance = balance
        self.lock = threading.Lock()


def transfer(src: Account, dst: Account, amount: int) -> None:
    """src から dst へ amount を送金する。多数のスレッドから同時に呼ばれてもデッドロックしないこと。

    - 両方の口座のロックを取ってから、残高の確認と更新を行う。
    - デッドロックを防ぐため、ロックは **常に id の小さい口座から** 取る（ロックの順序付け）。
      「src のロック → dst のロック」の順だと、A→B と B→A の送金が同時に起きたときに循環待ちになる。
    - amount <= 0、または同じ口座どうし（src is dst または同じ id）なら ValueError。
    - 残高不足なら InsufficientFunds（残高は変えない）。
    """
    raise NotImplementedError("演習3: transfer を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: asyncio で並行数を制限しつつ、順序を保って結果を集める
# ---------------------------------------------------------------------------

async def gather_with_concurrency_limit(
    aws: Iterable[Awaitable[Any]],
    limit: int,
    *,
    timeout: float | None = None,
    return_exceptions: bool = False,
) -> list[Any]:
    """aws（コルーチンなど）を同時に最大 limit 個まで実行し、結果を **入力と同じ順序で** 返す。

    外部 API を叩く処理を「並行数 10 まで」に抑えたいときなどに使う。asyncio.gather は全部を
    同時に始めてしまうので、相手のサーバーや接続プールを溢れさせることがある。

    - 同時に実行中の数は limit を超えず、仕事が残っている限り limit 個まで使い切ること。
    - timeout が指定されたら、各仕事に「実際に始まってから」timeout 秒の制限をかける
      （asyncio.wait_for）。超えたら asyncio.TimeoutError。
    - return_exceptions=True: 例外（タイムアウトを含む）をその位置の結果として返し、他は続ける。
    - return_exceptions=False: 最初の例外をそのまま送出する。その際、実行中の仕事はキャンセルし、
      まだ始めていない仕事は始めない（コルーチンは close() して「await されなかった」警告を防ぐ）。
    - aws が空なら []。limit < 1 なら ValueError。

    >>> async def square(x):
    ...     await asyncio.sleep(0.01 * (3 - x))
    ...     return x * x
    >>> asyncio.run(gather_with_concurrency_limit([square(i) for i in range(3)], 2))
    [0, 1, 4]

    ヒント（どちらでもよい）:
        (a) asyncio.Semaphore(limit) を使い、各仕事を `async with sem:` で包んでから gather する。
        (b) 共有のイテレータ enumerate(aws) から次の仕事を取り出して実行するワーカーを limit 個作る。
            (b) は仕事が 100 万個あってもタスクが limit 個で済む。
    """
    raise NotImplementedError("演習4: gather_with_concurrency_limit を実装してください")
