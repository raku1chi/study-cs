"""8.5 リファクタリングと技術的負債 — 解答例: ストラングラー・フィグのルーター

仕様は exercises/strangler.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import operator
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

Handler = Callable[[dict], Any]


class InvalidTransition(Exception):
    """状態機械で許されない遷移。"""


@dataclass(frozen=True)
class Mismatch:
    route: str
    request: dict
    legacy: Any
    modern: Any
    error: Optional[str] = None


@dataclass
class RouteStats:
    shadow_compared: int = 0
    shadow_mismatches: int = 0
    canary_requests: int = 0
    canary_errors: int = 0


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


@dataclass
class _Route:
    prefix: str
    mode: str = "legacy"
    percent: int = 0
    stats: RouteStats = field(default_factory=RouteStats)


class StranglerRouter:
    def __init__(
        self,
        legacy: Handler,
        modern: Handler,
        *,
        comparator: Callable[[Any, Any], bool] = operator.eq,
        key: Callable[[dict], str] = lambda request: str(request.get("user_id", "")),
        min_shadow_samples: int = 100,
        max_mismatch_rate: float = 0.01,
        min_canary_samples: int = 100,
        max_error_rate: float = 0.01,
        max_recorded_mismatches: int = 100,
    ) -> None:
        self._legacy = legacy
        self._modern = modern
        self._comparator = comparator
        self._key = key
        self._min_shadow_samples = min_shadow_samples
        self._max_mismatch_rate = max_mismatch_rate
        self._min_canary_samples = min_canary_samples
        self._max_error_rate = max_error_rate
        self._max_recorded = max_recorded_mismatches
        self._routes: dict[str, _Route] = {}
        self._mismatches: list[Mismatch] = []

    @property
    def mismatches(self) -> list[Mismatch]:
        return list(self._mismatches)

    # --- ルートの管理 ---------------------------------------------------------

    def add_route(self, prefix: str) -> None:
        if not prefix.startswith("/"):
            raise ValueError(f"接頭辞は / で始めてください: {prefix!r}")
        if prefix in self._routes:
            raise ValueError(f"すでに登録されています: {prefix!r}")
        self._routes[prefix] = _Route(prefix)

    def _route(self, prefix: str) -> _Route:
        if prefix not in self._routes:
            raise KeyError(prefix)
        return self._routes[prefix]

    def mode(self, prefix: str) -> tuple[str, int]:
        route = self._route(prefix)
        return route.mode, route.percent

    def stats(self, prefix: str) -> RouteStats:
        s = self._route(prefix).stats
        return RouteStats(s.shadow_compared, s.shadow_mismatches, s.canary_requests, s.canary_errors)

    def _match(self, path: str) -> Optional[_Route]:
        best: Optional[_Route] = None
        for prefix, route in self._routes.items():
            base = prefix.rstrip("/")
            if prefix == "/" or path == prefix or path.startswith(base + "/"):
                if best is None or len(prefix) > len(best.prefix):
                    best = route
        return best

    # --- リクエストの処理 -----------------------------------------------------

    def handle(self, request: dict) -> Any:
        route = self._match(request["path"])
        if route is None or route.mode == "legacy":
            return self._legacy(request)
        if route.mode in ("modern", "retired"):
            return self._modern(request)
        if route.mode == "shadow":
            return self._shadow(route, request)
        return self._canary(route, request)

    def _shadow(self, route: _Route, request: dict) -> Any:
        response = self._legacy(request)  # 利用者に返すのは常に旧実装の応答
        route.stats.shadow_compared += 1
        try:
            candidate = self._modern(request)
            error = None
            same = bool(self._comparator(response, candidate))
        except Exception as exc:  # 新実装の失敗は、利用者に見せずに記録だけする
            candidate, error, same = None, f"{type(exc).__name__}: {exc}", False
        if not same:
            route.stats.shadow_mismatches += 1
            if len(self._mismatches) < self._max_recorded:
                self._mismatches.append(Mismatch(route.prefix, request, response, candidate, error))
        return response

    def _bucket(self, route: _Route, request: dict) -> int:
        digest = hashlib.sha256(f"{route.prefix}:{self._key(request)}".encode("utf-8")).hexdigest()
        return int(digest, 16) % 100

    def _canary(self, route: _Route, request: dict) -> Any:
        if self._bucket(route, request) >= route.percent:
            return self._legacy(request)
        route.stats.canary_requests += 1
        try:
            return self._modern(request)
        except Exception:
            # 読み取り専用のルートを想定したフォールバック。書き込みなら二重実行に注意が必要
            route.stats.canary_errors += 1
            return self._legacy(request)

    # --- 状態機械 ---------------------------------------------------------------

    def promote(self, prefix: str, percent: Optional[int] = None) -> None:
        route = self._route(prefix)
        s = route.stats
        if route.mode == "legacy":
            if percent is not None:
                raise ValueError("legacy から shadow への遷移に percent は指定できません")
            route.mode = "shadow"
        elif route.mode == "shadow":
            percent = 1 if percent is None else percent
            if not isinstance(percent, int) or not 1 <= percent <= 99:
                raise ValueError(f"percent は 1〜99 の整数にしてください: {percent!r}")
            if s.shadow_compared < self._min_shadow_samples:
                raise InvalidTransition(f"比較の回数が足りません（{s.shadow_compared} / {self._min_shadow_samples}）")
            if _rate(s.shadow_mismatches, s.shadow_compared) > self._max_mismatch_rate:
                raise InvalidTransition(
                    f"不一致の割合が高すぎます（{s.shadow_mismatches} / {s.shadow_compared}）")
            route.mode, route.percent = "canary", percent
        elif route.mode == "canary":
            target = 100 if percent is None else percent
            if not isinstance(target, int) or not route.percent < target <= 100:
                raise ValueError(f"percent は現在（{route.percent}）より大きく 100 以下にしてください: {percent!r}")
            if s.canary_requests < self._min_canary_samples:
                raise InvalidTransition(f"canary の標本が足りません（{s.canary_requests} / {self._min_canary_samples}）")
            if _rate(s.canary_errors, s.canary_requests) > self._max_error_rate:
                raise InvalidTransition(f"エラーの割合が高すぎます（{s.canary_errors} / {s.canary_requests}）")
            if target == 100:
                route.mode, route.percent = "modern", 100
            else:
                route.percent = target
        elif route.mode == "modern":
            route.mode = "retired"  # ここから先は旧実装を撤去できる。戻る道はない
        else:
            raise InvalidTransition(f"{prefix}: すでに移行が完了しています")

    def rollback(self, prefix: str) -> None:
        route = self._route(prefix)
        if route.mode in ("legacy", "retired"):
            raise InvalidTransition(f"{prefix}: {route.mode} からは戻せません")
        route.mode, route.percent, route.stats = "legacy", 0, RouteStats()
