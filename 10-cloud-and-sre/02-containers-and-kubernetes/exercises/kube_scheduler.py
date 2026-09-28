"""10.2 コンテナオーケストレーションとKubernetes — 演習: ミニ・スケジューラ

kube-scheduler の中核である「フィルタ（置けるノードを絞る）→ スコア（良いノードを選ぶ）→
バインド（割り当てる）」と、優先度によるプリエンプション（追い出し）を小さく実装します。

- 演習1（★☆☆）: parse_cpu, parse_memory — Kubernetes のリソース量の表記を解析する
- 演習2（★★☆）: tolerates, filter_node, score_node, schedule — フィルタ・スコア・バインド
- 演習3（★★★）: preempt — 優先度の低い Pod を最小限追い出して置き場所を作る
（演習4・5 は reconciler.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.2

簡略化している点（本物の kube-scheduler との違い）:
    - 使う資源は CPU とメモリの requests だけ。ノードの使用量は「バインド済み Pod の requests の合計」。
    - nodeAffinity・Pod 間の affinity・トポロジー分散・ボリュームなどのプラグインは扱わない。
    - スコアは 1 つの戦略の点数から、PreferNoSchedule の taint 1 つにつき
      PREFER_NO_SCHEDULE_PENALTY 点を引くだけ（本物は複数プラグインの重み付き和）。
    - プリエンプションで PodDisruptionBudget や猶予期間は考慮しない。
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
# 演習1（★☆☆）: リソース量の解析
# ===========================================================================

def parse_cpu(quantity: str) -> int:
    """CPU の量をミリコア（1 コア = 1000m）の整数に変換する。

    - "250m" → 250、"1" → 1000、"0.5" → 500、".5" → 500、"2.25" → 2250。前後の空白は無視する。
    - 1m より細かい指定（"0.0001"、"1.5m"）は ValueError（Kubernetes も許さない）。
    - 負の数、空文字列、m 以外の接尾辞（"1k" など）、指数表記、数値でないものは ValueError。

    ヒント: 浮動小数点数で 0.1 * 1000 を計算すると誤差が出うる。fractions.Fraction("0.1") を使うと正確。
    """
    raise NotImplementedError("演習1: parse_cpu を実装してください")


def parse_memory(quantity: str) -> int:
    """メモリの量をバイト数の整数に変換する。

    - 接尾辞なしはバイト。10 進の接尾辞 k, M, G, T, P, E（10^3 倍ずつ。小文字の k に注意）と、
      2 進の接尾辞 Ki, Mi, Gi, Ti, Pi, Ei（2^10 倍ずつ）を受け付ける。
    - 小数も可: "1.5Gi" → 1610612736。バイト未満の端数は切り上げる（"0.5" → 1）。
    - 接尾辞 "m"（ミリ）は ValueError にし、メッセージに "Mi" を含めて書き間違いの可能性を伝える。
      （本物の Kubernetes は "400m" を 0.4 バイトとして受け付けてしまう。有名な落とし穴）
    - "1K"（大文字の K）、"1gb"、負の数、指数表記、空文字列などは ValueError。

    >>> parse_memory("128Mi")
    134217728
    >>> parse_memory("1G")
    1000000000
    """
    raise NotImplementedError("演習1: parse_memory を実装してください")


# ===========================================================================
# 演習2（★★☆）: フィルタ・スコア・バインド
# ===========================================================================

def tolerates(tolerations: list[Toleration], taint: Taint) -> bool:
    """tolerations のどれか 1 つが taint を許容すれば True。

    1 つの toleration が taint を許容する条件:
    - toleration.effect が空文字列、または taint.effect と等しい
    - かつ、operator が "Exists" なら key が空文字列（すべてのキーを許容）か taint.key と等しい。
      operator が "Equal" なら key と value の両方が taint と等しい。
    - operator が "Exists" / "Equal" 以外なら ValueError。
    """
    raise NotImplementedError("演習2: tolerates を実装してください")


def filter_node(pod: PodSpec, node: Node) -> list[str]:
    """pod を node に置けない理由のリストを返す。置けるなら空リスト。

    次の順に調べ、失敗した段階の理由だけを返す（kube-scheduler も失敗したプラグインで打ち切る）:
    1. taint: effect が "NoSchedule" か "NoExecute" の taint のうち、許容されないものがあれば
       ["node(s) had untolerated taint {キー: 値}"]（最初に見つかった taint。値が空なら "{キー: }"）
       "PreferNoSchedule" はフィルタでは落とさない（スコアで減点する）。
    2. nodeSelector: pod.node_selector のすべてのキーと値が node.labels に一致しなければ
       ["node(s) didn't match Pod's node affinity/selector"]
    3. リソース: バインド済み Pod の requests の合計 + pod の requests が allocatable を超えるなら、
       超えた資源ごとに "Insufficient cpu" / "Insufficient memory"（この順。両方のこともある）
    """
    raise NotImplementedError("演習2: filter_node を実装してください")


def score_node(pod: PodSpec, node: Node, strategy: str = "LeastAllocated") -> int:
    """pod を node に置いた「後」の使用率から、0〜100 の点数（小数点以下切り捨て）を返す。

    cpu = (バインド済みの CPU requests の合計 + pod の CPU) / ノードの CPU、mem も同様として:
    - "LeastAllocated"（既定）: ((1 - cpu) + (1 - mem)) / 2 × 100 — 空いているノードほど高い（分散配置）
    - "MostAllocated": (cpu + mem) / 2 × 100 — 詰まっているノードほど高い（ビンパッキング）
    - "BalancedAllocation": (1 - |cpu - mem| / 2) × 100 — CPU とメモリの使用率が揃うほど高い
    - それ以外の strategy は ValueError

    注意: 浮動小数点数で計算すると 0.29 × 100 が 28.999... になり、切り捨てで 1 点ずれる。
    fractions.Fraction で計算し、最後に math.floor する。
    """
    raise NotImplementedError("演習2: score_node を実装してください")


def schedule(pod: PodSpec, nodes: list[Node], strategy: str = "LeastAllocated") -> ScheduleResult:
    """pod を 1 つのノードに割り当てる（バインドする）。

    1. すべてのノードに filter_node を適用する。
    2. 置けるノードの点数 = score_node(pod, node, strategy)
                            - PREFER_NO_SCHEDULE_PENALTY × (許容されない PreferNoSchedule の taint の数)
    3. 最高点のノードを選ぶ（同点ならノード名の昇順で最初のもの）。node.pods に pod を追加し、
       ScheduleResult(ノード名, "Successfully assigned {pod.name} to {ノード名}") を返す。
    4. 置けるノードがなければ何も変更せず、
       ScheduleResult(None, unschedulable_message(len(nodes), 理由ごとの件数の Counter)) を返す。
       1 つのノードが複数の理由を持つときは、それぞれ数える。

    例: "0/3 nodes are available: 2 node(s) didn't match Pod's node affinity/selector,
         1 node(s) had untolerated taint {dedicated: gpu}."
    """
    raise NotImplementedError("演習2: schedule を実装してください")


# ===========================================================================
# 演習3（★★★）: プリエンプション
# ===========================================================================

def preempt(pod: PodSpec, nodes: list[Node]) -> tuple[str, list[str]] | None:
    """優先度の低い Pod を追い出して pod の置き場所を作る。作れなければ None（何も変更しない）。

    1. 候補ノード: filter_node の理由が「Insufficient ...」だけのノード（taint や nodeSelector が理由の
       ノードは、誰を追い出しても置けない）。
    2. 各候補ノードで、pod.priority より優先度が「低い」Pod（同じ優先度は対象外）を全部どけても
       pod が入らなければ、そのノードは候補外。
    3. 入るなら、どけた Pod を優先度の高い順（同じなら名前の昇順）に 1 つずつ「戻せるか」試し、
       戻しても pod が入るなら戻す。戻せなかった Pod が犠牲（victim）になる（犠牲を減らすため）。
    4. 候補ノードの中から、(犠牲の優先度の最大値, 犠牲の優先度の合計, 犠牲の数, ノード名) が
       最小のノードを選ぶ（重要な Pod をなるべく追い出さない）。
    5. 選んだノードから犠牲の Pod を取り除き、(ノード名, 犠牲の Pod 名の昇順リスト) を返す。
       pod 自身はバインドしない（本物でも、犠牲の Pod の終了を待ってから改めてスケジュールされる）。
    """
    raise NotImplementedError("演習3: preempt を実装してください")
