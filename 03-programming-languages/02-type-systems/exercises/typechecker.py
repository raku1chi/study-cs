"""3.2 型システム — 演習3・4: 型検査器と型推論

小さな式言語の型検査器（演習3）と、単一化による型推論（演習4、発展）を実装します。
型・式（抽象構文木）のデータクラス、型の表示関数などは与えられています。
`check` と `infer` の `raise NotImplementedError(...)` を実装に置き換えてください。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.2

このディレクトリで演習ごとに実行することもできます:
    python3 -m unittest -v test_typechecker.TestExercise3Check
    python3 -m unittest -v test_typechecker.TestExercise4Infer

対象の言語（構文は README を参照。ここでは構文木を直接組み立ててテストします）:
    リテラル   1, true, "abc"                          IntLit / BoolLit / StrLit
    変数       x                                       Var
    二項演算   x + 1, a < b, p and q, s ++ "!"         BinOp
    単項演算   -x, not p                               UnaryOp
    条件式     if c then a else b                      If
    局所変数   let x = e1 in e2                        Let
    関数       fn (x: int) => x + 1                    Lambda（型注釈あり）
               fn x => x + 1                           Lambda（型注釈なし: 演習4）
    関数適用   f 42                                    App（引数は 1 つ。複数引数はカリー化で表す）
    組         (1, true), fst p, snd p                 Pair / Fst / Snd

型付け規則（Γ は「変数名 → 型」の環境）:
    int / bool / str のリテラル     → それぞれ int / bool / str
    変数 x                          → Γ(x)。Γ になければエラー
    + - * / %                       → 両辺 int なら int
    < <= > >=                       → 両辺 int なら bool
    == !=                           → 両辺が同じ型で、関数型でなければ bool
    and or                          → 両辺 bool なら bool
    ++                              → 両辺 str なら str（文字列連結。+ とは別の演算子）
    単項 -  / not                   → int なら int / bool なら bool
    if c then a else b              → c が bool で、a と b が同じ型 T なら T
    let x = e1 in e2                → e1 の型を T1 として、Γ に x: T1 を加えて e2 を検査した型
    fn (x: T) => e                  → Γ に x: T を加えて e の型を R とすると、T -> R
    f a                             → f が T -> R 型で、a が T 型なら R
    (a, b)                          → a が A 型、b が B 型なら (A, B)
    fst p / snd p                   → p が (A, B) 型なら A / B
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union


# ---------------------------------------------------------------------------
# 型（与えられたもの）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TInt:
    """int 型"""


@dataclass(frozen=True)
class TBool:
    """bool 型"""


@dataclass(frozen=True)
class TStr:
    """str 型"""


@dataclass(frozen=True)
class TFun:
    """関数型 param -> result"""

    param: Type
    result: Type


@dataclass(frozen=True)
class TPair:
    """組の型 (first, second)"""

    first: Type
    second: Type


@dataclass(frozen=True)
class TVar:
    """型変数 'a（演習4 の型推論で「まだ分からない型」を表す）"""

    name: str


Type = Union[TInt, TBool, TStr, TFun, TPair, TVar]


def show_type(t: Type) -> str:
    """型を読みやすい文字列にする（与えられたもの）。エラーメッセージに使ってください。

    >>> show_type(TFun(TFun(TInt(), TInt()), TFun(TInt(), TBool())))
    '(int -> int) -> int -> bool'
    >>> show_type(TPair(TVar("a"), TStr()))
    "('a, str)"

    -> は右結合: int -> int -> bool は int -> (int -> bool) の意味。
    """
    match t:
        case TInt():
            return "int"
        case TBool():
            return "bool"
        case TStr():
            return "str"
        case TVar(name):
            return "'" + name
        case TPair(first, second):
            return f"({show_type(first)}, {show_type(second)})"
        case TFun(param, result):
            p = show_type(param)
            if isinstance(param, TFun):
                p = f"({p})"
            return f"{p} -> {show_type(result)}"
    raise TypeError(f"型ではありません: {t!r}")


def normalize_type_vars(t: Type) -> Type:
    """型変数の名前を、左から現れた順に 'a, 'b, 'c, ... に付け直す（与えられたもの）。

    演習4 の infer は、最後にこの関数を通した型を返してください（テストはこの形で比較します）。

    >>> show_type(normalize_type_vars(TFun(TVar("t7"), TFun(TVar("t3"), TVar("t7")))))
    "'a -> 'b -> 'a"
    """
    mapping: dict[str, str] = {}

    def fresh_name(i: int) -> str:
        return "abcdefghijklmnopqrstuvwxyz"[i] if i < 26 else f"t{i}"

    def go(u: Type) -> Type:
        match u:
            case TVar(name):
                if name not in mapping:
                    mapping[name] = fresh_name(len(mapping))
                return TVar(mapping[name])
            case TFun(param, result):
                p = go(param)
                return TFun(p, go(result))
            case TPair(first, second):
                f = go(first)
                return TPair(f, go(second))
            case _:
                return u

    return go(t)


# ---------------------------------------------------------------------------
# 式（抽象構文木。与えられたもの）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntLit:
    value: int


@dataclass(frozen=True)
class BoolLit:
    value: bool


@dataclass(frozen=True)
class StrLit:
    value: str


@dataclass(frozen=True)
class Var:
    name: str


@dataclass(frozen=True)
class BinOp:
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class UnaryOp:
    op: str
    operand: Expr


@dataclass(frozen=True)
class If:
    cond: Expr
    then: Expr
    else_: Expr


