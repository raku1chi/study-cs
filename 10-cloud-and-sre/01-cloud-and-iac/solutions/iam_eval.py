"""10.1 クラウドコンピューティングとIaC — 演習（IAM ポリシー評価器）の解答例

演習の仕様は exercises/iam_eval.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

Policy = Mapping[str, Any]


@dataclass(frozen=True)
class Request:
    """評価したいリクエスト（誰が、を除いた「何を・どれに・どんな状況で」）。

    - action: "s3:GetObject" のような「サービス:操作」
    - resource: "arn:aws:s3:::acme-reports/2026/q1.csv" のような ARN
    - context: 条件キーの値。例 {"aws:SourceIp": "203.0.113.5", "aws:MultiFactorAuthPresent": True}
    """

    action: str
    resource: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    """評価結果。

    - allowed: 許可されたか
    - reason: "allowed" / "explicit_deny" / "scp" / "implicit_deny" / "boundary" のいずれか
    - matched: 判断の根拠になったステートメントの Sid（Sid がなければ空文字列）。
      allowed のときは当てはまった Allow の Sid、explicit_deny のときは当てはまった Deny の Sid。
      それ以外（何も当てはまらなかった）は空のタプル。
    """

    allowed: bool
    reason: str
    matched: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 演習1: ワイルドカード照合
# ---------------------------------------------------------------------------

def wildcard_match(pattern: str, value: str, *, ignore_case: bool = False) -> bool:
    if ignore_case:
        pattern, value = pattern.lower(), value.lower()
    p = v = 0
    star_p = -1  # 直近に見た * の位置（-1 = まだない）
    star_v = 0   # その * が value のどこまでを「食べた」ことにしているか
    while v < len(value):
        if p < len(pattern) and pattern[p] == "*":
            # * はまず 0 文字にマッチさせてみる。失敗したら後で 1 文字ずつ延ばす
            star_p, star_v = p, v
            p += 1
        elif p < len(pattern) and (pattern[p] == "?" or pattern[p] == value[v]):
            p += 1
            v += 1
        elif star_p >= 0:
            # 行き詰まった: 直前の * にもう 1 文字多く食べさせてやり直す。
            # 戻るのは「直前の * 」だけでよいので、最悪でも O(len(pattern) × len(value))。
            # 素朴な再帰（* ごとに全分岐を試す）は指数時間になりうる。
            star_v += 1
            p, v = star_p + 1, star_v
        else:
            return False
    # value を使い切った。残りのパターンが * だけならマッチ
    while p < len(pattern) and pattern[p] == "*":
        p += 1
    return p == len(pattern)


# ---------------------------------------------------------------------------
# 演習2: 条件とポリシーの評価
# ---------------------------------------------------------------------------

def _as_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).lower()
    if s not in ("true", "false"):
        raise ValueError(f"真偽値として解釈できません: {v!r}")
    return s == "true"


def _as_number(v: Any) -> float:
    if isinstance(v, bool):
        raise ValueError(f"数値として解釈できません: {v!r}")
    try:
        return float(v)
    except (TypeError, ValueError):
        raise ValueError(f"数値として解釈できません: {v!r}") from None


def _in_network(ctx: Any, cidr: Any) -> bool:
    try:
        return ipaddress.ip_address(str(ctx)) in ipaddress.ip_network(str(cidr), strict=False)
    except ValueError:
        raise ValueError(f"IP アドレス/CIDR として解釈できません: {ctx!r}, {cidr!r}") from None


# 演算子名 → (「1 つの値」に対する肯定形の判定, 否定形か)
# 否定形（Not...）は「肯定形でどの値にもマッチしない」ことを意味する。
_Test = Callable[[Any, Any], bool]
_OPERATORS: dict[str, tuple[_Test, bool]] = {}


def _register(name: str, test: _Test, negated_name: str | None = None) -> None:
    _OPERATORS[name] = (test, False)
    if negated_name:
        _OPERATORS[negated_name] = (test, True)


_register("StringEquals", lambda c, p: str(c) == str(p), "StringNotEquals")
_register(
    "StringEqualsIgnoreCase",
    lambda c, p: str(c).lower() == str(p).lower(),
    "StringNotEqualsIgnoreCase",
)
_register("StringLike", lambda c, p: wildcard_match(str(p), str(c)), "StringNotLike")
_register("NumericEquals", lambda c, p: _as_number(c) == _as_number(p), "NumericNotEquals")
_register("NumericLessThan", lambda c, p: _as_number(c) < _as_number(p))
_register("NumericLessThanEquals", lambda c, p: _as_number(c) <= _as_number(p))
_register("NumericGreaterThan", lambda c, p: _as_number(c) > _as_number(p))
_register("NumericGreaterThanEquals", lambda c, p: _as_number(c) >= _as_number(p))
_register("Bool", lambda c, p: _as_bool(c) == _as_bool(p))
_register("IpAddress", _in_network, "NotIpAddress")


def _lookup(context: Mapping[str, Any], key: str) -> tuple[bool, Any]:
    """条件キーは大文字・小文字を区別しない（aws:SourceIp と AWS:SOURCEIP は同じ）。"""
    lowered = key.lower()
    for k, v in context.items():
        if k.lower() == lowered:
            return True, v
    return False, None


def condition_matches(
    condition: Mapping[str, Mapping[str, Any]] | None,
    context: Mapping[str, Any],
) -> bool:
    if not condition:
        return True
    for op_name, keys in condition.items():
        if_exists = op_name.endswith("IfExists")
        base = op_name[: -len("IfExists")] if if_exists else op_name
        if base not in _OPERATORS:
            raise ValueError(f"未対応の条件演算子です: {op_name}")
        test, negated = _OPERATORS[base]
        # 演算子の中の複数キーは AND、1 つのキーの複数の値は OR
        for key, expected in keys.items():
            values = list(expected) if isinstance(expected, (list, tuple)) else [expected]
            present, actual = _lookup(context, key)
            if not present:
                # キーがない: ...IfExists と否定形は true、それ以外は false（AWS の規則）
                ok = if_exists or negated
            else:
                any_match = any(test(actual, v) for v in values)
                ok = not any_match if negated else any_match
            if not ok:
                return False
    return True


def _as_list(value: Any, what: str) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)) and all(isinstance(v, str) for v in value):
        return list(value)
    raise ValueError(f"{what} は文字列か文字列のリストで指定してください: {value!r}")


def _statements(policy: Policy) -> list[Mapping[str, Any]]:
    """ポリシーのステートメントを検証しながら取り出す（評価の前に不正を見つけるため）。"""
    if "Statement" not in policy:
        raise ValueError("ポリシーに Statement がありません")
    raw = policy["Statement"]
    statements = [raw] if isinstance(raw, Mapping) else list(raw)
    for st in statements:
        if st.get("Effect") not in ("Allow", "Deny"):
            raise ValueError(f"Effect は Allow か Deny です: {st.get('Effect')!r}")
        if ("Action" in st) == ("NotAction" in st):
            raise ValueError("Action と NotAction のどちらか一方だけを指定してください")
        if ("Resource" in st) == ("NotResource" in st):
            raise ValueError("Resource と NotResource のどちらか一方だけを指定してください")
    return statements


def _statement_matches(st: Mapping[str, Any], request: Request) -> bool:
    # アクション名は大文字・小文字を区別しない。NotAction は「列挙したもの以外すべて」
    if "Action" in st:
        ok = any(wildcard_match(p, request.action, ignore_case=True) for p in _as_list(st["Action"], "Action"))
    else:
        ok = not any(
            wildcard_match(p, request.action, ignore_case=True) for p in _as_list(st["NotAction"], "NotAction")
        )
    if not ok:
        return False
    # リソース（ARN）は大文字・小文字を区別する
    if "Resource" in st:
        ok = any(wildcard_match(p, request.resource) for p in _as_list(st["Resource"], "Resource"))
    else:
        ok = not any(wildcard_match(p, request.resource) for p in _as_list(st["NotResource"], "NotResource"))
    return ok and condition_matches(st.get("Condition"), request.context)


def _matches(policies: Sequence[Policy], request: Request, effect: str) -> list[str]:
    """effect のステートメントのうち、リクエストに当てはまるものの Sid を返す。"""
    sids = []
    for policy in policies:
        for st in _statements(policy):
            if st["Effect"] == effect and _statement_matches(st, request):
                sids.append(st.get("Sid", ""))
    return sids


def evaluate(
    request: Request,
    identity_policies: Sequence[Policy],
    *,
    boundary: Policy | None = None,
    scps: Sequence[Sequence[Policy]] | None = None,
) -> Decision:
    scp_levels = [list(level) for level in scps] if scps is not None else []
    everything = list(identity_policies) + ([boundary] if boundary is not None else [])
    for level in scp_levels:
        everything += level
    # 構文の不正は、評価の結果に関係なく先に見つける
    for policy in everything:
        _statements(policy)

    # 1. どこか 1 か所でも明示的な Deny が当てはまれば、それで終わり（最優先）
    denies = _matches(everything, request, "Deny")
    if denies:
        return Decision(False, "explicit_deny", tuple(denies))
    # 2. SCP は権限を「与えない」。各階層のどこかで Allow されていないと上限の外
    for level in scp_levels:
        if not _matches(level, request, "Allow"):
            return Decision(False, "scp")
    # 3. アイデンティティベースのポリシーで Allow されていなければ暗黙の拒否（既定は拒否）
    allows = _matches(list(identity_policies), request, "Allow")
    if not allows:
        return Decision(False, "implicit_deny")
    # 4. 権限境界は「上限」。境界でも Allow されていなければ拒否（有効な権限は積集合）
    if boundary is not None and not _matches([boundary], request, "Allow"):
        return Decision(False, "boundary")
    return Decision(True, "allowed", tuple(allows))
