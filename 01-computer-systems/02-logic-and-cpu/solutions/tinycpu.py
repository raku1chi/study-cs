"""1.2 論理回路と CPU の仕組み — 演習3・4 解答例: TinyCPU エミュレータとアセンブラ

仕様（命令セット・命令の形式・アセンブリの文法）は exercises/tinycpu.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from typing import NamedTuple

WORD_BITS = 16
WORD_MASK = (1 << WORD_BITS) - 1   # 0xFFFF
SIGN_BIT = 1 << (WORD_BITS - 1)    # 0x8000
NUM_REGS = 8

OPCODES = {
    "HALT": 0x00, "LOADI": 0x01, "MOV": 0x02, "ADD": 0x03,
    "SUB": 0x04, "AND": 0x05, "OR": 0x06, "XOR": 0x07,
    "SHL": 0x08, "SHR": 0x09, "CMP": 0x0A, "JMP": 0x0B,
    "JZ": 0x0C, "JNZ": 0x0D, "LOAD": 0x0E, "STORE": 0x0F,
}
MNEMONICS = {code: name for name, code in OPCODES.items()}


class CPUError(Exception):
    """実行時のエラー（不正な命令、範囲外のアクセス、ステップ数の超過など）。"""


class AssemblerError(ValueError):
    """アセンブリのソースの誤り。メッセージは「行 N: 」で始まる。"""


class Instruction(NamedTuple):
    op: int   # 命令の種類（オペコード）: ビット 31〜24
    a: int    # レジスタ番号 a: ビット 23〜20
    b: int    # レジスタ番号 b: ビット 19〜16
    imm: int  # 即値（16 ビット）: ビット 15〜0


def encode(op: int, a: int = 0, b: int = 0, imm: int = 0) -> int:
    """命令を 32 ビットの機械語にする（用意済み）。"""
    if not 0 <= op <= 0xFF:
        raise ValueError(f"op は 0〜255: {op}")
    if not (0 <= a <= 0xF and 0 <= b <= 0xF):
        raise ValueError(f"レジスタ欄は 0〜15: a={a}, b={b}")
    if not 0 <= imm <= 0xFFFF:
        raise ValueError(f"imm は 0〜65535: {imm}")
    return (op << 24) | (a << 20) | (b << 16) | imm


def decode(word: int) -> Instruction:
    if not 0 <= word <= 0xFFFF_FFFF:
        raise ValueError(f"機械語は 32 ビットの符号なし整数です: {word}")
    # シフトとマスクでビットフィールドを切り出す。ハードウェアでは配線を分けるだけで済む
    return Instruction(word >> 24, (word >> 20) & 0xF, (word >> 16) & 0xF, word & 0xFFFF)


class CPU:
    def __init__(self, program: list[int], memory_size: int = 256) -> None:
        self.program = list(program)       # 命令メモリ（32 ビットの機械語のリスト）
        self.memory = [0] * memory_size    # データメモリ（16 ビットの語のリスト）
        self.regs = [0] * NUM_REGS         # r0〜r7
        self.pc = 0                        # プログラムカウンタ: 次に実行する命令の番地
        self.z = self.n = self.c = self.v = 0  # フラグ
        self.halted = False
        self.steps = 0                     # これまでに実行した命令数

    # --- フラグの計算 -------------------------------------------------------

    def _set_zn(self, result: int) -> None:
        self.z = int(result == 0)
        self.n = int(bool(result & SIGN_BIT))

    def _add(self, x: int, y: int, carry_in: int) -> int:
        """x + y + carry_in を 16 ビットで計算し、4 つのフラグを設定する（ALU の加算器）。"""
        raw = x + y + carry_in
        result = raw & WORD_MASK
        self._set_zn(result)
        self.c = raw >> WORD_BITS  # 最上位ビットからの桁上がり
        # x と y の符号が同じで、結果の符号がそれと異なる ⇔ 符号付きオーバーフロー
        self.v = int(bool((x ^ result) & (y ^ result) & SIGN_BIT))
        return result

    def _sub(self, x: int, y: int) -> int:
        # x - y = x + (y のビット反転) + 1。C は「借りなし（x >= y）」で 1（ARM と同じ規約）
        return self._add(x, (~y) & WORD_MASK, 1)

    def _logic(self, result: int) -> int:
        self._set_zn(result)
        self.c = self.v = 0
        return result

    def _address(self, base: int, offset: int) -> int:
        addr = (base + offset) & WORD_MASK
        if addr >= len(self.memory):
            raise CPUError(f"データメモリの範囲外です: 番地 {addr}（大きさ {len(self.memory)}）")
        return addr

    # --- 1 命令の実行 ---------------------------------------------------------

    def step(self) -> None:
        if self.halted:
            raise CPUError("CPU は停止しています")
        # フェッチ: PC が指す命令を読み、PC を次へ進める
        if not 0 <= self.pc < len(self.program):
            raise CPUError(f"PC が命令メモリの範囲外です: {self.pc}")
        word = self.program[self.pc]
        self.pc += 1
        # デコード: ビットフィールドに分け、命令として正しいかを確かめる
        try:
            op, a, b, imm = decode(word)
        except ValueError as exc:
            raise CPUError(str(exc)) from exc
        name = MNEMONICS.get(op)
        if name is None:
            raise CPUError(f"不正な命令です: オペコード {op:#04x}（番地 {self.pc - 1}）")
        if a >= NUM_REGS or b >= NUM_REGS:
            raise CPUError(f"不正なレジスタ番号です: a={a}, b={b}（番地 {self.pc - 1}）")
        # 実行
        r = self.regs
        if name == "HALT":
            self.halted = True
        elif name == "LOADI":
            r[a] = imm
        elif name == "MOV":
            r[a] = r[b]
        elif name == "ADD":
            r[a] = self._add(r[a], r[b], 0)
        elif name == "SUB":
            r[a] = self._sub(r[a], r[b])
        elif name == "CMP":
            self._sub(r[a], r[b])  # 結果は捨て、フラグだけを残す
        elif name == "AND":
            r[a] = self._logic(r[a] & r[b])
        elif name == "OR":
            r[a] = self._logic(r[a] | r[b])
        elif name == "XOR":
            r[a] = self._logic(r[a] ^ r[b])
        elif name == "SHL":
            r[a] = self._logic((r[a] << imm) & WORD_MASK)
        elif name == "SHR":
            r[a] = self._logic(r[a] >> imm)  # 論理シフト: 上位には 0 が入る
        elif name == "JMP":
            self.pc = imm
        elif name == "JZ":
            if self.z:
                self.pc = imm
        elif name == "JNZ":
            if not self.z:
                self.pc = imm
        elif name == "LOAD":
            r[a] = self.memory[self._address(r[b], imm)]
        elif name == "STORE":
            self.memory[self._address(r[b], imm)] = r[a]
        self.steps += 1

    def run(self, max_steps: int = 10_000) -> int:
        executed = 0
        while not self.halted:
            if executed >= max_steps:
                raise CPUError(f"{max_steps} ステップ以内に停止しませんでした（無限ループ？）")
            self.step()
            executed += 1
        return executed


# ---------------------------------------------------------------------------
# 演習4: 2 パスアセンブラ
# ---------------------------------------------------------------------------

# 各命令のオペランドの種類
FORMATS: dict[str, tuple[str, ...]] = {
    "HALT": (),
    "LOADI": ("reg", "imm"),
    "MOV": ("reg", "reg"), "ADD": ("reg", "reg"), "SUB": ("reg", "reg"),
    "AND": ("reg", "reg"), "OR": ("reg", "reg"), "XOR": ("reg", "reg"), "CMP": ("reg", "reg"),
    "SHL": ("reg", "shift"), "SHR": ("reg", "shift"),
    "JMP": ("target",), "JZ": ("target",), "JNZ": ("target",),
    "LOAD": ("reg", "mem"), "STORE": ("reg", "mem"),
}

_LABEL_DEF_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:(.*)$")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*$")
_REG_RE = re.compile(r"[rR]([0-9]+)$")
_MEM_RE = re.compile(r"\[\s*([^\]+]+?)\s*(?:\+\s*([^\]]+?)\s*)?\]$")


def _is_register_name(name: str) -> bool:
    return _REG_RE.match(name) is not None


def assemble(source: str) -> list[int]:
    # --- 1 パス目: ラベルの番地を集め、命令の行を取り出す ---------------------
    labels: dict[str, int] = {}
    lines: list[tuple[int, str, list[str]]] = []
    for lineno, raw in enumerate(source.splitlines(), 1):
        text = raw.split(";", 1)[0].strip()  # コメントを取り除く
        m = _LABEL_DEF_RE.match(text)
        while m:  # 1 行に複数のラベルがあってもよい（"a: b: HALT"）
            name = m.group(1)
            if _is_register_name(name):
                raise AssemblerError(f"行 {lineno}: レジスタ名はラベルに使えません: {name}")
            if name in labels:
                raise AssemblerError(f"行 {lineno}: ラベル {name} が重複しています")
            labels[name] = len(lines)  # 次に来る命令の番地
            text = m.group(2).strip()
            m = _LABEL_DEF_RE.match(text)
        if not text:
            continue
        mnemonic, *rest = text.split(None, 1)
        operands = [op.strip() for op in rest[0].split(",")] if rest else []
        lines.append((lineno, mnemonic.upper(), operands))

    # --- 2 パス目: 命令を機械語に変換する（ラベルはすべて番地が分かっている）---
    code: list[int] = []
    for lineno, mnemonic, operands in lines:
        def fail(message: str) -> AssemblerError:
            return AssemblerError(f"行 {lineno}: {message}")

        def reg(text: str) -> int:
            m = _REG_RE.match(text)
            if not m or int(m.group(1)) >= NUM_REGS:
                raise fail(f"レジスタは r0〜r{NUM_REGS - 1} です: {text!r}")
            return int(m.group(1))

        def number(text: str, lo: int, hi: int) -> int:
            try:
                value = int(text, 0)  # 10 進数、0x で始まる 16 進数、0b で始まる 2 進数
            except ValueError:
                raise fail(f"数値として読めません: {text!r}") from None
            if not lo <= value <= hi:
                raise fail(f"値が範囲外です: {value}（{lo}〜{hi}）")
            return value

        if mnemonic not in FORMATS:
            raise fail(f"未知の命令です: {mnemonic}")
        kinds = FORMATS[mnemonic]
        if len(operands) != len(kinds):
            raise fail(f"{mnemonic} のオペランドは {len(kinds)} 個です: {operands}")
        a = b = imm = 0
        for pos, (kind, text) in enumerate(zip(kinds, operands)):
            if kind == "reg":
                # 1 つ目のレジスタは a 欄、2 つ目（MOV r1, r2 の r2 など）は b 欄に入る
                if pos == 0:
                    a = reg(text)
                else:
                    b = reg(text)
            elif kind == "imm":
                imm = number(text, -(1 << (WORD_BITS - 1)), WORD_MASK) & WORD_MASK  # -1 は 0xFFFF
            elif kind == "shift":
                imm = number(text, 0, WORD_BITS - 1)
            elif kind == "target":
                if _NAME_RE.match(text) and not _is_register_name(text):
                    if text not in labels:
                        raise fail(f"未定義のラベルです: {text}")
                    imm = labels[text]
                else:
                    imm = number(text, 0, WORD_MASK)
            elif kind == "mem":
                m = _MEM_RE.match(text)
                if not m:
                    raise fail(f"メモリの書き方は [rN] か [rN+数値] です: {text!r}")
                b = reg(m.group(1))
                imm = number(m.group(2), 0, WORD_MASK) if m.group(2) else 0
        code.append(encode(OPCODES[mnemonic], a, b, imm))
    return code


MULTIPLY_PROGRAM = """
; r0 = r1 × r2 (mod 2^16)。筆算と同じく「r2 のビットが 1 の桁だけ、ずらした r1 を足す」
        LOADI r0, 0          ; 結果
        LOADI r3, 1          ; 最下位ビットを取り出すためのマスク
loop:   MOV   r4, r2
        AND   r4, r3         ; r2 の最下位ビットが 1 なら
        JZ    skip
        ADD   r0, r1         ;   結果に r1 を足す
skip:   SHL   r1, 1          ; r1 を 2 倍にする（次の桁の重み）
        SHR   r2, 1          ; r2 を 1 ビット右へ。0 になったら Z=1
        JNZ   loop
        HALT
"""
