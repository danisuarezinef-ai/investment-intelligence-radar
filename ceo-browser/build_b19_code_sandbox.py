from __future__ import annotations

import argparse
import json
import os
import subprocess
import uuid
from pathlib import Path


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )


def build_sandbox(root: str | Path) -> Path:
    root = Path(root).expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(f"sandbox path is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)

    git(root, "init")
    git(root, "config", "user.email", "ceo-sandbox@example.invalid")
    git(root, "config", "user.name", "CEO Sandbox")

    (root / "calc.py").write_text(
        "def add(a, b):\n"
        "    return a - b\n",
        encoding="utf-8",
    )
    (root / "test_calc.py").write_text(
        "import unittest\n"
        "from calc import add\n\n"
        "class TestCalc(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )
    marker = {
        "schema_version": 1,
        "phase": "B19",
        "sandbox": True,
        "production": False,
        "real_trading": False,
        "purpose": "B20 free browser coding gate",
    }
    (root / "CEO_B19_SANDBOX.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    git(root, "add", ".")
    git(root, "commit", "-m", "B19 baseline with intentional bug")
    return root


def main() -> int:
    parser = argparse.ArgumentParser()
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    default = local / "CEO de IAs" / "sandboxes" / f"b20-{uuid.uuid4().hex[:10]}"
    parser.add_argument("--root", default=str(default))
    args = parser.parse_args()
    root = build_sandbox(args.root)
    print(str(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
