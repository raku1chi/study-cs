"""メールの文面。"""


def invoice_mail(customer, invoice):
    name = customer.get("name", "お客様")
    return f"{name} 様\nご請求金額: {invoice['total'] + invoice['shipping']:,} 円（税別）\n"


def shipping_mail(customer, tracking_number):
    return f"{customer.get('name', 'お客様')} 様\n発送しました。お問い合わせ番号: {tracking_number}\n"
