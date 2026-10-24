# Contributing

Discuss bugs or proposed changes in an issue first; include a minimal synthetic
reproduction, expected/actual behavior and Python/OS versions. Never upload real
private inputs. Suggestions and reports are welcome. This repository's maintainer
implements accepted changes; third-party commits are not automatically merged.

Use Python 3.11+ and an isolated virtual environment:

```console
python -m pip install -e . -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m coverage run -m unittest discover -s tests -v
python -m coverage report
python -m build
python tools/smoke.py
```

Tests include independent oracles, CLI failures and boundary cases. Add tests for
behavior changes; keep limits, error codes and documentation consistent. CI runs
checks only, with read-only permissions. All release commits use the maintainer's
GitHub identity without additional contribution trailers or automated commits.
