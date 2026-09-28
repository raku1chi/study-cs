"""10.1 クラウドコンピューティングとIaC — 演習: ミニ terraform plan / apply

Terraform / OpenTofu の中核である「差分計算（plan）」と「適用（apply）」を小さく作ります。
依存グラフ・トポロジカルソート・置き換えの連鎖・create_before_destroy・ドリフトといった
IaC の実務でつまずく概念が、なぜそう動くのかを実装を通して理解することが目標です。

- 演習3（★★☆）: find_refs, resolve, build_graph, topo_sort — 参照・依存グラフ・実行順序
- 演習4（★★★）: plan — 差分計算、置き換えの連鎖、操作の順序付け
- 演習5（★★☆）: apply, refresh — 適用とドリフト検出
（演習1・2 は iam_eval.py にあります）

データの形:
    config（あるべき姿）: {アドレス: {"attrs": {...}, "depends_on": [...], "create_before_destroy": bool}}
        アドレスは "aws_vpc.main" のような「種別.名前」。depends_on と create_before_destroy は省略可。
        attrs の文字列の中に "${aws_vpc.main.id}" と書くと、そのリソースの id を参照できる。
    state（前回 apply した結果の記録）: {アドレス: {"id": "r-0001", "attrs": {...解決済みの値...},
                                                    "deps": [依存先アドレス, ...]}}
    schema: {種別: 変更すると置き換え（作り直し）が必要な属性名の集合}（Terraform の "forces replacement"）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.1

制約: graphlib モジュールは使わないでください（トポロジカルソートを自分で書くのが演習です）。

簡略化している点: 本物の Terraform は独立した操作を並列に実行し、プロバイダごとのスキーマや
モジュール・変数・count/for_each などを扱います。ここでは 1 つずつ決定的な順に実行します。
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
# 演習3（★★☆）: 参照・依存グラフ・トポロジカルソート
# ===========================================================================

def find_refs(value: Any) -> set[str]:
    """属性値の中に書かれた参照 "${種別.名前.id}" を探し、参照先のアドレスの集合を返す。

    - value は文字列・数値・真偽値・None・list・tuple・dict を任意に入れ子にしたもの。
      dict は値だけを調べる（キーは調べない）。
    - 1 つの文字列の中に参照が埋め込まれていてもよい（"arn:${aws_s3_bucket.logs.id}/*"）。
    - "${...}" の中身が「種別.名前.id」の形でなければ ValueError
      （この演習では .id 以外の属性の参照や、変数 ${var.x} は扱わない）。

    >>> sorted(find_refs({"vpc_id": "${aws_vpc.main.id}", "sgs": ["${aws_security_group.web.id}"]}))
    ['aws_security_group.web', 'aws_vpc.main']

    ヒント: REF_RE で "${...}" を探し、中身を REF_BODY_RE.fullmatch で検査する。
    """
    raise NotImplementedError("演習3: find_refs を実装してください")


def resolve(value: Any, lookup: Callable[[str], Any]) -> Any:
    """value の中の参照を、lookup(アドレス) が返す id に置き換えた「新しい」値を返す。

    - lookup が 1 つでも UNKNOWN を返したら、value 全体の代わりに UNKNOWN を返す
      （Terraform が "(known after apply)" と表示する状態）。
    - dict / list は必ず新しく作り直す（tuple は list にする）。state と config が
      同じオブジェクトを共有すると、片方の変更がもう片方に漏れるため。

    >>> resolve({"vpc_id": "${aws_vpc.main.id}"}, {"aws_vpc.main": "r-0001"}.__getitem__)
    {'vpc_id': 'r-0001'}
    """
    raise NotImplementedError("演習3: resolve を実装してください")


def build_graph(config: Config) -> dict[str, set[str]]:
    """設定から依存グラフ {アドレス: 依存先アドレスの集合} を作る。

    - 依存先 = attrs の中の参照（find_refs） ∪ depends_on に書かれたアドレス
    - アドレスが「種別.名前」の形（ADDRESS_RE）でなければ ValueError
    - 依存先が config にないアドレスなら ValueError
    """
    raise NotImplementedError("演習3: build_graph を実装してください")


def topo_sort(
    graph: Mapping[Hashable, set[Hashable]],
    key: Callable[[Hashable], Any] | None = None,
) -> list[Hashable]:
    """graph（{ノード: そのノードが依存するノードの集合}）をトポロジカルソートする。

    - 返すリストでは、どのノードも自分の依存先より後に来る。
    - 同時に取り出せるノードが複数あるときは key(ノード) が最小のものを先にする
      （key が None ならノードそのものの大小）。これで結果が決定的になる。
    - 依存先がグラフのキーにないときは ValueError。
    - 循環があれば CycleError(cycle) を送出する。cycle は [a, b, ..., a] の形で、
      cycle[i] は cycle[i+1] に依存していること（どの循環を返すかは問わない）。

    >>> topo_sort({"b": {"a"}, "c": {"a"}, "a": set()})
    ['a', 'b', 'c']

    ヒント: Kahn のアルゴリズム（未処理の依存先が 0 になったノードから取り出す）を、
    heapq を使った優先度付きキューで行う。最後まで取り出せなかったノードが残ったら循環がある。
    残ったノードはどれも「残ったノード」への依存を持つので、依存をたどり続ければ同じノードに戻る。
    """
    raise NotImplementedError("演習3: topo_sort を実装してください")


# ===========================================================================
# 演習4（★★★）: plan
# ===========================================================================

def plan(config: Config, state: State, schema: Schema) -> Plan:
    """あるべき姿（config）と前回の記録（state）の差分から、実行計画を作る。config と state は変更しない。

    (1) 各リソースの action を決める。依存先の action が分かっている必要があるので、
        build_graph と topo_sort で求めた順に処理する。
        - state にない → Change(アドレス, "create")
        - state にある → 設定の attrs の各値を resolve して、state の attrs と比べる。
          参照先が "create" または "replace" される場合、その id は apply まで分からないので UNKNOWN、
          それ以外は state に記録された id に置き換える。
          changed = 値が異なる属性・どちらか片方にしかない属性・UNKNOWN の属性の名前（昇順のタプル）
          forces = changed のうち schema[種別] に含まれる属性（昇順）
          forces があれば Change(アドレス, "replace", changed, forces)、
          changed だけなら Change(アドレス, "update", changed)、どちらもなければ変更なし（changes に入れない）。
        この仕組みで「VPC を作り直すとサブネットも作り直しになる」という連鎖が自然に起きる。
    (2) state にあって config にないリソース → Change(アドレス, "delete")
    (3) create_before_destroy（config のリソースに "create_before_destroy": True）は依存先に伝播する:
        A が CBD で、A が B に依存するなら B も CBD とみなす（推移的に）。
        replace のうち CBD のものは create_before_destroy=True の Change にする。
    (4) 実行手順（steps）を「操作のグラフ」のトポロジカルソートで求める。操作は
        ("create", a) / ("update", a) / ("destroy", a) で、replace は destroy と create の 2 つ、
        delete は destroy。次の規則で「先に終わっていなければならない操作」を決める:
        規則1: a が b に依存する（config）なら、a の create/update は b の create/update の後
        規則2: a が b に依存していた（state の "deps"）なら、b の destroy は a の destroy の後
        規則3: replace は、CBD でなければ destroy → create、CBD なら create → destroy
        規則4: a が b に依存していて（state の "deps"）、a が update され、b が delete または CBD の replace
               なら、b の destroy は a の update の後（参照を付け替えてから消す）
        同時に実行できる操作が複数あれば、destroy を優先し、次にアドレス順:
        key = (0 if destroy else 1, アドレス, 操作名)
    循環があれば CycleError（topo_sort がそのまま送出する）。

    例: VPC の cidr_block（置き換えが必要な属性）を変えると、
        steps = [destroy instance, destroy sg, destroy subnet, destroy vpc,
                 create vpc, create sg, create subnet, create instance]

    ヒント: (1) で参照先の action を見るには、それまでに作った changes を参照する lookup を作る。
    """
    raise NotImplementedError("演習4: plan を実装してください")


# ===========================================================================
# 演習5（★★☆）: apply と refresh
# ===========================================================================

def apply(plan: Plan, config: Config, state: State, cloud: FakeCloud) -> None:
    """plan.steps を順に cloud へ実行し、state をその場で（1 操作ごとに）更新する。

    - ("create", a): attrs を resolve（参照先の id は state から取る）して cloud.create(種別, attrs)。
      state[a] = {"id": 新しい id, "attrs": 解決済みの attrs, "deps": sorted(依存先)}。
      すでに state[a] がある（CBD の置き換え）なら、古い id を新しいエントリの "deposed" に退避する。
    - ("update", a): 同様に resolve して cloud.update(state[a]["id"], attrs)。state の attrs と deps を更新。
    - ("destroy", a): state[a] に "deposed" があればその id を cloud.delete して "deposed" を消す。
      なければ state[a]["id"] を cloud.delete して state から a を消す。
    - 最後に、config にあるすべてのリソースについて state の "deps" を最新の依存関係に更新する。
    - cloud が CloudError を送出したらそのまま伝える。失敗した操作は state に反映しない
      （それまでに成功した操作の結果は state に残る。apply はトランザクションではない）。
    """
    raise NotImplementedError("演習5: apply を実装してください")


def refresh(state: State, cloud: FakeCloud) -> dict[str, list[str]]:
    """実際のクラウドの状態を読み、state との差（ドリフト）を検出して state を現実に合わせる。

    - cloud.read(id) が None（管理外で削除された）なら、そのアドレスを state から消し、
      結果に {アドレス: ["(deleted)"]} を入れる。
    - 属性が異なれば、異なる属性名（どちらか片方にしかないものも含む）の昇順リストを結果に入れ、
      state の attrs をクラウドの値で置き換える。
    - 差がないリソースは結果に含めない。

    refresh の後に plan すると、「設定に戻すための差分」が出る（コンソールでの手作業の変更が
    次の apply で元に戻されるのはこのため）。
    """
    raise NotImplementedError("演習5: refresh を実装してください")
