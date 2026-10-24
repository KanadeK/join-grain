"""Exact equality-join forecasts without materializing joined rows."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

_CSV_LOCK = threading.RLock()
RELATIONSHIPS = ("one-to-one", "one-to-many", "many-to-one", "many-to-many")
JOINS = ("inner", "left", "right", "full")


class InputError(ValueError):
    """Invalid input, with a message that contains no CSV cell values."""


def _signature(info: os.stat_result) -> tuple:
    # Windows fstat() and stat() can disagree about creation time (st_ctime).
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _load(
    db: sqlite3.Connection,
    table: str,
    path: Path,
    keys: tuple[str, ...],
    delimiter: str,
    nulls: frozenset[str],
    max_rows: int,
) -> dict:
    # table comes only from fixed internal literals, never from a header or flag.
    db.execute(f"CREATE TABLE {table}(k BLOB PRIMARY KEY,n INTEGER NOT NULL) WITHOUT ROWID")
    rows = null_rows = 0
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        before = _signature(os.fstat(stream.fileno()))
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise InputError(f"{table}: missing CSV header") from exc
        if not header or any(not cell.strip() for cell in header):
            raise InputError(f"{table}: empty column name")
        if len(set(header)) != len(header):
            raise InputError(f"{table}: duplicate column name")
        if not set(keys).issubset(header):
            raise InputError(f"{table}: requested key column is absent")
        positions = [header.index(key) for key in keys]
        statement = f"INSERT INTO {table}(k,n) VALUES(?,1) ON CONFLICT(k) DO UPDATE SET n=n+1"
        for record, values in enumerate(reader, 2):
            rows += 1
            if rows > max_rows:
                raise InputError(f"{table}: row limit exceeded")
            if len(values) != len(header):
                raise InputError(f"{table}: wrong field count in record {record}")
            key = tuple(values[index] for index in positions)
            if any(value in nulls for value in key):
                null_rows += 1
                continue
            # Length-delimited JSON arrays avoid composite-key separator collisions.
            encoded = json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            db.execute(statement, (encoded,))
        if before != _signature(os.fstat(stream.fileno())) or before != _signature(path.stat()):
            raise InputError(f"{table}: input changed during reading")
    unique, duplicate_keys, duplicate_rows, maximum = db.execute(
        f"SELECT COUNT(*), COALESCE(SUM(n>1),0), "
        f"COALESCE(SUM(CASE WHEN n>1 THEN n ELSE 0 END),0), COALESCE(MAX(n),0) FROM {table}"
    ).fetchone()
    return {
        "rows": rows,
        "null_key_rows": null_rows,
        "distinct_nonnull_keys": unique,
        "duplicate_nonnull_keys": duplicate_keys,
        "rows_in_duplicate_nonnull_keys": duplicate_rows,
        "maximum_multiplicity": maximum,
    }


def audit(
    left: str | Path,
    right: str | Path,
    *,
    left_keys: tuple[str, ...],
    right_keys: tuple[str, ...] | None = None,
    expect: str = "many-to-one",
    how: str = "left",
    require_match: str = "none",
    max_output_rows: int | None = None,
    delimiter: str = ",",
    null_values: tuple[str, ...] = ("",),
    temp_dir: str | Path | None = None,
    max_rows: int = 10_000_000,
    max_field_chars: int = 1_048_576,
) -> dict:
    """Read two stable CSV exports and return aggregate counts and policy violations.

    Keys are exact Unicode text. Any configured NULL component never matches.
    Temporary SQLite stores raw non-NULL keys; reports never include those keys.
    """
    right_keys = right_keys if right_keys is not None else left_keys
    if (
        not left_keys
        or not right_keys
        or len(left_keys) != len(right_keys)
        or len(set(left_keys)) != len(left_keys)
        or len(set(right_keys)) != len(right_keys)
        or any(not isinstance(k, str) or not k for k in (*left_keys, *right_keys))
    ):
        raise InputError("provide equally sized, nonempty, distinct key-column lists")
    if (
        expect not in RELATIONSHIPS
        or how not in JOINS
        or require_match not in ("none", "left", "right", "both")
    ):
        raise InputError("unknown policy")
    if len(delimiter) != 1 or delimiter in '\r\n\x00"':
        raise InputError("delimiter must be one character other than quote, NUL or newline")
    if max_rows < 1 or not 1 <= max_field_chars <= 64 * 1024 * 1024:
        raise InputError("invalid resource limit")
    if max_output_rows is not None and max_output_rows < 0:
        raise InputError("output row limit must be nonnegative")
    if any(not isinstance(value, str) for value in null_values):
        raise InputError("NULL tokens must be strings")
    with _CSV_LOCK:
        previous_limit = csv.field_size_limit()
        try:
            csv.field_size_limit(max_field_chars)
            with tempfile.TemporaryDirectory(prefix="join-grain-", dir=temp_dir) as scratch:
                db = sqlite3.connect(Path(scratch) / "keys.sqlite3")
                try:
                    db.execute("PRAGMA cache_size=-8192")
                    db.execute("PRAGMA temp_store=FILE")
                    db.execute("PRAGMA journal_mode=OFF")
                    db.execute("PRAGMA synchronous=OFF")
                    snapshots = [(Path(p), _signature(Path(p).stat())) for p in (left, right)]
                    profiles = {}
                    for side, path, keys in (
                        ("left_input", left, left_keys),
                        ("right_input", right, right_keys),
                    ):
                        try:
                            profiles[side] = _load(
                                db,
                                side,
                                Path(path),
                                tuple(keys),
                                delimiter,
                                frozenset(null_values),
                                max_rows,
                            )
                        except UnicodeError as exc:
                            raise InputError(f"{side}: invalid UTF-8") from exc
                        except csv.Error as exc:
                            raise InputError(
                                f"{side}: malformed CSV or field limit exceeded"
                            ) from exc
                    if any(before != _signature(path.stat()) for path, before in snapshots):
                        raise InputError("input changed during audit")
                    matched_left = matched_right = inner = many_many_keys = 0
                    repeated_left = repeated_right = 0
                    for lcount, rcount in db.execute(
                        "SELECT l.n,r.n FROM left_input l JOIN right_input r USING(k)"
                    ):
                        matched_left += lcount
                        matched_right += rcount
                        inner += lcount * rcount
                        repeated_left += lcount * (rcount - 1)
                        repeated_right += rcount * (lcount - 1)
                        many_many_keys += int(lcount > 1 and rcount > 1)
                    lp, rp = profiles["left_input"], profiles["right_input"]
                    unmatched_left = lp["rows"] - matched_left
                    unmatched_right = rp["rows"] - matched_right
                    predictions = {
                        "inner": inner,
                        "left": inner + unmatched_left,
                        "right": inner + unmatched_right,
                        "full": inner + unmatched_left + unmatched_right,
                    }
                    violations = []
                    if expect in ("one-to-one", "one-to-many") and lp["duplicate_nonnull_keys"]:
                        violations.append("left_keys_not_unique")
                    if expect in ("one-to-one", "many-to-one") and rp["duplicate_nonnull_keys"]:
                        violations.append("right_keys_not_unique")
                    if require_match in ("left", "both") and unmatched_left:
                        violations.append("unmatched_left_rows")
                    if require_match in ("right", "both") and unmatched_right:
                        violations.append("unmatched_right_rows")
                    if max_output_rows is not None and predictions[how] > max_output_rows:
                        violations.append("output_row_limit_exceeded")
                    return {
                        "schema_version": 1,
                        "ok": not violations,
                        "policy": {
                            "expect": expect,
                            "how": how,
                            "require_match": require_match,
                            "max_output_rows": max_output_rows,
                        },
                        "left": lp,
                        "right": rp,
                        "matched_left_rows": matched_left,
                        "matched_right_rows": matched_right,
                        "unmatched_left_rows": unmatched_left,
                        "unmatched_right_rows": unmatched_right,
                        "predicted_rows": predictions,
                        "extra_copies_of_matched_left_rows": repeated_left,
                        "extra_copies_of_matched_right_rows": repeated_right,
                        "many_to_many_matching_keys": many_many_keys,
                        "violations": violations,
                    }
                finally:
                    db.close()
        finally:
            csv.field_size_limit(previous_limit)
