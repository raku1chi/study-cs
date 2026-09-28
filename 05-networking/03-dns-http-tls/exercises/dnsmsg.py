"""5.3 DNS・HTTP・TLS — 演習（dnsmsg）: DNS メッセージの組み立てと解析

DNS の問い合わせと応答は、RFC 1035 の 4 章で定められたバイナリ形式のメッセージです。
この演習では、問い合わせを組み立て、応答（data/*.hex に保存した実物と同じ形式のバイト列）を
解析します。特に、名前の「圧縮ポインタ」を安全に扱うことが山場です。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 5.3
    python3 tools/check.py -v 5.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_dnsmsg

使ってよいもの: struct（数値の変換）、ipaddress（A・AAAA のアドレスの文字列化）。

メッセージの構造:

    ヘッダ（12 バイト）: ID(2) フラグ(2) 質問数(2) 回答数(2) 権威数(2) 追加数(2)
        フラグ（16 ビット、上位から）: QR(1) OPCODE(4) AA(1) TC(1) RD(1) RA(1) Z(3) RCODE(4)
    質問セクション: 名前 ＋ タイプ(2) ＋ クラス(2) が「質問数」個
    回答・権威・追加セクション: リソースレコードがそれぞれの個数だけ
        リソースレコード = 名前 ＋ タイプ(2) クラス(2) TTL(4) RDATA の長さ(2) ＋ RDATA

名前の形式: ラベル（長さ 1 バイト ＋ 文字列）を並べ、長さ 0 のラベル（ルート）で終わる。
    "www.example.com" → 03 77 77 77 07 65 78 61 6d 70 6c 65 03 63 6f 6d 00
    長さのバイトの上位 2 ビットが 11 なら「圧縮ポインタ」: 次の 1 バイトと合わせた下位 14 ビットが、
    メッセージの先頭からのオフセット。名前の残りはそのオフセットから読む。
    例: c0 0c → オフセット 12 にある名前を続きとして読む（その先にさらにポインタがあってもよい）。
"""
from __future__ import annotations

import ipaddress  # noqa: F401
import struct  # noqa: F401
from dataclasses import dataclass, field

TYPE_A = 1
TYPE_NS = 2
TYPE_CNAME = 5
TYPE_SOA = 6
TYPE_PTR = 12
TYPE_MX = 15
TYPE_TXT = 16
TYPE_AAAA = 28
TYPE_SRV = 33
TYPE_OPT = 41
TYPE_ANY = 255
TYPE_CAA = 257
CLASS_IN = 1

RCODE_NOERROR = 0
RCODE_FORMERR = 1
RCODE_SERVFAIL = 2
RCODE_NXDOMAIN = 3


class DNSFormatError(ValueError):
    """DNS メッセージの形式が不正（実装済み）。"""


@dataclass
class Question:
    """質問セクションの 1 項目（実装済み）。"""

    name: str
    qtype: int
    qclass: int = CLASS_IN


@dataclass
class ResourceRecord:
    """リソースレコード（実装済み）。data は RDATA をタイプに応じて解釈したもの（parse_message を参照）。"""

    name: str
    rtype: int
    rclass: int
    ttl: int
    data: object


