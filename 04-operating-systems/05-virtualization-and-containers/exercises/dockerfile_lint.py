"""4.5 仮想化とコンテナ — 演習1: Dockerfile のベストプラクティスを検査するリンター

Dockerfile を解析し、よくある問題（タグの固定漏れ、root での実行、キャッシュの効かない順序、
秘密情報の埋め込み、シェル形式の CMD など）を規則 ID 付きで報告する小さなリンターを作ります。
実務では hadolint などのツールを CI に組み込みますが、ここでは仕組みを理解するために自作します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 4.5          # 合格数を表示（cfs_quota.py・image_layers.py も含む）
このディレクトリで、このファイルのテストだけを実行する:
    python3 -m unittest -v test_dockerfile_lint

実装後にコマンドラインから試す:
    python3 dockerfile_lint.py path/to/Dockerfile

簡略化している点: パーサーディレクティブ（# escape= など）、ヒアドキュメント（RUN <<EOF）、
ONBUILD の中身の検査には対応しなくてよい。エスケープ文字は常に \\ とする。
"""
from __future__ import annotations

import json  # noqa: F401  exec 形式（JSON の配列）の判定に使えます
import re  # noqa: F401
import shlex  # noqa: F401  ENV の KEY="値 に 空白" の分割に使えます
import sys
from typing import NamedTuple

KNOWN_INSTRUCTIONS = frozenset({
    "FROM", "RUN", "CMD", "LABEL", "MAINTAINER", "EXPOSE", "ENV", "ADD", "COPY", "ENTRYPOINT",
    "VOLUME", "USER", "WORKDIR", "ARG", "ONBUILD", "STOPSIGNAL", "HEALTHCHECK", "SHELL",
})

RULES = {
    "DF001": "ベースイメージのタグが未指定、または latest",
    "DF002": "最終ステージが root のまま実行される",
    "DF003": "apt-get update と apt-get install が同じ RUN にない",
    "DF004": "apt-get install に --no-install-recommends がない",
    "DF005": "ADD でリモートの URL を取得している（チェックサムの検証なし）",
    "DF006": "秘密情報らしい名前の ENV / ARG",
    "DF007": "依存関係のインストールより前に、コンテキスト全体を COPY している",
    "DF008": "CMD / ENTRYPOINT がシェル形式",
}


class Instruction(NamedTuple):
    lineno: int  # 命令が始まる行の番号（1 始まり）
    keyword: str  # 大文字にした命令名（"RUN" など）
    args: str  # 引数（継続行を 1 つの空白でつなぎ、前後の空白を除いたもの）


class Finding(NamedTuple):
    rule: str  # 規則 ID（RULES のキー）
    lineno: int  # 問題のある命令の行番号
    message: str  # 利用者向けの説明（何が問題で、どう直すか）


# ---------------------------------------------------------------------------
# 演習1a（★☆☆）: 構文解析
# ---------------------------------------------------------------------------

def parse_dockerfile(text: str) -> list[Instruction]:
    """Dockerfile のテキストを命令のリストにする。

    - 空行と、最初の空白以外の文字が # の行（コメント）は読み飛ばす。
      **継続行の途中にある空行・コメント行も読み飛ばす**（Docker と同じ）。
    - 行末（後ろの空白を除いた末尾）が \\ なら次の行に続く。\\ を取り除き、各行の前後の空白を除いて、
      1 つの空白でつなぐ。ファイルの最後が継続行で終わっていても、そこまでを 1 つの命令とする。
    - 最初の語を命令名とし、大文字にする（Docker は大文字・小文字を区別しない）。
      残りを args とする。命令名が KNOWN_INSTRUCTIONS になければ ValueError
      （継続の \\ を書き忘れると、次の行が命令として解釈されてこうなる）。

    >>> parse_dockerfile("FROM alpine:3.20\\nrun echo a \\\\\\n  && echo b\\n")
    [Instruction(lineno=1, keyword='FROM', args='alpine:3.20'), Instruction(lineno=2, keyword='RUN', args='echo a && echo b')]
    """
    raise NotImplementedError("演習1a: parse_dockerfile を実装してください")


# ---------------------------------------------------------------------------
# 演習1b（★★☆）: 検査
# ---------------------------------------------------------------------------

def lint(text: str) -> list[Finding]:
    """Dockerfile を検査し、Finding のリストを (行番号, 規則 ID) の順に並べて返す。

    ステージ: FROM から次の FROM の直前までを 1 つのステージとする（最後のステージが「最終ステージ」）。
    FROM の引数: 先頭の --platform=... などの「--」で始まるオプションを読み飛ばした最初の語がイメージ名。
    その後に「AS 名前」があればステージ名（大文字・小文字を区別しない）。

    規則（テストはこの定義で答え合わせをします）:
      DF001 FROM のイメージにタグがない、またはタグが latest。
            タグは、イメージ名の最後の「/」より後ろの部分にある「:」の後ろ（localhost:5000/app の
            5000 はレジストリのポートでありタグではない）。次は対象外: scratch、それまでに定義された
            ステージ名、$ を含むもの（変数）、@ を含むもの（ダイジェストで固定）。
      DF002 最終ステージに USER 命令がない（→ 最終ステージの FROM の行で報告）、または最後の USER の
            ユーザー部分（「:」より前）が root か 0（→ その USER の行で報告）。FROM が 1 つもなければ対象外。
      DF003 RUN の中に apt-get update があるのに、同じ RUN に apt-get install がない。
      DF004 RUN の中の apt-get install のコマンドに --no-install-recommends がない（1 つの RUN につき最大 1 件）。
            コマンドの区切りは &&、||、;、| とし、区切られた部分ごとに判定する。
            apt-get と update/install の間にオプション（-y、-q など）があってもよい。
      DF005 ADD の取り込み元（最後の引数以外）に http:// か https:// で始まるものがあり、
            --checksum= のオプションがない。ADD ["src", "dst"] の JSON 形式も扱うこと。
      DF006 ENV / ARG で定義する名前が、大文字・小文字を区別せずに PASSWORD、PASSWD、SECRET、TOKEN、
            API_KEY（APIKEY）、PRIVATE_KEY（PRIVATEKEY）、ACCESS_KEY（ACCESSKEY）、CREDENTIAL の
            いずれかを含む（名前ごとに 1 件）。
            ENV は「KEY=値 KEY2="値"」の形式と、古い「KEY 値」の形式の両方がある。ARG は「名前」か「名前=既定値」。
      DF007 同じステージの中で、COPY/ADD の取り込み元に「.」か「./」（コンテキスト全体）があり（--from= 付きは除く）、
            それより後の RUN に依存関係のインストール（pip/pip3/poetry/npm/yarn/pnpm/bundle/composer の
            install、npm ci、go mod download）がある。最初のそのような COPY の行で、ステージにつき 1 件。
      DF008 CMD / ENTRYPOINT の引数が JSON の文字列の配列（exec 形式）でない（シェル形式）。

    ヒント: 規則ごとに小さな補助関数に分けると見通しがよい。正規表現の例:
        re.compile(r"\\bapt-get\\b(\\s+-\\S+)*\\s+install\\b")
    """
    raise NotImplementedError("演習1b: lint を実装してください")


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        for f in lint(fh.read()):
            print(f"{f.lineno:4d}: {f.rule} {f.message}")
