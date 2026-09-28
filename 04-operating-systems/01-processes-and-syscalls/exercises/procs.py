"""4.1 プロセス・スレッド・システムコール — 演習: fork/exec/pipe でシェルのパイプラインを作る

シェルが `cmd1 | cmd2 | cmd3` を実行するときに内部で行っていることを、Python の os モジュールの
薄いラッパー（ほぼシステムコールそのもの）だけで実装します。**Unix 専用** です（Windows では
テストがスキップされます）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.1
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_procs

制約（学びのための縛り）:
    - subprocess モジュール、os.system、os.popen、os.posix_spawn は使わないでください。
      使ってよいのは os.pipe / os.fork / os.dup2 / os.close / os.execvp / os.waitpid /
      os.read / os.write / os.WIFEXITED などと、threading です。
    - 演習4a では os.waitstatus_to_exitcode を使わないでください（テストの中の答え合わせ用です）。

fork した子プロセスの中での注意:
    - exec に失敗したときは、必ず os._exit(127) で終了すること。sys.exit() は例外を投げるだけなので、
      親からコピーされた呼び出し元のコード（テストランナーなど）が子の中で動き続けてしまいます。
"""
from __future__ import annotations

import os  # noqa: F401
import signal  # noqa: F401  子で SIGPIPE を既定の動作に戻すのに使います
import threading  # noqa: F401  入力の書き込みを別スレッドで行うのに使えます
from typing import NamedTuple, Sequence


class PipelineResult(NamedTuple):
    output: bytes  # 最後のコマンドの標準出力のすべて
    statuses: list[int]  # 各コマンドの終了ステータス（wait_status_to_code の規約）


# ---------------------------------------------------------------------------
# 演習4a（★☆☆）: 終了ステータスの解読
# ---------------------------------------------------------------------------

def wait_status_to_code(status: int) -> int:
    """os.waitpid() が返す status を、subprocess と同じ規約の整数に変換する。

    - 正常終了（exit）なら、その終了コード（0〜255）
    - シグナルで終了したなら、-シグナル番号（例: SIGKILL なら -9）
    - それ以外（停止中など）は ValueError

    ヒント: os.WIFEXITED / os.WEXITSTATUS / os.WIFSIGNALED / os.WTERMSIG を使う。
    status のビット配置を自分で解釈しないこと（OS の実装の詳細なので）。
    """
    raise NotImplementedError("演習4a: wait_status_to_code を実装してください")


# ---------------------------------------------------------------------------
# 演習4b（★★★）: パイプライン
# ---------------------------------------------------------------------------

def run_pipeline(commands: Sequence[Sequence[str]], input: bytes | None = None) -> PipelineResult:
    """commands[0] | commands[1] | ... をパイプでつないで実行し、最後の出力と各終了ステータスを返す。

    - 各コマンドは argv のリスト（例: ["sort", "-r"]）。コマンドは PATH から探す（os.execvp）。
    - input が None でなければ、それを先頭のコマンドの標準入力に流し込む。
      None なら、先頭のコマンドは親の標準入力をそのまま引き継ぐ。
    - 最後のコマンドの標準出力をすべて読み、PipelineResult.output として返す。
    - 標準エラー出力は親のものをそのまま引き継ぐ（取り込まない）。
    - 全員の終了を待ち（waitpid）、ゾンビを残さないこと。親の fd も漏らさないこと。
    - コマンドが見つからない・実行できないときは、その子は終了ステータス 127 で終わる
      （実行権限がない場合は 126 でもよい）。run_pipeline 自体は例外にしない。
    - commands が空、または空の argv を含むときは ValueError。

    >>> run_pipeline([["printf", "b\\na\\n"], ["sort"]])
    PipelineResult(output=b'a\\nb\\n', statuses=[0, 0])

    ハマりどころ（テストはこれらを確かめます）:
      1. 親は、子に渡したパイプの端を必ず閉じる。書き込み端を誰かが 1 つでも持っている限り、
         読み手に EOF が届かず、パイプライン全体が終わらなくなる。
      2. 子の中でも、dup2 で 0/1 番に付け替えた後、元のパイプの fd は閉じる。
      3. Python は起動時に SIGPIPE を「無視」に設定しており、無視の設定は exec 後も引き継がれる。
         子で exec する前に signal.signal(signal.SIGPIPE, signal.SIG_DFL) で既定の動作に戻さないと、
         `yes | head -n 3` の yes が SIGPIPE で終われない。
      4. input が大きいとき、親が input を全部書いてから出力を読むとデッドロックする
         （パイプのバッファは有限。Linux の既定は 64 KiB）。書き込みは別スレッドで行うとよい。
         先頭のコマンドが入力を読み切らずに終わると BrokenPipeError になるので、それは無視する。
    """
    raise NotImplementedError("演習4b: run_pipeline を実装してください")
