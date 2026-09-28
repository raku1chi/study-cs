"""7.2 レプリケーションと一貫性 — 演習: セッション保証（解答例）

演習の仕様は exercises/session_consistency.py の docstring を参照してください。
"""
from __future__ import annotations

from typing import Any

LEADER = "leader"

# ---------------------------------------------------------------------------
# 演習1: レプリケーションラグのあるリーダー・フォロワー構成
# ---------------------------------------------------------------------------


class ReplicatedStore:
    def __init__(self, num_followers: int = 2) -> None:
        if num_followers < 1:
            raise ValueError(f"フォロワーは 1 台以上です: {num_followers}")
        # リーダーのログ: LSN（1 始まりの通し番号）順の (key, value)
        self._log: list[tuple[str, Any]] = []
        self._leader_data: dict[str, Any] = {}
        self._follower_data: list[dict[str, Any]] = [{} for _ in range(num_followers)]
        self._applied: list[int] = [0] * num_followers

    @property
    def num_followers(self) -> int:
        return len(self._follower_data)

    @property
    def leader_lsn(self) -> int:
        return len(self._log)

    def _check_follower(self, follower: int) -> None:
        if not 0 <= follower < self.num_followers:
            raise IndexError(f"フォロワー番号が範囲外です: {follower}")

    def write(self, key: str, value: Any) -> int:
        self._log.append((key, value))
        self._leader_data[key] = value
        return self.leader_lsn

    def replicate(self, follower: int, up_to: int | None = None) -> None:
        self._check_follower(follower)
        if up_to is not None and up_to < 0:
            raise ValueError(f"up_to は 0 以上です: {up_to}")
        target = self.leader_lsn if up_to is None else min(up_to, self.leader_lsn)
        data = self._follower_data[follower]
        # ログを先頭から順に適用する（途中を飛ばさない = 一貫したプレフィックス）
        for lsn in range(self._applied[follower] + 1, target + 1):
            key, value = self._log[lsn - 1]
            data[key] = value
        self._applied[follower] = max(self._applied[follower], target)

    def applied_lsn(self, node: int | str) -> int:
        if node == LEADER:
            return self.leader_lsn
        self._check_follower(node)  # type: ignore[arg-type]
        return self._applied[node]  # type: ignore[index]

    def read(self, node: int | str, key: str) -> Any:
        if node == LEADER:
            return self._leader_data.get(key)
        self._check_follower(node)  # type: ignore[arg-type]
        return self._follower_data[node].get(key)  # type: ignore[index]


# ---------------------------------------------------------------------------
# 演習1（続き）: セッション保証
# ---------------------------------------------------------------------------


class Session:
    def __init__(
        self,
        store: ReplicatedStore,
        *,
        read_your_writes: bool = True,
        monotonic_reads: bool = True,
        fallback: str = "leader",
        token: int = 0,
    ) -> None:
        if fallback not in ("leader", "wait"):
            raise ValueError(f"fallback は 'leader' か 'wait' です: {fallback!r}")
        if token < 0:
            raise ValueError(f"token は 0 以上です: {token}")
        self.store = store
        self.read_your_writes = read_your_writes
        self.monotonic_reads = monotonic_reads
        self.fallback = fallback
        # 別の端末から引き継いだトークンは「そこまでの書き込みを見たい」という要求として扱う
        self.write_lsn = token
        self.read_lsn = 0
        self.last_served_by: int | str | None = None

    @property
    def token(self) -> int:
        return max(self.write_lsn, self.read_lsn)

    def required_lsn(self) -> int:
        required = 0
        if self.read_your_writes:
            required = max(required, self.write_lsn)
        if self.monotonic_reads:
            required = max(required, self.read_lsn)
        return required

    def write(self, key: str, value: Any) -> int:
        lsn = self.store.write(key, value)
        self.write_lsn = max(self.write_lsn, lsn)
        return lsn

    def read(self, key: str, prefer: int | str) -> Any:
        required = self.required_lsn()
        node = prefer
        if self.store.applied_lsn(prefer) < required:
            if self.fallback == "leader":
                node = LEADER  # リーダーは常に最新なので、必ず要求を満たす
            else:
                # 「待つ」: フォロワーが必要な位置まで追いつくのを待つ（ここでは追いつかせる）
                self.store.replicate(prefer, up_to=required)  # type: ignore[arg-type]
        value = self.store.read(node, key)
        self.last_served_by = node
        # 読んだレプリカの状態（どこまで適用済みか）を覚えておく。次の読み取りはこれより古くしない
        self.read_lsn = max(self.read_lsn, self.store.applied_lsn(node))
        return value
