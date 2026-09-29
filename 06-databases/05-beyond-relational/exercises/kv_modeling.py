"""6.5 データモデルの多様性とデータストアの選定 — 演習2: アクセスパターンから設計する KV のデータモデル

Amazon DynamoDB に代表される「パーティションキー＋ソートキー」型のキーバリューストアを
メモリ上で簡略化して実装し（演習2-1）、その上で EC サイトのアクセスパターンを満たすキーを
設計します（演習2-2）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.5
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_kv_modeling

RDB との考え方の違い:
    RDB は「正規化したテーブルを作り、問い合わせは後から SQL で自由に書く」。
    このタイプの KVS は結合も任意の条件の検索もできないので、「どんな問い合わせ（アクセスパターン）が
    必要か」を先に列挙し、それぞれが 1 回の get_item か query で済むようにキーを設計する。
    複数の種類の項目を 1 つの表に入れる「単一テーブル設計」がよく使われる。

この演習の Table（DynamoDB の簡略版。実物の API とは異なる）:
    - 項目は dict。"PK"（パーティションキー）と "SK"（ソートキー）は必須で、空でない文字列。
    - 同じ PK の項目は SK の昇順に並んで保存され、query で PK を指定し、SK の条件
      （begins_with = 前方一致、between = 範囲）で絞り込んで取り出せる。
    - GSI（グローバルセカンダリインデックス）: 別の属性の組をキーにした索引。
      Table(gsis={"GSI1": ("GSI1PK", "GSI1SK")}) のように定義する。その 2 つの属性を持つ項目だけが
      索引に入る（疎なインデックス）。
    - self.calls: 各操作の呼び出し回数（collections.Counter）。テストはアクセスパターンの関数が
      「query または get_item を 1 回だけ使い、scan は使わない」ことを確かめる。
"""
from __future__ import annotations

import copy  # noqa: F401  返す項目をコピーするのに使えます
from bisect import bisect_left, bisect_right, insort  # noqa: F401  演習2-1 で使えます
from collections import Counter
from collections.abc import Mapping
from typing import Any

Item = dict[str, Any]


# ---------------------------------------------------------------------------
# 演習2-1（★★☆）: DynamoDB 風の表
# ---------------------------------------------------------------------------

class Table:
    """パーティションキー＋ソートキーの表と GSI。

    >>> t = Table(gsis={"GSI1": ("email", "SK")})
    >>> t.put_item({"PK": "USER#1", "SK": "PROFILE", "email": "a@example.com"})
    >>> t.put_item({"PK": "USER#1", "SK": "ORDER#2025-01-05", "total": 300})
    >>> t.put_item({"PK": "USER#1", "SK": "ORDER#2025-03-01", "total": 500})
    >>> [i["SK"] for i in t.query("USER#1", begins_with="ORDER#")]
    ['ORDER#2025-01-05', 'ORDER#2025-03-01']
    >>> [i["PK"] for i in t.query("a@example.com", index="GSI1")]
    ['USER#1']
    >>> t.calls["query"]
    2
    """

    def __init__(self, gsis: Mapping[str, tuple[str, str]] | None = None) -> None:
        """gsis: {GSI 名: (パーティションキーの属性名, ソートキーの属性名)}。

        self.gsis と self.calls = Counter() を用意すること（テストが参照する）。
        """
        self.gsis = dict(gsis or {})
        self.calls: Counter[str] = Counter()
        raise NotImplementedError("演習2-1: Table.__init__ の残り（データ構造の用意）を実装してください")

    def put_item(self, item: Mapping[str, Any]) -> None:
        """項目を保存する（同じ PK と SK の項目があれば置き換える）。calls["put_item"] を 1 増やす。

        - PK・SK がない、または空でない文字列でなければ ValueError。
        - GSI の 2 つの属性をどちらも持つ項目は、その GSI に登録する。持っていれば、どちらも空でない
          文字列でなければ ValueError（何も保存しないこと）。
        - 置き換えのときは、古い項目の GSI のエントリを取り除いてから新しい項目を登録する。
        - 呼び出し側が後から dict を書き換えても影響を受けないよう、コピーして保存する。
        """
        raise NotImplementedError("演習2-1: put_item を実装してください")

    def get_item(self, pk: str, sk: str) -> Item | None:
        """PK と SK が一致する項目（のコピー）を返す。なければ None。calls["get_item"] を 1 増やす。"""
        raise NotImplementedError("演習2-1: get_item を実装してください")

    def delete_item(self, pk: str, sk: str) -> None:
        """項目を削除する（なければ何もしない）。GSI からも取り除く。calls["delete_item"] を 1 増やす。"""
        raise NotImplementedError("演習2-1: delete_item を実装してください")

    def query(
        self,
        pk: str,
        *,
        begins_with: str | None = None,
        between: tuple[str, str] | None = None,
        index: str | None = None,
        reverse: bool = False,
        limit: int | None = None,
    ) -> list[Item]:
        """パーティションキー pk の項目を、ソートキーの昇順（reverse=True なら降順）で返す。

        - index=None なら表そのもの（PK / SK）、GSI 名なら その GSI のキーで検索する。
          GSI では、ソートキーが同じ項目は (PK, SK) の昇順に並べる。存在しない GSI 名は ValueError。
        - begins_with: ソートキーがこの文字列で始まるものだけ。
        - between=(lo, hi): lo <= ソートキー <= hi のものだけ（文字列の大小比較）。
        - begins_with と between の両方を指定したら ValueError。
        - limit: 並べた後の先頭から最大 limit 件（1 以上。0 以下は ValueError）。
        - calls["query"] を 1 増やす。項目はコピーを返す。
        """
        raise NotImplementedError("演習2-1: query を実装してください")

    def scan(self) -> list[Item]:
        """すべての項目を (PK, SK) の順で返す（表全体を読むので遅い）。calls["scan"] を 1 増やす。"""
        raise NotImplementedError("演習2-1: scan を実装してください")


