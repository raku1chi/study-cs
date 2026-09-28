"""11.2 暗号技術の基礎 — 解答例（block_modes）

【教育目的・本番では使わない】ToyFeistelCipher は仕組みを学ぶための自作暗号です。
本番では AES-GCM や ChaCha20-Poly1305 などの AEAD を、検証済みのライブラリで使います。

演習の仕様は exercises/block_modes.py の docstring を参照してください。
"""
from __future__ import annotations

import hashlib
import hmac

BLOCK_SIZE = 16
HALF = BLOCK_SIZE // 2
DEFAULT_ROUNDS = 4
NONCE_SIZE = 8


def xor_bytes(a: bytes, b: bytes) -> bytes:
    if len(a) != len(b):
        raise ValueError(f"長さが違います: {len(a)} と {len(b)}")
    return bytes(x ^ y for x, y in zip(a, b))


class ToyFeistelCipher:
    """HMAC-SHA256 をラウンド関数にした、16 バイトブロックの Feistel 暗号（教育用）。"""

    def __init__(self, key: bytes, rounds: int = DEFAULT_ROUNDS) -> None:
        if len(key) < 16:
            raise ValueError("鍵は 16 バイト以上にしてください")
        if rounds < 1:
            raise ValueError("ラウンド数は 1 以上です")
        self.rounds = rounds
        # 主鍵からラウンドごとに別の鍵を導出する（ラウンド鍵）
        self._round_keys = [
            hmac.new(key, b"toy-feistel round " + bytes([i]), hashlib.sha256).digest()
            for i in range(rounds)
        ]

    def _f(self, i: int, half: bytes) -> bytes:
        """ラウンド関数 F_i: 8 バイト → 8 バイト。逆関数を持つ必要がないのが Feistel の利点。"""
        return hmac.new(self._round_keys[i], half, hashlib.sha256).digest()[:HALF]

    # -----------------------------------------------------------------------
    # 演習1: Feistel 構造
    # -----------------------------------------------------------------------

    def encrypt_block(self, block: bytes) -> bytes:
        if len(block) != BLOCK_SIZE:
            raise ValueError(f"ブロックは {BLOCK_SIZE} バイトです: {len(block)}")
        left, right = block[:HALF], block[HALF:]
        for i in range(self.rounds):
            left, right = right, xor_bytes(left, self._f(i, right))
        return left + right

    def decrypt_block(self, block: bytes) -> bytes:
        if len(block) != BLOCK_SIZE:
            raise ValueError(f"ブロックは {BLOCK_SIZE} バイトです: {len(block)}")
        left, right = block[:HALF], block[HALF:]
        # 暗号化の各ラウンド (L, R) → (R, L ⊕ F(R)) を逆順に巻き戻す。
        # F 自体を逆算する必要はない（同じ F(R) をもう一度 XOR すれば消える）
        for i in reversed(range(self.rounds)):
            left, right = xor_bytes(right, self._f(i, left)), left
        return left + right


# ---------------------------------------------------------------------------
# 演習2: PKCS#7 パディングと ECB モード
# ---------------------------------------------------------------------------

def pkcs7_pad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    if not 1 <= block_size <= 255:
        raise ValueError("block_size は 1〜255 です")
    # 必ず 1 バイト以上付ける（ちょうど割り切れるときは 1 ブロック丸ごと付ける）
    n = block_size - len(data) % block_size
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    if not data or len(data) % block_size:
        raise ValueError("長さがブロック長の正の倍数ではありません")
    n = data[-1]
    if not 1 <= n <= block_size or data[-n:] != bytes([n]) * n:
        raise ValueError("パディングが不正です")
    return data[:-n]


def _blocks(data: bytes, size: int = BLOCK_SIZE) -> list[bytes]:
    return [data[i:i + size] for i in range(0, len(data) - len(data) % size, size)]


def ecb_encrypt(cipher: ToyFeistelCipher, plaintext: bytes) -> bytes:
    return b"".join(cipher.encrypt_block(b) for b in _blocks(pkcs7_pad(plaintext)))


def ecb_decrypt(cipher: ToyFeistelCipher, ciphertext: bytes) -> bytes:
    if not ciphertext or len(ciphertext) % BLOCK_SIZE:
        raise ValueError("暗号文の長さがブロック長の正の倍数ではありません")
    return pkcs7_unpad(b"".join(cipher.decrypt_block(b) for b in _blocks(ciphertext)))


# ---------------------------------------------------------------------------
# 演習3: CTR モード
# ---------------------------------------------------------------------------

def ctr_keystream(cipher: ToyFeistelCipher, nonce: bytes, length: int) -> bytes:
    if len(nonce) != NONCE_SIZE:
        raise ValueError(f"nonce は {NONCE_SIZE} バイトです")
    if length < 0:
        raise ValueError("length は 0 以上です")
    out = bytearray()
    counter = 0
    while len(out) < length:
        # 入力ブロック = nonce（8 バイト）‖ カウンタ（8 バイト、ビッグエンディアン）
        out += cipher.encrypt_block(nonce + counter.to_bytes(8, "big"))
        counter += 1
    return bytes(out[:length])


def ctr_encrypt(cipher: ToyFeistelCipher, nonce: bytes, data: bytes) -> bytes:
    # 暗号化も復号も「鍵ストリームとの XOR」なので同じ関数でよい。パディングも不要
    return xor_bytes(data, ctr_keystream(cipher, nonce, len(data)))


# ---------------------------------------------------------------------------
# 演習4: 攻撃者の視点 — ECB の検出・nonce の再利用・ビット反転
# ---------------------------------------------------------------------------

def count_repeated_blocks(data: bytes, block_size: int = BLOCK_SIZE) -> int:
    blocks = _blocks(data, block_size)
    return len(blocks) - len(set(blocks))


def looks_like_ecb(ciphertext: bytes) -> bool:
    return count_repeated_blocks(ciphertext) > 0


def recover_plaintext_from_nonce_reuse(c1: bytes, c2: bytes, known_p1: bytes) -> bytes:
    # 同じ鍵ストリーム K で c1 = p1 ⊕ K、c2 = p2 ⊕ K → c1 ⊕ c2 = p1 ⊕ p2。K は消える
    n = min(len(c1), len(c2), len(known_p1))
    return xor_bytes(xor_bytes(c1[:n], c2[:n]), known_p1[:n])


def ctr_bitflip(ciphertext: bytes, known_plaintext: bytes, target_plaintext: bytes) -> bytes:
    if not len(ciphertext) == len(known_plaintext) == len(target_plaintext):
        raise ValueError("3 つの長さを揃えてください")
    # c ⊕ (p ⊕ p') を復号すると (p ⊕ K ⊕ p ⊕ p') ⊕ K = p'。鍵を知らなくても平文を書き換えられる
    return xor_bytes(ciphertext, xor_bytes(known_plaintext, target_plaintext))
