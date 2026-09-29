"""9.4 API設計 — 解答例: 冪等キー（Idempotency-Key）の層

演習の仕様は exercises/idempotency.py の docstring を参照してください。
"""
from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

REPLAY_HEADER = "Idempotent-Replayed"
MAX_KEY_LENGTH = 255
PROBLEM_BASE = "https://errors.example.com/"


@dataclass(frozen=True)
class Request:
    client_id: str
    method: str
    path: str
    body: dict


@dataclass
class Response:
    status: int
    body: dict
    headers: dict[str, str] = field(default_factory=dict)


def problem(status: int, slug: str, title: str, detail: str = "") -> Response:
    body = {"type": PROBLEM_BASE + slug, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return Response(status, body, {"Content-Type": "application/problem+json"})


# ---------------------------------------------------------------------------
# 演習3a: リクエストの指紋
# ---------------------------------------------------------------------------

def fingerprint(request: Request) -> str:
    # キーの順序や空白の違いで指紋が変わらないよう、正規化した JSON にしてからハッシュする
    canonical = json.dumps(
        {"method": request.method.upper(), "path": request.path, "body": request.body},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def valid_key(key: str) -> bool:
    return 0 < len(key) <= MAX_KEY_LENGTH and all("!" <= ch <= "~" for ch in key)


# ---------------------------------------------------------------------------
# 演習3b: 冪等キーの層
# ---------------------------------------------------------------------------

@dataclass
class _Record:
    fingerprint: str
    done: bool = False
    completed: bool = False
    response: Response | None = None
    expires_at: float = 0.0
    waiters: int = 0


class IdempotencyLayer:
    def __init__(
        self,
        handler: Callable[[Request], Response],
        *,
        ttl: float = 24 * 3600,
        wait_timeout: float = 5.0,
        clock: Callable[[], float] = time.monotonic,
        cache_server_errors: bool = False,
    ) -> None:
        self._handler = handler
        self._ttl = ttl
        self._wait_timeout = wait_timeout
        self._clock = clock
        self._cache_server_errors = cache_server_errors
        self._records: dict[tuple[str, str], _Record] = {}
        # 1 つのロックと、それに結び付いた条件変数ですべての記録を守る
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self.executions = 0

    def handle(self, key: str | None, request: Request) -> Response:
        if not key:
            return problem(400, "idempotency-key-required", "Idempotency-Key ヘッダーが必要です")
        if not valid_key(key):
            return problem(400, "invalid-idempotency-key",
                           "Idempotency-Key は 1〜255 文字の表示可能な ASCII 文字です")
        fp = fingerprint(request)
        scope = (request.client_id, key)  # キーはクライアントごとの名前空間で管理する

        with self._cond:
            record = self._records.get(scope)
            if record is not None and record.completed and self._clock() >= record.expires_at:
                del self._records[scope]  # 期限切れ: 忘れて、新しいリクエストとして扱う
                record = None

            if record is None:
                record = _Record(fp)
                self._records[scope] = record
                self.executions += 1
            else:
                if record.fingerprint != fp:
                    return problem(422, "idempotency-key-reused",
                                   "同じ Idempotency-Key が別の内容のリクエストに使われました")
                if not record.done:
                    # 同じキーの処理が実行中: 完了を待って、同じ結果を返す
                    record.waiters += 1
                    try:
                        finished = self._cond.wait_for(lambda: record.done, timeout=self._wait_timeout)
                    finally:
                        record.waiters -= 1
                    if not finished:
                        return problem(409, "request-in-progress",
                                       "同じ Idempotency-Key のリクエストを処理中です。後で再試行してください")
                return self._replay(record.response)

        # ここに来るのは「最初の実行者」だけ。ハンドラはロックの外で呼ぶ（待っている人を妨げない）
        try:
            response = self._handler(request)
        except BaseException:
            with self._cond:
                record.response = problem(500, "internal-error", "内部エラーが発生しました")
                record.done = True
                self._forget(scope, record)  # 失敗は保存しない: 同じキーで再試行できる
                self._cond.notify_all()
            raise

        with self._cond:
            record.response = copy.deepcopy(response)
            record.done = True
            if response.status < 500 or self._cache_server_errors:
                record.completed = True
                record.expires_at = self._clock() + self._ttl
            else:
                self._forget(scope, record)
            self._cond.notify_all()
        return copy.deepcopy(response)

    def _forget(self, scope: tuple[str, str], record: _Record) -> None:
        if self._records.get(scope) is record:
            del self._records[scope]

    @staticmethod
    def _replay(response: Response) -> Response:
        replay = copy.deepcopy(response)
        replay.headers[REPLAY_HEADER] = "true"
        return replay

    def waiting_count(self, client_id: str, key: str) -> int:
        with self._lock:
            record = self._records.get((client_id, key))
            return record.waiters if record is not None else 0

    def purge_expired(self) -> int:
        now = self._clock()
        with self._lock:
            expired = [s for s, r in self._records.items() if r.completed and now >= r.expires_at]
            for scope in expired:
                del self._records[scope]
            return len(expired)
