# Verification — 0.1.0

Local checks executed 2026-10-24 on Windows, Python 3.13.16 and SQLite bundled
with that interpreter. Results describe those executed checks, not a proof of
all inputs or a claim of universal capacity.

- 21 unittest tests passed, including 120 seeded random two-table comparisons
  against independently materialized nested-loop joins.
- Six-million-row join forecast tested from 2,000 and 3,000 repeated inputs;
  the cross-product was not materialized by the implementation.
- Composite key separator/newline cases, exact text/NULL behavior, all four join
  types, empty tables, invalid CSV/encoding/options, limits and CLI exits checked.
- Source immutability and report redaction checked with synthetic sentinel data.
  Scratch cleanup checked after successful runs, parse/limit errors and interrupts.
- A left export changed during the right scan fails rather than returning stale
  counts. This is metadata-based detection, not a transactional snapshot.
- Coverage.py measured 98% statement coverage locally; subprocess CLI tests also
  execute the module entry point, outside the parent coverage session.
- Ruff lint and formatting checks passed. Both source archive and wheel were
  built. Each distribution was installed in a separate clean venv outside the
  checkout; documented CLI counts/policy exits and uninstall passed for both.
- Synthetic benchmark, 100,000 distinct keys per side: correct one-to-one counts,
  3.860 seconds with tracemalloc enabled, peak traced Python allocation 170,853
  bytes. This excludes SQLite C allocations, OS page cache and interpreter RSS.
  It is a single-machine observation, not a capacity or total-RAM guarantee.

Review found Windows `stat()`/`fstat()` creation-time differences could falsely
report changes. The comparison now uses device/inode/size/modification time;
the randomized and empty-table cases pass on Windows. Source validation is
rechecked after both scans to catch changes to the earlier input.

No runtime dependency was introduced. No upstream implementation or third-party
test fixture was copied. CI targets Linux, macOS and Windows on Python 3.11,
3.13 and 3.14; inspect the repository's Actions run for actual remote results.
