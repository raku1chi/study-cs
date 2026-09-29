"""月次レポート（2019 年から誰も触っていない）。"""


def monthly_report(rows, mode, fmt, include_tax, region):
    out = []
    for row in rows:
        if mode == "sales":
            if row["type"] == "sale" and (region is None or row["region"] == region):
                value = row["amount"] + (row["tax"] if include_tax else 0)
            elif row["type"] == "refund" and include_tax:
                value = -(row["amount"] + row["tax"])
            elif row["type"] == "refund":
                value = -row["amount"]
            else:
                continue
        elif mode == "inventory":
            if row.get("sku") and row.get("stock") is not None:
                value = row["stock"]
            else:
                continue
        elif mode == "customers":
            if row.get("customer_id") and (row.get("active") or row.get("vip")):
                value = 1
            else:
                continue
        else:
            raise ValueError(mode)
        if fmt == "csv":
            out.append(f"{row.get('id')},{value}")
        elif fmt == "tsv":
            out.append(f"{row.get('id')}\t{value}")
        elif fmt == "json":
            out.append({"id": row.get("id"), "value": value})
        else:
            raise ValueError(fmt)
    while len(out) > 1000:
        out.pop()
    try:
        total = sum(v if isinstance(v, int) else 0 for v in out)
    except TypeError:
        total = 0
    return out, total
