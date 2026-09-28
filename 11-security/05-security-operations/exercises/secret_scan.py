"""11.5 セキュリティ運用とサプライチェーン — 演習（secret_scan）

ソースコードや設定ファイルに紛れ込んだ秘密情報（API キー・トークン・秘密鍵）を検出する
スキャナを作ります。CI に組み込んで「秘密をコミットさせない」ために使う類のツールです。
2 つの見つけ方を組み合わせます。
  - 既知の形式を正規表現で確実に捕まえる（AWS のアクセスキー ID、GitHub トークン、秘密鍵ヘッダ）
  - 「ランダムに見える文字列」をシャノンエントロピーで捕まえる（形式が分からない秘密のため）

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.5
    python3 tools/check.py -v 11.5

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_secret_scan

★注意★ テストや例で使う値はすべて「明らかに偽物」の値です。本物の鍵やトークンを
コードやテストに書いてはいけません（それ自体が漏えいです）。
"""
from __future__ import annotations

import math  # noqa: F401
import re
from collections import Counter  # noqa: F401
from dataclasses import dataclass

# 既知の形式の検出器: (種類, 正規表現)
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
)

# 高エントロピー判定の対象にするトークン（base64/16進で使われる文字が 16 文字以上続くもの）
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
        """ログや報告に出すための伏字。8 文字以下は全部伏せ、長いものは先頭 4 文字 + "..." + 末尾 2 文字。"""
        raise NotImplementedError("演習2: Finding.redacted を実装してください")


# ---------------------------------------------------------------------------
# 演習1（★☆☆相当）: シャノンエントロピー
# ---------------------------------------------------------------------------

def shannon_entropy(text: str) -> float:
    """文字列の 1 文字あたりのシャノンエントロピー（ビット）を返す。

    定義: 各文字 c の出現確率を p(c) とすると、H = -Σ p(c) * log2 p(c)。
    - 空文字列は 0.0。
    - すべて同じ文字なら 0.0（-0.0 ではなく +0.0 を返すこと。ヒント: 最後に + 0.0）。

    >>> round(shannon_entropy("0123"), 3)
    2.0
    """
    raise NotImplementedError("演習1: shannon_entropy を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆相当）: 行の走査
# ---------------------------------------------------------------------------

def is_allowlisted(line: str, markers: tuple[str, ...] = ALLOWLIST_MARKERS) -> bool:
    """行に許可コメント（markers のいずれか。大文字小文字は無視）が含まれれば True。"""
    raise NotImplementedError("演習2: is_allowlisted を実装してください")


def scan_line(
    line: str,
    lineno: int,
    *,
    min_entropy: float = DEFAULT_MIN_ENTROPY,
    min_length: int = DEFAULT_MIN_LENGTH,
    markers: tuple[str, ...] = ALLOWLIST_MARKERS,
) -> list[Finding]:
    """1 行を走査して Finding のリストを返す。

    - 許可コメントのある行（is_allowlisted）は空リストを返す。
    - まず PATTERNS の各正規表現で既知の形式を検出する（種類はタプルの 1 要素目）。
    - 次に _TOKEN_RE で取り出したトークンのうち、長さが min_length 以上で
      shannon_entropy が min_entropy 以上のものを "high-entropy" として検出する。
      ただし、既に既知の形式で報告した文字位置と重なるトークンは二重に報告しない。
    - Finding.line は lineno。既知の形式 → 高エントロピーの順で返す。
    """
    raise NotImplementedError("演習2: scan_line を実装してください")


def scan_text(
    text: str,
    *,
    min_entropy: float = DEFAULT_MIN_ENTROPY,
    min_length: int = DEFAULT_MIN_LENGTH,
    markers: tuple[str, ...] = ALLOWLIST_MARKERS,
) -> list[Finding]:
    """複数行のテキストを 1 行ずつ scan_line し、出現順（行番号順）に Finding を返す。

    行番号は 1 から始まる（text.splitlines() を enumerate(..., start=1) で回すとよい）。
    """
    raise NotImplementedError("演習2: scan_text を実装してください")
