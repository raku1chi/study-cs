"""9.6 システム設計ケーススタディ — 演習1・2: URL 短縮サービスの符号化

ケーススタディ 1（URL 短縮）の核心部分を実装します。

    演習1（★☆☆）: base62_encode / base62_decode — 数値と 62 進数の文字列の相互変換
    演習2（★★☆）: CodeGenerator — 連番から「衝突しない・連番に見えない」固定長のコードを作る全単射
                   validate_alias / validate_url / Shortener — 入力の検証とサービス本体

連番（データベースの自動採番など）をそのまま 62 進数にすると、衝突は起きませんが、
「a1b2c3」の次は「a1b2c4」と推測でき、登録数（事業の規模）も漏れます。そこで、連番 n に対して

    code = base62((a × n + b) mod 62^k)     （a は 62 と互いに素な定数）

を計算します。a が 62^k と互いに素なら、この写像は 0〜62^k−1 の上の **全単射**（一対一の並べ替え）なので、
異なる番号は必ず異なるコードになり、逆算（counter_for）もできます。ただし、これは難読化であって
暗号ではありません。いくつかのコードを集めれば a と b は推測できるので、秘密を守る目的には使わないこと。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.6

制約: 演習1 では int(s, base) などの組み込みの基数変換は使えないので（62 進数は対象外）、自分で実装する。
"""
from __future__ import annotations

import math  # noqa: F401  演習2で使えます
import re
import threading  # noqa: F401  演習2で使えます（Shortener のロック）
from urllib.parse import urlsplit  # noqa: F401  演習2で使えます

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)  # 62
_INDEX = {ch: i for i, ch in enumerate(ALPHABET)}

RESERVED = frozenset({"api", "admin", "login", "logout", "signup", "static", "assets", "health",
                      "about", "help", "terms", "privacy", "www"})
_ALIAS = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
MAX_URL_LENGTH = 2048


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 62 進数
# ---------------------------------------------------------------------------

def base62_encode(n: int, width: int | None = None) -> str:
    """0 以上の整数 n を、ALPHABET を使った 62 進数の文字列にする（大文字と小文字は別の数字）。

    - n が負、または int でない（bool も不可）なら ValueError
    - width を指定したら、先頭を ALPHABET[0]（"0"）で埋めてその桁数にする。収まらなければ ValueError

    >>> base62_encode(0), base62_encode(61), base62_encode(62)
    ('0', 'Z', '10')
    >>> base62_encode(125, width=4)
    '0021'
    """
    raise NotImplementedError("演習1: base62_encode を実装してください")


def base62_decode(s: str) -> int:
    """base62_encode の逆。空文字列や ALPHABET にない文字は ValueError。

    >>> base62_decode("10"), base62_decode("0021")
    (62, 125)
    """
    raise NotImplementedError("演習1: base62_decode を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 連番から、推測しにくく衝突しない短縮コードへ
# ---------------------------------------------------------------------------

def default_multiplier(length: int) -> int:
    """既定の乗数（実装済み）: 62^length × (黄金比 − 1) 付近の、62 と互いに素な奇数。

    連続する番号が、コードの空間の中で大きく離れた位置に散らばる（フィボナッチ・ハッシュの考え方）。
    """
    modulus = BASE ** length
    m = int(modulus * 0.6180339887498949) | 1
    while math.gcd(m, BASE) != 1:
        m += 2
    return m


class CodeGenerator:
    """連番 counter（0 以上 62^length 未満）と、length 文字のコードを一対一に対応させる。

    - multiplier が None なら default_multiplier(length) を使う。
    - multiplier は 0 < multiplier < 62^length で、62 と互いに素（math.gcd(multiplier, 62) == 1）。
      offset は 0 以上 62^length 未満。length は 1 以上。違反は ValueError。
    - code_for(n) = base62_encode((n × multiplier + offset) mod 62^length, width=length)
      n が範囲外（または int でない・bool）なら ValueError。
    - counter_for(code) は code_for の逆。長さが違う・不正な文字を含むコードは ValueError。
      ヒント: 乗数の「法 62^length での逆元」は pow(multiplier, -1, modulus) で求まる。
    - capacity: 発行できるコードの総数（62^length）。
    """

    def __init__(self, length: int = 7, multiplier: int | None = None, offset: int = 0) -> None:
        raise NotImplementedError("演習2: CodeGenerator.__init__ を実装してください")

    @property
    def capacity(self) -> int:
        raise NotImplementedError("演習2: CodeGenerator.capacity を実装してください")

    def code_for(self, counter: int) -> str:
        raise NotImplementedError("演習2: CodeGenerator.code_for を実装してください")

    def counter_for(self, code: str) -> int:
        raise NotImplementedError("演習2: CodeGenerator.counter_for を実装してください")


def validate_alias(alias: str, *, code_length: int = 7, reserved: frozenset[str] = RESERVED) -> str:
    """利用者が指定した別名（カスタムエイリアス）を検証し、問題なければそのまま返す。違反は ValueError。

    - 3〜30 文字の英数字・"-"・"_" だけ（_ALIAS の正規表現）
    - 予約語（大文字・小文字を区別せずに比較。"Admin" も不可）はだめ（サービス自身のパスと衝突する）
    - ちょうど code_length 文字で、すべてが ALPHABET の文字である別名はだめ
      （将来、自動生成されるコードとまったく同じ文字列になりうるため。"-" や "_" を含むか、
       長さが違えば、自動生成のコードとは衝突しない）
    """
    raise NotImplementedError("演習2: validate_alias を実装してください")


def validate_url(url: str) -> str:
    """短縮する URL を検証し、問題なければそのまま返す。違反は ValueError。

    - 1〜MAX_URL_LENGTH 文字の文字列
    - 空白文字（str.isspace）や制御文字（U+0000〜U+001F と U+007F）を含まない
    - urlsplit で分解したスキームが http か https（javascript: や data: を短縮させない）
    - ホスト名がある（urlsplit(url).hostname が空でない）
    """
    raise NotImplementedError("演習2: validate_url を実装してください")


class AliasTakenError(ValueError):
    pass


class Shortener:
    """メモリ上の URL 短縮サービス。

    - shorten(url, alias=None): url を検証し、
        * alias があれば validate_alias（code_length は生成器の length）で検証して登録し、alias を返す。
          使用済みなら AliasTakenError。
        * alias がなければ、内部の連番（0 から始まる）に対応するコードを生成器で作り、連番を 1 進めて返す。
          連番が capacity に達していたら OverflowError。
      同じ URL を 2 回短縮したら、別のコードを返してよい（重複の除去はしない）。
    - resolve(code): 登録済みの URL を返す。なければ KeyError。
    - 複数のスレッドから同時に呼ばれても、同じコードを 2 回発行しないこと（self._lock を使う）。
    """

    def __init__(self, generator: CodeGenerator | None = None) -> None:
        raise NotImplementedError("演習2: Shortener.__init__ を実装してください")

    def shorten(self, url: str, alias: str | None = None) -> str:
        raise NotImplementedError("演習2: Shortener.shorten を実装してください")

    def resolve(self, code: str) -> str:
        raise NotImplementedError("演習2: Shortener.resolve を実装してください")

