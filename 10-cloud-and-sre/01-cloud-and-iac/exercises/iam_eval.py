"""10.1 クラウドコンピューティングとIaC — 演習: IAM ポリシー評価器（簡略版）

AWS IAM のポリシー評価ロジックを、小さく作り直します。クラウドの権限事故の多くは
「このポリシーで結局何が許可されるのか」を正しく読めないことから起きます。評価器を
自分で書くと、明示的な拒否・暗黙の拒否・条件・権限境界・SCP の関係が腹落ちします。

- 演習1（★☆☆）: wildcard_match — `*` と `?` のワイルドカード照合
- 演習2（★★☆）: condition_matches, evaluate — 条件ブロックとポリシー全体の評価

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.1
    python3 tools/check.py -v 10.1

制約（学びのための縛り）:
    - 演習1 では fnmatch・re・glob などのパターン照合ライブラリを使わないでください。
    - IP アドレスの判定には標準ライブラリの ipaddress を使ってかまいません。

簡略化している点（本物の AWS との違い）:
    - Principal・リソースベースポリシー・セッションポリシー・RCP は扱いません。
    - ポリシー変数（${aws:username} など）、ForAnyValue / ForAllValues、多値のコンテキストキーは扱いません。
    - ARN はセグメントに分けず、文字列全体をワイルドカード照合します。
"""
from __future__ import annotations

import ipaddress  # noqa: F401  演習2で使えます（ip_address, ip_network）
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# ポリシーは AWS と同じ JSON 形式の dict:
# {"Version": "2012-10-17", "Statement": [{"Sid": ..., "Effect": "Allow", "Action": [...], "Resource": [...]}]}
Policy = Mapping[str, Any]


@dataclass(frozen=True)
class Request:
    """評価したいリクエスト（誰が、を除いた「何を・どれに・どんな状況で」）。

    - action: "s3:GetObject" のような「サービス:操作」
    - resource: "arn:aws:s3:::acme-reports/2026/q1.csv" のような ARN
    - context: 条件キーの値。例 {"aws:SourceIp": "203.0.113.5", "aws:MultiFactorAuthPresent": True}
    """

    action: str
    resource: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    """評価結果。

    - allowed: 許可されたか
    - reason: "allowed" / "explicit_deny" / "scp" / "implicit_deny" / "boundary" のいずれか
    - matched: 判断の根拠になったステートメントの Sid（Sid がなければ空文字列）。
      allowed のときは当てはまった Allow の Sid、explicit_deny のときは当てはまった Deny の Sid。
      それ以外（何も当てはまらなかった）は空のタプル。
    """

    allowed: bool
    reason: str
    matched: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: ワイルドカード照合
# ---------------------------------------------------------------------------

