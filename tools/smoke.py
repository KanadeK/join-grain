"""Install both distribution formats into clean venvs and run the documented flow."""

import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def checked(command, **kwargs):
    result = subprocess.run(command, capture_output=True, text=True, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stderr)
    return result


def main():
    with tempfile.TemporaryDirectory(prefix="join-grain-smoke-") as directory:
        scratch = Path(directory)
        for suffix in ("*.whl", "*.tar.gz"):
            (artifact,) = (ROOT / "dist").glob(suffix)
            environment = scratch / ("wheel" if suffix == "*.whl" else "sdist")
            venv.EnvBuilder(with_pip=True).create(environment)
            binaries = environment / ("Scripts" if os.name == "nt" else "bin")
            python = binaries / ("python.exe" if os.name == "nt" else "python")
            executable = binaries / ("join-grain.exe" if os.name == "nt" else "join-grain")
            checked(
                [str(python), "-m", "pip", "install", "--disable-pip-version-check", str(artifact)],
                cwd=scratch,
            )
            checked([str(executable), "--version"], cwd=scratch)
            command = [
                str(executable),
                str(ROOT / "examples/orders.csv"),
                str(ROOT / "examples/customers.csv"),
                "--left-key",
                "customer_id",
                "--left-key",
                "region",
            ]
            failed = subprocess.run(command, capture_output=True, text=True, cwd=scratch)
            assert failed.returncode == 1, failed.stderr
            report = json.loads(failed.stdout)
            assert report["predicted_rows"] == {"inner": 4, "left": 6, "right": 5, "full": 7}
            passed = checked([*command, "--expect", "many-to-many"], cwd=scratch)
            assert json.loads(passed.stdout)["ok"]
            checked([str(python), "-m", "pip", "uninstall", "-y", "join-grain"], cwd=scratch)
            print(f"PASS {artifact.name}: isolated install, CLI policies, uninstall")


if __name__ == "__main__":
    main()
