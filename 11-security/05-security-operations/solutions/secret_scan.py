"""11.5 セキュリティ運用とサプライチェーン — 解答例（secret_scan）

演習の仕様は exercises/secret_scan.py の docstring を参照してください。
テストや例で使う値はすべて「明らかに偽物」の値です（本物の鍵は絶対に載せないこと）。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

# 既知の形式の検出器: (種類, 正規表現)。具体的な形が分かるものは正規表現で確実に捕まえる
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
)

# 高エントロピー判定の対象にするトークン（base64/16進で使われる文字の並び）
_TOKEN_RE = re.compile(r"[A-Za-z0-9+/=_-]{16,}")
DEFAULT_MIN_ENTROPY = 4.0
DEFAULT_MIN_LENGTH = 20
ALLOWLIST_MARKERS = ("allowlist secret", "gitleaks:allow", "nosec", "pragma: allowlist")


@dataclass(frozen=True)
class Finding:
    line: int  # 1 始まりの行番号
    kind: str
    secret: str

    @property
    def redacted(self) -> str:
        if len(self.secret) <= 8:
            return "*" * len(self.secret)
        return f"{self.secret[:4]}...{self.secret[-2:]}"


# ---------------------------------------------------------------------------
# 演習1: シャノンエントロピー
# ---------------------------------------------------------------------------

def shannon_entropy(text: str) -> float:
    """文字列の 1 文字あたりのシャノンエントロピー（ビット）を返す。空文字列は 0.0。"""
    if not text:
        return 0.0
    n = len(text)
    counts = Counter(text)
    entropy = -sum((c / n) * math.log2(c / n) for c in counts.values())
    return entropy + 0.0  # -0.0 を 0.0 に正規化する


# ---------------------------------------------------------------------------
# 演習2: 行の走査
# ---------------------------------------------------------------------------

def is_allowlisted(line: str, markers: tuple[str, ...] = ALLOWLIST_MARKERS) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in markers)


def scan_line(
    line: str,
    lineno: int,
    *,
    min_entropy: float = DEFAULT_MIN_ENTROPY,
    min_length: int = DEFAULT_MIN_LENGTH,
    markers: tuple[str, ...] = ALLOWLIST_MARKERS,
) -> list[Finding]:
    """1 行を走査して Finding のリストを返す。許可コメントがある行は空リスト。"""
    if is_allowlisted(line, markers):
        return []
    findings: list[Finding] = []
    seen_spans: list[tuple[int, int]] = []
    # 1. 既知の形式（確実性が高いので先に取り、後の重複判定に使う）
    for kind, pattern in PATTERNS:
        for m in pattern.finditer(line):
            findings.append(Finding(lineno, kind, m.group(0)))
            seen_spans.append((m.start(), m.end()))
    # 2. 一般的な高エントロピー文字列
    for m in _TOKEN_RE.finditer(line):
        token = m.group(0)
        if len(token) < min_length:
            continue
        # 既知の形式で報告済みの範囲と重なるものは二重に数えない
        if any(m.start() < end and start < m.end() for start, end in seen_spans):
            continue
        if shannon_entropy(token) >= min_entropy:
            findings.append(Finding(lineno, "high-entropy", token))
    return findings


def scan_text(
    text: str,
    *,
    min_entropy: float = DEFAULT_MIN_ENTROPY,
    min_length: int = DEFAULT_MIN_LENGTH,
    markers: tuple[str, ...] = ALLOWLIST_MARKERS,
) -> list[Finding]:
    """複数行のテキストを走査する。結果は出現順（行番号順）で返す。"""
    findings: list[Finding] = []
    for i, line in enumerate(text.splitlines(), start=1):
        findings.extend(scan_line(line, i, min_entropy=min_entropy, min_length=min_length, markers=markers))
    return findings
