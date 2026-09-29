"""8.3 バージョン管理とコードレビュー — 演習1: Git のオブジェクトモデルを実装する（minigit）

Git の中心は「内容で番地が決まる（content-addressable）オブジェクトの保管庫」と、
コミットがつくる有向非巡回グラフ（DAG）です。この演習では、本物の Git と **同じハッシュ値**
になるように blob・tree・commit オブジェクトを作り、履歴をたどる処理とマージベースの計算を実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 8.3

Git がインストールされていれば、結果を本物と照らし合わせられます（テストは Git なしで動きます）:
    echo "hello" | git hash-object --stdin        # ce013625030ba8dba906f756967f9e9ca394464a
    git cat-file -p <ハッシュ>                     # オブジェクトの中身を表示

演習の構成:
    1-1 encode_object / hash_object      （★☆☆）オブジェクトの符号化とハッシュ
    1-2 write_tree                       （★★☆）ファイルの集合から tree オブジェクトの木を作る
    1-3 commit_tree / parse_commit       （★★☆）commit オブジェクトの作成と解析
    1-4 log / is_ancestor / merge_bases  （★★★）DAG をたどる

制約: ハッシュ関数には hashlib.sha1 を使ってください（Git の既定のオブジェクト形式は SHA-1）。
      zlib 圧縮やファイルへの保存は不要です（本物の Git は .git/objects に zlib 圧縮して保存します）。
"""
from __future__ import annotations

import hashlib  # noqa: F401  実装で使います
from dataclasses import dataclass
from typing import Iterable, Optional

OBJECT_TYPES = ("blob", "tree", "commit", "tag")


# ---------------------------------------------------------------------------
# 演習1-1（★☆☆）: オブジェクトの符号化とハッシュ
# ---------------------------------------------------------------------------

def encode_object(obj_type: str, content: bytes) -> bytes:
    """Git のオブジェクトの「ハッシュを取る対象のバイト列」を返す。

    形式: "<型> <内容のバイト数>\\0" というヘッダ（ASCII）の後ろに、内容をそのまま続けたもの。
    obj_type が OBJECT_TYPES のどれでもなければ ValueError。

    >>> encode_object("blob", b"hello\\n")
    b'blob 6\\x00hello\\n'
    """
    raise NotImplementedError("演習1-1: encode_object を実装してください")


def hash_object(content: bytes, obj_type: str = "blob") -> str:
    """encode_object の結果の SHA-1 を、40 桁の小文字の 16 進数で返す（git hash-object と同じ）。

    >>> hash_object(b"hello\\n")
    'ce013625030ba8dba906f756967f9e9ca394464a'
    >>> hash_object(b"")                    # 空のファイル
    'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391'
    >>> hash_object(b"", "tree")            # 空の tree
    '4b825dc642cb6eb9a060e54bf8d69288fbee4904'
    """
    raise NotImplementedError("演習1-1: hash_object を実装してください")


class ObjectStore:
    """メモリ上のオブジェクトの保管庫（このクラスは完成しています）。

    本物の Git の .git/objects に相当します。ハッシュ（sha）をキーに (型, 内容) を保存します。
    同じ内容は同じ sha になるので、何度 put しても 1 つしか保存されません（重複の排除）。
    """

    def __init__(self) -> None:
        self._objects: dict[str, tuple[str, bytes]] = {}

    def put(self, obj_type: str, content: bytes) -> str:
        sha = hash_object(content, obj_type)
        self._objects[sha] = (obj_type, content)
        return sha

    def get(self, sha: str) -> tuple[str, bytes]:
        """(型, 内容) を返す。なければ KeyError。"""
        return self._objects[sha]

    def __contains__(self, sha: object) -> bool:
        return sha in self._objects

    def __len__(self) -> int:
        return len(self._objects)


# ---------------------------------------------------------------------------
# 演習1-2（★★☆）: tree オブジェクト
# ---------------------------------------------------------------------------

def write_tree(store: ObjectStore, files: dict[str, bytes], executables: Iterable[str] = ()) -> str:
    """パス → 内容 の辞書から、blob と（入れ子の）tree オブジェクトを store に保存し、根の tree の sha を返す。

    - files のキーは "/" 区切りの相対パス（例: "src/app.py"）。値はファイルの内容（bytes）。
    - executables に含まれるパスは実行可能ファイルとして扱う。
    - 各ディレクトリについて 1 つの tree オブジェクトを作る。tree の内容は、エントリを次の形式で
      連結したもの:
          <モード> <名前>\\0<参照先の sha の生の 20 バイト>
        モード（ASCII）: 通常のファイル "100644"、実行可能ファイル "100755"、ディレクトリ "40000"
        （git cat-file -p では "040000" と表示されますが、オブジェクトの中身は先頭の 0 がない "40000"）
        sha は 16 進数の文字列ではなく、bytes.fromhex(sha) で得られる 20 バイトであることに注意。
    - エントリの順序: 名前を UTF-8 のバイト列として昇順に並べる。ただし **ディレクトリの名前は
      末尾に "/" が付いているものとして比較する**。例えばファイル "a.txt" とディレクトリ "a" は、
      "a.txt" と "a/" の比較になり、"." (0x2E) < "/" (0x2F) なので "a.txt" が先。
    - files が空なら、空の tree（内容が空の tree オブジェクト）の sha を返す。
    - 不正なパスは ValueError: 空文字列、"/" で始まる・終わる、空の要素（"a//b"）、
      "." や ".." の要素、同じパスがファイルとディレクトリの両方として使われる（"a" と "a/b"）。
      executables に files にないパスがあっても ValueError。

    ヒント: まずパスを "/" で分割して入れ子の辞書を作り、葉（ファイル）から順に再帰的に
            tree を作ると書きやすい。
    """
    raise NotImplementedError("演習1-2: write_tree を実装してください")


