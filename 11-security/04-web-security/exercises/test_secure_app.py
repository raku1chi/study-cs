"""11.4 安全なWebアプリ（secure_app）— テスト

実行: python3 tools/check.py 11.4   （またはこのディレクトリで python3 -m unittest -v）

このテストには 2 種類あります:
  - 「機能テスト」（Functional*）: 正常な使い方。脆弱なスタブでも解答でも通ります。
  - 「攻撃テスト」（Attack*）: 攻撃が防げているかを確かめます。スタブでは失敗し、
    脆弱性を直すと通ります。目標はすべての攻撃テストを通すことです。
"""
import sqlite3
import unittest

from secure_app import (
    SafeString,
    User,
    authenticate,
    escape_attribute,
    escape_html,
    get_invoice,
    init_db,
    mark_safe,
    render,
    search_users,
)


class TestFunctionalSql(unittest.TestCase):
    def setUp(self):
        self.db = init_db()

    def tearDown(self):
        self.db.close()

    def test_search_finds_users(self):
        self.assertEqual(search_users(self.db, "Acme"), ["Alice (Acme)", "Bob (Acme)"])
        self.assertEqual(search_users(self.db, "Carol"), ["Carol (Globex)"])
        self.assertEqual(search_users(self.db, "見つからない"), [])

    def test_valid_login(self):
        user = authenticate(self.db, "alice", "pw-alice")
        self.assertIsNotNone(user)
        self.assertEqual((user.id, user.tenant_id, user.username), (1, 10, "alice"))

    def test_wrong_password_rejected(self):
        self.assertIsNone(authenticate(self.db, "alice", "wrong"))
        self.assertIsNone(authenticate(self.db, "nobody", "pw-alice"))


class TestAttackSql(unittest.TestCase):
    def setUp(self):
        self.db = init_db()

    def tearDown(self):
        self.db.close()

    def test_search_does_not_leak_via_union(self):
        # LIKE への UNION 注入でパスワード列を引き抜こうとする
        results = search_users(self.db, "x%' UNION SELECT password FROM users --")
        for secret in ("pw-alice", "pw-bob", "pw-carol", "pw-weird"):
            self.assertNotIn(secret, results, "パスワードが検索結果に漏れてはいけない")

    def test_search_wildcards_are_literal(self):
        # "%" を渡しても全件一致にならない（メタ文字がエスケープされている）
        self.assertEqual(search_users(self.db, "%"), [])

    def test_login_auth_bypass_is_blocked(self):
        for username, password in [
            ("alice' --", "any"),
            ("alice'/*", "*/"),
            ("' OR '1'='1", "' OR '1'='1"),
            ("' OR 1=1 --", "x"),
            ("nobody' UNION SELECT 1,10,'alice','x' --", "x"),
        ]:
            self.assertIsNone(authenticate(self.db, username, password),
                              f"SQL インジェクションによる認証回避: {username!r}")

    def test_legit_username_with_quotes_works(self):
        # 記号を含む正当なユーザー名でも、パラメータ化していれば壊れずに動く
        user = authenticate(self.db, "admin'; --", "pw-weird")
        self.assertIsNotNone(user)
        self.assertEqual(user.id, 4)


class TestFunctionalEscaping(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(escape_html("こんにちは 42"), "こんにちは 42")
        self.assertEqual(escape_attribute("normal-value"), "normal-value")

    def test_render_substitutes(self):
        self.assertEqual(render("こんにちは、{{ name }} さん", name="山田"), "こんにちは、山田 さん")
        self.assertEqual(render("合計: {{ n }}", n=100), "合計: 100")

    def test_render_missing_variable(self):
        with self.assertRaises(KeyError):
            render("{{ missing }}", other="x")


class TestAttackEscaping(unittest.TestCase):
    def test_escape_html_body(self):
        self.assertEqual(escape_html("<script>alert(1)</script>"),
                         "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertEqual(escape_html("a & b"), "a &amp; b")

    def test_escape_attribute_quotes(self):
        # 属性値の中でクォートをエスケープしないと value=".." を抜け出せる
        payload = '" onerror="alert(1)'
        escaped = escape_attribute(payload)
        self.assertNotIn('"', escaped)
        self.assertEqual(escaped, "&quot; onerror=&quot;alert(1)")
        self.assertEqual(escape_attribute("it's"), "it&#x27;s")

    def test_render_auto_escapes_body(self):
        out = render("<p>{{ comment }}</p>", comment="<img src=x onerror=alert(1)>")
        self.assertEqual(out, "<p>&lt;img src=x onerror=alert(1)&gt;</p>")
        self.assertNotIn("<img", out)

    def test_render_auto_escapes_attribute(self):
        out = render('<a title="{{ t | attr }}">x</a>', t='" onmouseover="alert(1)')
        self.assertNotIn('title="" onmouseover', out)
        self.assertEqual(out, '<a title="&quot; onmouseover=&quot;alert(1)">x</a>')

    def test_mark_safe_opts_out(self):
        # 明示的に安全と印を付けた HTML だけはそのまま入る
        safe = mark_safe("<b>強調</b>")
        self.assertIsInstance(safe, SafeString)
        self.assertEqual(render("<div>{{ body }}</div>", body=safe), "<div><b>強調</b></div>")
        # 印のない同じ文字列は必ずエスケープされる
        self.assertEqual(render("<div>{{ body }}</div>", body="<b>強調</b>"),
                         "<div>&lt;b&gt;強調&lt;/b&gt;</div>")

    def test_escape_functions_return_safe_string(self):
        self.assertIsInstance(escape_html("x"), SafeString)
        self.assertIsInstance(escape_attribute("x"), SafeString)
        self.assertIsInstance(render("{{ x }}", x="y"), SafeString)


class TestFunctionalIdor(unittest.TestCase):
    def setUp(self):
        self.db = init_db()

    def tearDown(self):
        self.db.close()

    def test_owner_can_read_own_invoice(self):
        alice = User(1, 10, "alice")
        row = get_invoice(self.db, 100, alice)
        self.assertIsNotNone(row)
        self.assertEqual(row["amount"], 5000)


class TestAttackIdor(unittest.TestCase):
    def setUp(self):
        self.db = init_db()

    def tearDown(self):
        self.db.close()

    def test_cannot_read_other_users_invoice_same_tenant(self):
        alice = User(1, 10, "alice")
        # 101 は同じテナント（Acme）だが所有者は bob
        self.assertIsNone(get_invoice(self.db, 101, alice), "同僚の請求書も所有者でなければ見えない")

    def test_cannot_read_other_tenant_invoice(self):
        alice = User(1, 10, "alice")
        # 102 は別テナント（Globex）の carol の請求書。ID を推測して +2 しても見えてはいけない
        self.assertIsNone(get_invoice(self.db, 102, alice), "他テナントの請求書（IDOR/BOLA）")

    def test_forged_user_object_still_needs_matching_tenant(self):
        # 攻撃者が current_user のテナントを詐称しても、所有者 ID が合わなければ見えない
        forged = User(1, 20, "alice")
        self.assertIsNone(get_invoice(self.db, 102, forged))


if __name__ == "__main__":
    unittest.main()
