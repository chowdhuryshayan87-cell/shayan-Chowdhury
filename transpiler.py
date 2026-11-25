"""Token-safe transpiler: flavour source -> ordinary Python source.

Only NAME tokens are edited, from the end of the file to the start, so strings,
comments, spacing and identifiers that merely contain a keyword (for example
``appealing``) are left exactly as written.
"""
import io
import tokenize

from .errors import PitchSyntaxError
from .flavours import resolve_flavour


def transpile(source, flavour=None):
    fl = resolve_flavour(flavour, source)
    try:
        tokens = [tok for tok in tokenize.generate_tokens(io.StringIO(source).readline)
                  if tok.type not in (tokenize.COMMENT, tokenize.NL)]
    except tokenize.TokenError as exc:
        line = exc.args[1][0] if len(exc.args) > 1 and isinstance(exc.args[1], tuple) else None
        raise PitchSyntaxError(str(exc.args[0]), line)
    except SyntaxError as exc:
        raise PitchSyntaxError(exc.msg, exc.lineno)

    edits = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME:
            continue
        prev = tokens[i - 1] if i > 0 else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if prev is not None and prev.type == tokenize.OP and prev.string == ".":
            continue  # attribute name
        replacement = None
        if tok.string in fl.keyword_aliases:
            replacement = fl.keyword_aliases[tok.string]
        elif (tok.string in fl.builtin_aliases and nxt is not None
              and nxt.type == tokenize.OP and nxt.string == "("):
            replacement = fl.builtin_aliases[tok.string]
        if replacement is not None:
            edits.append((tok.start[0] - 1, tok.start[1], tok.end[1], replacement))

    lines = io.StringIO(source).readlines()
    for row, start, end, replacement in sorted(edits, reverse=True):
        line = lines[row]
        lines[row] = line[:start] + replacement + line[end:]
    return "".join(lines)
