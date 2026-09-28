"""11.3 認可モデル（authz）— テスト

実行: python3 tools/check.py 11.3   （またはこのディレクトリで python3 -m unittest -v）
"""
import unittest

from authz import RBAC, ReBAC, RelationTuple

SCHEMA = {
    "group": {"member": {}},
    "folder": {
        "owner": {},
        "editor": {"computed_userset": ["owner"]},
        "viewer": {"computed_userset": ["editor"], "tuple_to_userset": [("parent", "viewer")]},
        "parent": {},
    },
    "document": {
        "owner": {},
        "editor": {"computed_userset": ["owner"], "tuple_to_userset": [("parent", "editor")]},
        "viewer": {"computed_userset": ["editor"], "tuple_to_userset": [("parent", "viewer")]},
        "parent": {},
    },
}


def make_rbac() -> RBAC:
    rbac = RBAC()
    rbac.add_role("viewer", {"invoice:read"})
    rbac.add_role("editor", {"invoice:write"}, inherits=["viewer"])
    rbac.add_role("accountant", {"invoice:approve"}, inherits=["viewer"])
    rbac.add_role("admin", {"user:manage"}, inherits=["editor", "accountant"])
    return rbac


class TestExercise1RoleHierarchy(unittest.TestCase):
    def test_effective_roles(self):
        rbac = make_rbac()
        self.assertEqual(rbac.effective_roles("viewer"), {"viewer"})
        self.assertEqual(rbac.effective_roles("editor"), {"editor", "viewer"})
        self.assertEqual(rbac.effective_roles("admin"), {"admin", "editor", "accountant", "viewer"},
                         "ひし形の継承（admin → editor/accountant → viewer）")

    def test_permissions_are_inherited(self):
        rbac = make_rbac()
        rbac.assign("alice", "acme", "admin")
        self.assertEqual(
            rbac.permissions_of("alice", "acme"),
            {"invoice:read", "invoice:write", "invoice:approve", "user:manage"},
        )
        rbac.assign("bob", "acme", "editor")
        self.assertTrue(rbac.is_allowed("bob", "acme", "invoice:read"))
        self.assertTrue(rbac.is_allowed("bob", "acme", "invoice:write"))
        self.assertFalse(rbac.is_allowed("bob", "acme", "invoice:approve"))
        self.assertFalse(rbac.is_allowed("bob", "acme", "user:manage"))

    def test_roles_of(self):
        rbac = make_rbac()
        rbac.assign("carol", "acme", "accountant")
        self.assertEqual(rbac.roles_of("carol", "acme"), {"accountant", "viewer"})
        self.assertEqual(rbac.roles_of("nobody", "acme"), set())

    def test_revoke(self):
        rbac = make_rbac()
        rbac.assign("dave", "acme", "editor")
        rbac.revoke("dave", "acme", "editor")
        self.assertFalse(rbac.is_allowed("dave", "acme", "invoice:read"))
        rbac.revoke("dave", "acme", "editor")  # 2 回目も例外にしない（冪等）

    def test_add_inheritance_later(self):
        rbac = make_rbac()
        rbac.add_role("auditor", {"audit:read"})
        rbac.add_inheritance("admin", "auditor")
        rbac.assign("erin", "acme", "admin")
        self.assertTrue(rbac.is_allowed("erin", "acme", "audit:read"))

    def test_cycles_are_rejected(self):
        rbac = make_rbac()
        with self.assertRaises(ValueError):
            rbac.add_inheritance("viewer", "admin")  # admin → … → viewer → admin
        with self.assertRaises(ValueError):
            rbac.add_inheritance("editor", "editor")
        # 拒否された変更は反映されていない
        self.assertEqual(rbac.effective_roles("viewer"), {"viewer"})

    def test_invalid_definitions(self):
        rbac = make_rbac()
        with self.assertRaises(ValueError):
            rbac.add_role("viewer")  # 重複
        with self.assertRaises(ValueError):
            rbac.add_role("x", inherits=["ghost"])
        with self.assertRaises(ValueError):
            rbac.assign("alice", "acme", "ghost")
        with self.assertRaises(ValueError):
            rbac.add_inheritance("admin", "ghost")
        with self.assertRaises(ValueError):
            rbac.effective_roles("ghost")


class TestExercise2TenantIsolation(unittest.TestCase):
    def test_roles_do_not_leak_across_tenants(self):
        rbac = make_rbac()
        rbac.assign("alice", "acme", "admin")
        # acme の管理者でも、globex のデータには一切触れない
        self.assertEqual(rbac.permissions_of("alice", "globex"), set())
        self.assertFalse(rbac.is_allowed("alice", "globex", "invoice:read"))

    def test_same_user_different_roles_per_tenant(self):
        rbac = make_rbac()
        rbac.assign("frank", "acme", "admin")
        rbac.assign("frank", "globex", "viewer")
        self.assertTrue(rbac.is_allowed("frank", "acme", "invoice:write"))
        self.assertFalse(rbac.is_allowed("frank", "globex", "invoice:write"))
        self.assertTrue(rbac.is_allowed("frank", "globex", "invoice:read"))
        rbac.revoke("frank", "globex", "viewer")
        self.assertTrue(rbac.is_allowed("frank", "acme", "invoice:read"), "別テナントの取り消しは影響しない")


