"""5.3 DNS・HTTP・TLS — 解答例（dnsmsg）

演習の仕様は exercises/dnsmsg.py の docstring を参照してください。
DNS メッセージの形式は RFC 1035 の 4 章で定められています。
"""
from __future__ import annotations

import ipaddress
import struct
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

HEADER = struct.Struct("!HHHHHH")  # ID, フラグ, 質問数, 回答数, 権威数, 追加数


class DNSFormatError(ValueError):
    """DNS メッセージの形式が不正。"""


@dataclass
class Question:
    name: str
    qtype: int
    qclass: int = CLASS_IN


@dataclass
class ResourceRecord:
    name: str
    rtype: int
    rclass: int
    ttl: int
    data: object


@dataclass
class DNSMessage:
    id: int
    qr: bool
    opcode: int
    aa: bool
    tc: bool
    rd: bool
    ra: bool
    rcode: int
    questions: list[Question] = field(default_factory=list)
    answers: list[ResourceRecord] = field(default_factory=list)
    authorities: list[ResourceRecord] = field(default_factory=list)
    additionals: list[ResourceRecord] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 演習3: 問い合わせの組み立て
# ---------------------------------------------------------------------------

def encode_name(name: str) -> bytes:
    if name.endswith("."):
        name = name[:-1]  # 末尾のドット（ルート）は省略可能
    out = bytearray()
    if name:
        for label in name.split("."):
            raw = label.encode("ascii")  # 国際化ドメイン名は事前に Punycode（xn--…）に変換しておく
            if not 1 <= len(raw) <= 63:
                raise ValueError(f"ラベルの長さは 1〜63 バイトです: {label!r}")
            out.append(len(raw))  # ラベル = 長さ 1 バイト + 文字列
            out += raw
    out.append(0)  # 長さ 0 のラベル（ルート）で終わる
    if len(out) > 255:
        raise ValueError(f"名前が長すぎます（{len(out)} > 255 バイト）")
    return bytes(out)


def build_query(name: str, qtype: int, *, txid: int, recursion_desired: bool = True) -> bytes:
    if not 0 <= txid <= 0xFFFF:
        raise ValueError(f"ID は 16 ビットです: {txid}")
    if not 0 <= qtype <= 0xFFFF:
        raise ValueError(f"タイプは 16 ビットです: {qtype}")
    flags = 0x0100 if recursion_desired else 0  # RD（再帰を希望）ビット
    return HEADER.pack(txid, flags, 1, 0, 0, 0) + encode_name(name) + struct.pack("!HH", qtype, CLASS_IN)


# ---------------------------------------------------------------------------
# 演習3: 応答の解析
# ---------------------------------------------------------------------------

