"""9.1 ソフトウェアアーキテクチャの基礎 — 解答例: アーキテクチャ適応度関数（archcheck）

演習の仕様は exercises/archcheck.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import ast
import json
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# 設定とデータ型（演習ではなく、最初から実装済みの部分）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """レイヤー規則。JSON の設定ファイルから Rules.from_dict / load_rules で作る。"""

    layers: dict[str, str]
    allowed: dict[str, frozenset[str]]
    forbidden_external: dict[str, frozenset[str]] = field(default_factory=dict)
    ignore: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        layers = dict(data["layers"])
        allowed = {name: frozenset(data.get("allowed", {}).get(name, [])) for name in layers}
        unknown = {dep for deps in allowed.values() for dep in deps} - set(layers)
        if unknown:
            raise ValueError(f"allowed に未定義のレイヤーがあります: {sorted(unknown)}")
        forbidden = {k: frozenset(v) for k, v in data.get("forbidden_external", {}).items()}
        return cls(layers, allowed, forbidden, frozenset(data.get("ignore", [])))


def load_rules(path: Path) -> Rules:
    return Rules.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True, order=True)
class Violation:
    kind: str  # "layer" | "external" | "unassigned"
    source: str
    target: str
    message: str = field(compare=False)


@dataclass
class DependencyGraph:
    internal: dict[str, set[str]]
    external: dict[str, set[str]]


# ---------------------------------------------------------------------------
# 演習1: モジュール名と相対 import の解決
# ---------------------------------------------------------------------------

def module_name(path: Path, root: Path) -> str:
    rel = Path(path).relative_to(root).with_suffix("")
    parts = list(rel.parts)
    # パッケージの __init__.py は「パッケージそのもの」を表す
    if parts[-1] == "__init__":
        parts.pop()
    if not parts:
        raise ValueError(f"root 直下の __init__.py はモジュール名を持ちません: {path}")
    return ".".join(parts)


def resolve_relative(module: str, is_package: bool, level: int, name: str | None) -> str:
    if level < 1:
        raise ValueError(f"level は 1 以上: {level}")
    # 「自分が属するパッケージ」を起点にする。パッケージ（__init__.py）なら自分自身が起点
    package = module.split(".") if is_package else module.split(".")[:-1]
    # level が 1 増えるごとに 1 つ上のパッケージへ
    up = level - 1
    if up >= len(package):
        raise ValueError(f"{module} からの相対 import（level={level}）がトップレベルを超えています")
    base = package[: len(package) - up]
    return ".".join(base + [name]) if name else ".".join(base)


# ---------------------------------------------------------------------------
# 演習2: ast で import を抽出する
# ---------------------------------------------------------------------------

def imports_of(source: str, module: str, is_package: bool = False) -> set[str]:
    tree = ast.parse(source)  # 構文エラーは SyntaxError としてそのまま伝える
    found: set[str] = set()
    # ast.walk は関数の中・if TYPE_CHECKING の中・try の中も含めて全ノードを巡回する
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)  # "import a.b as c" でも依存先は a.b
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = resolve_relative(module, is_package, node.level, node.module)
            else:
                base = node.module or ""
            if base == "__future__":
                continue  # コンパイラへの指示であって、依存関係ではない
            for alias in node.names:
                # "from x import y" の y はサブモジュールかもしれないので x.y を候補として返す。
                # 本当にモジュールかどうかは build_graph が「存在するモジュール」と照合して決める
                found.add(base if alias.name == "*" else f"{base}.{alias.name}")
    return found


# ---------------------------------------------------------------------------
# 演習3: 依存グラフを作る
# ---------------------------------------------------------------------------

def _python_files(root: Path) -> list[Path]:
    files = []
    for p in sorted(root.rglob("*.py")):
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") or part == "__pycache__" for part in rel_parts):
            continue
        files.append(p)
    return files


def _longest_internal_prefix(dotted: str, modules: set[str]) -> str | None:
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        if candidate in modules:
            return candidate
    return None


def build_graph(root: Path) -> DependencyGraph:
    root = Path(root)
    sources: dict[str, tuple[str, bool]] = {}
    for path in _python_files(root):
        if path.parent == root and path.name == "__init__.py":
            continue
        name = module_name(path, root)
        sources[name] = (path.read_text(encoding="utf-8"), path.name == "__init__.py")

    modules = set(sources)
    top_levels = {m.split(".")[0] for m in modules}
    internal: dict[str, set[str]] = {m: set() for m in modules}
    external: dict[str, set[str]] = {m: set() for m in modules}
    for name, (source, is_package) in sources.items():
        for dotted in imports_of(source, name, is_package):
            target = _longest_internal_prefix(dotted, modules)
            if target is not None:
                if target != name:  # 自分自身への辺は意味がないので捨てる
                    internal[name].add(target)
            elif dotted.split(".")[0] not in top_levels:
                external[name].add(dotted.split(".")[0])
    return DependencyGraph(internal, external)


# ---------------------------------------------------------------------------
# 演習4: レイヤー規則の検査
# ---------------------------------------------------------------------------

def layer_of(module: str, rules: Rules) -> str | None:
    best: tuple[int, str] | None = None
    for layer, prefix in rules.layers.items():
        # "shop.domainx" が "shop.domain" に一致しないよう、ドット区切りの境界で比較する
        if module == prefix or module.startswith(prefix + "."):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), layer)
    return best[1] if best else None


def check_rules(graph: DependencyGraph, rules: Rules) -> list[Violation]:
    violations: set[Violation] = set()
    for module in graph.internal:
        if module in rules.ignore:
            continue
        if layer_of(module, rules) is None:
            violations.add(Violation("unassigned", module, "", f"{module} はどのレイヤーにも属していません"))

    for source, targets in graph.internal.items():
        if source in rules.ignore:
            continue
        src_layer = layer_of(source, rules)
        if src_layer is None:
            continue
        for target in targets:
            if target in rules.ignore:
                continue
            dst_layer = layer_of(target, rules)
            if dst_layer is None or dst_layer == src_layer:
                continue
            if dst_layer not in rules.allowed.get(src_layer, frozenset()):
                violations.add(Violation(
                    "layer", source, target,
                    f"{source} → {target}: レイヤー {src_layer} から {dst_layer} への依存は許可されていません",
                ))

    for source, names in graph.external.items():
        src_layer = layer_of(source, rules)
        if src_layer is None or source in rules.ignore:
            continue
        for name in names & rules.forbidden_external.get(src_layer, frozenset()):
            violations.add(Violation(
                "external", source, name,
                f"{source} → {name}: レイヤー {src_layer} では外部モジュール {name} の使用が禁止されています",
            ))
    return sorted(violations)


# ---------------------------------------------------------------------------
# 演習5: 循環依存の検出（Tarjan の強連結成分分解を反復で）
# ---------------------------------------------------------------------------

def find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    # 辺の先にしか現れないノードも頂点として扱う
    nodes = sorted(set(edges) | {t for ts in edges.values() for t in ts})
    succ = {n: sorted(edges.get(n, ())) for n in nodes}
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    sccs: list[list[str]] = []
    counter = 0

    for start in nodes:
        if start in index:
            continue
        # 再帰の代わりに「(ノード, 次に調べる後続の位置)」の明示的なスタックを使う。
        # 再帰版は数千モジュールの鎖で RecursionError になる
        work: list[tuple[str, int]] = [(start, 0)]
        index[start] = lowlink[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, i = work[-1]
            if i < len(succ[node]):
                work[-1] = (node, i + 1)
                nxt = succ[node][i]
                if nxt not in index:
                    index[nxt] = lowlink[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, 0))
                elif nxt in on_stack:
                    lowlink[node] = min(lowlink[node], index[nxt])
                continue
            # node の後続をすべて調べ終えた
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                # node は強連結成分の根。スタックから node までを取り出す
                component = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    component.append(w)
                    if w == node:
                        break
                if len(component) > 1 or node in edges.get(node, ()):
                    sccs.append(sorted(component))
    return sorted(sccs)


def cycle_example(edges: dict[str, set[str]], members: list[str]) -> list[str]:
    if not members:
        raise ValueError("members が空です")
    allowed = set(members)
    start = min(members)
    if start in edges.get(start, ()):
        return [start, start]
    # start から出発して start に戻る最短経路を、成分の内部だけを通る幅優先探索で探す
    parent: dict[str, str] = {}
    queue = deque()
    for nxt in sorted(edges.get(start, ())):
        if nxt in allowed and nxt not in parent:
            parent[nxt] = start
            queue.append(nxt)
    while queue:
        node = queue.popleft()
        for nxt in sorted(edges.get(node, ())):
            if nxt == start:
                path = [start]
                cur = node
                while cur != start:
                    path.append(cur)
                    cur = parent[cur]
                # path は [start, node, ..., 最初の一歩] の逆順になっているので並べ直す
                return [start] + list(reversed(path[1:])) + [start]
            if nxt in allowed and nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    raise ValueError(f"{sorted(members)} は循環を構成していません")


# ---------------------------------------------------------------------------
# 演習6: まとめて実行する（CI で使えるコマンドにする）
# ---------------------------------------------------------------------------

@dataclass
class Report:
    violations: list[Violation]
    cycles: list[list[str]]

    @property
    def ok(self) -> bool:
        return not self.violations and not self.cycles


def run_check(root: Path, rules: Rules) -> Report:
    graph = build_graph(root)
    return Report(check_rules(graph, rules), find_cycles(graph.internal))


def format_report(report: Report, edges: dict[str, set[str]] | None = None) -> str:
    lines = []
    for v in report.violations:
        lines.append(f"[{v.kind}] {v.message}")
    for members in report.cycles:
        if edges is not None:
            lines.append("[cycle] " + " → ".join(cycle_example(edges, members)))
        else:
            lines.append("[cycle] " + ", ".join(members))
    if report.ok:
        lines.append("OK: 違反はありません")
    else:
        lines.append(f"NG: 違反 {len(report.violations)} 件 / 循環 {len(report.cycles)} 件")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("使い方: python3 archcheck.py <ソースのルート> <規則の JSON>", file=sys.stderr)
        return 2
    root, rules_path = Path(args[0]), Path(args[1])
    graph = build_graph(root)
    report = Report(check_rules(graph, load_rules(rules_path)), find_cycles(graph.internal))
    print(format_report(report, graph.internal))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
