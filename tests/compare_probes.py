"""Compare two probe_behaviour.py outputs and print every difference.

    python3 tests/compare_probes.py old.json new.json
Exit code 0 when identical, 1 otherwise.
"""

import json
import sys


def walk(a, b, path, out):
    if type(a) is not type(b):
        out.append((path, a, b))
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            walk(a.get(k, "<missing>"), b.get(k, "<missing>"), f"{path}/{k}", out)
    elif isinstance(a, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append((path, a, b))


def count(node):
    if isinstance(node, dict):
        return sum(count(v) for v in node.values())
    if isinstance(node, list):
        return sum(count(v) for v in node) or 1
    return 1


def main(old, new):
    a = json.load(open(old, encoding="utf-8"))
    b = json.load(open(new, encoding="utf-8"))
    diffs = []
    walk(a, b, "", diffs)
    for path, x, y in diffs:
        print(f"{path}\n   old: {json.dumps(x)[:300]}\n   new: {json.dumps(y)[:300]}")
    print(f"{len(diffs)} difference(s); {count(a)} recorded values")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