def decode_name(message: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    pos = offset
    run_start = offset  # いま読んでいるラベルの並びの先頭
    end: int | None = None  # 元の位置で、名前の直後にあたるオフセット
    wire_length = 1  # 名前全体の長さ（最後のルートの 1 バイトを含む）
    while True:
        if pos >= len(message):
            raise DNSFormatError("名前の途中でメッセージが終わっています")
        length = message[pos]
        if length & 0xC0 == 0xC0:  # 上位 2 ビットが 11 なら圧縮ポインタ
            if pos + 1 >= len(message):
                raise DNSFormatError("ポインタの途中でメッセージが終わっています")
            target = ((length & 0x3F) << 8) | message[pos + 1]
            if end is None:
                end = pos + 2  # 最初のポインタの直後が、この名前の終わり
            # ポインタは「前に出てきた名前」を指すはず。いま読んでいる並びの先頭より前だけを
            # 許せば、飛ぶたびに位置が小さくなるので、ループ（自分自身を指すポインタなど）は起きない
            if target >= run_start:
                raise DNSFormatError(f"前方または自分自身を指すポインタです: {target}")
            pos = run_start = target
            continue
        if length & 0xC0:
            raise DNSFormatError(f"未対応のラベル形式です: {length:#04x}")
        if length == 0:
            break
        start = pos + 1
        if start + length > len(message):
            raise DNSFormatError("ラベルの途中でメッセージが終わっています")
        wire_length += length + 1
        if wire_length > 255:
            raise DNSFormatError("名前が 255 バイトを超えています")
        try:
            labels.append(message[start : start + length].decode("ascii"))
        except UnicodeDecodeError:
            raise DNSFormatError("ASCII 以外のバイトを含むラベルです（この演習では扱いません）") from None
        pos = start + length
    if end is None:
        end = pos + 1
    return (".".join(labels) if labels else "."), end


def _parse_rdata(message: bytes, rtype: int, start: int, rdlength: int) -> object:
    rdata = message[start : start + rdlength]
    end = start + rdlength

    def name_at(offset: int) -> tuple[str, int]:
        name, nxt = decode_name(message, offset)
        if nxt > end:
            raise DNSFormatError("RDATA の範囲を超えた名前です")
        return name, nxt

    def expect_end(nxt: int) -> None:
        if nxt != end:
            raise DNSFormatError(f"RDATA の長さが合いません（タイプ {rtype}）")

    if rtype == TYPE_A:
        if rdlength != 4:
            raise DNSFormatError("A レコードの RDATA は 4 バイトです")
        return str(ipaddress.IPv4Address(rdata))
    if rtype == TYPE_AAAA:
        if rdlength != 16:
            raise DNSFormatError("AAAA レコードの RDATA は 16 バイトです")
        return str(ipaddress.IPv6Address(rdata))
    if rtype in (TYPE_NS, TYPE_CNAME, TYPE_PTR):
        name, nxt = name_at(start)  # RDATA の中の名前も圧縮されうるので、メッセージ全体を渡す
        expect_end(nxt)
        return name
    if rtype == TYPE_MX:
        if rdlength < 3:
            raise DNSFormatError("MX レコードが短すぎます")
        (preference,) = struct.unpack_from("!H", message, start)
        exchange, nxt = name_at(start + 2)
        expect_end(nxt)
        return preference, exchange
    if rtype == TYPE_SOA:
        mname, nxt = name_at(start)
        rname, nxt = name_at(nxt)
        if end - nxt != 20:
            raise DNSFormatError("SOA レコードの数値部分は 20 バイトです")
        return (mname, rname, *struct.unpack_from("!IIIII", message, nxt))
    if rtype == TYPE_SRV:
        if rdlength < 7:
            raise DNSFormatError("SRV レコードが短すぎます")
        priority, weight, port = struct.unpack_from("!HHH", message, start)
        target, nxt = name_at(start + 6)
        expect_end(nxt)
        return priority, weight, port, target
    if rtype == TYPE_TXT:
        strings, pos = [], 0
        while pos < rdlength:  # 長さ 1 バイト + 文字列 の <character-string> が 1 つ以上並ぶ
            n = rdata[pos]
            if pos + 1 + n > rdlength:
                raise DNSFormatError("TXT の文字列が RDATA をはみ出しています")
            strings.append(bytes(rdata[pos + 1 : pos + 1 + n]))
            pos += 1 + n
        if not strings:
            raise DNSFormatError("TXT レコードが空です")
        return tuple(strings)
    if rtype == TYPE_CAA:
        if rdlength < 2 or rdlength < 2 + rdata[1]:
            raise DNSFormatError("CAA レコードが短すぎます")
        flags, tag_len = rdata[0], rdata[1]
        tag = rdata[2 : 2 + tag_len].decode("ascii")
        return flags, tag, bytes(rdata[2 + tag_len :])
    return bytes(rdata)  # それ以外（OPT など）は生のバイト列のまま


def _parse_record(message: bytes, offset: int) -> tuple[ResourceRecord, int]:
    name, pos = decode_name(message, offset)
    if pos + 10 > len(message):
        raise DNSFormatError("リソースレコードのヘッダが途中で切れています")
    rtype, rclass, ttl, rdlength = struct.unpack_from("!HHIH", message, pos)
    pos += 10
    if pos + rdlength > len(message):
        raise DNSFormatError("RDATA が途中で切れています")
    data = _parse_rdata(message, rtype, pos, rdlength)
    return ResourceRecord(name, rtype, rclass, ttl, data), pos + rdlength


def parse_message(data: bytes) -> DNSMessage:
    if len(data) < HEADER.size:
        raise DNSFormatError("ヘッダ（12 バイト）がありません")
    txid, flags, qdcount, ancount, nscount, arcount = HEADER.unpack_from(data)
    msg = DNSMessage(
        id=txid,
        qr=bool(flags & 0x8000),
        opcode=(flags >> 11) & 0x0F,
        aa=bool(flags & 0x0400),
        tc=bool(flags & 0x0200),
        rd=bool(flags & 0x0100),
        ra=bool(flags & 0x0080),
        rcode=flags & 0x000F,
    )
    pos = HEADER.size
    for _ in range(qdcount):
        name, pos = decode_name(data, pos)
        if pos + 4 > len(data):
            raise DNSFormatError("質問が途中で切れています")
        qtype, qclass = struct.unpack_from("!HH", data, pos)
        pos += 4
        msg.questions.append(Question(name, qtype, qclass))
    for count, section in ((ancount, msg.answers), (nscount, msg.authorities), (arcount, msg.additionals)):
        for _ in range(count):
            record, pos = _parse_record(data, pos)
            section.append(record)
    if pos != len(data):
        raise DNSFormatError(f"メッセージの末尾に余分なデータがあります（{len(data) - pos} バイト）")
    return msg
