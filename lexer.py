"""Lexer: converts flavour source text into a flat list of tokens.

Python's own ``tokenize`` module does the heavy lifting (strings, numbers,
indentation). This layer then maps flavour words back to canonical Python words.
"""
import ast
import io
import keyword
import re
import tokenize
from dataclasses import dataclass
from typing import Any

from .errors import PitchSyntaxError
from .flavours import resolve_flavour

_FSTRING_TYPES = {
    getattr(tokenize, name)
    for name in ("FSTRING_START", "FSTRING_MIDDLE", "FSTRING_END",
                 "TSTRING_START", "TSTRING_MIDDLE", "TSTRING_END")
    if hasattr(tokenize, name)
}


@dataclass
class Token:
    type: str
    value: Any
    line: int


def _convert_number(text, line):
    try:
        return int(text, 0)
    except ValueError:
        pass
    if re.fullmatch(r"0[0-9_]+", text):
        raise PitchSyntaxError("leading zeros in decimal numbers are not allowed", line)
    try:
        return float(text)
    except ValueError:
        raise PitchSyntaxError("invalid number {!r}".format(text), line)


class Lexer:
    def __init__(self, source, flavour=None):
        self.source = source
        self.flavour = resolve_flavour(flavour, source)

    def _raw_tokens(self):
        try:
            raw = list(tokenize.generate_tokens(io.StringIO(self.source).readline))
        except tokenize.TokenError as exc:
            line = None
            if len(exc.args) > 1 and isinstance(exc.args[1], tuple):
                line = exc.args[1][0]
            raise PitchSyntaxError(str(exc.args[0]), line)
        except SyntaxError as exc:
            raise PitchSyntaxError(exc.msg, exc.lineno)
        skipped = (tokenize.COMMENT, tokenize.NL, tokenize.ENDMARKER)
        return [tok for tok in raw if tok.type not in skipped]

    def tokenize(self):
        sig = self._raw_tokens()
        out = []
        for i, tok in enumerate(sig):
            line = tok.start[0]
            kind = tok.type
            if kind in _FSTRING_TYPES:
                raise PitchSyntaxError(
                    "f-strings are not supported by the PVM (use --mode transpile)", line)
            if kind == tokenize.NEWLINE:
                out.append(Token("NEWLINE", "\n", line))
            elif kind == tokenize.INDENT:
                out.append(Token("INDENT", tok.string, line))
            elif kind == tokenize.DEDENT:
                out.append(Token("DEDENT", "", line))
            elif kind == tokenize.NUMBER:
                out.append(Token("NUMBER", _convert_number(tok.string, line), line))
            elif kind == tokenize.STRING:
                out.append(Token("STRING", self._string_value(tok.string, line), line))
            elif kind == tokenize.NAME:
                prev = sig[i - 1] if i > 0 else None
                nxt = sig[i + 1] if i + 1 < len(sig) else None
                out.append(self._name_token(tok, prev, nxt))
            elif kind == tokenize.OP:
                out.append(Token(tok.string, tok.string, line))
            elif kind == tokenize.ERRORTOKEN:
                if tok.string.strip():
                    raise PitchSyntaxError("unexpected character {!r}".format(tok.string), line)
            else:
                raise PitchSyntaxError("unsupported token {!r}".format(tok.string), line)
        out.append(Token("EOF", None, len(self.source.splitlines()) + 1))
        return out

    @staticmethod
    def _string_value(text, line):
        try:
            value = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            raise PitchSyntaxError("invalid string literal", line)
        if isinstance(value, bytes):
            raise PitchSyntaxError("bytes literals are not supported", line)
        return value

    def _name_token(self, tok, prev, nxt):
        word = tok.string
        line = tok.start[0]
        # Attribute names (obj.name) are never renamed.
        if prev is not None and prev.type == tokenize.OP and prev.string == ".":
            return Token("NAME", word, line)
        flavour = self.flavour
        if word in flavour.keyword_aliases:
            return Token("KEYWORD", flavour.keyword_aliases[word], line)
        # Built-in aliases only count when they are called, so variables may reuse the word.
        if (word in flavour.builtin_aliases and nxt is not None
                and nxt.type == tokenize.OP and nxt.string == "("):
            return Token("NAME", flavour.builtin_aliases[word], line)
        if keyword.iskeyword(word):
            return Token("KEYWORD", word, line)
        return Token("NAME", word, line)
