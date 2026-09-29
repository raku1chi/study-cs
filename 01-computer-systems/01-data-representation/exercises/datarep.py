"""1.1 情報の表現 — 演習

各関数の docstring（仕様）を読み、`raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 1.1          # 合格数を表示
    python3 tools/check.py -v 1.1       # 各テストの結果を詳しく表示

このディレクトリで直接実行することもできます:
    python3 -m unittest -v

制約（学びのための縛り）:
    - 演習1・2・3 では int(s, base)・bin()・oct()・hex()・format()・f文字列の書式指定など、
      基数変換そのものを行う組み込み機能を使わないでください。
    - 演習5 では str.encode()・bytes.decode()・codecs モジュールを使わないでください。
    - テストの中では答え合わせのために組み込み機能を使っています。
"""
from __future__ import annotations

import math  # noqa: F401  演習4で使えます（math.ldexp など）
import struct  # noqa: F401  演習4で使えます

DIGITS = "0123456789abcdef"


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: 基数変換
# ---------------------------------------------------------------------------

def to_base(n: int, base: int) -> str:
    """非負整数 n を base 進数の文字列に変換する（2 <= base <= 16）。

    - 10 以上の桁は小文字の a〜f で表す。
    - n == 0 のときは "0" を返す。
    - base が範囲外、または n が負のときは ValueError を送出する。

    >>> to_base(10, 2)
    '1010'
    >>> to_base(255, 16)
    'ff'
    >>> to_base(0, 8)
    '0'

    ヒント: n を base で割った余りが、一番下の桁になる。
    """
    raise NotImplementedError("演習1: to_base を実装してください")


