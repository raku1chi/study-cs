"""1.4 演習5 のテスト: 小さなリンカ

実行: python3 tools/check.py 1.4   （またはこのディレクトリで python3 -m unittest -v test_minilinker）
"""
import copy
import unittest

from minilinker import START_CODE_SIZE, LinkError, ObjectModule, link
from stackvm import VM


def main_module():
    # main: return square(7)
    return ObjectModule(
        name="main",
        code=[("PUSH", 7), ("CALL", 0, 1), ("RET",)],
        symbols={"main": 0},
        relocations=[(1, "square")],
    )


def mathlib_module():
    # square(x) = x * x
    return ObjectModule(
        name="mathlib",
        code=[("LOAD", 0), ("LOAD", 0), ("MUL",), ("RET",)],
        symbols={"square": 0},
    )


def counter_module(name, symbol, times):
    """times 回ループして times を返す関数。ループの先頭はローカルシンボル loop。"""
    return ObjectModule(
        name=name,
        code=[
            ("PUSH", times), ("STORE", 0),           # 0-1: k = times
            ("PUSH", 0), ("STORE", 1),               # 2-3: count = 0
            ("LOAD", 0), ("JZ", 0),                  # 4-5: k == 0 なら done へ（再配置）
            ("LOAD", 0), ("PUSH", 1), ("SUB",), ("STORE", 0),
            ("LOAD", 1), ("PUSH", 1), ("ADD",), ("STORE", 1),
            ("JMP", 0),                              # 14: loop へ（再配置）
            ("LOAD", 1), ("RET",),                   # 15-16: done
        ],
        symbols={symbol: 0},
        local_symbols={"loop": 4, "done": 15},
        relocations=[(5, "done"), (14, "loop")],
    )


class TestExercise5Link(unittest.TestCase):
    def test_docstring_example(self):
        code, table = link([main_module(), mathlib_module()])
        self.assertEqual(table, {"main": 2, "square": 5})
        self.assertEqual(code, [
            ("CALL", 2, 0), ("HALT",),
            ("PUSH", 7), ("CALL", 5, 1), ("RET",),
            ("LOAD", 0), ("LOAD", 0), ("MUL",), ("RET",),
        ])
        self.assertEqual(START_CODE_SIZE, 2)

    def test_linked_program_runs(self):
        code, _ = link([main_module(), mathlib_module()])
        self.assertEqual(VM(code).run(), 49)

    def test_module_order_changes_addresses_not_behavior(self):
        code, table = link([mathlib_module(), main_module()])
        self.assertEqual(table, {"square": 2, "main": 6})
        self.assertEqual(code[0], ("CALL", 6, 0), "スタートアップコードは entry を呼ぶ")
        self.assertEqual(VM(code).run(), 49)

    def test_local_symbols_are_relocated_by_module_base(self):
        caller = ObjectModule(
            name="main",
            code=[("CALL", 0, 0), ("CALL", 0, 0), ("ADD",), ("RET",)],
            symbols={"main": 0},
            relocations=[(0, "three"), (1, "five")],
        )
        a = counter_module("a", "three", 3)
        b = counter_module("b", "five", 5)  # 同じ名前のローカルシンボル loop / done を持つ
        code, table = link([caller, a, b])
        self.assertEqual(table["three"], 2 + 4)
        self.assertEqual(table["five"], 2 + 4 + 17)
        self.assertEqual(code[table["three"] + 5], ("JZ", table["three"] + 15))
        self.assertEqual(code[table["five"] + 14], ("JMP", table["five"] + 4))
        self.assertEqual(VM(code).run(), 8)

    def test_local_symbol_takes_precedence_and_is_invisible_elsewhere(self):
        lib = ObjectModule(
            name="lib",
            code=[("PUSH", 1), ("RET",), ("PUSH", 2), ("RET",)],
            symbols={"api": 0},
            local_symbols={"helper": 2},
        )
        user = ObjectModule(
            name="main",
            code=[("CALL", 0, 0), ("RET",)],
            symbols={"main": 0},
            relocations=[(0, "helper")],  # 他のモジュールのローカルシンボルは見えない
        )
        with self.assertRaises(LinkError):
            link([user, lib])

    def test_cross_module_recursion(self):
        # fact は自分自身をグローバルシンボルとして参照する（再配置が必要）
        fact = ObjectModule(
            name="fact",
            code=[
                ("LOAD", 0), ("PUSH", 2), ("LT",), ("JZ", 0),       # 0-3: n < 2 でなければ recurse へ
                ("PUSH", 1), ("RET",),                                # 4-5
                ("LOAD", 0), ("LOAD", 0), ("PUSH", 1), ("SUB",),      # 6-9: recurse
                ("CALL", 0, 1), ("MUL",), ("RET",),                   # 10-12
            ],
            symbols={"fact": 0},
            local_symbols={"recurse": 6},
            relocations=[(3, "recurse"), (10, "fact")],
        )
        main = ObjectModule(
            name="main",
            code=[("PUSH", 10), ("CALL", 0, 1), ("RET",)],
            symbols={"main": 0},
            relocations=[(1, "fact")],
        )
        code, _ = link([fact, main])
        self.assertEqual(VM(code).run(), 3628800)

    def test_does_not_modify_input_modules(self):
        modules = [main_module(), mathlib_module()]
        before = copy.deepcopy(modules)
        link(modules)
        self.assertEqual(modules, before)

    def test_custom_entry(self):
        start = ObjectModule(name="start", code=[("PUSH", 3), ("RET",)], symbols={"start": 0})
        code, _ = link([start], entry="start")
        self.assertEqual(VM(code).run(), 3)


class TestExercise5LinkErrors(unittest.TestCase):
    def assert_link_error(self, modules, *fragments, entry="main"):
        with self.assertRaises(LinkError) as cm:
            link(modules, entry=entry)
        for fragment in fragments:
            self.assertIn(fragment, str(cm.exception), "エラーメッセージに原因のシンボル名などを含める")

    def test_undefined_symbol(self):
        self.assert_link_error([main_module()], "square")

    def test_multiple_definition(self):
        other = ObjectModule(name="other", code=[("PUSH", 0), ("RET",)], symbols={"square": 0})
        self.assert_link_error([main_module(), mathlib_module(), other], "square")

    def test_missing_entry(self):
        self.assert_link_error([mathlib_module()], "main")
        self.assert_link_error([main_module(), mathlib_module()], "start", entry="start")

    def test_relocation_out_of_range(self):
        bad = main_module()
        bad.relocations = [(10, "square")]
        self.assert_link_error([bad, mathlib_module()])

    def test_relocation_on_instruction_without_argument(self):
        bad = main_module()
        bad.relocations = [(2, "square")]  # ("RET",) には書き換える引数がない
        self.assert_link_error([bad, mathlib_module()])

    def test_symbol_offset_out_of_range(self):
        bad = mathlib_module()
        bad.symbols = {"square": 4}
        self.assert_link_error([main_module(), bad])


if __name__ == "__main__":
    unittest.main()
