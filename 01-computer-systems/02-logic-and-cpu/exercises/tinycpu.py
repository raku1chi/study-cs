"""1.2 論理回路と CPU の仕組み — 演習3・4: TinyCPU エミュレータとアセンブラ

小さな CPU「TinyCPU」を作ります。演習3 で機械語を解釈して実行する CPU（フェッチ・デコード・実行の
繰り返し）を、演習4 でアセンブリ言語を機械語に変換するアセンブラと、アセンブリのプログラムを書きます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.2
このディレクトリで、この演習のテストだけを実行することもできます:
    python3 -m unittest -v test_tinycpu

======================================================================
TinyCPU の仕様（命令セットアーキテクチャ, ISA）
======================================================================

- データは 16 ビットの語（word）。レジスタ・メモリの値は常に 0〜65535 のビットパターンで、
  演算結果は下位 16 ビットだけを残す（2^16 を法として回り込む）。符号付きかどうかは解釈の問題（1.1 章）。
- 汎用レジスタは r0〜r7 の 8 本。すべて同等（x86 や RISC-V のような特別な役割はない）。
- 命令メモリとデータメモリが分かれている（ハーバード・アーキテクチャ）。
    - 命令メモリ: 32 ビットの機械語のリスト。PC（プログラムカウンタ）は「何番目の命令か」を指す。
    - データメモリ: 16 ビットの語のリスト（既定で 256 語）。番地も「何番目の語か」。
- フラグは Z（結果が 0）、N（結果の最上位ビット）、C（桁上がり）、V（符号付きオーバーフロー）の 4 つ。

命令の形式（すべての命令が 32 ビット固定長）:

     31      24 23   20 19   16 15                0
    ┌──────────┬───────┬───────┬───────────────────┐
    │ op (8)   │ a (4) │ b (4) │ imm (16)          │
    └──────────┴───────┴───────┴───────────────────┘
    例: LOADI r1, 10 → op=0x01, a=1, b=0, imm=10 → 0x0110000A

| op   | 命令  | アセンブリ         | 動作                                 | フラグ           |
|------|-------|--------------------|--------------------------------------|------------------|
| 0x00 | HALT  | HALT               | 停止する                             | 変化なし         |
| 0x01 | LOADI | LOADI ra, imm      | ra ← imm                             | 変化なし         |
| 0x02 | MOV   | MOV ra, rb         | ra ← rb                              | 変化なし         |
| 0x03 | ADD   | ADD ra, rb         | ra ← ra + rb                         | Z N C V          |
| 0x04 | SUB   | SUB ra, rb         | ra ← ra − rb                         | Z N C V          |
| 0x05 | AND   | AND ra, rb         | ra ← ra AND rb（ビットごと）         | Z N（C=V=0）     |
| 0x06 | OR    | OR ra, rb          | ra ← ra OR rb（ビットごと）          | Z N（C=V=0）     |
| 0x07 | XOR   | XOR ra, rb         | ra ← ra XOR rb（ビットごと）         | Z N（C=V=0）     |
| 0x08 | SHL   | SHL ra, imm        | ra ← ra << imm（下位 16 ビット）     | Z N（C=V=0）     |
| 0x09 | SHR   | SHR ra, imm        | ra ← ra >> imm（論理シフト）         | Z N（C=V=0）     |
| 0x0A | CMP   | CMP ra, rb         | ra − rb を計算してフラグだけ更新     | Z N C V          |
| 0x0B | JMP   | JMP ラベル         | PC ← imm                             | 変化なし         |
| 0x0C | JZ    | JZ ラベル          | Z = 1 なら PC ← imm                  | 変化なし         |
| 0x0D | JNZ   | JNZ ラベル         | Z = 0 なら PC ← imm                  | 変化なし         |
| 0x0E | LOAD  | LOAD ra, [rb+imm]  | ra ← メモリ[(rb + imm) mod 2^16]     | 変化なし         |
| 0x0F | STORE | STORE ra, [rb+imm] | メモリ[(rb + imm) mod 2^16] ← ra     | 変化なし         |

- ADD / SUB / CMP のフラグは演習2 の ALU と同じ規則（16 ビット）。SUB と CMP の C は「借りなし（ra >= rb、
  符号なし）」なら 1（ARM と同じ規約）。
- 使わない欄は 0 にする（例: JMP の a, b）。
"""
from __future__ import annotations

