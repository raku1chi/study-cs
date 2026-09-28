"""1.4 プログラムが動く仕組み — 演習1〜4 解答例: スタックマシン型の仮想マシン

仕様（命令セット・呼び出し規約・アセンブリの文法）は exercises/stackvm.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

Instr = tuple  # ("PUSH", 5) のような「命令名, 引数…」のタプル

NUM_LOCALS = 16

# 命令名 → 引数の個数
ARITY = {
    "PUSH": 1, "POP": 0, "ADD": 0, "SUB": 0, "MUL": 0, "DIV": 0, "MOD": 0,
    "DUP": 0, "SWAP": 0, "JMP": 1, "JZ": 1, "EQ": 0, "LT": 0,
    "LOAD": 1, "STORE": 1, "CALL": 2, "RET": 0, "HALT": 0,
}


class VMError(Exception):
    """実行時のエラー（スタックの空読み、不正な命令、0 除算、ステップ数の超過など）。"""


class StackOverflowError(VMError):
    """呼び出しの深さが上限を超えた。"""


class AssemblerError(ValueError):
    """アセンブリのソースの誤り。メッセージは「行 N: 」で始まる。"""


@dataclass
class Frame:
    return_address: int                                      # RET で戻る番地（最初のフレームは -1）
    locals: list[int] = field(default_factory=lambda: [0] * NUM_LOCALS)
    stack: list[int] = field(default_factory=list)          # このフレームのオペランドスタック


# ---------------------------------------------------------------------------
# 演習1・2: VM 本体と、呼び出しの深さの制限
# ---------------------------------------------------------------------------

class VM:
    def __init__(self, code: list[Instr], max_depth: int = 1000, max_steps: int = 1_000_000) -> None:
        self.code = list(code)
        self.max_depth = max_depth
        self.max_steps = max_steps
        self.frames: list[Frame] = [Frame(return_address=-1)]
        self.pc = 0
        self.steps = 0
        self.halted = False

    @property
    def frame(self) -> Frame:
        return self.frames[-1]

    def _pop(self) -> int:
        stack = self.frame.stack
        if not stack:
            raise VMError(f"スタックが空です（番地 {self.pc - 1}）")
        return stack.pop()

    def _local_index(self, i: int) -> int:
        if not 0 <= i < NUM_LOCALS:
            raise VMError(f"ローカル変数の番号は 0〜{NUM_LOCALS - 1} です: {i}")
        return i

    def step(self) -> None:
        if self.halted:
            raise VMError("VM は停止しています")
        if not 0 <= self.pc < len(self.code):
            raise VMError(f"PC が範囲外です: {self.pc}")
        instr = self.code[self.pc]
        if not isinstance(instr, tuple) or not instr or instr[0] not in ARITY or len(instr) != 1 + ARITY[instr[0]]:
            raise VMError(f"不正な命令です: {instr!r}（番地 {self.pc}）")
        if not all(isinstance(arg, int) for arg in instr[1:]):
            raise VMError(f"引数は整数です: {instr!r}（番地 {self.pc}）")
        op, args = instr[0], instr[1:]
        self.pc += 1  # フェッチしたら PC を次へ。ジャンプ系の命令はこの後で上書きする
        stack = self.frame.stack

        if op == "PUSH":
            stack.append(args[0])
        elif op == "POP":
            self._pop()
        elif op in ("ADD", "SUB", "MUL", "DIV", "MOD", "EQ", "LT"):
            b = self._pop()  # 右側のオペランドが上に積まれている
            a = self._pop()
            if op in ("DIV", "MOD") and b == 0:
                raise VMError(f"0 で割りました（番地 {self.pc - 1}）")
            result = {
                "ADD": lambda: a + b, "SUB": lambda: a - b, "MUL": lambda: a * b,
                "DIV": lambda: a // b, "MOD": lambda: a % b,
                "EQ": lambda: int(a == b), "LT": lambda: int(a < b),
            }[op]()
            stack.append(result)
        elif op == "DUP":
            v = self._pop()
            stack.extend((v, v))
        elif op == "SWAP":
            b = self._pop()
            a = self._pop()
            stack.extend((b, a))
        elif op == "JMP":
            self.pc = args[0]
        elif op == "JZ":
            if self._pop() == 0:
                self.pc = args[0]
        elif op == "LOAD":
            stack.append(self.frame.locals[self._local_index(args[0])])
        elif op == "STORE":
            self.frame.locals[self._local_index(args[0])] = self._pop()
        elif op == "CALL":
            addr, nargs = args
            # 演習2: 新しいフレームを積む前に深さを確かめる。
            # Python の再帰を使わず自前のフレームのリストで管理しているので、上限は自由に決められる
            if len(self.frames) >= self.max_depth:
                raise StackOverflowError(
                    f"呼び出しの深さが上限 {self.max_depth} を超えました（番地 {self.pc - 1}）"
                )
            if not 0 <= nargs <= NUM_LOCALS:
                raise VMError(f"引数の個数は 0〜{NUM_LOCALS} です: {nargs}")
            if len(stack) < nargs:
                raise VMError(f"引数が足りません: {nargs} 個必要（番地 {self.pc - 1}）")
            # 呼び出し側のスタックから引数を取り出し、積んだ順に locals[0], locals[1], … へ入れる
            callee = Frame(return_address=self.pc)
            if nargs:
                callee.locals[:nargs] = stack[-nargs:]
                del stack[-nargs:]
            self.frames.append(callee)
            self.pc = addr
        elif op == "RET":
            if len(self.frames) == 1:
                raise VMError("戻る先がありません（最初のフレームで RET）")
            value = self._pop()
            finished = self.frames.pop()      # 呼ばれた側のフレームを捨てる
            self.frame.stack.append(value)    # 戻り値は呼び出し側のスタックへ
            self.pc = finished.return_address
        elif op == "HALT":
            self.halted = True
        self.steps += 1

    def run(self) -> Optional[int]:
        while not self.halted:
            if self.steps >= self.max_steps:
                raise VMError(f"{self.max_steps} ステップ以内に停止しませんでした")
            self.step()
        return self.frame.stack[-1] if self.frame.stack else None


# ---------------------------------------------------------------------------
# 演習3: アセンブラ
# ---------------------------------------------------------------------------

_LABEL_DEF_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_INT_RE = re.compile(r"[+-]?\d+$")


def assemble(source: str) -> list[Instr]:
    labels: dict[str, int] = {}
    lines: list[tuple[int, str, list[str]]] = []
    # 1 パス目: ラベルの番地を集める
    for lineno, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip()
        m = _LABEL_DEF_RE.match(text)
        while m:
            name = m.group(1)
            if name in labels:
                raise AssemblerError(f"行 {lineno}: ラベル {name} が重複しています")
            labels[name] = len(lines)
            text = m.group(2).strip()
            m = _LABEL_DEF_RE.match(text)
        if not text:
            continue
        mnemonic, *rest = text.split(None, 1)
        operands = [op.strip() for op in rest[0].split(",")] if rest else []
        lines.append((lineno, mnemonic.upper(), operands))

    # 2 パス目: 命令のタプルを作り、ラベルを番地に置き換える
    code: list[Instr] = []
    for lineno, mnemonic, operands in lines:
        if mnemonic not in ARITY:
            raise AssemblerError(f"行 {lineno}: 未知の命令です: {mnemonic}")
        if len(operands) != ARITY[mnemonic]:
            raise AssemblerError(f"行 {lineno}: {mnemonic} の引数は {ARITY[mnemonic]} 個です: {operands}")
        args: list[int] = []
        for text in operands:
            if _INT_RE.match(text):
                args.append(int(text))
            elif _NAME_RE.match(text):
                if text not in labels:
                    raise AssemblerError(f"行 {lineno}: 未定義のラベルです: {text}")
                args.append(labels[text])
            else:
                raise AssemblerError(f"行 {lineno}: 整数かラベル名を書いてください: {text!r}")
        code.append((mnemonic, *args))
    return code


# ---------------------------------------------------------------------------
# 演習4: VM のプログラム
# ---------------------------------------------------------------------------

def factorial_iterative(n: int) -> list[Instr]:
    return assemble(f"""
        PUSH 1
        STORE 0          ; acc = 1
        PUSH {n}
        STORE 1          ; k = n
