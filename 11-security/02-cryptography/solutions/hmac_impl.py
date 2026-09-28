"""11.2 暗号技術の基礎 — 解答例（hmac_impl）

演習の仕様は exercises/hmac_impl.py の docstring を参照してください。
本番では標準ライブラリの hmac モジュール（hmac.new / hmac.compare_digest）を使います。
"""
from __future__ import annotations

import hashlib

BLOCK_SIZE = 64  # SHA-256 のブロック長（バイト）
DIGEST_SIZE = 32  # SHA-256 の出力長（バイト）
IPAD = 0x36
OPAD = 0x5C


# ---------------------------------------------------------------------------
# 演習1: HMAC-SHA256
# ---------------------------------------------------------------------------

def hmac_sha256(key: bytes, message: bytes) -> bytes:
    if not isinstance(key, (bytes, bytearray)) or not isinstance(message, (bytes, bytearray)):
        raise TypeError("key と message は bytes で渡してください")
    # 1. ブロック長より長い鍵は、まずハッシュして短くする（RFC 2104）
    if len(key) > BLOCK_SIZE:
        key = hashlib.sha256(key).digest()
    # 2. ブロック長まで 0x00 で埋める
    key = bytes(key).ljust(BLOCK_SIZE, b"\x00")
    # 3. H((K ⊕ opad) ‖ H((K ⊕ ipad) ‖ m))
    inner_key = bytes(b ^ IPAD for b in key)
    outer_key = bytes(b ^ OPAD for b in key)
    inner = hashlib.sha256(inner_key + message).digest()
    return hashlib.sha256(outer_key + inner).digest()


# ---------------------------------------------------------------------------
# 演習2: 定数時間比較と検証
# ---------------------------------------------------------------------------

def constant_time_equal(a: bytes, b: bytes) -> bool:
    if len(a) != len(b):
        # 長さは秘密ではない（タグ長は公開仕様）ので、ここで早く返してよい
        return False
    diff = 0
    # 途中で return しない: 最初に違ったバイトの位置が処理時間に表れないようにする
    for x, y in zip(a, b):
        diff |= x ^ y
    return diff == 0


def verify_hmac(key: bytes, message: bytes, tag: bytes) -> bool:
    return constant_time_equal(hmac_sha256(key, message), tag)


# ---------------------------------------------------------------------------
# 演習3: SHA-256 のパディング（長さ拡張攻撃の「のり」）
# ---------------------------------------------------------------------------

def sha256_padding(message_length: int) -> bytes:
    if message_length < 0:
        raise ValueError("長さは 0 以上です")
    # 0x80（ビット 1 と 7 個の 0）→ 0x00 を k 個 → 64 ビットのビッグエンディアンのビット長。
    # 全体の長さが 64 バイトの倍数になるように k を決める: (len + 1 + k + 8) ≡ 0 (mod 64)
    zeros = (55 - message_length) % BLOCK_SIZE
    return b"\x80" + b"\x00" * zeros + (message_length * 8).to_bytes(8, "big")
