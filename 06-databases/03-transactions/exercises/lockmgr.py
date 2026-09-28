"""6.3 トランザクションと同時実行制御 — 演習2: ロックマネージャとデッドロック検出

2 相ロック（2PL）方式の DBMS の中にある「ロックマネージャ」を実装します。
共有ロック（S）と排他ロック（X）、ロックの昇格、先着順（FIFO）の待ち行列、
待ちグラフ（wait-for graph）によるデッドロックの検出を扱います。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.3
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_lockmgr

時間の流れはテストが 1 ステップずつ進めます（スレッドは使いません）。例:
    lm = LockManager()
    lm.acquire(1, "A", "X")   # → "granted"
    lm.acquire(2, "A", "S")   # → "waiting"（T1 の X と両立しない）
    lm.release_all(1)         # → [2]（T1 のコミットで T2 に S が与えられた）

約束:
    - トランザクションは整数の番号で表す。番号が大きいほど後に始まった（若い）とみなす。
    - 互換性: S と S は両立する。それ以外（S と X、X と S、X と X）は両立しない。
    - 厳格な 2PL（strict 2PL）: ロックはトランザクションの終わり（release_all）まで保持する。
    - 待ち中のトランザクションは新しい要求を出せない（1 つの要求で待っているため）。
"""
from __future__ import annotations

from dataclasses import dataclass

MODES = ("S", "X")


class LockError(Exception):
    """不正な操作（待ち中・中断済み・終了済みのトランザクションからの要求など）。"""


def compatible(held: str, requested: str) -> bool:
    """互換性の表（提供済み）。held のロックがあるときに requested を与えられるか。

    |        | S 要求 | X 要求 |
    |--------|--------|--------|
    | S 保持 |   ○    |   ×    |
    | X 保持 |   ×    |   ×    |
    """
    return held == "S" and requested == "S"


@dataclass
class Request:
    """待ち行列の 1 つの要求（提供済み）。upgrade は S から X への昇格要求かどうか。"""

    txn: int
    mode: str
    upgrade: bool = False


class LockManager:
    """ロックマネージャ。

    提供済みの属性（使っても、自分の設計に変えてもよい。下の holders / waiters / status は
    この属性を使う前提で書かれている）:
        _holders: {資源: {トランザクション: "S" または "X"}}  保持しているロック
        _queues: {資源: [Request, ...]}                       待ち行列（先頭から順に与える）
        _waiting_on: {トランザクション: 資源}                    待っているトランザクション
        _finished: release_all したトランザクションの集合
        aborted: デッドロックの犠牲として中断したトランザクションの一覧（中断した順）
    """

    def __init__(self) -> None:
        self._holders: dict[str, dict[int, str]] = {}
        self._queues: dict[str, list[Request]] = {}
        self._waiting_on: dict[int, str] = {}
        self._finished: set[int] = set()
        self.aborted: list[int] = []

    # --- 提供済み: 状態の参照 --------------------------------------------------

    def holders(self, resource: str) -> dict[int, str]:
        """resource のロックを保持しているトランザクションとモード（番号の昇順）。"""
        return dict(sorted(self._holders.get(resource, {}).items()))

    def waiters(self, resource: str) -> list[tuple[int, str]]:
        """resource の待ち行列（先頭から順に (トランザクション, 要求モード)）。"""
        return [(r.txn, r.mode) for r in self._queues.get(resource, [])]

    def status(self, txn: int) -> str:
        """"running" / "waiting" / "aborted"（デッドロックの犠牲）/ "finished"（release_all 済み）。

        まだ一度も現れていないトランザクションは "running"。
        """
        if txn in self.aborted:
            return "aborted"
        if txn in self._finished:
            return "finished"
        if txn in self._waiting_on:
            return "waiting"
        return "running"

    # -----------------------------------------------------------------------
    # 演習2-1（★★☆）: ロックの獲得と解放
    # -----------------------------------------------------------------------

    def acquire(self, txn: int, resource: str, mode: str) -> str:
        """txn が resource に mode（"S" / "X"）のロックを要求する。

        戻り値:
            "granted" … ロックを得た（すでに十分なロックを持っていた場合も含む）
            "waiting" … 待ち行列に入った
            "aborted" … 待ちがデッドロックを生んだため、txn 自身が犠牲として中断された

        規則:
          - mode が "S" でも "X" でもなければ ValueError。txn が待ち中・中断済み・終了済みなら LockError。
          - すでに X を持っている、または同じモードを持っているなら、すぐ "granted"。
          - S を持っていて X を要求する（昇格）: 保持者が自分だけなら、すぐ X に昇格して "granted"。
            そうでなければ、昇格要求を待ち行列の **先頭** に入れて待つ。
          - 新しい要求: 待ち行列が空で、かつ他の保持者全員と両立するときだけ、すぐ "granted"。
            そうでなければ待ち行列の末尾に入れて待つ（先に待っている要求を追い越さない: FIFO）。
          - 待つことになったら、すぐにデッドロックを検出する（演習2-2）。閉路が見つかったら、
            閉路の中で番号が最も大きい（最も若い）トランザクションを中断する: aborted に加え、
            保持しているロックをすべて解放し、待ち行列から要求を取り除く（解放によって、
            他の待ちが与えられることもある）。閉路がなくなるまで繰り返す。
            要求者自身が中断されたら "aborted"。他が中断された結果ロックを得られたら "granted"。
        """
        raise NotImplementedError("演習2-1: acquire を実装してください")

    def release_all(self, txn: int) -> list[int]:
        """txn の終了（コミットまたはアボート）。すべてのロックを解放し、待ち中の要求も取り消す。

        解放した資源ごとに（資源名の昇順で）、待ち行列の先頭から、与えられる要求を順に与える。
        先頭の要求が与えられなければ、そこで止める（後ろの要求が両立しても追い越さない）。
        昇格要求は、自分以外の保持者がいなくなったら与えられる。

        戻り値: この解放によってロックを得たトランザクションの一覧（与えた順）。
        release_all したトランザクションの状態は "finished" になり、以後の acquire は LockError。
        既に終了・中断しているトランザクションに対しては何もせず [] を返す。
        """
        raise NotImplementedError("演習2-1: release_all を実装してください")

    # -----------------------------------------------------------------------
    # 演習2-2（★★★）: 待ちグラフとデッドロック検出
    # -----------------------------------------------------------------------

    def wait_for_graph(self) -> dict[int, set[int]]:
        """待ちグラフ {待っているトランザクション: {待たされている相手, ...}} を返す。

        待ち行列の各要求 W（モード m）について、次の相手への辺 W → T を張る:
          - 同じ資源の保持者 T（W 自身を除く）で、T の保持モードが m と両立しないもの
          - 同じ待ち行列で W より前にいる要求 T（W 自身を除く）で、T の要求モードが m と両立しないもの
            （FIFO なので、T が先に与えられて解放するまで W は進めない）
        辺のないトランザクションは含めない。キーは番号の昇順。
        """
        raise NotImplementedError("演習2-2: wait_for_graph を実装してください")

    def find_cycle(self, start: int) -> list[int] | None:
        """待ちグラフで start から出発して start に戻る閉路を探し、見つかれば頂点の列を返す。

        結果は [start, v1, v2, ...] の形で、start → v1 → v2 → ... → start が閉路になる。
        深さ優先探索で、隣の頂点は番号の小さい順にたどり、最初に見つかった閉路を返す。
        なければ None。
        """
        raise NotImplementedError("演習2-2: find_cycle を実装してください")
