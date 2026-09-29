"""6.5 データモデルの多様性とデータストアの選定 — 演習2 解答例: アクセスパターンから設計するキーバリューのデータモデル

演習の仕様は exercises/kv_modeling.py の docstring を参照してください。
"""
from __future__ import annotations

import copy
from bisect import bisect_left, bisect_right, insort
from collections import Counter
from collections.abc import Mapping
from typing import Any

Item = dict[str, Any]


# ---------------------------------------------------------------------------
# 演習2-1: DynamoDB 風の表
# ---------------------------------------------------------------------------

class Table:
    def __init__(self, gsis: Mapping[str, tuple[str, str]] | None = None) -> None:
        self.gsis = dict(gsis or {})
        self.calls: Counter[str] = Counter()
        # パーティションキー → {ソートキー: 項目} と、ソートキーの昇順のリスト
        self._items: dict[str, dict[str, Item]] = {}
        self._order: dict[str, list[str]] = {}
        # GSI 名 → GSI のパーティションキー → [(GSI のソートキー, PK, SK)] の昇順のリスト
        self._gsi: dict[str, dict[str, list[tuple[str, str, str]]]] = {name: {} for name in self.gsis}

    @staticmethod
    def _check_key(value: Any, name: str) -> None:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{name} は空でない文字列にしてください: {value!r}")

    def _gsi_key(self, index: str, item: Item) -> tuple[str, str] | None:
        pk_attr, sk_attr = self.gsis[index]
        if pk_attr not in item or sk_attr not in item:
            return None  # 疎なインデックス: 属性を持たない項目は GSI に入らない
        self._check_key(item[pk_attr], pk_attr)
        self._check_key(item[sk_attr], sk_attr)
        return item[pk_attr], item[sk_attr]

    def _unindex(self, item: Item) -> None:
        for index in self.gsis:
            key = self._gsi_key(index, item)
            if key is not None:
                entries = self._gsi[index][key[0]]
                entries.remove((key[1], item["PK"], item["SK"]))
                if not entries:
                    del self._gsi[index][key[0]]

    def put_item(self, item: Mapping[str, Any]) -> None:
        self.calls["put_item"] += 1
        item = copy.deepcopy(dict(item))
        self._check_key(item.get("PK"), "PK")
        self._check_key(item.get("SK"), "SK")
        gsi_keys = {index: self._gsi_key(index, item) for index in self.gsis}  # 先に検査する
        pk, sk = item["PK"], item["SK"]
        partition = self._items.setdefault(pk, {})
        if sk in partition:
            self._unindex(partition[sk])  # 上書き: 古い項目の GSI のエントリを消す
        else:
            insort(self._order.setdefault(pk, []), sk)
        partition[sk] = item
        for index, key in gsi_keys.items():
            if key is not None:
                insort(self._gsi[index].setdefault(key[0], []), (key[1], pk, sk))

    def get_item(self, pk: str, sk: str) -> Item | None:
        self.calls["get_item"] += 1
        item = self._items.get(pk, {}).get(sk)
        return copy.deepcopy(item) if item is not None else None

    def delete_item(self, pk: str, sk: str) -> None:
        self.calls["delete_item"] += 1
        partition = self._items.get(pk, {})
        item = partition.pop(sk, None)
        if item is None:
            return
        self._unindex(item)
        self._order[pk].remove(sk)
        if not partition:
            del self._items[pk]
            del self._order[pk]

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
        self.calls["query"] += 1
        if begins_with is not None and between is not None:
            raise ValueError("begins_with と between は同時に指定できません")
        if limit is not None and limit <= 0:
            raise ValueError("limit は 1 以上にしてください")
        if index is None:
            keys = [(sk, pk, sk) for sk in self._order.get(pk, [])]
        else:
            if index not in self.gsis:
                raise ValueError(f"GSI がありません: {index}")
            keys = self._gsi[index].get(pk, [])
        sort_keys = [k[0] for k in keys]
        # ソートキーは昇順に並んでいるので、範囲は二分探索で切り出せる
        if begins_with is not None:
            lo = bisect_left(sort_keys, begins_with)
            hi = lo
            while hi < len(sort_keys) and sort_keys[hi].startswith(begins_with):
                hi += 1
        elif between is not None:
            lo, hi = bisect_left(sort_keys, between[0]), bisect_right(sort_keys, between[1])
        else:
            lo, hi = 0, len(sort_keys)
        selected = keys[lo:hi]
        if reverse:
            selected = selected[::-1]
        if limit is not None:
            selected = selected[:limit]
        return [copy.deepcopy(self._items[p][s]) for _, p, s in selected]

    def scan(self) -> list[Item]:
        self.calls["scan"] += 1
        return [copy.deepcopy(self._items[pk][sk]) for pk in sorted(self._items) for sk in self._order[pk]]


