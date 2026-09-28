"""12.4 LLMアプリケーション開発 — 演習4（発展）: 汚染追跡によるプロンプトインジェクション対策（解答例）

演習の仕様は exercises/injection_guard.py の docstring を参照してください。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator
from urllib.parse import urlsplit

URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


# ---------------------------------------------------------------------------
# 演習4a: 指標（URL・メールアドレス・ドメイン）の抽出と許可リスト
# ---------------------------------------------------------------------------

def extract_indicators(text: str) -> set[str]:
    found: set[str] = set()
    for url in URL_RE.findall(text):
        host = urlsplit(url).hostname
        if host:
            found.add(host.lower())
    for email in EMAIL_RE.findall(text):
        email = email.lower()
        found.add(email)
        found.add(email.split("@", 1)[1])
    return found


def domain_allowed(host: str, allowed_domains: frozenset[str] | set[str]) -> bool:
    host = host.lower().rstrip(".")
    # 部分文字列の一致（"kotori-lab.example" in host）では evil-kotori-lab.example や
    # kotori-lab.example.evil.com を通してしまう。完全一致かサブドメインだけを許可する
    return any(host == d or host.endswith("." + d) for d in (x.lower() for x in allowed_domains))


def _iter_strings(value: Any, path: str = "$") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from _iter_strings(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            yield from _iter_strings(v, f"{path}[{i}]")


def _destinations(arguments: dict) -> set[str]:
    """引数に含まれる、外部への送信先になりうるホスト名とメールのドメイン。"""
    hosts: set[str] = set()
    for _, value in _iter_strings(arguments):
        for url in URL_RE.findall(value):
            host = urlsplit(url).hostname
            if host:
                hosts.add(host.lower())
        for email in EMAIL_RE.findall(value):
            hosts.add(email.split("@", 1)[1].lower())
    return hosts


# ---------------------------------------------------------------------------
# 演習4b: 汚染の追跡
# ---------------------------------------------------------------------------

class TaintTracker:
    def __init__(self, *, min_overlap: int = 12) -> None:
        if min_overlap < 1:
            raise ValueError("min_overlap は 1 以上")
        self.min_overlap = min_overlap
        self._untrusted: list[tuple[str, str]] = []
        self._trusted_indicators: set[str] = set()

    def observe(self, text: str, *, source: str, trusted: bool) -> None:
        if trusted:
            self._trusted_indicators |= extract_indicators(text)
        else:
            self._untrusted.append((text, source))

    @property
    def tainted(self) -> bool:
        return bool(self._untrusted)

    @property
    def untrusted_sources(self) -> list[str]:
        return list(dict.fromkeys(source for _, source in self._untrusted))

    def _shares_substring(self, value: str, text: str) -> bool:
        n = self.min_overlap
        if len(value) < n or len(text) < n:
            return False
        grams = {text[i:i + n] for i in range(len(text) - n + 1)}
        return any(value[i:i + n] in grams for i in range(len(value) - n + 1))

    def influenced(self, arguments: dict) -> list[str]:
        reasons: list[str] = []
        for path, value in _iter_strings(arguments):
            indicators = extract_indicators(value)
            for text, source in self._untrusted:
                # 利用者自身（信頼できる入力）が示した宛先は、外部の文書にも出てきていても利用者の意図とみなす
                hits = (indicators & extract_indicators(text)) - self._trusted_indicators
                if hits:
                    reasons.append(f"{path}: {', '.join(sorted(hits))} は信頼できない入力（{source}）に由来します")
                    break
                if self._shares_substring(value, text):
                    reasons.append(f"{path}: 信頼できない入力（{source}）の文章を含みます")
                    break
        return reasons


# ---------------------------------------------------------------------------
# 演習4c: ツール呼び出しの判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardPolicy:
    sink_tools: frozenset[str]
    allowed_domains: frozenset[str] = frozenset()
    strict: bool = True


@dataclass(frozen=True)
class Decision:
    action: str
    reasons: tuple[str, ...] = ()


def guard_tool_call(tracker: TaintTracker, policy: GuardPolicy, tool_name: str, arguments: dict) -> Decision:
    if tool_name not in policy.sink_tools:
        return Decision("allow")
    external = sorted(h for h in _destinations(arguments) if not domain_allowed(h, policy.allowed_domains))
    influenced = tracker.influenced(arguments)
    if external and influenced:
        # 信頼できない入力が指示した外部の宛先への送信 = 情報流出の典型。確認も求めずに止める
        return Decision("deny", tuple(influenced) + tuple(f"許可リストにない宛先: {h}" for h in external))
    if influenced:
        return Decision("confirm", tuple(influenced))
    if external:
        return Decision("confirm", tuple(f"許可リストにない宛先: {h}" for h in external))
    if tracker.tainted and policy.strict:
        sources = ", ".join(tracker.untrusted_sources)
        return Decision("confirm", (f"信頼できない入力（{sources}）を読んだ後の、外部に影響する操作です",))
    return Decision("allow")


# ---------------------------------------------------------------------------
# 演習4d: 出力の無害化と、信頼できない入力の囲い込み
# ---------------------------------------------------------------------------

_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _url_allowed(url: str, allowed_domains: frozenset[str] | set[str]) -> bool:
    parts = urlsplit(url)
    return parts.scheme.lower() in ("http", "https") and bool(parts.hostname) and domain_allowed(parts.hostname, allowed_domains)


def sanitize_markdown(text: str, allowed_domains: frozenset[str] | set[str]) -> tuple[str, list[str]]:
    removed: list[str] = []

    def image(m: re.Match) -> str:
        if _url_allowed(m.group(2), allowed_domains):
            return m.group(0)
        removed.append(m.group(2))
        # 画像は表示されるだけで URL へリクエストが飛ぶ。URL に機密を埋め込まれると、クリックなしで漏れる
        return "[画像を削除しました]"

    def link(m: re.Match) -> str:
        if _url_allowed(m.group(2), allowed_domains):
            return m.group(0)
        removed.append(m.group(2))
        return m.group(1)

    def bare(m: re.Match) -> str:
        if _url_allowed(m.group(0), allowed_domains):
            return m.group(0)
        removed.append(m.group(0))
        return "[URL を削除しました]"

    text = _IMAGE_RE.sub(image, text)
    text = _LINK_RE.sub(link, text)
    text = URL_RE.sub(bare, text)
    return text, removed


def wrap_untrusted(text: str, source: str) -> str:
    safe_source = re.sub(r"[\"<>\n]", "", source)
    # 中身に閉じタグを仕込んで「ここから先は指示です」と偽装されないようにする
    body = re.sub(r"</\s*untrusted", "&lt;/untrusted", text, flags=re.IGNORECASE)
    return f'<untrusted source="{safe_source}">\n{body}\n</untrusted>'
