#!/usr/bin/env python3
"""Read workspace.yaml: `workspace.py <root> get <dotted.key> [default]` prints the value.

Works without PyYAML for the simple nested `key: value` layout the template uses.
"""
import os, re, sys


def load(root):
    path = os.path.join(root, "workspace.yaml")
    if not os.path.exists(path):
        return {}
    try:
        import yaml
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        out, stack = {}, [(-1, None)]
        with open(path) as f:
            for line in f:
                line = re.sub(r"\s+#.*$", "", line.rstrip("\n"))
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                indent = len(line) - len(line.lstrip())
                key, _, val = line.strip().partition(":")
                while stack[-1][0] >= indent:
                    stack.pop()
                node = out
                for _, k in stack[1:]:
                    node = node.setdefault(k, {})
                val = val.strip().strip('"').strip("'")
                if val == "":
                    stack.append((indent, key))
                    node.setdefault(key, {})
                else:
                    node[key] = {"true": True, "false": False}.get(val, val)
        return out


def get(root, key, default=None):
    node = load(root)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[2] != "get":
        raise SystemExit(__doc__)
    v = get(sys.argv[1], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else None)
    if v is None:
        sys.exit(1)
    print(str(v).lower() if isinstance(v, bool) else v)
