"""10.6 クラウドコスト管理（FinOps）— 演習: タグの監査と未配賦の費用

費用を「誰の・どのサービスの・どの環境の」ものか分けて見るには、リソースへのタグ付けが
欠かせません。タグの規約への準拠をチェックし、規約を満たさない（配賦できない）費用が
どれだけあるかを報告します。

- 演習6（★☆☆）: check_resource, audit, cost_report
（演習1〜5 は cloudcost.py にあります）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.6
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
# 演習6（★☆☆）: タグの監査
# ===========================================================================

def check_resource(resource: Resource, policy: TagPolicy) -> list[str]:
    """1 つのリソースの規約違反を、規約のキーの昇順で返す（違反がなければ空リスト）。

    - キーがない、または値が空白だけ: "missing:{キー}"。
      大文字・小文字だけが違うキーがあれば（例: "Team"）、修正の手がかりとして
      "missing:team (found Team)" のように付け加える（タグのキーは大文字・小文字を区別する）。
    - 値が許される値の集合にない: "invalid:{キー}={値}"（集合が None なら空でない任意の値でよい）。
    - 規約にないタグが付いていても問題にしない。
    """
    raise NotImplementedError("演習6: check_resource を実装してください")


def audit(resources: Sequence[Resource], policy: TagPolicy) -> dict[str, list[str]]:
    """違反のあるリソースだけを {リソース ID: check_resource の結果} で返す。"""
    raise NotImplementedError("演習6: audit を実装してください")


def cost_report(resources: Sequence[Resource], policy: TagPolicy, group_by: str = "team") -> dict[str, object]:
    """タグ付けの状況と、配賦できた・できなかった費用の報告を返す。

    返り値の dict:
    - "total": 全リソースの月額の合計
    - "compliant_cost": 規約を満たすリソースの月額の合計
    - "compliance_by_count": 規約を満たすリソースの数の割合（リソースがなければ 1.0）
    - "compliance_by_cost": 規約を満たすリソースの金額の割合（合計が 0 なら 1.0）
    - "by_group": 規約を満たすリソースは tags[group_by] の値ごとに、満たさないものは UNALLOCATED に集計した
      {グループ: 金額}。金額の降順、同じならグループ名の昇順に並べる。
    group_by が規約の必須タグでなければ ValueError。

    数の割合と金額の割合が大きく違うことがある（高価なリソースほどタグが漏れていると、金額の割合が下がる）。
    FinOps で追うべきは金額の割合。
    """
    raise NotImplementedError("演習6: cost_report を実装してください")
