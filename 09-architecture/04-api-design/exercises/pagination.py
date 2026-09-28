"""9.4 API設計 — 演習2: カーソル（キーセット）ページネーション

「新しい順の一覧」を API で返すとき、OFFSET を使ったページ送り（?page=2）は、
ページを読んでいる間に新しい項目が追加されると、同じ項目が 2 回返ったり、逆に読み飛ばされたりします。
この演習では、最後に返した項目の位置（created_at, item_id）を **署名付きの不透明なカーソル** にして返し、
次のページはその位置より後ろから読む **キーセットページネーション** を実装します。

    演習2a: encode_cursor / decode_cursor — 改ざんを検出できる、URL に載せられるカーソル
    演習2b: paginate — 挿入・削除が起きても重複も欠落もしないページ送り

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.4

並び順: created_at の新しい順。同じ created_at の項目は item_id の降順（全順序にするための「決勝点」）。
"""
from __future__ import annotations

import base64  # noqa: F401  演習2a で使えます
import binascii  # noqa: F401
import bisect
import hashlib  # noqa: F401
import hmac  # noqa: F401
import json  # noqa: F401
from dataclasses import dataclass

MAX_LIMIT = 100
CURSOR_VERSION = 1


# ---------------------------------------------------------------------------
# 実装済み: データとストア
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Item:
    item_id: str
    created_at: int   # エポックからのミリ秒
    title: str = ""

    @property
    def key(self) -> tuple[int, str]:
        """並べ替えのキー (created_at, item_id)。"""
        return (self.created_at, self.item_id)


class ItemStore:
    """項目を保持し、キー (created_at, item_id) の昇順の一覧を保つ（DB のインデックスの代わり）。"""

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
        """(created_at, item_id) の **昇順** のリスト（変更しないこと）。bisect で位置を探せる。"""
        return self._keys

    def __len__(self) -> int:
        return len(self._items)


@dataclass(frozen=True)
class Page:
    items: list[Item]
    next_cursor: str | None   # 次のページがなければ None


class InvalidCursorError(ValueError):
    """カーソルが壊れている・改ざんされている・別の条件のもの。API では 400 にする。"""


def paginate_offset(store: ItemStore, limit: int, offset: int) -> list[Item]:
    """比較用: OFFSET 方式のページ送り（新しい順）。本文で、この方式の問題を確かめる。"""
    keys = store.sorted_keys()
    newest_first = list(reversed(keys))
    return [store.get(item_id) for _, item_id in newest_first[offset:offset + limit]]


# ---------------------------------------------------------------------------
# 演習2a: 署名付きの不透明なカーソル
# ---------------------------------------------------------------------------

def encode_cursor(position: tuple[int, str], secret: bytes, *, scope: str = "") -> str:
    """位置 (created_at, item_id) を、署名付きのカーソル文字列にする。

    形式: 「ペイロード」と「署名」を base64url（パディングの = なし）にして "." でつないだもの。
    - ペイロード: {"v": CURSOR_VERSION, "t": created_at, "id": item_id, "s": scope} を
      json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False) して UTF-8 にしたもの
    - 署名: HMAC-SHA256(secret, ペイロード) の 32 バイト
    scope は検索条件（例: "owner=u1"）。別の条件の一覧にカーソルを流用させないために署名に含める。
    結果は URL にそのまま載せられる文字（英数字・"-"・"_"・"."）だけからなる。
    """
    raise NotImplementedError("演習2a: encode_cursor を実装してください")


def decode_cursor(cursor: str, secret: bytes, *, scope: str = "") -> tuple[int, str]:
    """encode_cursor の逆。次のどれかに当てはまれば InvalidCursorError:

    - "." で区切った部分が 2 つでない、base64url として不正（許される文字は英数字・"-"・"_"）
    - 署名が一致しない（比較は hmac.compare_digest で定数時間に行うこと）
    - ペイロードが JSON の辞書でない、v が CURSOR_VERSION でない、t が int（bool は不可）でない、
      id が str でない
    - s が引数の scope と一致しない
    署名を検証してからペイロードを解釈すること（検証していないデータを信用しない）。
    """
    raise NotImplementedError("演習2a: decode_cursor を実装してください")


# ---------------------------------------------------------------------------
# 演習2b: キーセットページネーション
# ---------------------------------------------------------------------------

def paginate(store: ItemStore, limit: int, cursor: str | None, secret: bytes, *, scope: str = "") -> Page:
    """新しい順に最大 limit 件を返す。cursor が None なら先頭から、そうでなければカーソルの位置の続きから。

    - limit は 1〜MAX_LIMIT の int（bool は不可）。それ以外は ValueError。
    - 「続き」とは、並び順でカーソルの位置より厳密に後ろ（= キーが厳密に小さい）の項目。
      カーソルの位置の項目が削除されていても、続きから正しく読めること。
    - next_cursor は、このページの最後の項目の位置のカーソル。ただし、もう後ろに項目がなければ None
      （空のページを取りに来させない。limit + 1 件を調べれば分かる）。
    - store.sorted_keys() は昇順なので、bisect.bisect_left で「カーソルの位置より小さい範囲の終わり」を
      O(log n) で探せる（DB ではインデックスを使った WHERE (created_at, id) < (?, ?) に相当）。
    """
    raise NotImplementedError("演習2b: paginate を実装してください")
