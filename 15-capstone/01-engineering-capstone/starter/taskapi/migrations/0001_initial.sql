-- 0001_initial: 初期スキーマ
--
-- 設計方針（15.1 章「スターターコード」も参照）
--   1. テナントが所有するすべてのテーブルに tenant_id を持たせる。
--   2. 子テーブルは (tenant_id, 親の id) の複合外部キーで親を参照する。
--      これで「別テナントのプロジェクトに属するタスク」のような行を DB 自身が拒否する。
--      複合外部キーの参照先には UNIQUE (tenant_id, id) が必要。
--   3. ID は種類を表すプレフィックス付きのランダム文字列（例: prj_3f2c...）。
--   4. 日時は UTC の ISO 8601 文字列（例: 2026-04-01T09:00:00.000Z）。
--   5. 適用済みのマイグレーションは編集しない。変更は 0002_xxx.sql のように新しいファイルで行う。

CREATE TABLE tenants (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE users (
    tenant_id    TEXT NOT NULL REFERENCES tenants (id),
    id           TEXT PRIMARY KEY,
    email        TEXT NOT NULL,
    display_name TEXT NOT NULL,
    role         TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    created_at   TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, email)
);

CREATE TABLE projects (
    tenant_id   TEXT NOT NULL REFERENCES tenants (id),
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    UNIQUE (tenant_id, name)
);
CREATE INDEX projects_by_tenant_created ON projects (tenant_id, created_at, id);

CREATE TABLE tasks (
    tenant_id   TEXT NOT NULL,
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done')),
    assignee_id TEXT,                         -- NULL = 未割り当て
    due_date    TEXT,                         -- 日付のみ（YYYY-MM-DD）。どのタイムゾーンの日付かは M1 で決める
    version     INTEGER NOT NULL DEFAULT 1,   -- 楽観的ロック（M2）で使う
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects (tenant_id, id),
    FOREIGN KEY (tenant_id, assignee_id) REFERENCES users (tenant_id, id)
);
CREATE INDEX tasks_by_project ON tasks (tenant_id, project_id, created_at, id);

CREATE TABLE comments (
    tenant_id   TEXT NOT NULL,
    id          TEXT PRIMARY KEY,
    task_id     TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (tenant_id, task_id) REFERENCES tasks (tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, author_id) REFERENCES users (tenant_id, id)
);
CREATE INDEX comments_by_task ON comments (tenant_id, task_id, created_at, id);
