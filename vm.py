"""PitchVM: a stack-based virtual machine with a call stack of frames."""
import operator
import sys

from .compiler import compile_source
from .errors import PitchError, PitchRuntimeError
from .opcodes import Opcode as O

_MISSING = object()

_BINARY = {
    O.BINARY_ADD: operator.add, O.BINARY_SUB: operator.sub, O.BINARY_MUL: operator.mul,
    O.BINARY_DIV: operator.truediv, O.BINARY_FLOORDIV: operator.floordiv,
    O.BINARY_MOD: operator.mod, O.BINARY_POW: operator.pow,
}
_COMPARE = {
    "==": operator.eq, "!=": operator.ne, "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}
# Methods that may be called with obj.name(...). Anything else is refused.
ALLOWED_METHODS = frozenset({
    "append", "pop", "insert", "remove", "extend", "reverse", "sort", "count", "index",
    "upper", "lower", "strip", "split", "join", "replace", "startswith", "endswith", "title",
})


class PitchFunction:
    """A user function created by MAKE_FUNCTION."""

    def __init__(self, name, code, defaults):
        self.name = name
        self.code = code
        self.defaults = defaults

    def __repr__(self):
        return "<function {}>".format(self.name)


class _Frame:
    def __init__(self, code, local_vars):
        self.code = code
        self.ip = 0
        self.stack = []
        self.locals = local_vars


class PitchVM:
    def __init__(self, stdout=None, stdin=None, max_steps=None, max_depth=200):
        self.stdout = stdout or sys.stdout
        self.stdin = stdin
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.globals = {}
        self.steps = 0
        self.builtins = self._make_builtins()

    # ---- built-in functions (canonical English names)
    def _make_builtins(self):
        def pitch_print(*args, sep=" ", end="\n", **_ignored):
            self.stdout.write(sep.join(str(arg) for arg in args) + end)

        def pitch_input(prompt=""):
            if self.stdin is None:
                return input(prompt)
            self.stdout.write(str(prompt))
            line = self.stdin.readline()
            if not line:
                raise EOFError("no more input")
            return line.rstrip("\n")

        return {
            "print": pitch_print, "input": pitch_input, "len": len, "str": str, "int": int,
            "float": float, "bool": bool, "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "range": range, "sorted": sorted, "list": list,
        }

    def _bind(self, func, positional, keywords):
        params = func.code.params
        if len(positional) > len(params):
            raise TypeError("{}() takes {} positional argument(s) but {} were given".format(
                func.name, len(params), len(positional)))
        bound = dict(zip(params, positional))
        for key, value in keywords.items():
            if key not in params:
                raise TypeError("{}() got an unexpected keyword argument {!r}".format(func.name, key))
            if key in bound:
                raise TypeError("{}() got multiple values for argument {!r}".format(func.name, key))
            bound[key] = value
        first_default = len(params) - len(func.defaults)
        missing = []
        for index, param in enumerate(params):
            if param not in bound:
                if index >= first_default:
                    bound[param] = func.defaults[index - first_default]
                else:
                    missing.append(param)
        if missing:
            raise TypeError("{}() missing required argument(s): {}".format(
                func.name, ", ".join(missing)))
        return bound

    # ---- main loop
    def run(self, code, environment=None):
        self.globals = environment if environment is not None else {}
        frames = [_Frame(code, self.globals)]
        self.steps = 0
        while frames:
            frame = frames[-1]
            ins = frame.code.instructions[frame.ip]
            frame.ip += 1
            self.steps += 1
            if self.max_steps is not None and self.steps > self.max_steps:
                raise PitchRuntimeError("step limit of {} exceeded (possible infinite loop)".format(
                    self.max_steps), ins.line, frame.code.name)
            op, arg, stack = ins.opcode, ins.arg, frame.stack
            try:
                if op is O.LOAD_CONST:
                    stack.append(arg)
                elif op is O.LOAD_NAME:
                    if arg in frame.locals:
                        stack.append(frame.locals[arg])
                    elif arg in self.globals:
                        stack.append(self.globals[arg])
                    else:
                        raise NameError("name {!r} is not defined".format(arg))
                elif op is O.STORE_NAME:
                    frame.locals[arg] = stack.pop()
                elif op in _BINARY:
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(_BINARY[op](left, right))
                elif op is O.UNARY_NEG:
                    stack.append(-stack.pop())
                elif op is O.UNARY_POS:
                    stack.append(+stack.pop())
                elif op is O.UNARY_NOT:
                    stack.append(not stack.pop())
                elif op is O.COMPARE_OP:
                    right = stack.pop()
                    left = stack.pop()
                    if arg == "in":
                        stack.append(left in right)
                    elif arg == "not in":
                        stack.append(left not in right)
                    else:
                        stack.append(_COMPARE[arg](left, right))
                elif op is O.BUILD_LIST:
                    items = stack[-arg:] if arg else []
                    if arg:
                        del stack[-arg:]
                    stack.append(list(items))
                elif op is O.BINARY_SUBSCR:
                    index = stack.pop()
                    obj = stack.pop()
                    stack.append(obj[index])
                elif op is O.STORE_SUBSCR:
                    value = stack.pop()
                    index = stack.pop()
                    obj = stack.pop()
                    obj[index] = value
                elif op is O.GET_ITER:
                    stack.append(iter(stack.pop()))
                elif op is O.FOR_ITER:
                    try:
                        stack.append(next(stack[-1]))
                    except StopIteration:
                        stack.pop()
                        frame.ip = arg
                elif op is O.JUMP:
                    frame.ip = arg
                elif op is O.POP_JUMP_IF_FALSE:
                    if not stack.pop():
                        frame.ip = arg
                elif op is O.POP_JUMP_IF_TRUE:
                    if stack.pop():
                        frame.ip = arg
                elif op is O.JUMP_IF_FALSE_OR_POP:
                    if not stack[-1]:
                        frame.ip = arg
                    else:
                        stack.pop()
                elif op is O.JUMP_IF_TRUE_OR_POP:
                    if stack[-1]:
                        frame.ip = arg
                    else:
                        stack.pop()
                elif op is O.MAKE_FUNCTION:
                    func_code, count = arg
                    defaults = tuple(stack[-count:]) if count else ()
                    if count:
                        del stack[-count:]
                    stack.append(PitchFunction(func_code.name, func_code, defaults))
                elif op is O.CALL:
                    name, argc, kwnames = arg
                    total = argc + len(kwnames)
                    values = stack[-total:] if total else []
                    if total:
                        del stack[-total:]
                    positional = values[:argc]
                    keywords = dict(zip(kwnames, values[argc:]))
                    target = frame.locals.get(name, _MISSING)
                    if target is _MISSING:
                        target = self.globals.get(name, _MISSING)
                    if isinstance(target, PitchFunction):
                        if len(frames) >= self.max_depth:
                            raise PitchRuntimeError("maximum recursion depth exceeded",
                                                    ins.line, frame.code.name)
                        frames.append(_Frame(target.code, self._bind(target, positional, keywords)))
                    elif target is _MISSING:
                        builtin = self.builtins.get(name)
                        if builtin is None:
                            raise NameError("name {!r} is not defined".format(name))
                        stack.append(builtin(*positional, **keywords))
                    else:
                        raise TypeError("{!r} object is not callable".format(type(target).__name__))
                elif op is O.CALL_METHOD:
                    name, argc = arg
                    args = stack[-argc:] if argc else []
                    if argc:
                        del stack[-argc:]
                    obj = stack.pop()
                    if name not in ALLOWED_METHODS:
                        raise AttributeError("method {!r} is not supported by the PVM".format(name))
                    method = getattr(obj, name, None)
                    if method is None:
                        raise AttributeError("{!r} object has no method {!r}".format(
                            type(obj).__name__, name))
                    stack.append(method(*args))
                elif op is O.POP_TOP:
                    stack.pop()
                elif op is O.PRINT_EXPR:
                    value = stack.pop()
                    if value is not None:
                        self.stdout.write(repr(value) + "\n")
                elif op is O.RETURN_VALUE:
                    value = stack.pop()
                    frames.pop()
                    if frames:
                        frames[-1].stack.append(value)
                elif op is O.HALT:
                    break
                else:
                    raise RuntimeError("unknown opcode {!r}".format(op))
            except PitchError:
                raise
            except Exception as exc:
                raise PitchRuntimeError("{}: {}".format(type(exc).__name__, exc),
                                        ins.line, frame.code.name) from exc
        return self.globals


def run_source(source, flavour=None, stdout=None, stdin=None, environment=None,
               max_steps=None, echo=False):
    """Compile and run source text. Returns the global environment."""
    code = compile_source(source, flavour, echo=echo)
    return PitchVM(stdout=stdout, stdin=stdin, max_steps=max_steps).run(code, environment)
