"""
Parses all .py files in this directory into ASTs and serializes the
full project tree to a single JSON file for later visualization.

Output: ast_tree.json (written next to this script)

Usage:
    python format_code.py
"""

import ast
import json
import sys
from pathlib import Path


def serialize(value) -> object:
    """Recursively serialize any AST value into plain JSON-compatible types."""
    if isinstance(value, ast.AST):
        result = {"_type": value.__class__.__name__}
        # Every declared field on the node, no filtering
        for field_name in value._fields:
            result[field_name] = serialize(getattr(value, field_name, None))
        # Source location attributes (separate from _fields)
        for attr_name in value._attributes:
            if hasattr(value, attr_name):
                result[attr_name] = getattr(value, attr_name)
        return result
    if isinstance(value, list):
        return [serialize(item) for item in value]
    # Primitive: str, int, float, bool, None, bytes, complex, Ellipsis
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, bytes):
        return {"_type": "bytes", "value": value.decode("unicode_escape")}
    if isinstance(value, complex):
        return {"_type": "complex", "real": value.real, "imag": value.imag}
    if value is ...:
        return {"_type": "Ellipsis"}
    # Fallback: stringify anything unexpected
    return str(value)


def parse_file(file_path: Path, root: Path) -> dict | None:
    """Parse a single .py file and return its tree dict, or None on error."""
    source = file_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  [SKIP] {file_path.relative_to(root)} — syntax error: {e}", file=sys.stderr)
        return None

    return {
        "file": str(file_path.relative_to(root)),
        "source": source,
        "tree": serialize(tree),
    }


def main() -> None:
    root = Path(__file__).resolve().parent
    output_path = root / "ast_tree.json"

    py_files = sorted(root.rglob("*.py"))
    # Exclude this script itself
    py_files = [f for f in py_files if f.resolve() != Path(__file__).resolve()]

    project = {"project_root": root.name, "files": []}

    for py_file in py_files:
        print(f"Parsing: {py_file.relative_to(root)}")
        parsed = parse_file(py_file, root)
        if parsed is None:
            continue
        project["files"].append(parsed)

    output_path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    print(f"\nDone. AST tree written to: {output_path}")
    print(f"  Files parsed: {len(project['files'])}")


if __name__ == "__main__":
    main()