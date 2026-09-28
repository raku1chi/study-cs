"""7.4 合意と協調 — 演習: リースとフェンシングトークン（解答例）

演習の仕様は exercises/fencing.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class StaleTokenError(Exception):
    pass


@dataclass
class Lease:
    holder: str
    token: int
    expires_at: int


class LockService:
    def __init__(self, lease_ms: int, clock: Callable[[], int]) -> None:
        if lease_ms <= 0:
            raise ValueError(f"lease_ms は正の数です: {lease_ms}")
        self.lease_ms = lease_ms
        self.clock = clock
        self._leases: dict[str, Lease] = {}
        self._last_token = 0  # 全ロック共通で単調増加（etcd のリビジョンのように）

    def _valid(self, name: str) -> Lease | None:
        lease = self._leases.get(name)
        if lease is None or self.clock() >= lease.expires_at:
            return None  # 期限切れのリースは、保持者が何を思っていようと無効
        return lease

    def acquire(self, name: str, client_id: str) -> int | None:
        lease = self._valid(name)
        now = self.clock()
        if lease is not None:
            if lease.holder != client_id:
                return None
            lease.expires_at = now + self.lease_ms  # 保持者による再取得は延長として扱う
            return lease.token
        self._last_token += 1
        self._leases[name] = Lease(client_id, self._last_token, now + self.lease_ms)
        return self._last_token

    def renew(self, name: str, client_id: str, token: int) -> bool:
        lease = self._valid(name)
        if lease is None or lease.holder != client_id or lease.token != token:
            return False  # 一度でも期限が切れたら、延長はできない（別のクライアントが取っているかもしれない）
        lease.expires_at = self.clock() + self.lease_ms
        return True

    def release(self, name: str, client_id: str, token: int) -> bool:
        lease = self._valid(name)
        if lease is None or lease.holder != client_id or lease.token != token:
            return False
        del self._leases[name]
        return True

    def holder(self, name: str) -> tuple[str, int] | None:
        lease = self._valid(name)
        return None if lease is None else (lease.holder, lease.token)


class FencedStorage:
    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self._max_token: dict[str, int] = {}

    def write(self, key: str, value: Any, token: int) -> None:
        # 見たことのある最大のトークンより小さいトークンの書き込みは、古いロック保持者からのものなので拒否する
        if token < self._max_token.get(key, 0):
            raise StaleTokenError(f"{key}: トークン {token} は古い（最新 {self._max_token[key]}）")
        self._max_token[key] = token
        self.data[key] = value

    def read(self, key: str) -> Any:
        return self.data.get(key)


class UnfencedStorage:
    """悪い例: トークンを検査しないストレージ（比較用）。"""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}

    def write(self, key: str, value: Any, token: int | None = None) -> None:
        self.data[key] = value

    def read(self, key: str) -> Any:
        return self.data.get(key)
