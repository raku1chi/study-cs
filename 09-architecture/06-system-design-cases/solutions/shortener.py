"""9.6 システム設計ケーススタディ — 解答例: URL 短縮サービスの符号化

演習の仕様は exercises/shortener.py の docstring を参照してください。
"""
from __future__ import annotations

import math
import re
import threading
from urllib.parse import urlsplit

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)  # 62
_INDEX = {ch: i for i, ch in enumerate(ALPHABET)}

RESERVED = frozenset({"api", "admin", "login", "logout", "signup", "static", "assets", "health",
                      "about", "help", "terms", "privacy", "www"})
_ALIAS = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
MAX_URL_LENGTH = 2048


# ---------------------------------------------------------------------------
# 演習1: 62 進数
# ---------------------------------------------------------------------------

def base62_encode(n: int, width: int | None = None) -> str:
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        raise ValueError(f"0 以上の整数を指定してください: {n!r}")
    digits = []
    while True:
        n, r = divmod(n, BASE)
        digits.append(ALPHABET[r])
        if n == 0:
            break
    s = "".join(reversed(digits))
    if width is not None:
        if len(s) > width:
            raise ValueError(f"{width} 桁に収まりません")
        s = s.rjust(width, ALPHABET[0])
    return s


def base62_decode(s: str) -> int:
    if not s:
        raise ValueError("空文字列は変換できません")
    value = 0
    for ch in s:
        d = _INDEX.get(ch)
        if d is None:
            raise ValueError(f"62 進数として不正な文字です: {ch!r}")
        value = value * BASE + d
    return value


# ---------------------------------------------------------------------------
# 演習2: 連番から、推測しにくく衝突しない短縮コードへ
# ---------------------------------------------------------------------------

def default_multiplier(length: int) -> int:
    # 黄金比に近い位置の奇数から始め、62 と互いに素（2 でも 31 でも割り切れない）な値を探す。
    # 連続する番号が、コードの空間の中で大きく離れた位置に散らばる（フィボナッチ・ハッシュの考え方）
    modulus = BASE ** length
    m = int(modulus * 0.6180339887498949) | 1
    while math.gcd(m, BASE) != 1:
        m += 2
    return m


class CodeGenerator:
    def __init__(self, length: int = 7, multiplier: int | None = None, offset: int = 0) -> None:
        if length < 1:
            raise ValueError("length は 1 以上です")
        self.length = length
        self.modulus = BASE ** length
        self.multiplier = default_multiplier(length) if multiplier is None else multiplier
        if not 0 < self.multiplier < self.modulus or math.gcd(self.multiplier, BASE) != 1:
            # 62^length を法として逆元を持つ（全単射になる）のは、62 と互いに素な数だけ
            raise ValueError("multiplier は 62^length 未満の、62 と互いに素な正の整数です")
        if not 0 <= offset < self.modulus:
            raise ValueError("offset は 0 以上 62^length 未満です")
        self.offset = offset
        self._inverse = pow(self.multiplier, -1, self.modulus)  # Python 3.8 以降: 法 m での逆元

    @property
    def capacity(self) -> int:
        return self.modulus

    def code_for(self, counter: int) -> str:
        if isinstance(counter, bool) or not isinstance(counter, int) or not 0 <= counter < self.modulus:
            raise ValueError(f"counter は 0 以上 {self.modulus} 未満です: {counter!r}")
        # (a × n + b) mod M は、a が M と互いに素なら全単射。異なる番号は必ず異なるコードになる
        return base62_encode((counter * self.multiplier + self.offset) % self.modulus, width=self.length)

    def counter_for(self, code: str) -> int:
        if len(code) != self.length:
            raise ValueError(f"コードは {self.length} 文字です: {code!r}")
        value = base62_decode(code)
        return ((value - self.offset) * self._inverse) % self.modulus


# ---------------------------------------------------------------------------
# 演習2（続き）: 入力の検証と、サービス本体
# ---------------------------------------------------------------------------

def validate_alias(alias: str, *, code_length: int = 7, reserved: frozenset[str] = RESERVED) -> str:
    if not isinstance(alias, str) or not _ALIAS.match(alias):
        raise ValueError("別名は 3〜30 文字の英数字・ハイフン・アンダースコアです")
    if alias.lower() in reserved:
        raise ValueError(f"{alias!r} は予約語なので使えません")
    if len(alias) == code_length and all(ch in _INDEX for ch in alias):
        # 自動生成のコードと同じ形の別名を許すと、将来の自動生成のコードと衝突しうる
        raise ValueError(f"{code_length} 文字の英数字だけの別名は、自動生成のコードと衝突しうるので使えません")
    return alias


def validate_url(url: str) -> str:
    if not isinstance(url, str) or not url or len(url) > MAX_URL_LENGTH:
        raise ValueError(f"URL は 1〜{MAX_URL_LENGTH} 文字です")
    if any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in url):
        raise ValueError("URL に空白や制御文字は使えません")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise ValueError("http か https の URL だけを短縮できます（javascript: などは不可）")
    if not parts.hostname:
        raise ValueError("ホスト名がありません")
    return url


class AliasTakenError(ValueError):
    pass


class Shortener:
    def __init__(self, generator: CodeGenerator | None = None) -> None:
        self._gen = generator or CodeGenerator()
        self._next = 0
        self._urls: dict[str, str] = {}
        self._lock = threading.Lock()

    def shorten(self, url: str, alias: str | None = None) -> str:
        validate_url(url)
        with self._lock:
            if alias is not None:
                validate_alias(alias, code_length=self._gen.length)
                if alias in self._urls:
                    raise AliasTakenError(f"別名 {alias!r} は使われています")
                self._urls[alias] = url
                return alias
            if self._next >= self._gen.capacity:
                raise OverflowError("コードの空間を使い切りました（桁数を増やす必要があります）")
            code = self._gen.code_for(self._next)
            self._next += 1
            self._urls[code] = url
            return code

    def resolve(self, code: str) -> str:
        with self._lock:
            try:
                return self._urls[code]
            except KeyError:
                raise KeyError(f"未登録のコードです: {code!r}") from None
