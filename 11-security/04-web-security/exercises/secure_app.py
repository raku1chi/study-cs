"""11.4 Webアプリケーションセキュリティ — 演習（secure_app）

★この演習は「動くけれど脆弱なコード」を直す形式です★
下の実装は正常系では動きますが、SQL インジェクション・XSS・IDOR の脆弱性を抱えています。
テストには「機能テスト」（正常系。今も通る）と「攻撃テスト」（今は失敗する）があります。
攻撃テストがすべて通るように、各関数を安全に書き直してください。

対象:
  - 演習1（★☆☆）: search_users / authenticate の SQL インジェクション
  - 演習2（★★☆）: escape_html / escape_attribute / render の XSS（文脈に応じた出力エスケープ）
  - 演習3（★☆☆）: get_invoice の IDOR（安全でない直接オブジェクト参照）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.4
    python3 tools/check.py -v 11.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_secure_app

ヒント:
  - SQL は文字列連結をやめ、プレースホルダ（?）で値を渡す（sqlite3 の execute の第2引数）。
    LIKE のワイルドカード（% _）は値の側でエスケープする。
  - 出力は「どこに埋め込むか」（要素の内容か、属性値か）で必要なエスケープが変わる。
  - オブジェクトを ID で取り出すときは、必ず「その人が見てよいものか」を一緒に確認する。
"""
from __future__ import annotations

import hmac  # noqa: F401  定数時間比較に使えます
import re
import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# データベースの準備（この部分は演習の対象外。書き換えないでください）
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password TEXT NOT NULL
);
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    owner_id INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    memo TEXT NOT NULL
);
"""

SEED_USERS = [
    (1, 10, "alice", "Alice (Acme)", "pw-alice"),
    (2, 10, "bob", "Bob (Acme)", "pw-bob"),
    (3, 20, "carol", "Carol (Globex)", "pw-carol"),
    (4, 20, "admin'; --", "変な名前の人", "pw-weird"),
]
SEED_INVOICES = [
    (100, 10, 1, 5000, "Acme: alice の請求書"),
    (101, 10, 2, 8000, "Acme: bob の請求書"),
    (102, 20, 3, 3000, "Globex: carol の請求書"),
]


def init_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.executemany("INSERT INTO users VALUES (?, ?, ?, ?, ?)", SEED_USERS)
    db.executemany("INSERT INTO invoices VALUES (?, ?, ?, ?, ?)", SEED_INVOICES)
    db.commit()
    return db


@dataclass(frozen=True)
class User:
    id: int
    tenant_id: int
    username: str


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: SQL インジェクション ← 直してください
# ---------------------------------------------------------------------------

def search_users(db: sqlite3.Connection, keyword: str) -> list[str]:
    """display_name に keyword を含むユーザーの表示名を返す（前方後方一致）。

    【脆弱】keyword を SQL 文に直接埋め込んでいるため、SQL インジェクションが可能です。
    """
    query = "SELECT display_name FROM users WHERE display_name LIKE '%" + keyword + "%' ORDER BY id"
    return [row["display_name"] for row in db.execute(query).fetchall()]


def authenticate(db: sqlite3.Connection, username: str, password: str) -> User | None:
    """username と password が一致すれば User、しなければ None を返す。

    【脆弱】文字列連結で SQL を組み立てているため、「alice' --」で認証を回避できます。
    """
    query = (
        "SELECT id, tenant_id, username FROM users "
        "WHERE username = '" + username + "' AND password = '" + password + "'"
    )
    row = db.execute(query).fetchone()
    if row is None:
        return None
    return User(row["id"], row["tenant_id"], row["username"])


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 文脈に応じた出力エスケープと自動エスケープテンプレート ← 直してください
# ---------------------------------------------------------------------------

class SafeString(str):
    """「すでに安全（エスケープ済み・信頼できる）」と印を付けた文字列。"""


def mark_safe(text: str) -> SafeString:
    return SafeString(text)


def escape_html(text: str) -> SafeString:
    """要素の内容（body）向けのエスケープ。

    【脆弱】何もエスケープしていません。& < > を実体参照に変換してください。
    """
    return SafeString(str(text))


def escape_attribute(text: str) -> SafeString:
    """属性値向けのエスケープ。

    【脆弱】< > しかエスケープしていないので、value="..." のクォートを閉じて属性を注入できます。
    body のエスケープに加えて、" と ' もエスケープしてください。
    """
    return SafeString(str(text).replace("<", "&lt;").replace(">", "&gt;"))


_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*(?:\|\s*(\w+)\s*)?\}\}")


def render(template: str, **context: object) -> SafeString:
    """{{ name }} を context の値で置き換える。

    【脆弱】値をそのまま埋め込んでいるので XSS が起きます。既定で自動エスケープするように直してください:
      - {{ name }}        要素の内容として escape_html でエスケープ
      - {{ name | attr }} 属性値として escape_attribute でエスケープ
      - 値が SafeString のときだけ、その文脈でもエスケープせずそのまま入れる
    context に無い変数は KeyError にすること。
    """
    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(context[name])

    return SafeString(_PLACEHOLDER_RE.sub(replace, template))


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: IDOR（安全でない直接オブジェクト参照） ← 直してください
# ---------------------------------------------------------------------------

def get_invoice(db: sqlite3.Connection, invoice_id: int, current_user: User) -> sqlite3.Row | None:
    """current_user が閲覧してよい場合だけ、請求書の行を返す（そうでなければ None）。

    【脆弱】ID だけで引いているため、ID を推測すれば他人・他テナントの請求書が見えます。
    current_user のテナントと所有者に一致するかを確認してください。
    """
    return db.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
