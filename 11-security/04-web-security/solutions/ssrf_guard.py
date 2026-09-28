"""11.4 Webアプリケーションセキュリティ — 解答例（ssrf_guard）

演習の仕様は exercises/ssrf_guard.py の docstring を参照してください。
"""
from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit

Resolver = Callable[[str], list[str]]

ALLOWED_SCHEMES = frozenset({"http", "https"})
_HOSTNAME_RE = re.compile(r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*\.?")


class SsrfError(ValueError):
    """URL が SSRF 対策のポリシーに反することを表す。"""


@dataclass(frozen=True)
class SafeURL:
    url: str
    scheme: str
    host: str
    port: int
    addresses: tuple[str, ...]  # 解決された（安全と判定された）宛先 IP


# ---------------------------------------------------------------------------
# 演習1: IP アドレスの分類
# ---------------------------------------------------------------------------

def parse_loose_ipv4(host: str) -> str | None:
    """C の inet_aton と同じ規則で、10 進・16 進・8 進や省略記法の IPv4 を解釈する。

    IP として解釈できれば正規の "a.b.c.d" を、できなければ None を返す。
    攻撃者はこの「緩い」記法で検査をすり抜けようとするので、防御側も同じ解釈を再現する。
    """
    parts = host.split(".")
    if not 1 <= len(parts) <= 4:
        return None
    nums: list[int] = []
    for p in parts:
        if not p or not p.isascii():
            return None
        s = p.lower()
        try:
            if s.startswith("0x"):
                v = int(s[2:], 16) if len(s) > 2 else -1
            elif s.startswith("0") and len(s) > 1:
                v = int(s, 8)
            else:
                v = int(s, 10)
        except ValueError:
            return None
        if v < 0:
            return None
        nums.append(v)
    # 先頭のパートは 1 バイトずつ、最後のパートが残りのバイトをすべて受け持つ
    if any(v > 0xFF for v in nums[:-1]):
        return None
    lead = nums[:-1]
    if nums[-1] > 256 ** (4 - len(lead)) - 1:
        return None
    value = 0
    for v in lead:
        value = (value << 8) | v
    value = (value << (8 * (4 - len(lead)))) | nums[-1]
    return str(ipaddress.IPv4Address(value))


def classify_address(ip_str: str) -> str:
    """IP 文字列を分類する。安全に外部へ出せるなら "global"、それ以外はブロック理由を返す。

    IPv4 射影 IPv6（::ffff:127.0.0.1 など）は中の IPv4 に開いてから判定する。
    """
    ip = ipaddress.ip_address(ip_str)  # 標準表記でなければ ValueError
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return classify_address(str(mapped))
    # 6to4（2002::/16）や Teredo（2001::/32）に埋め込まれた IPv4 も開いて調べるのが本来は望ましい
    if ip.is_unspecified:
        return "unspecified"  # 0.0.0.0 / ::
    if ip.is_loopback:
        return "loopback"  # 127.0.0.0/8, ::1
    if ip.is_link_local:
        return "link-local"  # 169.254.0.0/16（クラウドのメタデータ 169.254.169.254 を含む）, fe80::/10
    if ip.is_multicast:
        return "multicast"
    if ip.is_private:
        return "private"  # 10/8, 172.16/12, 192.168/16, fc00::/7, など
    if ip.is_reserved:
        return "reserved"
    if ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"):
        return "shared"  # キャリアグレード NAT（CGNAT）。is_private では捕まらない
    return "global"


def is_safe_address(ip_str: str) -> bool:
    return classify_address(ip_str) == "global"


# ---------------------------------------------------------------------------
# 演習2: ホスト名の解決とブロック
# ---------------------------------------------------------------------------

def _resolve_host(host: str, resolver: Resolver) -> list[str]:
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]  # IPv6 リテラルの角括弧
    # 1. まず標準表記の IP リテラルか
    try:
        return [str(ipaddress.ip_address(host))]
    except ValueError:
        pass
    # 2. 緩い記法の IPv4（2130706433 など）は、正規化してから IP として扱う（DNS は引かない）
    loose = parse_loose_ipv4(host)
    if loose is not None:
        return [loose]
    # 3. DNS 名として構文を検査してから解決する
    if not _HOSTNAME_RE.fullmatch(host):
        raise SsrfError(f"ホスト名の形式が不正です: {host!r}")
    if host.rstrip(".").rsplit(".", 1)[-1].isdigit():
        # 一番右のラベルが全部数字の名前は、リゾルバによって数値 IP と解釈されうる
        raise SsrfError(f"数値のように見えるホスト名は拒否します: {host!r}")
    addrs = resolver(host)
    if not addrs:
        raise SsrfError(f"名前を解決できませんでした: {host!r}")
    return addrs


def validate_url(url: str, resolver: Resolver, *, allowed_schemes: frozenset[str] = ALLOWED_SCHEMES) -> SafeURL:
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise SsrfError(f"URL を解釈できません: {exc}") from exc
    if parts.scheme.lower() not in allowed_schemes:
        raise SsrfError(f"許可されていないスキームです: {parts.scheme!r}")
    host = parts.hostname  # urlsplit が小文字化・角括弧の除去をしてくれる
    if not host:
        raise SsrfError("ホストがありません")
    if parts.username or parts.password:
        # user:pass@host 記法は「@ の前を本物のホストだと錯覚させる」細工に使われる
        raise SsrfError("認証情報付きの URL は許可しません")
    try:
        port = parts.port if parts.port is not None else (443 if parts.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise SsrfError(f"ポート番号が不正です: {exc}") from exc

    addresses = _resolve_host(host, resolver)
    for ip in addresses:
        reason = classify_address(ip)
        if reason != "global":
            # 解決されたどれか 1 つでも内部向けなら拒否する
            raise SsrfError(f"内部向けのアドレスへの接続は禁止です（{host} → {ip}: {reason}）")
    return SafeURL(url, parts.scheme.lower(), host, port, tuple(addresses))


# ---------------------------------------------------------------------------
# 演習3: リダイレクトの再検査
# ---------------------------------------------------------------------------

def validate_redirect_chain(
    initial_url: str,
    redirects: list[str],
    resolver: Resolver,
    *,
    allowed_schemes: frozenset[str] = ALLOWED_SCHEMES,
    max_redirects: int = 5,
) -> list[SafeURL]:
    """最初の URL と、その後のリダイレクト先を **1 つずつ再検査** する。

    最初の URL だけを検査して以後のリダイレクトを信用すると、外部の安全な URL から
    169.254.169.254 へ 302 で飛ばす、という古典的なすり抜けを許してしまう。
    """
    if len(redirects) > max_redirects:
        raise SsrfError(f"リダイレクトが多すぎます（上限 {max_redirects}）")
    chain = [validate_url(initial_url, resolver, allowed_schemes=allowed_schemes)]
    for location in redirects:
        chain.append(validate_url(location, resolver, allowed_schemes=allowed_schemes))
    return chain
