import json

from shop.application.place_order import place_order


def handle_request(body: str) -> str:
    # 関数の中の import も依存関係に含まれる（しかも合成ルートへの逆向きの依存）
    from shop.main import app_config

    payload = json.loads(body)
    return json.dumps({"ok": True, "config": app_config(), "payload": payload})


__all__ = ["place_order", "handle_request"]
