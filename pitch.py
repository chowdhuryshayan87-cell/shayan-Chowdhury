"""Pitch command line tool: run, disassemble, transpile, REPL and flavour management."""
import argparse
import sys
from pathlib import Path

from pitchvm.flavours import BUILTIN_DIR
from pitchvm import (CANONICAL_BUILTINS, CANONICAL_KEYWORDS, DEFAULT_FLAVOUR, FlavourError,
                     PitchError, __version__, check_alias, compile_source, disassemble,
                     get_flavour, list_flavours, resolve_flavour, run_source, transpile,
                     write_flavour_file)

COMMANDS = ("run", "dis", "transpile", "repl", "flavour", "-h", "--help", "--version")


# ---- helpers ---------------------------------------------------------------
def read_source(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def format_table(headers, rows):
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join("{:<" + str(w) + "}" for w in widths)
    out = [line.format(*headers), line.format(*["-" * w for w in widths])]
    out.extend(line.format(*[str(c) for c in row]) for row in rows)
    return "\n".join(text.rstrip() for text in out)


def run_transpiled(source, flavour, filename="<pitch>"):
    code = transpile(source, flavour)
    exec(compile(code, filename, "exec"), {"__name__": "__main__"})


def report(exc):
    print("{}: {}".format(type(exc).__name__, exc), file=sys.stderr)


# ---- argument parsing ------------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="pitch", description="Run and transpile flavoured Python on the Pitch VM.")
    parser.add_argument("--version", action="version", version="pitch " + __version__)
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run a file")
    run.add_argument("file")
    run.add_argument("--flavour")
    run.add_argument("--mode", choices=("pvm", "transpile"), default="pvm")
    run.add_argument("--max-steps", type=int, default=None, help="stop after N VM instructions")

    dis = sub.add_parser("dis", help="show the bytecode of a file")
    dis.add_argument("file")
    dis.add_argument("--flavour")

    tr = sub.add_parser("transpile", help="convert a file to plain Python")
    tr.add_argument("file")
    tr.add_argument("-o", "--output")
    tr.add_argument("--flavour")

    repl_parser = sub.add_parser("repl", help="interactive prompt")
    repl_parser.add_argument("--flavour")
    repl_parser.add_argument("--mode", choices=("pvm", "transpile"), default="pvm")

    fl = sub.add_parser("flavour", help="list, inspect and create flavours")
    fsub = fl.add_subparsers(dest="flavour_command")
    fsub.add_parser("list", help="list available flavours")
    show = fsub.add_parser("show", help="show every word of a flavour")
    show.add_argument("name")
    new = fsub.add_parser("new", help="create a flavour file you can edit")
    new.add_argument("name")
    new.add_argument("--from", dest="base", default="python", help="copy words from this flavour")
    new.add_argument("--dir", default=None, help="target folder (default: ./flavours)")
    new.add_argument("--description")
    fsub.add_parser("wizard", help="create a flavour by answering prompts")
    return parser


def parse_cli_args(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS:
        argv.insert(0, "run")  # shorthand: pitch file.pitch
    return build_parser().parse_args(argv)


# ---- REPL ------------------------------------------------------------------
def read_block(first, input_fn=input):
    lines = [first]
    if first.rstrip().endswith(":"):
        while True:
            try:
                line = input_fn("... ")
            except EOFError:
                break
            if not line.strip():
                break
            lines.append(line)
    return "\n".join(lines)


def repl(mode="pvm", flavour=None, input_fn=input):
    fl = get_flavour(flavour or DEFAULT_FLAVOUR)
    env = {}
    print("Pitch REPL ({} flavour, {} mode). Type exit to quit, :flavour NAME to switch.".format(
        fl.name, mode))
    while True:
        try:
            first = input_fn(">>> ")
        except EOFError:
            break
        except KeyboardInterrupt:
            print()
            continue
        text = first.strip()
        if text in ("exit", "quit", ":quit"):
            break
        if not text:
            continue
        if text.startswith(":flavour"):
            parts = text.split()
            try:
                if len(parts) == 2:
                    fl = get_flavour(parts[1])
                    print("Switched to flavour '{}'".format(fl.name))
                else:
                    print("Usage: :flavour NAME")
            except FlavourError as exc:
                report(exc)
            continue
        source = read_block(first, input_fn)
        try:
            if mode == "pvm":
                run_source(source, fl, environment=env, echo=True)
            else:
                code = transpile(source, fl)
                exec(compile(code + "\n", "<pitch-repl>", "single"), env, env)
        except Exception as exc:  # keep the prompt alive after any error
            report(exc)


# ---- flavour wizard --------------------------------------------------------
def new_flavour_wizard():
    name = input("New flavour name (letters, digits, underscore): ").strip()
    description = input("Short description: ").strip() or None
    base = input("Start from which flavour? [python]: ").strip() or "python"
    base_flavour = get_flavour(base)
    print("Type the new word for each item, press Enter to keep the word shown,")
    print("or type /done to keep everything that is left.")
    current = {c: base_flavour.alias_for(c) for c in CANONICAL_KEYWORDS + CANONICAL_BUILTINS}
    used = set(current.values())
    for canonical in CANONICAL_KEYWORDS + CANONICAL_BUILTINS:
        while True:
            answer = input("  {:<9} [{}]: ".format(canonical, current[canonical])).strip()
            if answer == "/done":
                break
            if not answer or answer == current[canonical]:
                break
            try:
                check_alias(answer, canonical, name)
                if answer in used:
                    raise FlavourError("{!r} is already used by another item".format(answer))
            except FlavourError as exc:
                print("    " + str(exc))
                continue
            used.discard(current[canonical])
            used.add(answer)
            current[canonical] = answer
            break
        if answer == "/done":
            break
    path = write_flavour_file(
        name, base=base, description=description,
        keywords={c: current[c] for c in CANONICAL_KEYWORDS},
        builtins={c: current[c] for c in CANONICAL_BUILTINS})
    print("Created {}".format(path))
    return path


# ---- interactive menu ------------------------------------------------------
def choose_flavour():
    names = ", ".join(f.name for f in list_flavours())
    answer = input("Flavour ({}) [{}]: ".format(names, DEFAULT_FLAVOUR)).strip()
    return answer or DEFAULT_FLAVOUR


def create_and_run_file():
    flavour = choose_flavour()
    get_flavour(flavour)
    path = input("New file name [hello.pitch]: ").strip() or "hello.pitch"
    if Path(path).exists() and input("{} exists. Overwrite? [y/N]: ".format(path)).strip().lower() != "y":
        print("Cancelled.")
        return
    print("Enter your code. Finish with a line containing only END.")
    lines = []
    while True:
        line = input()
        if line == "END":
            break
        lines.append(line)
    source = "# flavour: {}\n".format(flavour) + "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(source)
    print("Saved {}".format(path))
    run_source(source)


def interactive_menu():
    while True:
        print("\nPitch")
        print("1. Run file\n2. Create a new file and run it\n3. Launch REPL")
        print("4. Disassemble file\n5. Show transpiled Python\n6. List flavours")
        print("7. Create a new flavour\n8. Exit")
        choice = input("Choose: ").strip()
        if choice == "8":
            return 0
        try:
            if choice == "1":
                run_source(read_source(input("File path: ").strip()))
            elif choice == "2":
                create_and_run_file()
            elif choice == "3":
                repl(flavour=choose_flavour())
            elif choice == "4":
                print(disassemble(compile_source(read_source(input("File path: ").strip()))))
            elif choice == "5":
                print(transpile(read_source(input("File path: ").strip()), None), end="")
            elif choice == "6":
                print_flavour_list()
            elif choice == "7":
                new_flavour_wizard()
            else:
                print("Please choose 1-8.")
        except (PitchError, OSError) as exc:
            report(exc)


# ---- flavour sub-commands --------------------------------------------------
def print_flavour_list():
    errors = []
    rows = []
    for fl in list_flavours(errors):
        origin = "built-in" if fl.path is None or fl.path.parent == BUILTIN_DIR else str(fl.path)
        rows.append((fl.name, fl.description, origin))
    print(format_table(("NAME", "DESCRIPTION", "SOURCE"), rows))
    for message in errors:
        print("warning: " + message, file=sys.stderr)


def show_flavour(name):
    fl = get_flavour(name)
    print("{}: {}".format(fl.name, fl.description))
    rows = [("keyword", c, fl.alias_for(c)) for c in CANONICAL_KEYWORDS]
    rows += [("built-in", c, fl.alias_for(c)) for c in CANONICAL_BUILTINS]
    print(format_table(("KIND", "PYTHON", fl.name.upper()), rows))


def flavour_command(args):
    if args.flavour_command == "list":
        print_flavour_list()
    elif args.flavour_command == "show":
        show_flavour(args.name)
    elif args.flavour_command == "new":
        path = write_flavour_file(args.name, directory=args.dir, base=args.base,
                                  description=args.description)
        print("Created {}. Edit the words in that file, then use it with --flavour {}".format(
            path, args.name.lower()))
    elif args.flavour_command == "wizard":
        new_flavour_wizard()
    else:
        print_flavour_list()
    return 0


# ---- entry point -----------------------------------------------------------
def dispatch(args):
    if not args.command:
        return interactive_menu()
    if args.command == "repl":
        repl(args.mode, args.flavour)
        return 0
    if args.command == "flavour":
        return flavour_command(args)
    source = read_source(args.file)
    if args.command == "run":
        if args.mode == "pvm":
            run_source(source, args.flavour, max_steps=args.max_steps)
        else:
            try:
                run_transpiled(source, args.flavour, args.file)
            except PitchError:
                raise
            except Exception as exc:
                report(exc)
                return 1
    elif args.command == "dis":
        print(disassemble(compile_source(source, args.flavour)))
    elif args.command == "transpile":
        output = transpile(source, args.flavour)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(output)
        else:
            print(output, end="")
    return 0


def main(argv=None):
    args = parse_cli_args(argv)
    try:
        return dispatch(args)
    except PitchError as exc:
        report(exc)
        return 1
    except OSError as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
