"""10.4 オブザーバビリティ — 演習（W3C Trace Context とスパンの解析）の解答例

演習の仕様は exercises/tracectx.py の docstring を参照してください。
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
# 演習5: traceparent の解析・生成・伝播
# ===========================================================================

_HEX = re.compile(r"[0-9a-f]+")


def _is_hex(s: str, length: int) -> bool:
    return len(s) == length and _HEX.fullmatch(s) is not None


def parse_traceparent(header: str) -> TraceParent:
    value = header.strip(" \t")
    if len(value) < 55:
        raise ValueError("traceparent が短すぎます")
    version = value[:2]
    if not _is_hex(version, 2) or version == "ff":
        raise ValueError(f"不正なバージョンです: {version!r}")
    # 固定位置の区切り文字。大文字の 16 進数は仕様上不正
    if value[2] != "-" or value[35] != "-" or value[52] != "-":
        raise ValueError("区切り文字の位置が不正です")
    trace_id, parent_id, flags = value[3:35], value[36:52], value[53:55]
    if not _is_hex(trace_id, 32) or trace_id == "0" * 32:
        raise ValueError("trace-id は 32 桁の小文字の 16 進数で、すべて 0 ではいけません")
    if not _is_hex(parent_id, 16) or parent_id == "0" * 16:
        raise ValueError("parent-id は 16 桁の小文字の 16 進数で、すべて 0 ではいけません")
    if not _is_hex(flags, 2):
        raise ValueError("trace-flags は 2 桁の小文字の 16 進数です")
    if version == "00":
        if len(value) != 55:
            raise ValueError("バージョン 00 の traceparent は 55 文字ちょうどです")
    elif len(value) > 55 and value[55] != "-":
        # 将来のバージョンは後ろにフィールドが増えうる。知っている部分だけを読み、残りは無視する
        raise ValueError("将来のバージョンでも、flags の後は文字列の終わりか '-' でなければなりません")
    return TraceParent(version, trace_id, parent_id, int(flags, 16))


def format_traceparent(tp: TraceParent) -> str:
    return f"{tp.version}-{tp.trace_id}-{tp.parent_id}-{tp.flags:02x}"


def _random_hex(rng: random.Random, bits: int) -> str:
    while True:
        value = rng.getrandbits(bits)
        if value:  # すべて 0 の ID は無効
            return f"{value:0{bits // 4}x}"


def new_trace(rng: random.Random, sampled: bool = True) -> TraceParent:
    return TraceParent("00", _random_hex(rng, 128), _random_hex(rng, 64), SAMPLED if sampled else 0)


def child(parent: TraceParent, rng: random.Random) -> TraceParent:
    # 同じトレースの中で新しいスパンを作り、その ID を次の呼び出し先への parent-id にする。
    # 知っているのは sampled フラグだけなので、他のビットは 0 にして、バージョン 00 で送る
    return TraceParent("00", parent.trace_id, _random_hex(rng, 64), parent.flags & SAMPLED)


# ===========================================================================
# 演習6: スパンの木・自己時間・クリティカルパス
# ===========================================================================

def build_tree(spans: Sequence[Span]) -> SpanTree:
    by_id: dict[str, Span] = {}
    for s in spans:
        if s.span_id in by_id:
            raise ValueError(f"span_id が重複しています: {s.span_id}")
        if s.end < s.start:
            raise ValueError(f"end が start より前です: {s.span_id}")
        by_id[s.span_id] = s
    roots = [s for s in spans if s.parent_id is None]
    if len(roots) != 1:
        raise ValueError(f"ルートのスパンはちょうど 1 つ必要です（{len(roots)} 個）")
    children: dict[str, list[Span]] = defaultdict(list)
    for s in spans:
        if s.parent_id is not None:
            if s.parent_id not in by_id:
                raise ValueError(f"親が見つかりません: {s.span_id} → {s.parent_id}")
            children[s.parent_id].append(s)
    for kids in children.values():
        kids.sort(key=lambda s: (s.start, s.span_id))
    # ルートから辿れないスパン（親子の循環）を検出する
    seen, stack = set(), [roots[0].span_id]
    while stack:
        sid = stack.pop()
        seen.add(sid)
        stack.extend(c.span_id for c in children.get(sid, []))
    if len(seen) != len(by_id):
        raise ValueError("ルートから辿れないスパンがあります（親子関係が循環している）")
    return SpanTree(roots[0], by_id, {sid: children.get(sid, []) for sid in by_id})


def _union_length(intervals: list[tuple[float, float]]) -> float:
    total, cur_start, cur_end = 0.0, None, None
    for s, e in sorted(intervals):
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total += cur_end - cur_start
    return total


def self_times(tree: SpanTree) -> dict[str, float]:
    result = {}
    for sid, span in tree.spans.items():
        # 子の区間を自分の区間に切り詰めてから和集合をとる。並行する子を二重に引かないため
        clipped = [(max(c.start, span.start), min(c.end, span.end)) for c in tree.children[sid]]
        busy = _union_length([(s, e) for s, e in clipped if e > s])
        result[sid] = (span.end - span.start) - busy
    return result


def self_time_by_service(tree: SpanTree) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for sid, t in self_times(tree).items():
        totals[tree.spans[sid].service] += t
    return dict(sorted(totals.items(), key=lambda kv: (-kv[1], kv[0])))


def critical_path(tree: SpanTree) -> list[tuple[str, float, float]]:
    segments: list[tuple[str, float, float]] = []

    def walk(span: Span, lo: float, hi: float) -> None:
        # 子を親の区間 [lo, hi] に切り詰め、終わりの遅い順に並べる（同じなら長い方＝開始の早い方）
        kids = []
        for c in tree.children[span.span_id]:
            s, e = max(c.start, lo), min(c.end, hi)
            if e > s:
                kids.append((e, s, c))
        kids.sort(key=lambda k: (-k[0], k[1], k[2].span_id))
        cursor = hi
        for e, s, c in kids:
            if e > cursor:
                continue  # 今見ている時点より後に終わる子は、別の子と並行して走っていた
            if e < cursor:
                segments.append((span.span_id, e, cursor))  # 子を待っていない時間は自分の仕事
            walk(c, s, e)   # 最後に終わった子が、この時点までの遅延を決めている
            cursor = s
        if lo < cursor:
            segments.append((span.span_id, lo, cursor))

    walk(tree.root, tree.root.start, tree.root.end)
    segments.reverse()  # 後ろから辿って集めたので、時刻順に並べ直す
    return segments
