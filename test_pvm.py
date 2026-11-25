import io
import unittest

from pitchvm import (CANONICAL_BUILTINS, Compiler, Lexer, Parser, PitchRuntimeError,
                     PitchSyntaxError, PitchVM, compile_source, disassemble, run_source)
from pitchvm.opcodes import JUMP_OPCODES, Opcode as O
from pitchvm.parser import Assign, Program


def run(source, flavour="python", **kwargs):
    out = io.StringIO()
    env = run_source(source, flavour, stdout=out, **kwargs)
    return out.getvalue(), env


class LexerParserTests(unittest.TestCase):
    def test_lexer_maps_flavour_words(self):
        tokens = Lexer("appeal six:\n    scoreboard(1)\n", "cricket").tokenize()
        kinds = [(t.type, t.value) for t in tokens]
        self.assertIn(("KEYWORD", "if"), kinds)
        self.assertIn(("KEYWORD", "True"), kinds)
        self.assertIn(("NAME", "print"), kinds)

    def test_builtin_alias_only_when_called(self):
        tokens = Lexer("balls = 3\nx = balls(\"ab\")\n", "cricket").tokenize()
        names = [t.value for t in tokens if t.type == "NAME"]
        self.assertEqual(names, ["balls", "x", "len"])

    def test_attribute_names_are_not_renamed(self):
        tokens = Lexer("x.appeal(1)\n", "cricket").tokenize()
        self.assertIn(("NAME", "appeal"), [(t.type, t.value) for t in tokens])

    def test_parser_builds_program(self):
        tree = Parser(Lexer("x = 1\n", "python").tokenize()).parse()
        self.assertIsInstance(tree, Program)
        self.assertIsInstance(tree.statements[0], Assign)

    def test_syntax_errors_carry_line_numbers(self):
        with self.assertRaises(PitchSyntaxError) as ctx:
            run("x = 1\ny = = 2\n")
        self.assertEqual(ctx.exception.line, 2)

    def test_unsupported_keyword_message(self):
        with self.assertRaises(PitchSyntaxError) as ctx:
            run("import os\n")
        self.assertIn("transpile", str(ctx.exception))

    def test_fstrings_rejected(self):
        with self.assertRaises(PitchSyntaxError):
            run('x = 1\nprint(f"{x}")\n')


class ExecutionTests(unittest.TestCase):
    def test_arithmetic_precedence_and_power(self):
        out, _ = run("print(8 - 3 * 2, -2 ** 2, 2 ** 3 ** 2, 7 // 2, 7 % 4, 7 / 2)\n")
        self.assertEqual(out, "2 -4 512 3 3 3.5\n")

    def test_comparison_chain_and_logic(self):
        out, _ = run("x = 5\nprint(1 < x < 10, 1 < x < 3, x in [5, 6], x not in [5], not x == 5)\n")
        self.assertEqual(out, "True False True False False\n")

    def test_short_circuit_returns_values(self):
        out, _ = run("print(0 or 7, 3 and 4, None or 'x')\n")
        self.assertEqual(out, "7 4 x\n")

    def test_ternary(self):
        out, _ = run("x = 3\nprint('big' if x > 2 else 'small')\n")
        self.assertEqual(out, "big\n")

    def test_while_with_break_and_continue(self):
        src = ("i = 0\nt = 0\nwhile True:\n    i += 1\n    if i % 2 == 0:\n        continue\n"
               "    if i > 7:\n        break\n    t += i\nprint(t)\n")
        self.assertEqual(run(src)[0], "16\n")

    def test_for_loop_break_leaves_stack_clean(self):
        src = ("t = 0\nfor i in range(3):\n    for j in range(10):\n        if j == 2:\n"
               "            break\n        t += 1\nprint(t)\n")
        self.assertEqual(run(src)[0], "6\n")

    def test_for_over_list_and_string(self):
        out, _ = run("for c in 'ab':\n    print(c)\nfor n in [1, 2]:\n    print(n)\n")
        self.assertEqual(out, "a\nb\n1\n2\n")

    def test_lists_and_methods(self):
        src = "a = [3, 1]\na.append(2)\na[0] = 9\na[1] += 10\nprint(a, a[-1], len(a))\nprint(a.pop(), a)\n"
        self.assertEqual(run(src)[0], "[9, 11, 2] 2 3\n2 [9, 11]\n")

    def test_functions_defaults_keywords_recursion(self):
        src = ("def fact(n):\n    if n <= 1:\n        return 1\n    return n * fact(n - 1)\n"
               "def add(a, b=10):\n    return a + b\n"
               "print(fact(6), add(1), add(1, 2), add(b=5, a=1))\n")
        self.assertEqual(run(src)[0], "720 11 3 6\n")

    def test_function_without_return_gives_none(self):
        self.assertEqual(run("def f():\n    pass\nprint(f())\n")[0], "None\n")

    def test_function_locals_do_not_leak(self):
        with self.assertRaises(PitchRuntimeError):
            run("def f():\n    secret = 1\nf()\nprint(secret)\n")

    def test_print_sep_and_end(self):
        self.assertEqual(run("print('a', 'b', sep='-', end='!')\n")[0], "a-b!")

    def test_single_line_suite(self):
        self.assertEqual(run("if True: print('ok')\n")[0], "ok\n")

    def test_input_from_stdin(self):
        out = io.StringIO()
        run_source("name = input('Name? ')\nprint('Hi', name)\n", "python",
                   stdout=out, stdin=io.StringIO("Shayan\n"))
        self.assertEqual(out.getvalue(), "Name? Hi Shayan\n")

    def test_environment_persists_between_runs(self):
        env = {}
        run_source("def twice(x):\n    return x * 2\ny = 4\n", "python", environment=env)
        out = io.StringIO()
        run_source("print(twice(y))\n", "python", stdout=out, environment=env)
        self.assertEqual(out.getvalue(), "8\n")

    def test_echo_mode_prints_expression_values(self):
        out = io.StringIO()
        run_source("1 + 2\nx = 5\nx\nprint('p')\n", "python", stdout=out, echo=True)
        self.assertEqual(out.getvalue(), "3\n5\np\n")


