"""11.3 認証と認可 — 演習（authz）

2 つの認可モデルを実装します。
  - RBAC（ロールベースアクセス制御）: ロールの継承（階層）と、マルチテナントの分離
  - ReBAC（関係ベースアクセス制御）: Google の Zanzibar 論文（2019）に倣った「関係タプル」と、
    owner ⊇ editor ⊇ viewer のような計算される関係・グループの入れ子・親フォルダからの継承

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 11.3
    python3 tools/check.py -v 11.3

このディレクトリで直接実行することもできます:
    python3 -m unittest -v test_authz

ReBAC の表記（Zanzibar 論文の記法）:
    関係タプル  object#relation@subject
        document:readme#owner@user:alice          alice は readme の owner
        document:readme#editor@group:eng#member   eng グループのメンバー全員が readme の editor
        document:spec#parent@folder:proj          spec の親は proj フォルダ
    主体（subject）は "type:id"（個人）か "type:id#relation"（userset = その関係を持つ主体の集合）。

スキーマ（どの型にどの関係があり、関係どうしがどうつながるか）:
    {
      "document": {
        "owner":  {},                                    # 直接のタプルだけ
        "editor": {"computed_userset": ["owner"]},       # editor = 直接 ∪ owner
        "viewer": {"computed_userset": ["editor"],       # viewer = 直接 ∪ editor ∪ 親の viewer
                   "tuple_to_userset": [("parent", "viewer")]},
        "parent": {},
      },
      ...
    }
    - computed_userset: 同じオブジェクトの別の関係を持つ主体も含める
    - tuple_to_userset: (tupleset, computed) の組。(このオブジェクト, tupleset, X) というタプルが
      あれば、X の computed 関係を持つ主体も含める（「親フォルダの閲覧者は中の文書も閲覧できる」）
"""
from __future__ import annotations

import re  # noqa: F401
from dataclasses import dataclass
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 演習1（★☆☆）・演習2（★★☆）: RBAC（ロールの継承とテナント分離）
# ---------------------------------------------------------------------------


