"""11.4 Webアプリケーションセキュリティ — 解答例（secure_app）

演習の仕様は exercises/secure_app.py の docstring を参照してください。
ここでは脆弱な実装を、安全な実装に直しています（← が修正の要点）。
"""
from __future__ import annotations

import hmac
import re
import sqlite3
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# データベースの準備（この部分は演習の対象外。両方の版で共通）
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
# 演習1: SQL インジェクション
# ---------------------------------------------------------------------------

def search_users(db: sqlite3.Connection, keyword: str) -> list[str]:
    """display_name に keyword を含むユーザーの表示名を返す（前方後方一致）。"""
    # ← プレースホルダ（?）で値を渡す。LIKE のワイルドカードは自分で付ける。
    #    文字列に keyword を埋め込まないので、keyword に SQL を書かれても値として扱われる。
    like = f"%{_escape_like(keyword)}%"
    rows = db.execute(
        "SELECT display_name FROM users WHERE display_name LIKE ? ESCAPE '\\' ORDER BY id",
        (like,),
    ).fetchall()
    return [row["display_name"] for row in rows]


def _escape_like(text: str) -> str:
    # LIKE のメタ文字（% _ \）を無効化する。これをしないと "%" で全件が漏れる
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def authenticate(db: sqlite3.Connection, username: str, password: str) -> User | None:
    """username と password が一致すれば User、しなければ None を返す。"""
    # ← ユーザー名で 1 行だけ引き、パスワードは定数時間比較する。
    #    「' OR '1'='1」などを入れても、値として扱われるだけで条件は変わらない。
    row = db.execute(
        "SELECT id, tenant_id, username, password FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        return None
    # 本来はハッシュ（Argon2id など。11.2 参照）を比較する。ここでは平文だが比較だけは定数時間で
    if not hmac.compare_digest(row["password"].encode("utf-8"), password.encode("utf-8")):
        return None
    return User(row["id"], row["tenant_id"], row["username"])


# ---------------------------------------------------------------------------
# 演習2: 文脈に応じた出力エスケープと自動エスケープテンプレート
# ---------------------------------------------------------------------------

class SafeString(str):
    """「すでに安全（エスケープ済み・信頼できる）」と印を付けた文字列。"""


def mark_safe(text: str) -> SafeString:
    return SafeString(text)


def escape_html(text: str) -> SafeString:
    """要素の内容（body）向けのエスケープ。& < > を実体参照にする。"""
    escaped = str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return SafeString(escaped)


def escape_attribute(text: str) -> SafeString:
    """属性値向けのエスケープ。body のエスケープに加えて、クォート類も実体参照にする。

    属性でクォートをエスケープしないと、value="..." を閉じて onerror= などを注入できる。
    """
    escaped = (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
    return SafeString(escaped)


_PLACEHOLDER_RE = re.compile(r"\{\{\s*(\w+)\s*(?:\|\s*(\w+)\s*)?\}\}")


def render(template: str, **context: object) -> SafeString:
    """{{ name }} を context の値で置き換える。既定で自動エスケープする。

    - {{ name }}        要素の内容として escape_html
    - {{ name | attr }} 属性値として escape_attribute
    値が SafeString なら、その文脈でもエスケープせずそのまま入れる（明示的な安全マーク）。
    """
    def replace(match: re.Match[str]) -> str:
        name, filt = match.group(1), match.group(2)
        if name not in context:
            raise KeyError(f"テンプレート変数がありません: {name}")
        value = context[name]
        if isinstance(value, SafeString):
            return str(value)  # 明示的に安全と印を付けた値はそのまま
        if filt == "attr":
            return escape_attribute(str(value))
        if filt in (None, "html"):
            return escape_html(str(value))
        raise ValueError(f"未知のフィルタです: {filt}")

    return SafeString(_PLACEHOLDER_RE.sub(replace, template))


# ---------------------------------------------------------------------------
# 演習3: IDOR（安全でない直接オブジェクト参照）
# ---------------------------------------------------------------------------

def get_invoice(db: sqlite3.Connection, invoice_id: int, current_user: User) -> sqlite3.Row | None:
    """current_user が閲覧してよい場合だけ、請求書の行を返す（そうでなければ None）。"""
    # ← ID で引くだけでなく、テナントと所有者の一致も WHERE 句で確かめる。
    #    「ID を +1 すれば他社の請求書が見える」状態（IDOR/BOLA）を防ぐ。
    return db.execute(
        "SELECT * FROM invoices WHERE id = ? AND tenant_id = ? AND owner_id = ?",
        (invoice_id, current_user.tenant_id, current_user.id),
    ).fetchone()