@dataclass(frozen=True)
class Let:
    name: str
    value: Expr
    body: Expr


@dataclass(frozen=True)
class Lambda:
    param: str
    param_type: Type | None  # None なら型注釈なし（演習4 の infer でのみ扱う）
    body: Expr


@dataclass(frozen=True)
class App:
    func: Expr
    arg: Expr


@dataclass(frozen=True)
class Pair:
    first: Expr
    second: Expr


@dataclass(frozen=True)
class Fst:
    pair: Expr


@dataclass(frozen=True)
class Snd:
    pair: Expr


Expr = Union[IntLit, BoolLit, StrLit, Var, BinOp, UnaryOp, If, Let, Lambda, App, Pair, Fst, Snd]


class TypeCheckError(Exception):
    """型エラー（与えられたもの）。メッセージで原因を説明する。"""


INT, BOOL, STR = TInt(), TBool(), TStr()

# 演算子の型（与えられたもの）: (左辺の型, 右辺の型, 結果の型)。== と != は別扱い
BINARY_OPS: dict[str, tuple[Type, Type, Type]] = {
    "+": (INT, INT, INT),
    "-": (INT, INT, INT),
    "*": (INT, INT, INT),
    "/": (INT, INT, INT),
    "%": (INT, INT, INT),
    "<": (INT, INT, BOOL),
    "<=": (INT, INT, BOOL),
    ">": (INT, INT, BOOL),
    ">=": (INT, INT, BOOL),
    "and": (BOOL, BOOL, BOOL),
    "or": (BOOL, BOOL, BOOL),
    "++": (STR, STR, STR),
}
EQUALITY_OPS = ("==", "!=")
UNARY_OPS: dict[str, tuple[Type, Type]] = {"-": (INT, INT), "not": (BOOL, BOOL)}


# ---------------------------------------------------------------------------
# 演習3（★★★）: 型検査器
# ---------------------------------------------------------------------------

def check(expr: Expr, env: Mapping[str, Type] | None = None) -> Type:
    """式 expr の型を求める。型が合わなければ TypeCheckError を送出する。

    - env は自由変数の型（省略時は空）。env 自体を書き換えてはいけない。
    - 規則はモジュールの docstring の「型付け規則」の通り。
    - 型注釈のない Lambda（param_type が None）は TypeCheckError とする（演習4 で扱う）。
    - 未知の演算子は TypeCheckError。式ではない値（Expr のどのクラスでもない）は TypeError。

    エラーメッセージの要件（テストで確認します）:
    - 型が合わないときは、関係する型を show_type で表示した文字列（"int"、"bool"、
      "int -> int" など）をメッセージに含めること。
      例: 「+ の左辺は int でなければなりませんが、bool でした」
    - 未定義の変数は、その変数名をメッセージに含めること。

    >>> check(BinOp("+", IntLit(1), IntLit(2)))
    TInt()
    >>> show_type(check(Lambda("x", INT, BinOp("<", Var("x"), IntLit(10)))))
    'int -> bool'

    ヒント: match 文で式の種類ごとに場合分けし、部分式の型を再帰的に求める。
    「期待した型と実際の型を比べ、違えばエラー」という補助関数を作ると見通しがよい。
    """
    raise NotImplementedError("演習3: check を実装してください")


# ---------------------------------------------------------------------------
# 演習4（★★★ 発展）: 単一化による型推論
# ---------------------------------------------------------------------------

def infer(expr: Expr, env: Mapping[str, Type] | None = None) -> Type:
    """型注釈のない関数を含む式の型を推論する。型が合わなければ TypeCheckError。

    check と同じ規則に加えて、次を扱う:
    - 型注釈のない Lambda の引数には、新しい型変数（例: TVar("t1")）を割り当てる。
    - 「この 2 つの型は等しくなければならない」という制約が出るたびに単一化（unify）し、
      型変数に何が入るか（代入, substitution）を記録していく。
    - 関数適用 f a では、新しい型変数 r を作り、「f の型 = (a の型) -> r」を単一化する。
    - fst p / snd p では、新しい型変数 A, B を作り、「p の型 = (A, B)」を単一化する。
    - 出現検査（occurs check）: 型変数 'a を 'a 自身を含む型（'a -> int など）と
      等しくしようとしたら、無限の型になるので TypeCheckError（例: fn x => x x）。
    - == と != は両辺を単一化する。解決後の型が関数型ならエラー（型変数のままなら許す）。
    - let は単相でよい（let 多相は扱わなくてよい）。
    - 最後に、代入をすべて適用した型を normalize_type_vars に通して返す。

    >>> show_type(infer(Lambda("x", None, BinOp("+", Var("x"), IntLit(1)))))
    'int -> int'
    >>> show_type(infer(Lambda("x", None, Var("x"))))
    "'a -> 'a"
    >>> f, x = Var("f"), Var("x")
    >>> show_type(infer(Lambda("f", None, Lambda("x", None, App(f, App(f, x))))))
    "('a -> 'a) -> 'a -> 'a"

    ヒント: 代入を dict[str, Type] で持ち、型変数を「代入をたどった先の型」に置き換える
    関数（prune / resolve）と、unify(a, b) を作る。unify は
      - 同じ型なら何もしない
      - 片方が型変数なら（出現検査のうえで）代入に追加
      - 両方が TFun なら引数どうし・結果どうしを unify（TPair も同様）
      - それ以外はエラー
    """
    raise NotImplementedError("演習4: infer を実装してください")
