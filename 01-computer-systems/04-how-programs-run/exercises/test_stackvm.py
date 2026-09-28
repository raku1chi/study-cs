"""1.4 演習1〜4 のテスト: スタックマシン型の仮想マシン

実行: python3 tools/check.py 1.4   （またはこのディレクトリで python3 -m unittest -v test_stackvm）
"""
import math
import sys
import unittest

from stackvm import (
    VM,
    AssemblerError,
    StackOverflowError,
    VMError,
    assemble,
    factorial_iterative,
    factorial_recursive,
    fibonacci,
)


def run(code, **kwargs):
    return VM(code, **kwargs).run()


# square(x) = x * x を呼ぶプログラム（アセンブラを使わずに番地を手で書いたもの）
SQUARE_PROGRAM = [
    ("PUSH", 7),        # 0
    ("CALL", 4, 1),     # 1: square(7)
    ("HALT",),          # 2
    ("HALT",),          # 3（使われない）
    ("LOAD", 0),        # 4: square
    ("LOAD", 0),        # 5
    ("MUL",),           # 6
    ("RET",),           # 7
]


class TestExercise1Arithmetic(unittest.TestCase):
    def test_push_add_halt(self):
        self.assertEqual(run([("PUSH", 2), ("PUSH", 3), ("ADD",), ("HALT",)]), 5)

    def test_operand_order(self):
        # a を先に積み、b を後に積む。SUB は a - b
        self.assertEqual(run([("PUSH", 7), ("PUSH", 2), ("SUB",), ("HALT",)]), 5)
        self.assertEqual(run([("PUSH", 7), ("PUSH", 2), ("DIV",), ("HALT",)]), 3)
        self.assertEqual(run([("PUSH", 7), ("PUSH", 2), ("MOD",), ("HALT",)]), 1)
        self.assertEqual(run([("PUSH", -7), ("PUSH", 2), ("DIV",), ("HALT",)]), -4, "Python の // と同じ")
        self.assertEqual(run([("PUSH", 6), ("PUSH", 7), ("MUL",), ("HALT",)]), 42)

    def test_comparisons(self):
        self.assertEqual(run([("PUSH", 3), ("PUSH", 3), ("EQ",), ("HALT",)]), 1)
        self.assertEqual(run([("PUSH", 3), ("PUSH", 4), ("EQ",), ("HALT",)]), 0)
        self.assertEqual(run([("PUSH", 3), ("PUSH", 4), ("LT",), ("HALT",)]), 1)
        self.assertEqual(run([("PUSH", 4), ("PUSH", 3), ("LT",), ("HALT",)]), 0)

    def test_dup_swap_pop(self):
        self.assertEqual(run([("PUSH", 5), ("DUP",), ("MUL",), ("HALT",)]), 25)
        self.assertEqual(run([("PUSH", 1), ("PUSH", 10), ("SWAP",), ("SUB",), ("HALT",)]), 9)
        self.assertEqual(run([("PUSH", 1), ("PUSH", 2), ("POP",), ("HALT",)]), 1)

    def test_halt_with_empty_stack_returns_none(self):
        self.assertIsNone(run([("HALT",)]))

    def test_locals(self):
        code = [("PUSH", 42), ("STORE", 3), ("LOAD", 3), ("LOAD", 3), ("ADD",), ("LOAD", 15), ("ADD",), ("HALT",)]
        self.assertEqual(run(code), 84, "locals は 0 で初期化されている")

    def test_jumps(self):
        # 10 から 1 ずつ減らし、0 になるまでの回数を数える
        code = [
            ("PUSH", 10), ("STORE", 0),      # 0-1: k = 10
            ("PUSH", 0), ("STORE", 1),       # 2-3: count = 0
            ("LOAD", 0), ("JZ", 15),         # 4-5: k == 0 なら 15 へ
            ("LOAD", 0), ("PUSH", 1), ("SUB",), ("STORE", 0),       # 6-9: k -= 1
            ("LOAD", 1), ("PUSH", 1), ("ADD",), ("STORE", 1),       # 10-13: count += 1
            ("JMP", 4),                      # 14
            ("LOAD", 1), ("HALT",),          # 15-16
        ]
        vm = VM(code)
        self.assertEqual(vm.run(), 10)
        self.assertTrue(vm.halted)
        # 初期化 4 + ループ 1 周 11 命令 × 10 周 + 最後の判定 2 + 後始末 2
        self.assertEqual(vm.steps, 4 + 11 * 10 + 2 + 2)

    def test_step_counts_instructions(self):
        vm = VM([("PUSH", 1), ("PUSH", 2), ("ADD",), ("HALT",)])
        vm.step()
        vm.step()
        self.assertEqual((vm.pc, vm.steps, vm.frame.stack), (2, 2, [1, 2]))
        vm.run()
        self.assertEqual(vm.steps, 4)


