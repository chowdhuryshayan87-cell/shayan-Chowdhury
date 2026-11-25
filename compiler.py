"""Compiler: walks the AST and emits bytecode (one CodeObject per function)."""
from .errors import PitchSyntaxError
from .lexer import Lexer
from .opcodes import CodeObject, Instruction, Opcode as O
from .parser import Parser

BINARY_OPS = {
    "+": O.BINARY_ADD, "-": O.BINARY_SUB, "*": O.BINARY_MUL, "/": O.BINARY_DIV,
    "//": O.BINARY_FLOORDIV, "%": O.BINARY_MOD, "**": O.BINARY_POW,
}
UNARY_OPS = {"-": O.UNARY_NEG, "+": O.UNARY_POS, "not": O.UNARY_NOT}


class _Loop:
    def __init__(self, kind, start):
        self.kind = kind          # "while" or "for"
        self.start = start        # jump target for 'continue'
        self.breaks = []          # JUMP instructions to patch with the loop end


class _Scope:
    def __init__(self, name, params):
        self.name = name
        self.params = params
        self.code = []
        self.loops = []


class Compiler:
    def __init__(self, echo=False):
        self.echo = echo          # REPL mode: print values of top-level expression statements
        self.scopes = []
        self.line = 0

    # ---- helpers
    @property
    def scope(self):
        return self.scopes[-1]

    def emit(self, opcode, arg=None):
        self.scope.code.append(Instruction(opcode, arg, self.line))
        return len(self.scope.code) - 1

    def here(self):
        return len(self.scope.code)

    def patch(self, index, target):
        self.scope.code[index].arg = target

    def error(self, message, node):
        return PitchSyntaxError(message, getattr(node, "line", None))

    def compile(self, program):
        self.scopes = [_Scope("<main>", [])]
        self.line = 1
        for statement in program.statements:
            self.visit(statement)
        self.emit(O.HALT)
        scope = self.scopes.pop()
        return CodeObject("<main>", [], scope.code)

    def visit(self, node):
        method = getattr(self, "visit_" + type(node).__name__, None)
        if method is None:
            raise TypeError("cannot compile node type " + type(node).__name__)
        if getattr(node, "line", 0):
            self.line = node.line
        return method(node)

    def visit_all(self, statements):
        for statement in statements:
            self.visit(statement)

    # ---- expressions
    def visit_Const(self, n):
        self.emit(O.LOAD_CONST, n.value)

    def visit_Name(self, n):
        self.emit(O.LOAD_NAME, n.id)

    def visit_UnaryOp(self, n):
        self.visit(n.operand)
        self.line = n.line
        self.emit(UNARY_OPS[n.op])

    def visit_BinOp(self, n):
        self.visit(n.left)
        self.visit(n.right)
        self.line = n.line
        self.emit(BINARY_OPS[n.op])

    def visit_Compare(self, n):
        self.visit(n.left)
        self.visit(n.right)
        self.line = n.line
        self.emit(O.COMPARE_OP, n.op)

    def visit_BoolOp(self, n):
        self.visit(n.left)
        jump = self.emit(O.JUMP_IF_FALSE_OR_POP if n.op == "and" else O.JUMP_IF_TRUE_OR_POP, -1)
        self.visit(n.right)
        self.patch(jump, self.here())

    def visit_IfExp(self, n):
        self.visit(n.cond)
        to_else = self.emit(O.POP_JUMP_IF_FALSE, -1)
        self.visit(n.then)
        to_end = self.emit(O.JUMP, -1)
        self.patch(to_else, self.here())
        self.visit(n.other)
        self.patch(to_end, self.here())

    def visit_ListExpr(self, n):
        for item in n.items:
            self.visit(item)
        self.emit(O.BUILD_LIST, len(n.items))

    def visit_Index(self, n):
        self.visit(n.obj)
        self.visit(n.index)
        self.line = n.line
        self.emit(O.BINARY_SUBSCR)

    def visit_Call(self, n):
        for arg in n.args:
            self.visit(arg)
        for _, value in n.kwargs:
            self.visit(value)
        self.line = n.line
        self.emit(O.CALL, (n.name, len(n.args), tuple(key for key, _ in n.kwargs)))

    def visit_MethodCall(self, n):
        self.visit(n.obj)
        for arg in n.args:
            self.visit(arg)
        self.line = n.line
        self.emit(O.CALL_METHOD, (n.name, len(n.args)))

    # ---- statements
    def visit_ExprStmt(self, n):
        self.visit(n.expr)
        self.line = n.line
        if self.echo and len(self.scopes) == 1:
            self.emit(O.PRINT_EXPR)
        else:
            self.emit(O.POP_TOP)

    def visit_Assign(self, n):
        self.visit(n.value)
        self.line = n.line
        self.emit(O.STORE_NAME, n.name)

    def visit_IndexAssign(self, n):
        self.visit(n.obj)
        self.visit(n.index)
        self.visit(n.value)
        self.line = n.line
        self.emit(O.STORE_SUBSCR)

    def visit_Pass(self, n):
        pass

    def visit_If(self, n):
        self.visit(n.cond)
        to_else = self.emit(O.POP_JUMP_IF_FALSE, -1)
        self.visit_all(n.body)
        if n.orelse:
            to_end = self.emit(O.JUMP, -1)
            self.patch(to_else, self.here())
            self.visit_all(n.orelse)
            self.patch(to_end, self.here())
        else:
            self.patch(to_else, self.here())

    def visit_While(self, n):
        start = self.here()
        self.visit(n.cond)
        to_end = self.emit(O.POP_JUMP_IF_FALSE, -1)
        loop = _Loop("while", start)
        self.scope.loops.append(loop)
        self.visit_all(n.body)
        self.scope.loops.pop()
        self.line = n.line
        self.emit(O.JUMP, start)
        end = self.here()
        self.patch(to_end, end)
        for jump in loop.breaks:
            self.patch(jump, end)

    def visit_For(self, n):
        self.visit(n.iterable)
        self.line = n.line
        self.emit(O.GET_ITER)
        start = self.here()
        for_iter = self.emit(O.FOR_ITER, -1)
        self.emit(O.STORE_NAME, n.var)
        loop = _Loop("for", start)
        self.scope.loops.append(loop)
        self.visit_all(n.body)
        self.scope.loops.pop()
        self.line = n.line
        self.emit(O.JUMP, start)
        end = self.here()
        self.patch(for_iter, end)
        for jump in loop.breaks:
            self.patch(jump, end)

    def visit_Break(self, n):
        if not self.scope.loops:
            raise self.error("'break' outside loop", n)
        loop = self.scope.loops[-1]
        if loop.kind == "for":
            self.emit(O.POP_TOP)  # discard the loop iterator
        loop.breaks.append(self.emit(O.JUMP, -1))

    def visit_Continue(self, n):
        if not self.scope.loops:
            raise self.error("'continue' not properly in loop", n)
        self.emit(O.JUMP, self.scope.loops[-1].start)

    def visit_Return(self, n):
        if len(self.scopes) == 1:
            raise self.error("'return' outside function", n)
        if n.value is None:
            self.emit(O.LOAD_CONST, None)
        else:
            self.visit(n.value)
        self.line = n.line
        self.emit(O.RETURN_VALUE)

    def visit_FunctionDef(self, n):
        if len(self.scopes) > 1:
            raise self.error("nested function definitions are not supported", n)
        defaults = [default for _, default in n.params if default is not None]
        for default in defaults:
            self.visit(default)
        self.scopes.append(_Scope(n.name, [name for name, _ in n.params]))
        self.visit_all(n.body)
        self.line = n.line
        self.emit(O.LOAD_CONST, None)
        self.emit(O.RETURN_VALUE)
        scope = self.scopes.pop()
        code = CodeObject(n.name, scope.params, scope.code)
        self.line = n.line
        self.emit(O.MAKE_FUNCTION, (code, len(defaults)))
        self.emit(O.STORE_NAME, n.name)


def compile_source(source, flavour=None, echo=False):
    """Lex, parse and compile source text into a CodeObject."""
    tokens = Lexer(source, flavour).tokenize()
    tree = Parser(tokens).parse()
    return Compiler(echo=echo).compile(tree)
