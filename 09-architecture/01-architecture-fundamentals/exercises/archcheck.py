"""9.1 ソフトウェアアーキテクチャの基礎 — 演習: アーキテクチャ適応度関数（archcheck）

「ドメイン層はインフラに依存しない」「循環依存を作らない」といったアーキテクチャの規則は、
文書に書くだけではすぐに破られます。この演習では、規則を **自動テストとして CI で実行できる形**
（進化的アーキテクチャでいう適応度関数, fitness function）にする小さなツールを作ります。

    1. Python の import を ast で解析し（コードを実行せずに）
    2. モジュール間の依存グラフを作り
    3. 設定ファイル（JSON）のレイヤー規則に照らして違反を見つけ
    4. 循環依存を検出して、具体的な循環の経路を示す

検査対象のサンプルは data/shop_app/ にあります（shop パッケージと rules.json）。
このサンプルは import されず、テキストとして解析されるだけです。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 9.1
    python3 tools/check.py -v 9.1

完成したら、コマンドとしても使えます（exercises/ で）:
    python3 archcheck.py data/shop_app data/shop_app/rules.json

制約:
    - import の解析には ast を使うこと（正規表現では、文字列やコメントの中の import に騙される）。
    - 検査対象のコードを import・実行しないこと（副作用のあるコードもあるため）。
    - 演習5 では graphlib などの既製の循環検出を使わず、自分で実装すること。
"""
from __future__ import annotations

import ast  # noqa: F401  演習2で使います
import json
import sys
from collections import deque  # noqa: F401  演習5で使えます
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# 設定とデータ型（演習ではなく、最初から実装済みの部分）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Rules:
    """レイヤー規則。

    - layers: レイヤー名 → モジュール名の接頭辞（例: {"domain": "shop.domain"}）。
      "shop.domain" 自身と "shop.domain." で始まるモジュールがそのレイヤーに属する。
    - allowed: レイヤー名 → 依存してよい「他の」レイヤー名の集合（同じレイヤー内の依存は常に許可）。
    - forbidden_external: レイヤー名 → 使用を禁止する外部モジュールのトップレベル名
      （例: {"domain": {"sqlite3"}}）。
    - ignore: レイヤー検査の対象外にするモジュール名（完全一致。例: トップレベルの "shop"）。
    """

    layers: dict[str, str]
    allowed: dict[str, frozenset[str]]
    forbidden_external: dict[str, frozenset[str]] = field(default_factory=dict)
    ignore: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        layers = dict(data["layers"])
        allowed = {name: frozenset(data.get("allowed", {}).get(name, [])) for name in layers}
        unknown = {dep for deps in allowed.values() for dep in deps} - set(layers)
        if unknown:
            raise ValueError(f"allowed に未定義のレイヤーがあります: {sorted(unknown)}")
        forbidden = {k: frozenset(v) for k, v in data.get("forbidden_external", {}).items()}
        return cls(layers, allowed, forbidden, frozenset(data.get("ignore", [])))


def load_rules(path: Path) -> Rules:
    """JSON ファイルから Rules を読み込む（形式は data/shop_app/rules.json を参照）。"""
    return Rules.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True, order=True)
class Violation:
    """規則違反 1 件。kind は "layer" / "external" / "unassigned" のいずれか。

    - layer:      source（モジュール）→ target（モジュール）が許可されていないレイヤー間の依存
    - external:   source（モジュール）が禁止された外部モジュール target を使っている
    - unassigned: source（モジュール）がどのレイヤーにも属していない（target は ""）
    message は人間向けの説明で、比較・並べ替えには使わない。
    """

    kind: str
    source: str
    target: str
    message: str = field(compare=False)


@dataclass
class DependencyGraph:
    """依存グラフ。

    - internal: モジュール名 → 依存先の「内部」モジュール名の集合（すべての内部モジュールがキーになる）
    - external: モジュール名 → import している外部モジュールのトップレベル名の集合
    """

    internal: dict[str, set[str]]
    external: dict[str, set[str]]


# ---------------------------------------------------------------------------
# 演習1（★☆☆）: モジュール名と相対 import の解決
# ---------------------------------------------------------------------------

def module_name(path: Path, root: Path) -> str:
    """root（sys.path に入る場所）からの相対パスを、ドット区切りのモジュール名にする。

    >>> module_name(Path("src/shop/domain/order.py"), Path("src"))
    'shop.domain.order'
    >>> module_name(Path("src/shop/domain/__init__.py"), Path("src"))   # パッケージそのもの
    'shop.domain'

    root 直下の __init__.py のように名前が空になる場合は ValueError。
    """
    raise NotImplementedError("演習1: module_name を実装してください")


