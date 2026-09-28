"""8.1 良いコードと設計原則 — 解答例: 設計の「におい」を測る静的解析器

仕様は exercises/design_smells.py の docstring を参照してください。
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Union

SMELL_KINDS = ("long_function", "too_many_params", "deep_nesting", "high_complexity")

FunctionNode = Union[ast.FunctionDef, ast.AsyncFunctionDef]
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# 本体に入ると入れ子が 1 段深くなる文。TryStar（except*）は Python 3.11 以降にだけある
NESTING_NODES: tuple[type, ...] = (
    ast.If, ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith, ast.Try, ast.Match,
) + ((ast.TryStar,) if hasattr(ast, "TryStar") else ())


@dataclass(frozen=True)
class FunctionMetrics:
    name: str
    lineno: int
    length: int
    params: int
    max_nesting: int
    complexity: int


@dataclass(frozen=True)
class Smell:
    name: str
    lineno: int
    kind: str
    value: int
    limit: int


# ---------------------------------------------------------------------------
# 測定
# ---------------------------------------------------------------------------

def analyze_source(source: str) -> list[FunctionMetrics]:
    tree = ast.parse(source)
    found: list[tuple[int, int, FunctionMetrics]] = []

    def visit(node: ast.AST, prefix: str, in_class: bool) -> None:
        # 関数・クラスを探しながら、修飾名の接頭辞を組み立てる
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                found.append((child.lineno, child.col_offset, _measure(child, name, in_class)))
                visit(child, f"{name}.", in_class=False)
            elif isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.", in_class=True)
            else:
                visit(child, prefix, in_class=False)

    visit(tree, "", in_class=False)
    return [metrics for _, _, metrics in sorted(found, key=lambda t: (t[0], t[1]))]


def _measure(func: FunctionNode, name: str, is_method: bool) -> FunctionMetrics:
    return FunctionMetrics(
        name=name,
        lineno=func.lineno,
        length=func.end_lineno - func.lineno + 1,
        params=_count_params(func.args, is_method),
        max_nesting=max((_nesting(stmt, 0) for stmt in func.body), default=0),
        complexity=1 + sum(_decisions(stmt) for stmt in func.body),
    )


def _count_params(args: ast.arguments, is_method: bool) -> int:
    positional = [*args.posonlyargs, *args.args]
    count = len(positional) + len(args.kwonlyargs)
    count += (args.vararg is not None) + (args.kwarg is not None)
    if is_method and positional and positional[0].arg in ("self", "cls"):
        count -= 1
    return count


def _is_elif(node: ast.If) -> bool:
    """node.orelse が elif か（`else:` の中に書いた if ではないか）。"""
    return (
        len(node.orelse) == 1
        and isinstance(node.orelse[0], ast.If)
        and node.orelse[0].col_offset == node.col_offset
    )


def _nesting(node: ast.AST, depth: int) -> int:
    """node 以下で到達する最大の入れ子の深さを返す。depth は node が置かれている深さ。"""
    if isinstance(node, SCOPE_NODES):
        return depth  # 入れ子の関数・クラスは別に測るので、中には入らない
    if isinstance(node, ast.If) and _is_elif(node):
        # if の本体は 1 段深い。elif の連鎖は if と同じ深さとして続ける
        return max(
            max((_nesting(s, depth + 1) for s in node.body), default=depth + 1),
            _nesting(node.orelse[0], depth),
        )
    if isinstance(node, NESTING_NODES):
        inner = depth + 1
        best = inner
        for child in ast.iter_child_nodes(node):
            # body・orelse・handlers・finalbody・cases の中身はすべて 1 段深い
            best = max(best, _nesting(child, inner))
        return best
    # それ以外（式、except 節や case のような入れ物）は深さを変えずに子を調べる
    return max((_nesting(child, depth) for child in ast.iter_child_nodes(node)), default=depth)


def _decisions(node: ast.AST) -> int:
    """node 以下にある分岐点の数（入れ子の関数・クラスの中は数えない）。"""
    if isinstance(node, SCOPE_NODES):
        return 0
    count = 0
    if isinstance(node, (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler)):
        count += 1
    elif isinstance(node, ast.BoolOp):
        count += len(node.values) - 1
    elif isinstance(node, ast.comprehension):
        count += 1 + len(node.ifs)
    elif isinstance(node, ast.match_case) and not _is_wildcard_case(node):
        count += 1
    return count + sum(_decisions(child) for child in ast.iter_child_nodes(node))


def _is_wildcard_case(case: ast.match_case) -> bool:
    pattern = case.pattern
    return case.guard is None and isinstance(pattern, ast.MatchAs) and pattern.pattern is None and pattern.name is None


# ---------------------------------------------------------------------------
# 判定と報告
# ---------------------------------------------------------------------------

def find_smells(
    source: str,
    *,
    max_length: int = 40,
    max_params: int = 4,
    max_nesting: int = 3,
    max_complexity: int = 10,
) -> list[Smell]:
    smells: list[Smell] = []
    for m in analyze_source(source):
        checks = (
            ("long_function", m.length, max_length),
            ("too_many_params", m.params, max_params),
            ("deep_nesting", m.max_nesting, max_nesting),
            ("high_complexity", m.complexity, max_complexity),
        )
        smells.extend(Smell(m.name, m.lineno, kind, value, limit) for kind, value, limit in checks if value > limit)
    return smells


MESSAGES = {
    "long_function": "関数が長すぎます（{value} 行 > {limit}）",
    "too_many_params": "引数が多すぎます（{value} > {limit}）",
    "deep_nesting": "入れ子が深すぎます（{value} > {limit}）",
    "high_complexity": "循環的複雑度が高すぎます（{value} > {limit}）",
}


def format_report(smells: list[Smell], filename: str = "<source>") -> str:
    if not smells:
        return f"{filename}: 問題は見つかりませんでした"
    return "\n".join(
        f"{filename}:{s.lineno} {s.name}: " + MESSAGES[s.kind].format(value=s.value, limit=s.limit)
        for s in smells
    )


def main(argv: list[str]) -> int:
    exit_code = 0
    for path in argv:
        smells = find_smells(Path(path).read_text(encoding="utf-8"))
        print(format_report(smells, filename=path))
        if smells:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
