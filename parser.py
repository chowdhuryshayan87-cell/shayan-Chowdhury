"""Recursive-descent parser that turns tokens into an AST."""
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from .errors import PitchSyntaxError


# ---- AST nodes -------------------------------------------------------------
class Node:
    pass


@dataclass
class Const(Node):
    value: Any
    line: int = 0


@dataclass
class Name(Node):
    id: str
    line: int = 0


@dataclass
class UnaryOp(Node):
    op: str
    operand: Node
    line: int = 0


@dataclass
class BinOp(Node):
    left: Node
    op: str
    right: Node
    line: int = 0


@dataclass
class BoolOp(Node):
    op: str  # "and" / "or"
    left: Node
    right: Node
    line: int = 0


@dataclass
class Compare(Node):
    left: Node
    op: str
    right: Node
    line: int = 0


@dataclass
class IfExp(Node):
    cond: Node
    then: Node
    other: Node
    line: int = 0


@dataclass
class Call(Node):
    name: str
    args: List[Node]
    kwargs: List[Tuple[str, Node]]
    line: int = 0


@dataclass
class MethodCall(Node):
    obj: Node
    name: str
    args: List[Node]
    line: int = 0


@dataclass
class Index(Node):
    obj: Node
    index: Node
    line: int = 0


@dataclass
class ListExpr(Node):
    items: List[Node]
    line: int = 0


@dataclass
class ExprStmt(Node):
    expr: Node
    line: int = 0


@dataclass
class Assign(Node):
    name: str
    value: Node
    line: int = 0


@dataclass
class IndexAssign(Node):
    obj: Node
    index: Node
    value: Node
    line: int = 0


@dataclass
class If(Node):
    cond: Node
    body: List[Node]
    orelse: List[Node] = field(default_factory=list)
    line: int = 0


@dataclass
class While(Node):
    cond: Node
    body: List[Node]
    line: int = 0


@dataclass
class For(Node):
    var: str
    iterable: Node
    body: List[Node]
    line: int = 0


@dataclass
class Break(Node):
    line: int = 0


@dataclass
class Continue(Node):
    line: int = 0


@dataclass
class Pass(Node):
    line: int = 0


@dataclass
class Return(Node):
    value: Optional[Node] = None
    line: int = 0


@dataclass
class FunctionDef(Node):
    name: str
    params: List[Tuple[str, Optional[Node]]]
    body: List[Node]
    line: int = 0


@dataclass
class Program(Node):
    statements: List[Node]
    line: int = 0


AUGMENTED = {"+=": "+", "-=": "-", "*=": "*", "/=": "/", "//=": "//", "%=": "%", "**=": "**"}
COMPARISONS = ("==", "!=", "<", "<=", ">", ">=")


