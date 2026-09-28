"""1.2 演習3・4 のテスト: TinyCPU エミュレータとアセンブラ

実行: python3 tools/check.py 1.2   （またはこのディレクトリで python3 -m unittest -v test_tinycpu）
"""
import random
import unittest

from tinycpu import (
    CPU,
    MULTIPLY_PROGRAM,
    OPCODES,
    AssemblerError,
    CPUError,
    Instruction,
    assemble,
    decode,
    encode,
)


def E(name: str, a: int = 0, b: int = 0, imm: int = 0) -> int:
    """テスト用: 命令名で機械語を作る（手でアセンブルするのと同じ）。"""
    return encode(OPCODES[name], a, b, imm)


def run_program(program, regs=None, memory=None, max_steps=10_000) -> CPU:
    cpu = CPU(program)
    for i, value in (regs or {}).items():
        cpu.regs[i] = value
    for addr, value in (memory or {}).items():
        cpu.memory[addr] = value
    cpu.run(max_steps=max_steps)
    return cpu


def flags(cpu: CPU) -> tuple:
    return (cpu.z, cpu.n, cpu.c, cpu.v)


# 1〜10 の和（r0 に 55）。ループは r1 を 1 ずつ減らし、0 になったら（Z=1）抜ける
SUM_PROGRAM = [
    E("LOADI", 0, 0, 0),    # 0: r0 = 0（合計）
    E("LOADI", 1, 0, 10),   # 1: r1 = 10（n）
    E("LOADI", 2, 0, 1),    # 2: r2 = 1（定数）
    E("ADD", 0, 1),         # 3: r0 += r1
    E("SUB", 1, 2),         # 4: r1 -= 1（0 になったら Z=1）
    E("JNZ", imm=3),        # 5: Z=0 なら 3 番地へ
    E("HALT"),              # 6
]


class TestExercise3Decode(unittest.TestCase):
    def test_example(self):
        self.assertEqual(decode(0x0110000A), Instruction(1, 1, 0, 10))
        self.assertEqual(decode(0), Instruction(0, 0, 0, 0))
        self.assertEqual(decode(0xFFFFFFFF), Instruction(0xFF, 0xF, 0xF, 0xFFFF))

    def test_round_trip_with_encode(self):
        rng = random.Random(31)
        for _ in range(500):
            fields = (rng.randrange(256), rng.randrange(16), rng.randrange(16), rng.randrange(65536))
            self.assertEqual(tuple(decode(encode(*fields))), fields)

    def test_out_of_range_word(self):
        for word in (-1, 1 << 32):
            with self.assertRaises(ValueError, msg=hex(word)):
                decode(word)


