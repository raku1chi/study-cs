from shop.billing.invoice import build_invoice, split_invoice


def test_gold_discount():
    order = {"items": [{"sku": "A", "price": 1000, "qty": 1}]}
    assert build_invoice(order, {"tier": "gold"}, {"send_mail": False})["total"] == 900


def test_split():
    invoice = {"lines": [{"sku": str(i)} for i in range(5)]}
    assert [len(p) for p in split_invoice(invoice, 2)] == [2, 2, 1]
