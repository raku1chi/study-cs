"""12.4 LLMアプリケーション開発 — 演習4（発展・★★★）: 汚染追跡によるプロンプトインジェクション対策

LLM エージェントが Web ページやメールなどの「信頼できない入力」を読むと、その中に仕込まれた指示
（間接プロンプトインジェクション）に従ってしまうことがあります。プロンプトの工夫だけでは確実に防げないので、
**モデルの外側** で、ツール呼び出しを決定的なルールで検査します。

    1. 汚染（taint）の追跡: どの入力が信頼できないかを記録し、ツールの引数がそこに由来するかを調べる
    2. 判定: 外部に情報を出す・副作用のあるツール（sink）の呼び出しを、allow / confirm / deny に振り分ける
    3. 出力の無害化: モデルの出力に含まれる、許可されていない宛先への画像・リンク・URL を取り除く
       （Markdown の画像は表示されるだけで URL にリクエストが飛ぶので、URL に機密を埋め込まれると漏れる）
    4. 信頼できない入力の囲い込み: 区切りのタグを偽装されないように包む

これは「完全な防御」ではなく、被害を限定する多層防御の 1 層です（本文 5 節を参照）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 12.4
このディレクトリで直接実行する場合:
    python3 -m unittest -v test_injection_guard
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator  # noqa: F401
from urllib.parse import urlsplit  # noqa: F401  ホスト名の取り出しに使えます

# URL とメールアドレスの正規表現（実装済み。簡略化したもので、すべての形式を網羅するものではない）
URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")


# ---------------------------------------------------------------------------
# 演習4a: 指標（URL・メールアドレス・ドメイン）の抽出と許可リスト
# ---------------------------------------------------------------------------

def extract_indicators(text: str) -> set[str]:
    """text に含まれる「宛先の指標」の集合を返す（すべて小文字）。

    - URL_RE に一致する各 URL のホスト名（urlsplit(url).hostname）
    - EMAIL_RE に一致する各メールアドレスと、その @ より後ろのドメイン

    >>> sorted(extract_indicators("Boss@Kotori-Lab.example / https://docs.kotori-lab.example/a"))
    ['boss@kotori-lab.example', 'docs.kotori-lab.example', 'kotori-lab.example']
    """
    raise NotImplementedError("演習4a: extract_indicators を実装してください")


def domain_allowed(host: str, allowed_domains: frozenset[str] | set[str]) -> bool:
    """host が許可リストのドメインそのもの、またはそのサブドメインなら True（大文字小文字は区別しない）。

    注意: "kotori-lab.example" in host のような部分一致は、evil-kotori-lab.example や
    kotori-lab.example.evil.com を許してしまう。「完全一致」か「. + ドメイン で終わる」で判定する。
    """
    raise NotImplementedError("演習4a: domain_allowed を実装してください")


# ---------------------------------------------------------------------------
# 演習4b: 汚染の追跡
# ---------------------------------------------------------------------------

class TaintTracker:
    """エージェントが読んだ入力を、信頼できるもの（利用者の依頼など）と信頼できないもの
    （Web ページ・受信メール・ツールの出力など）に分けて記録する。

    - min_overlap < 1 なら ValueError。
    - observe(text, source=..., trusted=...) で記録する。
    - tainted: 信頼できない入力を 1 つでも読んだら True。
    - untrusted_sources: 信頼できない入力の source を、重複なし・読んだ順で返す。
    """

    def __init__(self, *, min_overlap: int = 12) -> None:
        raise NotImplementedError("演習4b: TaintTracker.__init__ を実装してください")

    def observe(self, text: str, *, source: str, trusted: bool) -> None:
        raise NotImplementedError("演習4b: TaintTracker.observe を実装してください")

    @property
    def tainted(self) -> bool:
        raise NotImplementedError("演習4b: TaintTracker.tainted を実装してください")

    @property
    def untrusted_sources(self) -> list[str]:
        raise NotImplementedError("演習4b: TaintTracker.untrusted_sources を実装してください")

    def influenced(self, arguments: dict) -> list[str]:
        """ツールの引数のうち、信頼できない入力に由来すると疑われるものの説明のリスト（なければ空）。

        引数の中の文字列を再帰的にたどり（dict は "$.key"、list は "$.key[0]" のようなパスで表す）、
        各文字列 value と各信頼できない入力 text について、次のどちらかなら「由来する」とみなす:
          (1) extract_indicators(value) と extract_indicators(text) の共通部分から、
              信頼できる入力に現れた指標を除いたものが空でない（利用者自身が指定した宛先は数えない）
          (2) value と text に、長さ min_overlap 以上の共通の部分文字列がある。
              ただし、その部分文字列が信頼できる入力にも現れる場合は数えない
        1 つの文字列につき、最初に見つかった信頼できない入力について 1 件だけ説明を追加する。
        説明には、引数のパス（例: "$.to"）と、入力の source（例: "web:travel-summary"）を含めること。
        """
        raise NotImplementedError("演習4b: TaintTracker.influenced を実装してください")


# ---------------------------------------------------------------------------
# 演習4c: ツール呼び出しの判定
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GuardPolicy:
    """判定の方針（実装済み）。

    sink_tools: 外部に情報を出す・副作用のあるツールの名前（メール送信、HTTP の POST など）
    allowed_domains: 送信してよい宛先のドメイン（自社のドメインなど）
    strict: True なら、信頼できない入力を読んだ後の sink の呼び出しは、すべて人の確認を求める
    """

    sink_tools: frozenset[str]
    allowed_domains: frozenset[str] = frozenset()
    strict: bool = True


@dataclass(frozen=True)
class Decision:
    """判定の結果（実装済み）。action は "allow" / "confirm" / "deny"。"""

    action: str
    reasons: tuple[str, ...] = ()


def guard_tool_call(tracker: TaintTracker, policy: GuardPolicy, tool_name: str, arguments: dict) -> Decision:
    """ツール呼び出しを判定する。上から順に最初に当てはまるものを返す:

    1. sink でないツール → allow
    2. 外部の宛先（引数の文字列に含まれる URL のホスト名とメールのドメインのうち、許可リストにないもの）があり、
       かつ tracker.influenced(arguments) が空でない → deny（信頼できない入力が指示した外部への送信 = 情報流出の典型）
    3. influenced が空でない → confirm（理由に influenced の説明を入れる）
    4. 外部の宛先がある → confirm（理由に宛先のホスト名を含める）
    5. tracker.tainted かつ policy.strict → confirm（理由に信頼できない入力の source を含める）
    6. それ以外 → allow
    """
    raise NotImplementedError("演習4c: guard_tool_call を実装してください")


# ---------------------------------------------------------------------------
# 演習4d: 出力の無害化と、信頼できない入力の囲い込み
# ---------------------------------------------------------------------------

def sanitize_markdown(text: str, allowed_domains: frozenset[str] | set[str]) -> tuple[str, list[str]]:
    """モデルの出力（Markdown）から、許可されていない宛先の画像・リンク・URL を取り除く。

    許可される URL: スキームが http / https で、ホスト名が domain_allowed を満たすもの。
    次の順に処理し、(無害化した文字列, 取り除いた URL のリスト（見つけた順）) を返す:
      1. 画像 ![代替テキスト](URL) → 許可されなければ "[画像を削除しました]" に置き換える
      2. リンク [テキスト](URL) → 許可されなければ テキスト だけにする
      3. 残りの生の URL（URL_RE）→ 許可されなければ "[URL を削除しました]" に置き換える
    ヒント: re.sub の置き換えに関数を渡すと、一致ごとに判定できる。
    画像とリンクの正規表現の例: r'!\\[([^\\]]*)\\]\\(([^)\\s]+)(?:\\s+"[^"]*")?\\)'（リンクは先頭の ! を除く）
    """
    raise NotImplementedError("演習4d: sanitize_markdown を実装してください")


def wrap_untrusted(text: str, source: str) -> str:
    """信頼できない入力を、モデルに渡すために次の形で包む:

        <untrusted source="{source}">
        {text}
        </untrusted>

    - source からは " < > と改行を取り除く。
    - text の中の "</untrusted"（大文字小文字を問わない。"</ untrusted" のような空白も含む）は
      "&lt;/untrusted" に置き換え、閉じタグを偽装されないようにする。
    """
    raise NotImplementedError("演習4d: wrap_untrusted を実装してください")
