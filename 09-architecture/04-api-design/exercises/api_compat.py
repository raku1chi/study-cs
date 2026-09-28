"""9.4 API設計 — 演習4: API スキーマの後方互換性の検査（破壊的変更の検出）

公開した API は、利用者のコードがそれに依存した瞬間から「契約」になります。
新しいバージョンのスキーマが古いクライアントを壊さないか（後方互換性）を、CI で自動的に
判定できれば、うっかり破壊的変更をリリースする事故を防げます（9.1 の適応度関数の一種です）。

この演習では、OpenAPI を大幅に簡略化した次の形式のスキーマを 2 つ比べ、変更を分類します。

    {
      "endpoints": {
        "POST /orders": {
          "request":  {"フィールド名": フィールド定義, ...},   # 省略可（本文なし）
          "response": {"フィールド名": フィールド定義, ...}    # 省略可
        },
        ...
      }
    }

    フィールド定義: {"type": "string" | "integer" | "number" | "boolean" | "object" | "array",
                     "required": 真偽値（省略時 False）,
                     "enum": [許される値, ...]（string・integer・number のみ、省略可）,
                     "fields": {...}（object のとき必須）,
                     "items": フィールド定義（array のとき必須。要素には required を書かない）}

最大のポイントは **データの流れる向きで互換性の判定が逆になる** ことです。
リクエスト（クライアント → サーバー）はサーバーが「受け取る」側、レスポンス（サーバー → クライアント）は
クライアントが「受け取る」側です。受け取る側が壊れるかどうかで考えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.4
"""
from __future__ import annotations

from dataclasses import dataclass, field

TYPES = {"string", "integer", "number", "boolean", "object", "array"}
ENUM_TYPES = {"string", "integer", "number"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
FIELD_KEYS = {"type", "required", "enum", "fields", "items"}


@dataclass(frozen=True, order=True)
class Change:
    """変更 1 件。

    - endpoint: "POST /orders" など
    - location: "endpoint"（エンドポイント自体の追加・削除）/ "request" / "response"
    - path: フィールドの位置。トップレベルは "coupon"、オブジェクトの中は "shipping.method"、
      配列の要素は "items[]"、配列の要素のオブジェクトの中は "items[].sku"。エンドポイント単位の変更は ""
    - kind: 変更の種類（下の表）
    - breaking: 古いクライアントを壊しうるなら True
    - message: 人が読む説明（比較には使わない）
    """

    endpoint: str
    location: str
    path: str
    kind: str
    breaking: bool = field(compare=False)
    message: str = field(compare=False)


# ---------------------------------------------------------------------------
# 実装済み: スキーマの形式の検証とレポートの整形
# ---------------------------------------------------------------------------

def validate_schema(schema: dict) -> None:
    """スキーマの形式を検査し、不正なら ValueError を送出する。"""
    if not isinstance(schema, dict) or not isinstance(schema.get("endpoints"), dict):
        raise ValueError("スキーマには endpoints（辞書）が必要です")
    for ep, spec in schema["endpoints"].items():
        method, _, path = ep.partition(" ")
        if method not in METHODS or not path.startswith("/"):
            raise ValueError(f"エンドポイントは 'METHOD /path' の形式です: {ep!r}")
        if not isinstance(spec, dict) or set(spec) - {"request", "response"}:
            raise ValueError(f"{ep}: 使えるキーは request と response だけです")
        for loc in ("request", "response"):
            if loc in spec:
                _validate_fields(spec[loc], f"{ep} {loc}")


def _validate_fields(fields: dict, where: str) -> None:
    if not isinstance(fields, dict):
        raise ValueError(f"{where}: フィールドの定義は辞書です")
    for name, spec in fields.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"{where}: フィールド名が不正です: {name!r}")
        _validate_field(spec, f"{where} {name}", allow_required=True)


