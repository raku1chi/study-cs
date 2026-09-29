"""注文の受付。"""
from shop.orders.models import Order


class OrderService:
    def __init__(self, repo, inventory, clock):
        self.repo = repo
        self.inventory = inventory
        self.clock = clock

    def place(self, customer_id, items):
        if not items:
            raise ValueError("empty order")
        for item in items:
            if item["qty"] <= 0:
                raise ValueError("qty must be positive")
            if not self.inventory.available(item["sku"], item["qty"]):
                raise RuntimeError(f"out of stock: {item['sku']}")
        order = Order(customer_id=customer_id, items=items, placed_at=self.clock())
        self.repo.save(order)
        return order

    def cancel(self, order_id):
        order = self.repo.get(order_id)
        if order is None:
            raise KeyError(order_id)
        if order.status in ("shipped", "delivered"):
            raise RuntimeError("already shipped")
        order.status = "cancelled"
        self.repo.save(order)
        return order
