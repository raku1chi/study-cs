"""4.5 仮想化とコンテナ — 解答例: Dockerfile のベストプラクティスを検査するリンター

演習の仕様は exercises/dockerfile_lint.py の docstring を参照してください。

コマンドラインから試す:
    python3 dockerfile_lint.py path/to/Dockerfile
"""
from __future__ import annotations

import json
import re
import shlex
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
    lineno: int
    keyword: str
    args: str


class Finding(NamedTuple):
    rule: str
    lineno: int
    message: str


# ---------------------------------------------------------------------------
# 演習1a: 構文解析
# ---------------------------------------------------------------------------

def parse_dockerfile(text: str) -> list[Instruction]:
    instructions: list[Instruction] = []
    parts: list[str] = []  # 継続行を集めている途中の断片
    start = 0
    for lineno, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue  # 空行とコメント行は、継続行の途中にあっても読み飛ばす
        if not parts:
            start = lineno
        continued = stripped.endswith("\\")
        parts.append(stripped[:-1].strip() if continued else stripped)
        if continued:
            continue
        instructions.append(_make_instruction(start, " ".join(p for p in parts if p)))
        parts = []
    if parts:  # ファイルの最後が継続行で終わっていた
        instructions.append(_make_instruction(start, " ".join(p for p in parts if p)))
    return instructions


def _make_instruction(lineno: int, line: str) -> Instruction:
    keyword, _, args = line.partition(" ")
    keyword = keyword.upper()
    if keyword not in KNOWN_INSTRUCTIONS:
        raise ValueError(f"{lineno} 行目: 命令として解釈できません: {line[:40]!r}（継続の \\ を忘れていませんか）")
    return Instruction(lineno, keyword, args.strip())


# ---------------------------------------------------------------------------
# 演習1b: 検査
# ---------------------------------------------------------------------------

_SECRET_NAME = re.compile(r"PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|ACCESS_?KEY|CREDENTIAL", re.I)
_SEGMENT_SPLIT = re.compile(r"&&|\|\||;|\|")
_APT_UPDATE = re.compile(r"\bapt-get\b(\s+-\S+)*\s+update\b")
_APT_INSTALL = re.compile(r"\bapt-get\b(\s+-\S+)*\s+install\b")
_DEP_INSTALL = re.compile(
    r"\b(pip3?|poetry|npm|yarn|pnpm|bundle|composer)\s+(install|ci)\b|\bgo\s+mod\s+download\b"
)


def _split_options(args: str) -> tuple[list[str], list[str]]:
    """先頭の --xxx 形式のオプションと、残りの引数に分ける（JSON 形式にも対応）。"""
    if args.startswith("["):
        try:
            values = json.loads(args)
            if isinstance(values, list) and all(isinstance(v, str) for v in values):
                return [], values
        except json.JSONDecodeError:
            pass
    tokens = args.split()
    i = 0
    while i < len(tokens) and tokens[i].startswith("--"):
        i += 1
    return tokens[:i], tokens[i:]


def _is_exec_form(args: str) -> bool:
    try:
        value = json.loads(args)
    except json.JSONDecodeError:
        return False
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _env_names(keyword: str, args: str) -> list[str]:
    try:
        tokens = shlex.split(args)
    except ValueError:
        tokens = args.split()
    if not tokens:
        return []
    if keyword == "ENV" and "=" not in tokens[0]:
        return [tokens[0]]  # 古い形式 ENV NAME value
    return [t.split("=", 1)[0] for t in tokens if t and not t.startswith("=")]