def from_base(s: str, base: int) -> int:
    """base 進数の文字列 s を整数に変換する（2 <= base <= 16）。

    - 英字の桁は大文字・小文字のどちらも受け付ける（"FF" も "ff" も 255）。
    - 空文字列、base 進数として使えない文字を含む場合、base が範囲外の場合は
      ValueError を送出する。

    >>> from_base("1010", 2)
    10
    >>> from_base("FF", 16)
    255

    ヒント: 上の桁から順に「これまでの値 × base + 次の桁の値」を繰り返す（ホーナー法）。
    """
    raise NotImplementedError("演習1: from_base を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★☆☆）: 2の補数
# ---------------------------------------------------------------------------

def to_twos_complement(n: int, bits: int) -> str:
    """整数 n を bits ビットの 2 の補数表現（'0'/'1' の文字列、長さ bits）に変換する。

    - bits <= 0 のときは ValueError（この検査を最初に行う）。
    - n が bits ビットの符号付き整数の範囲（-2^(bits-1) 〜 2^(bits-1)-1）外なら OverflowError。

    >>> to_twos_complement(5, 8)
    '00000101'
    >>> to_twos_complement(-1, 8)
    '11111111'
    >>> to_twos_complement(-128, 8)
    '10000000'

    ヒント: 負の数 -x は、符号なし整数 2^bits - x と同じビット列になる。
    """
    raise NotImplementedError("演習2: to_twos_complement を実装してください")


def from_twos_complement(s: str) -> int:
    """2 の補数表現のビット列 s（長さ = ビット幅）を整数に変換する。

    - 空文字列や '0'/'1' 以外の文字を含む場合は ValueError。

    >>> from_twos_complement("11111111")
    -1
    >>> from_twos_complement("0111")
    7
    >>> from_twos_complement("1000")
    -8
    """
    raise NotImplementedError("演習2: from_twos_complement を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 固定幅の加算とオーバーフロー検出
# ---------------------------------------------------------------------------

def add_signed(a: int, b: int, bits: int) -> tuple[int, bool]:
    """bits ビットの符号付き整数 a と b を、ハードウェアと同じ規則で加算する。

    戻り値は (結果, オーバーフローしたか)。
    - 結果は 2^bits を法として回り込んだ値を、符号付き整数として解釈したもの。
    - オーバーフローとは「数学的な和 a + b が bits ビットの符号付き範囲に収まらないこと」。
    - bits <= 0 なら ValueError（この検査を最初に行う）。a または b がそもそも範囲外なら OverflowError。

    >>> add_signed(100, 27, 8)
    (127, False)
    >>> add_signed(127, 1, 8)
    (-128, True)
    >>> add_signed(-128, -1, 8)
    (127, True)

    発展: 「a + b を計算してから範囲チェック」ではなく、ハードウェアのように
    「下位 bits ビットだけを残す」「符号ビットの変化でオーバーフローを判定する」
    という方法で実装してみよう。
    """
    raise NotImplementedError("演習3: add_signed を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: IEEE 754 倍精度浮動小数点数の分解と組み立て
# ---------------------------------------------------------------------------

def float_fields(x: float) -> tuple[int, int, int]:
    """倍精度浮動小数点数 x を (符号, 指数部, 仮数部) の生のビットフィールドに分解する。

    - 符号: 0 または 1（1 ビット）
    - 指数部: 0〜2047 の整数（11 ビット、バイアス 1023 を引く前の値）
    - 仮数部: 0〜2^52-1 の整数（52 ビット、暗黙の先頭 1 は含まない）

    >>> float_fields(1.0)
    (0, 1023, 0)
    >>> float_fields(-2.0)
    (1, 1024, 0)

    ヒント: struct.pack(">d", x) で 8 バイトのビッグエンディアン表現が得られる。
    それを struct.unpack(">Q", ...) で 64 ビット符号なし整数として読み直し、
    シフトとマスクで各フィールドを取り出す。
    """
    raise NotImplementedError("演習4: float_fields を実装してください")


def classify_float(x: float) -> str:
    """x の種類を "zero" / "subnormal" / "normal" / "infinity" / "nan" のいずれかで返す。

    math.isnan() などは使わず、float_fields() で得たビットフィールドから判定すること。
    （+0.0 も -0.0 も "zero"、+inf も -inf も "infinity"）
    """
    raise NotImplementedError("演習4: classify_float を実装してください")


def fields_to_float(sign: int, exponent: int, fraction: int) -> float:
    """ビットフィールドから浮動小数点数を「式に従って」組み立てる（float_fields の逆）。

    struct は使わず、IEEE 754 の定義式で値を計算すること。
    - 正規化数（1 <= exponent <= 2046）: (-1)^sign × (1 + fraction / 2^52) × 2^(exponent - 1023)
    - 非正規化数とゼロ（exponent == 0）: (-1)^sign × (fraction / 2^52) × 2^(-1022)
    - exponent == 2047: fraction == 0 なら ±無限大、それ以外は NaN
    - 各フィールドが範囲外なら ValueError

    ヒント: math.ldexp(m, e) は m × 2^e を誤差なく計算する。
    符号付きゼロ（-0.0）も正しく返すこと。
    """
    raise NotImplementedError("演習4: fields_to_float を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: UTF-8 エンコーダ／デコーダ
# ---------------------------------------------------------------------------

def utf8_encode(code_points: list[int]) -> bytes:
    """Unicode コードポイントの列を UTF-8 のバイト列に変換する。

    - 0〜0x10FFFF の範囲外、またはサロゲート（0xD800〜0xDFFF）は ValueError。

    >>> utf8_encode([0x41])
    b'A'
    >>> utf8_encode([0x3042]).hex(" ")    # 「あ」
    'e3 81 82'

    | コードポイント       | バイト列のビットパターン                     |
    |----------------------|----------------------------------------------|
    | U+0000  〜 U+007F    | 0xxxxxxx                                     |
    | U+0080  〜 U+07FF    | 110xxxxx 10xxxxxx                            |
    | U+0800  〜 U+FFFF    | 1110xxxx 10xxxxxx 10xxxxxx                   |
    | U+10000 〜 U+10FFFF  | 11110xxx 10xxxxxx 10xxxxxx 10xxxxxx          |
    """
    raise NotImplementedError("演習5: utf8_encode を実装してください")


def utf8_decode(data: bytes) -> list[int]:
    """UTF-8 のバイト列をコードポイントの列に変換する。不正なバイト列は ValueError。

    次のような不正を検出すること（Python 組み込みの厳格なデコーダと同じ判定になる）:
    - 先頭バイトとして使えないバイト（0x80〜0xBF の単独出現、0xC0、0xC1、0xF5〜0xFF）
    - 継続バイト（10xxxxxx）であるべき位置に、それ以外のバイトがある
    - 途中で途切れたシーケンス
    - 冗長な表現（overlong。例: '/' を 2 バイトで表した C0 AF）
    - サロゲート（U+D800〜U+DFFF）や U+10FFFF を超える値

    >>> utf8_decode(bytes.fromhex("e3 81 82"))
    [12354]
    """
    raise NotImplementedError("演習5: utf8_decode を実装してください")