import re  # noqa: F401  演習4 で使えます
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
    """アセンブリのソースの誤り。メッセージは「行 N: 」で始める。"""


class Instruction(NamedTuple):
    op: int   # 命令の種類（オペコード）: ビット 31〜24
    a: int    # レジスタ番号 a: ビット 23〜20
    b: int    # レジスタ番号 b: ビット 19〜16
    imm: int  # 即値（16 ビット）: ビット 15〜0


def encode(op: int, a: int = 0, b: int = 0, imm: int = 0) -> int:
    """命令を 32 ビットの機械語にする（用意済み。decode の逆）。

    >>> hex(encode(OPCODES["LOADI"], 1, 0, 10))
    '0x110000a'
    """
    if not 0 <= op <= 0xFF:
        raise ValueError(f"op は 0〜255: {op}")
    if not (0 <= a <= 0xF and 0 <= b <= 0xF):
        raise ValueError(f"レジスタ欄は 0〜15: a={a}, b={b}")
    if not 0 <= imm <= 0xFFFF:
        raise ValueError(f"imm は 0〜65535: {imm}")
    return (op << 24) | (a << 20) | (b << 16) | imm


# ---------------------------------------------------------------------------
# 演習3（★★★）: デコーダと CPU
# ---------------------------------------------------------------------------

def decode(word: int) -> Instruction:
    """32 ビットの機械語を、ビットフィールド (op, a, b, imm) に分解する。

    - word が 0〜2^32−1 の範囲外なら ValueError。
    - オペコードやレジスタ番号が正しいかどうかは、ここでは調べない（CPU.step で調べる）。

    >>> decode(0x0110000A)
    Instruction(op=1, a=1, b=0, imm=10)

    ヒント: 1.1 章の演習4（IEEE 754 の分解）と同じく、シフトとマスクで取り出す。
    """
    raise NotImplementedError("演習3: decode を実装してください")


