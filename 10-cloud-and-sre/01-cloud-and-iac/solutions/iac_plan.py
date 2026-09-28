"""10.1 クラウドコンピューティングとIaC — 演習（ミニ terraform plan / apply）の解答例

演習の仕様は exercises/iac_plan.py の docstring を参照してください。
「提供コード」の部分（FakeCloud・Change・Plan など）は exercises/ と同一です。
"""
from __future__ import annotations

import copy
import heapq
import re
from dataclasses import dataclass
from typing import Any, Callable, Hashable, Mapping

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

REF_RE = re.compile(r"\$\{([^}]*)\}")
REF_BODY_RE = re.compile(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)\.id")
ADDRESS_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")

Config = Mapping[str, Mapping[str, Any]]
State = dict[str, dict[str, Any]]
Schema = Mapping[str, set[str]]


class CycleError(ValueError):
    """依存関係が循環している。cycle は [a, b, ..., a] の形（cycle[i] は cycle[i+1] に依存）。"""

    def __init__(self, cycle: list[Hashable]) -> None:
        super().__init__("依存関係が循環しています: " + " -> ".join(map(str, cycle)))
        self.cycle = list(cycle)


class CloudError(Exception):
    """架空のクラウド API が返すエラー。"""


class _Unknown:
    """apply するまで値が決まらないことを表す印（Terraform の "known after apply"）。"""

    _instance = None

    def __new__(cls) -> "_Unknown":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "(known after apply)"


UNKNOWN = _Unknown()


def resource_type(address: str) -> str:
    """"aws_vpc.main" → "aws_vpc"。"""
    return address.split(".", 1)[0]


@dataclass(frozen=True)
class Change:
    """1 つのリソースに対する変更。action は "create" / "update" / "replace" / "delete"。"""

    address: str
    action: str
    changed: tuple[str, ...] = ()             # 値が変わる（または apply まで分からない）属性
    forces_replacement: tuple[str, ...] = ()  # changed のうち、置き換えの原因になった属性
    create_before_destroy: bool = False


@dataclass
class Plan:
    changes: dict[str, Change]
    steps: list[tuple[str, str]]  # 実行順の操作: ("create" | "update" | "destroy", アドレス)

    def summary(self) -> str:
        if not self.changes:
            return "No changes. Your infrastructure matches the configuration."
        actions = [c.action for c in self.changes.values()]
        add = sum(a in ("create", "replace") for a in actions)
        change = actions.count("update")
        destroy = sum(a in ("delete", "replace") for a in actions)
        return f"Plan: {add} to add, {change} to change, {destroy} to destroy."

    def render(self) -> str:
        """terraform plan 風の表示。"""
        lines = []
        for address in sorted(self.changes):
            c = self.changes[address]
            if c.action == "create":
                lines.append(f"  + {address}")
            elif c.action == "delete":
                lines.append(f"  - {address}")
            elif c.action == "update":
                lines.append(f"  ~ {address} (update: {', '.join(c.changed)})")
            else:
                mark = "+/-" if c.create_before_destroy else "-/+"
                lines.append(f"{mark} {address} (replace; forces: {', '.join(c.forces_replacement)})")
        lines.append(self.summary())
        return "\n".join(lines)


_ID_RE = re.compile(r"\br-\d{4,}\b")


def _ids_in(value: Any) -> set[str]:
    if isinstance(value, str):
        return set(_ID_RE.findall(value))
    if isinstance(value, Mapping):
        return set().union(*(_ids_in(v) for v in value.values())) if value else set()
    if isinstance(value, (list, tuple)):
        return set().union(*(_ids_in(v) for v in value)) if value else set()
    return set()


