"""6.4 ストレージエンジンと障害回復 — 演習2: 小さな LSM 木を作る

RocksDB・Cassandra・LevelDB などが使う LSM 木（Log-Structured Merge-tree）の骨格を実装します。
書き込みは WAL（先行書き込みログ）とメモリ上の memtable に入り、memtable が一杯になると
ソート済みの不変ファイル SSTable としてディスクに書き出されます（フラッシュ）。
SSTable が増えたら、まとめて 1 つにします（コンパクション）。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 6.4
このディレクトリで、この演習だけを実行する:
    python3 -m unittest -v test_lsm

ディレクトリの中身:
    wal.log                 1 行 1 操作の JSON: ["put", キー, 値] または ["del", キー]
    00000003-t0.sst         SSTable。名前は「連番（8 桁）-t段（tier）」。連番が大きいほど新しい
    00000007-t1.sst         中身は 1 行 1 項目の JSON: [キー, 値]（値が null なら墓標）。キーの昇順

提供済みの SSTable クラス（下）は、疎な索引（16 件ごとのキーとファイル内の位置）と Bloom フィルタ
（[2.4 基本データ構造] の確率的データ構造）を持ち、get でファイルのごく一部だけを読みます。

約束:
    - キーと値は str（そうでなければ TypeError）。memtable では、削除を値 None（墓標）で表す。
    - self.sstables は SSTable のリストで、新しい順（連番の降順）に並べる。
    - 使ってはいけないもの: dbm、shelve、sqlite3 など既存のストレージエンジン。
"""
from __future__ import annotations

import hashlib
import heapq  # noqa: F401  演習2-2 の k-way マージで使えます
import json
import os
import re
from bisect import bisect_right
from collections.abc import Iterable, Iterator
from pathlib import Path

# ---------------------------------------------------------------------------
# 提供済み: Bloom フィルタと SSTable（変更しなくてよい）
# ---------------------------------------------------------------------------


