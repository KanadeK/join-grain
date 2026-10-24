# join-grain

Predict CSV join size **before a duplicate key expands the result**. Reads two
exports into a temporary disk-backed key index, computes exact inner/left/right/
full equality-join row counts, and checks your expected relationship. No joined
rows are allocated. Reports contain aggregate counts, never keys or cell values.

Python 3.11+, standard library only. [中文说明](README.zh-CN.md).

## Install and try

Install from source; this project is not published on PyPI:

```console
git clone https://github.com/KanadeK/join-grain.git
cd join-grain
python -m venv .venv
```

Activate with `.venv\Scripts\activate` on Windows or `source .venv/bin/activate`
on macOS/Linux, then:

```console
python -m pip install .
join-grain examples/orders.csv examples/customers.csv --left-key customer_id --left-key region
```

This synthetic example intentionally exits **1**: the customer lookup repeats
`(A,north)`. The report predicts **4 inner, 6 left, 5 right, 7 full rows** from
4 orders and 3 customer records. Two order rows would be duplicated. Fix the
lookup or deliberately declare `--expect many-to-many` to accept multiplicity.

```console
python -m join_grain orders.csv customers.csv --left-key customer_id --right-key id --require-match left --max-output-rows 100000
join-grain left.csv right.csv --left-key account --left-key region --how full --expect one-to-one
join-grain left.csv right.csv --left-key id --delimiter ";" --null-value NULL --temp-dir private-scratch
```

The scratch parent must exist. JSON is written to stdout; input errors go to
stderr. Exit **0** means policy passed, **1** a completed forecast failed policy,
**2** invalid input/options or I/O failure, **130** interruption. Redirecting stdout
is your shell's responsibility; do not redirect over an input file.

## Counting and policy

For a matched key appearing `L` times on the left and `R` times on the right,
the inner join has `L*R` rows. A left/right join adds unmatched rows from that
side; a full join adds both. Empty key components are NULL and never match,
including another NULL. `--null-value` adds tokens; it does not remove blank NULLs.

Keys use exact text: `001`, `1`, `1 ` and different Unicode spellings differ.
No type inference, trimming, case folding or delimiter sniffing. Repeat key flags
in corresponding order for composite keys. Both files use the same delimiter.
Duplicate or blank headers, unknown key columns, ragged/blank records, malformed
quoting and invalid UTF-8 stop the run. UTF-8 BOM, CRLF and quoted newlines work.

`--expect` defaults to `many-to-one`; uniqueness is checked over **all non-NULL
keys**, even unmatched keys. NULL-key rows are excluded from uniqueness checks
and included in unmatched counts. `--require-match` can require `left`, `right`,
`both` or `none` (default). `--how` chooses which predicted count is checked by
`--max-output-rows`; all four counts are always reported. Many-to-many is an
explicitly allowed relationship, not an automatic failure. There is no monetary
reconciliation, SQL execution or row export.

## Resources and privacy

SQLite's page cache is configured to 8 MiB; Python holds the current CSV record
and query row rather than all distinct keys. This is not a hard process-RAM cap:
CSV parsing and SQLite need additional memory. Temporary disk grows with distinct
keys and may fill. Defaults allow 10 million records **per input** and 1 MiB
characters per field; flags change those limits (field maximum 64 MiB characters).
Runtime is approximately proportional to records times index lookup cost; no
cross-product is materialized. See [verification](docs/VERIFICATION.md).

**Raw keys are stored in the temporary database.** Choose private, appropriately
encrypted scratch storage for sensitive data. Reports omit filenames, headers,
keys, row bodies and key hashes, but counts can still be sensitive. Source exports
are not modified. Normal completion, input errors and handled interrupts clean
the scratch directory; a crash or forced termination can leave `join-grain-*`
directories. Remove only remnants of stopped processes. Cleanup is not secure
erasure. Stable exports are required: detected metadata changes fail the run,
but this is not a transactional snapshot against hostile writers.

The library temporarily changes Python's process-global CSV field limit under
its own lock and restores it. Unrelated CSV readers in other threads do not share
that lock; use separate processes when combining them. No runtime network calls.

## Alternatives and development

[pandas.merge](https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.merge.html)
provides relationship validation within Python;
[csvkit](https://github.com/wireservice/csvkit) and
[qsv](https://github.com/dathere/qsv) offer broad CSV operations.
[JoinWitness](https://github.com/loaff123/joinwitness) already provides join
preflight with amount analysis and offline HTML reports, using in-memory key
aggregates. Use it for that workflow. join-grain addresses the narrower case of
disk-backed key aggregation, aggregate-only CI output and all four join counts.
No competitor implementation is copied.

```console
python -m pip install -e . -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m unittest discover -s tests -v
python -m build
python tools/smoke.py
python tools/benchmark.py --rows 100000
```

Uninstall with `python -m pip uninstall join-grain`; remove your virtual environment,
checkout, `build/`, `dist/` and saved reports when no longer needed. Examples and
tests clean their temporary data. [MIT](LICENSE). Version **0.1.0**. See
[contribution](CONTRIBUTING.md), [security](SECURITY.md) and
[dependency licenses](THIRD_PARTY.md).