class TestExercise3Instructions(unittest.TestCase):
    def test_loadi_mov_halt(self):
        cpu = run_program([E("LOADI", 3, 0, 1234), E("MOV", 5, 3), E("HALT")])
        self.assertEqual(cpu.regs[3], 1234)
        self.assertEqual(cpu.regs[5], 1234)
        self.assertTrue(cpu.halted)
        self.assertEqual(cpu.pc, 3, "HALT の次の番地を指したまま止まる")
        self.assertEqual(cpu.steps, 3)

    def test_step_executes_one_instruction(self):
        cpu = CPU([E("LOADI", 0, 0, 7), E("LOADI", 1, 0, 8), E("HALT")])
        cpu.step()
        self.assertEqual((cpu.regs[0], cpu.regs[1], cpu.pc, cpu.steps), (7, 0, 1, 1))
        cpu.step()
        self.assertEqual((cpu.regs[1], cpu.pc), (8, 2))
        self.assertFalse(cpu.halted)

    def test_add_wraps_and_sets_flags(self):
        cpu = run_program([E("ADD", 0, 1), E("HALT")], regs={0: 0xFFFF, 1: 1})
        self.assertEqual(cpu.regs[0], 0)
        self.assertEqual(flags(cpu), (1, 0, 1, 0), "0xFFFF + 1: Z=1, C=1（-1 + 1 = 0 なので V=0）")
        cpu = run_program([E("ADD", 0, 1), E("HALT")], regs={0: 0x7FFF, 1: 1})
        self.assertEqual(cpu.regs[0], 0x8000)
        self.assertEqual(flags(cpu), (0, 1, 0, 1), "32767 + 1: 符号付きオーバーフロー")

    def test_sub_flags(self):
        cpu = run_program([E("SUB", 0, 1), E("HALT")], regs={0: 3, 1: 5})
        self.assertEqual(cpu.regs[0], 0xFFFE)
        self.assertEqual(flags(cpu), (0, 1, 0, 0), "3 - 5: 借りが発生 → C=0")
        cpu = run_program([E("SUB", 0, 1), E("HALT")], regs={0: 5, 1: 3})
        self.assertEqual(cpu.regs[0], 2)
        self.assertEqual(flags(cpu), (0, 0, 1, 0), "5 - 3: 借りなし → C=1")
        cpu = run_program([E("SUB", 0, 1), E("HALT")], regs={0: 0x8000, 1: 1})
        self.assertEqual(cpu.regs[0], 0x7FFF)
        self.assertEqual(flags(cpu), (0, 0, 1, 1), "-32768 - 1: 符号付きオーバーフロー")

    def test_cmp_sets_flags_without_writing(self):
        cpu = run_program([E("CMP", 0, 1), E("HALT")], regs={0: 42, 1: 42})
        self.assertEqual(cpu.regs[0], 42, "CMP はレジスタを書き換えない")
        self.assertEqual(flags(cpu), (1, 0, 1, 0))
        cpu = run_program([E("CMP", 0, 1), E("HALT")], regs={0: 1, 1: 2})
        self.assertEqual(flags(cpu), (0, 1, 0, 0))

    def test_logic_ops(self):
        cpu = run_program([E("AND", 0, 1), E("OR", 2, 1), E("XOR", 3, 1), E("HALT")],
                          regs={0: 0b1100, 1: 0b1010, 2: 0b1100, 3: 0b1100})
        self.assertEqual(cpu.regs[0], 0b1000)
        self.assertEqual(cpu.regs[2], 0b1110)
        self.assertEqual(cpu.regs[3], 0b0110)
        cpu = run_program([E("ADD", 0, 0), E("XOR", 1, 1), E("HALT")], regs={0: 0x8000, 1: 5})
        self.assertEqual(flags(cpu), (1, 0, 0, 0), "論理演算は C と V を 0 にする")

    def test_shifts(self):
        cpu = run_program([E("SHL", 0, 0, 4), E("SHR", 1, 0, 15), E("SHR", 2, 0, 1), E("HALT")],
                          regs={0: 0x1234, 1: 0x8000, 2: 1})
        self.assertEqual(cpu.regs[0], 0x2340, "あふれた上位ビットは捨てる")
        self.assertEqual(cpu.regs[1], 1, "論理シフトなので上位には 0 が入る")
        self.assertEqual(cpu.regs[2], 0)
        self.assertEqual(cpu.z, 1)

    def test_shift_by_16_or_more_gives_zero(self):
        cpu = run_program([E("SHL", 0, 0, 16), E("HALT")], regs={0: 0xFFFF})
        self.assertEqual(cpu.regs[0], 0)

    def test_jumps(self):
        # r0 = 1 のとき JZ は分岐しない、JNZ は分岐する
        prog = [
            E("LOADI", 0, 0, 1),
            E("LOADI", 1, 0, 0),
            E("CMP", 0, 1),        # 1 - 0 → Z=0
            E("JZ", imm=6),        # 分岐しない
            E("JNZ", imm=7),       # 分岐する
            E("HALT"),             # 5: ここには来ない
            E("HALT"),             # 6: ここにも来ない
            E("LOADI", 2, 0, 99),  # 7
            E("JMP", imm=10),
            E("LOADI", 2, 0, 0),   # 9: 飛ばされる
            E("HALT"),             # 10
        ]
        cpu = run_program(prog)
        self.assertEqual(cpu.regs[2], 99)
        self.assertEqual(cpu.pc, 11)

    def test_load_store_base_plus_offset(self):
        prog = [
            E("LOADI", 1, 0, 10),   # r1 = 10（ベース）
            E("LOADI", 2, 0, 777),
            E("STORE", 2, 1, 5),    # メモリ[15] = 777
            E("LOAD", 3, 1, 5),     # r3 = メモリ[15]
            E("LOAD", 4, 1),        # r4 = メモリ[10]
            E("HALT"),
        ]
        cpu = run_program(prog, memory={10: 42})
        self.assertEqual(cpu.memory[15], 777)
        self.assertEqual(cpu.regs[3], 777)
        self.assertEqual(cpu.regs[4], 42)

    def test_address_wraps_mod_2_16(self):
        # 0xFFFF + 2 = 0x10001 → 下位 16 ビットで 1 番地
        cpu = run_program([E("LOAD", 0, 1, 2), E("HALT")], regs={1: 0xFFFF}, memory={1: 5})
        self.assertEqual(cpu.regs[0], 5)

    def test_moves_and_loads_keep_flags(self):
        prog = [E("CMP", 0, 0), E("LOADI", 1, 0, 5), E("MOV", 2, 1), E("LOAD", 3, 0), E("HALT")]
        cpu = run_program(prog)
        self.assertEqual(flags(cpu), (1, 0, 1, 0), "LOADI / MOV / LOAD はフラグを変えない")


