"""9.4 API設計 — 解答例: カーソル（キーセット）ページネーション

演習の仕様は exercises/pagination.py の docstring を参照してください。
"""
from __future__ import annotations

import base64
import binascii
import bisect
import hashlib
import hmac
import json
from dataclasses import dataclass

MAX_LIMIT = 100
CURSOR_VERSION = 1


@dataclass(frozen=True)
class Item:
    item_id: str
    created_at: int
    title: str = ""

    @property
    def key(self) -> tuple[int, str]:
        return (self.created_at, self.item_id)


class ItemStore:
    def __init__(self) -> None:
        self._items: dict[str, Item] = {}
        self._keys: list[tuple[int, str]] = []

    def insert(self, item: Item) -> None:
        if item.item_id in self._items:
            raise ValueError(f"重複した ID: {item.item_id}")
        self._items[item.item_id] = item
        bisect.insort(self._keys, item.key)

    def delete(self, item_id: str) -> None:
        item = self._items.pop(item_id)
        i = bisect.bisect_left(self._keys, item.key)
        del self._keys[i]

    def get(self, item_id: str) -> Item:
        return self._items[item_id]

    def sorted_keys(self) -> list[tuple[int, str]]:
        return self._keys

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class Page:
    items: list[Item]
    next_cursor: str | None


class InvalidCursorError(ValueError):
    pass


def paginate_offset(store: ItemStore, limit: int, offset: int) -> list[Item]:
    keys = store.sorted_keys()
    newest_first = list(reversed(keys))
    return [store.get(item_id) for _, item_id in newest_first[offset:offset + limit]]


# ---------------------------------------------------------------------------
# 演習1: 署名付きの不透明なカーソル
# ---------------------------------------------------------------------------

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    if not text or not all(c.isascii() and (c.isalnum() or c in "-_") for c in text):
        raise InvalidCursorError("カーソルの形式が不正です")
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError):
        raise InvalidCursorError("カーソルの形式が不正です") from None


def _sign(secret: bytes, payload: bytes) -> bytes:
    return hmac.new(secret, payload, hashlib.sha256).digest()


def encode_cursor(position: tuple[int, str], secret: bytes, *, scope: str = "") -> str:
    created_at, item_id = position
    payload = json.dumps(
        {"v": CURSOR_VERSION, "t": created_at, "id": item_id, "s": scope},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return f"{_b64encode(payload)}.{_b64encode(_sign(secret, payload))}"


def decode_cursor(cursor: str, secret: bytes, *, scope: str = "") -> tuple[int, str]:
    parts = cursor.split(".")
    if len(parts) != 2:
        raise InvalidCursorError("カーソルの形式が不正です")
    payload, signature = _b64decode(parts[0]), _b64decode(parts[1])
    # 署名の比較は定数時間で（先頭から何バイト一致したかを、応答時間から推測させない）
    if not hmac.compare_digest(signature, _sign(secret, payload)):
        raise InvalidCursorError("カーソルの署名が一致しません（改ざん、または別の鍵で作られた）")
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise InvalidCursorError("カーソルの内容が不正です") from None
    if not isinstance(data, dict) or data.get("v") != CURSOR_VERSION:
        raise InvalidCursorError("未対応のカーソルのバージョンです")
    t, item_id = data.get("t"), data.get("id")
    if not isinstance(t, int) or isinstance(t, bool) or not isinstance(item_id, str):
        raise InvalidCursorError("カーソルの内容が不正です")
    if data.get("s") != scope:
        raise InvalidCursorError("このカーソルは別の検索条件のものです")
    return (t, item_id)


# ---------------------------------------------------------------------------
# 演習2: キーセットページネーション
# ---------------------------------------------------------------------------

def paginate(store: ItemStore, limit: int, cursor: str | None, secret: bytes, *, scope: str = "") -> Page:
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit は 1〜{MAX_LIMIT} の整数です: {limit!r}")
    keys = store.sorted_keys()  # (created_at, item_id) の昇順
    if cursor is None:
        end = len(keys)
    else:
        # 新しい順に返すので、次のページは「カーソルの位置より厳密に古い」もの。
        # 位置は値で表しているので、カーソルの項目が削除されていても続きから探せる
        end = bisect.bisect_left(keys, decode_cursor(cursor, secret, scope=scope))
    # limit + 1 件を見ることで、「次のページがあるか」を余計な問い合わせなしで判定する
    start = max(0, end - (limit + 1))
    window = keys[start:end][::-1]
    page_keys = window[:limit]
    items = [store.get(item_id) for _, item_id in page_keys]
    has_more = len(window) > limit
    next_cursor = encode_cursor(page_keys[-1], secret, scope=scope) if has_more else None
    return Page(items, next_cursor)