# ---- Parser ----------------------------------------------------------------
class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    # token helpers
    def cur(self):
        return self.tokens[min(self.pos, len(self.tokens) - 1)]

    def peek(self, offset=1):
        return self.tokens[min(self.pos + offset, len(self.tokens) - 1)]

    def take(self):
        tok = self.cur()
        if tok.type != "EOF":
            self.pos += 1
        return tok

    def at(self, type_, value=None):
        tok = self.cur()
        return tok.type == type_ and (value is None or tok.value == value)

    def at_keyword(self, value):
        return self.at("KEYWORD", value)

    def match(self, type_, value=None):
        return self.take() if self.at(type_, value) else None

    @staticmethod
    def describe(tok):
        names = {"NEWLINE": "end of line", "EOF": "end of file",
                 "INDENT": "indent", "DEDENT": "dedent"}
        return names.get(tok.type, repr(tok.value))

    def error(self, message, tok=None):
        return PitchSyntaxError(message, (tok or self.cur()).line)

    def expect(self, type_, value=None):
        tok = self.match(type_, value)
        if tok is None:
            wanted = repr(value) if value is not None else type_.lower()
            raise self.error("expected {}, got {}".format(wanted, self.describe(self.cur())))
        return tok

    def unexpected(self, tok):
        if tok.type == "INDENT":
            return self.error("unexpected indent", tok)
        if tok.type == "KEYWORD" and tok.value in ("elif", "else"):
            return self.error("unexpected '{}' without a matching 'if'".format(tok.value), tok)
        if tok.type == "KEYWORD":
            return self.error("keyword '{}' is not supported by the PVM "
                              "(use --mode transpile)".format(tok.value), tok)
        return self.error("expected an expression, got {}".format(self.describe(tok)), tok)

    def expect_end(self):
        if self.match("NEWLINE") or self.at("EOF"):
            return
        raise self.error("expected end of line, got {}".format(self.describe(self.cur())))

    # statements
    def parse(self):
        statements = []
        while not self.at("EOF"):
            statements.append(self.parse_statement())
        return Program(statements, 1)

    def parse_block(self):
        self.expect(":")
        if self.match("NEWLINE"):
            if not self.at("INDENT"):
                raise self.error("expected an indented block")
            self.take()
            body = []
            while not (self.at("DEDENT") or self.at("EOF")):
                body.append(self.parse_statement())
            self.match("DEDENT")
            return body
        return [self.parse_simple_statement()]

    def parse_statement(self):
        tok = self.cur()
        if tok.type == "KEYWORD":
            if tok.value == "if":
                return self.parse_if()
            if tok.value == "while":
                self.take()
                cond = self.parse_expression()
                return While(cond, self.parse_block(), tok.line)
            if tok.value == "for":
                return self.parse_for()
            if tok.value == "def":
                return self.parse_def()
        return self.parse_simple_statement()

    def parse_if(self):
        tok = self.take()  # 'if' or 'elif'
        cond = self.parse_expression()
        body = self.parse_block()
        orelse = []
        if self.at_keyword("elif"):
            orelse = [self.parse_if()]
        elif self.at_keyword("else"):
            self.take()
            orelse = self.parse_block()
        return If(cond, body, orelse, tok.line)

    def parse_for(self):
        tok = self.take()
        var = self.expect("NAME").value
        self.expect("KEYWORD", "in")
        iterable = self.parse_expression()
        return For(var, iterable, self.parse_block(), tok.line)

    def parse_def(self):
        tok = self.take()
        name = self.expect("NAME").value
        self.expect("(")
        params = []
        seen = set()
        has_default = False
        while not self.at(")"):
            pname_tok = self.expect("NAME")
            if pname_tok.value in seen:
                raise self.error("duplicate parameter {!r}".format(pname_tok.value), pname_tok)
            seen.add(pname_tok.value)
            default = None
            if self.match("="):
                default = self.parse_expression()
                has_default = True
            elif has_default:
                raise self.error("parameter without default follows parameter with default",
                                 pname_tok)
            params.append((pname_tok.value, default))
            if not self.match(","):
                break
        self.expect(")")
        return FunctionDef(name, params, self.parse_block(), tok.line)

    def parse_simple_statement(self):
        tok = self.cur()
        if tok.type == "KEYWORD" and tok.value in ("break", "continue", "pass"):
            self.take()
            self.expect_end()
            return {"break": Break, "continue": Continue, "pass": Pass}[tok.value](tok.line)
        if tok.type == "KEYWORD" and tok.value == "return":
            self.take()
            value = None
            if not (self.at("NEWLINE") or self.at("EOF")):
                value = self.parse_expression()
            self.expect_end()
            return Return(value, tok.line)
        expr = self.parse_expression()
        op_tok = self.cur()
        if op_tok.type == "=":
            self.take()
            value = self.parse_expression()
            self.expect_end()
            return self.make_assign(expr, value, tok.line)
        if op_tok.type in AUGMENTED:
            self.take()
            value = self.parse_expression()
            self.expect_end()
            combined = BinOp(expr, AUGMENTED[op_tok.type], value, tok.line)
            return self.make_assign(expr, combined, tok.line)
        self.expect_end()
        return ExprStmt(expr, tok.line)

    def make_assign(self, target, value, line):
        if isinstance(target, Name):
            return Assign(target.id, value, line)
        if isinstance(target, Index):
            return IndexAssign(target.obj, target.index, value, line)
        raise PitchSyntaxError("cannot assign to this expression", line)

    # expressions (lowest to highest precedence)
    def parse_expression(self):
        node = self.parse_or()
        if self.at_keyword("if"):
            tok = self.take()
            cond = self.parse_or()
            if not self.at_keyword("else"):
                raise self.error("conditional expression needs an 'else' part")
            self.take()
            other = self.parse_expression()
            return IfExp(cond, node, other, tok.line)
        return node

    def parse_or(self):
        node = self.parse_and()
        while self.at_keyword("or"):
            tok = self.take()
            node = BoolOp("or", node, self.parse_and(), tok.line)
        return node

    def parse_and(self):
        node = self.parse_not()
        while self.at_keyword("and"):
            tok = self.take()
            node = BoolOp("and", node, self.parse_not(), tok.line)
        return node

    def parse_not(self):
        if self.at_keyword("not"):
            tok = self.take()
            return UnaryOp("not", self.parse_not(), tok.line)
        return self.parse_comparison()

    def comparison_operator(self):
        tok = self.cur()
        if tok.type in COMPARISONS:
            self.take()
            return tok.type
        if tok.type == "KEYWORD" and tok.value == "in":
            self.take()
            return "in"
        if tok.type == "KEYWORD" and tok.value == "not":
            nxt = self.peek()
            if nxt.type == "KEYWORD" and nxt.value == "in":
                self.take()
                self.take()
                return "not in"
        return None

    def parse_comparison(self):
        left = self.parse_arith()
        result = None
        previous = left
        while True:
            line = self.cur().line
            op = self.comparison_operator()
            if op is None:
                break
            right = self.parse_arith()
            comparison = Compare(previous, op, right, line)
            # a < b < c  becomes  (a < b) and (b < c)
            result = comparison if result is None else BoolOp("and", result, comparison, line)
            previous = right
        return result if result is not None else left

    def parse_arith(self):
        node = self.parse_term()
        while self.cur().type in ("+", "-"):
            tok = self.take()
            node = BinOp(node, tok.type, self.parse_term(), tok.line)
        return node

    def parse_term(self):
        node = self.parse_unary()
        while self.cur().type in ("*", "/", "//", "%"):
            tok = self.take()
            node = BinOp(node, tok.type, self.parse_unary(), tok.line)
        return node

    def parse_unary(self):
        if self.cur().type in ("-", "+"):
            tok = self.take()
            return UnaryOp(tok.type, self.parse_unary(), tok.line)
        return self.parse_power()

    def parse_power(self):
        base = self.parse_postfix()
        if self.at("**"):
            tok = self.take()
            return BinOp(base, "**", self.parse_unary(), tok.line)
        return base

    def parse_postfix(self):
        node = self.parse_primary()
        while True:
            tok = self.cur()
            if tok.type == "(":
                if not isinstance(node, Name):
                    raise self.error("only named functions can be called", tok)
                node = self.parse_call(node)
            elif tok.type == "[":
                self.take()
                index = self.parse_expression()
                self.expect("]")
                node = Index(node, index, tok.line)
            elif tok.type == ".":
                self.take()
                name = self.expect("NAME").value
                if not self.at("("):
                    raise self.error("attribute access is not supported; only method calls "
                                     "such as items.append(x)")
                self.take()
                args = []
                while not self.at(")"):
                    args.append(self.parse_expression())
                    if not self.match(","):
                        break
                self.expect(")")
                node = MethodCall(node, name, args, tok.line)
            else:
                return node

    def parse_call(self, name_node):
        line = self.take().line  # '('
        args, kwargs, seen = [], [], set()
        while not self.at(")"):
            if self.at("NAME") and self.peek().type == "=":
                key = self.take().value
                self.take()
                if key in seen:
                    raise self.error("keyword argument {!r} repeated".format(key))
                seen.add(key)
                kwargs.append((key, self.parse_expression()))
            else:
                if kwargs:
                    raise self.error("positional argument follows keyword argument")
                args.append(self.parse_expression())
            if not self.match(","):
                break
        self.expect(")")
        return Call(name_node.id, args, kwargs, line)

    def parse_primary(self):
        tok = self.cur()
        if tok.type == "NUMBER":
            self.take()
            return Const(tok.value, tok.line)
        if tok.type == "STRING":
            self.take()
            value = tok.value
            while self.at("STRING"):  # "a" "b" joins like Python
                value += self.take().value
            return Const(value, tok.line)
        if tok.type == "KEYWORD" and tok.value in ("True", "False", "None"):
            self.take()
            return Const({"True": True, "False": False, "None": None}[tok.value], tok.line)
        if tok.type == "NAME":
            self.take()
            return Name(tok.value, tok.line)
        if tok.type == "(":
            self.take()
            node = self.parse_expression()
            self.expect(")")
            return node
        if tok.type == "[":
            self.take()
            items = []
            while not self.at("]"):
                items.append(self.parse_expression())
                if not self.match(","):
                    break
            self.expect("]")
            return ListExpr(items, tok.line)
        raise self.unexpected(tok)