class CPU:
    """TinyCPU の状態と、命令の実行。__init__ は用意済みです（状態の定義そのものが仕様）。"""

    def __init__(self, program: list[int], memory_size: int = 256) -> None:
        self.program = list(program)       # 命令メモリ（32 ビットの機械語のリスト）
        self.memory = [0] * memory_size    # データメモリ（16 ビットの語のリスト）
        self.regs = [0] * NUM_REGS         # r0〜r7
        self.pc = 0                        # プログラムカウンタ: 次に実行する命令の番地
        self.z = self.n = self.c = self.v = 0  # フラグ（0 か 1）
        self.halted = False
        self.steps = 0                     # これまでに実行した命令数

    def step(self) -> None:
        """命令を 1 つ実行する（フェッチ → デコード → 実行）。

        1. フェッチ: program[pc] を読み、pc を 1 進める。pc が範囲外なら CPUError。
        2. デコード: decode() でビットフィールドに分ける。
           - 未知のオペコード、a または b が 8 以上（命令の種類にかかわらず）なら CPUError。
           - word が 32 ビットの範囲外なら CPUError。
        3. 実行: モジュールの docstring の表に従って、レジスタ・メモリ・フラグ・pc を更新する。
           - ジャンプ命令は pc を imm に書き換える（フェッチで進めた値を上書き）。
           - LOAD / STORE の番地がデータメモリの大きさ以上なら CPUError。
           - HALT は halted を True にする（pc は HALT の次を指したままになる）。
        4. steps を 1 増やす。
        すでに停止している（halted が True）のに呼ばれたら CPUError。

        ヒント: ADD の V フラグは「2 つの入力の符号ビットが同じで、結果の符号ビットがそれと異なる」。
        ビット演算で書くと ((x ^ result) & (y ^ result) & 0x8000) != 0。
        SUB は x + (~y & 0xFFFF) + 1 として加算器を使い回すと、C と V が自然に求まる。
        """
        raise NotImplementedError("演習3: CPU.step を実装してください")

    def run(self, max_steps: int = 10_000) -> int:
        """HALT するまで step() を繰り返し、この run で実行した命令数を返す。

        - HALT 命令自体も 1 ステップと数える。
        - max_steps 個の命令を実行しても停止しなければ CPUError（無限ループ対策）。
        - 呼び出した時点ですでに停止していれば、何もせず 0 を返す。
        """
        raise NotImplementedError("演習3: CPU.run を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 2 パスアセンブラと、アセンブリのプログラム
# ---------------------------------------------------------------------------

def assemble(source: str) -> list[int]:
    """TinyCPU のアセンブリ言語のソースを、機械語（32 ビット整数）のリストに変換する。

    文法:
        - 1 行に 1 命令。空行は無視する。「;」から行末まではコメント。
        - 行頭に「名前:」と書くとラベルを定義できる。ラベルの値は、その次に来る命令の番地。
          ラベルだけの行も、同じ行に命令が続く行（"loop: ADD r0, r1"）も書ける。
          名前は英字か _ で始まり、英数字と _ が続く（大文字小文字を区別）。r0 のようなレジスタ名は不可。
        - 命令名とレジスタ名は大文字小文字を区別しない（add R0, r1 も可）。
        - オペランドはカンマで区切る。各命令のオペランドは docstring の表のとおり。
            レジスタ : r0〜r7
            即値     : 10 進数（負の数も可）、0x で始まる 16 進数、0b で始まる 2 進数
                       LOADI は −32768〜65535（負の数は 2 の補数で 16 ビットにする: −1 → 0xFFFF）
                       SHL / SHR は 0〜15
            ジャンプ先: ラベル名、または 0〜65535 の数値（番地）
            メモリ   : [rN] または [rN+数値]（数値は 0〜65535。[r2] は [r2+0] と同じ）

    - 誤りがあれば AssemblerError を送出する。メッセージは「行 N: 」（N は 1 始まりの行番号）で始める。
      未知の命令、オペランドの数の誤り、不正なレジスタ、範囲外の即値、未定義のラベル、ラベルの重複など。

    >>> [hex(w) for w in assemble("LOADI r1, 10\\nHALT")]
    ['0x110000a', '0x0']
    >>> [hex(w) for w in assemble("loop: JMP loop")]
    ['0xb000000']

    ヒント: 1 パス目で各ラベルの番地（その時点までの命令数）を辞書に集め、2 パス目で命令を変換する。
    前方参照（まだ定義されていないラベルへのジャンプ）を解決するために 2 回に分けるのがポイント。
    """
    raise NotImplementedError("演習4: assemble を実装してください")


# r1 × r2 を計算して r0 に入れ、HALT するプログラムを書いてください（演習4 の後半）。
#   - 入力: r1, r2（0〜65535）。出力: r0 = (r1 × r2) mod 2^16。r1〜r7 とフラグは壊してかまいません。
#   - 300 ステップ以内に HALT すること。r2 回だけ足し算を繰り返す方法では間に合いません。
#   - TinyCPU には掛け算命令がありません。筆算と同じく「r2 のビットが 1 の桁だけ、ずらした r1 を足す」
#     シフトと加算の方法を使います（ハードウェアの掛け算器も、基本はこの考え方です）。
MULTIPLY_PROGRAM = """
; ここにプログラムを書いてください
        HALT
"""
