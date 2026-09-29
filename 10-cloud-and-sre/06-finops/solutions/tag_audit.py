"""10.6 クラウドコスト管理（FinOps）— 演習（タグの監査と未配賦の費用）の解答例

演習の仕様は exercises/tag_audit.py の docstring を参照してください。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Mapping, Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

UNALLOCATED = "(未配賦)"


@dataclass(frozen=True)
class Resource:
    id: str
    type: str
    monthly_cost: int                          # 円
    tags: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TagPolicy:
    # タグのキー → 許される値の集合（None なら空でない任意の値）
    required: Mapping[str, frozenset[str] | None]


# 架空の組織のタグ規約の例
EXAMPLE_POLICY = TagPolicy({
    "team": None,
    "env": frozenset({"prod", "stg", "dev"}),
    "cost-center": frozenset({"CC-100", "CC-200", "CC-300"}),
})


# ===========================================================================
# 演習6: タグの監査
# ===========================================================================

def check_resource(resource: Resource, policy: TagPolicy) -> list[str]:
    problems = []
    for key in sorted(policy.required):
        allowed = policy.required[key]
        value = resource.tags.get(key)
        if value is None or not value.strip():
            # タグのキーは大文字・小文字を区別する。表記ゆれ（Team と team）は修正の手がかりとして示す
            near = sorted(k for k in resource.tags if k.lower() == key.lower() and k != key)
            problems.append(f"missing:{key}" + (f" (found {near[0]})" if near else ""))
        elif allowed is not None and value not in allowed:
            problems.append(f"invalid:{key}={value}")
    return problems


def audit(resources: Sequence[Resource], policy: TagPolicy) -> dict[str, list[str]]:
    report = {}
    for r in resources:
        problems = check_resource(r, policy)
        if problems:
            report[r.id] = problems
    return report


def cost_report(resources: Sequence[Resource], policy: TagPolicy, group_by: str = "team") -> dict[str, object]:
    if group_by not in policy.required:
        raise ValueError(f"group_by は規約の必須タグのどれか: {group_by!r}")
    total = sum(r.monthly_cost for r in resources)
    compliant = [r for r in resources if not check_resource(r, policy)]
    compliant_ids = {r.id for r in compliant}
    compliant_cost = sum(r.monthly_cost for r in compliant)
    by_group: dict[str, int] = defaultdict(int)
    for r in resources:
        # 規約を満たすリソースだけを、タグの値で配賦する。それ以外は「未配賦」に集める
        key = r.tags[group_by] if r.id in compliant_ids else UNALLOCATED
        by_group[key] += r.monthly_cost
    return {
        "total": total,
        "compliant_cost": compliant_cost,
        "compliance_by_count": len(compliant) / len(resources) if resources else 1.0,
        "compliance_by_cost": compliant_cost / total if total else 1.0,
        "by_group": dict(sorted(by_group.items(), key=lambda kv: (-kv[1], kv[0]))),
    }