def wildcard_match(pattern: str, value: str, *, ignore_case: bool = False) -> bool:
    """IAM と同じワイルドカード規則で value が pattern にマッチするかを返す。

    - `*` は 0 文字以上の任意の文字列（`/` や `:` も含む）にマッチする。
    - `?` はちょうど 1 文字にマッチする。
    - それ以外の文字はリテラル（`.` や `[` に正規表現の意味はない）。パターンの `*` は常にワイルドカード。
    - ignore_case=True なら大文字・小文字を区別しない（IAM のアクション名はこちら）。

    >>> wildcard_match("s3:Get*", "s3:GetObject")
    True
    >>> wildcard_match("arn:aws:s3:::acme-reports/*", "arn:aws:s3:::acme-reports")
    False
    >>> wildcard_match("a?c", "abc")
    True

    計算量の要件: 最悪でも O(len(pattern) × len(value)) にすること。
    `*` ごとに「何文字食べるか」を全部試す素朴な再帰は、`"*a" * 25 + "b"` のような
    パターンで指数時間になります（10.5 で扱う、正規表現のバックトラックによる障害と同じ構造）。

    ヒント: 2 つの方法があります。
    (a) 動的計画法: dp[i][j] = 「pattern[:i] が value[:j] にマッチするか」
    (b) 貪欲法: 直近の `*` の位置だけを覚えておき、行き詰まったらその `*` に
        1 文字多く食べさせてやり直す（戻る先は直近の `*` だけでよい）。
    """
    raise NotImplementedError("演習1: wildcard_match を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: 条件ブロックとポリシーの評価
# ---------------------------------------------------------------------------

def condition_matches(
    condition: Mapping[str, Mapping[str, Any]] | None,
    context: Mapping[str, Any],
) -> bool:
    """ステートメントの Condition ブロックが context で成り立つかを返す。

    condition の形: {演算子: {条件キー: 値 または 値のリスト}}
        例 {"StringEquals": {"aws:RequestedRegion": ["ap-northeast-1", "ap-northeast-3"]},
            "Bool": {"aws:SecureTransport": "true"}}

    評価の規則（AWS と同じ）:
    - condition が None または空なら True。
    - 複数の演算子は AND、1 つの演算子の中の複数のキーも AND、1 つのキーの複数の値は OR。
    - 条件キーの名前は大文字・小文字を区別しない（"aws:SourceIp" と "AWS:SOURCEIP" は同じキー）。
    - context にキーがない場合: 通常の演算子は False。否定形（StringNotEquals など）は True。
      演算子名の末尾に "IfExists" が付いていれば（例 "BoolIfExists"）、キーがないとき True。
    - 否定形は「肯定形で、どの値にも一致しない」とき True（例: StringNotEquals ["a", "b"] は a でも b でもない）。

    対応する演算子（これ以外は ValueError）:
    | 演算子 | 意味 |
    |---|---|
    | StringEquals / StringNotEquals | 文字列の完全一致（大文字・小文字を区別） |
    | StringEqualsIgnoreCase / StringNotEqualsIgnoreCase | 大文字・小文字を区別しない完全一致 |
    | StringLike / StringNotLike | wildcard_match による照合（大文字・小文字を区別） |
    | NumericEquals / NumericNotEquals / NumericLessThan / NumericLessThanEquals / NumericGreaterThan / NumericGreaterThanEquals | 数値比較（"3600" のような文字列も数値として扱う） |
    | Bool | 真偽値の比較（True/False または "true"/"false"。大文字・小文字は問わない） |
    | IpAddress / NotIpAddress | context の IP アドレスが CIDR（"203.0.113.0/24"）に含まれるか。IPv6 も可 |

    数値・真偽値・IP アドレスとして解釈できない値は ValueError。

    >>> condition_matches({"BoolIfExists": {"aws:MultiFactorAuthPresent": "false"}}, {})
    True
    >>> condition_matches({"StringEquals": {"aws:RequestedRegion": "ap-northeast-1"}}, {})
    False
    """
    raise NotImplementedError("演習2: condition_matches を実装してください")


def evaluate(
    request: Request,
    identity_policies: Sequence[Policy],
    *,
    boundary: Policy | None = None,
    scps: Sequence[Sequence[Policy]] | None = None,
) -> Decision:
    """リクエストが許可されるかを評価する。

    引数:
    - identity_policies: プリンシパル（ユーザー・ロール）にアタッチされたポリシーのリスト
    - boundary: 権限境界（permissions boundary）。None なら境界なし
    - scps: AWS Organizations の SCP。組織の階層（ルート → OU → … → アカウント）の各レベルに
      アタッチされたポリシーのリストを、上の階層から順に並べたもの。None なら SCP なし。
      例 [[FullAWSAccess], [リージョン制限, FullAWSAccess]]

    ステートメントが「当てはまる」条件:
    - Action のどれかにマッチ（NotAction なら、どれにもマッチしない）。アクションは大文字・小文字を区別しない
    - かつ Resource のどれかにマッチ（NotResource なら、どれにもマッチしない）。リソースは区別する
    - かつ Condition が成り立つ
    Statement は 1 つの dict でも、dict のリストでもよい。Action / Resource などは文字列でもリストでもよい。

    判定の順序（AWS の評価ロジックを簡略化したもの）:
    1. すべてのポリシー（identity・boundary・全階層の SCP）の中に、当てはまる Deny が 1 つでもあれば
       Decision(False, "explicit_deny", 当てはまった Deny の Sid)。明示的な拒否は常に最優先。
    2. SCP の各階層について、その階層に当てはまる Allow が 1 つもなければ Decision(False, "scp")。
       SCP は権限を与えない。「使ってよい上限」を決めるだけで、各階層すべてで許可が必要。
    3. identity_policies に当てはまる Allow がなければ Decision(False, "implicit_deny")（既定は拒否）。
    4. boundary があり、そこに当てはまる Allow がなければ Decision(False, "boundary")。
       有効な権限は identity と boundary の積集合になる。
    5. 以上を通れば Decision(True, "allowed", identity_policies で当てはまった Allow の Sid)。
    Sid はポリシーの順・ステートメントの順に並べる。

    不正なポリシーは、評価結果に関係なく（Deny が先に見つかっても）ValueError:
    - "Statement" がない
    - Effect が "Allow" / "Deny" 以外、または Effect がない
    - Action と NotAction の両方がある、またはどちらもない（Resource / NotResource も同様）

    ヒント: まず「1 つのステートメントがリクエストに当てはまるか」を判定する補助関数を作ると、
    あとは上の 1〜5 を順に書くだけになります。
    """
    raise NotImplementedError("演習2: evaluate を実装してください")