def make_rebac() -> ReBAC:
    z = ReBAC(SCHEMA)
    for t in [
        RelationTuple("document:readme", "owner", "user:alice"),
        RelationTuple("document:readme", "editor", "group:eng#member"),
        RelationTuple("group:eng", "member", "user:bob"),
        RelationTuple("group:eng", "member", "group:backend#member"),  # グループの入れ子
        RelationTuple("group:backend", "member", "user:carol"),
        RelationTuple("folder:proj", "viewer", "user:dave"),
        RelationTuple("folder:proj", "editor", "user:erin"),
        RelationTuple("document:spec", "parent", "folder:proj"),
        RelationTuple("document:spec", "owner", "user:frank"),
    ]:
        z.write(t.object, t.relation, t.subject)
    return z


class TestExercise3ReBAC(unittest.TestCase):
    def test_direct_and_computed_relations(self):
        z = make_rebac()
        # owner ⊆ editor ⊆ viewer
        for rel in ("owner", "editor", "viewer"):
            self.assertTrue(z.check("document:readme", rel, "user:alice"), rel)
        self.assertTrue(z.check("document:spec", "viewer", "user:frank"))
        self.assertFalse(z.check("document:readme", "owner", "user:frank"))

    def test_group_usersets(self):
        z = make_rebac()
        self.assertTrue(z.check("document:readme", "editor", "user:bob"))
        self.assertTrue(z.check("document:readme", "viewer", "user:bob"))
        self.assertFalse(z.check("document:readme", "owner", "user:bob"))
        self.assertTrue(z.check("group:eng", "member", "user:carol"), "入れ子のグループ")
        self.assertTrue(z.check("document:readme", "editor", "user:carol"))

    def test_parent_folder_inheritance(self):
        z = make_rebac()
        self.assertTrue(z.check("document:spec", "viewer", "user:dave"), "フォルダの閲覧者は中の文書も閲覧できる")
        self.assertFalse(z.check("document:spec", "editor", "user:dave"))
        self.assertTrue(z.check("document:spec", "editor", "user:erin"), "フォルダの編集者は中の文書も編集できる")
        self.assertTrue(z.check("document:spec", "viewer", "user:erin"))
        self.assertFalse(z.check("document:readme", "viewer", "user:dave"), "別のフォルダの文書には及ばない")

    def test_unknown_user_has_no_access(self):
        z = make_rebac()
        for obj in ("document:readme", "document:spec", "folder:proj"):
            for rel in ("owner", "editor", "viewer"):
                self.assertFalse(z.check(obj, rel, "user:mallory"), (obj, rel))

    def test_delete(self):
        z = make_rebac()
        z.delete("group:eng", "member", "user:bob")
        self.assertFalse(z.check("document:readme", "editor", "user:bob"), "グループから外れたら即座に失う")
        self.assertTrue(z.check("document:readme", "editor", "user:carol"))
        z.delete("group:eng", "member", "user:bob")  # 存在しないタプルの削除は何もしない

    def test_duplicate_write_is_idempotent(self):
        z = make_rebac()
        z.write("group:eng", "member", "user:bob")
        z.delete("group:eng", "member", "user:bob")
        self.assertFalse(z.check("group:eng", "member", "user:bob"))


class TestExercise4ReBACRobustness(unittest.TestCase):
    def test_cycles_terminate(self):
        z = ReBAC(SCHEMA)
        z.write("group:a", "member", "group:b#member")
        z.write("group:b", "member", "group:a#member")
        self.assertFalse(z.check("group:a", "member", "user:zed"), "循環があっても無限ループにならない")
        z.write("group:b", "member", "user:zed")
        self.assertTrue(z.check("group:a", "member", "user:zed"))

    def test_folder_cycle_terminates(self):
        z = ReBAC(SCHEMA)
        z.write("folder:x", "parent", "folder:y")
        z.write("folder:y", "parent", "folder:x")
        self.assertFalse(z.check("folder:x", "viewer", "user:zed"))
        z.write("folder:y", "owner", "user:zed")
        self.assertTrue(z.check("folder:x", "viewer", "user:zed"))

    def test_write_validation(self):
        z = ReBAC(SCHEMA)
        bad = [
            ("document:readme", "commenter", "user:x"),  # 未定義の関係
            ("doc:readme", "owner", "user:x"),  # 未定義の型
            ("document", "owner", "user:x"),  # id がない
            ("document:", "owner", "user:x"),
            ("document:readme", "owner", "alice"),  # 主体の形式
            ("document:readme", "owner", "user:"),
            ("document:readme", "editor", "group:eng#admin"),  # 未定義の関係の userset
            ("document:readme", "parent", "folder:proj#viewer"),  # parent の相手はオブジェクト
            ("document:readme", "parent", "planet:mars"),  # 未定義の型のオブジェクト
        ]
        for args in bad:
            with self.assertRaises(ValueError, msg=str(args)):
                z.write(*args)

    def test_check_validation(self):
        z = make_rebac()
        with self.assertRaises(ValueError):
            z.check("document:readme", "commenter", "user:alice")
        with self.assertRaises(ValueError):
            z.check("document:readme", "viewer", "group:eng#member")
        with self.assertRaises(ValueError):
            z.check("nothing", "viewer", "user:alice")

    def test_schema_validation(self):
        with self.assertRaises(ValueError):
            ReBAC({"document": {"viewer": {"computed_userset": ["editor"]}}})  # editor が未定義
        with self.assertRaises(ValueError):
            ReBAC({"document": {"viewer": {"tuple_to_userset": [("parent", "viewer")]}}})  # parent が未定義
        with self.assertRaises(ValueError):
            ReBAC({"document": {"viewer": {"magic": []}}})

    def test_schema_is_copied(self):
        schema = {"group": {"member": {}}}
        z = ReBAC(schema)
        schema["group"]["admin"] = {}
        with self.assertRaises(ValueError, msg="構築後にスキーマの dict を書き換えても影響しない"):
            z.write("group:g", "admin", "user:x")


if __name__ == "__main__":
    unittest.main()