# ---------------------------------------------------------------------------
# 演習2-2（★★☆）: アクセスパターンのためのキー設計
# ---------------------------------------------------------------------------
#
# エンティティ（引数・戻り値の形）:
#   顧客: {"customer_id": "c1", "name": "佐藤", "email": "sato@example.com"}
#   注文: {"order_id": "o1001", "customer_id": "c1", "ordered_at": "2025-06-01T10:00:00Z",
#          "status": "paid", "items": [{"product_id": "p1", "quantity": 2, "unit_price": 1200}, ...]}
#     ordered_at は UTC の ISO 8601 形式の文字列（文字列の大小と時刻の前後が一致する）
#   注文のヘッダ: 注文から items を除いた {"order_id", "customer_id", "ordered_at", "status"} の 4 つだけの dict
#
# 読み取りの関数は、table.query か table.get_item を「ちょうど 1 回」だけ呼ぶこと（scan は禁止）。
# 書き込みの関数（put_*・update_*）は、何回呼んでもよい。
# PK・SK・GSI の属性の名前と値の形は自由に設計してよい。テストはこれらの関数だけを通して確かめる。
#
# ヒント（単一テーブル設計の定石）:
#   - キーに種類の接頭辞を付ける（"CUSTOMER#c1"、"ORDER#o1001"）。
#   - 一緒に読むものは同じ PK に置き、ソートキーの接頭辞で種類を分ける（"ITEM#p1"）。
#   - 範囲で絞りたい・並べたい値（日時）をソートキーの先頭に置く。
#   - PK / SK とは別の切り口で探したいときは GSI を使う。GSI のキーの値が変わる更新（ステータスの変更）では、
#     GSI の属性も書き換える。


def make_table() -> Table:
    """このアプリケーション用の Table を作る（必要な GSI を定義する）。"""
    raise NotImplementedError("演習2-2: make_table を実装してください")


def put_customer(table: Table, customer: Mapping[str, Any]) -> None:
    """顧客を保存する。"""
    raise NotImplementedError("演習2-2: put_customer を実装してください")


def get_customer(table: Table, customer_id: str) -> dict[str, Any] | None:
    """顧客を {"customer_id", "name", "email"} の dict で返す（キーの属性は含めない）。なければ None。"""
    raise NotImplementedError("演習2-2: get_customer を実装してください")


def put_order(table: Table, order: Mapping[str, Any]) -> None:
    """注文（ヘッダと明細）を保存する。"""
    raise NotImplementedError("演習2-2: put_order を実装してください")


def get_order(table: Table, order_id: str) -> dict[str, Any] | None:
    """注文のヘッダを返す。なければ None。"""
    raise NotImplementedError("演習2-2: get_order を実装してください")


def get_order_items(table: Table, order_id: str) -> list[dict[str, Any]]:
    """注文の明細 [{"product_id", "quantity", "unit_price"}, ...] を product_id の昇順で返す。"""
    raise NotImplementedError("演習2-2: get_order_items を実装してください")


def get_orders_for_customer(
    table: Table,
    customer_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
    newest_first: bool = True,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """顧客の注文のヘッダの一覧（「注文履歴」画面）。

    - since <= ordered_at < until のものだけ（None ならその側は制限なし）。since・until は
      "2025-06-01" や "2025-06-01T12:00:00Z" のような ISO 8601 の文字列。
    - ordered_at の降順（newest_first=False なら昇順）。同時刻なら order_id の順（降順なら逆順）。
    - limit: 先頭から最大 limit 件。
    """
    raise NotImplementedError("演習2-2: get_orders_for_customer を実装してください")


def update_order_status(table: Table, order_id: str, status: str) -> None:
    """注文のステータスを変更する。存在しない注文なら KeyError。"""
    raise NotImplementedError("演習2-2: update_order_status を実装してください")


def get_orders_by_status(table: Table, status: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """あるステータスの注文のヘッダを、ordered_at の古い順に返す（「未発送の注文」画面など）。"""
    raise NotImplementedError("演習2-2: get_orders_by_status を実装してください")