def _validate_field(spec: dict, where: str, allow_required: bool) -> None:
    if not isinstance(spec, dict):
        raise ValueError(f"{where}: フィールドの定義は辞書です")
    unknown = set(spec) - FIELD_KEYS
    if unknown:
        raise ValueError(f"{where}: 未知のキー {sorted(unknown)}")
    t = spec.get("type")
    if t not in TYPES:
        raise ValueError(f"{where}: 未知の型 {t!r}")
    if "required" in spec and (not allow_required or not isinstance(spec["required"], bool)):
        raise ValueError(f"{where}: required は（配列の要素以外で）真偽値を指定します")
    if "enum" in spec:
        values = spec["enum"]
        if t not in ENUM_TYPES or not isinstance(values, list) or not values or len(set(values)) != len(values):
            raise ValueError(f"{where}: enum は文字列・数値の型に、重複のない空でないリストで指定します")
    if (t == "object") != ("fields" in spec):
        raise ValueError(f"{where}: fields は object 型にだけ、必ず指定します")
    if (t == "array") != ("items" in spec):
        raise ValueError(f"{where}: items は array 型にだけ、必ず指定します")
    if t == "object":
        _validate_fields(spec["fields"], where)
    if t == "array":
        _validate_field(spec["items"], where + "[]", allow_required=False)


def format_report(changes: list[Change]) -> str:
    """変更の一覧を、CI のログに出せる複数行の文字列にする。"""
    lines = []
    for c in changes:
        where = c.location if not c.path else f"{c.location} {c.path}"
        lines.append(f"[{'破壊的' if c.breaking else '互換'}] {c.endpoint} {where}: {c.message}")
    n_breaking = sum(c.breaking for c in changes)
    lines.append(f"破壊的な変更 {n_breaking} 件 / 互換な変更 {len(changes) - n_breaking} 件")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 演習4（★★★）: 差分と互換性の判定
# ---------------------------------------------------------------------------

def diff_schemas(old: dict, new: dict) -> list[Change]:
    """2 つのスキーマの差分を、Change のソート済みリストで返す（変更がなければ空）。

    まず validate_schema で両方を検査する（不正なら ValueError）。
    request / response が省略されているエンドポイントは、フィールドが 0 個として比較する。

    | kind                | 意味                           | request で破壊的か | response で破壊的か |
    |---------------------|--------------------------------|--------------------|---------------------|
    | endpoint-removed    | エンドポイントの削除           | （location は endpoint。常に破壊的） |
    | endpoint-added      | エンドポイントの追加           | （location は endpoint。常に互換）   |
    | field-removed       | フィールドの削除               | はい               | はい                |
    | field-added         | フィールドの追加               | 必須なら はい      | いいえ              |
    | type-changed        | 型の変更（下の注を参照）       | はい               | はい                |
    | made-required       | 任意 → 必須                    | はい               | いいえ              |
    | made-optional       | 必須 → 任意                    | いいえ             | はい                |
    | enum-values-added   | enum に値が増えた              | いいえ             | はい                |
    | enum-values-removed | enum から値が減った            | はい               | いいえ              |
    | enum-added          | enum の制限が新たに付いた      | はい               | いいえ              |
    | enum-removed        | enum の制限がなくなった        | いいえ             | はい                |

    - 型の変更の例外: integer → number（広げる）は request では互換・response では破壊的。
      number → integer（狭める）は request では破壊的・response では互換。それ以外の型の変更は常に破壊的。
    - 型が変わったフィールドは、それ以上（required・enum・中身）を比較しない。
    - 同じフィールドで required と enum の両方が変わったら、両方の Change を出す。
      enum に値が増えも減りもしたら、enum-values-added と enum-values-removed の両方を出す。
    - object は fields の中を、array は items を再帰的に比較する（パスの書き方は Change を参照）。
    - 結果は sorted() で並べる（Change は endpoint, location, path, kind の順で比較される）。
    """
    raise NotImplementedError("演習4: diff_schemas を実装してください")


def is_backward_compatible(old: dict, new: dict) -> bool:
    """破壊的な変更が 1 つもなければ True。"""
    raise NotImplementedError("演習4: is_backward_compatible を実装してください")
