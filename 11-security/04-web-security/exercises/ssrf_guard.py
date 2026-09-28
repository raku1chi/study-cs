"""11.4 Webアプリケーションセキュリティ — 演習（ssrf_guard）

SSRF（Server-Side Request Forgery, サーバーサイドリクエストフォージェリ）を防ぐ URL 検証器を作ります。
「ユーザーが指定した URL をサーバーが取りに行く」機能（画像の取り込み、Webhook、URL プレビューなど）は、
細工された URL でクラウドのメタデータ（169.254.169.254）や社内ネットワークに接続させられる危険があります。

作るもの:
  - 演習1: IP アドレスの分類（内部向けか、外部に出してよいか）と、緩い記法の IPv4 の正規化
  - 演習2: URL を解析し、ホストを（注入した）リゾルバで解決して、内部向けなら拒否する
  - 演習3: リダイレクト先を 1 つずつ再検査する

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.4
    python3 tools/check.py -v 11.4

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_ssrf_guard

設計の方針（この演習での決定）:
  - 名前解決は **引数で渡されるリゾルバ**（host -> IP 文字列のリスト）で行います。テストを
    ネットワークなしで決定的にするためです。本番では resolver を「実際に接続する IP を返し、
    かつ結果をピン留めする」実装にします（DNS リバインディング対策）。
  - 「緩い」IPv4 記法（10 進の 2130706433、16 進の 0x7f000001、8 進の 0177.0.0.1）は
    **正規化して** IP として分類します（拒否ではなく正規化を選ぶのは、攻撃者がこれらで
    127.0.0.1 に到達しようとする仕組みを、防御側でも同じ解釈で捕まえるためです）。
"""
from __future__ import annotations

import ipaddress
import re  # noqa: F401
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlsplit  # noqa: F401

Resolver = Callable[[str], list[str]]

ALLOWED_SCHEMES = frozenset({"http", "https"})


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
# 演習1（★★☆相当）: IP アドレスの分類
# ---------------------------------------------------------------------------

def parse_loose_ipv4(host: str) -> str | None:
    """C の inet_aton と同じ規則で、10 進・16 進・8 進や省略記法の IPv4 を解釈する。

    IP として解釈できれば正規の "a.b.c.d" を、できなければ None を返す。

    規則: '.' で 1〜4 個のパートに分ける。各パートは、0x で始まれば 16 進、0 で始まり
    2 文字以上なら 8 進、それ以外は 10 進。先頭のパートは 1 バイト（0〜255）ずつ、
    最後のパートが残りのバイトをすべて受け持つ（4 パートなら各 1 バイト、1 パートなら 32 ビット全体）。
    各パートが受け持てる範囲を超えたら None。

    >>> parse_loose_ipv4("2130706433"), parse_loose_ipv4("0x7f000001"), parse_loose_ipv4("127.1")
    ('127.0.0.1', '127.0.0.1', '127.0.0.1')
    """
    raise NotImplementedError("演習1: parse_loose_ipv4 を実装してください")


def classify_address(ip_str: str) -> str:
    """IP 文字列を分類する。外部に出してよいなら "global"、内部向けならその理由を返す。

    理由の文字列（この順で優先して判定する）:
      "unspecified"（0.0.0.0, ::）/ "loopback"（127.0.0.0/8, ::1）/
      "link-local"（169.254.0.0/16, fe80::/10。クラウドのメタデータを含む）/
      "multicast" / "private"（10/8, 172.16/12, 192.168/16, fc00::/7 など）/
      "reserved" / "shared"（100.64.0.0/10 の CGNAT）/ "global"

    重要: IPv4 射影 IPv6（例 ::ffff:127.0.0.1）は、中の IPv4 アドレスに開いてから分類し直すこと。
    ipaddress モジュールの ip.is_loopback / is_private / is_link_local などが使えます
    （ip_str が標準表記でなければ ValueError のままでよい）。
    """
    raise NotImplementedError("演習1: classify_address を実装してください")


def is_safe_address(ip_str: str) -> bool:
    """classify_address が "global" なら True。"""
    raise NotImplementedError("演習1: is_safe_address を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★★）: ホスト名の解決とブロック
# ---------------------------------------------------------------------------

def validate_url(url: str, resolver: Resolver, *, allowed_schemes: frozenset[str] = ALLOWED_SCHEMES) -> SafeURL:
    """url を検証し、安全なら SafeURL を返す。ポリシー違反なら SsrfError。

    手順:
      1. urlsplit で分解する（解釈できなければ SsrfError）。
      2. スキーム（小文字化）が allowed_schemes になければ SsrfError。
      3. ホスト（parts.hostname。urlsplit が小文字化と IPv6 の角括弧の除去をする）が空なら SsrfError。
      4. ユーザー情報（parts.username / parts.password）があれば SsrfError
         （user@host 記法で本物のホストを錯覚させる細工に使われる）。
      5. ポート（なければ https:443 / http:80）。不正なら SsrfError。
      6. ホストを IP に解決する:
           - 標準表記の IP リテラルならそれを使う（DNS は引かない）
           - parse_loose_ipv4 で解釈できればそれを使う（DNS は引かない）
           - それ以外は DNS 名として構文検査し（不正なら SsrfError）、resolver(host) で解決する。
             一番右のラベルが全部数字の名前は拒否する（数値 IP と解釈されうるため）。
             解決結果が空なら SsrfError。
      7. 解決されたすべての IP を classify_address で調べ、1 つでも "global" でなければ SsrfError。
      8. SafeURL(url, スキーム, host, port, 解決された IP のタプル) を返す。
    """
    raise NotImplementedError("演習2: validate_url を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★☆☆相当）: リダイレクトの再検査
# ---------------------------------------------------------------------------

def validate_redirect_chain(
    initial_url: str,
    redirects: list[str],
    resolver: Resolver,
    *,
    allowed_schemes: frozenset[str] = ALLOWED_SCHEMES,
    max_redirects: int = 5,
) -> list[SafeURL]:
    """最初の URL と、各リダイレクト先を 1 つずつ validate_url で再検査し、SafeURL のリストを返す。

    - redirects の数が max_redirects を超えたら SsrfError。
    - どれか 1 つでも検証に失敗したら、その SsrfError をそのまま送出する。

    最初の URL だけ検査して以後のリダイレクトを信用すると、「入口は公開 URL、302 の
    Location が 169.254.169.254」というすり抜けを許してしまう。だから毎回検査する。
    """
    raise NotImplementedError("演習3: validate_redirect_chain を実装してください")
