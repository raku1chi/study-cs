"""11.2 暗号技術の基礎 — 演習（block_modes）

╔══════════════════════════════════════════════════════════════════════╗
║ 【教育目的・本番では使わない】                                          ║
║ ToyFeistelCipher は、仕組みを学ぶためにこの教材用に作った暗号です。       ║
║ 安全性の検証を受けていないので、実際のデータの保護には絶対に使わず、      ║
║ 本番では AES-GCM や ChaCha20-Poly1305 を検証済みのライブラリで使います。  ║
╚══════════════════════════════════════════════════════════════════════╝

ブロック暗号そのもの（Feistel 構造）と、その「使い方」である利用モード（ECB・CTR）を
実装し、攻撃者の立場で次の 3 つを確かめます。
  - ECB は同じ平文ブロックを同じ暗号文ブロックにするので、データの「模様」が漏れる
  - CTR で nonce を使い回すと、2 つの平文の XOR が漏れる
  - 暗号化だけでは改ざんを防げない（ビット反転攻撃）→ 認証付き暗号（AEAD）が必要

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.2
    python3 tools/check.py -v 11.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_block_modes
"""
from __future__ import annotations

import hashlib
import hmac

BLOCK_SIZE = 16  # ブロック長（バイト）。AES と同じ 128 ビット
HALF = BLOCK_SIZE // 2
DEFAULT_ROUNDS = 4
NONCE_SIZE = 8


def xor_bytes(a: bytes, b: bytes) -> bytes:
    """同じ長さの 2 つのバイト列の XOR を返す（長さが違えば ValueError）。この関数は完成済みです。"""
    if len(a) != len(b):
        raise ValueError(f"長さが違います: {len(a)} と {len(b)}")
    return bytes(x ^ y for x, y in zip(a, b))


