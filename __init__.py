"""PitchVM: flavoured Python dialects, a bytecode compiler and a stack VM."""
from .compiler import Compiler, compile_source
from .disassembler import disassemble, disassemble_source
from .errors import FlavourError, PitchError, PitchRuntimeError, PitchSyntaxError
from .flavours import (CANONICAL_BUILTINS, CANONICAL_KEYWORDS, DEFAULT_FLAVOUR, Flavour,
                       check_alias, detect_flavour, get_flavour, list_flavours,
                       resolve_flavour, write_flavour_file)
from .lexer import Lexer, Token
from .opcodes import CodeObject, Instruction, Opcode
from .parser import Parser
from .transpiler import transpile
from .vm import PitchFunction, PitchVM, run_source

__version__ = "1.0.0"

__all__ = [
    "CANONICAL_BUILTINS", "CANONICAL_KEYWORDS", "CodeObject", "Compiler", "DEFAULT_FLAVOUR",
    "Flavour", "FlavourError", "Instruction", "Lexer", "Opcode", "Parser", "PitchError",
    "PitchFunction", "PitchRuntimeError", "PitchSyntaxError", "PitchVM", "Token",
    "check_alias", "compile_source", "detect_flavour", "disassemble", "disassemble_source",
    "get_flavour", "list_flavours", "resolve_flavour", "run_source", "transpile",
    "write_flavour_file",
]