loop:   LOAD 1
        JZ done          ; k == 0 なら終わり
        LOAD 0
        LOAD 1
        MUL
        STORE 0          ; acc = acc * k
        LOAD 1
        PUSH 1
        SUB
        STORE 1          ; k = k - 1
        JMP loop
done:   LOAD 0
        HALT
    """)


def factorial_recursive(n: int) -> list[Instr]:
    return assemble(f"""
        PUSH {n}
        CALL fact, 1
        HALT
fact:   LOAD 0           ; n
        PUSH 2
        LT               ; n < 2 ?
        JZ recurse
        PUSH 1           ; fact(0) = fact(1) = 1
        RET
recurse:
        LOAD 0
        LOAD 0
        PUSH 1
        SUB
        CALL fact, 1     ; fact(n - 1)
        MUL              ; n * fact(n - 1)
        RET
    """)


def fibonacci(n: int) -> list[Instr]:
    return assemble(f"""
        PUSH 0
        STORE 0          ; a = F(0)
        PUSH 1
        STORE 1          ; b = F(1)
        PUSH {n}
        STORE 2          ; 残り回数
loop:   LOAD 2
        JZ done
        LOAD 0
        LOAD 1
        DUP
        STORE 0          ; a = b
        ADD
        STORE 1          ; b = 古い a + b
        LOAD 2
        PUSH 1
        SUB
        STORE 2
        JMP loop
done:   LOAD 0           ; n 回進めた後の a = F(n)
        HALT
    """)
