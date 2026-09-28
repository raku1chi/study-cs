import sqlite3

from shop.domain.order import Order
from shop.domain.pricing import TaxRate


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)

    def save(self, order: Order) -> None:
        self.conn.execute("INSERT INTO orders (id) VALUES (?)", (order.order_id,))


def load_tax_rates(conn: sqlite3.Connection) -> "dict[str, TaxRate]":
    return {"standard": 0.10, "reduced": 0.08}
