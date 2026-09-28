"""7.1 分散システムの本質 — 演習: 決定的ネットワークシミュレータと「実質1回」の処理（解答例）

演習の仕様は exercises/simnet.py の docstring を参照してください。
"""
from __future__ import annotations

import heapq
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable

# ---------------------------------------------------------------------------
# 演習4: 決定的な離散イベント・ネットワークシミュレータ
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Message:
    src: str
    dst: str
    payload: Any
    sent_at: float


class Network:
    def __init__(
        self,
        seed: int = 0,
        *,
        min_delay: float = 1.0,
        max_delay: float = 10.0,
        drop_rate: float = 0.0,
        duplicate_rate: float = 0.0,
    ) -> None:
        if min_delay < 0 or max_delay < min_delay:
            raise ValueError(f"遅延は 0 <= min_delay <= max_delay で指定してください: {min_delay}, {max_delay}")
        for name, rate in (("drop_rate", drop_rate), ("duplicate_rate", duplicate_rate)):
            if not 0.0 <= rate <= 1.0:
                raise ValueError(f"{name} は 0〜1 で指定してください: {rate}")
        # 非決定性の源はこの乱数生成器 1 つだけ。シードが同じなら実行は完全に再現する
        self.rng = random.Random(seed)
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.drop_rate = drop_rate
        self.duplicate_rate = duplicate_rate
        self.now = 0.0
        self.stats = {"sent": 0, "dropped": 0, "duplicated": 0, "delivered": 0}
        self.log: list[tuple[float, str, str, Any]] = []
        self._handlers: dict[str, Callable[[Message], None]] = {}
        # イベントキュー: (発火時刻, 通し番号, コールバック)。通し番号で同時刻の順序を固定する
        self._queue: list[tuple[float, int, Callable[[], None]]] = []
        self._seq = 0
        self._groups: list[frozenset[str]] | None = None

    def register(self, node_id: str, handler: Callable[[Message], None]) -> None:
        if node_id in self._handlers:
            raise ValueError(f"ノード {node_id} は登録済みです")
        self._handlers[node_id] = handler

    def _push(self, at: float, callback: Callable[[], None]) -> None:
        self._seq += 1
        heapq.heappush(self._queue, (at, self._seq, callback))

    def _connected(self, a: str, b: str) -> bool:
        if self._groups is None or a == b:
            return True
        return any(a in g and b in g for g in self._groups)

    def send(self, src: str, dst: str, payload: Any) -> None:
        for node in (src, dst):
            if node not in self._handlers:
                raise ValueError(f"未登録のノードです: {node}")
        self.stats["sent"] += 1
        if not self._connected(src, dst) or self.rng.random() < self.drop_rate:
            self.stats["dropped"] += 1
            return
        copies = 1
        if self.rng.random() < self.duplicate_rate:
            copies = 2
            self.stats["duplicated"] += 1
        msg = Message(src, dst, payload, self.now)
        for _ in range(copies):
            # コピーごとに独立な遅延 → 追い越し（順序の入れ替わり）が自然に起きる
            delay = self.rng.uniform(self.min_delay, self.max_delay)
            self._push(self.now + delay, lambda m=msg: self._deliver(m))

    def _deliver(self, msg: Message) -> None:
        # 配送の瞬間に分断されていれば、途中で失われたものとして扱う
        if not self._connected(msg.src, msg.dst):
            self.stats["dropped"] += 1
            return
        self.stats["delivered"] += 1
        self.log.append((self.now, msg.src, msg.dst, msg.payload))
        self._handlers[msg.dst](msg)

    def schedule(self, delay: float, callback: Callable[[], None]) -> None:
        if delay < 0:
            raise ValueError(f"delay は 0 以上です: {delay}")
        self._push(self.now + delay, callback)

    def partition(self, *groups: Iterable[str]) -> None:
        self._groups = [frozenset(g) for g in groups]

    def heal(self) -> None:
        self._groups = None

    def pending(self) -> int:
        return len(self._queue)

    def run(self, until: float | None = None, max_events: int = 1_000_000) -> int:
        processed = 0
        while self._queue:
            at, _, callback = self._queue[0]
            if until is not None and at > until:
                break
            heapq.heappop(self._queue)
            self.now = at
            callback()
            processed += 1
            if processed > max_events:
                raise RuntimeError(f"イベント数が上限 {max_events} を超えました（無限ループの可能性）")
        if until is not None and until > self.now:
            self.now = until
        return processed


# ---------------------------------------------------------------------------
# 演習5: at-least-once 配信（再送と ACK）と冪等な受信側
# ---------------------------------------------------------------------------


class ReliableSender:
    def __init__(
        self,
        net: Network,
        node_id: str,
        *,
        retry_interval: float = 30.0,
        max_attempts: int = 10,
    ) -> None:
        if retry_interval <= 0 or max_attempts < 1:
            raise ValueError("retry_interval > 0、max_attempts >= 1 で指定してください")
        self.net = net
        self.node_id = node_id
        self.retry_interval = retry_interval
        self.max_attempts = max_attempts
        self.pending: dict[str, tuple[str, Any]] = {}
        self.attempts: dict[str, int] = {}
        self.acked: set[str] = set()
        self.failed: set[str] = set()
        self._counter = 0
        net.register(node_id, self.on_message)

    def send(self, dst: str, body: Any) -> str:
        self._counter += 1
        # メッセージ ID は送信側が 1 回だけ決め、再送でも同じ ID を使う（重複排除の鍵）
        msg_id = f"{self.node_id}-{self._counter}"
        self.pending[msg_id] = (dst, body)
        self.attempts[msg_id] = 0
        self._attempt(msg_id)
        return msg_id

    def _attempt(self, msg_id: str) -> None:
        if msg_id not in self.pending:
            return  # すでに ACK 済み
        if self.attempts[msg_id] >= self.max_attempts:
            # 諦める。ただし「相手が処理しなかった」とは限らない（ACK だけ失われた可能性）
            del self.pending[msg_id]
            self.failed.add(msg_id)
            return
        self.attempts[msg_id] += 1
        dst, body = self.pending[msg_id]
        self.net.send(self.node_id, dst, {"type": "DATA", "id": msg_id, "body": body})
        self.net.schedule(self.retry_interval, lambda: self._attempt(msg_id))

    def on_message(self, msg: Message) -> None:
        payload = msg.payload
        if payload.get("type") == "ACK" and payload["id"] in self.pending:
            del self.pending[payload["id"]]
            self.acked.add(payload["id"])


class IdempotentReceiver:
    def __init__(
        self,
        net: Network,
        node_id: str,
        process: Callable[[Any], None] | None = None,
    ) -> None:
        self.net = net
        self.node_id = node_id
        self.processed: list[Any] = []
        self.seen: set[str] = set()
        self.duplicates = 0
        self._process = process
        net.register(node_id, self.on_message)

    def on_message(self, msg: Message) -> None:
        payload = msg.payload
        if payload.get("type") != "DATA":
            return
        msg_id = payload["id"]
        if msg_id in self.seen:
            self.duplicates += 1
        else:
            # 実システムでは「処理結果」と「処理済み ID」を同じトランザクションで保存する（7.5 参照）
            self.seen.add(msg_id)
            self.processed.append(payload["body"])
            if self._process is not None:
                self._process(payload["body"])
        # 重複にも必ず ACK を返す。最初の ACK が失われた場合、送信側はこの ACK を待っている
        self.net.send(self.node_id, msg.src, {"type": "ACK", "id": msg_id})
