"""6.3 トランザクションと同時実行制御 — 演習1: MVCC でスナップショット分離を実装する

PostgreSQL や MySQL（InnoDB）が使っている多版型同時実行制御（MVCC）の核心を、
メモリ上のキーバリューストアとして実装します。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.3
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_mvcc

作るもの（スナップショット分離、snapshot isolation）:
    store = MVCCStore()
    t1 = store.begin()          # 開始した時点の「スナップショット」を読む
    t1.put("x", 1)              # 書き込みはコミットまで自分の中だけ（他からは見えない）
    t1.get("x")                 # → 1（自分の書き込みは見える: read-your-own-writes）
    t1.commit()                 # 全部が一度に見えるようになる（原子性）

約束:
    - 論理時計: ストアは「最後にコミットした時刻」clock（最初は 0）を持つ。
      begin() したトランザクションの start_ts は、その時点の clock。
      commit() のたびに clock を 1 進め、その値をそのトランザクションの commit_ts とする
      （読み取り専用のトランザクションでも進めてよい）。
    - 読み取り: キーの「commit_ts <= start_ts であるバージョンのうち最新のもの」が見える。
      ただし自分が put / delete したキーは、自分の書き込みが見える。
    - 書き込みの衝突（first-committer-wins）: commit() のとき、自分が書いたキーのどれかに
      「自分の start_ts より後にコミットされたバージョン」があれば、コミットせずに
      中断（status = "aborted"）し、SerializationError を送出する。
      これで「ロストアップデート」は防げるが、「書き込みスキュー」は防げない（テストで確かめる）。
    - status は "active" / "committed" / "aborted"。active でないトランザクションの操作
      （commit の 2 回目も含む）は TransactionError。
    - 値には任意のオブジェクトを使えるが、None を値として保存することは考えなくてよい
      （get は、キーがない・削除済みのとき default を返す）。

発展課題（任意）: MVCCStore(serializable=True) で、書き込みスキューも防ぐ（簡略化した SSI）。
実装しない場合は、__init__ の NotImplementedError を残してください（テストはスキップされます）。
"""
from __future__ import annotations

from typing import Any


class TransactionError(Exception):
    """終了したトランザクションを操作しようとした。"""


class SerializationError(Exception):
    """直列化できない（コミットすると異常が起きる）ので中断した。アプリケーションは再試行する。"""