def resolve_relative(module: str, is_package: bool, level: int, name: str | None) -> str:
    """相対 import（from . import x / from ..y import z）の基準となる絶対モジュール名を返す。

    - module: import 文が書かれているモジュールの名前
    - is_package: そのモジュールがパッケージ（__init__.py）なら True
    - level: 先頭のドットの数（1 以上。0 以下なら ValueError）
    - name: ドットの後ろに書かれた名前（"from . import x" なら None、"from ..y.z import w" なら "y.z"）

    規則: まず「自分が属するパッケージ」を起点にする（パッケージ自身なら自分、普通のモジュールなら親）。
    level が 1 増えるごとに 1 つ上のパッケージに上がり、最後に name を連結する。
    トップレベルより上に出ようとしたら ValueError（Python の実行時と同じく不正）。

    >>> resolve_relative("shop.domain.order", False, 1, "money")
    'shop.domain.money'
    >>> resolve_relative("shop.domain.order", False, 2, None)
    'shop'
    >>> resolve_relative("shop.domain", True, 1, "money")      # shop/domain/__init__.py の中
    'shop.domain.money'
    """
    raise NotImplementedError("演習1: resolve_relative を実装してください")


# ---------------------------------------------------------------------------
# 演習2（★★☆）: ast で import を抽出する
# ---------------------------------------------------------------------------

def imports_of(source: str, module: str, is_package: bool = False) -> set[str]:
    """ソースコード中のすべての import を、絶対的なドット区切りの名前の集合として返す。

    - "import a.b.c" / "import a.b as x"   → "a.b.c" / "a.b"
    - "from x.y import z"                  → "x.y.z"（z がサブモジュールか関数かはここでは区別しない）
    - "from x import *"                    → "x"
    - "from . import z" などの相対 import   → resolve_relative で絶対名にしてから同様に扱う
    - "from __future__ import ..." は依存関係ではないので含めない
    - 関数の中・クラスの中・if TYPE_CHECKING: の中・try の中の import もすべて含める
    - 構文エラーのソースは SyntaxError をそのまま送出してよい

    >>> sorted(imports_of("import os\\nfrom .money import Money", "shop.domain.order"))
    ['os', 'shop.domain.money.Money']

    ヒント: ast.parse → ast.walk で全ノードを巡回し、ast.Import と ast.ImportFrom を拾う。
    ImportFrom の node.level が相対 import のドットの数、node.module がその後ろの名前。
    """
    raise NotImplementedError("演習2: imports_of を実装してください")


# ---------------------------------------------------------------------------
# 演習3（★★☆）: 依存グラフを作る
# ---------------------------------------------------------------------------

