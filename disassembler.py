"""Human-readable bytecode listing."""
from .compiler import compile_source
from .opcodes import JUMP_OPCODES, Opcode as O


def _argument_text(ins):
    op, arg = ins.opcode, ins.arg
    if op in JUMP_OPCODES:
        return "to {:04d}".format(arg)
    if op is O.CALL:
        name, argc, kwnames = arg
        text = "{}() with {} positional arg(s)".format(name, argc)
        if kwnames:
            text += ", keywords: " + ", ".join(kwnames)
        return text
    if op is O.CALL_METHOD:
        name, argc = arg
        return ".{}() with {} arg(s)".format(name, argc)
    if op is O.MAKE_FUNCTION:
        code, count = arg
        return "function {}({}) [{} default(s)]".format(code.name, ", ".join(code.params), count)
    return "" if arg is None else repr(arg)


def _format_code(code):
    title = "<main>" if code.name == "<main>" else "function {}({})".format(
        code.name, ", ".join(code.params))
    targets = {ins.arg for ins in code.instructions if ins.opcode in JUMP_OPCODES}
    row = "{} {:<4}  {:>4}  {:<20}  {}"
    lines = ["== {} ==".format(title),
             row.format("  ", "ADDR", "LINE", "OPCODE", "ARGUMENT"),
             row.format("  ", "----", "----", "-" * 20, "-" * 24)]
    for address, ins in enumerate(code.instructions):
        marker = ">>" if address in targets else "  "
        lines.append(row.format(marker, "{:04d}".format(address), ins.line,
                                ins.opcode.name, _argument_text(ins)).rstrip())
    return "\n".join(lines)


def disassemble(code):
    """Return a listing of the main code followed by every function body."""
    blocks = []
    queue = [code]
    while queue:
        current = queue.pop(0)
        blocks.append(_format_code(current))
        for ins in current.instructions:
            if ins.opcode is O.MAKE_FUNCTION:
                queue.append(ins.arg[0])
    return "\n\n".join(blocks)


def disassemble_source(source, flavour=None):
    return disassemble(compile_source(source, flavour))
