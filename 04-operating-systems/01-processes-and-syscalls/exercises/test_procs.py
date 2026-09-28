"""4.1 fork/exec/pipe によるパイプライン — テスト（Unix 専用。Windows ではスキップされます）

実行: python3 tools/check.py 4.1   （またはこのディレクトリで python3 -m unittest -v test_procs）
"""
import contextlib
import os
import signal
import sys
import unittest

from procs import PipelineResult, run_pipeline, wait_status_to_code

PY = sys.executable
UNIX = hasattr(os, "fork") and hasattr(signal, "setitimer")


class Hang(Exception):
    pass


@contextlib.contextmanager
def time_limit(seconds: float):
    """時間内に終わらなければ Hang 例外にする（パイプの端の閉じ忘れによるハングを検出するため）。"""

    def on_alarm(signum, frame):
        raise Hang(f"{seconds} 秒以内に終わりませんでした。パイプの端の閉じ忘れか、"
                   "入力を書き終えるまで出力を読まないことによるデッドロックを疑ってください")

    old = signal.signal(signal.SIGALRM, on_alarm)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


def run(commands, input=None, seconds=10.0) -> PipelineResult:
    with time_limit(seconds):
        return run_pipeline(commands, input=input)


def open_fd_count() -> int:
    return len(os.listdir("/dev/fd"))


@unittest.skipUnless(UNIX, "fork と setitimer が必要です（Unix 専用）")
class TestExercise4aWaitStatus(unittest.TestCase):
    def status_of(self, child_body) -> int:
        pid = os.fork()
        if pid == 0:
            try:
                child_body()
            finally:
                os._exit(99)
        return os.waitpid(pid, 0)[1]

    def test_normal_exit_codes(self):
        for code in (0, 1, 3, 255):
            status = self.status_of(lambda code=code: os._exit(code))
            self.assertEqual(wait_status_to_code(status), code)

    def test_killed_by_signal_is_negative(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            status = self.status_of(lambda sig=sig: os.kill(os.getpid(), sig))
            self.assertEqual(wait_status_to_code(status), -sig)


@unittest.skipUnless(UNIX, "fork と setitimer が必要です（Unix 専用）")
class TestExercise4bPipeline(unittest.TestCase):
    def test_single_command(self):
        self.assertEqual(run([["echo", "hello"]]), (b"hello\n", [0]))

    def test_two_commands(self):
        result = run([[PY, "-c", "print('b'); print('a'); print('c')"], ["sort"]])
        self.assertEqual(result.output, b"a\nb\nc\n")
        self.assertEqual(result.statuses, [0, 0])

    def test_three_commands(self):
        result = run([
            [PY, "-c", "print('hello world')"],
            ["tr", "a-z", "A-Z"],
            [PY, "-c", "import sys; data = sys.stdin.read(); print(data.strip(), len(data))"],
        ])
        self.assertEqual(result.output, b"HELLO WORLD 12\n")
        self.assertEqual(result.statuses, [0, 0, 0])

    def test_input_is_fed_to_first_command(self):
        self.assertEqual(run([["tr", "a-z", "A-Z"]], input=b"abc\n").output, b"ABC\n")
        self.assertEqual(run([["cat"], ["cat"]], input=b"").output, b"")

    def test_large_data_through_several_pipes(self):
        n = 2 * 1024 * 1024  # パイプのバッファ（Linux の既定は 64 KiB）よりずっと大きい
        result = run([
            [PY, "-c", f"import sys; sys.stdout.buffer.write(b'x' * {n})"],
            ["cat"],
            [PY, "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
        ])
        self.assertEqual(result.output, f"{n}\n".encode())

    def test_large_input_and_output_do_not_deadlock(self):
        data = bytes(range(256)) * 4096  # 1 MiB
        result = run([["cat"]], input=data)
        self.assertEqual(len(result.output), len(data))
        self.assertEqual(result.output, data)

    def test_exit_status_of_each_command(self):
        result = run([["sh", "-c", "echo out; exit 3"], ["cat"], ["sh", "-c", "cat; exit 5"]])
        self.assertEqual(result.output, b"out\n")
        self.assertEqual(result.statuses, [3, 0, 5])

    def test_killed_command_has_negative_status(self):
        result = run([[PY, "-c", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"]])
        self.assertEqual(result.statuses, [-signal.SIGKILL])

    def test_command_not_found_is_127(self):
        result = run([["study-cs-no-such-command"], ["cat"]])
        self.assertEqual(result.statuses[0], 127)
        self.assertEqual(result.output, b"")

    def test_sigpipe_is_restored_in_children(self):
        # yes は、読み手の head が終了した後に書き込もうとして SIGPIPE で終了するのが正しい動き
        result = run([["yes"], ["head", "-n", "3"]])
        self.assertEqual(result.output, b"y\ny\ny\n")
        self.assertEqual(
            result.statuses, [-signal.SIGPIPE, 0],
            "子で SIGPIPE を既定の動作（SIG_DFL）に戻していないと、yes は EPIPE で異常終了（1）する",
        )

    def test_no_file_descriptor_leak_and_no_zombies(self):
        before = open_fd_count()
        for _ in range(5):
            run([["echo", "x"], ["cat"]], input=None)
            run([["cat"]], input=b"y")
        self.assertEqual(open_fd_count(), before, "親で閉じ忘れた fd があります")
        with self.assertRaises(ChildProcessError, msg="wait されていない子（ゾンビ）が残っています"):
            os.waitpid(-1, os.WNOHANG)

    def test_invalid_arguments(self):
        with self.assertRaises(ValueError):
            run_pipeline([])
        with self.assertRaises(ValueError):
            run_pipeline([["echo", "a"], []])


if __name__ == "__main__":
    unittest.main()
