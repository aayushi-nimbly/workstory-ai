"""Validate an experience JSON file.

Usage:
    uv run workstory-validate path/to/workstory-experience.json

Exit code is 0 when the file is valid (warnings allowed) and 1 otherwise.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from app.experience.checks import Issue, check_references
from app.experience.models import ExperienceFile


@dataclass
class ValidationResult:
    data: ExperienceFile | None
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    @property
    def is_valid(self) -> bool:
        return self.data is not None and not self.errors


def _format_location(loc: tuple[int | str, ...]) -> str:
    path = ""
    for part in loc:
        path += f"[{part}]" if isinstance(part, int) else (f".{part}" if path else str(part))
    return path or "(root)"


def validate_data(raw: object) -> ValidationResult:
    """Validate already-parsed JSON data."""
    try:
        data = ExperienceFile.model_validate(raw)
    except ValidationError as exc:
        issues = [Issue("error", _format_location(err["loc"]), err["msg"]) for err in exc.errors()]
        return ValidationResult(data=None, issues=issues)
    return ValidationResult(data=data, issues=check_references(data))


def validate_file(path: Path) -> ValidationResult:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ValidationResult(None, [Issue("error", str(path), "file not found")])
    except json.JSONDecodeError as exc:
        return ValidationResult(
            None, [Issue("error", str(path), f"invalid JSON at line {exc.lineno}: {exc.msg}")]
        )
    return validate_data(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a WorkStory experience JSON file.")
    parser.add_argument("file", type=Path)
    args = parser.parse_args(argv)

    result = validate_file(args.file)
    for issue in result.issues:
        print(issue)

    if result.is_valid:
        data = result.data
        assert data is not None
        print(
            f"\n✓ Valid: {len(data.projects)} projects, {len(data.pull_requests)} PRs, "
            f"{len(data.skills)} skills, {len(data.categories)} categories, "
            f"{len(result.warnings)} warning(s)."
        )
        return 0

    print(f"\n✗ Invalid: {len(result.errors)} error(s), {len(result.warnings)} warning(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
