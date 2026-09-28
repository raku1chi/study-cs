"""3.2 型システム — 型検査器と型推論（解答例）

演習の仕様は exercises/typechecker.py の docstring を参照してください。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Union


# ---------------------------------------------------------------------------
# 型（与えられたもの）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TInt:
    pass


@dataclass(frozen=True)
class TBool:
    pass


@dataclass(frozen=True)
class TStr:
    pass


@dataclass(frozen=True)
class TFun:
    param: Type
    result: Type


@dataclass(frozen=True)
class TPair:
    first: Type
    second: Type


@dataclass(frozen=True)
class TVar:
    name: str


Type = Union[TInt, TBool, TStr, TFun, TPair, TVar]


def show_type(t: Type) -> str:
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
# 式（与えられたもの）
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
    param_type: Type | None
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
    """型エラー。メッセージで原因を説明する。"""


INT, BOOL, STR = TInt(), TBool(), TStr()

# 二項演算子の型: (左辺の型, 右辺の型, 結果の型)。== と != は別扱い
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
# 演習3: 型検査器（すべての引数に型注釈がある場合）
# ---------------------------------------------------------------------------

def _expect(actual: Type, expected: Type, what: str) -> None:
    if actual != expected:
        raise TypeCheckError(
            f"{what}は {show_type(expected)} でなければなりませんが、{show_type(actual)} でした"
        )


def check(expr: Expr, env: Mapping[str, Type] | None = None) -> Type:
    env = dict(env or {})
    match expr:
        case IntLit():
            return INT
        case BoolLit():
            return BOOL
        case StrLit():
            return STR
        case Var(name):
            if name not in env:
                raise TypeCheckError(f"未定義の変数です: {name}")
            return env[name]
        case BinOp(op, left, right) if op in EQUALITY_OPS:
            lt, rt = check(left, env), check(right, env)
            if lt != rt:
                raise TypeCheckError(
                    f"{op} の両辺の型が一致しません: {show_type(lt)} と {show_type(rt)}"
                )
            if isinstance(lt, TFun):
                raise TypeCheckError(f"{op} で関数（{show_type(lt)}）を比較することはできません")
            return BOOL
        case BinOp(op, left, right):
            if op not in BINARY_OPS:
                raise TypeCheckError(f"未知の演算子です: {op}")
            lt_expected, rt_expected, result = BINARY_OPS[op]
            _expect(check(left, env), lt_expected, f"{op} の左辺")
            _expect(check(right, env), rt_expected, f"{op} の右辺")
            return result
        case UnaryOp(op, operand):
            if op not in UNARY_OPS:
                raise TypeCheckError(f"未知の演算子です: {op}")
            expected, result = UNARY_OPS[op]
            _expect(check(operand, env), expected, f"単項 {op} の被演算子")
            return result
        case If(cond, then, else_):
            _expect(check(cond, env), BOOL, "if の条件")
            tt, et = check(then, env), check(else_, env)
            if tt != et:
                raise TypeCheckError(
                    f"if の両分岐の型が一致しません: then は {show_type(tt)}、else は {show_type(et)}"
                )
            return tt
        case Let(name, value, body):
            # 束縛した名前は body の中だけで見える（外側の env は変更しない）
            return check(body, {**env, name: check(value, env)})
        case Lambda(param, param_type, body):
            if param_type is None:
                raise TypeCheckError(
                    f"引数 {param} に型注釈がありません（注釈なしの関数は演習4の infer で扱います）"
                )
            return TFun(param_type, check(body, {**env, param: param_type}))
        case App(func, arg):
            ft = check(func, env)
            if not isinstance(ft, TFun):
                raise TypeCheckError(f"関数ではない値（{show_type(ft)}）を呼び出しています")
            at = check(arg, env)
            if at != ft.param:
                raise TypeCheckError(
                    f"引数の型が一致しません: {show_type(ft.param)} を期待しましたが "
                    f"{show_type(at)} が渡されました"
                )
            return ft.result
        case Pair(first, second):
            return TPair(check(first, env), check(second, env))
        case Fst(pair) | Snd(pair):
            pt = check(pair, env)
            if not isinstance(pt, TPair):
                name = "fst" if isinstance(expr, Fst) else "snd"
                raise TypeCheckError(f"{name} には組が必要ですが、{show_type(pt)} でした")
            return pt.first if isinstance(expr, Fst) else pt.second
    raise TypeError(f"式ではありません: {expr!r}")


# ---------------------------------------------------------------------------
# 演習4（発展）: 単一化による型推論
# ---------------------------------------------------------------------------

class _Inferencer:
    def __init__(self) -> None:
        self.subst: dict[str, Type] = {}  # 型変数の名前 → 判明した型
        self.counter = 0

    def fresh(self) -> TVar:
        self.counter += 1
        return TVar(f"t{self.counter}")

    def prune(self, t: Type) -> Type:
        """型変数なら、代入をたどって「今わかっている型」を返す（1 段だけ浅く）。"""
        while isinstance(t, TVar) and t.name in self.subst:
            t = self.subst[t.name]
        return t

    def resolve(self, t: Type) -> Type:
        """型の中のすべての型変数に代入を適用する（深く）。"""
        t = self.prune(t)
        match t:
            case TFun(param, result):
                return TFun(self.resolve(param), self.resolve(result))
            case TPair(first, second):
                return TPair(self.resolve(first), self.resolve(second))
            case _:
                return t

    def occurs(self, name: str, t: Type) -> bool:
        t = self.prune(t)
        match t:
            case TVar(n):
                return n == name
            case TFun(param, result):
                return self.occurs(name, param) or self.occurs(name, result)
            case TPair(first, second):
                return self.occurs(name, first) or self.occurs(name, second)
            case _:
                return False

    def unify(self, a: Type, b: Type, what: str) -> None:
        a, b = self.prune(a), self.prune(b)
        if a == b:
            return
        if isinstance(b, TVar) and not isinstance(a, TVar):
            a, b = b, a
        if isinstance(a, TVar):
            # 出現検査: 'a = 'a -> int のような「無限の型」を拒否する
            if self.occurs(a.name, b):
                raise TypeCheckError(
                    f"{what}: 型 {show_type(self.resolve(a))} が {show_type(self.resolve(b))} "
                    "の中に現れるため、無限の型になります"
                )
            self.subst[a.name] = b
            return
        if isinstance(a, TFun) and isinstance(b, TFun):
            self.unify(a.param, b.param, what)
            self.unify(a.result, b.result, what)
            return
        if isinstance(a, TPair) and isinstance(b, TPair):
            self.unify(a.first, b.first, what)
            self.unify(a.second, b.second, what)
            return
        raise TypeCheckError(
            f"{what}: {show_type(self.resolve(a))} と {show_type(self.resolve(b))} は一致しません"
        )

    def infer(self, expr: Expr, env: dict[str, Type]) -> Type:
        match expr:
            case IntLit():
                return INT
            case BoolLit():
                return BOOL
            case StrLit():
                return STR
            case Var(name):
                if name not in env:
                    raise TypeCheckError(f"未定義の変数です: {name}")
                return env[name]
            case BinOp(op, left, right) if op in EQUALITY_OPS:
                lt, rt = self.infer(left, env), self.infer(right, env)
                self.unify(lt, rt, f"{op} の両辺")
                if isinstance(self.prune(lt), TFun):
                    raise TypeCheckError(f"{op} で関数を比較することはできません")
                return BOOL
            case BinOp(op, left, right):
                if op not in BINARY_OPS:
                    raise TypeCheckError(f"未知の演算子です: {op}")
                lt_expected, rt_expected, result = BINARY_OPS[op]
                self.unify(self.infer(left, env), lt_expected, f"{op} の左辺")
                self.unify(self.infer(right, env), rt_expected, f"{op} の右辺")
                return result
            case UnaryOp(op, operand):
                if op not in UNARY_OPS:
                    raise TypeCheckError(f"未知の演算子です: {op}")
                expected, result = UNARY_OPS[op]
                self.unify(self.infer(operand, env), expected, f"単項 {op} の被演算子")
                return result
            case If(cond, then, else_):
                self.unify(self.infer(cond, env), BOOL, "if の条件")
                tt = self.infer(then, env)
                self.unify(tt, self.infer(else_, env), "if の両分岐")
                return tt
            case Let(name, value, body):
                # 単相の let（let 多相は扱わない）
                return self.infer(body, {**env, name: self.infer(value, env)})
            case Lambda(param, param_type, body):
                # 注釈がなければ「まだ分からない型」を表す新しい型変数を置く
                pt = param_type if param_type is not None else self.fresh()
                return TFun(pt, self.infer(body, {**env, param: pt}))
            case App(func, arg):
                ft = self.infer(func, env)
                at = self.infer(arg, env)
                result = self.fresh()
                # 「func は at -> result 型の関数である」という等式を解く
                self.unify(ft, TFun(at, result), "関数適用")
                return result
            case Pair(first, second):
                return TPair(self.infer(first, env), self.infer(second, env))
            case Fst(pair) | Snd(pair):
                a, b = self.fresh(), self.fresh()
                self.unify(self.infer(pair, env), TPair(a, b), "fst" if isinstance(expr, Fst) else "snd")
                return a if isinstance(expr, Fst) else b
        raise TypeError(f"式ではありません: {expr!r}")


def infer(expr: Expr, env: Mapping[str, Type] | None = None) -> Type:
    inferencer = _Inferencer()
    t = inferencer.infer(expr, dict(env or {}))
    return normalize_type_vars(inferencer.resolve(t))