class TestExercise1Calls(unittest.TestCase):
    def test_call_and_return(self):
        vm = VM(SQUARE_PROGRAM)
        self.assertEqual(vm.run(), 49)
        self.assertEqual(len(vm.frames), 1, "RET でフレームが捨てられている")
        self.assertEqual(vm.pc, 3, "HALT（番地 2）の次を指して止まる")

    def test_arguments_go_to_locals_in_push_order(self):
        # f(a, b) = a - b を f(10, 3) で呼ぶ
        code = [
            ("PUSH", 10), ("PUSH", 3), ("CALL", 4, 2), ("HALT",),
            ("LOAD", 0), ("LOAD", 1), ("SUB",), ("RET",),
        ]
        self.assertEqual(run(code), 7)

    def test_frames_have_separate_locals_and_stacks(self):
        code = [
            ("PUSH", 111), ("STORE", 0),        # 0-1: 呼び出し側の locals[0] = 111
            ("PUSH", 5),                         # 2: 呼び出し側のスタックに 5 を残しておく
            ("PUSH", 1), ("CALL", 9, 1),         # 3-4: g(1)
            ("ADD",),                            # 5: 5 + g(1)
            ("LOAD", 0), ("ADD",),               # 6-7: + 111（呼ばれた側に書き換えられていない）
            ("HALT",),                           # 8
            ("PUSH", 999), ("STORE", 0),         # 9-10: g の locals[0] を書き換える
            ("PUSH", 77), ("PUSH", 20),          # 11-12: g のスタックにゴミを残す
            ("RET",),                            # 13: 20 を返す（77 はフレームと一緒に捨てられる）
        ]
        self.assertEqual(run(code), 5 + 20 + 111)

    def test_recursive_calls(self):
        # sum(n) = n + sum(n-1), sum(0) = 0 を再帰で
        code = [
            ("PUSH", 100), ("CALL", 3, 1), ("HALT",),
            ("LOAD", 0), ("JZ", 12),                         # 3-4: n == 0 なら 12 へ
            ("LOAD", 0), ("LOAD", 0), ("PUSH", 1), ("SUB",),  # 5-8
            ("CALL", 3, 1), ("ADD",), ("RET",),              # 9-11: n + sum(n-1)
            ("PUSH", 0), ("RET",),                           # 12-13
        ]
        self.assertEqual(run(code), 5050)

    def test_errors(self):
        cases = {
            "空のスタックから取り出す": [("ADD",), ("HALT",)],
            "未知の命令": [("NOP",), ("HALT",)],
            "引数の個数の誤り": [("PUSH",), ("HALT",)],
            "整数でない引数": [("PUSH", "x"), ("HALT",)],
            "0 除算": [("PUSH", 1), ("PUSH", 0), ("DIV",), ("HALT",)],
            "MOD の 0 除算": [("PUSH", 1), ("PUSH", 0), ("MOD",), ("HALT",)],
            "ローカル変数の番号": [("LOAD", 16), ("HALT",)],
            "HALT がない": [("PUSH", 1)],
            "範囲外へのジャンプ": [("JMP", 99)],
            "最初のフレームで RET": [("PUSH", 1), ("RET",)],
            "引数が足りない CALL": [("CALL", 2, 2), ("HALT",), ("RET",)],
            "戻り値のない RET": [("CALL", 2, 0), ("HALT",), ("RET",)],
        }
        for label, code in cases.items():
            with self.assertRaises(VMError, msg=label):
                run(code)

    def test_step_limit(self):
        with self.assertRaises(VMError):
            run([("JMP", 0)], max_steps=1000)

    def test_step_after_halt(self):
        vm = VM([("HALT",)])
        vm.run()
        with self.assertRaises(VMError):
            vm.step()


def recursion_program(depth_arg: int):
    """f(n) = f(n - 1)（n == 0 なら 0）。n + 1 段の呼び出しになる。"""
    return [
        ("PUSH", depth_arg), ("CALL", 3, 1), ("HALT",),
        ("LOAD", 0), ("JZ", 10),
        ("LOAD", 0), ("PUSH", 1), ("SUB",), ("CALL", 3, 1), ("RET",),
        ("PUSH", 0), ("RET",),
    ]