# ---------------------------------------------------------------------------
# 演習2-2: アクセスパターンのためのキー設計（単一テーブル設計）
# ---------------------------------------------------------------------------
#
#   項目              PK                  SK                          GSI1PK / GSI1SK                       GSI2PK / GSI2SK
#   顧客              CUSTOMER#<id>       PROFILE
#   注文のヘッダ      ORDER#<order_id>    #HEADER                     CUSTOMER#<id> / <ordered_at>#<order_id>  STATUS#<status> / <ordered_at>#<order_id>
#   注文の明細        ORDER#<order_id>    ITEM#<product_id>
#
#   - 注文のヘッダと明細を同じパーティションに置くと、注文 1 件分を 1 回の query で読める。
#   - 顧客ごとの注文の一覧は GSI1 で、ソートキーを注文日時で始めると期間の絞り込みと並べ替えが効く。
#   - ステータスごとの一覧は GSI2。ステータスが変わったら GSI2PK を書き換える。

HEADER_FIELDS = ("order_id", "customer_id", "ordered_at", "status")


def make_table() -> Table:
    return Table(gsis={"GSI1": ("GSI1PK", "GSI1SK"), "GSI2": ("GSI2PK", "GSI2SK")})


def _customer_key(customer_id: str) -> str:
    return f"CUSTOMER#{customer_id}"


def _order_key(order_id: str) -> str:
    return f"ORDER#{order_id}"


def _header(item: Mapping[str, Any]) -> dict[str, Any]:
    return {k: item[k] for k in HEADER_FIELDS}


def put_customer(table: Table, customer: Mapping[str, Any]) -> None:
    table.put_item({"PK": _customer_key(customer["customer_id"]), "SK": "PROFILE", **customer})


def get_customer(table: Table, customer_id: str) -> dict[str, Any] | None:
    item = table.get_item(_customer_key(customer_id), "PROFILE")
    if item is None:
        return None
    return {k: v for k, v in item.items() if k not in ("PK", "SK")}


def put_order(table: Table, order: Mapping[str, Any]) -> None:
    header = _header(order)
    sort_key = f"{order['ordered_at']}#{order['order_id']}"
    table.put_item({
        "PK": _order_key(order["order_id"]),
        "SK": "#HEADER",
        **header,
        "GSI1PK": _customer_key(order["customer_id"]),
        "GSI1SK": sort_key,
        "GSI2PK": f"STATUS#{order['status']}",
        "GSI2SK": sort_key,
    })
    for line in order["items"]:
        table.put_item({"PK": _order_key(order["order_id"]), "SK": f"ITEM#{line['product_id']}", **line})


def get_order(table: Table, order_id: str) -> dict[str, Any] | None:
    item = table.get_item(_order_key(order_id), "#HEADER")
    return _header(item) if item is not None else None


def get_order_items(table: Table, order_id: str) -> list[dict[str, Any]]:
    items = table.query(_order_key(order_id), begins_with="ITEM#")
    return [{"product_id": i["product_id"], "quantity": i["quantity"], "unit_price": i["unit_price"]} for i in items]


def get_orders_for_customer(
    table: Table,
    customer_id: str,
    *,
    since: str | None = None,
    until: str | None = None,
    newest_first: bool = True,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    # ソートキーは "<ordered_at>#<order_id>"。"~" は ASCII で英数字より後ろなので、上限の番兵に使える。
    # until は含まない: "<until>" は "<until>#..." より小さいので、between の上限にすれば until ちょうどは除かれる
    lower = since if since is not None else ""
    upper = until if until is not None else "~"
    items = table.query(
        _customer_key(customer_id), between=(lower, upper), index="GSI1", reverse=newest_first, limit=limit
    )
    return [_header(i) for i in items]


def update_order_status(table: Table, order_id: str, status: str) -> None:
    item = table.get_item(_order_key(order_id), "#HEADER")
    if item is None:
        raise KeyError(order_id)
    item["status"] = status
    item["GSI2PK"] = f"STATUS#{status}"  # GSI のキーも更新しないと、古いステータスの一覧に残る
    table.put_item(item)


def get_orders_by_status(table: Table, status: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    items = table.query(f"STATUS#{status}", index="GSI2", limit=limit)
    return [_header(i) for i in items]