class RuntimeErrorTests(unittest.TestCase):
    def test_division_by_zero_reports_line(self):
        with self.assertRaises(PitchRuntimeError) as ctx:
            run("x = 1\ny = x / 0\n")
        self.assertEqual(ctx.exception.line, 2)
        self.assertIn("ZeroDivisionError", str(ctx.exception))

    def test_undefined_name(self):
        with self.assertRaises(PitchRuntimeError) as ctx:
            run("print(nothing)\n")
        self.assertIn("NameError", str(ctx.exception))

    def test_error_inside_function_names_the_function(self):
        with self.assertRaises(PitchRuntimeError) as ctx:
            run("def f():\n    return 1 / 0\nf()\n")
        self.assertEqual(ctx.exception.where, "f")

    def test_recursion_limit(self):
        with self.assertRaises(PitchRuntimeError) as ctx:
            run("def f():\n    return f()\nf()\n")
        self.assertIn("recursion", str(ctx.exception))

    def test_step_limit_stops_infinite_loop(self):
        with self.assertRaises(PitchRuntimeError) as ctx:
            run("while True:\n    pass\n", max_steps=500)
        self.assertIn("step limit", str(ctx.exception))

    def test_wrong_argument_count(self):
        with self.assertRaises(PitchRuntimeError):
            run("def f(a):\n    return a\nf(1, 2)\n")

    def test_unknown_method_is_blocked(self):
        with self.assertRaises(PitchRuntimeError):
            run("x = [1]\nx.__class__()\n")

    def test_break_outside_loop_is_compile_error(self):
        with self.assertRaises(PitchSyntaxError):
            run("break\n")

    def test_return_outside_function_is_compile_error(self):
        with self.assertRaises(PitchSyntaxError):
            run("return 1\n")

    def test_nested_def_is_rejected(self):
        with self.assertRaises(PitchSyntaxError):
            run("def a():\n    def b():\n        pass\n")


class BytecodeTests(unittest.TestCase):
    def test_vm_builtins_match_flavour_vocabulary(self):
        self.assertEqual(set(PitchVM().builtins), set(CANONICAL_BUILTINS))

    def test_program_ends_with_halt_and_jumps_in_range(self):
        code = compile_source("x = 1\nif x:\n    print(x)\nwhile x < 3:\n    x += 1\n", "python")
        self.assertIs(code.instructions[-1].opcode, O.HALT)
        for ins in code.instructions:
            if ins.opcode in JUMP_OPCODES:
                self.assertTrue(0 <= ins.arg < len(code.instructions))

    def test_compiler_instance_is_reusable(self):
        tree = Parser(Lexer("x = 1\n", "python").tokenize()).parse()
        compiler = Compiler()
        self.assertEqual(len(compiler.compile(tree).instructions),
                         len(compiler.compile(tree).instructions))

    def test_disassembler_lists_functions_and_targets(self):
        text = disassemble(compile_source("def f(a, b=1):\n    return a\nwhile True:\n    f(1)\n",
                                          "python"))
        self.assertIn("ADDR", text)
        self.assertIn("MAKE_FUNCTION", text)
        self.assertIn("== function f(a, b) ==", text)
        self.assertIn(">>", text)
        self.assertIn("RETURN_VALUE", text)


if __name__ == "__main__":
    unittest.main()
