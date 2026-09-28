"""10.2 コンテナオーケストレーションとKubernetes — 演習: ミニ Deployment コントローラ

Kubernetes のコントローラは「あるべき状態」と「観測した状態」を比べ、差を埋める操作を
何度でも繰り返す（調整ループ）ことでシステムを収束させます。ここでは ReplicaSet と
Deployment のコントローラを小さく作り、ローリングアップデートがなぜ安全なのかを確かめます。

- 演習4（★☆☆）: resolve_fenceposts — maxSurge / maxUnavailable を Pod 数に換算する
- 演習5（★★☆）: deletion_order, sync_replicaset — ReplicaSet の突き合わせ（どの Pod から消すか）
- 演習6（★★★）: Deployment.reconcile / status — ローリングアップデートと進捗の判定
（演習1〜3 は kube_scheduler.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.2

時間のモデル:
    時刻は整数。テストは t = 0, 1, 2, ... の順に reconcile(t) を呼ぶ。Pod は作成された時刻から
    Cluster.startup[リビジョン] 後に Ready になる（None なら永遠に Ready にならない）。
    削除は即座に完了する（本物では終了処理に時間がかかる）。

簡略化している点: 本物の Deployment コントローラ（kubernetes/pkg/controller/deployment）の
アルゴリズムを参考にしていますが、minReadySeconds・rollout 中のスケール・一時停止・
revisionHistoryLimit などは扱いません。
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
# 演習4（★☆☆）: maxSurge / maxUnavailable の解決
# ===========================================================================

def resolve_fenceposts(max_surge: int | str, max_unavailable: int | str, replicas: int) -> tuple[int, int]:
    """(surge, unavailable) の Pod 数を返す。

    - 整数ならそのまま。"25%" のような文字列なら replicas に対する割合。
      **maxSurge は切り上げ、maxUnavailable は切り捨て**（Kubernetes と同じ）。
    - 両方が 0 になった場合は unavailable を 1 にする（1 つも入れ替えられなくなるため）。
    - 負の値、"25"（% なし）、"x%"、小数、真偽値、負の replicas は ValueError。

    >>> resolve_fenceposts("25%", "25%", 10)
    (3, 2)

    ヒント: 浮動小数点数を使わず、整数の除算で切り上げ（-(-a // b)）と切り捨て（a // b）を計算する。
    """
    raise NotImplementedError("演習4: resolve_fenceposts を実装してください")


# ===========================================================================
# 演習5（★★☆）: ReplicaSet の突き合わせ
# ===========================================================================

def deletion_order(pods: list[Pod], now: int) -> list[Pod]:
    """スケールダウンのとき、先に削除すべき順に pods を並べた新しいリストを返す。

    1. Ready でない Pod を先に（消しても可用性が下がらない）。その中では created_at の新しいものから。
    2. 次に Ready な Pod。Ready になった時刻（ready_at）が新しいものから、同じなら created_at の新しいものから。
    3. それでも同じなら、名前の降順（この演習の Pod 名は連番なので、新しいものから）。

    ヒント: sorted は安定ソート。先に名前の降順で並べてから主キーで並べると 3. を満たせる。
    """
    raise NotImplementedError("演習5: deletion_order を実装してください")


def sync_replicaset(cluster: Cluster, revision: int, desired: int, now: int) -> tuple[int, list[str]]:
    """revision の Pod 数を desired に合わせる（ReplicaSet コントローラの 1 回分の仕事）。

    - 足りなければ cluster.create_pod(revision, now) で不足分を作り、(作った数, []) を返す。
    - 多すぎれば deletion_order の先頭から余分な数だけ cluster.delete_pod(名前, now) で消し、
      (0, 消した Pod 名のリスト（消した順）) を返す。
    - ちょうどなら (0, [])。他のリビジョンの Pod には触らない。desired が負なら ValueError。
    """
    raise NotImplementedError("演習5: sync_replicaset を実装してください")


# ===========================================================================
# 演習6（★★★）: Deployment のローリングアップデート
# ===========================================================================


class Deployment:
    """Deployment コントローラ。replica_sets に「リビジョン → その ReplicaSet の目標 Pod 数」を持つ。

    属性:
    - replicas: 目標の Pod 数（テストが途中で書き換えてスケールさせることがある）
    - revision: 現在のテンプレートのリビジョン（新しい ReplicaSet）
    - replica_sets: dict[int, int]。一度作った ReplicaSet は 0 になっても残す（ロールバックで再利用する）
    """

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
        self.replica_sets: dict[int, int] = {}
        self._last_progress = 0
        self._last_signature: tuple | None = None
        # ヒント: 設定の検証のために、ここで resolve_fenceposts を 1 回呼んでおくとよい

    def rollout(self, revision: int, now: int) -> None:
        """テンプレートを revision に変更する（kubectl set image / rollout undo に相当）。

        revision を切り替え、「最後に進捗した時刻」を now にする。ReplicaSet の数の変更は reconcile で行う。
        """
        raise NotImplementedError("演習6: Deployment.rollout を実装してください")

    def reconcile(self, now: int) -> None:
        """調整ループの 1 回分。次の (A)(B)(C) をこの順に行う。

        surge, unavailable = resolve_fenceposts(max_surge, max_unavailable, replicas)
        rs = replica_sets、new = 現在の revision（rs になければ 0 で追加）、
        olds = new 以外で目標数が 1 以上のリビジョン（小さい順 = 古い順）

        (A) 新しい ReplicaSet を増やす
            - rs[new] > replicas なら rs[new] = replicas（スケールダウン）
            - rs[new] < replicas なら、room = replicas + surge - sum(rs の全目標数) として
              rs[new] += max(0, min(room, replicas - rs[new]))
        (B) 古い ReplicaSet を減らす
            min_available = replicas - unavailable
            new_unavailable = rs[new] - (new の Ready な Pod 数)
            max_scaled_down = sum(rs の全目標数) - min_available - new_unavailable
            olds が空でなく max_scaled_down > 0 のときだけ:
            (B-1) 古い順に、各 r について unhealthy = rs[r] - (r の Ready な Pod 数) として、
                  合計が max_scaled_down を超えない範囲で rs[r] を unhealthy だけ減らす
                  （Ready でない Pod は消しても可用性が下がらない。これがないと壊れた旧 Pod が居座る）
            (B-2) budget = (全リビジョンの Ready な Pod 数) - min_available として、
                  古い順に rs[r] を min(rs[r], 残りの budget) ずつ減らす
        (C) すべての ReplicaSet について（リビジョンの小さい順に）sync_replicaset で Pod 数を目標に合わせる

        最後に進捗を記録する: (rs の内容, new の Ready な Pod 数) が前回の reconcile から変わっていたら、
        「最後に進捗した時刻」を now にする。

        この手順により、rollout 中も常に
            Pod の総数 <= replicas + surge、Ready な Pod 数 >= replicas - unavailable
        が保たれる（なぜそうなるか、テストが通ったら説明できるようにしよう）。
        """
        raise NotImplementedError("演習6: Deployment.reconcile を実装してください")

    def status(self, now: int) -> str:
        """"complete" / "progressing" / "stalled" のいずれかを返す。

        - "complete": rs[revision] == replicas、revision 以外の Pod が 1 つもなく、
          revision の Pod が replicas 個あり、すべて Ready
        - "stalled": complete でなく、now - (最後に進捗した時刻) > progress_deadline
          （Kubernetes の ProgressDeadlineExceeded。自動でロールバックはしない）
        - それ以外は "progressing"
        """
        raise NotImplementedError("演習6: Deployment.status を実装してください")
