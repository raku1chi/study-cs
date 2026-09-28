"""11.3 認証と認可 — 演習（totp）

認証アプリ（Google Authenticator や Microsoft Authenticator など）が表示する 6 桁の
ワンタイムパスワードを、仕様（RFC 4226 の HOTP、RFC 6238 の TOTP）どおりに実装し、
サーバー側の検証で必要になる「時計のずれの許容」と「リプレイ防止」を作ります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.3
    python3 tools/check.py -v 11.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_totp

テストでは RFC 4226 Appendix D と RFC 6238 Appendix B の公式テストベクタを使っています。

HOTP の定義（RFC 4226）:
    HOTP(K, C) = Truncate(HMAC-SHA-1(K, C)) mod 10^桁数
    C はカウンタを 8 バイトのビッグエンディアンにしたもの。
    Truncate（動的切り詰め）: HMAC 値の最後のバイトの下位 4 ビットを offset とし、
    offset から 4 バイトをビッグエンディアンの整数として読み、最上位ビットを 0 にする（& 0x7FFFFFFF）。
TOTP の定義（RFC 6238）:
    TOTP(K, T) = HOTP(K, floor((T − T0) / X))   （X は時間ステップ、既定 30 秒。T0 は既定 0）
"""
from __future__ import annotations

import base64  # noqa: F401
import binascii  # noqa: F401
import hashlib
import hmac  # noqa: F401
import struct  # noqa: F401
import time
from typing import Callable

ALGORITHMS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: HOTP（RFC 4226）
# ---------------------------------------------------------------------------

def hotp(secret: bytes, counter: int, digits: int = 6, algorithm: str = "sha1") -> str:
    """HOTP の値を、先頭を 0 で埋めた digits 桁の文字列で返す。

    - digits が 6〜8 でなければ ValueError（RFC 4226 は 6 桁以上を要求）。
    - algorithm が ALGORITHMS のキー（"sha1", "sha256", "sha512"）でなければ ValueError。
    - counter が 0 以上 2^64 未満でなければ ValueError。

    >>> hotp(b"12345678901234567890", 0)
    '755224'

    ヒント: struct.pack(">Q", counter) で 8 バイトのビッグエンディアンになる。
    """
    raise NotImplementedError("演習1: hotp を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: TOTP（RFC 6238）
# ---------------------------------------------------------------------------

def time_step(unix_time: float, step: int = 30, t0: int = 0) -> int:
    """時刻 unix_time（UNIX 時間の秒）が属する時間ステップ floor((unix_time − t0) / step) を返す。

    step <= 0 なら ValueError。

    >>> time_step(59)
    1
    """
    raise NotImplementedError("演習2: time_step を実装してください")


def totp(
    secret: bytes,
    unix_time: float,
    *,
    step: int = 30,
    t0: int = 0,
    digits: int = 6,
    algorithm: str = "sha1",
) -> str:
    """時刻 unix_time における TOTP の値を返す（= hotp(secret, time_step(...), digits, algorithm)）。

    >>> totp(b"12345678901234567890", 59, digits=8)
    '94287082'
    """
    raise NotImplementedError("演習2: totp を実装してください")


def b32decode_secret(text: str) -> bytes:
    """認証アプリに登録する Base32 の秘密鍵をバイト列に戻す。

    - 空白（スペース・改行）を取り除き、大文字にしてからデコードする。
    - 末尾のパディング '=' が省略されていてもよい（長さが 8 の倍数になるまで補う）。
    - Base32 として不正なら ValueError。

    >>> b32decode_secret("gezd gnbv gy3t qojq")
    b'1234567890'
    """
    raise NotImplementedError("演習2: b32decode_secret を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 検証（時計のずれの許容とリプレイ防止）
# ---------------------------------------------------------------------------

class TotpVerifier:
    """1 人の利用者の TOTP を検証する（サーバー側）。

    本番では last_used_step を DB に保存し、同時に届いた 2 つのリクエストの両方を
    受理しないよう、更新を原子的に行う必要があります（6.3 のトランザクションを参照）。
    """

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
        """パラメータを保存する。

        - window < 0、または digits・algorithm が hotp の条件を満たさなければ ValueError
          （hotp(secret, 0, digits, algorithm) を 1 回呼べば検査を兼ねられる）。
        - self.last_used_step（最後に受理した時間ステップ）を None で初期化する。
        """
        raise NotImplementedError("演習3: TotpVerifier.__init__ を実装してください")

    def verify(self, code: str, now: float | None = None) -> bool:
        """code が正しければ True を返し、受理したステップを last_used_step に記録する。

        1. code が str で、ちょうど digits 桁の **ASCII の** 数字でなければ False
           （"１２３４５６" のような全角数字も str.isdigit() は True を返すので注意）。
        2. now が None なら self.clock() を現在時刻とする。
        3. 現在のステップ c について、c − window 〜 c + window（負のステップは除く）の順に
           hotp を計算し、hmac.compare_digest で比較する。最初に一致したステップを採用する。
        4. 一致しなければ False。
        5. 採用したステップが last_used_step 以下なら False（リプレイ、または古いコード）。
        6. last_used_step を更新して True。

        失敗した検証では last_used_step を変えないこと。
        """
        raise NotImplementedError("演習3: TotpVerifier.verify を実装してください")
