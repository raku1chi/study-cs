"""コマンドラインの入り口。

    python3 -m taskapi migrate                 # 未適用のマイグレーションを適用する
    python3 -m taskapi create-tenant "Acme"    # テナントを作成し、ID を表示する
    python3 -m taskapi serve                   # HTTP サーバーを起動する（Ctrl-C で停止）

設定は環境変数で渡します（TASKAPI_DB_PATH・TASKAPI_HOST・TASKAPI_PORT など。config.py を参照）。
"""
from __future__ import annotations

import argparse
import logging
import sys
from contextlib import closing

from . import db, store
from .app import create_app
from .config import Config
from .server import serve
from .timeutil import utc_now


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m taskapi", description="チーム向けタスク管理API（15.1 スターター）")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate", help="未適用のマイグレーションを適用する")
    tenant_parser = commands.add_parser("create-tenant", help="テナントを作成し、ID を表示する")
    tenant_parser.add_argument("name")
    commands.add_parser("serve", help="HTTP サーバーを起動する")
    args = parser.parse_args(argv)

    config = Config.from_env()
    with closing(db.connect(config.db_path)) as conn:
        if args.command == "migrate":
            applied = db.migrate(conn)
            for migration in applied:
                print(f"applied {migration.version:04d}_{migration.name}")
            if not applied:
                print("no pending migrations")
            return 0

        # migrate 以外は、スキーマが最新でなければ動かない（古いスキーマのまま動き出す事故を防ぐ）
        pending = db.pending_migrations(conn)
        if pending:
            names = ", ".join(f"{m.version:04d}_{m.name}" for m in pending)
            print(f"未適用のマイグレーションがあります（{names}）。先に migrate を実行してください", file=sys.stderr)
            return 1

        if args.command == "create-tenant":
            name = args.name.strip()
            if not name:
                print("テナント名を指定してください", file=sys.stderr)
                return 2
            with db.transaction(conn):
                tenant = store.create_tenant(conn, name, utc_now())
            print(tenant["id"])
            return 0

    # serve: TODO(M4) ログを JSON Lines で標準出力に書く設定に置き換える
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    serve(create_app(config), config.host, config.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
