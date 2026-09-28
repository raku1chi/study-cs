"""10.2 コンテナオーケストレーションとKubernetes — 演習（ミニ・スケジューラ）の解答例

演習の仕様は exercises/kube_scheduler.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

EFFECTS = ("NoSchedule", "PreferNoSchedule", "NoExecute")
STRATEGIES = ("LeastAllocated", "MostAllocated", "BalancedAllocation")
PREFER_NO_SCHEDULE_PENALTY = 50


@dataclass(frozen=True)
class Taint:
    key: str
    value: str = ""
    effect: str = "NoSchedule"


@dataclass(frozen=True)
class Toleration:
    key: str = ""
    operator: str = "Equal"  # "Equal" または "Exists"
    value: str = ""
    effect: str = ""         # "" はすべての effect にマッチ


@dataclass
class PodSpec:
    name: str
    cpu: str = "0"           # requests（Kubernetes の数量表記）
    memory: str = "0"
    node_selector: dict[str, str] = field(default_factory=dict)
    tolerations: list[Toleration] = field(default_factory=list)
    priority: int = 0


@dataclass
class Node:
    name: str
    cpu: str                 # allocatable（Pod に割り当て可能な量）
    memory: str
    labels: dict[str, str] = field(default_factory=dict)
    taints: list[Taint] = field(default_factory=list)
    pods: list[PodSpec] = field(default_factory=list)


@dataclass(frozen=True)
class ScheduleResult:
    node: str | None         # 割り当てたノード名。割り当てられなければ None（Pending）
    message: str


def unschedulable_message(total_nodes: int, reasons: Counter) -> str:
    """kube-scheduler のイベントメッセージを模した文字列を作る。"""
    parts = ", ".join(f"{count} {reason}" for reason, count in sorted(reasons.items()))
    return f"0/{total_nodes} nodes are available: {parts}."


# ===========================================================================
# 演習1: リソース量の解析
# ===========================================================================

_NUMBER = r"(\d+(?:\.\d*)?|\.\d+)"
_CPU_RE = re.compile(_NUMBER + r"(m?)")
_MEM_RE = re.compile(_NUMBER + r"(Ki|Mi|Gi|Ti|Pi|Ei|k|M|G|T|P|E|m)?")
_MEM_UNITS = {
    None: 1,
    "k": 10**3, "M": 10**6, "G": 10**9, "T": 10**12, "P": 10**15, "E": 10**18,
    "Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40, "Pi": 2**50, "Ei": 2**60,
}


def parse_cpu(quantity: str) -> int:
    m = _CPU_RE.fullmatch(quantity.strip()) if isinstance(quantity, str) else None
    if m is None:
        raise ValueError(f"CPU の量として解釈できません: {quantity!r}")
    # 浮動小数点数ではなく Fraction で計算する（"0.1" * 1000 を誤差なく 100 にするため）
    value = Fraction(m.group(1))
    millis = value if m.group(2) == "m" else value * 1000
    if millis.denominator != 1:
        raise ValueError(f"CPU は 1m（0.001 コア）より細かく指定できません: {quantity!r}")
    return int(millis)


def parse_memory(quantity: str) -> int:
    m = _MEM_RE.fullmatch(quantity.strip()) if isinstance(quantity, str) else None
    if m is None:
        raise ValueError(f"メモリの量として解釈できません: {quantity!r}")
    if m.group(2) == "m":
        # 本物の Kubernetes は「ミリバイト」として受け付けてしまう。書き間違いとして拒否する
        raise ValueError(f"{quantity!r} は 0.001 バイト単位の指定です。Mi（メビバイト）や M（メガバイト）の書き間違いでは？")
    value = Fraction(m.group(1)) * _MEM_UNITS[m.group(2)]
    return math.ceil(value)  # バイト未満は切り上げ


# ===========================================================================
# 演習2: フィルタ・スコア・バインド
# ===========================================================================

def tolerates(tolerations: list[Toleration], taint: Taint) -> bool:
    for t in tolerations:
        if t.effect and t.effect != taint.effect:
            continue
        if t.operator == "Exists":
            if t.key == "" or t.key == taint.key:  # キーなしの Exists はすべてを許容する
                return True
        elif t.operator == "Equal":
            if t.key == taint.key and t.value == taint.value:
                return True
        else:
            raise ValueError(f"operator は Equal か Exists です: {t.operator!r}")
    return False


def _used(node: Node) -> tuple[int, int]:
    return (sum(parse_cpu(p.cpu) for p in node.pods), sum(parse_memory(p.memory) for p in node.pods))


def filter_node(pod: PodSpec, node: Node) -> list[str]:
    # kube-scheduler と同じく、失敗したプラグインの理由で止める（taint → selector → リソース）
    for taint in node.taints:
        if taint.effect in ("NoSchedule", "NoExecute") and not tolerates(pod.tolerations, taint):
            return [f"node(s) had untolerated taint {{{taint.key}: {taint.value}}}"]
    if any(node.labels.get(k) != v for k, v in pod.node_selector.items()):
        return ["node(s) didn't match Pod's node affinity/selector"]
    used_cpu, used_mem = _used(node)
    reasons = []
    # requests（予約量）の合計で判定する。実際の使用量ではない
    if used_cpu + parse_cpu(pod.cpu) > parse_cpu(node.cpu):
        reasons.append("Insufficient cpu")
    if used_mem + parse_memory(pod.memory) > parse_memory(node.memory):
        reasons.append("Insufficient memory")
    return reasons


def score_node(pod: PodSpec, node: Node, strategy: str = "LeastAllocated") -> int:
    if strategy not in STRATEGIES:
        raise ValueError(f"未知の戦略です: {strategy!r}")
    used_cpu, used_mem = _used(node)
    cpu = Fraction(used_cpu + parse_cpu(pod.cpu), parse_cpu(node.cpu))
    mem = Fraction(used_mem + parse_memory(pod.memory), parse_memory(node.memory))
    if strategy == "LeastAllocated":      # 空きが多いほど高い → 分散配置
        score = ((1 - cpu) + (1 - mem)) / 2 * 100
    elif strategy == "MostAllocated":     # 詰まっているほど高い → ビンパッキング
        score = (cpu + mem) / 2 * 100
    else:                                 # CPU とメモリの使用率が揃っているほど高い
        score = (1 - abs(cpu - mem) / 2) * 100
    return math.floor(score)


def schedule(pod: PodSpec, nodes: list[Node], strategy: str = "LeastAllocated") -> ScheduleResult:
    reasons: Counter = Counter()
    best: tuple[int, str] | None = None
    best_node: Node | None = None
    for node in nodes:
        failed = filter_node(pod, node)
        if failed:
            reasons.update(failed)
            continue
        soft = sum(
            1 for t in node.taints
            if t.effect == "PreferNoSchedule" and not tolerates(pod.tolerations, t)
        )
        total = score_node(pod, node, strategy) - PREFER_NO_SCHEDULE_PENALTY * soft
        # 最高点を選ぶ。同点ならノード名の昇順（(−点, 名前) が最小のもの）
        key = (-total, node.name)
        if best is None or key < best:
            best, best_node = key, node
    if best_node is None:
        return ScheduleResult(None, unschedulable_message(len(nodes), reasons))
    best_node.pods.append(pod)  # バインド
    return ScheduleResult(best_node.name, f"Successfully assigned {pod.name} to {best_node.name}")


# ===========================================================================
# 演習3: プリエンプション
# ===========================================================================

def _fits(pod: PodSpec, node: Node, remaining: list[PodSpec]) -> bool:
    cpu = sum(parse_cpu(p.cpu) for p in remaining) + parse_cpu(pod.cpu)
    mem = sum(parse_memory(p.memory) for p in remaining) + parse_memory(pod.memory)
    return cpu <= parse_cpu(node.cpu) and mem <= parse_memory(node.memory)


def preempt(pod: PodSpec, nodes: list[Node]) -> tuple[str, list[str]] | None:
    candidates = []
    for node in nodes:
        reasons = filter_node(pod, node)
        # リソース不足だけが理由のノードでなければ、誰を追い出しても置けない
        if not reasons or any(not r.startswith("Insufficient") for r in reasons):
            continue
        lower = [p for p in node.pods if p.priority < pod.priority]
        keep = [p for p in node.pods if p.priority >= pod.priority]
        # (1) 優先度の低い Pod を全部どけても入らないなら、このノードは候補外
        if not _fits(pod, node, keep):
            continue
        # (2) 優先度の高いものから順に「戻せるなら戻す」（恩赦）。戻せなかったものが犠牲になる
        victims = []
        for p in sorted(lower, key=lambda p: (-p.priority, p.name)):
            if _fits(pod, node, keep + [p]):
                keep.append(p)
            else:
                victims.append(p)
        priorities = [v.priority for v in victims]
        rank = (max(priorities), sum(priorities), len(victims), node.name)
        candidates.append((rank, node, victims))
    if not candidates:
        return None
    _, node, victims = min(candidates, key=lambda c: c[0])
    names = {v.name for v in victims}
    node.pods = [p for p in node.pods if p.name not in names]  # 追い出す（バインドはしない）
    return node.name, sorted(names)
