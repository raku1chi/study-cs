"""3.4 言語処理系を作る — 演習: MiniLang インタプリタ

小さなプログラミング言語 MiniLang のインタプリタを、6 つの段階に分けて作ります。

    let x = 10;
    fn fact(n) { if (n <= 1) { return 1; } return n * fact(n - 1); }
    print(fact(x));                                   // 3628800
    let make_counter = fn() { let c = 0; return fn() { c = c + 1; return c; }; };

    段階1（★★☆）: tokenize                         — 字句解析（文字列 → トークン列）
    段階2（★★☆）: Parser の式のメソッド             — 構文解析（トークン列 → 式の構文木）
    段階3（★★☆）: is_truthy / values_equal / apply_unary / apply_binary / Interpreter.evaluate
                                                   — 式の評価
    段階4（★★★）: Parser の文のメソッド / Environment / Interpreter.execute
                                                   — 文・変数・スコープ・制御構造
    段階5（★★★）: 関数の構文解析 / Interpreter.call_function
                                                   — 関数・クロージャ・再帰
    段階6（★★☆）: fold_constants                   — 定数畳み込み（最適化）

構文木のデータクラス、エラーのクラス、Parser の補助メソッド、run() などは与えられています。
「段階N:」と書かれたメソッド・関数の raise NotImplementedError(...) を実装に置き換えてください。
README の「演習の進め方」に、段階ごとの手順と解説があります。

テストの実行（リポジトリのルートで）:
    python3 tools/check.py 3.4

このディレクトリで段階ごとに実行する:
    python3 -m unittest -v test_minilang.TestStage1Tokenizer
    python3 -m unittest -v test_minilang.TestStage2ExpressionParser
    python3 -m unittest -v test_minilang.TestStage3ExpressionEvaluator   （構文木を直接渡すので段階1・2に依存しない）
    python3 -m unittest -v test_minilang.TestStage4Statements
    python3 -m unittest -v test_minilang.TestStage5Functions
    python3 -m unittest -v test_minilang.TestStage6ConstantFolding

制約: Python の eval / exec / ast / tokenize / re モジュールは使わないでください。
字句解析は 1 文字ずつ読む手書きの状態機械として書くことが目的です。

MiniLang の文法（EBNF。{ } は 0 回以上の繰り返し、[ ] は省略可能）:

    program        = { declaration } EOF ;
    declaration    = let_decl | fn_decl | statement ;
    let_decl       = "let" IDENT "=" expression ";" ;
    fn_decl        = "fn" IDENT "(" [ parameters ] ")" block ;
    parameters     = IDENT { "," IDENT } ;
    statement      = print_stmt | if_stmt | while_stmt | return_stmt | block | expr_stmt ;
    print_stmt     = "print" "(" expression ")" ";" ;
    if_stmt        = "if" "(" expression ")" block [ "else" ( if_stmt | block ) ] ;
    while_stmt     = "while" "(" expression ")" block ;
    return_stmt    = "return" [ expression ] ";" ;
    block          = "{" { declaration } "}" ;
    expr_stmt      = expression ";" ;

    expression     = assignment ;
    assignment     = IDENT "=" assignment | logic_or ;
    logic_or       = logic_and { "or" logic_and } ;
    logic_and      = equality { "and" equality } ;
    equality       = comparison { ( "==" | "!=" ) comparison } ;
    comparison     = term { ( "<" | "<=" | ">" | ">=" ) term } ;
    term           = factor { ( "+" | "-" ) factor } ;
    factor         = unary { ( "*" | "/" | "%" ) unary } ;
    unary          = ( "-" | "not" ) unary | call ;
    call           = primary { "(" [ arguments ] ")" } ;
    arguments      = expression { "," expression } ;
    primary        = INT | STRING | "true" | "false" | "nil" | IDENT
                   | "(" expression ")" | fn_expr ;
    fn_expr        = "fn" "(" [ parameters ] ")" block ;

意味の規則（Python と違うところに注意）:
    - 値は 整数・文字列・真偽値（true / false）・nil・関数 の 5 種類。
    - 偽とみなすのは false と nil だけ。0 や "" は真（Ruby や Lua と同じ）。
    - 暗黙の型変換はしない。"a" + 1 や true + 1 は実行時エラー。
    - 整数の / と % は、C や Java と同じく 0 に向かって切り捨てる（-7 / 2 は -3、-7 % 2 は -1）。
    - == は型が違えば false（true == 1 は false）。
    - and / or は短絡評価し、真偽値ではなく被演算子の値を返す（nil or 5 は 5）。
    - print は標準出力ではなく、Interpreter.output（文字列のリスト）に追加する。
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace  # noqa: F401  replace は段階6で使えます
from typing import Callable, Union

# ===========================================================================
# 共通の定義（与えられたもの）
# ===========================================================================


class MiniLangError(Exception):
    """MiniLang のエラーの基底クラス。line は 1 始まりの行番号（不明なら 0）。

    str(e) は「3行目: 0 で割ることはできません」のように行番号を先頭に付ける。
    """

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(f"{line}行目: {message}" if line else message)
        self.message = message
        self.line = line


class LexError(MiniLangError):
    """字句解析のエラー（段階1）"""


class ParseError(MiniLangError):
    """構文解析のエラー（段階2・4・5）"""


class MiniRuntimeError(MiniLangError):
    """実行時のエラー（段階3〜5）"""


@dataclass(frozen=True)
class Token:
    """トークン。

    type:   種類。"INT"・"STRING"・"IDENT"・"EOF"、キーワードはその綴り（"let" など）、
            演算子・記号はその文字列（"+"、"<="、"(" など）。
    lexeme: ソースコード上の文字列そのもの（STRING なら引用符やエスケープも含む）。
    value:  INT なら int、STRING ならエスケープを解釈した後の str、それ以外は None。
    line, col: トークンの先頭文字の位置（どちらも 1 始まり）。
    """

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
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}  # \n \t \" \\ の 4 種類


def _line(default: int = 0):
    """行番号のフィールド。== の比較と repr には含めない（テストで構文木の形だけを比べるため）。"""
    return field(default=default, compare=False, repr=False)


# ---- 式の構文木 ----
@dataclass(frozen=True)
class Number:
    """整数リテラル 42"""

    value: int
    line: int = _line()


@dataclass(frozen=True)
class String:
    """文字列リテラル "abc"（value はエスケープを解釈した後の文字列）"""

    value: str
    line: int = _line()


@dataclass(frozen=True)
class Boolean:
    """true / false"""

    value: bool
    line: int = _line()


@dataclass(frozen=True)
class Nil:
    """nil"""

    line: int = _line()


@dataclass(frozen=True)
class Var:
    """変数の参照 x"""

    name: str
    line: int = _line()


@dataclass(frozen=True)
class Assign:
    """代入 x = value（式なので値を持つ。line は変数名の行）"""

    name: str
    value: Expr
    line: int = _line()


@dataclass(frozen=True)
class Unary:
    """単項演算 -x, not x（op は "-" か "not"。line は演算子の行）"""

    op: str
    operand: Expr
    line: int = _line()


@dataclass(frozen=True)
class Binary:
    """二項演算 left op right（op は "+" "-" "*" "/" "%" "==" "!=" "<" "<=" ">" ">="。line は演算子の行）"""

    op: str
    left: Expr
    right: Expr
    line: int = _line()


@dataclass(frozen=True)
class Logical:
    """論理演算 left and right / left or right（短絡評価するので Binary と分ける。line は演算子の行）"""

    op: str
    left: Expr
    right: Expr
    line: int = _line()


@dataclass(frozen=True)
class Call:
    """関数呼び出し callee(args...)（line は "(" の行）"""

    callee: Expr
    args: tuple[Expr, ...]
    line: int = _line()


@dataclass(frozen=True)
class FunctionExpr:
    """無名関数 fn(params...) { body }（line は fn の行）"""

    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    line: int = _line()


# ---- 文の構文木 ----
@dataclass(frozen=True)
class ExprStmt:
    """式文 expr;"""

    expr: Expr
    line: int = _line()


@dataclass(frozen=True)
class Print:
    """print(expr);"""

    expr: Expr
    line: int = _line()


@dataclass(frozen=True)
class Let:
    """let name = value;"""

    name: str
    value: Expr
    line: int = _line()


@dataclass(frozen=True)
class Block:
    """{ stmts... }（新しいスコープを作る）"""

    stmts: tuple[Stmt, ...]
    line: int = _line()


@dataclass(frozen=True)
class If:
    """if (cond) then_branch else else_branch（else_branch は Block か If か None）"""

    cond: Expr
    then_branch: Block
    else_branch: Stmt | None = None
    line: int = _line()


@dataclass(frozen=True)
class While:
    """while (cond) body"""

    cond: Expr
    body: Block
    line: int = _line()


@dataclass(frozen=True)
class Return:
    """return value;（value は省略可能で、その場合は None）"""

    value: Expr | None = None
    line: int = _line()


@dataclass(frozen=True)
class FnDecl:
    """fn name(params...) { body }"""

    name: str
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    line: int = _line()


Expr = Union[Number, String, Boolean, Nil, Var, Assign, Unary, Binary, Logical, Call, FunctionExpr]
Stmt = Union[ExprStmt, Print, Let, Block, If, While, Return, FnDecl]
LITERALS = (Number, String, Boolean, Nil)


# ===========================================================================
# 段階1（★★☆）: 字句解析
# ===========================================================================


def tokenize(source: str) -> list[Token]:
    """ソースコードをトークンのリストに変換する。最後に必ず EOF トークンを 1 つ付ける。

    規則:
    - 空白（" ", "\\t", "\\r"）と改行は読み飛ばす。改行で line を 1 増やし、col を 1 に戻す。
    - "//" から行末まではコメントとして読み飛ばす。
    - 整数: ASCII の数字の並び（"007" は 7）。value は int。
    - 識別子: ASCII の英字か "_" で始まり、英数字と "_" が続く。KEYWORDS に含まれるなら
      type はその綴り（"let" など）、それ以外は "IDENT"。最長一致で読むこと（"letter" は IDENT）。
    - 文字列: '"' から '"' まで。エスケープは ESCAPES の 4 種類（\\n \\t \\" \\\\）。
      途中で行末やファイルの終わりに達したら LexError（line は文字列が始まった行）。
      それ以外のエスケープ（\\q など）も LexError。
    - 演算子・記号: TWO_CHAR_OPS を ONE_CHAR_OPS より先に試す（"<=" を "<" と "=" にしない）。
    - "!" 単独（"!=" 以外）や、それ以外の知らない文字は LexError（line はその文字の行）。
    - EOF トークンの位置は、最後に読んだ位置（ファイルの終わり）。

    >>> [(t.type, t.value) for t in tokenize("let x = 10;")]
    [('let', None), ('IDENT', None), ('=', None), ('INT', 10), (';', None), ('EOF', None)]
    >>> t = tokenize('print("hi\\\\n");')[2]
    >>> (t.type, t.value, t.line, t.col)
    ('STRING', 'hi\\n', 1, 7)

    ヒント: 位置 i の 1 文字を見て「数字なら数字が続く限り読む」「英字なら…」と分岐する。
    読みながら行番号と桁番号を更新するのを忘れずに。
    """
    raise NotImplementedError("段階1: tokenize を実装してください")


# ===========================================================================
# 段階2・4・5: 構文解析（再帰下降）
# ===========================================================================


class Parser:
    """再帰下降構文解析器。文法の規則 1 つにメソッド 1 つが対応する。

    各メソッドは「今の位置から、その規則に当てはまる部分を読み、構文木を返す」。
    読み進めるには advance()、次のトークンを確かめるには check() / match() を使う。
    構文木のノードには、docstring に書いたトークンの行番号を line=... で入れること。
    """

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.function_depth = 0  # 今いくつの関数本体の中にいるか（段階5の return の検査に使う）

    # ---- 補助メソッド（与えられたもの）----
    def peek(self) -> Token:
        """次に読むトークン（まだ読み進めない）。"""
        return self.tokens[self.pos]

    def peek_next(self) -> Token:
        """次の次のトークン。"""
        return self.tokens[min(self.pos + 1, len(self.tokens) - 1)]

    def previous(self) -> Token:
        """最後に読んだトークン。"""
        return self.tokens[self.pos - 1]

    def at_end(self) -> bool:
        return self.peek().type == "EOF"

    def advance(self) -> Token:
        """次のトークンを読んで返す（EOF では進まない）。"""
        token = self.peek()
        if not self.at_end():
            self.pos += 1
        return token

    def check(self, *types: str) -> bool:
        """次のトークンの種類が types のどれかなら True（読み進めない）。"""
        return self.peek().type in types

    def match(self, *types: str) -> bool:
        """次のトークンの種類が types のどれかなら読み進めて True。"""
        if self.check(*types):
            self.advance()
            return True
        return False

    def expect(self, type_: str, message: str) -> Token:
        """次のトークンが type_ なら読んで返す。違えば ParseError を送出する。"""
        if self.check(type_):
            return self.advance()
        raise self.error(message)

    def error(self, message: str, token: Token | None = None) -> ParseError:
        """token（省略時は次のトークン）の位置の ParseError を作って返す（raise self.error(...) と使う）。"""
        token = token or self.peek()
        where = "ファイルの終わり" if token.type == "EOF" else f"'{token.lexeme}'"
        return ParseError(f"{message}（{where} の位置）", token.line)

    # ---- 段階2（★★☆）: 式 ----
    def parse_expression(self) -> Expr:
        """段階2: expression = assignment ;"""
        raise NotImplementedError("段階2: Parser.parse_expression を実装してください")

    def assignment(self) -> Expr:
        """段階2: assignment = IDENT "=" assignment | logic_or ;

        1 トークン先読みでは「x = ...」と「x + ...」を区別できないので、
        まず logic_or() で左辺を読み、次が "=" なら代入とみなす。
        - 左辺が Var なら Assign(name, 右辺, line=左辺の行)。右辺は assignment() を再帰で読む（右結合）。
        - 左辺が Var でなければ ParseError（例: 1 = 2、a + b = c）。
        """
        raise NotImplementedError("段階2: Parser.assignment を実装してください")

    def logic_or(self) -> Expr:
        """段階2: logic_or = logic_and { "or" logic_and } ;  → Logical("or", ...)（左結合）"""
        raise NotImplementedError("段階2: Parser.logic_or を実装してください")

    def logic_and(self) -> Expr:
        """段階2: logic_and = equality { "and" equality } ;  → Logical("and", ...)（左結合）"""
        raise NotImplementedError("段階2: Parser.logic_and を実装してください")

    def equality(self) -> Expr:
        """段階2: equality = comparison { ( "==" | "!=" ) comparison } ;  → Binary（左結合）"""
        raise NotImplementedError("段階2: Parser.equality を実装してください")

    def comparison(self) -> Expr:
        """段階2: comparison = term { ( "<" | "<=" | ">" | ">=" ) term } ;  → Binary（左結合）"""
        raise NotImplementedError("段階2: Parser.comparison を実装してください")

    def term(self) -> Expr:
        """段階2: term = factor { ( "+" | "-" ) factor } ;  → Binary（左結合）

        左結合にするには、ループで「これまでの結果」を左の子にして木を積み上げる:
            expr = self.factor()
            while 次が + か -:
                op = self.advance()
                expr = Binary(op.type, expr, self.factor(), line=op.line)
        上の 5 つのメソッドも同じ形なので、共通の補助メソッドにまとめるとよい。
        """
        raise NotImplementedError("段階2: Parser.term を実装してください")

    def factor(self) -> Expr:
        """段階2: factor = unary { ( "*" | "/" | "%" ) unary } ;  → Binary（左結合）"""
        raise NotImplementedError("段階2: Parser.factor を実装してください")

    def unary(self) -> Expr:
        """段階2: unary = ( "-" | "not" ) unary | call ;  → Unary(op, operand, line=演算子の行)"""
        raise NotImplementedError("段階2: Parser.unary を実装してください")

    def call(self) -> Expr:
        """段階2・5: call = primary { "(" [ arguments ] ")" } ;

        段階2では return self.primary() だけでよい。
        段階5で、primary の後に "(" が続く限り、finish_call で Call を積み上げる（f(1)(2) も可）。
        """
        raise NotImplementedError("段階2: Parser.call を実装してください")

    def primary(self) -> Expr:
        """段階2・5: 最も基本的な式。

        - INT → Number、STRING → String、true / false → Boolean、nil → Nil、IDENT → Var
        - "(" expression ")" → 中の式をそのまま返す（括弧のノードは作らない）。")" がなければ ParseError
        - 段階5: "fn" → 無名関数 FunctionExpr(params, body, line=fn の行)（function_rest を使う）
        - それ以外は ParseError（「式が必要です」）
        """
        raise NotImplementedError("段階2: Parser.primary を実装してください")

    # ---- 段階4（★★★）: 文 ----
    def parse_program(self) -> list[Stmt]:
        """段階4: program = { declaration } EOF ;  → 文のリスト"""
        raise NotImplementedError("段階4: Parser.parse_program を実装してください")

    def declaration(self) -> Stmt:
        """段階4・5: declaration = let_decl | fn_decl | statement ;

        次が "let" なら let_declaration。
        段階5: 次が "fn" で、その次が IDENT なら fn_declaration（"fn (" なら無名関数の式文なので statement へ）。
        それ以外は statement。
        """
        raise NotImplementedError("段階4: Parser.declaration を実装してください")

    def let_declaration(self) -> Stmt:
        """段階4: let_decl = "let" IDENT "=" expression ";" ;  → Let(name, value, line=let の行)"""
        raise NotImplementedError("段階4: Parser.let_declaration を実装してください")

    def statement(self) -> Stmt:
        """段階4・5: 次のトークンで print / if / while / return（段階5）/ block / 式文 に振り分ける。"""
        raise NotImplementedError("段階4: Parser.statement を実装してください")

    def print_statement(self) -> Stmt:
        """段階4: print_stmt = "print" "(" expression ")" ";" ;  → Print(expr, line=print の行)"""
        raise NotImplementedError("段階4: Parser.print_statement を実装してください")

    def if_statement(self) -> Stmt:
        """段階4: if_stmt = "if" "(" expression ")" block [ "else" ( if_stmt | block ) ] ;

        → If(cond, then_branch, else_branch, line=if の行)。else if は else_branch に If を入れる。
        """
        raise NotImplementedError("段階4: Parser.if_statement を実装してください")

    def while_statement(self) -> Stmt:
        """段階4: while_stmt = "while" "(" expression ")" block ;  → While(cond, body, line=while の行)"""
        raise NotImplementedError("段階4: Parser.while_statement を実装してください")

    def block(self) -> Block:
        """段階4: block = "{" { declaration } "}" ;  → Block(tuple(stmts), line="{" の行)

        "}" の前にファイルが終わったら ParseError。
        """
        raise NotImplementedError("段階4: Parser.block を実装してください")

    def expression_statement(self) -> Stmt:
        """段階4: expr_stmt = expression ";" ;  → ExprStmt(expr, line=式の行)"""
        raise NotImplementedError("段階4: Parser.expression_statement を実装してください")

    # ---- 段階5（★★★）: 関数 ----
    def fn_declaration(self) -> Stmt:
        """段階5: fn_decl = "fn" IDENT "(" [ parameters ] ")" block ;

        → FnDecl(name, params, body, line=fn の行)。body はブロックの中の文のタプル（Block ではない）。
        """
        raise NotImplementedError("段階5: Parser.fn_declaration を実装してください")

    def function_rest(self) -> tuple[tuple[str, ...], tuple[Stmt, ...]]:
        """段階5: 関数の "(" [ parameters ] ")" block の部分を読み、(引数名のタプル, 本体の文のタプル) を返す。

        - 同じ引数名が 2 回現れたら ParseError。
        - 本体を読む間は self.function_depth を 1 増やしておく（読み終えたら戻す）。
          return_statement はこれを見て「関数の外の return」を検出する。
        fn_declaration と primary（無名関数）の両方から使う。
        """
        raise NotImplementedError("段階5: Parser.function_rest を実装してください")

    def return_statement(self) -> Stmt:
        """段階5: return_stmt = "return" [ expression ] ";" ;  → Return(value または None, line=return の行)

        関数の外（function_depth が 0）なら ParseError。
        """
        raise NotImplementedError("段階5: Parser.return_statement を実装してください")

    def finish_call(self, callee: Expr, paren: Token) -> Expr:
        """段階5: "(" を読んだ直後から、[ arguments ] ")" を読んで Call(callee, args, line=paren.line) を返す。"""
        raise NotImplementedError("段階5: Parser.finish_call を実装してください")


def parse(source: str) -> list[Stmt]:
    """ソースコード全体を文のリストに構文解析する（与えられたもの）。"""
    return Parser(tokenize(source)).parse_program()


def parse_expr(source: str) -> Expr:
    """ソースコードを 1 つの式として構文解析する（与えられたもの）。式の後に余計なものがあれば ParseError。"""
    parser = Parser(tokenize(source))
    expr = parser.parse_expression()
    if not parser.at_end():
        raise parser.error("式の後に余分なトークンがあります")
    return expr


# ===========================================================================
# 段階3〜5: 評価器（木をたどるインタプリタ）
# ===========================================================================


class Environment:
    """変数の環境（スコープ）。values に変数を持ち、見つからなければ parent（外側のスコープ）を探す。"""

    def __init__(self, parent: Environment | None = None) -> None:
        """与えられたもの。"""
        self.values: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value: object) -> None:
        """段階4: このスコープに変数を定義する（同じスコープに同名があれば上書きしてよい）。"""
        raise NotImplementedError("段階4: Environment.define を実装してください")

    def get(self, name: str, line: int = 0) -> object:
        """段階4: 変数の値を返す。このスコープになければ parent、その parent…とたどる。

        どこにもなければ MiniRuntimeError（未定義の変数。line を渡すこと）。
        """
        raise NotImplementedError("段階4: Environment.get を実装してください")

    def assign(self, name: str, value: object, line: int = 0) -> None:
        """段階4: 既存の変数に代入する。get と同じ順にたどり、**見つかったスコープの** 値を書き換える。

        どこにもなければ MiniRuntimeError（代入で新しい変数は作らない。変数の作成は let だけ）。
        """
        raise NotImplementedError("段階4: Environment.assign を実装してください")


@dataclass(eq=False)
class Function:
    """ユーザー定義の関数の値（与えられたもの）。closure は関数が **定義された** 環境。"""

    name: str | None  # 無名関数なら None
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    closure: Environment


@dataclass(eq=False)
class Builtin:
    """組み込み関数の値（与えられたもの）。fn(引数のリスト, 呼び出しの行番号) を呼ぶ。"""

    name: str
    arity: int
    fn: Callable[[list[object], int], object]


class ReturnSignal(Exception):
    """return 文の実行を、関数の呼び出し元まで伝えるための例外（与えられたもの）。

    return は「関数の途中から、何段もの文や while をまとめて抜ける」制御なので、
    ホスト言語（Python）の例外を使って実現する。call_function がこれを捕まえる。
    """

    def __init__(self, value: object) -> None:
        super().__init__("return")
        self.value = value


def stringify(value: object) -> str:
    """値を print で表示する文字列にする（与えられたもの）。

    nil → "nil"、真偽値 → "true" / "false"、関数 → "<fn 名前>" か "<fn>"、組み込み関数 → "<builtin 名前>"。
    bool は int のサブクラスなので、int より先に判定していることに注意。
    """
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


# 組み込み関数（与えられたもの）: str(x) は stringify(x)、len(s) は文字列の長さ
BUILTINS = (
    Builtin("str", 1, lambda args, line: stringify(args[0])),
    Builtin("len", 1, _builtin_len),
)


def _type_name(value: object) -> str:
    """値の型の名前（エラーメッセージ用。与えられたもの）。bool を int より先に判定する。"""
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, str):
        return "str"
    return "function"


# ---- 段階3（★★☆）: 演算の意味 ----
def is_truthy(value: object) -> bool:
    """段階3: MiniLang での真偽。false と nil だけが偽で、それ以外（0 や "" を含む）はすべて真。"""
    raise NotImplementedError("段階3: is_truthy を実装してください")


def values_equal(a: object, b: object) -> bool:
    """段階3: MiniLang の == の意味。型（_type_name）が違えば False。同じなら Python の == で比べる。

    関数（Function / Builtin）どうしは、同じオブジェクトのときだけ等しい（is で比べる）。
    Python では True == 1 だが、MiniLang では true == 1 は false であることに注意。
    """
    raise NotImplementedError("段階3: values_equal を実装してください")


def apply_unary(op: str, value: object, line: int = 0) -> object:
    """段階3: 単項演算を計算する。

    - "-": 整数（bool は除く）の符号反転。整数でなければ MiniRuntimeError。
    - "not": not is_truthy(value)（常に bool を返す）。
    """
    raise NotImplementedError("段階3: apply_unary を実装してください")


def apply_binary(op: str, left: object, right: object, line: int = 0) -> object:
    """段階3: 二項演算を計算する。型が合わなければ MiniRuntimeError（line を渡すこと）。

    - "==" / "!=": values_equal を使う。どの型の組み合わせでもエラーにならない。
    - "+": 整数どうしなら和、文字列どうしなら連結。それ以外はエラー。
    - "-" "*" "/" "%": 整数どうしのみ。bool は整数として扱わない（true + 1 はエラー）。
      "/" と "%" は 0 に向かって切り捨てる（-7 / 2 == -3、-7 % 2 == -1、7 % -2 == 1）。
      右辺が 0 なら MiniRuntimeError（0 で割ることはできません）。
    - "<" "<=" ">" ">=": 整数どうし、または文字列どうし（辞書順）。それ以外はエラー。

    段階6の定数畳み込みも、この関数を使って計算します（実行時と意味が食い違わないように）。

    ヒント: Python の // と % は負の無限大に向かって丸めるので、そのまま使うと -7 // 2 == -4 になる。
    """
    raise NotImplementedError("段階3: apply_binary を実装してください")


class Interpreter:
    """構文木をたどって実行するインタプリタ（tree-walking interpreter）。"""

    def __init__(self, max_steps: int = 1_000_000, max_depth: int = 200) -> None:
        """与えられたもの。globals に組み込み関数を入れておく。"""
        self.globals = Environment()
        self.output: list[str] = []  # print の出力先
        self.max_steps = max_steps  # while の反復と関数呼び出しの回数の上限（無限ループ対策）
        self.max_depth = max_depth  # 関数呼び出しの深さの上限（無限再帰対策）
        self.steps = 0
        self.depth = 0
        for builtin in BUILTINS:
            self.globals.values[builtin.name] = builtin

    # ---- 与えられたもの ----
    def interpret(self, program: list[Stmt]) -> None:
        """プログラム（文のリスト）を globals の中で順に実行する。

        木をたどる実装はホストの Python の再帰を使うので、実行中だけ Python の再帰の上限を
        引き上げ、それでも尽きたら MiniRuntimeError に変換する。
        """
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
        """実行ステップを 1 つ数え、上限を超えたら MiniRuntimeError。while の各反復と関数呼び出しで呼ぶ。"""
        self.steps += 1
        if self.steps > self.max_steps:
            raise MiniRuntimeError(f"実行ステップ数の上限（{self.max_steps}）を超えました", line)

    # ---- 段階4・5: 文の実行 ----
    def execute(self, stmt: Stmt, env: Environment) -> None:
        """段階4・5: 文を 1 つ実行する。

        段階4:
        - ExprStmt: 式を評価して結果を捨てる。
        - Print: 式を評価し、stringify した文字列を self.output に追加する。
        - Let: 式を評価し、env に define する。
        - Block: 新しい Environment(env) を作り、その中で execute_block する（ブロックごとのスコープ）。
        - If: 条件を評価し、is_truthy なら then_branch、そうでなく else_branch があればそれを実行する。
        - While: 条件が真の間、反復のたびに self.tick(stmt.line) を呼んでから本体を実行する。
        段階5:
        - FnDecl: Function(name, params, body, env) を作り、env に define する（env を閉じ込める）。
        - Return: 値（なければ None）を評価して ReturnSignal を送出する。
        それ以外は TypeError。
        """
        raise NotImplementedError("段階4: Interpreter.execute を実装してください")

    def execute_block(self, stmts: tuple[Stmt, ...], env: Environment) -> None:
        """段階4: 文の並びを、与えられた環境 env の中で順に実行する（新しい環境は作らない）。"""
        raise NotImplementedError("段階4: Interpreter.execute_block を実装してください")

    # ---- 段階3〜5: 式の評価 ----
    def evaluate(self, expr: Expr, env: Environment) -> object:
        """段階3〜5: 式を評価して値を返す。値は int / str / bool / None / Function / Builtin。

        段階3:
        - Number / String / Boolean → value、Nil → None
        - Unary → apply_unary(op, 被演算子の値, expr.line)
        - Binary → apply_binary(op, 左の値, 右の値, expr.line)（左→右の順に評価）
        - Logical → 短絡評価。or は左が真なら左の値、そうでなければ右の値。
                    and は左が偽なら左の値、そうでなければ右の値。右は必要なときだけ評価する。
        段階4:
        - Var → env.get(name, expr.line)
        - Assign → 右辺を評価し、env.assign(name, 値, expr.line)。式の値は代入した値。
        段階5:
        - FunctionExpr → Function(None, params, body, env)
        - Call → 呼び出す値と引数を（左から順に）評価し、self.call_function(値, 引数のリスト, expr.line)
        それ以外は TypeError。
        """
        raise NotImplementedError("段階3: Interpreter.evaluate を実装してください")

    def call_function(self, fn: object, args: list[object], line: int) -> object:
        """段階5: 関数を呼び出して戻り値を返す。

        - Builtin: 引数の数が arity と違えば MiniRuntimeError。fn.fn(args, line) の結果を返す。
        - Function:
          1. 引数の数が params と違えば MiniRuntimeError。
          2. self.tick(line) を呼ぶ。self.depth が self.max_depth 以上なら MiniRuntimeError（無限再帰対策）。
          3. 新しい環境 Environment(fn.closure) を作り、引数を define する。
             親は呼び出し元の env ではなく fn.closure（定義された場所）であることが、
             レキシカルスコープとクロージャの要。
          4. self.depth を 1 増やして本体を execute_block で実行し、終わったら（例外でも）1 減らす。
          5. ReturnSignal を捕まえたらその値を返す。最後まで return がなければ None を返す。
        - それ以外（整数や nil など）を呼ぼうとしたら MiniRuntimeError。
        """
        raise NotImplementedError("段階5: Interpreter.call_function を実装してください")


# ===========================================================================
# 段階6（★★☆）: 定数畳み込み
# ===========================================================================


def fold_constants(node):
    """段階6: 定数畳み込みをした新しい構文木を返す（元の構文木は変更しない）。

    node は 文のリスト・文・式 のいずれかで、同じ種類のものを返す。

    規則:
    - Binary / Unary: 子を先に畳み込み、すべての被演算子がリテラル（Number / String / Boolean / Nil）
      になったら apply_binary / apply_unary で計算し、結果のリテラルに置き換える。
      計算で MiniRuntimeError が起きる場合（1 / 0、"a" + 1 など）は **畳み込まずに残す**
      （エラーは実行時に、実行されたときだけ起きるべきだから）。
    - Logical: 左辺がリテラルなら、短絡評価の結果で置き換える。
        or で左辺が真 → 左辺、or で左辺が偽 → 右辺（を畳み込んだもの）
        and で左辺が偽 → 左辺、and で左辺が真 → 右辺（を畳み込んだもの）
      左辺がリテラルでなければ、両辺を畳み込むだけ。
    - If: 条件を畳み込み、リテラルになったら、真なら then_branch（Block）、偽なら else_branch、
      else_branch もなければ空の Block(()) に置き換える（実行されない分岐の除去）。
    - それ以外の文・式（While、Let、Call、関数の本体など）は、中に含まれる式と文を再帰的に畳み込む。
    - 変数（Var）は定数とみなさない。結合法則による並べ替え（x + 1 + 2 → x + 3）もしない。
    - 作ったリテラルの line は、置き換えた元のノードの line にする。

    >>> fold_constants(parse_expr("1 + 2 * 3"))
    Number(value=7)
    >>> fold_constants(parse_expr("x * (2 + 3)"))
    Binary(op='*', left=Var(name='x'), right=Number(value=5))

    ヒント: dataclasses.replace(node, left=..., right=...) で、一部のフィールドだけを
    変えた新しいノードを作れる（行番号も引き継がれる）。
    """
    raise NotImplementedError("段階6: fold_constants を実装してください")


# ===========================================================================
# まとめて実行する（与えられたもの）
# ===========================================================================


def run(source: str, *, optimize: bool = False, max_steps: int = 1_000_000, max_depth: int = 200) -> list[str]:
    """ソースコードを構文解析して実行し、print の出力（文字列のリスト）を返す。

    optimize=True なら、実行前に fold_constants を適用する。

    >>> run('let x = 6; print(x * 7); print("done");')
    ['42', 'done']
    """
    program = parse(source)
    if optimize:
        program = fold_constants(program)
    interpreter = Interpreter(max_steps=max_steps, max_depth=max_depth)
    interpreter.interpret(program)
    return interpreter.output