def lint(text: str) -> list[Finding]:
    instructions = parse_dockerfile(text)
    findings: list[Finding] = []
    add = lambda rule, ins, msg: findings.append(Finding(rule, ins.lineno, msg))  # noqa: E731

    stages: list[list[Instruction]] = []
    stage_names: set[str] = set()
    for ins in instructions:
        if ins.keyword == "FROM":
            stages.append([ins])
            _, rest = _split_options(ins.args)
            if not rest:
                continue
            image = rest[0]
            if len(rest) >= 3 and rest[1].upper() == "AS":
                stage_name = rest[2].lower()
            else:
                stage_name = None
            # DF001: タグなし・latest（scratch、前のステージ名、変数、ダイジェスト指定は対象外）
            last = image.rsplit("/", 1)[-1]
            if not (image.lower() == "scratch" or image.lower() in stage_names or "$" in image or "@" in image):
                if ":" not in last:
                    add("DF001", ins, f"ベースイメージ {image} にタグがありません。バージョンを固定してください")
                elif last.split(":", 1)[1] == "latest":
                    add("DF001", ins, f"ベースイメージ {image} が latest です。バージョンを固定してください")
            if stage_name:
                stage_names.add(stage_name)
        elif stages:
            stages[-1].append(ins)
        else:
            stages.append([ins])  # FROM より前の ARG など

        if ins.keyword == "RUN":
            segments = _SEGMENT_SPLIT.split(ins.args)
            if any(_APT_UPDATE.search(s) for s in segments) and not any(_APT_INSTALL.search(s) for s in segments):
                add("DF003", ins, "apt-get update は同じ RUN の中で apt-get install と組み合わせてください"
                                  "（別の RUN にすると古いパッケージ一覧がキャッシュされ続ける）")
            if any(_APT_INSTALL.search(s) and "--no-install-recommends" not in s for s in segments):
                add("DF004", ins, "apt-get install に --no-install-recommends を付けて、不要なパッケージを入れないでください")
        elif ins.keyword == "ADD":
            options, rest = _split_options(ins.args)
            sources = rest[:-1]
            if any(s.startswith(("http://", "https://")) for s in sources) and \
                    not any(o.startswith("--checksum=") for o in options):
                add("DF005", ins, "ADD で URL を取得するなら --checksum で内容を検証するか、"
                                  "RUN で取得してチェックサムを確認してください")
        elif ins.keyword in ("ENV", "ARG"):
            for name in _env_names(ins.keyword, ins.args):
                if _SECRET_NAME.search(name):
                    add("DF006", ins, f"{ins.keyword} {name} は秘密情報に見えます。イメージの履歴に残るので、"
                                      "ビルド時のシークレットのマウントや実行時の注入を使ってください")
        elif ins.keyword in ("CMD", "ENTRYPOINT"):
            if ins.args and not _is_exec_form(ins.args):
                add("DF008", ins, f"{ins.keyword} をシェル形式で書くと /bin/sh -c が PID 1 になり、"
                                  "シグナルがアプリに届きません。exec 形式（JSON の配列）で書いてください")

    # DF002: 最終ステージの実行ユーザー
    from_stages = [s for s in stages if s and s[0].keyword == "FROM"]
    if from_stages:
        final = from_stages[-1]
        users = [ins for ins in final if ins.keyword == "USER"]
        if not users:
            add("DF002", final[0], "最終ステージに USER がなく、root で実行されます。専用のユーザーを作って切り替えてください")
        else:
            user = users[-1].args.split(":", 1)[0].strip()
            if user in ("root", "0"):
                add("DF002", users[-1], "最終ステージの USER が root です。専用のユーザーに切り替えてください")

    # DF007: 同じステージで、コンテキスト全体の COPY が依存関係のインストールより前にある
    for stage in stages:
        copy_all = None
        for ins in stage:
            if ins.keyword in ("COPY", "ADD") and copy_all is None:
                options, rest = _split_options(ins.args)
                if not any(o.startswith("--from=") for o in options) and any(s in (".", "./") for s in rest[:-1]):
                    copy_all = ins
            elif ins.keyword == "RUN" and copy_all is not None and _DEP_INSTALL.search(ins.args):
                add("DF007", copy_all, "ソースを 1 行変えるだけで依存関係の再インストールが走ります。"
                                       "先に依存関係の定義ファイルだけを COPY してインストールしてください")
                break

    findings.sort(key=lambda f: (f.lineno, f.rule))
    return findings


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as fh:
        for f in lint(fh.read()):
            print(f"{f.lineno:4d}: {f.rule} {f.message}")