class RBAC:
    """ロールの継承つき RBAC。ロールの割り当ては (利用者, テナント) の組ごとに管理する。"""

    def __init__(self) -> None:
        """空の状態で初期化する（ロール → 権限、ロール → 継承する下位ロール、割り当て）。"""
        raise NotImplementedError("演習1: RBAC.__init__ を実装してください")

    def add_role(self, role: str, permissions: Iterable[str] = (), inherits: Iterable[str] = ()) -> None:
        """ロールを定義する。inherits は「このロールが継承する（権限をすべて含む）下位ロール」。

        例: add_role("editor", {"invoice:write"}, inherits=["viewer"])
            → editor は viewer の権限もすべて持つ
        - 同名のロールがすでにあれば ValueError。
        - inherits に未定義のロールがあれば ValueError。
        """
        raise NotImplementedError("演習1: add_role を実装してください")

    def add_inheritance(self, senior: str, junior: str) -> None:
        """定義済みのロールの間に「senior は junior を継承する」関係を後から追加する。

        - どちらかが未定義なら ValueError。
        - 追加すると継承が循環する（junior から継承をたどって senior に到達できる。
          senior == junior も含む）なら ValueError。その場合は何も変更しない。
        """
        raise NotImplementedError("演習1: add_inheritance を実装してください")

    def effective_roles(self, role: str) -> set[str]:
        """role 自身と、継承をたどって到達できるすべてのロールの集合を返す（未定義なら ValueError）。

        ひし形の継承（admin → editor と accountant → どちらも viewer）でも正しく動くこと。
        ヒント: スタックかキューを使った探索と、訪問済みの集合。
        """
        raise NotImplementedError("演習1: effective_roles を実装してください")

    def assign(self, user: str, tenant: str, role: str) -> None:
        """テナント tenant において user に role を割り当てる（未定義のロールなら ValueError）。"""
        raise NotImplementedError("演習2: assign を実装してください")

    def revoke(self, user: str, tenant: str, role: str) -> None:
        """割り当てを取り消す。割り当てられていなければ何もしない（冪等）。"""
        raise NotImplementedError("演習2: revoke を実装してください")

    def roles_of(self, user: str, tenant: str) -> set[str]:
        """テナント tenant で user が持つ実効ロール（割り当て + 継承）の集合を返す。

        **別のテナントでの割り当ては一切考慮しない**（テナント分離）。
        """
        raise NotImplementedError("演習2: roles_of を実装してください")

    def permissions_of(self, user: str, tenant: str) -> set[str]:
        """テナント tenant で user が持つ権限の集合を返す。"""
        raise NotImplementedError("演習2: permissions_of を実装してください")

    def is_allowed(self, user: str, tenant: str, permission: str) -> bool:
        """テナント tenant で user が permission を持つなら True。

        実務での使い方: tenant には **操作対象のリソースが属するテナント**（DB から読んだ値）を渡す。
        リクエストに含まれるテナント ID を信じると、他社のデータを覗かれる（BOLA/IDOR）。
        """
        raise NotImplementedError("演習2: is_allowed を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★★）・演習4（★★☆）: ReBAC（Zanzibar 風の関係タプル）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RelationTuple:
    """関係タプル object#relation@subject。"""

    object: str
    relation: str
    subject: str


class ReBAC:
    """Zanzibar 風の関係ベースアクセス制御（単一プロセス・メモリ上の簡易版）。"""

    def __init__(self, schema: dict[str, dict[str, dict[str, Any]]]) -> None:
        """スキーマを検証して保持する（演習4）。

        - 規則のキーは "computed_userset" と "tuple_to_userset" だけ。それ以外があれば ValueError。
        - computed_userset に同じ型の未定義の関係があれば ValueError。
        - tuple_to_userset の各要素は 2 要素の組で、1 つ目（tupleset）は同じ型の定義済みの関係。
          そうでなければ ValueError。（2 つ目は、たどった先の型で判定時に解釈する）
        - 引数の dict を後から書き換えられても影響を受けないよう、中身を複製して保持する。
        """
        raise NotImplementedError("演習4: ReBAC.__init__ を実装してください")

    def write(self, obj: str, relation: str, subject: str) -> None:
        """関係タプル obj#relation@subject を追加する（同じタプルが既にあれば何もしない）。

        検証（違反は ValueError）:
        - obj は "type:id" の形式で、type はスキーマで定義済み、id は空でない
          （使える文字の目安: 型は英小文字・数字・_、id は英数字と _ . @ -）
        - relation はその型で定義済み
        - subject は "type:id"（型は何でもよい。例: user:alice）か、
          "type:id#relation"（userset。type と relation はスキーマで定義済み）
        - relation が、その型のどこかの規則で tuple_to_userset の tupleset（例: parent）として
          使われているなら、subject は **スキーマで定義済みの型のオブジェクト**（# なし）でなければならない
        """
        raise NotImplementedError("演習3: write を実装してください")

    def delete(self, obj: str, relation: str, subject: str) -> None:
        """関係タプルを削除する。存在しなければ何もしない。"""
        raise NotImplementedError("演習3: delete を実装してください")

    def check(self, obj: str, relation: str, user: str) -> bool:
        """user（"type:id" 形式の主体）が obj に対して relation を持つなら True。

        - obj・relation の検証は write と同じ。user が "type:id" 形式でない（# を含むなど）なら ValueError。
        - 判定のアルゴリズム（深さ優先探索）: ノード (obj, relation) について
            1. 直接のタプル: 主体が user そのものなら True。userset "X#r" なら (X, r) を再帰的に判定
            2. computed_userset の各関係 r2 について (obj, r2) を判定
            3. tuple_to_userset の各 (tupleset, computed) について、(obj, tupleset, P) の各 P に対し
               (P, computed) を判定（P の型にその関係がなければ False 扱い）
          のいずれかで True になれば True。
        - **循環に注意**: グループ a のメンバーに b が、b のメンバーに a が入っていることがある。
          訪問済みの (obj, relation) を集合で覚え、2 度目は False を返して打ち切る
          （規則が和集合だけなので、打ち切っても答えは変わらない）。
        """
        raise NotImplementedError("演習3: check を実装してください")
