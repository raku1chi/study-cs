"""8.4 CI/CDとリリースエンジニアリング — 演習1: フィーチャーフラグの評価エンジン

フィーチャーフラグは「デプロイ（コードを本番に置く）」と「リリース（利用者に機能を見せる）」を
切り離す仕組みです。この演習では、フラグの設定（JSON で表せる dict）と利用者の属性（コンテキスト）
から、どの変種（variant）を返すかを決める評価エンジンを作ります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.4

フラグの設定の形式（例）:

    FLAGS = {
        "new-checkout": {
            "enabled": True,                          # False ならキルスイッチ: 常に off_variant
            "variants": {"on": True, "off": False},   # 変種の名前 → 返す値（任意の値）
            "off_variant": "off",
            "prerequisites": [{"flag": "new-cart", "variant": "on"}],   # 省略可
            "rules": [                                                  # 省略可。上から順に評価
                {"clauses": [{"attribute": "email", "op": "ends_with", "values": ["@example.com"]}],
                 "serve": {"variant": "on"}},
                {"clauses": [{"attribute": "country", "op": "in", "values": ["JP"]},
                             {"attribute": "plan", "op": "in", "values": ["pro", "enterprise"]}],
                 "serve": {"rollout": [["on", 50], ["off", 50]], "bucket_by": "org_id"}},
            ],
            "default": {"rollout": [["on", 10], ["off", 90]]},        # どのルールにも当たらないとき
        },
    }

評価の手順（evaluate）:
    1. フラグが存在しない、または設定が不正 → 理由 "ERROR"（呼び出し側の default を返す）
    2. enabled が False → off_variant を返す（理由 "OFF"）
    3. 前提条件（prerequisites）: 各前提フラグを同じコンテキストで評価し、変種が指定と違えば
       off_variant を返す（理由 "PREREQUISITE_FAILED"）。前提フラグが存在しない・OFF の場合も同じ。
       前提条件が循環していたら設定の誤りなので "ERROR"。
    4. rules を上から順に評価し、すべての clause が成り立つ最初のルールの serve を返す
       （理由 "RULE_MATCH"、rule_index にルールの番号）
    5. どれにも当たらなければ default の serve を返す（理由 "DEFAULT"）

serve の形式:
    {"variant": "on"}                                  → その変種
    {"rollout": [["on", 20], ["off", 80]], "bucket_by": "user_id"}
        → 割合での出し分け。重みは 0 以上の整数で、合計が 100 でなければ "ERROR"。
          bucket_by は省略時 "user_id"。コンテキストにその属性がなければ "ERROR"。
          bucket(フラグのキー, str(属性値)) が 0〜9999 のどこに入るかで変種を選ぶ:
          先頭の変種から順に、累積の重み × 100 未満なら、その変種。
          例: [["on", 20], ["off", 80]] なら、バケット 0〜1999 が on、2000〜9999 が off。

clause の形式: {"attribute": 属性名, "op": 演算子, "values": [値, ...]}
    - コンテキストに属性がなければ、その clause は **成り立たない**（not_in でも）。
    - "in" / "not_in"            : 属性値が values に含まれる / 含まれない
    - "starts_with" / "ends_with" / "contains": 属性値（str）が values のどれかで始まる / 終わる / を含む
    - "lt" / "lte" / "gt" / "gte": 属性値（数値）と values[0]（数値）の比較。bool は数値として扱わない
    - 型が合わない（文字列の演算子に数値など）ときは、成り立たないとする
    - 未知の演算子は設定の誤りなので "ERROR"

大原則: evaluate は **決して例外を送出しない**。フラグの評価の失敗でアプリケーションを落とすと、
        フラグが障害の原因になってしまうからです。設定がどれほど壊れていても、"ERROR" と
        呼び出し側の default を返してください。
"""
from __future__ import annotations

import hashlib  # noqa: F401  実装で使います
from dataclasses import dataclass
from typing import Any, Optional

BUCKETS = 10_000


@dataclass(frozen=True)
class Evaluation:
    """フラグの評価結果。"""

    value: Any  # 返す値（variants[variant]、ERROR のときは呼び出し側の default）
    variant: Optional[str]  # 選ばれた変種の名前（ERROR のときは None）
    reason: str  # "OFF" / "PREREQUISITE_FAILED" / "RULE_MATCH" / "DEFAULT" / "ERROR"
    rule_index: Optional[int] = None  # RULE_MATCH のとき、当たったルールの番号（0 始まり）
    error: Optional[str] = None  # ERROR のとき、原因の説明


def bucket(flag_key: str, key: str) -> int:
    """(フラグのキー, 利用者などのキー) から、0〜9999 の安定したバケット番号を計算する。

    sha256(f"{flag_key}:{key}" を UTF-8 にしたもの) の先頭 8 バイトをビッグエンディアンの
    符号なし整数として読み、10,000 で割った余りを返す。

    - 同じ入力なら、いつ・どのサーバーで計算しても同じ値になる（利用者の体験が揺れない）。
    - flag_key を混ぜるので、フラグが違えば同じ利用者でも別のバケットになる
      （「どの実験でも同じ 10% の利用者が対象になる」偏りを防ぐ）。
    """
    raise NotImplementedError("演習1: bucket を実装してください")


def evaluate(flags: dict, flag_key: str, context: dict, default: Any = None) -> Evaluation:
    """flags の中の flag_key を、context（利用者の属性の dict）で評価する。手順はモジュールの docstring を参照。

    ヒント: 前提条件の再帰的な評価と循環の検出のために、「評価中のフラグのキーの集合」を
            引数に持つ内部関数を作ると書きやすい。設定の誤りは内部で例外にして、
            evaluate の一番外側でまとめて Evaluation(default, None, "ERROR", error=...) に変換するとよい。
    """
    raise NotImplementedError("演習1: evaluate を実装してください")
