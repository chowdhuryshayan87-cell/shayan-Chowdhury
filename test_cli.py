import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pitch

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"


def call(argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = pitch.main(argv)
    return code, out.getvalue(), err.getvalue()


@mock.patch.dict(os.environ, {"PITCH_FLAVOURS": str(ROOT / "flavours")})
class CommandTests(unittest.TestCase):
    def test_run_and_shorthand(self):
        code, out, _ = call(["run", str(EXAMPLES / "chase.pitch")])
        self.assertEqual(code, 0)
        self.assertIn("Target chased in 3 overs", out)
        self.assertEqual(call([str(EXAMPLES / "chase.pitch")])[1], out)

    def test_run_in_transpile_mode(self):
        code, out, _ = call(["run", str(EXAMPLES / "primes.pitch"), "--mode", "transpile"])
        self.assertEqual(code, 0)
        self.assertIn("Count: 10", out)

    def test_flavour_flag_overrides_directive(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.pitch"
            path.write_text("dekhao(1)\n", encoding="utf-8")
            code, out, _ = call(["run", str(path), "--flavour", "banglish"])
            self.assertEqual((code, out), (0, "1\n"))

    def test_dis(self):
        code, out, _ = call(["dis", str(EXAMPLES / "run_rate.pitch")])
        self.assertEqual(code, 0)
        self.assertIn("MAKE_FUNCTION", out)
        self.assertIn("== function run_rate(runs, overs_bowled) ==", out)

    def test_transpile_to_stdout_and_file(self):
        code, out, _ = call(["transpile", str(EXAMPLES / "factorial.pitch")])
        self.assertIn("def factorial(n):", out)
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "out.py"
            call(["transpile", str(EXAMPLES / "factorial.pitch"), "-o", str(target)])
            self.assertIn("for i in range(1, 8):", target.read_text(encoding="utf-8"))

    def test_errors_are_reported_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.pitch"
            bad.write_text("# flavour: python\nx = 1 / 0\n", encoding="utf-8")
            code, _, err = call(["run", str(bad)])
            self.assertEqual(code, 1)
            self.assertIn("ZeroDivisionError", err)
            self.assertIn("line 2", err)
        code, _, err = call(["run", "missing_file.pitch"])
        self.assertEqual(code, 1)
        code, _, err = call(["run", str(EXAMPLES / "chase.pitch"), "--flavour", "nope"])
        self.assertEqual(code, 1)
        self.assertIn("unknown flavour", err)

    def test_max_steps_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            loop = Path(tmp) / "loop.pitch"
            loop.write_text("# flavour: python\nwhile True:\n    pass\n", encoding="utf-8")
            code, _, err = call(["run", str(loop), "--max-steps", "100"])
            self.assertEqual(code, 1)
            self.assertIn("step limit", err)

    def test_flavour_list_show_new(self):
        code, out, _ = call(["flavour", "list"])
        for name in ("python", "cricket", "banglish", "campus"):
            self.assertIn(name, out)
        code, out, _ = call(["flavour", "show", "cricket"])
        self.assertIn("appeal", out)
        self.assertIn("scoreboard", out)
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _ = call(["flavour", "new", "mine", "--from", "cricket", "--dir", tmp])
            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp) / "mine.json").exists())
            code, _, err = call(["flavour", "new", "mine", "--dir", tmp])
            self.assertEqual(code, 1)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as ctx:
            call(["--version"])
        self.assertEqual(ctx.exception.code, 0)


@mock.patch.dict(os.environ, {"PITCH_FLAVOURS": str(ROOT / "flavours")})
class InteractiveTests(unittest.TestCase):
    def feed(self, answers):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=answers), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            result = pitch.interactive_menu()
        return result, out.getvalue()

    def test_menu_run_file_and_exit(self):
        result, out = self.feed(["1", str(EXAMPLES / "factorial.pitch"), "8"])
        self.assertEqual(result, 0)
        self.assertIn("7 ! = 5040", out)

    def test_menu_create_and_run_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "new.pitch")
            answers = ["2", "cricket", target, "scoreboard(2 + 3)", "END", "8"]
            result, out = self.feed(answers)
            self.assertIn("5", out)
            text = Path(target).read_text(encoding="utf-8")
            self.assertTrue(text.startswith("# flavour: cricket\n"))

    def test_menu_shows_errors_and_continues(self):
        result, out = self.feed(["1", "does_not_exist.pitch", "9", "8"])
        self.assertEqual(result, 0)
        self.assertIn("Please choose 1-8.", out)

    def test_wizard_creates_valid_flavour(self):
        with tempfile.TemporaryDirectory() as tmp:
            answers = ["wizard_demo", "demo flavour", "python",
                       "maybe", "",            # if -> maybe, elif unchanged
                       "while", "otherwise",   # else -> rejected (keyword), then valid alias
                       "/done"]
            previous = os.getcwd()
            os.chdir(tmp)
            try:
                with mock.patch("builtins.input", side_effect=answers), \
                        contextlib.redirect_stdout(io.StringIO()) as out:
                    path = pitch.new_flavour_wizard()
                self.assertTrue((Path(tmp) / "flavours" / "wizard_demo.json").exists())
                self.assertTrue(path.exists())
                self.assertIn("already a Python keyword", out.getvalue())
            finally:
                os.chdir(previous)

    def run_repl(self, lines, **kwargs):
        out, err = io.StringIO(), io.StringIO()
        feed = iter(lines)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            pitch.repl(input_fn=lambda prompt="": next(feed), **kwargs)
        return out.getvalue(), err.getvalue()

    def test_repl_pvm_mode_keeps_state_and_echoes(self):
        text, _ = self.run_repl(["x = 4", "x * 2", "bowl sq(n):", "    deliver n * n", "",
                                 "scoreboard(sq(x))", "exit"], flavour="cricket")
        self.assertIn("8\n", text)
        self.assertIn("16\n", text)

    def test_repl_survives_errors_and_switches_flavour(self):
        text, err = self.run_repl(
            ["1 / 0", ":flavour banglish", "dekhao(7)", ":flavour nope", "exit"],
            flavour="cricket")
        self.assertIn("ZeroDivisionError", err)
        self.assertIn("unknown flavour", err)
        self.assertIn("Switched to flavour 'banglish'", text)
        self.assertIn("7\n", text)

    def test_repl_transpile_mode(self):
        text, _ = self.run_repl(["x = 3", "x + 1", "exit"], mode="transpile", flavour="python")
        self.assertIn("4\n", text)


if __name__ == "__main__":
    unittest.main()
