#!/usr/bin/env python3
"""Maintainer tool: sync iredis/data/commands.json from the redis/docs repo.

The upstream data file ``data/commands_core.json`` in
https://github.com/redis/docs shares the exact same structure as
iredis/data/commands.json, so entries can be merged verbatim.

Usage:

    # show new/removed/changed commands compared to the local file (read only)
    python scripts/update_commands_json.py --diff

    # merge the given commands from upstream into the local file
    python scripts/update_commands_json.py --merge HEXPIRE,HTTL

    # pin the upstream version with a branch/tag/commit sha
    python scripts/update_commands_json.py --ref <sha> --diff

We merge with an explicit allowlist instead of overwriting the whole file:
the upstream main branch contains unreleased commands, and every entry in
commands.json must ship a hand-written help document under
iredis/data/commands/ (guarded by tests/unittests/test_data_consistency.py).
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

UPSTREAM_URL = (
    "https://raw.githubusercontent.com/redis/docs/{ref}/data/commands_core.json"
)
LOCAL_PATH = Path(__file__).parent.parent / "iredis" / "data" / "commands.json"


def load_upstream(ref):
    url = UPSTREAM_URL.format(ref=ref)
    print(f"Downloading {url} ...", file=sys.stderr)
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_local():
    return json.loads(LOCAL_PATH.read_text(encoding="utf-8"))


def dump_local(data):
    # match the existing serialization so an empty merge produces zero diff:
    # top-level keys sorted, nested keys keep the upstream order
    ordered = {name: data[name] for name in sorted(data)}
    text = json.dumps(ordered, indent=4, ensure_ascii=False)
    LOCAL_PATH.write_text(text + "\n", encoding="utf-8")


def show_diff(upstream, local):
    added = sorted(set(upstream) - set(local))
    removed = sorted(set(local) - set(upstream))
    changed = sorted(
        name for name in set(upstream) & set(local) if upstream[name] != local[name]
    )
    print(f"upstream only ({len(added)}):")
    for name in added:
        since = upstream[name].get("since", "?")
        print(f"  {name} (since {since})")
    print(f"local only ({len(removed)}):")
    for name in removed:
        print(f"  {name}")
    print(f"changed ({len(changed)}):")
    for name in changed:
        print(f"  {name}")


def merge(upstream, local, names):
    missing = [name for name in names if name not in upstream]
    if missing:
        sys.exit(f"not found in upstream: {', '.join(missing)}")
    for name in names:
        local[name] = upstream[name]
    dump_local(local)
    print(f"merged {len(names)} command(s) into {LOCAL_PATH}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="main", help="redis/docs git ref")
    parser.add_argument("--diff", action="store_true", help="show diff only")
    parser.add_argument("--merge", help="comma-separated command names to merge")
    args = parser.parse_args()

    upstream = load_upstream(args.ref)
    local = load_local()

    if args.merge is not None:
        names = [n.strip().upper() for n in args.merge.split(",") if n.strip()]
        merge(upstream, local, names)
    else:
        show_diff(upstream, local)


if __name__ == "__main__":
    main()
