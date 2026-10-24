"""Command-line entry point."""

import argparse
import json
import sqlite3
import sys

from . import __version__
from .core import JOINS, RELATIONSHIPS, InputError, audit


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Forecast CSV join rows using a temporary disk index."
    )
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument(
        "--left-key", action="append", required=True, help="repeat for composite keys"
    )
    parser.add_argument("--right-key", action="append", help="defaults to the left column names")
    parser.add_argument("--expect", choices=RELATIONSHIPS, default="many-to-one")
    parser.add_argument("--how", choices=JOINS, default="left")
    parser.add_argument(
        "--require-match", choices=("none", "left", "right", "both"), default="none"
    )
    parser.add_argument("--max-output-rows", type=int)
    parser.add_argument("--delimiter", default=",")
    parser.add_argument(
        "--null-value", action="append", help="adds an exact NULL token; blank stays NULL"
    )
    parser.add_argument(
        "--temp-dir", help="private scratch parent; contains raw key data during audit"
    )
    parser.add_argument("--max-rows", type=int, default=10_000_000, help="per input")
    parser.add_argument("--max-field-chars", type=int, default=1_048_576)
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        report = audit(
            args.left,
            args.right,
            left_keys=tuple(args.left_key),
            right_keys=tuple(args.right_key) if args.right_key is not None else None,
            expect=args.expect,
            how=args.how,
            require_match=args.require_match,
            max_output_rows=args.max_output_rows,
            delimiter=args.delimiter,
            null_values=("", *(args.null_value or [])),
            temp_dir=args.temp_dir,
            max_rows=args.max_rows,
            max_field_chars=args.max_field_chars,
        )
    except InputError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    except (OSError, sqlite3.Error, OverflowError):
        print(json.dumps({"ok": False, "error": "input or scratch I/O failed"}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0 if report["ok"] else 1
