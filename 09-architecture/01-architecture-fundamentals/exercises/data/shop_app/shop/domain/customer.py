from dataclasses import dataclass

from . import order  # order も customer を import しているので循環依存になる

CustomerId = str


@dataclass
class Customer:
    customer_id: CustomerId
    name: str

    def is_new_order_valid(self, o: "order.Order") -> bool:
        return o.customer_id == self.customer_id
