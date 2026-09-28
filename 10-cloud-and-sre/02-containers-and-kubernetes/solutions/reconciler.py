"""10.2 コンテナオーケストレーションとKubernetes — 演習（ミニ Deployment コントローラ）の解答例

演習の仕様は exercises/reconciler.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Mapping

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================


@dataclass
class Pod:
    name: str
    revision: int            # どのテンプレート（リビジョン）から作られたか
    created_at: int
    ready_at: int | None     # この時刻以降 Ready。None なら永遠に Ready にならない（壊れたイメージなど）

    def is_ready(self, now: int) -> bool:
        return self.ready_at is not None and now >= self.ready_at


class Cluster:
    """Pod の作成・削除と Ready 判定だけを模した架空のクラスタ（そのまま使ってください）。

    startup[revision] は、そのリビジョンの Pod が作成されてから Ready になるまでの時間。
    None ならその Pod は Ready にならない（CrashLoopBackOff や readiness probe の失敗を模す）。
    指定のないリビジョンは 1。
    """

    def __init__(self, startup: Mapping[int, int | None] | None = None) -> None:
        self.startup = dict(startup or {})
        self.pods: dict[str, Pod] = {}
        self.events: list[str] = []
        self._seq = 0

    def create_pod(self, revision: int, now: int) -> Pod:
        self._seq += 1
        delay = self.startup.get(revision, 1)
        pod = Pod(f"web-r{revision}-{self._seq:03d}", revision, now, None if delay is None else now + delay)
        self.pods[pod.name] = pod
        self.events.append(f"t={now} create {pod.name}")
        return pod

    def delete_pod(self, name: str, now: int = -1) -> None:
        del self.pods[name]
        self.events.append(f"t={now} delete {name}")

    def pods_of(self, revision: int) -> list[Pod]:
        return sorted((p for p in self.pods.values() if p.revision == revision), key=lambda p: p.name)

    def ready_count(self, now: int, revision: int | None = None) -> int:
        return sum(
            1 for p in self.pods.values()
            if p.is_ready(now) and (revision is None or p.revision == revision)
        )


# ===========================================================================
# 演習4: maxSurge / maxUnavailable の解決
# ===========================================================================

_PERCENT_RE = re.compile(r"(\d+)%")


def _scaled(value: int | str, replicas: int, round_up: bool) -> int:
    if isinstance(value, bool):
        raise ValueError(f"整数か \"25%\" の形の文字列で指定してください: {value!r}")
    if isinstance(value, int):
        if value < 0:
            raise ValueError(f"負の値は指定できません: {value}")
        return value
    m = _PERCENT_RE.fullmatch(value) if isinstance(value, str) else None
    if m is None:
        raise ValueError(f"整数か \"25%\" の形の文字列で指定してください: {value!r}")
    num = int(m.group(1)) * replicas
    # 整数演算で切り上げ・切り捨て（浮動小数点の誤差を避ける）
    return -(-num // 100) if round_up else num // 100


def resolve_fenceposts(max_surge: int | str, max_unavailable: int | str, replicas: int) -> tuple[int, int]:
    if replicas < 0:
        raise ValueError(f"replicas は 0 以上: {replicas}")
    surge = _scaled(max_surge, replicas, round_up=True)
    unavailable = _scaled(max_unavailable, replicas, round_up=False)
    if surge == 0 and unavailable == 0:
        # 両方 0 では 1 つも入れ替えられない。切り捨てで 0 になった場合に備えて 1 にする
        unavailable = 1
    return surge, unavailable


# ===========================================================================
# 演習5: ReplicaSet の突き合わせ
# ===========================================================================

def deletion_order(pods: list[Pod], now: int) -> list[Pod]:
    def key(p: Pod) -> tuple[int, ...]:
        if p.is_ready(now):
            # Ready な Pod は、Ready になってからの時間が短いもの（新しいもの）から消す
            return (1, -p.ready_at, -p.created_at)  # type: ignore[operator]
        # Ready でない Pod を最優先で消す（消しても可用性が下がらない）。その中では新しく作られたものから
        return (0, -p.created_at)

    # sorted は安定なので、先に名前の降順に並べておけば、同順位は名前の降順（連番の新しいもの）になる
    return sorted(sorted(pods, key=lambda p: p.name, reverse=True), key=key)


def sync_replicaset(cluster: Cluster, revision: int, desired: int, now: int) -> tuple[int, list[str]]:
    if desired < 0:
        raise ValueError(f"desired は 0 以上: {desired}")
    pods = cluster.pods_of(revision)
    diff = desired - len(pods)
    if diff > 0:
        for _ in range(diff):
            cluster.create_pod(revision, now)
        return diff, []
    victims = [p.name for p in deletion_order(pods, now)[: -diff]] if diff < 0 else []
    for name in victims:
        cluster.delete_pod(name, now)
    return 0, victims


# ===========================================================================
# 演習6: Deployment のローリングアップデート
# ===========================================================================


class Deployment:
    def __init__(
        self,
        cluster: Cluster,
        replicas: int,
        *,
        max_surge: int | str = "25%",
        max_unavailable: int | str = "25%",
        revision: int = 1,
        progress_deadline: int = 10,
    ) -> None:
        self.cluster = cluster
        self.replicas = replicas
        self.max_surge = max_surge
        self.max_unavailable = max_unavailable
        self.revision = revision
        self.progress_deadline = progress_deadline
        self.replica_sets: dict[int, int] = {}  # リビジョン → その ReplicaSet の spec.replicas
        self._last_progress = 0
        self._last_signature: tuple | None = None
        resolve_fenceposts(max_surge, max_unavailable, replicas)  # 設定の検証

    def rollout(self, revision: int, now: int) -> None:
        self.revision = revision
        self._last_progress = now

    def reconcile(self, now: int) -> None:
        surge, unavailable = resolve_fenceposts(self.max_surge, self.max_unavailable, self.replicas)
        rs = self.replica_sets
        new = self.revision
        rs.setdefault(new, 0)
        olds = sorted(r for r in rs if r != new and rs[r] > 0)  # 古いリビジョンから

        # (A) 新しい ReplicaSet を増やす: 全体の合計が replicas + surge を超えない範囲で
        if rs[new] > self.replicas:
            rs[new] = self.replicas
        elif rs[new] < self.replicas:
            room = self.replicas + surge - sum(rs.values())
            rs[new] += max(0, min(room, self.replicas - rs[new]))

        # (B) 古い ReplicaSet を減らす: Ready な Pod が replicas - unavailable を下回らない範囲で
        min_available = self.replicas - unavailable
        new_unavailable = rs[new] - self.cluster.ready_count(now, new)
        max_scaled_down = sum(rs.values()) - min_available - new_unavailable
        if olds and max_scaled_down > 0:
            # (B-1) Ready でない古い Pod は、消しても可用性が下がらないので先に片付ける
            cleaned = 0
            for r in olds:
                unhealthy = rs[r] - self.cluster.ready_count(now, r)
                k = max(0, min(unhealthy, max_scaled_down - cleaned))
                rs[r] -= k
                cleaned += k
            # (B-2) Ready な Pod を、最低可用数を守れる分だけ減らす
            budget = self.cluster.ready_count(now) - min_available
            for r in olds:
                if budget <= 0:
                    break
                k = min(rs[r], budget)
                rs[r] -= k
                budget -= k

        # (C) 各 ReplicaSet の Pod 数を spec に合わせる（ReplicaSet コントローラの仕事）
        for r in sorted(rs):
            sync_replicaset(self.cluster, r, rs[r], now)

        # 進捗の記録: ReplicaSet の数や新しい Pod の Ready 数が変わったら「進んだ」
        signature = (tuple(sorted(rs.items())), self.cluster.ready_count(now, new))
        if signature != self._last_signature:
            self._last_signature = signature
            self._last_progress = now

    def status(self, now: int) -> str:
        new = self.revision
        others = [p for p in self.cluster.pods.values() if p.revision != new]
        if (
            self.replica_sets.get(new) == self.replicas
            and not others
            and len(self.cluster.pods_of(new)) == self.replicas
            and self.cluster.ready_count(now, new) == self.replicas
        ):
            return "complete"
        if now - self._last_progress > self.progress_deadline:
            return "stalled"
        return "progressing"