class BloomFilter:
    """「確実にない」か「あるかもしれない」かを、少ないメモリで答える集合（偽陽性あり、偽陰性なし）。"""

    def __init__(self, n_items: int, bits_per_item: int = 10, n_hashes: int = 7) -> None:
        self.m = max(8, n_items * bits_per_item)
        self.k = n_hashes
        self.bits = bytearray((self.m + 7) // 8)

    def _positions(self, key: str) -> Iterator[int]:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        h1 = int.from_bytes(digest[:8], "big")
        h2 = int.from_bytes(digest[8:16], "big") | 1
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, key: str) -> None:
        for p in self._positions(key):
            self.bits[p // 8] |= 1 << (p % 8)

    def might_contain(self, key: str) -> bool:
        return all(self.bits[p // 8] & (1 << (p % 8)) for p in self._positions(key))


def fsync_directory(path: Path) -> None:
    """ディレクトリのエントリ（ファイル名の変更）を永続化する（POSIX のみ）。"""
    if os.name != "posix":
        return
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


SSTABLE_NAME = re.compile(r"(\d{8})-t(\d+)\.sst")


class SSTable:
    """ソート済みの不変ファイル。

    - SSTable.write(directory, seq, tier, items): items（キーの昇順・重複なしの (キー, 値) の列。
      値 None は墓標）を一時ファイルに書き、fsync してから名前を変えて完成させる。
    - sst.get(key) -> (found, value): found が True で value が None なら「墓標が見つかった」。
    - sst.items(): (キー, 値) をキーの昇順に返す（墓標も含む）。
    - sst.seq, sst.tier, len(sst), sst.path, sst.reads（get でファイルを読んだ回数）
    """

    BLOCK = 16

    def __init__(self, path: Path) -> None:
        m = SSTABLE_NAME.fullmatch(path.name)
        if m is None:
            raise ValueError(f"SSTable のファイル名ではありません: {path.name}")
        self.path = path
        self.seq = int(m.group(1))
        self.tier = int(m.group(2))
        self.reads = 0
        self.index: list[tuple[str, int]] = []
        keys: list[str] = []
        offset = 0
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                key = json.loads(line)[0]
                if i % self.BLOCK == 0:
                    self.index.append((key, offset))
                keys.append(key)
                offset += len(line)
        self.count = len(keys)
        self.min_key = keys[0] if keys else None
        self.max_key = keys[-1] if keys else None
        self.bloom = BloomFilter(self.count)
        for key in keys:
            self.bloom.add(key)

    @classmethod
    def write(cls, directory: Path, seq: int, tier: int, items: Iterable[tuple[str, str | None]]) -> SSTable:
        path = directory / f"{seq:08d}-t{tier}.sst"
        tmp = directory / (path.name + ".tmp")
        prev = None
        with open(tmp, "w", encoding="utf-8") as f:
            for key, value in items:
                if prev is not None and key <= prev:
                    raise ValueError("SSTable に書く項目は、キーの昇順で重複なしにしてください")
                f.write(json.dumps([key, value], ensure_ascii=False) + "\n")
                prev = key
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fsync_directory(directory)
        return cls(path)

    def get(self, key: str) -> tuple[bool, str | None]:
        if self.count == 0 or key < self.min_key or key > self.max_key:
            return False, None
        if not self.bloom.might_contain(key):  # 確実にないなら、ファイルを読まずに済む
            return False, None
        i = bisect_right([k for k, _ in self.index], key) - 1
        if i < 0:
            return False, None
        self.reads += 1
        with open(self.path, "rb") as f:
            f.seek(self.index[i][1])  # 疎な索引で、キーがありうる 16 件のかたまりだけを読む
            for _ in range(self.BLOCK):
                line = f.readline()
                if not line:
                    break
                k, v = json.loads(line)
                if k == key:
                    return True, v
                if k > key:
                    break
        return False, None

    def items(self) -> Iterator[tuple[str, str | None]]:
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                k, v = json.loads(line)
                yield k, v

    def __len__(self) -> int:
        return self.count

    def __repr__(self) -> str:
        return f"SSTable(seq={self.seq}, tier={self.tier}, count={self.count})"


WAL_FILE = "wal.log"


# ---------------------------------------------------------------------------
# 演習2: LSM 木
# ---------------------------------------------------------------------------

class LSMTree:
    """LSM 木。

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     with LSMTree(d, memtable_limit=2) as db:
    ...         db.put("a", "1"); db.put("b", "2")    # 2 件で memtable が一杯 → SSTable へ
    ...         db.put("a", "3"); db.delete("b")      # 新しい値と墓標が、古い SSTable の値を隠す
    ...         db.get("a"), db.get("b"), db.scan()
    ('3', None, [('a', '3')])
    """

    # -----------------------------------------------------------------------
    # 演習2-1（★★☆）: 起動・WAL・書き込み
    # -----------------------------------------------------------------------

    def __init__(self, directory: str | os.PathLike, *, memtable_limit: int = 4, tier_size: int = 3,
                 sync: bool = False) -> None:
        """ディレクトリ（なければ作る）を開き、クラッシュ前の状態を復元する。

        - memtable_limit < 1 または tier_size < 2 なら ValueError。
        - self.dir, self.memtable_limit, self.tier_size, self.sync を設定する。
        - 名前が .tmp で終わるファイル（書きかけの SSTable）を削除する。
        - *.sst を SSTable(path) で開き、連番の降順に self.sstables に並べる。
          次に使う連番は、既存の最大の連番 + 1（なければ 1）。
        - self.memtable = {} とし、wal.log を先頭から再生する（["put", k, v] → memtable[k] = v、
          ["del", k] → memtable[k] = None）。改行で終わっていない行や JSON として不正な行に
          出会ったら、そこから後ろを書きかけの末尾とみなして wal.log を切り詰め、捨てたバイト数を
          self.wal_truncated_bytes に入れる（なければ 0）。再生中はフラッシュしなくてよい。
        - WAL を追記用に開いたままにする。
        """
        raise NotImplementedError("演習2-1: __init__ を実装してください")

    def put(self, key: str, value: str) -> None:
        """WAL に追記して（flush。sync=True なら os.fsync も）から memtable に入れる。

        memtable のキーの数が memtable_limit 以上になったら flush() する。
        """
        raise NotImplementedError("演習2-1: put を実装してください")

    def delete(self, key: str) -> None:
        """WAL に ["del", key] を追記し、memtable に墓標（None）を入れる。put と同じくフラッシュする。

        memtable から消すだけではいけない。古い SSTable にある値を隠すために墓標が必要。
        """
        raise NotImplementedError("演習2-1: delete を実装してください")

    # -----------------------------------------------------------------------
    # 演習2-2（★★☆）: 読み取りの経路
    # -----------------------------------------------------------------------

    def get(self, key: str) -> str | None:
        """memtable → SSTable（新しい順）の順に探し、最初に見つかったものを返す。墓標なら None。

        見つかった時点で探すのをやめること（古い SSTable は読まない）。
        """
        raise NotImplementedError("演習2-2: get を実装してください")

    def scan(self, lo: str | None = None, hi: str | None = None) -> list[tuple[str, str]]:
        """lo <= キー < hi の (キー, 値) を、キーの昇順で返す（墓標のキーは含めない）。

        lo / hi が None なら、その側は制限なし。memtable（ソートしたもの）とすべての SSTable を
        k-way マージし、同じキーは最も新しいソースの値を採用する。

        ヒント: 各ソースを (キー, ソースの番号, 値) の列にして heapq.merge に渡すと、同じキーでは
        番号の小さい（新しい）ソースが先に出てくる。
        """
        raise NotImplementedError("演習2-2: scan を実装してください")

    # -----------------------------------------------------------------------
    # 演習2-3（★★★）: フラッシュとコンパクション
    # -----------------------------------------------------------------------

    def flush(self) -> None:
        """memtable を tier 0 の SSTable に書き出す（空なら何もしない）。

        1. SSTable.write(self.dir, 次の連番, 0, キーの昇順に並べた memtable の項目（墓標も含む）)
        2. self.sstables の先頭に加え、memtable を空にする。
        3. WAL を空にする（SSTable が永続化された後で行うこと。順序が逆だと、その間の
           クラッシュでデータを失う）。
        4. コンパクションの条件を調べる（下記）。

        段ごとのコンパクション（size-tiered の簡略版）:
          新しい方から tier_size 個の SSTable がすべて同じ段 t なら、それらを 1 つにまとめて
          段 t + 1 の SSTable にする（新しい連番を付けて self.sstables の先頭に置き、元のファイルは
          削除する）。まとめた結果、また条件を満たすなら繰り返す。
          まとめるときは、同じキーは最も新しい値を採用する。墓標は、すべての SSTable を
          まとめるとき（それより古いデータが残らないとき）だけ捨ててよい。まとめた結果が空なら
          新しい SSTable は作らない。

        この規則では、段 t の SSTable は tier_size 個たまるごとに 1 段上がるので、SSTable の数は
        「tier_size 進数の各桁の数の合計」程度に抑えられる。
        """
        raise NotImplementedError("演習2-3: flush を実装してください")

    def compact_all(self) -> None:
        """すべての SSTable を 1 つにまとめる（墓標は捨てる）。段は既存の最大の段にする。

        SSTable がなければ何もしない。memtable は対象外（必要なら先に flush() する）。
        """
        raise NotImplementedError("演習2-3: compact_all を実装してください")

    # --- 提供済み ---------------------------------------------------------------

    def close(self) -> None:
        """WAL のファイルを閉じる（__init__ で self._wal に開いた前提）。memtable は WAL に残る。"""
        wal = getattr(self, "_wal", None)
        if wal is not None and not wal.closed:
            wal.close()

    def __enter__(self) -> LSMTree:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
