"""1.1 情報の表現 — 解答例

演習の仕様は exercises/datarep.py の docstring を参照してください。
ここでは「なぜそう書くのか」が分かるように、コメントを多めに付けています。
"""
from __future__ import annotations

import math
import struct

DIGITS = "0123456789abcdef"


# ---------------------------------------------------------------------------
# 演習1: 基数変換
# ---------------------------------------------------------------------------

def _check_base(base: int) -> None:
    if not 2 <= base <= 16:
        raise ValueError(f"base は 2〜16 で指定してください: {base}")


def to_base(n: int, base: int) -> str:
    _check_base(base)
    if n < 0:
        raise ValueError(f"負の数は扱いません: {n}")
    if n == 0:
        return "0"
    digits: list[str] = []
    # base で割った余りが、下の桁から順に得られる
    while n > 0:
        n, r = divmod(n, base)
        digits.append(DIGITS[r])
    return "".join(reversed(digits))


def from_base(s: str, base: int) -> int:
    _check_base(base)
    if not s:
        raise ValueError("空文字列は変換できません")
    value = 0
    # ホーナー法: 上の桁から「これまでの値 × base + 次の桁」を繰り返す
    for ch in s.lower():
        d = DIGITS.find(ch)
        if d < 0 or d >= base:
            raise ValueError(f"{base}進数として不正な文字です: {ch!r}")
        value = value * base + d
    return value


# ---------------------------------------------------------------------------
# 演習2: 2の補数
# ---------------------------------------------------------------------------

def _signed_range(bits: int) -> tuple[int, int]:
    if bits <= 0:
        raise ValueError(f"bits は 1 以上で指定してください: {bits}")
    return -(1 << (bits - 1)), (1 << (bits - 1)) - 1


def to_twos_complement(n: int, bits: int) -> str:
    lo, hi = _signed_range(bits)
    if not lo <= n <= hi:
        raise OverflowError(f"{n} は {bits} ビットの符号付き整数で表せません（{lo}〜{hi}）")
    # 負の数 -x は 2^bits - x というビット列で表す（= 2^bits を法とした同値な値）
    unsigned = n + (1 << bits) if n < 0 else n
    return to_base(unsigned, 2).rjust(bits, "0")


def from_twos_complement(s: str) -> int:
    if not s or any(c not in "01" for c in s):
        raise ValueError(f"0 と 1 からなるビット列を指定してください: {s!r}")
    value = from_base(s, 2)
    # 最上位ビットが 1 なら負の数。符号なしとしての値から 2^bits を引く
    if s[0] == "1":
        value -= 1 << len(s)
    return value


# ---------------------------------------------------------------------------
# 演習3: 固定幅の加算とオーバーフロー検出
# ---------------------------------------------------------------------------

def add_signed(a: int, b: int, bits: int) -> tuple[int, bool]:
    lo, hi = _signed_range(bits)
    for v in (a, b):
        if not lo <= v <= hi:
            raise OverflowError(f"{v} は {bits} ビットの符号付き整数で表せません")
    mask = (1 << bits) - 1
    # ハードウェアの加算器と同じく、下位 bits ビットだけを残す（あふれた桁は捨てる）
    raw = (a + b) & mask
    # 最上位ビット（符号ビット）が立っていれば負の数として解釈する
    result = raw - (1 << bits) if raw >> (bits - 1) else raw
    # 同符号どうしを足したのに結果の符号が変わった ⇔ 符号付きオーバーフロー
    overflow = (a < 0) == (b < 0) and (result < 0) != (a < 0)
    return result, overflow


# ---------------------------------------------------------------------------
# 演習4: IEEE 754 倍精度の分解と組み立て
# ---------------------------------------------------------------------------

EXP_BITS = 11
FRAC_BITS = 52
EXP_BIAS = 1023
EXP_MAX = (1 << EXP_BITS) - 1  # 2047


def float_fields(x: float) -> tuple[int, int, int]:
    # float を 8 バイトのビッグエンディアン表現にし、64 ビット整数として読み直す
    (bits64,) = struct.unpack(">Q", struct.pack(">d", x))
    sign = bits64 >> 63
    exponent = (bits64 >> FRAC_BITS) & EXP_MAX
    fraction = bits64 & ((1 << FRAC_BITS) - 1)
    return sign, exponent, fraction