class TestExercise2StackOverflow(unittest.TestCase):
    def test_infinite_recursion_is_stopped(self):
        code = [("CALL", 0, 0)]  # 自分自身を呼び続ける
        with self.assertRaises(StackOverflowError):
            run(code, max_depth=50)

    def test_stack_overflow_is_a_vm_error(self):
        self.assertTrue(issubclass(StackOverflowError, VMError))

    def test_depth_limit_is_exact(self):
        # f(n) は最初のフレームを含めて n + 2 個のフレームを使う
        self.assertEqual(run(recursion_program(8), max_depth=10), 0)
        with self.assertRaises(StackOverflowError):
            run(recursion_program(9), max_depth=10)

    def test_message_is_clear(self):
        with self.assertRaises(StackOverflowError) as cm:
            run([("CALL", 0, 0)], max_depth=20)
        self.assertIn("20", str(cm.exception), "上限の値をメッセージに含める")

    def test_deep_recursion_does_not_use_python_stack(self):
        # Python の再帰の上限（既定で 1000）より深い呼び出しでも、VM の上限の範囲なら動くこと
        depth = sys.getrecursionlimit() + 500
        self.assertEqual(run(recursion_program(depth), max_depth=depth + 10), 0)


FACTORIAL_SOURCE = """
; 反復で 5! を求める
        PUSH 1
        STORE 0          ; acc = 1
        PUSH 5
        STORE 1          ; k = 5
loop:   LOAD 1
        JZ done          ; k == 0 なら終わり
        LOAD 0
        LOAD 1
        MUL
        STORE 0          ; acc *= k
        LOAD 1
        PUSH 1
        SUB
        STORE 1          ; k -= 1
        JMP loop
done:   LOAD 0
        HALT
"""


class TestExercise3Assembler(unittest.TestCase):
    def test_docstring_example(self):
        self.assertEqual(assemble("PUSH 1\nloop: PUSH 2\nJMP loop"), [("PUSH", 1), ("PUSH", 2), ("JMP", 1)])

    def test_labels_comments_and_case(self):
        code = assemble(FACTORIAL_SOURCE)
        self.assertEqual(code[4], ("LOAD", 1))
        self.assertEqual(code[5], ("JZ", 15), "前方参照のラベル done は 15 番地")
        self.assertEqual(code[14], ("JMP", 4), "後方参照のラベル loop は 4 番地")
        self.assertEqual(len(code), 17)
        self.assertEqual(run(code), 120)
        self.assertEqual(assemble("push -3\n  halt  ; 停止"), [("PUSH", -3), ("HALT",)])

    def test_call_with_label_and_argument_count(self):
        code = assemble("""
            PUSH 6
            CALL double, 1
            HALT
    double: LOAD 0
            PUSH 2
            MUL
            RET
        """)
        self.assertEqual(code[1], ("CALL", 3, 1))
        self.assertEqual(run(code), 12)

    def test_label_on_its_own_line(self):
        self.assertEqual(assemble("start:\n\n  JMP start"), [("JMP", 0)])

    def test_empty_source(self):
        self.assertEqual(assemble("; なにもない\n"), [])

    def test_errors_report_line_numbers(self):
        cases = {
            "未知の命令": ("PUSH 1\nPUSHH 2", 2),
            "引数の個数": ("CALL f", 1),
            "未定義のラベル": ("PUSH 1\nPUSH 2\nJMP nowhere", 3),
            "ラベルの重複": ("a: PUSH 1\na: PUSH 2", 2),
            "不正な引数": ("PUSH 1.5", 1),
        }
        for label, (source, line) in cases.items():
            with self.assertRaises(AssemblerError, msg=label) as cm:
                assemble(source)
            self.assertRegex(str(cm.exception), rf"^行 ?{line}\b", f"{label}: メッセージは「行 {line}: 」で始める")


class TestExercise4Programs(unittest.TestCase):
    def test_factorial_iterative(self):
        for n in range(0, 13):
            self.assertEqual(run(factorial_iterative(n)), math.factorial(n), f"{n}!")
        self.assertEqual(run(factorial_iterative(25)), math.factorial(25))

    def test_factorial_iterative_uses_no_calls(self):
        ops = {instr[0] for instr in factorial_iterative(5)}
        self.assertNotIn("CALL", ops, "反復版は CALL を使わない")

    def test_factorial_recursive(self):
        for n in range(0, 13):
            self.assertEqual(run(factorial_recursive(n)), math.factorial(n), f"{n}!")

    def test_factorial_recursive_really_recurses(self):
        ops = {instr[0] for instr in factorial_recursive(5)}
        self.assertIn("CALL", ops)
        self.assertIn("RET", ops)
        # 深さの上限を小さくすると、再帰の深さが足りずに止まる
        self.assertEqual(run(factorial_recursive(5), max_depth=10), 120)
        with self.assertRaises(StackOverflowError):
            run(factorial_recursive(50), max_depth=10)

    def test_factorial_recursive_deep(self):
        self.assertEqual(run(factorial_recursive(900)), math.factorial(900))
        with self.assertRaises(StackOverflowError):
            run(factorial_recursive(3000))  # 既定の max_depth=1000 を超える

    def test_fibonacci(self):
        a, b = 0, 1
        for n in range(0, 31):
            self.assertEqual(run(fibonacci(n)), a, f"F({n})")
            a, b = b, a + b


if __name__ == "__main__":
    unittest.main()
