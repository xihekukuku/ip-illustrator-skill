#!/usr/bin/env python3
"""Fail a public release when private artifacts or machine-specific data are present."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


SKIP_DIRS = {".git", ".venv", "venv", "node_modules"}
FORBIDDEN_NAMES = {"__pycache__", ".DS_Store", ".pytest_cache"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".psd"}
TEXT_SUFFIXES = {
    "", ".md", ".txt", ".json", ".yaml", ".yml", ".py", ".toml", ".ini", ".cfg", ".gitignore"
}


def iter_paths(root: Path):
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(name for name in dirs if name not in SKIP_DIRS)
        base = Path(current)
        for name in dirs:
            yield base / name
        for name in sorted(files):
            yield base / name


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".", type=Path)
    parser.add_argument("--deny", action="append", default=[], help="Additional private literal to reject")
    args = parser.parse_args()

    root = args.root.expanduser().resolve(strict=True)
    problems: list[str] = []
    machine_path = re.compile(r"/(?:" + "Users" + r"|" + "home" + r")/[^/\s]+/")
    windows_path = re.compile(r"\b[A-Za-z]:\\")
    for path in iter_paths(root):
        relative = path.relative_to(root)
        if path.name in FORBIDDEN_NAMES or path.suffix == ".pyc":
            problems.append(f"build artifact: {relative}")
        if path.is_symlink():
            try:
                path.resolve(strict=True).relative_to(root)
            except (FileNotFoundError, ValueError):
                problems.append(f"escaping or broken symlink: {relative}")
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
            problems.append(f"binary image is not allowed in the public Skill repository: {relative}")
        if path.is_file() and path.suffix.lower() not in TEXT_SUFFIXES:
            problems.append(f"unapproved public repository file type: {relative}")
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            problems.append(f"non-UTF-8 text file: {relative}")
            continue
        validator_sources = {"ip_pack.py", Path(__file__).name}
        if path.name not in validator_sources and (machine_path.search(text) or windows_path.search(text)):
            problems.append(f"machine-specific absolute path in {relative}")
        if path.name not in validator_sources and "file://" in text:
            problems.append(f"file URL in {relative}")
        if path.name != Path(__file__).name and "github.com/OWNER/" in text:
            problems.append(f"unresolved GitHub owner placeholder in {relative}")
        for denied in args.deny:
            if denied and denied in text:
                problems.append(f"private literal {denied!r} in {relative}")

    if problems:
        for problem in sorted(set(problems)):
            print(f"error: {problem}", file=sys.stderr)
        return 2
    print(f"Public release check passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
