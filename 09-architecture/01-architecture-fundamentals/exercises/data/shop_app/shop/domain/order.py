from dataclasses import dataclass, field

from .money import Money
from shop.domain.customer import CustomerId


@dataclass
class Order:
    order_id: str
    customer_id: CustomerId
    lines: list = field(default_factory=list)

    def total(self) -> Money:
        total = Money(0)
        for line in self.lines:
            total = total + line.price
        return total
