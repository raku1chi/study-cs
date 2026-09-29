"""消費税の計算。"""
REDUCED = {"food"}


def tax_for(lines, shipping):
    base = {8: 0, 10: shipping}
    for line in lines:
        rate = 8 if line.get("category") in REDUCED else 10
        base[rate] += line["amount"]
    return {rate: amount * rate // 100 for rate, amount in base.items() if amount}


def is_reduced(category):
    return category in REDUCED
