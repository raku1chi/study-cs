"""11.3 認証と認可 — 解答例（authz）

演習の仕様は exercises/authz.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 演習1・2: RBAC（ロールの継承とテナント分離）
# ---------------------------------------------------------------------------


class RBAC:
    def __init__(self) -> None:
        self._permissions: dict[str, set[str]] = {}
        self._inherits: dict[str, set[str]] = {}  # 上位ロール → 継承する下位ロール
        self._assignments: dict[tuple[str, str], set[str]] = {}  # (利用者, テナント) → ロール

    def add_role(self, role: str, permissions: Iterable[str] = (), inherits: Iterable[str] = ()) -> None:
        if role in self._permissions:
            raise ValueError(f"ロールが重複しています: {role}")
        juniors = set(inherits)
        unknown = juniors - set(self._permissions)
        if unknown:
            raise ValueError(f"未定義のロールを継承しようとしています: {sorted(unknown)}")
        self._permissions[role] = set(permissions)
        self._inherits[role] = juniors

    def add_inheritance(self, senior: str, junior: str) -> None:
        for r in (senior, junior):
            if r not in self._permissions:
                raise ValueError(f"未定義のロールです: {r}")
        # junior から senior にたどり着けるなら、辺 senior → junior を足すと循環する
        if senior in self.effective_roles(junior):
            raise ValueError(f"継承が循環します: {senior} → {junior}")
        self._inherits[senior].add(junior)

    def effective_roles(self, role: str) -> set[str]:
        if role not in self._permissions:
            raise ValueError(f"未定義のロールです: {role}")
        seen: set[str] = set()
        stack = [role]
        while stack:  # 深さ優先探索。ひし形の継承（diamond）でも各ロールは 1 回だけ
            r = stack.pop()
            if r in seen:
                continue
            seen.add(r)
            stack.extend(self._inherits[r])
        return seen

    def assign(self, user: str, tenant: str, role: str) -> None:
        if role not in self._permissions:
            raise ValueError(f"未定義のロールです: {role}")
        self._assignments.setdefault((user, tenant), set()).add(role)

    def revoke(self, user: str, tenant: str, role: str) -> None:
        self._assignments.get((user, tenant), set()).discard(role)

    def roles_of(self, user: str, tenant: str) -> set[str]:
        roles: set[str] = set()
        # 割り当ては (利用者, テナント) の組ごと。別テナントの割り当ては一切見ない
        for r in self._assignments.get((user, tenant), set()):
            roles |= self.effective_roles(r)
        return roles

    def permissions_of(self, user: str, tenant: str) -> set[str]:
        perms: set[str] = set()
        for r in self.roles_of(user, tenant):
            perms |= self._permissions[r]
        return perms

    def is_allowed(self, user: str, tenant: str, permission: str) -> bool:
        return permission in self.permissions_of(user, tenant)


# ---------------------------------------------------------------------------
# 演習3・4: ReBAC（Zanzibar 風の関係タプル）
# ---------------------------------------------------------------------------

_OBJECT_RE = re.compile(r"[a-z][a-z0-9_]*:[A-Za-z0-9_.@-]+")
_NAME_RE = re.compile(r"[a-z][a-z0-9_]*")


@dataclass(frozen=True)
class RelationTuple:
    object: str
    relation: str
    subject: str


class ReBAC:
    def __init__(self, schema: dict[str, dict[str, dict[str, Any]]]) -> None:
        # スキーマを検証してから保持する（書き換えの影響を受けないよう、中身を複製する）
        self._schema: dict[str, dict[str, dict[str, Any]]] = {}
        for otype, relations in schema.items():
            if not _NAME_RE.fullmatch(otype):
                raise ValueError(f"型の名前が不正です: {otype!r}")
            self._schema[otype] = {}
            for rel, rule in relations.items():
                if not _NAME_RE.fullmatch(rel):
                    raise ValueError(f"関係の名前が不正です: {rel!r}")
                unknown_keys = set(rule) - {"computed_userset", "tuple_to_userset"}
                if unknown_keys:
                    raise ValueError(f"{otype}#{rel}: 未知の規則です: {sorted(unknown_keys)}")
                computed = list(rule.get("computed_userset", ()))
                ttu = [tuple(pair) for pair in rule.get("tuple_to_userset", ())]
                for other in computed:
                    if other not in relations:
                        raise ValueError(f"{otype}#{rel}: 未定義の関係を参照しています: {other}")
                for pair in ttu:
                    if len(pair) != 2 or pair[0] not in relations:
                        raise ValueError(f"{otype}#{rel}: tuple_to_userset が不正です: {pair}")
                self._schema[otype][rel] = {"computed_userset": computed, "tuple_to_userset": ttu}
        self._tuples: dict[tuple[str, str], list[str]] = {}

    # --- 入力の検証 ---------------------------------------------------------

    def _check_object(self, obj: str) -> str:
        if not isinstance(obj, str) or not _OBJECT_RE.fullmatch(obj):
            raise ValueError(f"オブジェクトは 'type:id' の形式です: {obj!r}")
        otype = obj.split(":", 1)[0]
        if otype not in self._schema:
            raise ValueError(f"未定義の型です: {otype}")
        return otype

    def _check_relation(self, obj: str, relation: str) -> None:
        otype = self._check_object(obj)
        if relation not in self._schema[otype]:
            raise ValueError(f"{otype} に関係 {relation!r} はありません")

    def _check_subject(self, subject: str) -> None:
        if not isinstance(subject, str):
            raise ValueError(f"主体が不正です: {subject!r}")
        if "#" in subject:
            sobj, _, srel = subject.partition("#")
            self._check_relation(sobj, srel)  # userset（例: group:eng#member）
        elif not _OBJECT_RE.fullmatch(subject):
            raise ValueError(f"主体は 'type:id' または 'type:id#relation' です: {subject!r}")

    def _is_tupleset(self, otype: str, relation: str) -> bool:
        return any(relation == pair[0] for rule in self._schema[otype].values() for pair in rule["tuple_to_userset"])

    # --- 書き込み -----------------------------------------------------------

    def write(self, obj: str, relation: str, subject: str) -> None:
        self._check_relation(obj, relation)
        self._check_subject(subject)
        otype = obj.split(":", 1)[0]
        if self._is_tupleset(otype, relation):
            # parent のような「オブジェクト間の関係」の相手は、定義済みの型のオブジェクト
            if "#" in subject:
                raise ValueError(f"{otype}#{relation} の相手はオブジェクトでなければなりません: {subject}")
            self._check_object(subject)
        subjects = self._tuples.setdefault((obj, relation), [])
        if subject not in subjects:
            subjects.append(subject)

    def delete(self, obj: str, relation: str, subject: str) -> None:
        subjects = self._tuples.get((obj, relation), [])
        if subject in subjects:
            subjects.remove(subject)

    # --- 判定 ---------------------------------------------------------------

    def check(self, obj: str, relation: str, user: str) -> bool:
        self._check_relation(obj, relation)
        if not isinstance(user, str) or "#" in user or not _OBJECT_RE.fullmatch(user):
            raise ValueError(f"判定する主体は 'type:id' です: {user!r}")
        return self._check(obj, relation, user, set())

    def _check(self, obj: str, relation: str, user: str, visited: set[tuple[str, str]]) -> bool:
        key = (obj, relation)
        if key in visited:
            # 同じノードに 2 度目に来た = 循環しているか、すでに調べ終えた（結果は False）。
            # 規則が和集合だけなら、ここで打ち切っても答えは変わらない
            return False
        visited.add(key)
        otype = obj.split(":", 1)[0]
        rule = self._schema[otype].get(relation)
        if rule is None:
            return False  # 親の型にその関係がない場合など
        # 1. 直接のタプル（Zanzibar の _this）
        for subject in self._tuples.get(key, []):
            if subject == user:
                return True
            if "#" in subject:
                sobj, _, srel = subject.partition("#")
                if self._check(sobj, srel, user, visited):
                    return True
        # 2. 同じオブジェクトの別の関係（computed_userset）: owner ⊆ editor ⊆ viewer
        for other in rule["computed_userset"]:
            if self._check(obj, other, user, visited):
                return True
        # 3. 関係をたどった先のオブジェクトの関係（tuple_to_userset）: 親フォルダの viewer
        for tupleset, computed in rule["tuple_to_userset"]:
            for parent in self._tuples.get((obj, tupleset), []):
                if self._check(parent, computed, user, visited):
                    return True
        return False