class TestExercise3Errors(unittest.TestCase):
    def test_unknown_opcode(self):
        with self.assertRaises(CPUError):
            run_program([encode(0x42), E("HALT")])

    def test_bad_register_field(self):
        with self.assertRaises(CPUError):
            run_program([encode(OPCODES["MOV"], 8, 0), E("HALT")])
        with self.assertRaises(CPUError):
            run_program([encode(OPCODES["JMP"], 0, 9, 0)])

    def test_invalid_word_in_program(self):
        with self.assertRaises(CPUError):
            run_program([1 << 32])

    def test_pc_out_of_range(self):
        with self.assertRaises(CPUError, msg="HALT がないまま命令メモリの外へ出た"):
            run_program([E("LOADI", 0, 0, 1)])
        with self.assertRaises(CPUError):
            run_program([E("JMP", imm=100)])

    def test_memory_out_of_range(self):
        with self.assertRaises(CPUError):
            run_program([E("LOADI", 1, 0, 256), E("LOAD", 0, 1), E("HALT")])
        with self.assertRaises(CPUError):
            run_program([E("STORE", 0, 0, 300), E("HALT")])

    def test_step_limit(self):
        cpu = CPU([E("JMP", imm=0)])
        with self.assertRaises(CPUError):
            cpu.run(max_steps=100)
        self.assertEqual(cpu.steps, 100)

    def test_step_after_halt(self):
        cpu = CPU([E("HALT")])
        self.assertEqual(cpu.run(), 1)
        self.assertEqual(cpu.run(), 0, "停止済みなら run は 0 を返す")
        with self.assertRaises(CPUError):
            cpu.step()


class TestExercise3Programs(unittest.TestCase):
    def test_sum_1_to_10(self):
        cpu = CPU(SUM_PROGRAM)
        executed = cpu.run()
        self.assertEqual(cpu.regs[0], 55)
        self.assertEqual(executed, 3 + 3 * 10 + 1, "ループ 1 周 = 3 命令 × 10 周 + 前後")

    def test_sum_1_to_1000_wraps(self):
        prog = list(SUM_PROGRAM)
        prog[1] = E("LOADI", 1, 0, 1000)
        cpu = run_program(prog)
        self.assertEqual(cpu.regs[0], 500500 % 65536, "16 ビットで回り込む")

    def test_array_sum_with_load(self):
        # メモリ 100〜104 番地の 5 個の数の和
        prog = [
            E("LOADI", 0, 0, 0),     # 0: r0 = 0
            E("LOADI", 1, 0, 100),   # 1: r1 = 100（ポインタ）
            E("LOADI", 2, 0, 5),     # 2: r2 = 5（残り個数）
            E("LOADI", 3, 0, 1),     # 3: r3 = 1
            E("LOAD", 4, 1),         # 4: r4 = メモリ[r1]
            E("ADD", 0, 4),          # 5
            E("ADD", 1, 3),          # 6
            E("SUB", 2, 3),          # 7
            E("JNZ", imm=4),         # 8
            E("HALT"),               # 9
        ]
        cpu = run_program(prog, memory={100: 3, 101: 1, 102: 4, 103: 1, 104: 5})
        self.assertEqual(cpu.regs[0], 14)


FIB_SOURCE = """
; メモリ 0 番地から、フィボナッチ数列の最初の N 項を書き込む
        LOADI r0, 0          ; a
        LOADI r1, 1          ; b
        LOADI r2, {n}        ; 残り回数
        LOADI r3, 1          ; 定数 1
        LOADI r4, 0          ; 書き込み先の番地
loop:   STORE r0, [r4]
        ADD   r4, r3
        MOV   r5, r0
        ADD   r5, r1         ; r5 = a + b
        MOV   r0, r1         ; a = b
        MOV   r1, r5         ; b = a + b
        SUB   r2, r3
        JNZ   loop
        HALT
"""


