"""Every example must give identical output on the PVM and as transpiled Python."""
import contextlib
import io
import os
import unittest
from pathlib import Path
from unittest import mock

from pitchvm import run_source, transpile

ROOT = Path(__file__).resolve().parent
EXPECTED = {
    "scorecard": "Matches played: 6\nTotal runs: 269\nAverage: 44.83\nHighest score: 101\n"
                 "Lowest score: 0\n0 -> duck\n12 -> keep going\n33 -> keep going\n"
                 "45 -> keep going\n78 -> half century\n101 -> century!\n",
    "run_rate": "Run rate: 7.5\nRun rate (10 overs): 8.0\nRequired rate: 10.0\nNo overs left: None\n",
    "chase": "Over 1 -> 14\nOver 2 -> 28\nOver 3 -> 33\nTarget chased in 3 overs\n",
    "primes": "Primes: [2, 3, 5, 7, 11, 13, 17, 19, 23, 29]\nCount: 10\n",
    "campus_marks": "Students: 5\nTopper: 91\nBackbencher: 58\nClass average: 74.4\n"
                    "58 needs revision\nGrade A students: 2\n",
}


@mock.patch.dict(os.environ, {"PITCH_FLAVOURS": str(ROOT / "flavours")})
class ExampleTests(unittest.TestCase):
    def run_both(self, path):
        source = path.read_text(encoding="utf-8")
        vm_out = io.StringIO()
        run_source(source, stdout=vm_out)
        py_out = io.StringIO()
        with contextlib.redirect_stdout(py_out):
            exec(compile(transpile(source), str(path), "exec"), {"__name__": "__main__"})
        return vm_out.getvalue(), py_out.getvalue()

    def test_every_example_matches_in_both_modes(self):
        files = sorted((ROOT / "examples").glob("*.pitch"))
        self.assertGreaterEqual(len(files), 8)
        for path in files:
            with self.subTest(example=path.name):
                vm_text, py_text = self.run_both(path)
                self.assertTrue(vm_text)
                self.assertEqual(vm_text, py_text)

    def test_known_outputs(self):
        for name, expected in EXPECTED.items():
            with self.subTest(example=name):
                vm_text, _ = self.run_both(ROOT / "examples" / (name + ".pitch"))
                self.assertEqual(vm_text, expected)


if __name__ == "__main__":
    unittest.main()
