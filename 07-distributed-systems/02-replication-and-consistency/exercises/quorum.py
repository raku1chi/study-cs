"""7.2 レプリケーションと一貫性 — 演習: Dynamo 風のクォーラム読み書き

リーダーを置かないレプリケーション（Amazon の Dynamo の論文に由来し、Cassandra などが採用）では、
クライアント（またはコーディネーター）が N 台のレプリカに書き込み、W 台から ACK が返れば成功、
読み取りは R 台に問い合わせて最もバージョンの新しい値を採用します。
W + R > N なら書き込んだ集合と読む集合が必ず重なるので、最新の書き込みが読める——というのが
クォーラムの考え方です。この演習では、その仕組みと、W + R <= N のときに古いデータが読めてしまう
ことを、乱数で「どのレプリカが応答したか」を模擬しながら確かめます。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.2
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_quorum

簡略化している点（本文 5 節で現実との違いを説明しています）:
    - バージョンは QuorumCluster が 1 から順に振る通し番号（単一のコーディネーターが時刻を持つ想定）。
      現実の Dynamo 系ではバージョンベクトルやタイムスタンプを使い、並行な書き込み（競合）が起こりうる。
    - put は「最初に ACK を返した W 台」にだけ書き込み、残りのレプリカには届かないものとする。
      現実には残りにも遅れて届くことが多く、失敗した書き込みが一部のレプリカに残ることもある。
    - 停止したレプリカはデータを失わず、古いデータを持ったまま復帰する。
"""
from __future__ import annotations

import random  # noqa: F401  QuorumCluster.rng = random.Random(seed) に使います
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Versioned:
    """バージョン付きの値。version が大きいほど新しい。"""

    value: Any
    version: int


class QuorumError(Exception):
    """稼働中のレプリカが W（または R）台に満たず、操作を完了できない。"""


# ---------------------------------------------------------------------------
# 演習2（★★★）: クォーラム読み書き・リードリペア・アンチエントロピー
# ---------------------------------------------------------------------------


class Replica:
    """1 台のレプリカ。

    属性: name（名前）, up（稼働中なら True。初期値 True）, store（key → Versioned の dict）

    - write(key, item): 手元に key がないか、item.version が手元のバージョンより **大きい** ときだけ
      保存して True を返す。そうでなければ何もせず False（古い書き込みが遅れて届いても巻き戻らない）。
    - read(key): 手元の Versioned を返す。なければ None。
    """

    def __init__(self, name: str) -> None:
        raise NotImplementedError("演習2: Replica.__init__ を実装してください")

    def write(self, key: str, item: Versioned) -> bool:
        raise NotImplementedError("演習2: Replica.write を実装してください")

    def read(self, key: str) -> Versioned | None:
        raise NotImplementedError("演習2: Replica.read を実装してください")


class QuorumCluster:
    """N 台のレプリカに対するクォーラム読み書き。

    属性:
        n, w, r: パラメータ（n >= 1、1 <= w <= n、1 <= r <= n。満たさなければ ValueError）
        replicas: Replica のリスト（名前は "r0", "r1", …）
        rng: random.Random(seed)。**どのレプリカを選ぶかは必ずこの乱数で決める**
        read_repairs: リードリペアで書き直した回数（初期値 0）

    is_strict_quorum（プロパティ）: w + r > n なら True。

    fail(i) / recover(i): i 番のレプリカを停止 / 復帰させる（復帰時のデータは停止前のまま）。

    put(key, value) -> int:
        1. 稼働中のレプリカが w 台未満なら QuorumError（バージョンも消費しない）。
        2. バージョンを 1 増やし（最初の put は 1）、Versioned(value, version) を作る。
        3. 稼働中のレプリカから rng.sample で **ちょうど w 台** を選んで書き込む。
        4. バージョンを返す。

    get(key) -> Versioned | None:
        1. 稼働中のレプリカが r 台未満なら QuorumError。
        2. 稼働中のレプリカから rng.sample で r 台を選んで読む。
        3. どれも持っていなければ None。持っていれば、最もバージョンの大きい Versioned を返す。
        4. **リードリペア**: 選んだ r 台のうち、その最新版を持っていない（古い・持っていない）レプリカに
           最新版を書き込み、1 台ごとに read_repairs を 1 増やす。

    anti_entropy() -> int:
        稼働中のレプリカどうしで全キーを突き合わせ、各キーの最新版を、それを持っていない稼働中の
        レプリカすべてに書き込む（バックグラウンドの同期の模擬）。書き込んだ (レプリカ, キー) の数を返す。
        停止中のレプリカは対象外。

    ヒント: rng.sample(稼働中のインデックスのリスト, k) で k 台を重複なく選べる。
    """

    def __init__(self, n: int = 3, w: int = 2, r: int = 2, seed: int = 0) -> None:
        raise NotImplementedError("演習2: QuorumCluster.__init__ を実装してください")

    @property
    def is_strict_quorum(self) -> bool:
        raise NotImplementedError("演習2: QuorumCluster.is_strict_quorum を実装してください")

    def fail(self, i: int) -> None:
        raise NotImplementedError("演習2: QuorumCluster.fail を実装してください")

    def recover(self, i: int) -> None:
        raise NotImplementedError("演習2: QuorumCluster.recover を実装してください")

    def put(self, key: str, value: Any) -> int:
        raise NotImplementedError("演習2: QuorumCluster.put を実装してください")

    def get(self, key: str) -> Versioned | None:
        raise NotImplementedError("演習2: QuorumCluster.get を実装してください")

    def anti_entropy(self) -> int:
        raise NotImplementedError("演習2: QuorumCluster.anti_entropy を実装してください")
