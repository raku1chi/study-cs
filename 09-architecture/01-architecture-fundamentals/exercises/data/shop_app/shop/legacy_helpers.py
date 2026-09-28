import os


def log(message: str) -> None:
    if os.environ.get("SHOP_DEBUG"):
        print(message)
