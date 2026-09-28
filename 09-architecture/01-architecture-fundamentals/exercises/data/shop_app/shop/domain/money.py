from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    amount: int
    currency: str = "JPY"

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("通貨が異なります")
        return Money(self.amount + other.amount, self.currency)
