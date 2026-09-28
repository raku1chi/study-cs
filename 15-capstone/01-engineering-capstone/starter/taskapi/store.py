"""データアクセス層（リポジトリ）。

テナントが所有するデータを扱う関数は、すべてテナントIDを必須の引数に取り、SQL の WHERE 句で
必ず絞り込みます。「テナントIDを渡し忘れる」ことを関数の形で起こりにくくするのが、テナント分離の
第一の防御線です（第二はスキーマの複合外部キー、第三は越境を試みるテスト）。

SQL の値はすべてプレースホルダ（?）で渡します。文字列の連結や f 文字列で SQL を組み立てては
いけません（SQL インジェクション。11.4 章）。
"""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any

from .timeutil import to_iso


class NotFound(Exception):
    """指定したテナントの中に、そのリソースが存在しない。"""


class Conflict(Exception):
    """一意制約などに違反した。"""


def new_id(prefix: str) -> str:
    """種類が分かるプレフィックス付きのランダムな ID（例: 'prj_3f2c…'）。中身は UUIDv4。

    連番と違い、ID から件数や作成順を推測されない。どの方式にするかは M1 の ADR で決め直してよい。
    """
    return f"{prefix}_{uuid.uuid4().hex}"


# --- テナント（テナントの外側にある唯一のテーブル） ---

def create_tenant(conn: sqlite3.Connection, name: str, now: datetime) -> dict[str, Any]:
    tenant = {"id": new_id("ten"), "name": name, "created_at": to_iso(now)}
    conn.execute("INSERT INTO tenants (id, name, created_at) VALUES (:id, :name, :created_at)", tenant)
    return tenant


def tenant_exists(conn: sqlite3.Connection, tenant_id: str) -> bool:
    return conn.execute("SELECT 1 FROM tenants WHERE id = ?", (tenant_id,)).fetchone() is not None


# --- プロジェクト ---

def create_project(conn: sqlite3.Connection, tenant_id: str, *, name: str, now: datetime) -> dict[str, Any]:
    project = {"id": new_id("prj"), "name": name, "created_at": to_iso(now)}
    try:
        conn.execute(
            "INSERT INTO projects (tenant_id, id, name, created_at) VALUES (?, ?, ?, ?)",
            (tenant_id, project["id"], name, project["created_at"]),
        )
    except sqlite3.IntegrityError as exc:
        if "UNIQUE" in str(exc):
            raise Conflict(f"project name already exists: {name}") from exc
        raise
    return project


def get_project(conn: sqlite3.Connection, tenant_id: str, project_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, name, created_at FROM projects WHERE tenant_id = ? AND id = ?",
        (tenant_id, project_id),
    ).fetchone()
    if row is None:
        raise NotFound(project_id)
    return dict(row)


def list_projects(conn: sqlite3.Connection, tenant_id: str, *, limit: int) -> list[dict[str, Any]]:
    # ORDER BY に id を加えて順序を一意にする（同じ時刻の行があっても結果が揺れない）
    rows = conn.execute(
        "SELECT id, name, created_at FROM projects WHERE tenant_id = ?"
        " ORDER BY created_at, id LIMIT ?",
        (tenant_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


# TODO(M2): tasks / comments / users のデータアクセス関数を追加する。
#   一覧はカーソル方式（WHERE (created_at, id) > (?, ?) ORDER BY created_at, id LIMIT ?）で。
