"""4.1 プロセス・スレッド・システムコール — 演習: シグナルによるグレースフルシャットダウン

`docker stop` や Kubernetes の Pod 削除では、まずプロセスに SIGTERM が送られ、一定時間
（猶予期間）内に終了しなければ SIGKILL で強制終了されます。SIGTERM を受け取ったら
「新しい仕事は受け付けず、処理中の仕事は最後までやり切り、終了コード 0 で終わる」ワーカーを作ります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.1
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_graceful_worker

コマンドラインから試す（Unix）:
    python3 graceful_worker.py 3 3 3 &     # 3 秒かかるジョブを 3 つ処理するワーカー
    kill -TERM %1                          # 処理中のジョブを終えてから終了するはず

ログの形式（テストはこの形式で答え合わせをします）:
    START <n>          n 番目（1 始まり）のジョブを開始した
    DONE <n>           n 番目のジョブを終えた
    SHUTDOWN <理由>     終了する。理由はシグナル名（"SIGTERM" など）か、全ジョブを終えたなら "completed"

main() と print_flush() は実装済みです。GracefulWorker の 3 つのメソッドを実装してください。
"""
from __future__ import annotations

import signal  # noqa: F401
import sys
import time
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def print_flush(line: str) -> None:
    # 標準出力がパイプのときはブロック単位でバッファリングされるので、1 行ごとに flush する
    print(line, flush=True)


# ---------------------------------------------------------------------------
# 演習5（★★☆）: グレースフルシャットダウンするワーカー
# ---------------------------------------------------------------------------

class GracefulWorker:
    """ジョブを 1 つずつ処理し、SIGTERM / SIGINT を受けたら処理中のジョブを終えてから止まるワーカー。

    属性:
        log: ログを 1 行出力する関数（テストではリストの append に差し替えられる）
        stop_requested: 停止が要求されたら True
        stop_signal: 最初に受け取ったシグナルの番号（まだなら None）
    """

    def __init__(self, log: Callable[[str], None] = print_flush) -> None:
        self.log = log
        self.stop_requested = False
        self.stop_signal: int | None = None

    def handle_signal(self, signum: int, frame: object) -> None:
        """シグナルハンドラ。signal.signal() に登録して使う。

        - stop_requested を True にする。
        - stop_signal が None なら signum を記録する（2 回目以降のシグナルでは上書きしない）。
        - **それ以外のことはしない**（ログ出力もしない）。ハンドラは処理の途中に割り込んで
          実行されるので、重い処理や入出力をすると、割り込まれた処理と競合しうる。
        """
        raise NotImplementedError("演習5: handle_signal を実装してください")

    def install(self) -> None:
        """SIGTERM と SIGINT の両方に handle_signal を登録する（signal.signal を使う）。"""
        raise NotImplementedError("演習5: install を実装してください")

    def run(self, jobs: Iterable[T], process: Callable[[T], object]) -> int:
        """jobs を先頭から 1 つずつ process(job) で処理し、終了コード（常に 0）を返す。

        - 各ジョブの前後に "START <n>" と "DONE <n>" をログに出す（n は 1 始まり）。
        - 停止が要求されていたら、次のジョブを **取り出す前に** ループを抜ける。
          jobs はキューのようなもので、取り出したジョブを処理せずに捨てると、そのジョブは失われる。
        - 処理中（process の実行中）に停止が要求されても、そのジョブは最後まで処理する。
        - 最後に "SHUTDOWN <理由>" をログに出す。理由は、停止要求があれば最初のシグナルの名前
          （signal.Signals(番号).name で "SIGTERM" などが得られる）、なければ "completed"。

        >>> lines = []
        >>> GracefulWorker(log=lines.append).run(["a", "b"], print)
        a
        b
        0
        >>> lines
        ['START 1', 'DONE 1', 'START 2', 'DONE 2', 'SHUTDOWN completed']

        ヒント: for 文で jobs を回すと、停止を確認する前に次の要素を取り出してしまう。
        iter() と next() を使うとよい。
        """
        raise NotImplementedError("演習5: run を実装してください")


def main(argv: list[str]) -> int:
    """コマンドライン引数を「ジョブにかかる秒数」の列として、ワーカーを動かす。"""
    durations = [float(a) for a in argv]
    worker = GracefulWorker()
    worker.install()
    # time.sleep はシグナルで中断されても、ハンドラが例外を投げなければ残り時間だけ眠り直す（PEP 475）
    return worker.run(durations, time.sleep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
