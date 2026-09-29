"""8.5 演習3 で振る舞いを固定する「レガシーコード」（完成しています。編集しないでください）

何年も改修が重ねられ、仕様書が残っていない送料の計算です。テストもありません。
このコードをリファクタリングする前に、承認テスト（characterize.py）で現在の振る舞いを記録します。
"""


def shipping_fee(weight_g, prefecture, express=False, member=False):
    # 2014 年: 全国一律 600 円で開始
    if weight_g <= 0:
        raise ValueError("weight_g must be positive")
    if prefecture == "沖縄県":
        base = 1200
    elif prefecture == "北海道":
        base = 900
    else:
        base = 600
    # 2017 年: 重量の追加料金（2kg を超えたら、超えた 1kg ごとに 200 円 + 基本の 200 円）
    if weight_g > 2000:
        base += (weight_g - 2000) // 1000 * 200 + 200
    # 2019 年: 速達は 1.5 倍（沖縄県は受け付けない）
    if express:
        base = base * 3 // 2
        if prefecture == "沖縄県":
            raise ValueError("沖縄県への速達は受け付けていません")
    # 2021 年: 会員は 100 円引き（速達を除く）
    if member and not express:
        base -= 100
    return base