def build_graph(root: Path) -> DependencyGraph:
    """root 以下のすべての .py ファイルを解析して DependencyGraph を返す。

    - root 以下の各 .py がモジュール（module_name で名前を付ける）。__pycache__ と、
      名前が "." で始まるディレクトリは無視する。root 直下の __init__.py は対象外。
    - imports_of が返した各名前を、次の規則で「内部の依存」か「外部の依存」に振り分ける:
        * 名前そのもの、またはそのドット区切りの接頭辞のうち、内部モジュールとして存在する
          **最も長いもの** への依存とする（"shop.domain.order.Order" → "shop.domain.order"）。
        * 内部モジュールが見つからず、先頭の要素（"sqlite3.dbapi2" なら "sqlite3"）が内部の
          トップレベル名でもなければ、外部依存としてその先頭の要素を記録する。
        * 自分自身への依存は記録しない。
    - internal と external には、依存がないモジュールも空集合をキーとして含める。

    ヒント: 1 回目のループでモジュール名の一覧を作り、2 回目のループで振り分ける。
    """
    raise NotImplementedError("演習3: build_graph を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★☆）: レイヤー規則の検査
# ---------------------------------------------------------------------------

def layer_of(module: str, rules: Rules) -> str | None:
    """モジュールが属するレイヤー名を返す（どこにも属さなければ None）。

    接頭辞はドット区切りの境界で比較すること: "shop.domainx" は "shop.domain" レイヤーではない。
    複数の接頭辞に一致したら、最も長い接頭辞のレイヤーを選ぶ。
    """
    raise NotImplementedError("演習4: layer_of を実装してください")


def check_rules(graph: DependencyGraph, rules: Rules) -> list[Violation]:
    """依存グラフをレイヤー規則で検査し、違反をソートして返す（重複なし）。

    1. unassigned: ignore に含まれず、どのレイヤーにも属さない内部モジュール 1 つにつき 1 件。
    2. layer: 内部の依存 source → target について、どちらも ignore になく、どちらもレイヤーに属し、
       レイヤーが異なり、かつ allowed[source のレイヤー] に target のレイヤーが含まれない場合。
       （どちらかがレイヤーに属さない辺は、1 の unassigned で報告済みなのでここでは報告しない）
    3. external: レイヤーに属する（ignore でない）モジュールが、そのレイヤーの
       forbidden_external に含まれる外部モジュールを使っている場合。

    Violation の message には、人が読んで直せる説明（どのレイヤーからどのレイヤーか等）を入れる。
    """
    raise NotImplementedError("演習4: check_rules を実装してください")


# ---------------------------------------------------------------------------
# 演習5（★★★）: 循環依存の検出
# ---------------------------------------------------------------------------

def find_cycles(edges: dict[str, set[str]]) -> list[list[str]]:
    """有向グラフの循環（強連結成分, SCC）を返す。

    - 要素が 2 つ以上の強連結成分、または自己ループ（a → a）を持つ 1 要素の成分を「循環」とする。
    - 各成分はノード名を昇順に並べたリスト、全体も昇順（先頭要素で比較）に並べて返す。
    - 辺の先にしか現れないノード（edges のキーにない名前）も頂点として扱う。
    - 数千モジュールが鎖状につながった巨大な循環でも RecursionError を起こさないこと
      （Python の再帰の深さの上限は既定で 1000 程度）。

    >>> find_cycles({"a": {"b"}, "b": {"a"}, "c": {"a"}})
    [['a', 'b']]

    ヒント: Tarjan の強連結成分分解を、再帰ではなく明示的なスタックで書く。
    （Kosaraju のアルゴリズムを反復で書いてもよい）
    """
    raise NotImplementedError("演習5: find_cycles を実装してください")


def cycle_example(edges: dict[str, set[str]], members: list[str]) -> list[str]:
    """強連結成分 members の中を通る、具体的な循環の経路を 1 つ返す（開発者に見せるため）。

    - 経路は members の最小の名前から出発して同じ名前に戻る: [start, ..., start]
    - 経路上の辺はすべて edges に存在し、経路上のノードはすべて members に含まれること。
    - start から start に戻る経路のうち、辺の数が最小のものを返す（同じ長さなら後続を名前の
      昇順に調べたときに最初に見つかるもの）。自己ループなら [start, start]。
    - members が空、または循環を構成していなければ ValueError。

    >>> cycle_example({"a": {"b"}, "b": {"c"}, "c": {"a"}}, ["a", "b", "c"])
    ['a', 'b', 'c', 'a']

    ヒント: start からの幅優先探索（BFS）で、各ノードの親を記録しておき、最後にたどり直す。
    """
    raise NotImplementedError("演習5: cycle_example を実装してください")


# ---------------------------------------------------------------------------
# 演習6（★☆☆）: まとめて実行する（CI で使えるコマンドにする）
# ---------------------------------------------------------------------------

@dataclass
class Report:
    violations: list[Violation]
    cycles: list[list[str]]

    @property
    def ok(self) -> bool:
        return not self.violations and not self.cycles


def run_check(root: Path, rules: Rules) -> Report:
    """build_graph → check_rules → find_cycles をまとめて実行し、Report を返す。"""
    raise NotImplementedError("演習6: run_check を実装してください")


def format_report(report: Report, edges: dict[str, set[str]] | None = None) -> str:
    """Report を人が読むための複数行の文字列にする。

    - 違反 1 件につき 1 行: "[kind] message"
    - 循環 1 件につき 1 行: "[cycle] a → b → a"（edges があれば cycle_example の経路を " → " で連結。
      なければ成分のノード名を ", " で連結）
    - 最終行: 問題がなければ "OK: 違反はありません"、あれば "NG: 違反 N 件 / 循環 M 件"
    """
    raise NotImplementedError("演習6: format_report を実装してください")


def main(argv: list[str] | None = None) -> int:
    """コマンドラインの入口: main([ソースのルート, 規則の JSON のパス])。

    - 引数が 2 個でなければ使い方を標準エラーに出して 2 を返す。
    - 検査結果（format_report の出力）を標準出力に出す。
    - 問題がなければ 0、違反か循環があれば 1 を返す（CI のジョブを失敗させるため）。
    """
    raise NotImplementedError("演習6: main を実装してください")


if __name__ == "__main__":
    sys.exit(main())
