"""合成ルート（composition root）: すべての部品を組み立てる場所。"""
from shop.adapters import db, web
from shop.application import place_order


def app_config() -> dict:
    return {"db_path": "shop.sqlite3"}


def main() -> None:
    database = db.Database(app_config()["db_path"])
    print(web, place_order, database)