class TestExercise4Assembler(unittest.TestCase):
    def test_docstring_examples(self):
        self.assertEqual(assemble("LOADI r1, 10\nHALT"), [0x0110000A, 0x00000000])
        self.assertEqual(assemble("loop: JMP loop"), [0x0B000000])

    def test_all_operand_kinds(self):
        source = """
            LOADI r7, 0x1F     ; 16 進数
            MOV   r1, r2
            ADD   r3, r4
            SHL   r5, 3
            LOAD  r6, [r1]
            STORE r2, [r3+200]
            CMP   r0, r7
            HALT
        """
        expected = [
            E("LOADI", 7, 0, 0x1F), E("MOV", 1, 2), E("ADD", 3, 4), E("SHL", 5, 0, 3),
            E("LOAD", 6, 1, 0), E("STORE", 2, 3, 200), E("CMP", 0, 7), E("HALT"),
        ]
        self.assertEqual(assemble(source), expected)

    def test_case_insensitive_and_spacing(self):
        self.assertEqual(assemble("  add R0,r1\n\tSub\tr2 , R3"), [E("ADD", 0, 1), E("SUB", 2, 3)])
        self.assertEqual(assemble("load r1, [ r2 + 4 ]"), [E("LOAD", 1, 2, 4)])

    def test_negative_immediate_is_twos_complement(self):
        self.assertEqual(assemble("LOADI r0, -1"), [E("LOADI", 0, 0, 0xFFFF)])
        self.assertEqual(assemble("LOADI r0, -32768"), [E("LOADI", 0, 0, 0x8000)])

    def test_labels_forward_backward_and_own_line(self):
        source = """
        start:
                JMP  end       ; 前方参照
        middle: JZ   start     ; 後方参照
        end:    JNZ  middle
                HALT
        """
        self.assertEqual(assemble(source), [E("JMP", imm=2), E("JZ", imm=0), E("JNZ", imm=1), E("HALT")])

    def test_numeric_jump_target(self):
        self.assertEqual(assemble("JMP 3"), [E("JMP", imm=3)])

    def test_comment_only_and_blank_lines(self):
        self.assertEqual(assemble("; コメントだけ\n\n   \nHALT ; 停止"), [E("HALT")])
        self.assertEqual(assemble(""), [])

    def test_errors_report_line_numbers(self):
        cases = {
            "未知の命令": ("HALT\nMUL r0, r1", 2),
            "オペランドの数": ("HALT\nHALT\nADD r0", 3),
            "レジスタ番号": ("MOV r8, r0", 1),
            "レジスタでない": ("ADD r0, 5", 1),
            "未定義のラベル": ("HALT\nJMP nowhere", 2),
            "ラベルの重複": ("a: HALT\na: HALT", 2),
            "即値が大きすぎる": ("LOADI r0, 65536", 1),
            "即値が小さすぎる": ("LOADI r0, -32769", 1),
            "シフト量": ("SHL r0, 16", 1),
            "数値でない": ("LOADI r0, ten", 1),
            "メモリの書き方": ("LOAD r0, r1", 1),
            "レジスタ名のラベル": ("r1: HALT", 1),
        }
        for label, (source, line) in cases.items():
            with self.assertRaises(AssemblerError, msg=label) as cm:
                assemble(source)
            self.assertRegex(str(cm.exception), rf"^行 ?{line}\b", f"{label}: メッセージは「行 {line}: 」で始める")

    def test_assembler_error_is_value_error(self):
        self.assertTrue(issubclass(AssemblerError, ValueError))

    def test_assembled_fibonacci_runs(self):
        cpu = run_program(assemble(FIB_SOURCE.format(n=10)))
        self.assertEqual(cpu.memory[:10], [0, 1, 1, 2, 3, 5, 8, 13, 21, 34])

    def test_fibonacci_wraps_at_16_bits(self):
        cpu = run_program(assemble(FIB_SOURCE.format(n=30)))
        a, b, expected = 0, 1, []
        for _ in range(30):
            expected.append(a % 65536)
            a, b = b, a + b
        self.assertEqual(cpu.memory[:30], expected)


class TestExercise4MultiplyProgram(unittest.TestCase):
    def run_multiply(self, x: int, y: int) -> CPU:
        return run_program(assemble(MULTIPLY_PROGRAM), regs={1: x, 2: y}, max_steps=300)

    def test_small_products(self):
        for x, y in [(3, 5), (7, 0), (0, 9), (1, 1), (12, 12), (255, 255)]:
            self.assertEqual(self.run_multiply(x, y).regs[0], x * y, f"{x} × {y}")

    def test_wraps_mod_2_16(self):
        self.assertEqual(self.run_multiply(65535, 65535).regs[0], (65535 * 65535) % 65536)
        self.assertEqual(self.run_multiply(300, 300).regs[0], 90000 % 65536)

    def test_random_products(self):
        rng = random.Random(41)
        for _ in range(40):
            x, y = rng.randrange(65536), rng.randrange(65536)
            self.assertEqual(self.run_multiply(x, y).regs[0], (x * y) % 65536, f"{x} × {y}")

    def test_fast_enough_for_large_multiplier(self):
        cpu = self.run_multiply(2, 65535)  # 足し算を 65535 回繰り返す方法では 300 ステップに収まらない
        self.assertEqual(cpu.regs[0], (2 * 65535) % 65536)
        self.assertLessEqual(cpu.steps, 300)


if __name__ == "__main__":
    unittest.main()
