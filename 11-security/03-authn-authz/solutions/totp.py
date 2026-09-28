"""11.3 認証と認可 — 解答例（totp）

演習の仕様は exercises/totp.py の docstring を参照してください。
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import struct
import time
from typing import Callable

ALGORITHMS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


# ---------------------------------------------------------------------------
# 演習1: HOTP（RFC 4226）
# ---------------------------------------------------------------------------

def hotp(secret: bytes, counter: int, digits: int = 6, algorithm: str = "sha1") -> str:
    if not 6 <= digits <= 8:
        raise ValueError(f"桁数は 6〜8 です: {digits}")
    if algorithm not in ALGORITHMS:
        raise ValueError(f"未対応のアルゴリズムです: {algorithm}")
    if not 0 <= counter < 2**64:
        raise ValueError(f"カウンタは 0 以上 2^64 未満です: {counter}")
    # 1. カウンタを 8 バイトのビッグエンディアンにして HMAC を取る
    mac = hmac.new(secret, struct.pack(">Q", counter), ALGORITHMS[algorithm]).digest()
    # 2. 動的切り詰め（dynamic truncation）: 最後のバイトの下位 4 ビットを開始位置にする
    offset = mac[-1] & 0x0F
    # 3. そこから 4 バイトを取り、最上位ビットを落として 31 ビットの整数にする
    #    （符号付き/符号なしの解釈の違いで実装がずれないようにするため）
    code = int.from_bytes(mac[offset:offset + 4], "big") & 0x7FFFFFFF
    # 4. 下位 digits 桁を取り、先頭を 0 で埋める
    return str(code % 10**digits).zfill(digits)


# ---------------------------------------------------------------------------
# 演習2: TOTP（RFC 6238）
# ---------------------------------------------------------------------------

def time_step(unix_time: float, step: int = 30, t0: int = 0) -> int:
    if step <= 0:
        raise ValueError("step は正の整数です")
    return int((unix_time - t0) // step)


def totp(
    secret: bytes,
    unix_time: float,
    *,
    step: int = 30,
    t0: int = 0,
    digits: int = 6,
    algorithm: str = "sha1",
) -> str:
    return hotp(secret, time_step(unix_time, step, t0), digits, algorithm)


def b32decode_secret(text: str) -> bytes:
    # 認証アプリの QR コードに入っている秘密鍵は Base32。空白・小文字・パディングなしを許容する
    cleaned = "".join(text.split()).upper()
    cleaned += "=" * (-len(cleaned) % 8)
    try:
        return base64.b32decode(cleaned)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("Base32 として不正な秘密鍵です") from exc


# ---------------------------------------------------------------------------
# 演習3: 検証（時刻のずれの許容とリプレイ防止）
# ---------------------------------------------------------------------------

class TotpVerifier:
    def __init__(
        self,
        secret: bytes,
        *,
        step: int = 30,
        digits: int = 6,
        window: int = 1,
        algorithm: str = "sha1",
        clock: Callable[[], float] = time.time,
    ) -> None:
        if window < 0:
            raise ValueError("window は 0 以上です")
        hotp(secret, 0, digits, algorithm)  # パラメータの検査を兼ねる
        self.secret = secret
        self.step = step
        self.digits = digits
        self.window = window
        self.algorithm = algorithm
        self.clock = clock
        self.last_used_step: int | None = None

    def verify(self, code: str, now: float | None = None) -> bool:
        if not isinstance(code, str) or len(code) != self.digits or not code.isascii() or not code.isdigit():
            return False
        current = time_step(self.clock() if now is None else now, self.step)
        matched: int | None = None
        # 利用者の端末とサーバーの時計のずれを許すため、前後 window ステップまで試す
        for s in range(max(0, current - self.window), current + self.window + 1):
            candidate = hotp(self.secret, s, self.digits, self.algorithm)
            # == ではなく定数時間比較（何桁目まで合っているかを処理時間から漏らさない）
            if hmac.compare_digest(candidate, code):
                matched = s
                break
        if matched is None:
            return False
        # リプレイ防止: 一度受理したステップ以前のコードは二度と受け付けない
        if self.last_used_step is not None and matched <= self.last_used_step:
            return False
        self.last_used_step = matched
        return True