def classify_float(x: float) -> str:
    _, exponent, fraction = float_fields(x)
    if exponent == 0:
        return "zero" if fraction == 0 else "subnormal"
    if exponent == EXP_MAX:
        return "infinity" if fraction == 0 else "nan"
    return "normal"


def fields_to_float(sign: int, exponent: int, fraction: int) -> float:
    if sign not in (0, 1):
        raise ValueError(f"sign は 0 か 1: {sign}")
    if not 0 <= exponent <= EXP_MAX:
        raise ValueError(f"exponent は 0〜{EXP_MAX}: {exponent}")
    if not 0 <= fraction < (1 << FRAC_BITS):
        raise ValueError(f"fraction は 0〜2^{FRAC_BITS}-1: {fraction}")
    s = -1.0 if sign else 1.0
    if exponent == EXP_MAX:
        return s * math.inf if fraction == 0 else math.nan
    if exponent == 0:
        # 非正規化数（とゼロ）: 0.F × 2^(1 - 1023)。暗黙の先頭 1 がない
        return s * math.ldexp(fraction, 1 - EXP_BIAS - FRAC_BITS)
    # 正規化数: 1.F × 2^(E - 1023)。fraction / 2^52 が小数部 F にあたる
    return s * math.ldexp((1 << FRAC_BITS) + fraction, exponent - EXP_BIAS - FRAC_BITS)


# ---------------------------------------------------------------------------
# 演習5: UTF-8 エンコーダ／デコーダ
# ---------------------------------------------------------------------------

def utf8_encode(code_points: list[int]) -> bytes:
    out = bytearray()
    for cp in code_points:
        if not 0 <= cp <= 0x10FFFF or 0xD800 <= cp <= 0xDFFF:
            raise ValueError(f"UTF-8 で符号化できないコードポイントです: {cp:#x}")
        if cp < 0x80:  # 0xxxxxxx
            out.append(cp)
        elif cp < 0x800:  # 110xxxxx 10xxxxxx
            out.append(0xC0 | (cp >> 6))
            out.append(0x80 | (cp & 0x3F))
        elif cp < 0x10000:  # 1110xxxx 10xxxxxx 10xxxxxx
            out.append(0xE0 | (cp >> 12))
            out.append(0x80 | ((cp >> 6) & 0x3F))
            out.append(0x80 | (cp & 0x3F))
        else:  # 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx
            out.append(0xF0 | (cp >> 18))
            out.append(0x80 | ((cp >> 12) & 0x3F))
            out.append(0x80 | ((cp >> 6) & 0x3F))
            out.append(0x80 | (cp & 0x3F))
    return bytes(out)


def utf8_decode(data: bytes) -> list[int]:
    result: list[int] = []
    i, n = 0, len(data)
    while i < n:
        b0 = data[i]
        if b0 < 0x80:
            result.append(b0)
            i += 1
            continue
        # 先頭バイトから長さを決める。C0・C1 は必ず冗長表現になるので最初から不正
        if 0xC2 <= b0 <= 0xDF:
            length, cp, minimum = 2, b0 & 0x1F, 0x80
        elif 0xE0 <= b0 <= 0xEF:
            length, cp, minimum = 3, b0 & 0x0F, 0x800
        elif 0xF0 <= b0 <= 0xF4:
            length, cp, minimum = 4, b0 & 0x07, 0x10000
        else:
            raise ValueError(f"不正な先頭バイト {b0:#04x}（位置 {i}）")
        if i + length > n:
            raise ValueError(f"途中で途切れたシーケンスです（位置 {i}）")
        for j in range(1, length):
            b = data[i + j]
            if b & 0xC0 != 0x80:  # 継続バイトは必ず 10xxxxxx
                raise ValueError(f"継続バイトではありません: {b:#04x}（位置 {i + j}）")
            cp = (cp << 6) | (b & 0x3F)
        if cp < minimum:
            raise ValueError(f"冗長な（overlong）表現です（位置 {i}）")
        if 0xD800 <= cp <= 0xDFFF:
            raise ValueError(f"サロゲート {cp:#x} は UTF-8 では不正です（位置 {i}）")
        if cp > 0x10FFFF:
            raise ValueError(f"Unicode の範囲外です: {cp:#x}（位置 {i}）")
        result.append(cp)
        i += length
    return result
