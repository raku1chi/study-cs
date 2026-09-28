import sqlite3  # ドメイン層がインフラ（DB ドライバ）に直接依存している

from shop.adapters.db import load_tax_rates  # ドメイン → アダプタ（外側）への依存

TaxRate = float


def price_with_tax(amount: int, conn: sqlite3.Connection) -> int:
    rate = load_tax_rates(conn)["standard"]
    return int(amount * (1 + rate))
