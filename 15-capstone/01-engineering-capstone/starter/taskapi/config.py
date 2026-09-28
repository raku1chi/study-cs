"""設定の読み込み（環境変数 → Config）。

設定値はコードに埋め込まず、環境変数から読みます（The Twelve-Factor App の「設定」の考え方）。
テストでは Config(...) を直接組み立てて注入します。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class Config:
    db_path: str = "taskapi.db"
    host: str = "127.0.0.1"
    port: int = 8000
    # これを超えるリクエストボディは読まずに 413 で拒否する（メモリを食い潰す攻撃への備え）
    max_body_bytes: int = 1024 * 1024

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Config":
        """環境変数 TASKAPI_DB_PATH / TASKAPI_HOST / TASKAPI_PORT / TASKAPI_MAX_BODY_BYTES を読む。

        不正な値は起動時に ValueError にする（おかしな設定のまま動き出すより、すぐ落ちる方が安全）。
        """
        env = os.environ if environ is None else environ
        return cls(
            db_path=env.get("TASKAPI_DB_PATH") or cls.db_path,
            host=env.get("TASKAPI_HOST") or cls.host,
            port=_int_setting(env, "TASKAPI_PORT", cls.port, minimum=0, maximum=65535),
            max_body_bytes=_int_setting(env, "TASKAPI_MAX_BODY_BYTES", cls.max_body_bytes, minimum=1),
        )


def _int_setting(
    env: Mapping[str, str],
    name: str,
    default: int,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} は整数で指定してください: {raw!r}") from None
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name} が範囲外です: {value}")
    return value