class Transaction:
    """1 つのトランザクション。MVCCStore.begin() で作られる。

    提供済みの属性（使っても、自分の設計に変えてもよい）:
        store: 属しているストア
        txid: トランザクション番号（1, 2, 3, ...）
        start_ts: スナップショットの時刻
        status: "active" / "committed" / "aborted"
        commit_ts: コミットした時刻（コミット前は None）
        writes: 書き込みバッファ {キー: 値}（削除は番兵の値で表すとよい）
        read_keys, read_prefixes: 読んだキーと、scan した接頭辞（発展課題の SSI で使う）
    """

    def __init__(self, store: MVCCStore, txid: int, start_ts: int) -> None:
        self.store = store
        self.txid = txid
        self.start_ts = start_ts
        self.status = "active"
        self.commit_ts: int | None = None
        self.writes: dict[str, Any] = {}
        self.read_keys: set[str] = set()
        self.read_prefixes: set[str] = set()

    # -----------------------------------------------------------------------
    # 演習1-1（★★☆）: 読み書き
    # -----------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """スナップショット（と自分の書き込み）から key の値を読む。なければ default。"""
        raise NotImplementedError("演習1-1: get を実装してください")

    def put(self, key: str, value: Any) -> None:
        """key に value を書く（コミットまで他のトランザクションには見えない）。"""
        raise NotImplementedError("演習1-1: put を実装してください")

    def delete(self, key: str) -> None:
        """key を削除する（墓標、tombstone を書く）。存在しないキーの削除もエラーにしない。"""
        raise NotImplementedError("演習1-1: delete を実装してください")

    def scan(self, prefix: str = "") -> dict[str, Any]:
        """prefix で始まるキーと値を、キーの昇順の dict で返す（削除済みは含めない）。

        スナップショットに見えるキーに、自分の書き込み（追加・更新・削除）を反映したもの。
        同じトランザクションで 2 回 scan すると、他のトランザクションが途中でキーを追加して
        コミットしても、同じ結果になる（ファントムが起きない）。
        """
        raise NotImplementedError("演習1-1: scan を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-2（★★★）: コミットと中断
    # -----------------------------------------------------------------------

    def commit(self) -> int:
        """コミットして commit_ts を返す。書き込みの衝突があれば中断して SerializationError。

        手順:
          1. first-committer-wins の検査（モジュールの docstring 参照）
          2. （発展課題）serializable なら、危険な構造の検査
          3. 時計を 1 進め、書き込みバッファの内容を、その時刻のバージョンとして一度に追加する
        """
        raise NotImplementedError("演習1-2: commit を実装してください")

    def abort(self) -> None:
        """中断する。書き込みはすべて捨てる（他のトランザクションには一度も見えていない）。"""
        raise NotImplementedError("演習1-2: abort を実装してください")


class MVCCStore:
    """MVCC のキーバリューストア。

    提供済みの属性（使っても、自分の設計に変えてもよい）:
        _versions: {キー: [バージョン, ...]}  バージョンは (値, commit_ts, txid) など。commit_ts の昇順
        _clock: 最後にコミットした時刻
        _next_txid: 次に払い出すトランザクション番号
        _txns: 開始したトランザクションの一覧（vacuum や SSI の判定で使う）
    """

    def __init__(self, serializable: bool = False) -> None:
        if serializable:
            raise NotImplementedError("発展課題: serializable モードは未実装です")
        self.serializable = serializable
        self._versions: dict[str, list[Any]] = {}
        self._clock = 0
        self._next_txid = 1
        self._txns: list[Transaction] = []

    def begin(self) -> Transaction:
        """新しいトランザクションを開始する（start_ts = 現在の _clock）。"""
        raise NotImplementedError("演習1-1: begin を実装してください")

    # -----------------------------------------------------------------------
    # 演習1-3（★★☆）: 古いバージョンの回収（VACUUM / purge）
    # -----------------------------------------------------------------------

    def version_count(self) -> int:
        """保持しているバージョンの総数（全キーの合計。墓標も数える）。"""
        raise NotImplementedError("演習1-3: version_count を実装してください")

    def vacuum(self) -> int:
        """もう誰にも見えないバージョンを削除し、削除した数を返す。

        - 基準の時刻 horizon = 実行中（active）のトランザクションの start_ts の最小値
          （実行中のものがなければ現在の _clock）。
        - 各キーについて、「commit_ts <= horizon のバージョンのうち最新のもの」より古い
          バージョンはすべて削除できる（どのスナップショットからも、もう見えない）。
        - さらに、残ったのが「commit_ts <= horizon の墓標」1 つだけなら、キーごと削除できる。

        長時間実行中のトランザクションがあると horizon が進まず、古いバージョンを回収できない。
        これが PostgreSQL で「長いトランザクションが VACUUM を妨げてテーブルが肥大化する」理由。
        """
        raise NotImplementedError("演習1-3: vacuum を実装してください")


# ---------------------------------------------------------------------------
# 発展課題（★★★・任意）: serializable=True（簡略化した SSI）
# ---------------------------------------------------------------------------
#
# スナップショット分離に、次の検査を加えると書き込みスキューを防げる。
#
#   rw 依存（反依存）: トランザクション R が読んだキー（または scan した接頭辞に含まれるキー）を、
#   R と並行するトランザクション W が書いたとき、R → W の rw 依存があるという。
#   （R のスナップショットには W の書き込みが見えていない。つまり「R は W より前に実行された」ことになる）
#
#   並行: A と B は、互いに相手のコミットより前に開始していれば並行（コミットしていない側の
#   コミット時刻は無限大とみなす）。つまり A.start_ts < B.commit_ts かつ B.start_ts < A.commit_ts。
#
#   危険な構造: コミットしようとするトランザクション T に、入ってくる rw 依存（U → T）と
#   出ていく rw 依存（T → V）の両方があるとき、T を中断する（SerializationError）。
#   U と V は、中断されていない並行トランザクション（コミット済みでも実行中でもよい）で、
#   同じトランザクションでもよい。読み取り専用のトランザクション（書き込みなし）は検査しない。
#
# 本物の SSI（PostgreSQL の SERIALIZABLE）は、コミット順などを考慮して偽陽性を減らし、
# 自分以外のトランザクションがピボットになる場合も検出する。この簡略版は偽陽性（本当は安全なのに
# 中断すること）を許すが、2 つのトランザクションの書き込みスキューは必ず防げる。
# ヒント: 判定のために、コミット済みのトランザクションの read_keys / read_prefixes / writes も残しておく。
