#!/usr/bin/env python3
"""Validate the public Skill's frontmatter, metadata, and required resources."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:
    raise SystemExit("PyYAML is required: python3 -m pip install PyYAML") from exc


REQUIRED_PATHS = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/privacy-and-rights.md",
    "references/ip-pack-format.md",
    "references/turnaround-workflow.md",
    "references/character-spec-template.md",
    "references/visual-style.md",
    "references/article-workflow.md",
    "references/review-output.md",
    "scripts/ip_pack.py",
    "scripts/build_review_longshot.py",
    "scripts/public_release_check.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", type=Path)
    args = parser.parse_args()
    root = args.skill.expanduser().resolve(strict=True)
    problems: list[str] = []

    for relative in REQUIRED_PATHS:
        if not (root / relative).is_file():
            problems.append(f"missing required file: {relative}")

    skill_path = root / "SKILL.md"
    if skill_path.is_file():
        text = skill_path.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
        if not match:
            problems.append("SKILL.md has invalid YAML frontmatter")
        else:
            try:
                frontmatter = yaml.safe_load(match.group(1))
            except yaml.YAMLError as exc:
                problems.append(f"SKILL.md frontmatter YAML error: {exc}")
            else:
                if not isinstance(frontmatter, dict):
                    problems.append("SKILL.md frontmatter must be an object")
                else:
                    if frontmatter.get("name") != root.name:
                        problems.append("frontmatter name must match the Skill directory")
                    description = frontmatter.get("description")
                    if not isinstance(description, str) or not (20 <= len(description) <= 1024):
                        problems.append("frontmatter description must be 20-1024 characters")
                    unexpected = set(frontmatter) - {"name", "description", "license", "compatibility", "metadata"}
                    if unexpected:
                        problems.append("unexpected frontmatter keys: " + ", ".join(sorted(unexpected)))

    metadata_path = root / "agents" / "openai.yaml"
    if metadata_path.is_file():
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            problems.append(f"openai.yaml YAML error: {exc}")
        else:
            interface = metadata.get("interface") if isinstance(metadata, dict) else None
            if not isinstance(interface, dict):
                problems.append("openai.yaml must contain interface")
            else:
                for key in ("display_name", "short_description", "default_prompt"):
                    if not isinstance(interface.get(key), str) or not interface[key].strip():
                        problems.append(f"openai.yaml interface.{key} is required")
                prompt = str(interface.get("default_prompt", ""))
                if "$personal-ip-article-illustrations" not in prompt:
                    problems.append("default_prompt must explicitly invoke the Skill")

    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 2
    print(f"Skill package is valid: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
