"""7.4 合意と協調 — 演習: リースとフェンシングトークン

分散ロックは、多くの場合「期限付きのロック」＝ **リース**（lease）として実装されます。保持者が落ちても、
期限が来れば自動的に解放されるからです。しかし、保持者が落ちたのではなく **一時停止していただけ**
（GC の世界の停止、VM の一時停止など）だと、目を覚ました保持者は、自分のリースが失効していることに気づかずに
書き込みます。そのとき、すでに別のクライアントがロックを取って書き込んでいれば、データが壊れます。

対策が **フェンシングトークン**（fencing token）です。ロックを取るたびに単調増加する番号を払い出し、
書き込み先のストレージが「これまでに見た最大の番号より小さい番号の書き込み」を拒否します。
この演習では、リース付きのロックサービスと、トークンを検査するストレージを実装し、
一時停止したクライアントのシナリオで効果を確かめます（Martin Kleppmann の記事 "How to do distributed locking", 2016 の例）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.4
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_fencing

時計は clock 引数で注入します（ミリ秒の整数を返す関数）。テストでは偽の時計で時間を進めます。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class StaleTokenError(Exception):
    """古いフェンシングトークンによる書き込みが拒否された。"""


@dataclass
class Lease:
    holder: str
    token: int
    expires_at: int  # この時刻（ミリ秒）以降は無効


# ---------------------------------------------------------------------------
# 演習6（★★☆）: リース付きのロックサービスと、トークンを検査するストレージ
# ---------------------------------------------------------------------------


class LockService:
    """名前付きのロックを、期限付きのリースとして貸し出すサービス（etcd や ZooKeeper の役割の模擬）。

    - リースは、clock() が expires_at **以上** になった瞬間に失効する（expires_at = 取得・延長した時刻 + lease_ms）。
    - トークンは、新しくリースを発行するたびに、**全ロック共通** で 1 から 1 ずつ増える（決して再利用しない）。

    acquire(name, client_id) -> int | None:
        - 有効なリースがなければ（未取得・失効・解放済み）、新しいトークンでリースを発行してそのトークンを返す。
        - 有効なリースを client_id 自身が持っていれば、期限を延長して **同じトークン** を返す。
        - 他のクライアントが有効なリースを持っていれば None。
    renew(name, client_id, token) -> bool:
        有効なリースの保持者とトークンが一致すれば期限を延長して True。失効していたら False（延長できない）。
    release(name, client_id, token) -> bool:
        有効なリースの保持者とトークンが一致すれば解放して True。それ以外は False。
    holder(name) -> (client_id, token) | None: 有効なリースの保持者とトークン。
    lease_ms <= 0 なら ValueError。
    """

    def __init__(self, lease_ms: int, clock: Callable[[], int]) -> None:
        raise NotImplementedError("演習6: LockService.__init__ を実装してください")

    def acquire(self, name: str, client_id: str) -> int | None:
        raise NotImplementedError("演習6: LockService.acquire を実装してください")

    def renew(self, name: str, client_id: str, token: int) -> bool:
        raise NotImplementedError("演習6: LockService.renew を実装してください")

    def release(self, name: str, client_id: str, token: int) -> bool:
        raise NotImplementedError("演習6: LockService.release を実装してください")

    def holder(self, name: str) -> tuple[str, int] | None:
        raise NotImplementedError("演習6: LockService.holder を実装してください")


class FencedStorage:
    """フェンシングトークンを検査するストレージ。

    - write(key, value, token): key についてこれまでに受け付けた最大のトークンより token が **小さければ**
      StaleTokenError を送出し、何も書かない。等しいか大きければ書き込み、最大トークンを更新する。
      （同じ保持者が同じトークンで何度書いてもよい。トークンの検査はキーごと）
    - read(key): 値（なければ None）。
    - data 属性に key → value の dict を持つこと。

    ポイント: 安全性を守っているのはロックサービスではなく、**書き込みを受け付ける側の検査** です。
    """

    def __init__(self) -> None:
        raise NotImplementedError("演習6: FencedStorage.__init__ を実装してください")

    def write(self, key: str, value: Any, token: int) -> None:
        raise NotImplementedError("演習6: FencedStorage.write を実装してください")

    def read(self, key: str) -> Any:
        raise NotImplementedError("演習6: FencedStorage.read を実装してください")


class UnfencedStorage:
    """悪い例（実装済み）: トークンを検査しないストレージ。テストで比較に使います。"""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def write(self, key: str, value: Any, token: int | None = None) -> None:
        self.data[key] = value

    def read(self, key: str) -> Any:
        return self.data.get(key)
