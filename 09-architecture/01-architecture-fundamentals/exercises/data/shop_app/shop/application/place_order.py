from typing import TYPE_CHECKING

from ..domain.order import Order
from ..domain import pricing
from shop.domain.money import Money
from shop import legacy_helpers

if TYPE_CHECKING:
    # 型ヒントのためだけの import でも、設計上は「アプリケーション層がアダプタを知っている」ことになる
    from shop.adapters.db import Database


def place_order(order: Order, db: "Database") -> Money:
    legacy_helpers.log("placing order")
    return order.total()
