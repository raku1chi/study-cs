"""4.1 プロセス・スレッド・システムコール — 解答例: fork/exec/pipe でシェルのパイプラインを作る

演習の仕様は exercises/procs.py の docstring を参照してください。
"""
from __future__ import annotations

import os
import signal
import sys
import threading
from typing import NamedTuple, Sequence


class PipelineResult(NamedTuple):
    output: bytes
    statuses: list[int]


# ---------------------------------------------------------------------------
# 演習4a: 終了ステータスの解読
# ---------------------------------------------------------------------------

def wait_status_to_code(status: int) -> int:
    # waitpid の status は「終了コード」と「終了させたシグナル」を 1 つの整数に詰めたもの。
    # 解読には必ずマクロ（WIFEXITED など）を使う。ビット配置は OS の実装の詳細なので直接触らない
    if os.WIFEXITED(status):
        return os.WEXITSTATUS(status)
    if os.WIFSIGNALED(status):
        return -os.WTERMSIG(status)
    raise ValueError(f"終了していないプロセスの status です: {status:#x}")


# ---------------------------------------------------------------------------
# 演習4b: パイプライン
# ---------------------------------------------------------------------------

def run_pipeline(commands: Sequence[Sequence[str]], input: bytes | None = None) -> PipelineResult:
    if not commands or any(len(argv) == 0 for argv in commands):
        raise ValueError("コマンドを 1 つ以上、各コマンドは空でない argv で指定してください")
    argvs = [[str(a) for a in argv] for argv in commands]

    owned: set[int] = set()  # 親が閉じる責任を持っている fd

    def make_pipe() -> tuple[int, int]:
        r, w = os.pipe()
        owned.update((r, w))
        return r, w

    def close(fd: int) -> None:
        owned.discard(fd)
        os.close(fd)

    pids: list[int] = []
    try:
        in_r, in_w = make_pipe() if input is not None else (None, None)  # 親 → 先頭のコマンド
        out_r, out_w = make_pipe()  # 末尾のコマンド → 親
        prev_r = in_r  # 次に起動するコマンドの標準入力（None なら親の標準入力を継承）
        for i, argv in enumerate(argvs):
            last = i == len(argvs) - 1
            r, w = (None, out_w) if last else make_pipe()
            pid = os.fork()
            if pid == 0:
                _exec_child(argv, stdin_fd=prev_r, stdout_fd=w, fds_to_close=set(owned))
            pids.append(pid)
            # 親は、子に渡し終えた端を必ず閉じる。書き込み端を 1 つでも持ち続けると、
            # 読み手に EOF が届かず、パイプラインが終わらなくなる
            if prev_r is not None:
                close(prev_r)
            close(w)
            prev_r = r

        writer = None
        if in_w is not None:
            # 入力の書き込みと出力の読み出しを同時に行う。親が入力を全部書いてから出力を読むと、
            # 入出力の両方のパイプが満杯（Linux の既定で 64 KiB）になった時点でデッドロックする
            owned.discard(in_w)  # 以後はスレッドが閉じる
            writer = threading.Thread(target=_feed, args=(in_w, input), daemon=True)
            writer.start()

        chunks = []
        while True:
            data = os.read(out_r, 65536)
            if not data:  # すべての書き込み端が閉じられた = EOF
                break
            chunks.append(data)
        if writer is not None:
            writer.join()
        # 子を回収（reap）する。wait しないとゾンビが残る
        statuses = [wait_status_to_code(os.waitpid(pid, 0)[1]) for pid in pids]
        return PipelineResult(b"".join(chunks), statuses)
    finally:
        for fd in list(owned):
            try:
                close(fd)
            except OSError:
                pass


def _feed(fd: int, data: bytes) -> None:
    try:
        view = memoryview(data)
        while view:
            n = os.write(fd, view)  # 部分的にしか書けないことがあるので、残りを書き続ける
            view = view[n:]
    except BrokenPipeError:
        pass  # 先頭のコマンドが入力を読み切らずに終了した（head など）。よくあることなので無視する
    finally:
        os.close(fd)


def _exec_child(argv: list[str], stdin_fd: int | None, stdout_fd: int, fds_to_close: set[int]) -> None:
    """fork した子プロセスの中で呼ぶ。exec に成功すれば戻らない。"""
    try:
        if stdin_fd is not None:
            os.dup2(stdin_fd, 0)  # 標準入力（fd 0）を前段のパイプの読み出し端に差し替える
        os.dup2(stdout_fd, 1)  # 標準出力（fd 1）を次段のパイプの書き込み端に差し替える
        for fd in fds_to_close:
            if fd > 2:
                os.close(fd)  # 余分な端を閉じる（Python の os.pipe() は O_CLOEXEC 付きだが、明示するのが原則）
        # Python は起動時に SIGPIPE を無視（SIG_IGN）に設定する。無視の設定は exec 後も引き継がれるため、
        # 戻さないと `yes | head` の yes が SIGPIPE で終われず、EPIPE エラーになってしまう
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        if hasattr(signal, "SIGXFSZ"):
            signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
        os.execvp(argv[0], argv)  # 成功するとプロセスの中身が argv[0] のプログラムに置き換わる
    except BaseException as e:  # noqa: BLE001  子では何が起きても必ず _exit する
        try:
            os.write(2, f"{argv[0]}: {getattr(e, 'strerror', None) or e}\n".encode("utf-8", "replace"))
        except OSError:
            pass
        # sys.exit() ではなく os._exit()。sys.exit は例外を投げるので、親から複製された
        # 呼び出し元のコード（テストランナーなど）が子の中で動き続けてしまう
        os._exit(126 if isinstance(e, PermissionError) else 127)
    os._exit(127)  # 到達しない（execvp は成功すれば戻らない）


if __name__ == "__main__":  # 例: python3 procs.py
    result = run_pipeline([["ls", "/"], ["sort", "-r"], ["head", "-n", "3"]])
    sys.stdout.write(result.output.decode())
    print(result.statuses)
