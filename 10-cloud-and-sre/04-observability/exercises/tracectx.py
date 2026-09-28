"""10.4 オブザーバビリティ — 演習: W3C Trace Context とスパンの解析

サービス間でトレースの文脈を運ぶ HTTP ヘッダー traceparent（W3C Trace Context）を解析・生成し、
集めたスパンから木を組み立てて、各スパンの自己時間と、リクエストの遅延を決めている
クリティカルパスを計算します。

- 演習5（★★☆）: parse_traceparent, format_traceparent, new_trace, child
- 演習6（★★★）: build_tree, self_times, self_time_by_service, critical_path

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 10.4

traceparent の形式（バージョン 00）: "{version}-{trace-id}-{parent-id}-{trace-flags}"
    例: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    version 2 桁 / trace-id 32 桁 / parent-id 16 桁 / trace-flags 2 桁。すべて小文字の 16 進数。

簡略化している点: tracestate ヘッダー、Trace Context Level 2 で追加されたフラグ、
スパンのリンクやイベントは扱いません。
"""
from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Sequence

# ===========================================================================
# 提供コード（演習の対象ではありません）
# ===========================================================================

SAMPLED = 0x01


@dataclass(frozen=True)
class TraceParent:
    version: str      # 2 桁の 16 進数（小文字）。この演習で生成するのは "00" だけ
    trace_id: str     # 32 桁の 16 進数（小文字）。トレース全体の ID
    parent_id: str    # 16 桁の 16 進数（小文字）。送信元のスパンの ID
    flags: int        # 0〜255。最下位ビットが sampled

    @property
    def sampled(self) -> bool:
        return bool(self.flags & SAMPLED)


@dataclass(frozen=True)
class Span:
    span_id: str
    parent_id: str | None   # ルートのスパンは None
    name: str
    service: str
    start: float            # ミリ秒
    end: float


@dataclass
class SpanTree:
    root: Span
    spans: dict[str, Span]              # span_id → Span
    children: dict[str, list[Span]]     # span_id → 子スパン（start、span_id の順）


# ===========================================================================
# 演習5（★★☆）: traceparent の解析・生成・伝播
# ===========================================================================

def parse_traceparent(header: str) -> TraceParent:
    """traceparent ヘッダーの値を解析する。不正なら ValueError。

    規則（W3C Trace Context Level 1）:
    - 前後の空白とタブは取り除いてから解析する。55 文字未満は不正。
    - version は小文字の 16 進数 2 桁で、"ff" は不正。
    - 3・36・53 文字目（0 始まりで 2・35・52）は "-"。
    - trace-id は小文字の 16 進数 32 桁で、すべて "0" は不正。parent-id は 16 桁で、すべて "0" は不正。
    - trace-flags は小文字の 16 進数 2 桁。
    - version が "00" なら全体でちょうど 55 文字（後ろに何か付いていれば不正）。
    - version が "00" 以外（将来のバージョン）なら、先頭 55 文字を上の規則で読み、56 文字目以降があれば
      56 文字目は "-" でなければならない（残りは無視する）。version はそのまま返す。
    - 大文字の 16 進数は不正。

    >>> parse_traceparent("00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01").sampled
    True
    """
    raise NotImplementedError("演習5: parse_traceparent を実装してください")


def format_traceparent(tp: TraceParent) -> str:
    """TraceParent をヘッダーの文字列にする。flags は小文字 2 桁の 16 進数（1 → "01"）。"""
    raise NotImplementedError("演習5: format_traceparent を実装してください")


def new_trace(rng: random.Random, sampled: bool = True) -> TraceParent:
    """新しいトレースを始める（リクエストの入口で、受け取った traceparent がないときに使う）。

    version "00"、trace-id は rng.getrandbits(128)、parent-id は rng.getrandbits(64) から作った
    小文字 16 進数（ゼロ埋め）。値が 0 なら引き直す（すべて 0 の ID は無効）。
    flags は sampled なら 0x01、そうでなければ 0x00。
    """
    raise NotImplementedError("演習5: new_trace を実装してください")


def child(parent: TraceParent, rng: random.Random) -> TraceParent:
    """受け取った文脈の中で新しいスパンを作り、次の呼び出し先に送る TraceParent を返す。

    - trace-id は parent と同じ（同じトレースに属する）
    - parent-id は新しいスパンの ID（rng.getrandbits(64) から。0 なら引き直す）
    - flags は sampled ビットだけを引き継ぎ、それ以外のビットは 0 にする（Level 1 の規定）
    - version は "00"（受け取ったのが将来のバージョンでも、自分が知っている形式で送る）
    """
    raise NotImplementedError("演習5: child を実装してください")


# ===========================================================================
# 演習6（★★★）: スパンの木・自己時間・クリティカルパス
# ===========================================================================

def build_tree(spans: Sequence[Span]) -> SpanTree:
    """スパンのリストから木を作る。

    - SpanTree(root, spans={span_id: Span}, children={span_id: 子のリスト})。children にはすべての
      span_id をキーとして入れ（子がなければ空リスト）、子は (start, span_id) の昇順に並べる。
    - 次の場合は ValueError: span_id の重複、end < start、parent_id が None のスパンがちょうど 1 つでない、
      parent_id が存在しないスパンを指している、ルートから辿れないスパンがある（親子関係の循環）。
    """
    raise NotImplementedError("演習6: build_tree を実装してください")


def self_times(tree: SpanTree) -> dict[str, float]:
    """各スパンの自己時間（子を待っていない時間）= (end - start) - (子の区間の和集合の長さ)。

    子の区間は、自分の区間 [start, end] に切り詰めてから和集合をとる（時計のずれで子がはみ出すことがある）。
    子どうしが並行して重なっている部分を二重に引かないこと（和集合であって合計ではない）。
    """
    raise NotImplementedError("演習6: self_times を実装してください")


def self_time_by_service(tree: SpanTree) -> dict[str, float]:
    """self_times をサービスごとに合計し、合計の降順（同じならサービス名の昇順）の dict で返す。"""
    raise NotImplementedError("演習6: self_time_by_service を実装してください")


def critical_path(tree: SpanTree) -> list[tuple[str, float, float]]:
    """クリティカルパス（ルートの終了時刻を決めている仕事の連なり）を返す。

    返り値は (span_id, 開始, 終了) の区間のリストで、時刻順に隙間なく並び、ルートの start から end までを覆う。
    長さ 0 の区間は含めない。

    アルゴリズム（終わりから逆向きに辿る）:
    walk(スパン, lo, hi): lo〜hi はそのスパンの（親に切り詰めた）区間
      1. 子の区間を [lo, hi] に切り詰め（長さ 0 以下になった子は捨てる）、終了の遅い順に並べる
         （終了が同じなら開始の早い順、次に span_id の順）
      2. cursor = hi。並べた順に子を見て、子の終了 > cursor ならその子は飛ばす（別の子と並行していた）。
         そうでなければ: 子の終了 < cursor なら (自分, 子の終了, cursor) は自分の仕事の区間。
         子について walk(子, 子の開始, 子の終了) を行い、cursor = 子の開始 にする。
      3. 最後に lo < cursor なら (自分, lo, cursor) も自分の仕事の区間。
    ルートについて walk(root, root.start, root.end) を行い、集めた区間を時刻順に並べて返す。

    並行して呼んだ 2 つの呼び出しのうち先に終わる方は、クリティカルパスに現れない。
    つまり、それを速くしてもリクエスト全体は速くならない。
    """
    raise NotImplementedError("演習6: critical_path を実装してください")
