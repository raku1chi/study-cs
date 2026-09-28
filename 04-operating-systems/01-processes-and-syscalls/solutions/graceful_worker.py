"""4.1 プロセス・スレッド・システムコール — 解答例: シグナルによるグレースフルシャットダウン

演習の仕様は exercises/graceful_worker.py の docstring を参照してください。

コマンドラインから試す:
    python3 graceful_worker.py 3 3 3 &     # 3 秒かかるジョブを 3 つ処理するワーカー
    kill -TERM %1                          # 処理中のジョブを終えてから終了する
"""
from __future__ import annotations

import signal
import sys
import time
from typing import Callable, Iterable, TypeVar

T = TypeVar("T")


def print_flush(line: str) -> None:
    # 標準出力がパイプのときはブロック単位でバッファリングされるので、1 行ごとに flush する
    print(line, flush=True)


class GracefulWorker:
    def __init__(self, log: Callable[[str], None] = print_flush) -> None:
        self.log = log
        self.stop_requested = False
        self.stop_signal: int | None = None

    def handle_signal(self, signum: int, frame: object) -> None:
        # ハンドラでは「止まってほしい」という事実を記録するだけにする。
        # ここでログ出力・ロック取得・重い後始末をすると、割り込まれた処理との競合や
        # 再入（reentrancy）の問題を起こしうる。実際の後始末はメインの流れで行う
        if self.stop_signal is None:
            self.stop_signal = signum
        self.stop_requested = True

    def install(self) -> None:
        signal.signal(signal.SIGTERM, self.handle_signal)  # kill、docker stop、Kubernetes の Pod 削除
        signal.signal(signal.SIGINT, self.handle_signal)  # 端末での Ctrl-C

    def run(self, jobs: Iterable[T], process: Callable[[T], object]) -> int:
        it = iter(jobs)
        n = 0
        # 停止の確認は「次のジョブを取り出す前」に行う。取り出してから確認すると、
        # キューから取ったジョブを処理せずに捨ててしまう
        while not self.stop_requested:
            try:
                job = next(it)
            except StopIteration:
                break
            n += 1
            self.log(f"START {n}")
            process(job)  # 処理中にシグナルが来ても、このジョブは最後までやり切る
            self.log(f"DONE {n}")
        reason = signal.Signals(self.stop_signal).name if self.stop_signal is not None else "completed"
        self.log(f"SHUTDOWN {reason}")
        return 0


def main(argv: list[str]) -> int:
    durations = [float(a) for a in argv]
    worker = GracefulWorker()
    worker.install()
    # time.sleep はシグナルで中断されても、ハンドラが例外を投げなければ残り時間だけ眠り直す（PEP 475）
    return worker.run(durations, time.sleep)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
