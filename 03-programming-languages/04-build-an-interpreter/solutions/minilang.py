"""3.4 言語処理系を作る — MiniLang インタプリタ（解答例）

演習の仕様は exercises/minilang.py の docstring を参照してください。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from typing import Callable, Union

# ===========================================================================
# 共通の定義（与えられたもの）
# ===========================================================================


class MiniLangError(Exception):
    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(f"{line}行目: {message}" if line else message)
        self.message = message
        self.line = line


class LexError(MiniLangError):
    pass


class ParseError(MiniLangError):
    pass


class MiniRuntimeError(MiniLangError):
    pass


@dataclass(frozen=True)
class Token:
    type: str
    lexeme: str
    value: object
    line: int
    col: int


KEYWORDS = frozenset(
    {"let", "fn", "if", "else", "while", "return", "print", "true", "false", "nil", "and", "or", "not"}
)
TWO_CHAR_OPS = frozenset({"==", "!=", "<=", ">="})
ONE_CHAR_OPS = frozenset("+-*/%<>=(){},;")
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _line(default: int = 0):
    return field(default=default, compare=False, repr=False)


# ---- 式 ----
@dataclass(frozen=True)
class Number:
    value: int
    line: int = _line()


@dataclass(frozen=True)
class String:
    value: str
    line: int = _line()


@dataclass(frozen=True)
class Boolean:
    value: bool
    line: int = _line()


@dataclass(frozen=True)
class Nil:
    line: int = _line()


@dataclass(frozen=True)
class Var:
    name: str
    line: int = _line()


@dataclass(frozen=True)
class Assign:
    name: str
    value: Expr
    line: int = _line()


@dataclass(frozen=True)
class Unary:
    op: str
    operand: Expr
    line: int = _line()


@dataclass(frozen=True)
class Binary:
    op: str
    left: Expr
    right: Expr
    line: int = _line()


@dataclass(frozen=True)
class Logical:
    op: str
    left: Expr
    right: Expr
    line: int = _line()


@dataclass(frozen=True)
class Call:
    callee: Expr
    args: tuple[Expr, ...]
    line: int = _line()


@dataclass(frozen=True)
class FunctionExpr:
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    line: int = _line()


# ---- 文 ----
@dataclass(frozen=True)
class ExprStmt:
    expr: Expr
    line: int = _line()


@dataclass(frozen=True)
class Print:
    expr: Expr
    line: int = _line()


@dataclass(frozen=True)
class Let:
    name: str
    value: Expr
    line: int = _line()


@dataclass(frozen=True)
class Block:
    stmts: tuple[Stmt, ...]
    line: int = _line()


@dataclass(frozen=True)
class If:
    cond: Expr
    then_branch: Block
    else_branch: Stmt | None = None
    line: int = _line()


@dataclass(frozen=True)
class While:
    cond: Expr
    body: Block
    line: int = _line()


@dataclass(frozen=True)
class Return:
    value: Expr | None = None
    line: int = _line()


@dataclass(frozen=True)
class FnDecl:
    name: str
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    line: int = _line()


Expr = Union[Number, String, Boolean, Nil, Var, Assign, Unary, Binary, Logical, Call, FunctionExpr]
Stmt = Union[ExprStmt, Print, Let, Block, If, While, Return, FnDecl]
LITERALS = (Number, String, Boolean, Nil)


# ===========================================================================
# 段階1: 字句解析
# ===========================================================================


def _is_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _is_ident_start(c: str) -> bool:
    return c.isascii() and (c.isalpha() or c == "_")


def _is_ident_char(c: str) -> bool:
    return _is_ident_start(c) or _is_digit(c)


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    i, line, col = 0, 1, 1
    n = len(source)

    def add(type_: str, lexeme: str, value: object, start_col: int) -> None:
        tokens.append(Token(type_, lexeme, value, line, start_col))

    while i < n:
        c = source[i]
        if c == "\n":
            i, line, col = i + 1, line + 1, 1
        elif c in " \t\r":
            i, col = i + 1, col + 1
        elif c == "/" and source.startswith("//", i):
            while i < n and source[i] != "\n":  # 行末までコメント（改行そのものは次の周回で処理）
                i, col = i + 1, col + 1
        elif _is_digit(c):
            start = i
            while i < n and _is_digit(source[i]):
                i += 1
            text = source[start:i]
            add("INT", text, int(text), col)
            col += i - start
        elif _is_ident_start(c):
            start = i
            while i < n and _is_ident_char(source[i]):
                i += 1
            text = source[start:i]
            # 最長一致: "letter" は let ＋ ter ではなく、1 つの識別子
            add(text if text in KEYWORDS else "IDENT", text, None, col)
            col += i - start
        elif c == '"':
            start, start_col = i, col
            i += 1
            chars: list[str] = []
            while True:
                if i >= n or source[i] == "\n":
                    raise LexError("文字列が閉じていません", line)
                ch = source[i]
                if ch == '"':
                    i += 1
                    break
                if ch == "\\":
                    if i + 1 >= n or source[i + 1] not in ESCAPES:
                        bad = source[i + 1] if i + 1 < n else ""
                        raise LexError(f"不明なエスケープシーケンスです: \\{bad}", line)
                    chars.append(ESCAPES[source[i + 1]])
                    i += 2
                else:
                    chars.append(ch)
                    i += 1
            lexeme = source[start:i]
            add("STRING", lexeme, "".join(chars), start_col)
            col = start_col + len(lexeme)
        elif source[i : i + 2] in TWO_CHAR_OPS:  # 2 文字の演算子を先に試す（最長一致）
            add(source[i : i + 2], source[i : i + 2], None, col)
            i, col = i + 2, col + 2
        elif c in ONE_CHAR_OPS:
            add(c, c, None, col)
            i, col = i + 1, col + 1
        elif c == "!":
            raise LexError("予期しない文字 '!' です（否定には not を使います）", line)
        else:
            raise LexError(f"予期しない文字です: {c!r}（{col}文字目）", line)
    tokens.append(Token("EOF", "", None, line, col))
    return tokens


# ===========================================================================
# 段階2・4・5: 構文解析（再帰下降）
# ===========================================================================


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.function_depth = 0

    # ---- 補助メソッド（与えられたもの）----
    def peek(self) -> Token:
        return self.tokens[self.pos]

    def peek_next(self) -> Token:
        return self.tokens[min(self.pos + 1, len(self.tokens) - 1)]

    def previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def at_end(self) -> bool:
        return self.peek().type == "EOF"

    def advance(self) -> Token:
        token = self.peek()
        if not self.at_end():
            self.pos += 1
        return token

    def check(self, *types: str) -> bool:
        return self.peek().type in types

    def match(self, *types: str) -> bool:
        if self.check(*types):
            self.advance()
            return True
        return False

    def expect(self, type_: str, message: str) -> Token:
        if self.check(type_):
            return self.advance()
        raise self.error(message)

    def error(self, message: str, token: Token | None = None) -> ParseError:
        token = token or self.peek()
        where = "ファイルの終わり" if token.type == "EOF" else f"'{token.lexeme}'"
        return ParseError(f"{message}（{where} の位置）", token.line)

    # ---- 段階2: 式 ----
    def parse_expression(self) -> Expr:
        return self.assignment()

    def assignment(self) -> Expr:
        expr = self.logic_or()
        if self.check("="):
            equals = self.advance()
            value = self.assignment()  # 右結合: a = b = 1 は a = (b = 1)
            if isinstance(expr, Var):
                return Assign(expr.name, value, line=expr.line)
            raise self.error("代入の左辺には変数名が必要です", equals)
        return expr

    def _binary_level(self, next_level: Callable[[], Expr], ops: tuple[str, ...], node=Binary) -> Expr:
        # term = factor { ("+" | "-") factor } のような規則を、ループで左結合に組み立てる
        expr = next_level()
        while self.check(*ops):
            op = self.advance()
            right = next_level()
            expr = node(op.type, expr, right, line=op.line)
        return expr

    def logic_or(self) -> Expr:
        return self._binary_level(self.logic_and, ("or",), Logical)

    def logic_and(self) -> Expr:
        return self._binary_level(self.equality, ("and",), Logical)

    def equality(self) -> Expr:
        return self._binary_level(self.comparison, ("==", "!="))

    def comparison(self) -> Expr:
        return self._binary_level(self.term, ("<", "<=", ">", ">="))

    def term(self) -> Expr:
        return self._binary_level(self.factor, ("+", "-"))

    def factor(self) -> Expr:
        return self._binary_level(self.unary, ("*", "/", "%"))

    def unary(self) -> Expr:
        if self.check("-", "not"):
            op = self.advance()
            return Unary(op.type, self.unary(), line=op.line)  # 右再帰なので -(-x) も書ける
        return self.call()

    def call(self) -> Expr:
        expr = self.primary()
        while self.check("("):  # f(1)(2) のように呼び出しは連続できる
            paren = self.advance()
            expr = self.finish_call(expr, paren)
        return expr

    def primary(self) -> Expr:
        token = self.peek()
        if self.match("INT"):
            return Number(token.value, line=token.line)
        if self.match("STRING"):
            return String(token.value, line=token.line)
        if self.match("true"):
            return Boolean(True, line=token.line)
        if self.match("false"):
            return Boolean(False, line=token.line)
        if self.match("nil"):
            return Nil(line=token.line)
        if self.match("IDENT"):
            return Var(token.lexeme, line=token.line)
        if self.match("("):
            expr = self.parse_expression()
            self.expect(")", "')' が必要です")
            return expr
        if self.match("fn"):
            params, body = self.function_rest()
            return FunctionExpr(params, body, line=token.line)
        raise self.error("式が必要です")

    # ---- 段階4: 文 ----
    def parse_program(self) -> list[Stmt]:
        stmts: list[Stmt] = []
        while not self.at_end():
            stmts.append(self.declaration())
        return stmts

    def declaration(self) -> Stmt:
        if self.check("let"):
            return self.let_declaration()
        if self.check("fn") and self.peek_next().type == "IDENT":
            return self.fn_declaration()
        return self.statement()

    def let_declaration(self) -> Stmt:
        let = self.expect("let", "'let' が必要です")
        name = self.expect("IDENT", "変数名が必要です")
        self.expect("=", "'=' が必要です")
        value = self.parse_expression()
        self.expect(";", "';' が必要です")
        return Let(name.lexeme, value, line=let.line)

    def statement(self) -> Stmt:
        if self.check("print"):
            return self.print_statement()
        if self.check("if"):
            return self.if_statement()
        if self.check("while"):
            return self.while_statement()
        if self.check("return"):
            return self.return_statement()
        if self.check("{"):
            return self.block()
        return self.expression_statement()

    def print_statement(self) -> Stmt:
        keyword = self.expect("print", "'print' が必要です")
        self.expect("(", "print の後に '(' が必要です")
        value = self.parse_expression()
        self.expect(")", "')' が必要です")
        self.expect(";", "';' が必要です")
        return Print(value, line=keyword.line)

    def if_statement(self) -> Stmt:
        keyword = self.expect("if", "'if' が必要です")
        self.expect("(", "if の後に '(' が必要です")
        cond = self.parse_expression()
        self.expect(")", "条件の後に ')' が必要です")
        then_branch = self.block()
        else_branch: Stmt | None = None
        if self.match("else"):
            # else if は「else の後に if 文が 1 つ続く」と解釈する
            else_branch = self.if_statement() if self.check("if") else self.block()
        return If(cond, then_branch, else_branch, line=keyword.line)

    def while_statement(self) -> Stmt:
        keyword = self.expect("while", "'while' が必要です")
        self.expect("(", "while の後に '(' が必要です")
        cond = self.parse_expression()
        self.expect(")", "条件の後に ')' が必要です")
        return While(cond, self.block(), line=keyword.line)

    def block(self) -> Block:
        brace = self.expect("{", "'{' が必要です")
        stmts: list[Stmt] = []
        while not self.check("}") and not self.at_end():
            stmts.append(self.declaration())
        self.expect("}", "'}' が必要です")
        return Block(tuple(stmts), line=brace.line)

    def expression_statement(self) -> Stmt:
        expr = self.parse_expression()
        self.expect(";", "';' が必要です")
        return ExprStmt(expr, line=expr.line)

    # ---- 段階5: 関数 ----
    def fn_declaration(self) -> Stmt:
        keyword = self.expect("fn", "'fn' が必要です")
        name = self.expect("IDENT", "関数名が必要です")
        params, body = self.function_rest()
        return FnDecl(name.lexeme, params, body, line=keyword.line)

    def function_rest(self) -> tuple[tuple[str, ...], tuple[Stmt, ...]]:
        self.expect("(", "'(' が必要です")
        params: list[str] = []
        if not self.check(")"):
            while True:
                name = self.expect("IDENT", "引数名が必要です")
                if name.lexeme in params:
                    raise self.error(f"引数名が重複しています: {name.lexeme}", name)
                params.append(name.lexeme)
                if not self.match(","):
                    break
        self.expect(")", "')' が必要です")
        self.function_depth += 1
        try:
            body = self.block()
        finally:
            self.function_depth -= 1
        return tuple(params), body.stmts

    def return_statement(self) -> Stmt:
        keyword = self.expect("return", "'return' が必要です")
        if self.function_depth == 0:
            raise self.error("関数の外で return は使えません", keyword)
        value = None if self.check(";") else self.parse_expression()
        self.expect(";", "';' が必要です")
        return Return(value, line=keyword.line)

    def finish_call(self, callee: Expr, paren: Token) -> Expr:
        args: list[Expr] = []
        if not self.check(")"):
            while True:
                args.append(self.parse_expression())
                if not self.match(","):
                    break
        self.expect(")", "引数の後に ')' が必要です")
        return Call(callee, tuple(args), line=paren.line)


def parse(source: str) -> list[Stmt]:
    return Parser(tokenize(source)).parse_program()


def parse_expr(source: str) -> Expr:
    parser = Parser(tokenize(source))
    expr = parser.parse_expression()
    if not parser.at_end():
        raise parser.error("式の後に余分なトークンがあります")
    return expr


# ===========================================================================
# 段階3〜5: 評価器（木をたどるインタプリタ）
# ===========================================================================


class Environment:
    def __init__(self, parent: Environment | None = None) -> None:
        self.values: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value: object) -> None:
        self.values[name] = value

    def get(self, name: str, line: int = 0) -> object:
        env: Environment | None = self
        while env is not None:  # 内側のスコープから外側へたどる（レキシカルスコープ）
            if name in env.values:
                return env.values[name]
            env = env.parent
        raise MiniRuntimeError(f"未定義の変数です: {name}", line)

    def assign(self, name: str, value: object, line: int = 0) -> None:
        env: Environment | None = self
        while env is not None:
            if name in env.values:
                env.values[name] = value  # 見つかったスコープの変数を書き換える
                return
            env = env.parent
        raise MiniRuntimeError(f"未定義の変数には代入できません: {name}", line)


@dataclass(eq=False)
class Function:
    name: str | None
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    closure: Environment


@dataclass(eq=False)
class Builtin:
    name: str
    arity: int
    fn: Callable[[list[object], int], object]


class ReturnSignal(Exception):
    def __init__(self, value: object) -> None:
        super().__init__("return")
        self.value = value


def stringify(value: object) -> str:
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, Function):
        return f"<fn {value.name}>" if value.name else "<fn>"
    if isinstance(value, Builtin):
        return f"<builtin {value.name}>"
    return str(value)


def _builtin_len(args: list[object], line: int) -> object:
    (s,) = args
    if not isinstance(s, str):
        raise MiniRuntimeError(f"len の引数は文字列でなければなりません: {stringify(s)}", line)
    return len(s)


BUILTINS = (
    Builtin("str", 1, lambda args, line: stringify(args[0])),
    Builtin("len", 1, _builtin_len),
)


def _type_name(value: object) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):  # bool は int のサブクラスなので先に判定する
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    return "function"


def is_truthy(value: object) -> bool:
    return value is not None and value is not False


def values_equal(a: object, b: object) -> bool:
    # Python では True == 1 だが、MiniLang では型が違えば等しくない
    if _type_name(a) != _type_name(b):
        return False
    if isinstance(a, (Function, Builtin)):
        return a is b
    return a == b


def _is_int(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def apply_unary(op: str, value: object, line: int = 0) -> object:
    if op == "-":
        if not _is_int(value):
            raise MiniRuntimeError(f"単項 - は整数にしか使えません: {_type_name(value)}", line)
        return -value
    if op == "not":
        return not is_truthy(value)
    raise MiniRuntimeError(f"未知の単項演算子です: {op}", line)


def apply_binary(op: str, left: object, right: object, line: int = 0) -> object:
    if op in ("==", "!="):
        eq = values_equal(left, right)
        return eq if op == "==" else not eq
    if op == "+" and isinstance(left, str) and isinstance(right, str):
        return left + right
    if op in ("<", "<=", ">", ">=") and isinstance(left, str) and isinstance(right, str):
        pass  # 文字列どうしの比較は辞書順
    elif not (_is_int(left) and _is_int(right)):
        raise MiniRuntimeError(
            f"{op} の両辺の型が不正です: {_type_name(left)} と {_type_name(right)}", line
        )
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op in ("/", "%"):
        if right == 0:
            raise MiniRuntimeError("0 で割ることはできません", line)
        # C や Java と同じく 0 に向かって切り捨てる（Python の // は負の無限大に向かう）
        q = abs(left) // abs(right)
        if (left < 0) != (right < 0):
            q = -q
        return q if op == "/" else left - q * right
    if op == "<":
        return left < right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    raise MiniRuntimeError(f"未知の演算子です: {op}", line)


class Interpreter:
    def __init__(self, max_steps: int = 1_000_000, max_depth: int = 200) -> None:
        self.globals = Environment()
        self.output: list[str] = []
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.steps = 0
        self.depth = 0
        for builtin in BUILTINS:
            self.globals.define(builtin.name, builtin)

    # ---- 与えられたもの ----
    def interpret(self, program: list[Stmt]) -> None:
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, 4000))
        try:
            for stmt in program:
                self.execute(stmt, self.globals)
        except RecursionError:
            raise MiniRuntimeError("再帰が深すぎます（ホストの Python のスタックが尽きました）") from None
        finally:
            sys.setrecursionlimit(old_limit)

    def tick(self, line: int) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise MiniRuntimeError(f"実行ステップ数の上限（{self.max_steps}）を超えました", line)

    # ---- 段階4・5: 文の実行 ----
    def execute(self, stmt: Stmt, env: Environment) -> None:
        match stmt:
            case ExprStmt(expr):
                self.evaluate(expr, env)
            case Print(expr):
                self.output.append(stringify(self.evaluate(expr, env)))
            case Let(name, value):
                env.define(name, self.evaluate(value, env))
            case Block(stmts):
                self.execute_block(stmts, Environment(env))  # ブロックごとに新しいスコープ
            case If(cond, then_branch, else_branch):
                if is_truthy(self.evaluate(cond, env)):
                    self.execute(then_branch, env)
                elif else_branch is not None:
                    self.execute(else_branch, env)
            case While(cond, body):
                while is_truthy(self.evaluate(cond, env)):
                    self.tick(stmt.line)
                    self.execute(body, env)
            case Return(value):
                raise ReturnSignal(None if value is None else self.evaluate(value, env))
            case FnDecl(name, params, body):
                # 関数は「定義された環境」を閉じ込める（クロージャ）。名前を先に定義しておくので再帰できる
                env.define(name, Function(name, params, body, env))
            case _:
                raise TypeError(f"文ではありません: {stmt!r}")

    def execute_block(self, stmts: tuple[Stmt, ...], env: Environment) -> None:
        for s in stmts:
            self.execute(s, env)

    # ---- 段階3〜5: 式の評価 ----
    def evaluate(self, expr: Expr, env: Environment) -> object:
        match expr:
            case Number(value) | String(value) | Boolean(value):
                return value
            case Nil():
                return None
            case Var(name):
                return env.get(name, expr.line)
            case Assign(name, value):
                v = self.evaluate(value, env)
                env.assign(name, v, expr.line)
                return v
            case Unary(op, operand):
                return apply_unary(op, self.evaluate(operand, env), expr.line)
            case Binary(op, left, right):
                return apply_binary(op, self.evaluate(left, env), self.evaluate(right, env), expr.line)
            case Logical(op, left, right):
                lv = self.evaluate(left, env)
                # 短絡評価: 結果が左辺で決まるなら右辺は評価しない
                if op == "or":
                    return lv if is_truthy(lv) else self.evaluate(right, env)
                return self.evaluate(right, env) if is_truthy(lv) else lv
            case Call(callee, args):
                fn = self.evaluate(callee, env)
                arg_values = [self.evaluate(a, env) for a in args]
                return self.call_function(fn, arg_values, expr.line)
            case FunctionExpr(params, body):
                return Function(None, params, body, env)
            case _:
                raise TypeError(f"式ではありません: {expr!r}")

    def call_function(self, fn: object, args: list[object], line: int) -> object:
        if isinstance(fn, Builtin):
            if len(args) != fn.arity:
                raise MiniRuntimeError(
                    f"{fn.name} の引数は {fn.arity} 個ですが、{len(args)} 個渡されました", line
                )
            return fn.fn(args, line)
        if not isinstance(fn, Function):
            raise MiniRuntimeError(f"関数ではない値（{_type_name(fn)}）は呼び出せません", line)
        if len(args) != len(fn.params):
            name = fn.name or "無名関数"
            raise MiniRuntimeError(
                f"{name} の引数は {len(fn.params)} 個ですが、{len(args)} 個渡されました", line
            )
        self.tick(line)
        if self.depth >= self.max_depth:
            raise MiniRuntimeError(f"呼び出しの深さが上限（{self.max_depth}）を超えました", line)
        # 新しい環境の親は「呼び出し元」ではなく「定義された場所」（レキシカルスコープ）
        call_env = Environment(fn.closure)
        for param, arg in zip(fn.params, args):
            call_env.define(param, arg)
        self.depth += 1
        try:
            self.execute_block(fn.body, call_env)
        except ReturnSignal as ret:
            return ret.value
        finally:
            self.depth -= 1
        return None


# ===========================================================================
# 段階6: 定数畳み込み
# ===========================================================================


def _literal_value(node: Expr) -> object:
    return None if isinstance(node, Nil) else node.value


def _to_literal(value: object, line: int) -> Expr | None:
    if value is None:
        return Nil(line=line)
    if isinstance(value, bool):
        return Boolean(value, line=line)
    if isinstance(value, int):
        return Number(value, line=line)
    if isinstance(value, str):
        return String(value, line=line)
    return None


def _fold_expr(expr: Expr) -> Expr:
    match expr:
        case Unary(op, operand):
            operand = _fold_expr(operand)
            if isinstance(operand, LITERALS):
                try:
                    # 実行時と同じ関数で計算するので、畳み込んでも意味が変わらない
                    folded = _to_literal(apply_unary(op, _literal_value(operand), expr.line), expr.line)
                except MiniRuntimeError:
                    folded = None  # エラーは実行時に、正しい行番号で起こさせる
                if folded is not None:
                    return folded
            return replace(expr, operand=operand)
        case Binary(op, left, right):
            left, right = _fold_expr(left), _fold_expr(right)
            if isinstance(left, LITERALS) and isinstance(right, LITERALS):
                try:
                    value = apply_binary(op, _literal_value(left), _literal_value(right), expr.line)
                    folded = _to_literal(value, expr.line)
                except MiniRuntimeError:
                    folded = None
                if folded is not None:
                    return folded
            return replace(expr, left=left, right=right)
        case Logical(op, left, right):
            left = _fold_expr(left)
            if isinstance(left, LITERALS):
                truthy = is_truthy(_literal_value(left))
                if (op == "or") == truthy:
                    return left  # or で左が真、and で左が偽なら、結果は左辺そのもの
                return _fold_expr(right)
            return replace(expr, left=left, right=_fold_expr(right))
        case Assign(name, value):
            return replace(expr, value=_fold_expr(value))
        case Call(callee, args):
            return replace(expr, callee=_fold_expr(callee), args=tuple(_fold_expr(a) for a in args))
        case FunctionExpr(params, body):
            return replace(expr, body=tuple(_fold_stmt(s) for s in body))
        case _:
            return expr  # リテラルと変数はそのまま


def _fold_stmt(stmt: Stmt) -> Stmt:
    match stmt:
        case ExprStmt(expr):
            return replace(stmt, expr=_fold_expr(expr))
        case Print(expr):
            return replace(stmt, expr=_fold_expr(expr))
        case Let(name, value):
            return replace(stmt, value=_fold_expr(value))
        case Block(stmts):
            return replace(stmt, stmts=tuple(_fold_stmt(s) for s in stmts))
        case If(cond, then_branch, else_branch):
            cond = _fold_expr(cond)
            then_b = _fold_stmt(then_branch)
            else_b = None if else_branch is None else _fold_stmt(else_branch)
            if isinstance(cond, LITERALS):
                # 条件が定数なら、実行されない側の分岐を取り除く（死んだコードの除去）
                if is_truthy(_literal_value(cond)):
                    return then_b
                return else_b if else_b is not None else Block((), line=stmt.line)
            return replace(stmt, cond=cond, then_branch=then_b, else_branch=else_b)
        case While(cond, body):
            return replace(stmt, cond=_fold_expr(cond), body=_fold_stmt(body))
        case Return(value):
            return replace(stmt, value=None if value is None else _fold_expr(value))
        case FnDecl(name, params, body):
            return replace(stmt, body=tuple(_fold_stmt(s) for s in body))
    raise TypeError(f"文ではありません: {stmt!r}")


def fold_constants(node):
    if isinstance(node, list):
        return [_fold_stmt(s) for s in node]
    if isinstance(node, (ExprStmt, Print, Let, Block, If, While, Return, FnDecl)):
        return _fold_stmt(node)
    return _fold_expr(node)


# ===========================================================================
# まとめて実行する（与えられたもの）
# ===========================================================================


def run(source: str, *, optimize: bool = False, max_steps: int = 1_000_000, max_depth: int = 200) -> list[str]:
    program = parse(source)
    if optimize:
        program = fold_constants(program)
    interpreter = Interpreter(max_steps=max_steps, max_depth=max_depth)
    interpreter.interpret(program)
    return interpreter.output
