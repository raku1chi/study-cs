"""7.2 レプリケーションと一貫性 — 演習: レプリケーションラグとセッション保証

非同期レプリケーションでは、フォロワーはリーダーより少し遅れて同じ状態になります（レプリケーションラグ）。
読み取りをフォロワーに分散すると、「自分が書いたはずのデータが見えない」「さっき見えたデータが消えた」
といった奇妙な現象が起きます。この演習では、ラグのあるリーダー・フォロワー構成を模擬し、
その上で次の 2 つのセッション保証（session guarantees）を、LSN（ログ上の位置）のトークンで実装します。

    - read-your-writes（自分の書き込みを読める）: セッションが書いた内容は、その後の読み取りで必ず見える
    - monotonic reads（単調読み取り）: 一度ある状態を見たら、それより古い状態は見せない

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 7.2
このディレクトリで、この演習だけを実行することもできます:
    python3 -m unittest -v test_session_consistency

用語:
    LSN（log sequence number）: リーダーのログ上の位置。1 回目の書き込みが LSN 1、2 回目が LSN 2 …。
    フォロワーの「適用済み LSN」が n なら、そのフォロワーは LSN 1〜n の書き込みを反映した状態にある。
"""
from __future__ import annotations

from typing import Any

LEADER = "leader"  # read などでノードを指定するとき、リーダーはこの文字列、フォロワーは 0 始まりの番号で表す

# ---------------------------------------------------------------------------
# 演習1（★★☆）: ラグのあるリーダー・フォロワー構成とセッション保証
# ---------------------------------------------------------------------------


class ReplicatedStore:
    """1 台のリーダーと num_followers 台のフォロワーからなる、非同期レプリケーションのキーバリューストア。

    - write(key, value): リーダーのログに追記し、リーダーのデータに反映して、その LSN を返す。
      フォロワーには **自動では反映されない**（レプリケーションラグ）。
    - replicate(follower, up_to=None): フォロワーをログの up_to 番目まで（None ならリーダーの最新まで）
      追いつかせる。ログは必ず先頭から順に適用し、途中を飛ばさない。
        * up_to がリーダーの LSN を超える場合は、リーダーの LSN までにとどめる
        * up_to が現在の適用済み LSN より小さい場合は何もしない（フォロワーは過去に戻らない）
        * up_to < 0 なら ValueError
    - applied_lsn(node): そのノードの適用済み LSN（リーダーなら leader_lsn）。
    - read(node, key): そのノードの状態での key の値。なければ None。
    - フォロワー番号が範囲外なら IndexError。num_followers < 1 なら ValueError。

    >>> store = ReplicatedStore(num_followers=2)
    >>> store.write("x", 1)
    1
    >>> store.read(LEADER, "x"), store.read(0, "x")
    (1, None)
    >>> store.replicate(0); store.read(0, "x")
    1
    """

    def __init__(self, num_followers: int = 2) -> None:
        raise NotImplementedError("演習1: ReplicatedStore.__init__ を実装してください")

    @property
    def num_followers(self) -> int:
        raise NotImplementedError("演習1: ReplicatedStore.num_followers を実装してください")

    @property
    def leader_lsn(self) -> int:
        """リーダーのログの最新の LSN（まだ書き込みがなければ 0）。"""
        raise NotImplementedError("演習1: ReplicatedStore.leader_lsn を実装してください")

    def write(self, key: str, value: Any) -> int:
        raise NotImplementedError("演習1: ReplicatedStore.write を実装してください")

    def replicate(self, follower: int, up_to: int | None = None) -> None:
        raise NotImplementedError("演習1: ReplicatedStore.replicate を実装してください")

    def applied_lsn(self, node: int | str) -> int:
        raise NotImplementedError("演習1: ReplicatedStore.applied_lsn を実装してください")

    def read(self, node: int | str, key: str) -> Any:
        raise NotImplementedError("演習1: ReplicatedStore.read を実装してください")


class Session:
    """1 人の利用者（1 つのセッション）から見た読み書き。LSN のトークンでセッション保証を実装する。

    状態:
        write_lsn: このセッションが書き込んだ最大の LSN（初期値は引数 token）
        read_lsn: このセッションが読んだノードの適用済み LSN の最大値（初期値 0）
        token（プロパティ）: max(write_lsn, read_lsn)。別の端末に渡すと、保証を引き継げる
        last_served_by: 直前の読み取りに応答したノード（LEADER またはフォロワー番号。初期値 None）

    required_lsn(): 読み取りに使うノードが満たすべき適用済み LSN の下限。
        read_your_writes が有効なら write_lsn 以上、monotonic_reads が有効なら read_lsn 以上。
        どちらも無効なら 0。

    write(key, value): ストアに書き込み、write_lsn を更新して LSN を返す。

    read(key, prefer): まず prefer のノード（フォロワー番号または LEADER）から読もうとする。
        - そのノードの適用済み LSN が required_lsn() 以上なら、そのまま読む。
        - 足りない場合:
            fallback == "leader" なら、リーダーから読む（リーダーは常に最新）。
            fallback == "wait" なら、store.replicate(prefer, up_to=required_lsn()) で
            **必要な位置までだけ** 追いつかせてから（＝追いつくのを待ってから）prefer から読む。
        - 読んだら last_served_by を記録し、read_lsn を max(read_lsn, 読んだノードの適用済み LSN) に更新する。
          （保証が無効でも read_lsn は記録する。有効かどうかは required_lsn() でだけ効く）

    検証: fallback が "leader" / "wait" 以外、token < 0 なら ValueError。

    実務との対応: MySQL の GTID を使った WAIT_FOR_EXECUTED_GTID_SET() や、MongoDB の因果一貫性セッション
    （afterClusterTime）は、この「トークンを持ち回り、足りなければ待つ」という仕組みの実例です（本文 3 節）。
    """

    def __init__(
        self,
        store: ReplicatedStore,
        *,
        read_your_writes: bool = True,
        monotonic_reads: bool = True,
        fallback: str = "leader",
        token: int = 0,
    ) -> None:
        raise NotImplementedError("演習1: Session.__init__ を実装してください")

    @property
    def token(self) -> int:
        raise NotImplementedError("演習1: Session.token を実装してください")

    def required_lsn(self) -> int:
        raise NotImplementedError("演習1: Session.required_lsn を実装してください")

    def write(self, key: str, value: Any) -> int:
        raise NotImplementedError("演習1: Session.write を実装してください")

    def read(self, key: str, prefer: int | str) -> Any:
        raise NotImplementedError("演習1: Session.read を実装してください")
