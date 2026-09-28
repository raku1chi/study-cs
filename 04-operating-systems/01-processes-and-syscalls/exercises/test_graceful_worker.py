"""4.1 グレースフルシャットダウン — テスト

実行: python3 tools/check.py 4.1   （またはこのディレクトリで python3 -m unittest -v test_graceful_worker）

後半のテストは、ワーカーを別プロセスとして起動し、本物の SIGTERM / SIGINT を送ります（Unix 専用）。
"""
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

from graceful_worker import GracefulWorker

WORKER = Path(__file__).parent / "graceful_worker.py"


class TestExercise5InProcess(unittest.TestCase):
    """シグナルを実際には送らず、ハンドラを直接呼んで振る舞いを確かめる。"""

    def setUp(self):
        self.lines: list[str] = []
        self.worker = GracefulWorker(log=self.lines.append)
        self.saved = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}

    def tearDown(self):
        for sig, handler in self.saved.items():
            signal.signal(sig, handler)

    def test_runs_all_jobs_without_signal(self):
        done = []
        self.assertEqual(self.worker.run(["a", "b", "c"], done.append), 0)
        self.assertEqual(done, ["a", "b", "c"])
        self.assertEqual(self.lines, [
            "START 1", "DONE 1", "START 2", "DONE 2", "START 3", "DONE 3", "SHUTDOWN completed",
        ])

    def test_signal_during_job_finishes_it_then_stops(self):
        def process(job):
            if job == 2:  # 2 番目のジョブの処理中に SIGTERM が届いた
                self.worker.handle_signal(signal.SIGTERM, None)

        self.assertEqual(self.worker.run([1, 2, 3, 4], process), 0)
        self.assertEqual(self.lines, ["START 1", "DONE 1", "START 2", "DONE 2", "SHUTDOWN SIGTERM"])
        self.assertTrue(self.worker.stop_requested)
        self.assertEqual(self.worker.stop_signal, signal.SIGTERM)

    def test_next_job_is_not_taken_after_stop_request(self):
        pulled = []

        def jobs():  # キューからジョブを取り出す操作のつもり
            for i in range(1, 6):
                pulled.append(i)
                yield i

        def process(job):
            if job == 2:
                self.worker.handle_signal(signal.SIGTERM, None)

        self.worker.run(jobs(), process)
        self.assertEqual(pulled, [1, 2], "停止要求の後に次のジョブを取り出すと、そのジョブが失われる")

    def test_signal_before_first_job(self):
        self.worker.handle_signal(signal.SIGINT, None)
        called = []
        self.assertEqual(self.worker.run([1, 2], called.append), 0)
        self.assertEqual(called, [])
        self.assertEqual(self.lines, ["SHUTDOWN SIGINT"])

    def test_handler_only_sets_flags(self):
        self.worker.handle_signal(signal.SIGTERM, None)
        self.assertTrue(self.worker.stop_requested)
        self.assertEqual(self.lines, [], "ハンドラの中ではログ出力などの処理をしない")

    def test_first_signal_is_remembered(self):
        self.worker.handle_signal(signal.SIGTERM, None)
        self.worker.handle_signal(signal.SIGINT, None)
        self.assertEqual(self.worker.stop_signal, signal.SIGTERM)

    def test_install_registers_handlers(self):
        self.worker.install()
        self.assertEqual(signal.getsignal(signal.SIGTERM), self.worker.handle_signal)
        self.assertEqual(signal.getsignal(signal.SIGINT), self.worker.handle_signal)


@unittest.skipUnless(os.name == "posix", "SIGTERM を送るテストは Unix 専用です")
class TestExercise5RealSignals(unittest.TestCase):
    """ワーカーを子プロセスとして起動し、本物のシグナルを送る。"""

    def start(self, *durations: float):
        proc = subprocess.Popen(
            [sys.executable, "-u", str(WORKER), *map(str, durations)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        lines: "queue.Queue[str | None]" = queue.Queue()

        def reader():
            for line in proc.stdout:
                lines.put(line.rstrip("\n"))
            lines.put(None)

        thread = threading.Thread(target=reader, daemon=True)
        thread.start()
        self.addCleanup(self.cleanup, proc, thread)
        return proc, lines

    @staticmethod
    def cleanup(proc, thread):
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
        thread.join(timeout=10)  # 読み取りスレッドが EOF まで読み終えてから閉じる
        proc.stdout.close()
        proc.stderr.close()

    def wait_for(self, lines, expected, timeout=10.0):
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.fail(f"{expected!r} が {timeout} 秒以内に出力されませんでした")
            try:
                line = lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                self.fail(f"{expected!r} が出力される前にワーカーが終了しました")
            if line == expected:
                return

    def rest(self, lines, timeout=10.0):
        out = []
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                line = lines.get(timeout=max(deadline - time.monotonic(), 0.01))
            except queue.Empty:
                continue
            if line is None:
                return out
            out.append(line)
        self.fail("ワーカーの出力が終わりません")

    def check_graceful(self, sig):
        proc, lines = self.start(1.0, 0.2, 0.2)  # 1 つ目のジョブは 1 秒かかる
        self.wait_for(lines, "START 1")  # ハンドラの登録は、最初のジョブを始める前に済んでいる
        proc.send_signal(sig)
        code = proc.wait(timeout=10)
        stderr = proc.stderr.read()
        self.assertEqual(self.rest(lines), ["DONE 1", f"SHUTDOWN {signal.Signals(sig).name}"], stderr)
        self.assertEqual(code, 0, f"グレースフルに終了したら終了コードは 0\n{stderr}")

    def test_sigterm_finishes_in_flight_job_and_exits_0(self):
        self.check_graceful(signal.SIGTERM)

    def test_sigint_is_also_graceful(self):
        self.check_graceful(signal.SIGINT)

    def test_exits_normally_without_signal(self):
        proc, lines = self.start(0.01, 0.01)
        self.assertEqual(proc.wait(timeout=10), 0)
        self.assertEqual(self.rest(lines), ["START 1", "DONE 1", "START 2", "DONE 2", "SHUTDOWN completed"])


if __name__ == "__main__":
    unittest.main()
