#!/usr/bin/env python3
"""Copy _lib/kvmkit into every App that imports it.

Apps install as self-contained ZIPs, so each one carries its own copy of the
shared library in <app>/kvmkit/. Edit only _lib/kvmkit/, then run:

    python3 _utils/sync-kvmkit.py          # update the copies
    python3 _utils/sync-kvmkit.py --check  # exit 1 if any copy is stale
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MASTER = ROOT / "_lib" / "kvmkit"
HEADER = "# Generated from _lib/kvmkit/{name} by _utils/sync-kvmkit.py. Edit the master copy.\n"
IMPORT = re.compile(r"^\s*(from\s+kvmkit[\s.]|import\s+kvmkit\b)", re.MULTILINE)


def apps_using_kvmkit():
    apps = []
    for app in sorted(ROOT.iterdir()):
        if not app.is_dir() or app.name.startswith((".", "_")) or not (app / "app.json").is_file():
            continue
        sources = [path for path in app.rglob("*.py") if "kvmkit" not in path.relative_to(app).parts]
        if any(IMPORT.search(path.read_text(encoding="utf-8")) for path in sources):
            apps.append(app)
    return apps


def expected_files():
    return {path.name: HEADER.format(name=path.name) + path.read_text(encoding="utf-8")
            for path in sorted(MASTER.glob("*.py"))}


def sync(check):
    expected = expected_files()
    stale = []
    for app in apps_using_kvmkit():
        target = app / "kvmkit"
        current = {path.name: path for path in target.glob("*.py")} if target.is_dir() else {}
        for name, content in expected.items():
            path = target / name
            if not path.is_file() or path.read_text(encoding="utf-8") != content:
                stale.append(path)
                if not check:
                    target.mkdir(exist_ok=True)
                    path.write_text(content, encoding="utf-8")
        for name, path in current.items():
            if name not in expected:
                stale.append(path)
                if not check:
                    path.unlink()
    return stale


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="report stale copies without changing them")
    args = parser.parse_args(argv)
    stale = sync(args.check)
    for path in stale:
        print(("stale: " if args.check else "updated: ") + str(path.relative_to(ROOT)))
    if args.check and stale:
        print("Run python3 _utils/sync-kvmkit.py to update the copies.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
