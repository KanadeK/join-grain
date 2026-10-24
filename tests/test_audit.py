import csv
import io
import json
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from join_grain import core
from join_grain.cli import main
from join_grain.core import InputError, audit


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.left = self.root / "left.csv"
        self.right = self.root / "right.csv"

    def write(self, path, rows):
        with path.open("w", encoding="utf-8", newline="") as stream:
            csv.writer(stream).writerows(rows)

    def run_audit(self, **kwargs):
        return audit(self.left, self.right, left_keys=("id",), **kwargs)

    def test_all_four_join_predictions(self):
        self.write(self.left, [["id"], ["a"], ["a"], ["b"], [""]])
        self.write(self.right, [["id"], ["a"], ["a"], ["a"], ["c"], [""]])
        report = self.run_audit()
        self.assertEqual(report["predicted_rows"], {"inner": 6, "left": 8, "right": 8, "full": 10})
        self.assertEqual(report["extra_copies_of_matched_left_rows"], 4)
        self.assertEqual(report["extra_copies_of_matched_right_rows"], 3)
        self.assertEqual(report["many_to_many_matching_keys"], 1)
        self.assertEqual(report["left"]["rows_in_duplicate_nonnull_keys"], 2)
        self.assertEqual(report["violations"], ["right_keys_not_unique"])

    def test_randomized_against_materialized_nested_loop_join(self):
        rng = random.Random(719)
        for _ in range(120):
            left = [rng.choice(["", "a", "b", "001", "1", "é"]) for _ in range(rng.randrange(18))]
            right = [rng.choice(["", "a", "c", "001", "1", "é"]) for _ in range(rng.randrange(18))]
            self.write(self.left, [["id"], *[[v] for v in left]])
            self.write(self.right, [["id"], *[[v] for v in right]])
            pairs = [
                (i, j) for i, a in enumerate(left) for j, b in enumerate(right) if a and a == b
            ]
            unleft = sum(not any(i == p[0] for p in pairs) for i in range(len(left)))
            unright = sum(not any(j == p[1] for p in pairs) for j in range(len(right)))
            report = self.run_audit(expect="many-to-many")
            self.assertEqual(
                report["predicted_rows"],
                {
                    "inner": len(pairs),
                    "left": len(pairs) + unleft,
                    "right": len(pairs) + unright,
                    "full": len(pairs) + unleft + unright,
                },
            )

    def test_composite_keys_are_unambiguous(self):
        self.write(self.left, [["a", "b"], ["a|b", "c"], ["a", "b|c"], ["x\ny", '"z']])
        self.write(self.right, [["a", "b"], ["a", "b|c"], ["x\ny", '"z']])
        report = audit(self.left, self.right, left_keys=("a", "b"))
        self.assertEqual(report["predicted_rows"]["inner"], 2)

    def test_key_names_may_differ(self):
        self.write(self.left, [["id"], ["001"]])
        self.write(self.right, [["customer"], ["001"]])
        self.assertTrue(self.run_audit(right_keys=("customer",))["ok"])

    def test_exact_text_and_custom_nulls(self):
        self.write(self.left, [["id"], ["001"], ["1 "], ["NULL"], [""]])
        self.write(self.right, [["id"], ["1"], ["NULL"], [""]])
        self.assertEqual(self.run_audit()["predicted_rows"]["inner"], 1)
        self.assertEqual(self.run_audit(null_values=("", "NULL"))["predicted_rows"]["inner"], 0)

    def test_null_component_never_matches(self):
        self.write(self.left, [["a", "b"], ["x", ""], ["x", ""]])
        self.write(self.right, [["a", "b"], ["x", ""]])
        report = audit(self.left, self.right, left_keys=("a", "b"), expect="one-to-one")
        self.assertTrue(report["ok"])
        self.assertEqual(report["predicted_rows"]["full"], 3)

    def test_empty_tables(self):
        for path in (self.left, self.right):
            self.write(path, [["id"]])
        report = self.run_audit(require_match="both", max_output_rows=0)
        self.assertTrue(report["ok"])
        self.assertEqual(report["predicted_rows"]["full"], 0)

    def test_policy_limits_and_uniqueness_are_global(self):
        self.write(self.left, [["id"], ["a"], ["a"]])
        self.write(self.right, [["id"], ["z"], ["z"]])
        report = self.run_audit(
            expect="one-to-one", require_match="both", how="full", max_output_rows=3
        )
        self.assertEqual(
            set(report["violations"]),
            {
                "left_keys_not_unique",
                "right_keys_not_unique",
                "unmatched_left_rows",
                "unmatched_right_rows",
                "output_row_limit_exceeded",
            },
        )

    def test_boundary_row_limit_and_cleanup(self):
        self.write(self.left, [["id"], ["a"], ["b"]])
        self.write(self.right, [["id"], ["a"]])
        scratch = self.root / "scratch"
        scratch.mkdir()
        self.assertTrue(self.run_audit(max_rows=2, temp_dir=scratch)["ok"])
        with self.assertRaises(InputError):
            self.run_audit(max_rows=1, temp_dir=scratch)
        self.assertEqual(list(scratch.iterdir()), [])

    def test_field_limit_restored_after_error(self):
        self.write(self.left, [["id"], ["sensitive-value"]])
        self.write(self.right, [["id"]])
        before = csv.field_size_limit()
        with self.assertRaises(InputError) as caught:
            self.run_audit(max_field_chars=4)
        self.assertEqual(csv.field_size_limit(), before)
        self.assertNotIn("sensitive-value", str(caught.exception))

    def test_bom_crlf_and_semicolon(self):
        self.left.write_bytes(b'\xef\xbb\xbfid;value\r\na;"two\r\nlines"\r\n')
        self.right.write_bytes(b"id;value\r\na;right\r\n")
        self.assertEqual(self.run_audit(delimiter=";")["predicted_rows"]["inner"], 1)

    def test_invalid_csv_inputs(self):
        self.write(self.right, [["id"]])
        for text in (
            "",
            "id,id\na,b\n",
            "id, \na,b\n",
            "x\na\n",
            'id\n"unterminated',
            "id,x\na\n",
            "id\na,b\n",
            "id\n\n",
        ):
            with self.subTest(text=text):
                self.left.write_text(text)
                with self.assertRaises(InputError):
                    self.run_audit()

    def test_invalid_encoding(self):
        self.left.write_bytes(b"id\n\xff\n")
        self.write(self.right, [["id"]])
        with self.assertRaisesRegex(InputError, "invalid UTF-8"):
            self.run_audit()

    def test_invalid_api_options(self):
        for options in (
            {"right_keys": ()},
            {"right_keys": ("id", "id")},
            {"max_rows": 0},
            {"delimiter": "\n"},
            {"delimiter": '"'},
            {"delimiter": "::"},
            {"expect": "invalid"},
            {"max_output_rows": -1},
            {"null_values": (None,)},
            {"max_field_chars": 0},
            {"how": "cross"},
            {"require_match": "all"},
        ):
            with self.subTest(options=options), self.assertRaises(InputError):
                self.run_audit(**options)

    def test_large_multiplicity_without_cartesian_materialization(self):
        self.write(self.left, [["id"], *[["a"] for _ in range(2000)]])
        self.write(self.right, [["id"], *[["a"] for _ in range(3000)]])
        self.assertEqual(
            self.run_audit(expect="many-to-many")["predicted_rows"]["inner"], 6_000_000
        )

    def test_source_bytes_unchanged_and_output_redacted(self):
        self.write(self.left, [["id", "private_column"], ["TOP-SECRET", "private-body"]])
        self.write(self.right, [["id"], ["TOP-SECRET"]])
        before = self.left.read_bytes(), self.right.read_bytes()
        output = json.dumps(self.run_audit())
        self.assertEqual(before, (self.left.read_bytes(), self.right.read_bytes()))
        for value in ("TOP-SECRET", "private-body", "private_column", str(self.root)):
            self.assertNotIn(value, output)

    def test_cli_exit_codes_and_json(self):
        self.write(self.left, [["id"], ["x"]])
        self.write(self.right, [["id"], ["x"], ["x"]])
        command = [
            sys.executable,
            "-m",
            "join_grain",
            str(self.left),
            str(self.right),
            "--left-key",
            "id",
        ]
        failed = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 1, failed.stderr)
        self.assertEqual(json.loads(failed.stdout)["predicted_rows"]["left"], 2)
        passed = subprocess.run(
            [*command, "--expect", "many-to-many"], capture_output=True, text=True
        )
        self.assertEqual(passed.returncode, 0, passed.stderr)
        self.left.write_text('id\n"private-data')
        invalid = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertEqual(invalid.stdout, "")
        self.assertNotIn("private-data", invalid.stderr)

    def test_cli_missing_file_and_version(self):
        command = [sys.executable, "-m", "join_grain"]
        result = subprocess.run(
            [*command, str(self.left), str(self.right), "--left-key", "id"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("I/O", result.stderr)
        version = subprocess.run([*command, "--version"], capture_output=True, text=True)
        self.assertEqual(version.stdout.strip(), "0.1.0")

    def test_change_to_left_while_reading_right_is_detected(self):
        self.write(self.left, [["id"], ["a"]])
        self.write(self.right, [["id"], ["a"]])
        original = core._load

        def changing_load(*args, **kwargs):
            profile = original(*args, **kwargs)
            if args[1] == "right_input":
                self.left.write_text("id\na\nnew-record\n")
            return profile

        with patch.object(core, "_load", side_effect=changing_load):
            with self.assertRaisesRegex(InputError, "changed"):
                self.run_audit()

    def test_cleanup_on_interrupt(self):
        self.write(self.left, [["id"]])
        self.write(self.right, [["id"]])
        scratch = self.root / "scratch"
        scratch.mkdir()
        with patch.object(core, "_load", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_audit(temp_dir=scratch)
        self.assertEqual(list(scratch.iterdir()), [])

    def test_cli_direct_returns_and_redacted_errors(self):
        self.write(self.left, [["id"], ["a"]])
        self.write(self.right, [["id"], ["a"]])
        args = [str(self.left), str(self.right), "--left-key", "id"]
        with redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(args), 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])
        with redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main([*args, "--max-rows", "0"]), 2)
        self.assertIn("resource limit", err.getvalue())
        with patch("join_grain.cli.audit", side_effect=OSError("secret path")):
            with redirect_stderr(io.StringIO()) as err:
                self.assertEqual(main(args), 2)
            self.assertNotIn("secret path", err.getvalue())
        with patch("join_grain.cli.audit", side_effect=KeyboardInterrupt):
            self.assertEqual(main(args), 130)


if __name__ == "__main__":
    unittest.main()
