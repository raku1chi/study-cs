"""8.2 テスト戦略 — 解答例: ミニ・ミューテーションテスト

仕様は exercises/mutation.py の docstring を参照してください。

設計: 変異箇所の「列挙」と「書き換え」を、同じ訪問順（ast.NodeTransformer の深さ優先・前順）で
行う 1 つのクラス _Mutator にまとめています。列挙では変異箇所を数えるだけ、書き換えでは
k 番目の箇所だけを変えます。こうすると、2 つの処理で順序がずれる種類のバグが起きません。
"""
from __future__ import annotations

import ast
import copy
from dataclasses import dataclass, field
from typing import Callable, Optional, Union

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]

ARITHMETIC: dict[type, type] = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.Div,
    ast.Div: ast.Mult,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}
COMPARISON: dict[type, tuple[type, ...]] = {
    ast.Lt: (ast.LtE, ast.GtE),
    ast.LtE: (ast.Lt, ast.Gt),
    ast.Gt: (ast.GtE, ast.LtE),
    ast.GtE: (ast.Gt, ast.Lt),
    ast.Eq: (ast.NotEq,),
    ast.NotEq: (ast.Eq,),
    ast.Is: (ast.IsNot,),
    ast.IsNot: (ast.Is,),
    ast.In: (ast.NotIn,),
    ast.NotIn: (ast.In,),
}
SYMBOLS: dict[type, str] = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%",
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
    ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in",
    ast.And: "and", ast.Or: "or",
}

# (kind, original, replacement, apply)。apply はノードを受け取り、置き換え後のノードを返す
Mutation = tuple[str, str, str, Callable[[ast.AST], ast.AST]]


@dataclass(frozen=True)
class Mutant:
    id: int
    kind: str
    lineno: int
    original: str
    replacement: str
    source: str


@dataclass
class MutationReport:
    total: int
    killed: int
    survived: list[Mutant] = field(default_factory=list)

    @property
    def score(self) -> float:
        return self.killed / self.total if self.total else 1.0


# ---------------------------------------------------------------------------
# 変異の規則
# ---------------------------------------------------------------------------

def _set_attr(name: str, value_factory: Callable[[], object]) -> Callable[[ast.AST], ast.AST]:
    def apply(node: ast.AST) -> ast.AST:
        setattr(node, name, value_factory())
        return node
    return apply


def _replace_compare_op(index: int, new_op: type) -> Callable[[ast.AST], ast.AST]:
    def apply(node: ast.AST) -> ast.AST:
        node.ops[index] = new_op()
        return node
    return apply


def _negate_test(node: ast.AST) -> ast.AST:
    node.test = ast.UnaryOp(op=ast.Not(), operand=node.test)
    return node


def _mutations_for(node: ast.AST) -> list[Mutation]:
    """1 つのノードに対する変異の一覧（仕様の表の順）。"""
    result: list[Mutation] = []
    if isinstance(node, (ast.BinOp, ast.AugAssign)) and type(node.op) in ARITHMETIC:
        new_op = ARITHMETIC[type(node.op)]
        result.append(("arithmetic", SYMBOLS[type(node.op)], SYMBOLS[new_op], _set_attr("op", new_op)))
    elif isinstance(node, ast.Compare):
        for i, op in enumerate(node.ops):
            for new_op in COMPARISON[type(op)]:
                result.append(("comparison", SYMBOLS[type(op)], SYMBOLS[new_op], _replace_compare_op(i, new_op)))
    elif isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):  # bool は int のサブクラスなので先に判定する
            result.append(("constant", repr(value), repr(not value), _set_attr("value", lambda: not value)))
        elif isinstance(value, int):
            for delta in (1, -1):
                new = value + delta
                result.append(("constant", repr(value), repr(new), _set_attr("value", lambda new=new: new)))
    elif isinstance(node, ast.BoolOp):
        new_op = ast.Or if isinstance(node.op, ast.And) else ast.And
        result.append(("boolean", SYMBOLS[type(node.op)], SYMBOLS[new_op], _set_attr("op", new_op)))
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        result.append(("boolean", "not", "", lambda n: n.operand))
    if isinstance(node, (ast.If, ast.While, ast.IfExp)):
        condition = ast.unparse(node.test)
        result.append(("boolean", condition, f"not ({condition})", _negate_test))
    return result


