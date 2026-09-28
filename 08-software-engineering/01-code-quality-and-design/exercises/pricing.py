"""8.1 良いコードと設計原則 — 演習1・2: 価格計算エンジンのリファクタリング（カタ）

このファイルは NotImplementedError のスタブではありません。架空の EC サイト
「ねこのて商店」（書籍・食品・雑貨を扱う）で何年も使われてきた、
**動いているが読みにくい** 価格計算コードです。あなたの仕事は 2 段階です。

  演習1（★★☆）リファクタリング:
      振る舞いを変えずに、読みやすく変更しやすい設計に直す。
      test_pricing.py の「特性テスト」（TestCharacterization で始まるクラス）を
      常に緑に保ったまま、小さな手順で進めること。
  演習2（★★★）機能追加:
      下の「新しい要件（v2）」を実装し、「新機能テスト」（TestNewFeature で始まるクラス）を通す。

Kent Beck の言葉にならい、「まず変更を容易にし（これが難しいかもしれない）、
それから容易な変更をする」という順で進めてください。先にこのままの形で機能を足してみて、
どこがつらいかを体験してから元に戻す、というのも良い学び方です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.1          # 最初は特性テストだけが通り、新機能テストは失敗する
    python3 tools/check.py -v 8.1       # 失敗理由を詳しく見る

演習3の design_smells.py を実装したら、リファクタリングの前後で
    python3 design_smells.py pricing.py      （exercises/ ディレクトリで実行）
を実行して、指標がどう変わるかを確かめてみましょう。

-----------------------------------------------------------------------------
現在の仕様（v1）
-----------------------------------------------------------------------------
calculate_total(cart, customer, coupon_code=None) -> dict

  cart     : 明細（dict）のリスト。各明細は
             {"sku": str, "category": "book" | "food" | "goods",
              "unit_price": int（税抜・円、0 以上）, "qty": int（1 以上）}
  customer : {"tier": "regular" | "silver" | "gold"}
  coupon_code : None, "WELCOME10", "GOODS500" のいずれか

  1. 小計（subtotal）= 各明細の unit_price × qty の合計（税抜）
  2. 会員ランク割引: book 以外の明細に silver 5%、gold 10%（明細ごとに 1 円未満切り捨て）。
     書籍は定価販売のため割り引かない（日本の再販売価格維持制度を模した、この店のルール）。
  3. クーポン
     - WELCOME10: regular 会員専用。book 以外の明細に 10%（明細ごとに切り捨て）。
       regular 以外の会員が使うと ValueError。
     - GOODS500 : goods 明細の割引後の合計が 3,000 円以上なら 500 円引き
       （10% 課税対象から差し引く）。条件を満たさなければ ValueError。
     - それ以外のコードは ValueError。
  4. 送料: 500 円（税抜）。gold 会員は無料。割引後の商品合計（税抜）が 5,000 円以上なら無料。
  5. 消費税: food は 8%、book・goods・送料は 10%。
     税率ごとに対象額を合計してから、1 回だけ切り捨てる。
  6. total = subtotal - discount + shipping + tax

  戻り値: {"subtotal": int, "discount": int, "shipping": int, "tax": int,
           "tax_by_rate": {8: int, 10: int}, "total": int}
  カートが空、明細の値が不正、未知のカテゴリ・会員ランク・クーポンは ValueError。

  注意: 仕様書は現実のコードより古いことがあります。特性テストは「仕様」ではなく
  「現在の振る舞い」を固定するものです。仕様に書かれていない振る舞いも守ってください。
  （変えたい振る舞いを見つけたら、リファクタリングとは別の変更として扱うこと）

-----------------------------------------------------------------------------
新しい要件（v2）— 演習2で実装する
-----------------------------------------------------------------------------
  N1. 新しい会員ランク "platinum" を追加する。
      - book 以外の明細に 15% の会員割引
      - 送料は常に無料
      - WELCOME10 は使えない（silver・gold と同じ扱い）
  N2. 期間限定キャンペーン「秋の食品フェア」を追加する。
      - 期間: 日本時間 2026-10-01 00:00 から、日本時間 2026-11-01 00:00 の直前まで
      - 期間中は food の明細に 5% の割引を追加する
      - 1 つの明細に複数の割引率がかかるときは、率を合計してから明細の金額に掛け、
        1 回だけ切り捨てる（例: gold 会員の food 明細 999 円 → 10% + 5% = 15% → 149 円引き）
      - 現在時刻は、キーワード専用引数 clock（引数なしで呼ぶと timezone 付きの datetime を
        返す関数）から得る。clock を省略したときはシステム時計（UTC の現在時刻）を使う。
      - clock が timezone なし（naive）の datetime を返したら ValueError

  v2 のシグネチャ: calculate_total(cart, customer, coupon_code=None, *, clock=None)
"""
from datetime import datetime  # noqa: F401  （使われていない import も「におい」の一つ）


def calculate_total(cart, customer, coupon_code=None):
    # 合計を計算する
    if len(cart) == 0:
        raise ValueError("カートが空です")
    tier = customer.get("tier")
    if tier != "regular" and tier != "silver" and tier != "gold":
        raise ValueError(f"不明な会員ランクです: {tier!r}")
    t = 0  # 小計
    d = 0  # 割引
    a8 = 0  # 8%
    a10 = 0  # 10%
    g = 0
    for it in cart:
        c = it.get("category")
        p = it.get("unit_price")
        q = it.get("qty")
        if not isinstance(p, int) or p < 0:
            raise ValueError(f"単価が不正です: {it!r}")
        if not isinstance(q, int) or q < 1:
            raise ValueError(f"数量が不正です: {it!r}")
        amt = p * q
        t = t + amt
        if c == "book":
            # 書籍
            a10 = a10 + amt
        elif c == "food" or c == "goods":
            x = 0
            if tier == "silver":
                x = amt * 5 // 100
            elif tier == "gold":
                x = amt * 10 // 100
            if coupon_code == "WELCOME10":
                if tier == "regular":
                    x = x + amt * 10 // 100
                else:
                    raise ValueError("WELCOME10 は一般会員（regular）のみ使えます")
            d = d + x
            if c == "food":
                a8 = a8 + amt - x
            else:
                a10 = a10 + amt - x
                g = g + amt - x
        else:
            raise ValueError(f"不明なカテゴリです: {c!r}")
    if coupon_code is not None and coupon_code != "WELCOME10":
        if coupon_code == "GOODS500":
            if g >= 3000:
                d = d + 500
                a10 = a10 - 500
            else:
                raise ValueError("GOODS500 は雑貨の合計が 3,000 円以上のときに使えます")
        else:
            raise ValueError(f"不明なクーポンです: {coupon_code!r}")
    # 送料は全国一律 600 円（税抜）
    s = 500
    if tier == "gold":
        s = 0
    if t - d >= 5000:
        s = 0
    a10 = a10 + s
    tx8 = a8 * 8 // 100
    tx10 = a10 * 10 // 100
    return {
        "subtotal": t,
        "discount": d,
        "shipping": s,
        "tax": tx8 + tx10,
        "tax_by_rate": {8: tx8, 10: tx10},
        "total": t - d + s + tx8 + tx10,
    }
