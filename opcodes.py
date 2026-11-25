"""Opcode definitions and the bytecode containers used by PitchVM."""
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, List, Optional


class Opcode(Enum):
    # Names and constants
    LOAD_CONST = auto()
    LOAD_NAME = auto()
    STORE_NAME = auto()
    # Arithmetic
    BINARY_ADD = auto()
    BINARY_SUB = auto()
    BINARY_MUL = auto()
    BINARY_DIV = auto()
    BINARY_FLOORDIV = auto()
    BINARY_MOD = auto()
    BINARY_POW = auto()
    UNARY_NEG = auto()
    UNARY_POS = auto()
    UNARY_NOT = auto()
    COMPARE_OP = auto()
    # Containers
    BUILD_LIST = auto()
    BINARY_SUBSCR = auto()
    STORE_SUBSCR = auto()
    # Loops and jumps
    GET_ITER = auto()
    FOR_ITER = auto()
    JUMP = auto()
    POP_JUMP_IF_FALSE = auto()
    POP_JUMP_IF_TRUE = auto()
    JUMP_IF_FALSE_OR_POP = auto()
    JUMP_IF_TRUE_OR_POP = auto()
    # Functions
    MAKE_FUNCTION = auto()
    CALL = auto()
    CALL_METHOD = auto()
    RETURN_VALUE = auto()
    # Stack and program control
    POP_TOP = auto()
    PRINT_EXPR = auto()
    HALT = auto()


JUMP_OPCODES = frozenset({
    Opcode.FOR_ITER,
    Opcode.JUMP,
    Opcode.POP_JUMP_IF_FALSE,
    Opcode.POP_JUMP_IF_TRUE,
    Opcode.JUMP_IF_FALSE_OR_POP,
    Opcode.JUMP_IF_TRUE_OR_POP,
})


@dataclass
class Instruction:
    opcode: Opcode
    arg: Optional[Any] = None
    line: int = 0


@dataclass
class CodeObject:
    """A compiled unit: the main program or one function body."""
    name: str
    params: List[str] = field(default_factory=list)
    instructions: List[Instruction] = field(default_factory=list)