class _Mutator(ast.NodeTransformer):
    """深さ優先・前順で変異箇所を数える。target を指定すると、その番号の箇所だけを書き換える。"""

    def __init__(self, target: Optional[int] = None):
        self.target = target
        self.count = 0
        self.points: list[tuple[str, int, str, str]] = []

    def visit(self, node: ast.AST) -> ast.AST:
        mutated: Optional[ast.AST] = None
        for kind, original, replacement, apply in _mutations_for(node):
            if self.target is None:
                self.points.append((kind, getattr(node, "lineno", 0), original, replacement))
            elif self.count == self.target:
                mutated = apply(node)
            self.count += 1
        return self.generic_visit(mutated if mutated is not None else node)


# ---------------------------------------------------------------------------
# 変異体の生成と実行
# ---------------------------------------------------------------------------

def _find_function(tree: ast.Module, function_name: str) -> int:
    for index, stmt in enumerate(tree.body):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == function_name:
            return index
    raise ValueError(f"トップレベルの関数 {function_name!r} が見つかりません")


def _mutate_body(func: FunctionNode, target: Optional[int]) -> tuple[FunctionNode, _Mutator]:
    func = copy.deepcopy(func)  # 元の木を書き換えない
    mutator = _Mutator(target)
    # 変異させるのは本体だけ（デコレータ・既定値・型注釈は対象外）
    func.body = [mutator.visit(stmt) for stmt in func.body]
    ast.fix_missing_locations(func)
    return func, mutator


def generate_mutants(source: str, function_name: str) -> list[Mutant]:
    tree = ast.parse(source)
    func = tree.body[_find_function(tree, function_name)]
    _, collector = _mutate_body(func, target=None)
    mutants = []
    for index, (kind, lineno, original, replacement) in enumerate(collector.points):
        mutated, _ = _mutate_body(func, target=index)
        mutants.append(Mutant(index + 1, kind, lineno, original, replacement, ast.unparse(mutated)))
    return mutants


def _load_function(tree: ast.Module, function_name: str, filename: str) -> Callable:
    namespace: dict = {"__name__": "__mutation_target__"}
    exec(compile(tree, filename, "exec"), namespace)
    return namespace[function_name]


def run_mutation_test(
    source: str,
    function_name: str,
    test: Callable[[Callable], None],
) -> MutationReport:
    tree = ast.parse(source)
    position = _find_function(tree, function_name)

    try:
        test(_load_function(tree, function_name, "<original>"))
    except Exception as exc:
        raise ValueError(f"元のコードでテストが失敗しています: {type(exc).__name__}: {exc}") from exc

    mutants = generate_mutants(source, function_name)
    survived: list[Mutant] = []
    for mutant in mutants:
        mutated_tree = copy.deepcopy(tree)
        mutated_tree.body[position] = ast.parse(mutant.source).body[0]
        try:
            test(_load_function(mutated_tree, function_name, f"<mutant {mutant.id}>"))
        except Exception:
            continue  # テストが失敗した = 変異体を殺した
        survived.append(mutant)
    return MutationReport(total=len(mutants), killed=len(mutants) - len(survived), survived=survived)


def format_report(report: MutationReport) -> str:
    lines = [f"変異スコア: {report.score * 100:.1f}%（{report.killed}/{report.total}）"]
    for m in report.survived:
        replacement = m.replacement or "（削除）"
        lines.append(f"  生存 #{m.id}（{m.lineno} 行目, {m.kind}）: {m.original} → {replacement}")
    return "\n".join(lines)
