"""6.3 トランザクションと同時実行制御 — 演習1 解答例: MVCC のキーバリューストア

演習の仕様は exercises/mvcc.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class TransactionError(Exception):
    pass


class SerializationError(Exception):
    pass


_DELETED = object()  # 削除（墓標）を表す番兵。書き込みバッファとバージョンの両方で使う


@dataclass
class Version:
    value: Any
    commit_ts: int
    txid: int

    @property
    def deleted(self) -> bool:
        return self.value is _DELETED


@dataclass(eq=False)
class Transaction:
    store: MVCCStore
    txid: int
    start_ts: int
    status: str = "active"
    commit_ts: int | None = None
    writes: dict[str, Any] = field(default_factory=dict)
    read_keys: set[str] = field(default_factory=set)
    read_prefixes: set[str] = field(default_factory=set)

    def _check_active(self) -> None:
        if self.status != "active":
            raise TransactionError(f"トランザクション {self.txid} は {self.status} です")

    def get(self, key: str, default: Any = None) -> Any:
        self._check_active()
        self.read_keys.add(key)
        # 自分の書き込みが最優先（read-your-own-writes）
        if key in self.writes:
            value = self.writes[key]
            return default if value is _DELETED else value
        version = self.store._visible_version(key, self.start_ts)
        if version is None or version.deleted:
            return default
        return version.value

    def put(self, key: str, value: Any) -> None:
        self._check_active()
        # 書き込みはコミットまで自分の中だけに溜める（他のトランザクションには見えない）
        self.writes[key] = value

    def delete(self, key: str) -> None:
        self._check_active()
        self.writes[key] = _DELETED

    def scan(self, prefix: str = "") -> dict[str, Any]:
        self._check_active()
        self.read_prefixes.add(prefix)
        result: dict[str, Any] = {}
        for key in self.store._versions:
            if key.startswith(prefix):
                version = self.store._visible_version(key, self.start_ts)
                if version is not None and not version.deleted:
                    result[key] = version.value
        for key, value in self.writes.items():
            if key.startswith(prefix):
                if value is _DELETED:
                    result.pop(key, None)
                else:
                    result[key] = value
        return dict(sorted(result.items()))

    def commit(self) -> int:
        self._check_active()
        return self.store._commit(self)

    def abort(self) -> None:
        self._check_active()
        self.status = "aborted"
        self.writes.clear()


class MVCCStore:
    def __init__(self, serializable: bool = False) -> None:
        self.serializable = serializable
        self._versions: dict[str, list[Version]] = {}  # キー → commit_ts の昇順のバージョン
        self._clock = 0  # 最後にコミットされた時刻
        self._next_txid = 1
        self._txns: list[Transaction] = []  # SSI の判定用に、終わったトランザクションも保持する

    def begin(self) -> Transaction:
        txn = Transaction(self, self._next_txid, start_ts=self._clock)
        self._next_txid += 1
        self._txns.append(txn)
        return txn

    def _visible_version(self, key: str, snapshot_ts: int) -> Version | None:
        # スナップショットの時刻までにコミットされた、最も新しいバージョン
        for version in reversed(self._versions.get(key, [])):
            if version.commit_ts <= snapshot_ts:
                return version
        return None

    def _commit(self, txn: Transaction) -> int:
        # first-committer-wins: 自分の開始後に、同じキーを先にコミットした者がいたら負け
        for key in txn.writes:
            versions = self._versions.get(key)
            if versions and versions[-1].commit_ts > txn.start_ts:
                txn.status = "aborted"
                txn.writes.clear()
                raise SerializationError(f"キー {key!r} は他のトランザクションが先に更新しました")
        if self.serializable and txn.writes and self._is_pivot(txn):
            txn.status = "aborted"
            txn.writes.clear()
            raise SerializationError("読み書きの依存関係が循環する可能性があります（危険な構造）")
        self._clock += 1
        txn.commit_ts = self._clock
        for key, value in txn.writes.items():
            self._versions.setdefault(key, []).append(Version(value, txn.commit_ts, txn.txid))
        txn.status = "committed"
        return txn.commit_ts

    # --- 発展: 簡略化した SSI ------------------------------------------------

    @staticmethod
    def _concurrent(a: Transaction, b: Transaction) -> bool:
        # 互いに相手のコミットより前に始まっていれば並行（まだコミットしていない側は無限大とみなす）
        inf = float("inf")
        a_end = a.commit_ts if a.commit_ts is not None else inf
        b_end = b.commit_ts if b.commit_ts is not None else inf
        return a.start_ts < b_end and b.start_ts < a_end

    @staticmethod
    def _read_overlaps(reader: Transaction, written: set[str]) -> bool:
        if reader.read_keys & written:
            return True
        return any(key.startswith(p) for p in reader.read_prefixes for key in written)

    def _is_pivot(self, txn: Transaction) -> bool:
        written = set(txn.writes)
        others = [u for u in self._txns if u is not txn and u.status != "aborted" and self._concurrent(u, txn)]
        # 入ってくる rw 依存: 並行する誰かが、txn の書くキーを（古いスナップショットで）読んだ
        has_in = any(self._read_overlaps(u, written) for u in others)
        # 出ていく rw 依存: txn が読んだキーを、並行する誰かが書いた（書こうとしている）
        has_out = any(self._read_overlaps(txn, set(v.writes)) for v in others)
        return has_in and has_out

    # --- ガベージコレクション -------------------------------------------------

    def version_count(self) -> int:
        return sum(len(v) for v in self._versions.values())

    def vacuum(self) -> int:
        active = [t.start_ts for t in self._txns if t.status == "active"]
        horizon = min(active) if active else self._clock
        removed = 0
        for key in list(self._versions):
            versions = self._versions[key]
            # horizon 以前にコミットされた最新のバージョンだけが、最も古いスナップショットに見える。
            # それより古いバージョンは、もう誰にも見えない
            keep_from = 0
            for i, version in enumerate(versions):
                if version.commit_ts <= horizon:
                    keep_from = i
            removed += keep_from
            del versions[:keep_from]
            if len(versions) == 1 and versions[0].deleted and versions[0].commit_ts <= horizon:
                removed += 1  # 誰からも「削除済み」にしか見えない墓標も消せる
                del self._versions[key]
        return removed
