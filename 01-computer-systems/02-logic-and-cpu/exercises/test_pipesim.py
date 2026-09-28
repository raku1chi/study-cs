"""1.2 演習5 のテスト: 5 段パイプラインのデータハザード

実行: python3 tools/check.py 1.2   （またはこのディレクトリで python3 -m unittest -v test_pipesim）
"""
import unittest

from pipesim import Instr, count_stalls, render, schedule, total_cycles


def alu(dst, *srcs):
    return Instr("alu", dst, tuple(srcs))


def load(dst, *srcs):
    return Instr("load", dst, tuple(srcs))


def store(*srcs):
    return Instr("store", None, tuple(srcs))


NOP = Instr("nop")

# Hennessy & Patterson の教科書でおなじみの例: a = b + e; c = b + f;
#   lw t1, b / lw t2, e / add t3, t1, t2 / sw t3, a / lw t4, f / add t5, t1, t4 / sw t5, c
HP_ORIGINAL = [
    load("t1", "gp"), load("t2", "gp"), alu("t3", "t1", "t2"), store("t3", "gp"),
    load("t4", "gp"), alu("t5", "t1", "t4"), store("t5", "gp"),
]
# lw t4 を前に移動するだけで、ロードユースのストールが消える
HP_REORDERED = [HP_ORIGINAL[i] for i in (0, 1, 4, 2, 3, 5, 6)]


class TestExercise5Schedule(unittest.TestCase):
    def test_empty_and_single(self):
        self.assertEqual(schedule([], True), [])
        self.assertEqual(schedule([alu("x1", "x2")], False), [3])
        self.assertEqual(total_cycles([alu("x1", "x2")], False), 5)

    def test_independent_instructions_never_stall(self):
        prog = [alu("x1", "x9"), load("x2", "x9"), alu("x3", "x8"), store("x7", "x6")]
        for fw in (True, False):
            self.assertEqual(schedule(prog, fw), [3, 4, 5, 6], f"forwarding={fw}")
            self.assertEqual(total_cycles(prog, fw), 4 + 4)

    def test_alu_to_alu(self):
        prog = [alu("x1", "x2", "x3"), alu("x4", "x1", "x5")]
        self.assertEqual(schedule(prog, forwarding=False), [3, 6], "WB まで待つ: 2 ストール")
        self.assertEqual(schedule(prog, forwarding=True), [3, 4], "EX→EX の転送でストールなし")

    def test_load_use(self):
        prog = [load("x1", "x2"), alu("x3", "x1", "x4")]
        self.assertEqual(schedule(prog, forwarding=False), [3, 6])
        self.assertEqual(schedule(prog, forwarding=True), [3, 5], "ロードユースは転送しても 1 ストール")

    def test_distance_hides_hazard(self):
        # 間に独立した命令が 1 つあれば、フォワーディングなしでも 1 ストールで済む
        prog = [alu("x1", "x2"), alu("x5", "x6"), alu("x3", "x1")]
        self.assertEqual(schedule(prog, False), [3, 4, 6])
        prog = [alu("x1", "x2"), NOP, NOP, alu("x3", "x1")]
        self.assertEqual(schedule(prog, False), [3, 4, 5, 6], "2 つ離れていれば待たない")
        prog = [load("x1", "x2"), NOP, alu("x3", "x1")]
        self.assertEqual(schedule(prog, True), [3, 4, 5])

    def test_most_recent_writer_matters(self):
        # x1 を load が書いた後に alu が書き直している。読むのは新しい方（alu）の値
        prog = [load("x1", "x9"), alu("x1", "x8"), alu("x2", "x1")]
        self.assertEqual(schedule(prog, True), [3, 4, 5])

    def test_reading_and_writing_same_register(self):
        prog = [alu("x1", "x1", "x2"), alu("x1", "x1", "x2")]
        self.assertEqual(schedule(prog, False), [3, 6])
        self.assertEqual(schedule(prog, True), [3, 4])

    def test_store_waits_for_its_data(self):
        prog = [load("x1", "x2"), store("x1", "x3")]
        self.assertEqual(schedule(prog, True), [3, 5])

    def test_stall_delays_everything_behind(self):
        prog = [load("x1", "x2"), alu("x3", "x1"), alu("x4", "x5"), alu("x6", "x7")]
        self.assertEqual(schedule(prog, True), [3, 5, 6, 7])
        self.assertEqual(count_stalls(prog, True), 1)

    def test_hennessy_patterson_example(self):
        self.assertEqual(schedule(HP_ORIGINAL, True), [3, 4, 6, 7, 8, 10, 11])
        self.assertEqual(count_stalls(HP_ORIGINAL, True), 2)
        self.assertEqual(total_cycles(HP_ORIGINAL, True), 13)
        self.assertEqual(count_stalls(HP_REORDERED, True), 0)
        self.assertEqual(total_cycles(HP_REORDERED, True), 11)
        self.assertEqual(count_stalls(HP_ORIGINAL, False), 8)
        self.assertEqual(count_stalls(HP_REORDERED, False), 5)

    def test_forwarding_never_hurts(self):
        progs = [HP_ORIGINAL, HP_REORDERED, [alu("a", "b"), load("c", "a"), alu("d", "c", "a"), store("d")]]
        for prog in progs:
            self.assertLessEqual(count_stalls(prog, True), count_stalls(prog, False))

    def test_render_uses_schedule(self):
        text = render([alu("x1", "x2"), alu("x3", "x1")], forwarding=False)
        self.assertIn("--", text)
        self.assertEqual(len(text.splitlines()), 3)

    def test_invalid_programs(self):
        bad = [
            [Instr("mul", "x1", ("x2",))],
            [Instr("alu", None, ("x2",))],
            [Instr("load", None, ("x2",))],
            [Instr("store", "x1", ("x2",))],
            [Instr("nop", None, ("x1",))],
        ]
        for prog in bad:
            with self.assertRaises(ValueError, msg=str(prog)):
                schedule(prog, True)


if __name__ == "__main__":
    unittest.main()