# ---------------------------------------------------------------------------
# 演習1-3（★★☆）: commit オブジェクト
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Commit:
    """解析した commit オブジェクト。"""

    tree: str
    parents: tuple[str, ...]
    author: str  # "Alice <alice@example.com> 1700000000 +0900" のように、行のヘッダ名より後ろ全体
    committer: str
    message: str

    @property
    def committer_time(self) -> int:
        """committer 行の UNIX 時刻（秒）。"""
        return int(self.committer.rsplit(" ", 2)[1])


def commit_tree(
    store: ObjectStore,
    tree: str,
    parents: Iterable[str],
    message: str,
    author: str,
    timestamp: int,
    tz: str = "+0900",
    committer: Optional[str] = None,
    committer_timestamp: Optional[int] = None,
) -> str:
    """commit オブジェクトを store に保存し、その sha を返す（git commit-tree と同じ形式）。

    内容（UTF-8）の形式:
        tree <tree の sha>
        parent <親の sha>          ← 親の数だけ、与えられた順に（最初のコミットは 0 行、マージは 2 行以上）
        author <author> <timestamp> <tz>
        committer <committer> <committer_timestamp> <tz>
        （空行）
        <message>
    - author・committer は "名前 <メールアドレス>" の形の文字列。committer を省略したら author と同じ。
      committer_timestamp を省略したら timestamp と同じ。
    - message の末尾に改行がなければ 1 つ付ける（git commit-tree -m と同じ結果にするため）。
    - tree と各 parent は store に存在し、それぞれ tree 型・commit 型でなければ ValueError。
    - tz は "+0900" や "-0500" の形（符号 + 4 桁）でなければ ValueError。
    """
    raise NotImplementedError("演習1-3: commit_tree を実装してください")


def parse_commit(content: bytes) -> Commit:
    """commit オブジェクトの内容を解析する。

    - 最初の空行までがヘッダ、その後ろがメッセージ（末尾の改行も含めてそのまま）。
    - ヘッダの行は "名前 値" の形。tree（1 つ）・parent（0 個以上）・author・committer を読む。
      それ以外のヘッダ（署名の gpgsig など）は無視してよい。
      （gpgsig のように複数行にわたるヘッダは、2 行目以降が空白 1 文字で始まる。これも読み飛ばすこと）
    - tree・author・committer のどれかがなければ ValueError。
    """
    raise NotImplementedError("演習1-3: parse_commit を実装してください")


# ---------------------------------------------------------------------------
# 演習1-4（★★★）: 履歴の DAG をたどる
# ---------------------------------------------------------------------------

def log(store: ObjectStore, head: str, first_parent: bool = False) -> list[str]:
    """head から到達できるコミットの sha の一覧を返す（git log に相当）。

    - first_parent=False: すべての親をたどり、到達できるすべてのコミット（head を含む）を、
      committer 時刻の新しい順に並べる。時刻が同じなら sha の昇順。各コミットは 1 回だけ。
    - first_parent=True: head から最初の親だけをたどった列（head, 親, 親の親, …）を返す
      （git log --first-parent。マージしたブランチの中のコミットは含まれない）。
    """
    raise NotImplementedError("演習1-4: log を実装してください")


def is_ancestor(store: ObjectStore, ancestor: str, descendant: str) -> bool:
    """ancestor が descendant 自身か、その祖先なら True（git merge-base --is-ancestor に相当）。

    これが True なら、ancestor を指しているブランチに descendant をマージするときは、
    新しいマージコミットを作らずにブランチの ref を descendant まで進めるだけで済む
    （早送り、fast-forward）。
    """
    raise NotImplementedError("演習1-4: is_ancestor を実装してください")


def merge_bases(store: ObjectStore, a: str, b: str) -> list[str]:
    """a と b の「最良の共通祖先」（マージベース）を、sha の昇順のリストで返す（git merge-base --all）。

    - 共通祖先: a と b の両方から到達できるコミット（a・b 自身を含む）。
    - 最良の共通祖先: 共通祖先のうち、ほかのどの共通祖先の祖先でもないもの（DAG の最小共通祖先）。
    - 普通は 1 つだが、互いにマージし合った履歴（criss-cross merge）では 2 つ以上になることがある。
    - 共通祖先がなければ空リスト（無関係な履歴）。
    """
    raise NotImplementedError("演習1-4: merge_bases を実装してください")
