"""7.4 合意と協調 — 演習: Saga オーケストレーター

マイクロサービスをまたぐ処理（在庫の引き当て → 決済 → 配送の手配）を 2 相コミットで束ねると、
サービス間の結合が強くなり、1 つのサービスの障害が全体を止めます。**Saga**（Garcia-Molina と Salem, 1987）は、
各サービスのローカルなトランザクションを順に実行し、途中で失敗したら、それまでに完了したステップを
**補償トランザクション**（compensating transaction）で逆順に取り消す方式です。

この演習では、中央のオーケストレーターが Saga を進める方式（orchestration）を実装します。

    - ステップを順に実行し、失敗したら完了済みのステップを逆順に補償する
    - 一時的な失敗（RetryableError）は、冪等なステップに限って指定回数まで再試行する
    - 状態を遷移のたびにストアへ保存し、プロセスが落ちても resume で続きから再開できる
    - 補償が失敗し続けたら FAILED にして、人手の介入を待つ

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.4
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_saga

永続化する状態（store.save に渡す dict。JSON にできる値だけで構成する）:
    {
      "status": "RUNNING" | "COMPENSATING" | "COMPLETED" | "COMPENSATED" | "FAILED",
      "ctx": {...},            # ステップ間で受け渡すデータ（ステップが書き込める）
      "completed": [...],      # 完了したステップ名（実行順）
      "compensated": [...],    # 補償し終えたステップ名（補償した順）
      "current": "pay" | None, # 開始を記録したが、完了をまだ記録していないステップ
      "error": str | None      # 失敗の説明
    }
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Sequence

RUNNING = "RUNNING"
COMPENSATING = "COMPENSATING"
COMPLETED = "COMPLETED"
COMPENSATED = "COMPENSATED"
FAILED = "FAILED"


class RetryableError(Exception):
    """一時的な失敗（タイムアウト、一時的な過負荷など）。冪等なステップなら再試行してよい。"""


class SimulatedCrash(BaseException):
    """オーケストレーターのプロセスが落ちたことを表す（テスト用）。

    BaseException のサブクラスなので `except Exception` では捕まらない。捕まえずに外へ伝えること。
    """


@dataclass
class Step:
    """Saga の 1 ステップ。

    action(ctx) を実行し、取り消すときは compensation(ctx) を呼ぶ（None なら取り消すものがない）。
    max_attempts: action を試す最大回数（1 なら再試行しない）。再試行するステップの action は冪等であること。
    """

    name: str
    action: Callable[[dict], None]
    compensation: Callable[[dict], None] | None = None
    max_attempts: int = 1


@dataclass
class SagaResult:
    saga_id: str
    status: str
    completed: list[str]
    compensated: list[str]
    error: str | None
    ctx: dict


class InMemorySagaStore:
    """Saga の状態のストア（実装済み）。JSON に変換して保存するので、実際のデータベースと同じく
    「保存した時点の値のコピー」が残る（保存後に dict を書き換えても、保存済みの内容は変わらない）。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self.saves = 0

    def save(self, saga_id: str, state: dict) -> None:
        self._data[saga_id] = json.dumps(state, ensure_ascii=False)
        self.saves += 1

    def load(self, saga_id: str) -> dict | None:
        raw = self._data.get(saga_id)
        return None if raw is None else json.loads(raw)


# ---------------------------------------------------------------------------
# 演習7（★★☆）: Saga オーケストレーター
# ---------------------------------------------------------------------------


class SagaOrchestrator:
    """Saga を実行・再開するオーケストレーター。

    __init__: ステップ名が重複していたり、max_attempts < 1 のステップがあったり、
              compensation_attempts < 1 なら ValueError。

    start(saga_id, ctx) -> SagaResult:
        - saga_id の状態がすでにストアにあれば ValueError（再開には resume を使う）。
        - ctx を JSON で往復させたコピーを状態の "ctx" にする（JSON にできない値なら TypeError がそのまま出る）。
        - status = RUNNING の初期状態を保存してから、実行を進める。

    resume(saga_id) -> SagaResult:
        ストアから状態を読み、status に応じて続きを実行する（なければ KeyError）。
        RUNNING → 前進を続ける / COMPENSATING・FAILED → 補償を続ける / COMPLETED・COMPENSATED → 何もしない。

    前進（status が RUNNING のとき）:
        ステップを順に見て、completed に入っているものは飛ばす。それ以外のステップについて:
        1. current = ステップ名 にして **保存**（ここで落ちたら、再開時にこのステップをやり直す）
        2. action(ctx) を実行する。
           - RetryableError なら、max_attempts 回まで再試行する。
           - それ以外の Exception なら再試行しない。
           - 失敗が確定したら: status = COMPENSATING、error = ステップ名を含む説明、current = None にして保存し、補償へ。
        3. 成功したら completed に追加し、current = None にして保存。
        全ステップが完了したら status = COMPLETED にして保存。

    補償（status が COMPENSATING か FAILED のとき）:
        - FAILED からの再開なら、まず status = COMPENSATING にして保存する。
        - completed を **逆順** に見て、compensated に入っているものと compensation が None のものは飛ばす。
        - compensation(ctx) を、成功するまで最大 compensation_attempts 回試す（どんな Exception でも再試行）。
          成功したら compensated に追加して保存。
          すべて失敗したら status = FAILED、error = ステップ名を含む説明 にして保存し、そこで止める。
        - 全部終わったら status = COMPENSATED にして保存。

    SagaResult は、最後の状態の status・completed・compensated・error・ctx のコピーで作る。

    注意: SimulatedCrash は捕まえないこと（プロセスが落ちたことを表す）。そのときストアには、
    落ちる直前に保存した状態が残っており、別の SagaOrchestrator インスタンスから resume できなければならない。
    """

    def __init__(
        self, steps: Sequence[Step], store: InMemorySagaStore, compensation_attempts: int = 3
    ) -> None:
        raise NotImplementedError("演習7: SagaOrchestrator.__init__ を実装してください")

    def start(self, saga_id: str, ctx: dict) -> SagaResult:
        raise NotImplementedError("演習7: SagaOrchestrator.start を実装してください")

    def resume(self, saga_id: str) -> SagaResult:
        raise NotImplementedError("演習7: SagaOrchestrator.resume を実装してください")
