# Third-party materials

## Runtime dependencies

None. Runtime uses the Python standard library only.

## Development and CI

Setuptools (MIT), build (MIT), Ruff (MIT), coverage.py (Apache-2.0), and their
transitive packaging/build helpers are development tools, not vendored source.
GitHub actions checkout/setup-python/upload-artifact are MIT-licensed services
referenced by commit SHA. Their source is not included here. Python itself is
distributed under the PSF license. These uses are compatible with MIT source.

Examples and test fixtures in this repository are synthetic and authored for
this project. No competitor code, third-party test suite, media or transcript
has been copied. README comparisons cite their original projects.