def _check_plain(value: Any) -> None:
    if isinstance(value, Mapping):
        for v in value.values():
            _check_plain(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            _check_plain(v)
    elif not isinstance(value, (str, int, float, bool, type(None))):
        raise CloudError(f"InvalidParameter: 送信できない値です: {value!r}")


class FakeCloud:
    """演習用の架空のクラウド API（そのまま使ってください）。

    本物のクラウドと同じように、参照の整合性を検査します。
    - create / update: 属性の中に書かれたリソース ID（"r-0001" の形）が存在しなければ InvalidReference
    - delete: 他のリソースの属性から ID が参照されていれば DependencyViolation
    """

    def __init__(self) -> None:
        self.resources: dict[str, dict[str, Any]] = {}
        self.log: list[str] = []
        self._next_id = 1

    def _check_refs(self, attrs: Mapping[str, Any]) -> None:
        _check_plain(attrs)
        missing = sorted(i for i in _ids_in(attrs) if i not in self.resources)
        if missing:
            raise CloudError(f"InvalidReference: 存在しないリソースを参照しています: {', '.join(missing)}")

    def create(self, rtype: str, attrs: Mapping[str, Any]) -> str:
        self._check_refs(attrs)
        rid = f"r-{self._next_id:04d}"
        self._next_id += 1
        self.resources[rid] = {"type": rtype, "attrs": copy.deepcopy(dict(attrs))}
        self.log.append(f"create {rid} {rtype}")
        return rid

    def update(self, rid: str, attrs: Mapping[str, Any]) -> None:
        if rid not in self.resources:
            raise CloudError(f"NotFound: {rid}")
        self._check_refs(attrs)
        self.resources[rid]["attrs"] = copy.deepcopy(dict(attrs))
        self.log.append(f"update {rid}")

    def delete(self, rid: str) -> None:
        if rid not in self.resources:
            raise CloudError(f"NotFound: {rid}")
        users = sorted(o for o, r in self.resources.items() if o != rid and rid in _ids_in(r["attrs"]))
        if users:
            raise CloudError(f"DependencyViolation: {rid} は {', '.join(users)} から参照されています")
        del self.resources[rid]
        self.log.append(f"delete {rid}")

    def read(self, rid: str) -> dict[str, Any] | None:
        """実在すれば属性のコピーを、なければ None を返す。"""
        r = self.resources.get(rid)
        return copy.deepcopy(r["attrs"]) if r is not None else None


# ===========================================================================
# 演習3: 参照・依存グラフ・トポロジカルソート
# ===========================================================================

def find_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str):
        for m in REF_RE.finditer(value):
            body = REF_BODY_RE.fullmatch(m.group(1))
            if body is None:
                raise ValueError(f"参照は ${{種別.名前.id}} の形で書いてください: {m.group(0)}")
            refs.add(body.group(1))
    elif isinstance(value, Mapping):
        for v in value.values():
            refs |= find_refs(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            refs |= find_refs(v)
    return refs


def resolve(value: Any, lookup: Callable[[str], Any]) -> Any:
    # 1 つでも「まだ分からない」参照を含むなら、値全体が分からない
    if any(lookup(ref) is UNKNOWN for ref in find_refs(value)):
        return UNKNOWN
    return _substitute(value, lookup)


def _substitute(value: Any, lookup: Callable[[str], Any]) -> Any:
    # 入れ物（dict / list）は必ず作り直す。state と config が同じオブジェクトを共有しないように
    if isinstance(value, str):
        return REF_RE.sub(lambda m: str(lookup(REF_BODY_RE.fullmatch(m.group(1)).group(1))), value)
    if isinstance(value, Mapping):
        return {k: _substitute(v, lookup) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_substitute(v, lookup) for v in value]
    return value


def build_graph(config: Config) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for address, spec in config.items():
        if not ADDRESS_RE.fullmatch(address):
            raise ValueError(f"アドレスは「種別.名前」の形にしてください: {address!r}")
        # 暗黙の依存（属性の中の参照）と明示的な依存（depends_on）の和
        graph[address] = find_refs(spec.get("attrs", {})) | set(spec.get("depends_on", ()))
    for address, deps in graph.items():
        for dep in sorted(deps):
            if dep not in graph:
                raise ValueError(f"{address} が未定義のリソース {dep} に依存しています")
    return graph


def topo_sort(
    graph: Mapping[Hashable, set[Hashable]],
    key: Callable[[Hashable], Any] | None = None,
) -> list[Hashable]:
    sort_key = key if key is not None else (lambda n: n)
    for node, deps in graph.items():
        for dep in deps:
            if dep not in graph:
                raise ValueError(f"{node!r} の依存先 {dep!r} がグラフにありません")
    # Kahn のアルゴリズム: 未処理の依存先が 0 個になったノードから順に取り出す。
    # 取り出し候補はヒープで管理し、同順位は key の小さい順にして結果を決定的にする
    pending = {node: len(deps) for node, deps in graph.items()}
    dependents: dict[Hashable, list[Hashable]] = {node: [] for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            dependents[dep].append(node)
    heap = [(sort_key(n), n) for n, count in pending.items() if count == 0]
    heapq.heapify(heap)
    order: list[Hashable] = []
    while heap:
        _, node = heapq.heappop(heap)
        order.append(node)
        for d in dependents[node]:
            pending[d] -= 1
            if pending[d] == 0:
                heapq.heappush(heap, (sort_key(d), d))
    if len(order) == len(graph):
        return order
    # 取り出せずに残ったノードは、必ず「残ったノード」への依存を 1 つ以上持つ。
    # そこから依存をたどり続ければ、いつか同じノードに戻る = 循環が見つかる
    left = {n for n, count in pending.items() if count > 0}
    node = min(left, key=sort_key)
    path: list[Hashable] = []
    seen: dict[Hashable, int] = {}
    while node not in seen:
        seen[node] = len(path)
        path.append(node)
        node = min((d for d in graph[node] if d in left), key=sort_key)
    raise CycleError(path[seen[node]:] + [node])


# ===========================================================================
# 演習4: plan
# ===========================================================================

def plan(config: Config, state: State, schema: Schema) -> Plan:
    graph = build_graph(config)
    order = topo_sort(graph)

    # (1) 依存先から順に、各リソースの action を決める。
    #     依存先が作り直されるなら、その id は apply まで分からない（UNKNOWN）
    changes: dict[str, Change] = {}
    for address in order:
        if address not in state:
            changes[address] = Change(address, "create")
            continue

        def lookup(ref: str) -> Any:
            ch = changes.get(ref)
            if ch is not None and ch.action in ("create", "replace"):
                return UNKNOWN
            return state[ref]["id"]

        desired = {k: resolve(v, lookup) for k, v in config[address].get("attrs", {}).items()}
        current = state[address]["attrs"]
        changed = tuple(sorted(
            k for k in set(desired) | set(current)
            if k not in desired or k not in current or desired[k] is UNKNOWN or desired[k] != current[k]
        ))
        forces = tuple(k for k in changed if k in schema.get(resource_type(address), set()))
        if forces:
            changes[address] = Change(address, "replace", changed, forces)
        elif changed:
            changes[address] = Change(address, "update", changed)

    # (2) 設定から消えたリソースは削除
    for address in sorted(state):
        if address not in config:
            changes[address] = Change(address, "delete")

    # (3) create_before_destroy は依存先にも伝播する（Terraform と同じ）。
    #     依存元だけ「先に作る」と、依存先の作り直しと順序が矛盾してしまうため
    cbd = {a for a, spec in config.items() if spec.get("create_before_destroy")}
    stack = list(cbd)
    while stack:
        for dep in graph[stack.pop()]:
            if dep not in cbd:
                cbd.add(dep)
                stack.append(dep)
    for address, ch in list(changes.items()):
        if ch.action == "replace" and address in cbd:
            changes[address] = Change(address, "replace", ch.changed, ch.forces_replacement, True)

    # (4) 操作のグラフを作る。ops[x] = 「x より先に終わっていなければならない操作」の集合
    ops: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for address, ch in changes.items():
        if ch.action in ("create", "update"):
            ops[(ch.action, address)] = set()
        elif ch.action == "delete":
            ops[("destroy", address)] = set()
        else:  # replace = destroy + create
            ops[("destroy", address)] = set()
            ops[("create", address)] = set()

    def apply_op(address: str) -> tuple[str, str] | None:
        for kind in ("create", "update"):
            if (kind, address) in ops:
                return (kind, address)
        return None

    # 規則1: 作成・更新は、依存先の作成・更新の後
    for address, deps in graph.items():
        me = apply_op(address)
        if me is None:
            continue
        for dep in deps:
            other = apply_op(dep)
            if other is not None:
                ops[me].add(other)
    # 規則2: 削除は逆順。依存元（state に記録された依存関係）を先に消す
    for address, entry in state.items():
        if ("destroy", address) in ops:
            for dep in entry.get("deps", ()):
                if ("destroy", dep) in ops:
                    ops[("destroy", dep)].add(("destroy", address))
    # 規則3: 置き換えは、既定では「消してから作る」。create_before_destroy なら「作ってから消す」
    for address, ch in changes.items():
        if ch.action == "replace":
            if ch.create_before_destroy:
                ops[("destroy", address)].add(("create", address))
            else:
                ops[("create", address)].add(("destroy", address))
    # 規則4: 消されるリソースを参照していた依存元が「更新」されるなら、更新（参照の付け替え）が先
    for address, entry in state.items():
        me = apply_op(address)
        if me is None or me[0] != "update":
            continue
        for dep in entry.get("deps", ()):
            ch = changes.get(dep)
            if ch is not None and (ch.action == "delete" or (ch.action == "replace" and ch.create_before_destroy)):
                ops[("destroy", dep)].add(me)

    # 実行可能なものが複数あれば、削除を優先し、次にアドレス順
    steps = topo_sort(ops, key=lambda op: (0 if op[0] == "destroy" else 1, op[1], op[0]))
    return Plan(changes, steps)


# ===========================================================================
# 演習5: apply と refresh
# ===========================================================================

def apply(plan: Plan, config: Config, state: State, cloud: FakeCloud) -> None:
    graph = build_graph(config)
    for kind, address in plan.steps:
        if kind == "destroy":
            entry = state[address]
            if "deposed" in entry:
                # create_before_destroy で退避しておいた古いオブジェクトを消す
                cloud.delete(entry["deposed"])
                del entry["deposed"]
            else:
                cloud.delete(entry["id"])
                del state[address]
            continue
        # apply の時点では依存先はすべて作成済みなので、参照を実際の id に解決できる
        attrs = {k: resolve(v, lambda ref: state[ref]["id"]) for k, v in config[address].get("attrs", {}).items()}
        if kind == "create":
            new_id = cloud.create(resource_type(address), attrs)
            entry = {"id": new_id, "attrs": attrs, "deps": sorted(graph[address])}
            if address in state:
                entry["deposed"] = state[address]["id"]
            state[address] = entry  # 1 操作ごとに state を更新する（途中で失敗しても進捗が残る）
        else:
            cloud.update(state[address]["id"], attrs)
            state[address]["attrs"] = attrs
            state[address]["deps"] = sorted(graph[address])
    for address in config:
        if address in state:
            state[address]["deps"] = sorted(graph[address])


def refresh(state: State, cloud: FakeCloud) -> dict[str, list[str]]:
    drift: dict[str, list[str]] = {}
    for address in sorted(state):
        entry = state[address]
        actual = cloud.read(entry["id"])
        if actual is None:
            # 管理外で削除されていた: state から外す（次の plan で作り直しになる）
            drift[address] = ["(deleted)"]
            del state[address]
            continue
        recorded = entry["attrs"]
        missing = object()
        keys = sorted(
            k for k in set(recorded) | set(actual)
            if recorded.get(k, missing) != actual.get(k, missing)
        )
        if keys:
            drift[address] = keys
            entry["attrs"] = actual  # state を現実に合わせる。plan が「設定に戻す差分」を出す
    return drift
