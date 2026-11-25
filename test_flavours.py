import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pitchvm import (CANONICAL_BUILTINS, CANONICAL_KEYWORDS, Flavour, FlavourError,
                     detect_flavour, get_flavour, list_flavours, transpile, write_flavour_file)

ROOT = Path(__file__).resolve().parent


class FlavourLoadingTests(unittest.TestCase):
    def test_builtin_flavours_load_and_cover_everything(self):
        for name in ("cricket", "banglish"):
            fl = get_flavour(name)
            self.assertEqual(set(fl.keywords), set(CANONICAL_KEYWORDS))
            self.assertEqual(set(fl.builtins), set(CANONICAL_BUILTINS))

    def test_python_flavour_is_identity(self):
        self.assertEqual(get_flavour("python").keyword_aliases, {})

    def test_unknown_flavour_lists_choices(self):
        with self.assertRaises(FlavourError) as ctx:
            get_flavour("klingon")
        self.assertIn("cricket", str(ctx.exception))

    def test_list_flavours_includes_python_first(self):
        self.assertEqual(list_flavours()[0].name, "python")

    def test_directive_detection(self):
        self.assertEqual(detect_flavour("# flavour: Banglish\nx = 1\n"), "banglish")
        self.assertEqual(detect_flavour("# flavor: cricket\n"), "cricket")
        self.assertIsNone(detect_flavour("x = 1\n"))
        late = "\n" * 6 + "# flavour: cricket\n"
        self.assertIsNone(detect_flavour(late))

    def test_validation_rejects_bad_aliases(self):
        bad = [
            {"keywords": {"if": "while"}},                 # python keyword
            {"keywords": {"if": "two words"}},             # not an identifier
            {"keywords": {"if": "x", "else": "x"}},        # duplicate alias
            {"keywords": {"nope": "x"}},                   # unknown canonical word
            {"builtins": {"print": "len"}},                # built-in name
            {"keywords": {"if": "same"}, "builtins": {"print": "same"}},
        ]
        for data in bad:
            with self.assertRaises(FlavourError, msg=str(data)):
                Flavour("t", "", data.get("keywords"), data.get("builtins"))

    def test_search_dirs_and_env_var(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "mine.json").write_text(json.dumps(
                {"description": "x", "keywords": {"if": "kya"}}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"PITCH_FLAVOURS": tmp}):
                self.assertEqual(get_flavour("mine").keyword_aliases, {"kya": "if"})

    def test_bad_json_and_unknown_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "broken.json").write_text("{not json", encoding="utf-8")
            (Path(tmp) / "typo.json").write_text('{"keywrods": {}}', encoding="utf-8")
            with mock.patch.dict(os.environ, {"PITCH_FLAVOURS": tmp}):
                with self.assertRaises(FlavourError):
                    get_flavour("broken")
                with self.assertRaises(FlavourError):
                    get_flavour("typo")
                errors = []
                list_flavours(errors)
                self.assertEqual(len(errors), 2)


class NewFlavourTests(unittest.TestCase):
    def test_write_new_flavour_and_use_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_flavour_file("kitchen", directory=tmp, base="python",
                                      description="cooking words",
                                      keywords={"if": "taste", "else": "serve"},
                                      builtins={"print": "plate"})
            self.assertTrue(path.exists())
            with mock.patch.dict(os.environ, {"PITCH_FLAVOURS": tmp}):
                out = transpile("taste True:\n    plate(1)\nserve:\n    plate(2)\n", "kitchen")
            self.assertEqual(out, "if True:\n    print(1)\nelse:\n    print(2)\n")

    def test_new_flavour_can_copy_a_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_flavour_file("copy_of_cricket", directory=tmp, base="cricket")
            data = json.loads((Path(tmp) / "copy_of_cricket.json").read_text(encoding="utf-8"))
            self.assertEqual(data["keywords"]["if"], "appeal")

    def test_refuses_overwrite_and_bad_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_flavour_file("once", directory=tmp)
            with self.assertRaises(FlavourError):
                write_flavour_file("once", directory=tmp)
            for name in ("9lives", "has space", "python", ""):
                with self.assertRaises(FlavourError):
                    write_flavour_file(name, directory=tmp)

    def test_invalid_alias_is_not_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FlavourError):
                write_flavour_file("bad", directory=tmp, keywords={"if": "while"})
            self.assertFalse((Path(tmp) / "bad.json").exists())


class TranspilerTests(unittest.TestCase):
    def test_keywords(self):
        self.assertIn("if x:", transpile("appeal x:\n    scoreboard(x)\n", "cricket"))

    def test_strings_comments_and_substrings_are_untouched(self):
        src = 'appealing = "appeal"  # notout\nappeal True:\n    scoreboard("balls")\n'
        out = transpile(src, "cricket")
        self.assertIn('appealing = "appeal"  # notout', out)
        self.assertIn("if True:", out)
        self.assertIn('print("balls")', out)

    def test_builtin_alias_only_replaced_when_called(self):
        out = transpile("balls = 2\nx = balls(\"ab\")\n", "cricket")
        self.assertEqual(out, 'balls = 2\nx = len("ab")\n')

    def test_attributes_untouched(self):
        self.assertEqual(transpile("obj.appeal(1)\n", "cricket"), "obj.appeal(1)\n")

    def test_functions_and_loops(self):
        src = "banao add(a, b):\n    ferot a + b\nproti i moddhe porjay(3):\n    dekhao(i)\n"
        out = transpile(src, "banglish")
        self.assertIn("def add", out)
        self.assertIn("for i in range(3):", out)
        self.assertIn("print(i)", out)

    def test_transpiler_handles_full_vocabulary(self):
        src = "attempt:\n    signal ValueError\ndropped ValueError:\n    leave\nstumps:\n    leave\n"
        out = transpile(src, "cricket")
        compile(out, "<t>", "exec")
        self.assertIn("try:", out)
        self.assertIn("raise ValueError", out)

    def test_source_directive_picks_flavour(self):
        self.assertIn("print(1)", transpile("# flavour: banglish\ndekhao(1)\n"))

    def test_bad_flavour_name(self):
        with self.assertRaises(FlavourError):
            transpile("x = 1\n", "not-a-flavour")


if __name__ == "__main__":
    unittest.main()
