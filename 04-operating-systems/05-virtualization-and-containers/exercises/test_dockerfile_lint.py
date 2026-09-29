"""4.5 仮想化とコンテナ — dockerfile_lint のテスト

実行: python3 tools/check.py 4.5   （またはこのディレクトリで python3 -m unittest -v test_dockerfile_lint）
"""
import unittest

from dockerfile_lint import RULES, Finding, Instruction, lint, parse_dockerfile

GOOD = """\
# syntax=docker/dockerfile:1
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

FROM python:3.12-slim
RUN apt-get update \\
    && apt-get install -y --no-install-recommends libpq5 \\
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home app
COPY --from=builder /app /app
USER app
CMD ["python", "/app/main.py"]
"""

BAD = """\
FROM ubuntu
RUN apt-get update
RUN apt-get install -y curl
ENV DB_PASSWORD=hunter2 LOG_LEVEL=info
ARG GITHUB_TOKEN
ADD https://example.com/tool.tar.gz /opt/
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD python app.py
"""


def rules_and_lines(findings):
    return sorted((f.rule, f.lineno) for f in findings)


class TestExercise1aParse(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(parse_dockerfile("FROM alpine:3.20\nRUN echo hi\n"), [
            Instruction(1, "FROM", "alpine:3.20"),
            Instruction(2, "RUN", "echo hi"),
        ])

    def test_continuations_comments_and_blank_lines(self):
        text = (
            "# 先頭のコメント\n"
            "\n"
            "from debian:12 as base\n"            # 小文字の命令も受け付ける
            "run apt-get update && \\\n"
            "    # 継続行の途中のコメントは無視される\n"
            "    apt-get install -y \\\n"
            "\n"
            "      curl\n"
            "  CMD [\"bash\"]   \n"
        )
        self.assertEqual(parse_dockerfile(text), [
            Instruction(3, "FROM", "debian:12 as base"),
            Instruction(4, "RUN", "apt-get update && apt-get install -y curl"),
            Instruction(9, "CMD", '["bash"]'),
        ])

    def test_trailing_continuation_at_end_of_file(self):
        self.assertEqual(parse_dockerfile("FROM a:1\nRUN echo \\\n"), [
            Instruction(1, "FROM", "a:1"), Instruction(2, "RUN", "echo"),
        ])

    def test_unknown_instruction_is_an_error(self):
        # RUN の継続の \ を忘れると、次の行が命令として解釈されてしまう
        with self.assertRaises(ValueError):
            parse_dockerfile("FROM a:1\nRUN apt-get install -y\n    curl\n")

    def test_empty(self):
        self.assertEqual(parse_dockerfile(""), [])
        self.assertEqual(parse_dockerfile("# only comments\n\n"), [])


class TestExercise1bLint(unittest.TestCase):
    def assert_rules(self, text, expected):
        self.assertEqual(rules_and_lines(lint(text)), sorted(expected), "\n" + text)

    def test_good_dockerfile_has_no_findings(self):
        self.assertEqual(lint(GOOD), [])

    def test_bad_dockerfile(self):
        self.assert_rules(BAD, [
            ("DF001", 1), ("DF002", 1), ("DF003", 2), ("DF004", 3), ("DF006", 4),
            ("DF006", 5), ("DF005", 6), ("DF007", 8), ("DF008", 10),
        ])

    def test_findings_are_sorted_and_described(self):
        findings = lint(BAD)
        self.assertEqual(findings, sorted(findings, key=lambda f: (f.lineno, f.rule)))
        for f in findings:
            self.assertIsInstance(f, Finding)
            self.assertIn(f.rule, RULES)
            self.assertTrue(f.message)

    def test_df001_base_image_tags(self):
        tail = "USER app\n"
        self.assert_rules("FROM ubuntu:latest\n" + tail, [("DF001", 1)])
        self.assert_rules("FROM docker.io/library/nginx\n" + tail, [("DF001", 1)])
        self.assert_rules("FROM localhost:5000/team/app\n" + tail, [("DF001", 1)])  # ポートはタグではない
        for ok in ("FROM localhost:5000/team/app:1.4", "FROM --platform=$BUILDPLATFORM golang:1.23 AS b",
                   "FROM scratch", "FROM alpine@sha256:" + "a" * 64, "FROM ${BASE_IMAGE}"):
            self.assert_rules(ok + "\n" + tail, [])

    def test_df001_previous_stage_is_not_an_image(self):
        text = "FROM golang:1.23 AS Build\nRUN go build\nFROM build\nUSER 1000\n"
        self.assert_rules(text, [])

    def test_df002_final_stage_user(self):
        self.assert_rules("FROM a:1\nRUN x\n", [("DF002", 1)])
        self.assert_rules("FROM a:1\nUSER app\nUSER root\n", [("DF002", 3)])
        self.assert_rules("FROM a:1\nUSER 0:0\n", [("DF002", 2)])
        self.assert_rules("FROM a:1\nUSER root\nRUN x\nUSER 10001:10001\n", [])
        # USER があるのが前のステージだけなら、最終ステージは root のまま
        self.assert_rules("FROM a:1 AS b\nUSER app\nFROM c:2\nCOPY --from=b /x /x\n", [("DF002", 3)])

    def test_df003_and_df004_apt_get(self):
        head, tail = "FROM a:1\n", "USER app\n"
        self.assert_rules(head + "RUN apt-get update\n" + tail, [("DF003", 2)])
        self.assert_rules(head + "RUN apt-get -q update && apt-get install -y --no-install-recommends curl\n" + tail, [])
        self.assert_rules(head + "RUN apt-get update && apt-get -y install curl\n" + tail, [("DF004", 2)])
        self.assert_rules(head + "RUN apt-get install -y --no-install-recommends a && apt-get install -y b\n" + tail,
                          [("DF004", 2)])

    def test_df005_add_url(self):
        head, tail = "FROM a:1\n", "USER app\n"
        self.assert_rules(head + "ADD http://example.com/x.tgz /x\n" + tail, [("DF005", 2)])
        self.assert_rules(head + 'ADD ["https://example.com/x.tgz", "/x"]\n' + tail, [("DF005", 2)])
        self.assert_rules(head + "ADD --checksum=sha256:" + "0" * 64 + " https://example.com/x.tgz /x\n" + tail, [])
        self.assert_rules(head + "ADD app.tar.gz /opt/\n" + tail, [])

    def test_df006_secret_like_names(self):
        head, tail = "FROM a:1\n", "USER app\n"
        self.assert_rules(head + "ENV API_KEY abc123\n" + tail, [("DF006", 2)])  # 古い形式
        self.assert_rules(head + 'ENV A=1 aws_secret_access_key="x y"\n' + tail, [("DF006", 2)])
        self.assert_rules(head + "ARG NPM_TOKEN\nARG VERSION=1.0\n" + tail, [("DF006", 2)])
        self.assert_rules(head + "ENV PATH=/opt/bin:$PATH LANG=C.UTF-8\n" + tail, [])

    def test_df007_copy_everything_before_installing_dependencies(self):
        tail = "USER app\n"
        self.assert_rules("FROM node:22\nCOPY . .\nRUN npm ci\n" + tail, [("DF007", 2)])
        self.assert_rules("FROM node:22\nCOPY package.json package-lock.json ./\nRUN npm ci\nCOPY . .\n" + tail, [])
        self.assert_rules("FROM golang:1.23\nCOPY ./ /src\nRUN go mod download\n" + tail, [("DF007", 2)])
        # ステージが違えば関係ない
        self.assert_rules("FROM node:22 AS a\nCOPY . .\nFROM node:22\nRUN npm install\n" + tail, [])

    def test_df008_shell_form(self):
        head = "FROM a:1\nUSER app\n"
        self.assert_rules(head + "CMD python app.py\n", [("DF008", 3)])
        self.assert_rules(head + "ENTRYPOINT /entrypoint.sh\n", [("DF008", 3)])
        self.assert_rules(head + 'ENTRYPOINT ["/entrypoint.sh"]\nCMD ["--port", "8080"]\n', [])


if __name__ == "__main__":
    unittest.main()
