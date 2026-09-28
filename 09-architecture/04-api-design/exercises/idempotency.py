"""9.4 API設計 — 演習3: 冪等キー（Idempotency-Key）の層

ネットワークは不安定です。クライアントが「決済して」と送ったリクエストの応答がタイムアウトしたとき、
決済が行われたのかどうか、クライアントには分かりません。安全に再送できるようにするのが
**冪等キー** です。クライアントはリクエストごとに一意なキー（UUID など）を生成して
Idempotency-Key ヘッダーで送り、サーバーは同じキーの再送に対して、処理をやり直さずに
最初の結果を返します。この演習では、任意のハンドラの前に置ける冪等キーの層を作ります。

    演習3a: fingerprint — リクエストの内容の指紋（同じキーで別の内容が送られたことを検出する）
    演習3b: IdempotencyLayer — 保存・再送・内容の不一致・同時実行・有効期限・失敗の扱い

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.4

エラー応答は RFC 9457（Problem Details for HTTP APIs）の形の辞書にします。problem() を使ってください。
"""
from __future__ import annotations

import copy  # noqa: F401  演習3b で使えます
import hashlib  # noqa: F401  演習3a で使えます
import json  # noqa: F401  演習3a で使えます
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

REPLAY_HEADER = "Idempotent-Replayed"
MAX_KEY_LENGTH = 255
PROBLEM_BASE = "https://errors.example.com/"


@dataclass(frozen=True)
class Request:
    """認証済みのリクエスト。client_id は認証で確かめたクライアント（冪等キーの名前空間になる）。"""

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
    """RFC 9457 の Problem Details 形式のエラー応答を作る（実装済み）。"""
    body = {"type": PROBLEM_BASE + slug, "title": title, "status": status}
    if detail:
        body["detail"] = detail
    return Response(status, body, {"Content-Type": "application/problem+json"})


def valid_key(key: str) -> bool:
    """キーの形式: 1〜255 文字の、表示可能な ASCII 文字（"!"〜"~"。空白は含まない）。（実装済み）"""
    return 0 < len(key) <= MAX_KEY_LENGTH and all("!" <= ch <= "~" for ch in key)


# ---------------------------------------------------------------------------
# 演習3a: リクエストの指紋
# ---------------------------------------------------------------------------

def fingerprint(request: Request) -> str:
    """リクエストの「内容」を表す SHA-256 の 16 進文字列（64 文字）を返す。

    - 対象は method（大文字に揃える）、path、body。client_id は含めない（キーのスコープで区別するため）。
    - body の辞書のキーの順序や JSON の空白の違いで結果が変わってはいけない。
      json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False) で正規化した文字列を
      UTF-8 にしてハッシュするとよい。
    """
    raise NotImplementedError("演習3a: fingerprint を実装してください")


# ---------------------------------------------------------------------------
# 演習3b: 冪等キーの層
# ---------------------------------------------------------------------------

class IdempotencyLayer:
    """handler の前に置く冪等キーの層。

    - handler: 本来の処理（例: 決済の実行）。Request を受け取り Response を返す。例外を送出することもある。
    - ttl: 完了した結果を覚えておく秒数（clock で測る）。過ぎたら同じキーでも新しいリクエストとして扱う。
    - wait_timeout: 同じキーの処理が実行中のとき、完了を待つ最大の秒数（実時間）。
    - clock: 現在時刻（秒）を返す関数。テストでは偽の時計を渡す。
    - cache_server_errors: True なら 5xx の応答も保存して再送に返す（Stripe の方式に近い）。
      False（既定）なら 5xx は保存せず、同じキーで再試行すると処理をやり直す。

    executions は handler を呼んだ回数（テストと監視のため）。
    """

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
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._records: dict = {}
        self.executions = 0

    def handle(self, key: str | None, request: Request) -> Response:
        """冪等キー key 付きのリクエストを処理する。

        1. key が None か空 → 400（slug: "idempotency-key-required"）。handler は呼ばない。
           key の形式が不正（valid_key が False）→ 400（slug: "invalid-idempotency-key"）。
        2. キーのスコープは (request.client_id, key)。別のクライアントの同じキーは無関係。
        3. そのスコープの記録がない（または期限切れ）なら、「実行中」として記録してから handler を呼ぶ。
           handler はロックの外で呼ぶこと（呼んでいる間も、他のキーのリクエストを止めない）。
        4. 記録があり、指紋（fingerprint）が違う → 422（slug: "idempotency-key-reused"）。handler は呼ばない。
        5. 記録があり、完了している → 保存した応答のコピーに、ヘッダー REPLAY_HEADER: "true" を付けて返す。
        6. 記録があり、実行中 → 完了を最大 wait_timeout 秒待つ。完了したら 5 と同じく、その応答を返す。
           待ちきれなければ 409（slug: "request-in-progress"）。
        7. handler の結果の扱い:
           - 5xx 未満（成功や 4xx）: 保存し、完了時刻 + ttl を期限とする。
           - 5xx: cache_server_errors が True なら保存。False なら記録を消す（次の再試行で実行し直す）。
           - 例外: 記録を消し、待っていた呼び出しには 500（slug: "internal-error"）の応答を渡したうえで、
             最初の呼び出し元には例外をそのまま送出する。
           待っていた呼び出しには、保存するかどうかに関係なく、その実行の応答（のコピー、再送ヘッダー付き）を返す。
        8. 返す Response は常にコピー。呼び出し側が変更しても、保存した応答が変わらないこと。

        ヒント: 記録には「指紋・完了したか・保存するか・応答・期限・待っている数」を持たせる。
        待つには self._cond.wait_for(条件, timeout=...) が使える。完了を知らせるのは notify_all()。
        """
        raise NotImplementedError("演習3b: IdempotencyLayer.handle を実装してください")

    def waiting_count(self, client_id: str, key: str) -> int:
        """そのキーの完了を今待っている呼び出しの数（監視とテストのため）。記録がなければ 0。"""
        raise NotImplementedError("演習3b: IdempotencyLayer.waiting_count を実装してください")

    def purge_expired(self) -> int:
        """期限切れの完了済みの記録を消し、消した数を返す（定期的なお掃除用）。"""
        raise NotImplementedError("演習3b: IdempotencyLayer.purge_expired を実装してください")
