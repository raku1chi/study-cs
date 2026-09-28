"""4.4 並行処理と同期 — 解答例: インターリーブの網羅的な探索

演習の仕様は exercises/interleave.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import Counter
from math import factorial
from typing import Mapping, NamedTuple, Sequence

Op = tuple  # ("read", 変数) / ("write", 変数) / ("inc",) / ("add", 整数) / ("lock", 名前) / ("unlock", 名前)
Outcome = tuple  # ((変数名, 値), ...) を変数名の順に並べたもの

_ARITY = {"read": 1, "write": 1, "inc": 0, "add": 1, "lock": 1, "unlock": 1}


class ExploreResult(NamedTuple):
    outcomes: Counter  # 最終状態 -> その状態に至るスケジュールの数
    deadlocks: int  # 全員が止まって先に進めなくなったスケジュールの数
    schedules: int  # 探索したスケジュール（完走またはデッドロックで終わる実行の並び）の総数


def increment_program(var: str = "x", lock: str | None = None) -> list[Op]:
    body: list[Op] = [("read", var), ("inc",), ("write", var)]
    return [("lock", lock), *body, ("unlock", lock)] if lock else body


def count_interleavings(lengths: Sequence[int]) -> int:
    if any(n < 0 for n in lengths):
        raise ValueError("長さは 0 以上")
    # 多項係数 (n1 + n2 + ...)! / (n1! n2! ...)
    result = factorial(sum(lengths))
    for n in lengths:
        result //= factorial(n)
    return result


def _validate(threads: Sequence[Sequence[Op]], initial: Mapping[str, int]) -> None:
    for t, prog in enumerate(threads):
        for op in prog:
            if not isinstance(op, tuple) or not op or op[0] not in _ARITY:
                raise ValueError(f"スレッド {t}: 不明な命令 {op!r}")
            if len(op) != 1 + _ARITY[op[0]]:
                raise ValueError(f"スレッド {t}: 命令の引数の数が違います {op!r}")
            if op[0] in ("read", "write") and op[1] not in initial:
                raise ValueError(f"スレッド {t}: 初期値のない共有変数 {op[1]!r}")
            if op[0] == "add" and not isinstance(op[1], int):
                raise ValueError(f"スレッド {t}: add の引数は整数 {op!r}")


def explore(threads: Sequence[Sequence[Op]], initial: Mapping[str, int]) -> ExploreResult:
    _validate(threads, initial)
    n = len(threads)
    pcs = [0] * n  # 各スレッドが次に実行する命令の位置
    regs = [0] * n  # 各スレッドのレジスタ（スレッドごとの一時的な値）
    shared = dict(initial)  # 共有変数
    owner: dict[str, int] = {}  # ロック名 -> 持っているスレッド
    outcomes: Counter = Counter()
    deadlocks = schedules = 0

    def runnable(t: int) -> bool:
        if pcs[t] >= len(threads[t]):
            return False
        op = threads[t][pcs[t]]
        # ロックが誰かに（自分にも）握られていれば、この lock 命令は実行できない（再入不可）
        return not (op[0] == "lock" and op[1] in owner)

    def dfs() -> None:
        nonlocal deadlocks, schedules
        ready = [t for t in range(n) if runnable(t)]
        if not ready:
            schedules += 1
            if all(pcs[t] >= len(threads[t]) for t in range(n)):
                outcomes[tuple(sorted(shared.items()))] += 1
            else:
                deadlocks += 1  # 未完了のスレッドがいるのに、誰も進めない
            return
        for t in ready:  # 次にどのスレッドが 1 命令進むか、のすべての選択肢を試す
            op = threads[t][pcs[t]]
            kind = op[0]
            saved_reg = regs[t]
            saved_var = None
            if kind == "read":
                regs[t] = shared[op[1]]
            elif kind == "write":
                saved_var = shared[op[1]]
                shared[op[1]] = regs[t]
            elif kind == "inc":
                regs[t] += 1
            elif kind == "add":
                regs[t] += op[1]
            elif kind == "lock":
                owner[op[1]] = t
            elif kind == "unlock":
                if owner.get(op[1]) != t:
                    raise ValueError(f"スレッド {t} は、持っていないロック {op[1]!r} を解放しようとしました")
                del owner[op[1]]
            pcs[t] += 1
            dfs()
            # 状態を元に戻して、次の選択肢を試す（バックトラック）
            pcs[t] -= 1
            regs[t] = saved_reg
            if kind == "write":
                shared[op[1]] = saved_var
            elif kind == "lock":
                del owner[op[1]]
            elif kind == "unlock":
                owner[op[1]] = t

    dfs()
    return ExploreResult(outcomes, deadlocks, schedules)
