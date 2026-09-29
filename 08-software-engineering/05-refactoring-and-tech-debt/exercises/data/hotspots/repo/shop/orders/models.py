"""注文のデータ。"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Order:
    customer_id: str
    items: list
    placed_at: datetime
    status: str = "placed"
    notes: list = field(default_factory=list)

    @property
    def item_count(self):
        return sum(item["qty"] for item in self.items)
