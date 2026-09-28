"""8.4 CI/CDとリリースエンジニアリング — 解答例: フィーチャーフラグの評価エンジン

仕様は exercises/flags.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from numbers import Real
from typing import Any, Optional

BUCKETS = 10_000


@dataclass(frozen=True)
class Evaluation:
    value: Any
    variant: Optional[str]
    reason: str
    rule_index: Optional[int] = None
    error: Optional[str] = None


class FlagConfigError(Exception):
    """フラグの設定・コンテキストの誤り。evaluate の外には出さない。"""


def bucket(flag_key: str, key: str) -> int:
    digest = hashlib.sha256(f"{flag_key}:{key}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % BUCKETS


def evaluate(flags: dict, flag_key: str, context: dict, default: Any = None) -> Evaluation:
    try:
        return _evaluate(flags, flag_key, context, visiting=frozenset())
    except Exception as exc:  # 設定がどれほど壊れていても、アプリケーションは落とさない
        return Evaluation(default, None, "ERROR", error=f"{type(exc).__name__}: {exc}")


def _evaluate(flags: dict, flag_key: str, context: dict, visiting: frozenset) -> Evaluation:
    if flag_key in visiting:
        raise FlagConfigError(f"前提条件が循環しています: {sorted(visiting | {flag_key})}")
    if flag_key not in flags:
        raise FlagConfigError(f"フラグがありません: {flag_key!r}")
    flag = flags[flag_key]
    variants = flag["variants"]

    def serve_variant(name: str, reason: str, rule_index: Optional[int] = None) -> Evaluation:
        if name not in variants:
            raise FlagConfigError(f"{flag_key}: 未定義の変種です: {name!r}")
        return Evaluation(variants[name], name, reason, rule_index)

    # 1. キルスイッチ
    if not flag["enabled"]:
        return serve_variant(flag["off_variant"], "OFF")

    # 2. 前提条件（循環を検出するため、評価中のキーを渡していく）
    for prerequisite in flag.get("prerequisites", []):
        if prerequisite["flag"] not in flags:
            return serve_variant(flag["off_variant"], "PREREQUISITE_FAILED")  # 前提フラグがない
        result = _evaluate(flags, prerequisite["flag"], context, visiting | {flag_key})
        if result.variant != prerequisite["variant"]:
            return serve_variant(flag["off_variant"], "PREREQUISITE_FAILED")

    # 3. ルール（上から順に、最初に当たったもの）
    for index, rule in enumerate(flag.get("rules", [])):
        if all(_clause_matches(clause, context) for clause in rule["clauses"]):
            return serve_variant(_serve(flag_key, rule["serve"], context), "RULE_MATCH", index)

    # 4. 既定
    return serve_variant(_serve(flag_key, flag["default"], context), "DEFAULT")


def _serve(flag_key: str, serve: dict, context: dict) -> str:
    if "variant" in serve:
        return serve["variant"]
    rollout = serve["rollout"]
    weights = [weight for _, weight in rollout]
    if any(not isinstance(w, int) or isinstance(w, bool) or w < 0 for w in weights) or sum(weights) != 100:
        raise FlagConfigError(f"{flag_key}: 重みは 0 以上の整数で、合計 100 にしてください: {rollout}")
    attribute = serve.get("bucket_by", "user_id")
    if attribute not in context:
        raise FlagConfigError(f"{flag_key}: コンテキストに {attribute!r} がないので割合を決められません")
    b = bucket(flag_key, str(context[attribute]))
    cumulative = 0
    for variant, weight in rollout:
        cumulative += weight * (BUCKETS // 100)
        if b < cumulative:
            return variant
    raise AssertionError("unreachable: 重みの合計は 100")


STRING_OPS = {
    "starts_with": str.startswith,
    "ends_with": str.endswith,
    "contains": lambda value, part: part in value,
}
NUMBER_OPS = {
    "lt": lambda a, b: a < b,
    "lte": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "gte": lambda a, b: a >= b,
}


def _is_number(x: object) -> bool:
    return isinstance(x, Real) and not isinstance(x, bool)


def _clause_matches(clause: dict, context: dict) -> bool:
    op, values = clause["op"], clause["values"]
    if op not in ("in", "not_in") and op not in STRING_OPS and op not in NUMBER_OPS:
        raise FlagConfigError(f"未知の演算子です: {op!r}")
    if clause["attribute"] not in context:
        return False  # 属性がなければ、否定の演算子でも成り立たない
    value = context[clause["attribute"]]
    if op == "in":
        return value in values
    if op == "not_in":
        return value not in values
    if op in STRING_OPS:
        return isinstance(value, str) and any(isinstance(v, str) and STRING_OPS[op](value, v) for v in values)
    target = values[0]
    return _is_number(value) and _is_number(target) and NUMBER_OPS[op](value, target)