class ToyFeistelCipher:
    """HMAC-SHA256 をラウンド関数にした、16 バイトブロックの Feistel 暗号（教育用）。

    __init__ と _f は完成済みです。encrypt_block / decrypt_block を実装してください。
    """

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
    # 演習1（★★☆）: Feistel 構造
    # -----------------------------------------------------------------------

    def encrypt_block(self, block: bytes) -> bytes:
        """16 バイトのブロックを暗号化する（長さが違えば ValueError）。

        アルゴリズム:
            L, R = block[:8], block[8:]
            i = 0, 1, ..., rounds-1 について:  L, R = R, L ⊕ F_i(R)
            return L ‖ R

        Luby と Rackoff は、F が擬似ランダム関数なら 3 ラウンドで擬似ランダム置換に、
        4 ラウンドで（復号側の問い合わせにも耐える）強い擬似ランダム置換になることを示しました。
        """
        raise NotImplementedError("演習1: encrypt_block を実装してください")

    def decrypt_block(self, block: bytes) -> bytes:
        """encrypt_block の逆変換（長さが違えば ValueError）。

        ヒント: 1 ラウンドの変換 (L, R) → (R, L ⊕ F(R)) を逆にたどる。
        出力の左半分がもとの R なので、それを使って F(R) を計算し直せば L が取り出せる。
        ラウンドは逆順（rounds-1, ..., 0）に処理する。F の逆関数は不要。
        """
        raise NotImplementedError("演習1: decrypt_block を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: PKCS#7 パディングと ECB モード
# ---------------------------------------------------------------------------

def pkcs7_pad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    """PKCS#7 パディングを付ける。n = block_size − len(data) % block_size として、値 n のバイトを n 個付ける。

    - 長さがちょうど割り切れるときも 1 ブロック分（値 block_size を block_size 個）付ける
      （そうしないと、末尾がたまたま 0x01 の平文とパディングを区別できない）。
    - block_size が 1〜255 でなければ ValueError。

    >>> pkcs7_pad(b"YELLOW SUBMARINE", 20)
    b'YELLOW SUBMARINE\\x04\\x04\\x04\\x04'
    """
    raise NotImplementedError("演習2: pkcs7_pad を実装してください")


def pkcs7_unpad(data: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    """PKCS#7 パディングを取り除く。不正なら ValueError。

    不正とは: 空・長さが block_size の倍数でない・末尾の値 n が 1〜block_size でない・
    末尾 n バイトがすべて n ではない。

    注意（実務）: 復号側が「パディングが不正」と「それ以外のエラー」を区別して返すと、
    それが手がかりになって暗号文が解読される（パディングオラクル攻撃）。
    AEAD を使えば、改ざんされた暗号文はパディングを見る前に拒否されます。
    """
    raise NotImplementedError("演習2: pkcs7_unpad を実装してください")


def ecb_encrypt(cipher: ToyFeistelCipher, plaintext: bytes) -> bytes:
    """ECB モードで暗号化する: PKCS#7 でパディングし、16 バイトごとに独立に encrypt_block する。"""
    raise NotImplementedError("演習2: ecb_encrypt を実装してください")


def ecb_decrypt(cipher: ToyFeistelCipher, ciphertext: bytes) -> bytes:
    """ECB モードで復号する。長さが 16 の正の倍数でなければ ValueError。復号後にパディングを外す。"""
    raise NotImplementedError("演習2: ecb_decrypt を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: CTR モード
# ---------------------------------------------------------------------------

def ctr_keystream(cipher: ToyFeistelCipher, nonce: bytes, length: int) -> bytes:
    """CTR モードの鍵ストリームを length バイト生成する。

    i 番目（0 から）のブロックは encrypt_block(nonce ‖ i を 8 バイトのビッグエンディアンにしたもの)。
    必要なだけブロックを作ってつなぎ、先頭 length バイトを返す。
    - nonce が 8 バイトでなければ ValueError。length が負なら ValueError。
    """
    raise NotImplementedError("演習3: ctr_keystream を実装してください")


def ctr_encrypt(cipher: ToyFeistelCipher, nonce: bytes, data: bytes) -> bytes:
    """data と鍵ストリームの XOR を返す。暗号化と復号は同じ操作（パディング不要）。

    **同じ鍵で同じ nonce を 2 回使ってはいけない**（演習4で理由を確かめます）。
    """
    raise NotImplementedError("演習3: ctr_encrypt を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: 攻撃者の視点 — ECB の検出・nonce の再利用・ビット反転
# ---------------------------------------------------------------------------

def count_repeated_blocks(data: bytes, block_size: int = BLOCK_SIZE) -> int:
    """data を block_size ごとに区切り、「それより前に同じブロックが現れている」ブロックの数を返す。

    = ブロック数 − 異なるブロックの種類数。末尾の block_size に満たない端数は数えない。

    >>> count_repeated_blocks(b"A" * 16 * 4 + b"B" * 16 * 2)
    4
    """
    raise NotImplementedError("演習4: count_repeated_blocks を実装してください")


def looks_like_ecb(ciphertext: bytes) -> bool:
    """暗号文に重複ブロックがあれば True（ECB で暗号化された疑いが強い）。"""
    raise NotImplementedError("演習4: looks_like_ecb を実装してください")


def recover_plaintext_from_nonce_reuse(c1: bytes, c2: bytes, known_p1: bytes) -> bytes:
    """同じ鍵・同じ nonce で暗号化された c1, c2 と、c1 の平文（の一部）known_p1 から、c2 の平文を復元する。

    長さは min(len(c1), len(c2), len(known_p1)) バイトまで。
    ヒント: c1 ⊕ c2 = p1 ⊕ p2（鍵ストリームが打ち消し合う）。
    """
    raise NotImplementedError("演習4: recover_plaintext_from_nonce_reuse を実装してください")


def ctr_bitflip(ciphertext: bytes, known_plaintext: bytes, target_plaintext: bytes) -> bytes:
    """鍵を知らずに、CTR の暗号文を「復号すると target_plaintext になる暗号文」に書き換える。

    3 つの長さが揃っていなければ ValueError。
    ヒント: 暗号文のビットを反転すると、復号結果の同じ位置のビットが反転する。
    """
    raise NotImplementedError("演習4: ctr_bitflip を実装してください")
