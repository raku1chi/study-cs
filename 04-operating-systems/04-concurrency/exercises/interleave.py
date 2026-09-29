"""4.4 並行処理と同期 — 演習5: インターリーブの網羅的な探索

競合状態のバグは「たまにしか起きない」ので、スレッドを実際に動かすテストでは見逃しがちです。
ここでは、各スレッドの命令列を小さな言語で書き、**あり得るすべての実行順序（インターリーブ）** を
網羅的に試して、最終状態ごとの件数とデッドロックの件数を数える「小さなモデル検査器」を作ります。
結果は毎回同じなので、「更新の喪失」や「ロックの順序によるデッドロック」を、不安定なテストに
頼らずに確かめられます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.4
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_interleave

命令（Op）の一覧。各スレッドは 1 つのレジスタ（初期値 0）を持つ:
    ("read", v)     レジスタ ← 共有変数 v
    ("write", v)    共有変数 v ← レジスタ
    ("inc",)        レジスタ ← レジスタ + 1
    ("add", k)      レジスタ ← レジスタ + k（k は整数）
    ("lock", L)     ロック L を取る。誰か（自分を含む）が持っていれば、この命令は実行できない（待つ）
    ("unlock", L)   ロック L を解放する。自分が持っていなければ ValueError

例: `x += 1` は read → inc → write の 3 命令になる（CPU や Python のバイトコードも同様に分かれる）。
"""
from __future__ import annotations

from collections import Counter
from math import factorial  # noqa: F401  count_interleavings で使えます
from typing import Mapping, NamedTuple, Sequence

Op = tuple
Outcome = tuple  # ((変数名, 値), ...) を変数名の順に並べたもの


class ExploreResult(NamedTuple):
    outcomes: Counter  # 最終状態 -> その状態で終わるスケジュールの数
    deadlocks: int  # 全員が止まって先に進めなくなったスケジュールの数
    schedules: int  # 探索したスケジュールの総数（完走したもの ＋ デッドロックしたもの）


def increment_program(var: str = "x", lock: str | None = None) -> list[Op]:
    """`var += 1` を表す命令列を返す（実装済み）。lock を指定すると、ロックで囲んだ版になる。"""
    body: list[Op] = [("read", var), ("inc",), ("write", var)]
    return [("lock", lock), *body, ("unlock", lock)] if lock else body


# ---------------------------------------------------------------------------
# 演習5（★★★）: インターリーブの網羅的な探索
# ---------------------------------------------------------------------------

def count_interleavings(lengths: Sequence[int]) -> int:
    """長さ lengths[i] の命令列を持つスレッドたちの、インターリーブ（ロックを考えない）の総数。

    各スレッドの中の順序は保ったまま、命令を 1 列に並べる方法の数で、多項係数
    (n1 + n2 + ...)! / (n1! × n2! × ...) になる。負の長さがあれば ValueError。

    >>> count_interleavings([3, 3])
    20
    >>> count_interleavings([10, 10, 10])   # 3 スレッド × 10 命令でも 5 兆通りを超える
    5550996791340
    """
    raise NotImplementedError("演習5: count_interleavings を実装してください")


def explore(threads: Sequence[Sequence[Op]], initial: Mapping[str, int]) -> ExploreResult:
    """すべてのインターリーブを試し、ExploreResult を返す。

    - 状態は「各スレッドの次の命令の位置・各スレッドのレジスタ・共有変数・ロックの持ち主」。
    - 各時点で「次の 1 命令を実行できるスレッド」（命令が残っていて、ロック待ちでないもの）を
      すべて試す。1 つのスケジュールは、次のどちらかで終わる:
        * 全スレッドが命令を実行し終えた → outcomes[最終状態] を 1 増やす。
          最終状態は tuple(sorted(共有変数.items())) とする（例: (("x", 2),)）。
        * 未完了のスレッドがいるのに、実行できるスレッドがいない → deadlocks を 1 増やす
          （命令を終えたスレッドがロックを持ったまま終わり、他が待ち続ける場合も含む）。
      どちらの場合も schedules を 1 増やす。
    - 不正な命令（未知の名前、引数の数の誤り、initial にない変数の read/write、整数でない add）は、
      探索を始める前に ValueError。持っていないロックの unlock は、実行した時点で ValueError。

    >>> r = explore([increment_program(), increment_program()], {"x": 0})
    >>> r.schedules, sorted(r.outcomes.items())
    (20, [((('x', 1),), 18), ((('x', 2),), 2)])

    ヒント: 深さ優先探索（再帰でよい。深さは命令の総数程度）。1 命令を実行して再帰し、
    戻ってきたら状態を元に戻して次の選択肢を試す（バックトラック）。
    状態をまるごとコピーして渡す方法でも、この演習の規模なら十分に速い。
    """
    raise NotImplementedError("演習5: explore を実装してください")
