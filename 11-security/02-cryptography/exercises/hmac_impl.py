"""11.2 暗号技術の基礎 — 演習（hmac_impl）

HMAC-SHA256 を、ハッシュ関数 hashlib.sha256 だけを部品にして自分で組み立てます。
あわせて、タイミング攻撃を防ぐ「定数時間比較」と、長さ拡張攻撃の鍵になる
SHA-256 のパディング規則を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.2
    python3 tools/check.py -v 11.2

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_hmac_impl

制約（学びのための縛り）:
    - hmac モジュール（hmac.new, hmac.digest, hmac.compare_digest）は使わないでください。
      テストでは答え合わせのために使っています。
    - 本番のコードでは、自作せずに hmac モジュールを使ってください。

参考: HMAC の定義（RFC 2104）
    HMAC(K, m) = H((K' ⊕ opad) ‖ H((K' ⊕ ipad) ‖ m))
    K' = K がブロック長より長ければ H(K)、そうでなければ K。これを 0x00 でブロック長まで埋める
    ipad = 0x36 をブロック長だけ並べたもの、opad = 0x5c をブロック長だけ並べたもの
"""
from __future__ import annotations

import hashlib  # noqa: F401  hashlib.sha256 を部品として使います

BLOCK_SIZE = 64  # SHA-256 のブロック長（バイト）
DIGEST_SIZE = 32  # SHA-256 の出力長（バイト）
IPAD = 0x36
OPAD = 0x5C


# ---------------------------------------------------------------------------
# 演習1（★★☆）: HMAC-SHA256
# ---------------------------------------------------------------------------

def hmac_sha256(key: bytes, message: bytes) -> bytes:
    """HMAC-SHA256 のタグ（32 バイト）を返す。

    - key・message が bytes（または bytearray）でなければ TypeError。
    - 鍵の長さは任意（0 バイトも、ブロック長 64 バイトより長い鍵も可）。

    >>> hmac_sha256(b"Jefe", b"what do ya want for nothing?").hex()[:16]
    '5bdcc146bf60754e'

    ヒント: bytes(b ^ IPAD for b in padded_key) で鍵と ipad の XOR が作れる。
    """
    raise NotImplementedError("演習1: hmac_sha256 を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 定数時間比較と検証
# ---------------------------------------------------------------------------

def constant_time_equal(a: bytes, b: bytes) -> bool:
    """a と b が等しければ True を返す。**比較にかかる時間が内容に依存しないように** 書くこと。

    - 長さが違えば False（長さは秘密ではないので、すぐ返してよい）。
    - 同じ長さなら、最初に違うバイトが見つかっても途中で return せず、全バイトを見る。
      例えば各バイトの XOR を OR で蓄積し、最後に 0 かどうかを見る。
    - 戻り値は bool（True / False）。

    なぜ必要か: `==` は最初に違うバイトで比較を打ち切るので、処理時間から
    「先頭何バイトまで合っているか」が漏れ、タグを 1 バイトずつ推測されうる（タイミング攻撃）。
    """
    raise NotImplementedError("演習2: constant_time_equal を実装してください")


def verify_hmac(key: bytes, message: bytes, tag: bytes) -> bool:
    """tag が hmac_sha256(key, message) と一致すれば True（定数時間で比較する）。"""
    raise NotImplementedError("演習2: verify_hmac を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆）: SHA-256 のパディング（長さ拡張攻撃の「のり」）
# ---------------------------------------------------------------------------

def sha256_padding(message_length: int) -> bytes:
    """長さ message_length バイトのメッセージに SHA-256 が内部で付け足すパディングを返す。

    FIPS 180-4 の規則:
      1. 0x80（ビット 1 に続く 7 ビットの 0）を付ける
      2. 0x00 を k 個付ける。k は「メッセージ + パディング全体の長さが 64 の倍数」になる最小の値
      3. 最後にメッセージの **ビット長** を 64 ビット（8 バイト）のビッグエンディアンで付ける

    - message_length が負なら ValueError。

    >>> len(sha256_padding(0)), len(sha256_padding(55)), len(sha256_padding(56))
    (64, 9, 72)

    これが分かると、長さ拡張攻撃で攻撃者が送る偽造メッセージ
        m ‖ sha256_padding(len(key) + len(m)) ‖ 追加データ
    の構造が理解できます（README の「MAC と HMAC」を参照）。
    """
    raise NotImplementedError("演習3: sha256_padding を実装してください")