@dataclass
class DNSMessage:
    """DNS メッセージ（実装済み）。"""

    id: int
    qr: bool  # True なら応答
    opcode: int
    aa: bool  # 権威のある応答
    tc: bool  # 切り詰められた（TCP で問い合わせ直すべき）
    rd: bool  # 再帰を希望
    ra: bool  # 再帰が可能
    rcode: int  # 0: 成功、3: 名前が存在しない（NXDOMAIN）など
    questions: list[Question] = field(default_factory=list)
    answers: list[ResourceRecord] = field(default_factory=list)
    authorities: list[ResourceRecord] = field(default_factory=list)
    additionals: list[ResourceRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 演習3（★★★）: 問い合わせの組み立て
# ---------------------------------------------------------------------------

def encode_name(name: str) -> bytes:
    """ドメイン名を DNS の形式（圧縮なし）にする。

    - 末尾の "." はあってもなくてもよい。"" と "." はルート（b"\\x00"）。
    - 各ラベルは ASCII で 1〜63 バイト。空のラベル（"a..b" や先頭の "."）・64 バイト以上・
      ASCII 以外（国際化ドメイン名は事前に Punycode に変換する）は ValueError。
    - 全体（最後の 0 を含む）が 255 バイトを超えたら ValueError。

    >>> encode_name("example.com")
    b'\\x07example\\x03com\\x00'
    """
    raise NotImplementedError("演習3: encode_name を実装してください")


def build_query(name: str, qtype: int, *, txid: int, recursion_desired: bool = True) -> bytes:
    """問い合わせのメッセージを作る。

    - ヘッダ: ID = txid、フラグは recursion_desired なら 0x0100（RD ビットだけ）、そうでなければ 0。
      質問数 1、ほかの数は 0。
    - 質問: encode_name(name) ＋ タイプ ＋ クラス IN（1）。
    - txid・qtype が 16 ビットの範囲外なら ValueError。

    >>> build_query("example.com", TYPE_A, txid=0x1234).hex(" ")
    '12 34 01 00 00 01 00 00 00 00 00 00 07 65 78 61 6d 70 6c 65 03 63 6f 6d 00 00 01 00 01'
    """
    raise NotImplementedError("演習3: build_query を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）: 応答の解析
# ---------------------------------------------------------------------------

def decode_name(message: bytes, offset: int) -> tuple[str, int]:
    """message の offset から始まる名前を読み、(名前, 名前の直後のオフセット) を返す。

    - 名前はラベルをドットでつないだ文字列（末尾のドットなし）。ルートだけなら "."。
    - 「直後のオフセット」は、元の位置で名前が占めていたバイトの次。圧縮ポインタが現れたら、
      最初のポインタ（2 バイト）の直後になる（ポインタの先で読んだ分は数えない）。
    - ラベルは ASCII として解釈する。ASCII 以外を含むラベルは DNSFormatError（簡略化）。

    次の場合は DNSFormatError（IndexError などを漏らさないこと）:
        - 名前の途中でメッセージが終わる（ラベルやポインタが途中で切れている）
        - 長さのバイトの上位 2 ビットが 01 または 10（予約済みのラベル形式）
        - 名前全体の長さが 255 バイトを超える
        - **圧縮ポインタのループ**: 悪意のあるメッセージは、自分自身や互いを指すポインタで
          素朴なパーサを無限ループさせられる。ポインタは「前に出てきた名前」を指すものなので、
          「いま読んでいるラベルの並びの先頭より前」を指すポインタだけを許すこと。
          そうすれば、ポインタをたどるたびに位置が必ず小さくなり、ループは起こりえない。

    >>> msg = bytes(12) + b"\\x03www\\x07example\\x03com\\x00" + b"\\x03api\\xc0\\x10"
    >>> decode_name(msg, 12)
    ('www.example.com', 29)
    >>> decode_name(msg, 29)     # "api" ＋ オフセット 16（example.com）へのポインタ
    ('api.example.com', 35)
    """
    raise NotImplementedError("演習3: decode_name を実装してください")


def parse_message(data: bytes) -> DNSMessage:
    """DNS メッセージを解析する。

    - ヘッダのフラグを各フィールドに分解し、質問・回答・権威・追加の各セクションを、
      ヘッダに書かれた個数だけ読む。
    - リソースレコードの data は、タイプに応じて次の形にする（RDATA の中の名前も圧縮されうるので、
      decode_name にはメッセージ全体を渡すこと）:

        A      "192.0.2.10"（文字列）              AAAA   "2001:db8::25"（ipaddress による正規形）
        NS, CNAME, PTR  名前（文字列）
        MX     (優先度, 名前)
        SOA    (MNAME, RNAME, SERIAL, REFRESH, RETRY, EXPIRE, MINIMUM)
        SRV    (優先度, 重み, ポート, ターゲット名)
        TXT    (bytes, ...)  … 長さ 1 バイト＋文字列 が 1 つ以上並んだもの。各文字列を bytes で
        CAA    (フラグ, タグ（文字列）, 値（bytes）) … フラグ 1 バイト、タグの長さ 1 バイト、タグ、値
        それ以外（OPT など）  RDATA の bytes そのまま

    次の場合は DNSFormatError:
        - ヘッダが 12 バイトない、各セクションや RDATA の途中でメッセージが終わる
        - RDATA の長さとタイプの形式が合わない（A が 4 バイトでない、名前が RDATA からはみ出す、
          MX・SRV などで名前の後ろに余りがある など）
        - 最後のレコードの後ろに余分なバイトがある

    >>> m = parse_message(build_query("example.com", TYPE_A, txid=1))
    >>> (m.id, m.qr, m.rd, m.questions)
    (1, False, True, [Question(name='example.com', qtype=1, qclass=1)])
    """
    raise NotImplementedError("演習3: parse_message を実装してください")
