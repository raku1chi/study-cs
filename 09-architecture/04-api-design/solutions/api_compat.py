"""9.4 API設計 — 解答例: API スキーマの後方互換性の検査

演習の仕様は exercises/api_compat.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass, field

TYPES = {"string", "integer", "number", "boolean", "object", "array"}
ENUM_TYPES = {"string", "integer", "number"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
FIELD_KEYS = {"type", "required", "enum", "fields", "items"}


@dataclass(frozen=True, order=True)
class Change:
    endpoint: str
    location: str
    path: str
    kind: str
    breaking: bool = field(compare=False)
    message: str = field(compare=False)


# ---------------------------------------------------------------------------
# スキーマの検証
# ---------------------------------------------------------------------------

def validate_schema(schema: dict) -> None:
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


# ---------------------------------------------------------------------------
# 差分と互換性の判定
# ---------------------------------------------------------------------------

LOCATION_JA = {"request": "リクエスト", "response": "レスポンス"}


def diff_schemas(old: dict, new: dict) -> list[Change]:
    validate_schema(old)
    validate_schema(new)
    out: list[Change] = []
    old_eps, new_eps = old["endpoints"], new["endpoints"]
    for ep in sorted(set(old_eps) | set(new_eps)):
        if ep not in new_eps:
            out.append(Change(ep, "endpoint", "", "endpoint-removed", True,
                              "エンドポイントが削除された（呼び出している利用者が壊れる）"))
        elif ep not in old_eps:
            out.append(Change(ep, "endpoint", "", "endpoint-added", False, "エンドポイントが追加された"))
        else:
            for loc in ("request", "response"):
                _diff_fields(ep, loc, old_eps[ep].get(loc, {}), new_eps[ep].get(loc, {}), "", out)
    return sorted(out)


def _diff_fields(ep: str, loc: str, old: dict, new: dict, prefix: str, out: list[Change]) -> None:
    ja = LOCATION_JA[loc]
    for name in sorted(set(old) | set(new)):
        path = prefix + name
        if name not in new:
            out.append(Change(ep, loc, path, "field-removed", True,
                              f"{ja}のフィールドが削除された" + (
                                  "（送ってくるクライアントが拒否されるか、値が黙って無視される）"
                                  if loc == "request" else "（読んでいるクライアントが壊れる）")))
        elif name not in old:
            required = new[name].get("required", False)
            if loc == "request" and required:
                out.append(Change(ep, loc, path, "field-added", True,
                                  "リクエストに必須フィールドが追加された（古いクライアントは送らない）"))
            elif loc == "request":
                out.append(Change(ep, loc, path, "field-added", False, "リクエストに任意のフィールドが追加された"))
            else:
                out.append(Change(ep, loc, path, "field-added", False,
                                  "レスポンスにフィールドが追加された（寛容な読み手は無視できる）"))
        else:
            _diff_field(ep, loc, old[name], new[name], path, out)


def _diff_field(ep: str, loc: str, old: dict, new: dict, path: str, out: list[Change]) -> None:
    request = loc == "request"
    ot, nt = old["type"], new["type"]
    if ot != nt:
        if {ot, nt} == {"integer", "number"}:
            # 型の広げ・狭めは、データの流れる向きで互換性が逆になる（入力は広げてよい、出力は狭めてよい）
            widened = ot == "integer"
            breaking = (not widened) if request else widened
            out.append(Change(ep, loc, path, "type-changed", breaking,
                              f"型が {ot} から {nt} に変わった（{'広げた' if widened else '狭めた'}）"))
        else:
            out.append(Change(ep, loc, path, "type-changed", True, f"型が {ot} から {nt} に変わった"))
        return  # 型が変わったら、中身の比較には意味がない

    old_req, new_req = old.get("required", False), new.get("required", False)
    if not old_req and new_req:
        out.append(Change(ep, loc, path, "made-required", request,
                          "任意から必須に変わった" + ("（古いクライアントは送らないことがある）" if request else "")))
    elif old_req and not new_req:
        out.append(Change(ep, loc, path, "made-optional", not request,
                          "必須から任意に変わった" + ("" if request else "（常にあると期待するクライアントが壊れる）")))

    old_enum, new_enum = old.get("enum"), new.get("enum")
    if old_enum is None and new_enum is not None:
        out.append(Change(ep, loc, path, "enum-added", request, f"値が {new_enum} に制限された"))
    elif old_enum is not None and new_enum is None:
        out.append(Change(ep, loc, path, "enum-removed", not request, "値の制限（enum）がなくなった"))
    elif old_enum is not None and new_enum is not None:
        added = [v for v in new_enum if v not in old_enum]
        removed = [v for v in old_enum if v not in new_enum]
        if added:
            # レスポンスの enum に値が増えると、全パターンを網羅して分岐しているクライアントが壊れる
            out.append(Change(ep, loc, path, "enum-values-added", not request, f"enum に {added} が追加された"))
        if removed:
            # リクエストの enum から値が減ると、その値を送っているクライアントが拒否される
            out.append(Change(ep, loc, path, "enum-values-removed", request, f"enum から {removed} が削除された"))

    if ot == "object":
        _diff_fields(ep, loc, old["fields"], new["fields"], path + ".", out)
    elif ot == "array":
        _diff_field(ep, loc, old["items"], new["items"], path + "[]", out)


def is_backward_compatible(old: dict, new: dict) -> bool:
    return not any(c.breaking for c in diff_schemas(old, new))


def format_report(changes: list[Change]) -> str:
    lines = []
    for c in changes:
        where = c.location if not c.path else f"{c.location} {c.path}"
        lines.append(f"[{'破壊的' if c.breaking else '互換'}] {c.endpoint} {where}: {c.message}")
    n_breaking = sum(c.breaking for c in changes)
    lines.append(f"破壊的な変更 {n_breaking} 件 / 互換な変更 {len(changes) - n_breaking} 件")
    return "\n".join(lines)
