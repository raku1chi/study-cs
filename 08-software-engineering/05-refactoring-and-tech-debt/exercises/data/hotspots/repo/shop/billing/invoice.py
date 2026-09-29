"""請求書の作成（何年も継ぎ足されてきたモジュール）。"""
from shop.billing.tax import tax_for
from shop.notifications.email_templates import invoice_mail


def build_invoice(order, customer, options=None):
    options = options or {}
    lines = []
    total = 0
    for item in order["items"]:
        if item.get("gift") and not options.get("show_gift_prices"):
            price = 0
        elif item.get("bundle"):
            price = sum(p["price"] for p in item["bundle"] if not p.get("free"))
        else:
            price = item["price"] * item["qty"]
        if customer.get("tier") == "gold" and item.get("category") != "book":
            price = price * 90 // 100
        elif customer.get("tier") == "silver" and item.get("category") != "book":
            price = price * 95 // 100
        lines.append({"sku": item["sku"], "amount": price})
        total += price
    if order.get("coupon"):
        if order["coupon"] == "WELCOME10" and customer.get("tier") == "regular":
            total -= total // 10
        elif order["coupon"] == "GOODS500" and total >= 3000:
            total -= 500
    shipping = 0 if total >= 5000 or customer.get("tier") == "gold" else 500
    tax = tax_for(lines, shipping)
    invoice = {"lines": lines, "total": total, "shipping": shipping, "tax": tax}
    if customer.get("email") and options.get("send_mail", True):
        invoice["mail"] = invoice_mail(customer, invoice)
    return invoice


def split_invoice(invoice, max_lines):
    if max_lines <= 0:
        raise ValueError("max_lines must be positive")
    pages = []
    for start in range(0, len(invoice["lines"]), max_lines):
        pages.append(invoice["lines"][start:start + max_lines])
    return pages or [[]]


def invoice_status(invoice, paid_at, cancelled_at, now):
    if cancelled_at is not None:
        return "cancelled"
    if paid_at is not None:
        return "paid" if paid_at <= now else "scheduled"
    if invoice.get("due_date") and invoice["due_date"] < now:
        return "overdue"
    return "open"
